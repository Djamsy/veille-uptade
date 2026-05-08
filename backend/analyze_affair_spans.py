#!/usr/bin/env python3
"""
ANALYSE DES CYCLES D'AFFAIRES
=============================

Ce script inspecte la collection `affairs` et calcule, par catégorie
d'événement, la durée réelle entre le premier et le dernier article
de chaque affaire. L'objectif est d'ajuster finement les valeurs de
FUSION_WINDOW_BY_CATEGORY dans affair_lifecycle_service.py.

Pour chaque catégorie (meurtre_arme, justice_proces, election_politique, …),
on affiche :
  - nombre d'affaires
  - item_count moyen
  - durée min / médiane / p75 / p90 / max (en jours)
  - recommandation de fenêtre (médiane arrondie vers le haut, bornée
    à [2, 21] jours)

USAGE :
  python analyze_affair_spans.py                # texte
  python analyze_affair_spans.py --json         # JSON pour export
  python analyze_affair_spans.py --min-items 2  # ne garde que les affaires
                                                 # avec >= 2 articles
"""

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("❌ pymongo manquant. `pip install pymongo`")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "veille_media")

# Réplique allégée de EVENT_CATEGORIES pour la classification locale.
# (Reste synchro avec affair_lifecycle_service.EVENT_CATEGORIES.)
EVENT_CATEGORIES = {
    "meurtre_arme": {"meurtre", "tué", "tuée", "tué par balles", "tuée par balles",
                     "assassiné", "assassinée", "homicide", "coups de couteau",
                     "coups de feu", "fusillade", "balle", "balles", "poignardé",
                     "poignardée", "féminicide", "tentative de meurtre"},
    "deces_retrouve_sans_vie": {"retrouvé sans vie", "retrouvée sans vie",
                                "retrouvé mort", "retrouvée morte", "corps retrouvé",
                                "corps sans vie", "décédé", "décédée", "décès",
                                "cadavre", "dépouille"},
    "violence_conjugale": {"violence conjugale", "violences conjugales",
                           "violences intrafamiliales", "femme battue",
                           "conjoint violent", "ex-compagnon"},
    "noyade_accident_mer": {"noyade", "noyé", "noyée", "plongeur", "plongée",
                            "disparition en mer", "baignade", "accident maritime",
                            "corps repêché", "sauvetage en mer"},
    "accident_route": {"accident de la route", "collision", "accident mortel",
                       "renversé", "percuté", "chauffard", "motocycliste",
                       "piéton fauché", "sortie de route"},
    "election_politique": {"élection", "election", "élu", "élue", "candidat",
                           "scrutin", "vote", "campagne électorale", "municipales",
                           "législatives", "second tour"},
    "catastrophe_naturelle": {"cyclone", "ouragan", "tempête tropicale", "séisme",
                              "tremblement", "inondation", "glissement de terrain",
                              "alerte météo", "vigilance rouge", "vigilance orange"},
    "greve_mouvement_social": {"grève", "manifestation", "blocage", "barrage",
                               "mobilisation", "mouvement social", "syndicat",
                               "débrayage"},
    "sante_epidemie": {"dengue", "épidémie", "pandémie", "covid", "virus",
                       "contamination", "chlordécone", "sargasses", "intoxication"},
    "justice_proces": {"procès", "tribunal", "condamné", "condamnée", "jugement",
                       "audience", "garde à vue", "mis en examen", "détention",
                       "incarcéré", "réquisitions", "verdict", "assises"},
    "trafic_drogue": {"trafic de drogue", "stupéfiants", "cocaïne", "cannabis",
                      "saisie de drogue", "trafiquant", "réseau de drogue"},
    "agriculture_economie": {"campagne sucrière", "sucrière", "canne", "récolte",
                             "plantation", "agricole", "banane", "rhum",
                             "distillerie", "filière"},
    "memoire_esclavage": {"esclavage", "esclave", "abolition", "traite", "négrière",
                          "commémoration de l'abolition", "22 mai", "27 mai",
                          "marronnage"},
    "commemoration_ceremonie": {"commémoration", "cérémonie", "hommage",
                                "recueillement", "gerbe", "monument", "mémorial",
                                "dépôt de gerbe", "minute de silence"},
}

CURRENT_DEFAULTS = {
    "meurtre_arme": 3, "deces_retrouve_sans_vie": 3, "noyade_accident_mer": 3,
    "accident_route": 3, "violence_conjugale": 7, "greve_mouvement_social": 7,
    "sante_epidemie": 7, "catastrophe_naturelle": 7, "trafic_drogue": 7,
    "justice_proces": 14, "election_politique": 14, "agriculture_economie": 10,
    "memoire_esclavage": 10, "commemoration_ceremonie": 10,
}


def detect_category(text: str):
    if not text:
        return None
    t = text.lower()
    best = (None, 0)
    for name, kws in EVENT_CATEGORIES.items():
        score = sum(1 for kw in kws if kw in t)
        if score > best[1]:
            best = (name, score)
    return best[0] if best[1] >= 1 else None


def parse_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str):
        try:
            s = v.replace("Z", "+00:00") if v.endswith("Z") else v
            dt = datetime.fromisoformat(s)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None


def percentile(values, p):
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def recommend_window(spans_days):
    """Recommandation = p75 arrondi au jour supérieur, borné [2, 21]."""
    if not spans_days:
        return None
    p75 = percentile(spans_days, 0.75)
    rec = max(2, min(21, int(p75) + (1 if p75 % 1 > 0 else 0)))
    return rec


def analyze(min_items: int):
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ismaster")
    except Exception as e:
        print(f"❌ MongoDB: {e}")
        return 2
    db = client[DB_NAME]

    total = 0
    by_cat = defaultdict(lambda: {"spans": [], "items": [], "count": 0})
    uncategorized = {"spans": [], "items": [], "count": 0}

    for aff in db["affairs"].find({}):
        total += 1
        item_count = aff.get("item_count", 1)
        if item_count < min_items:
            continue
        start = parse_dt(aff.get("created_at") or aff.get("promoted_at"))
        end = parse_dt(aff.get("last_activity")) or start
        if start is None or end is None:
            continue
        span_days = max(0.0, (end - start).total_seconds() / 86400.0)
        cat = detect_category(f"{aff.get('title', '')} {aff.get('description', '')}")
        bucket = by_cat[cat] if cat else uncategorized
        bucket["spans"].append(span_days)
        bucket["items"].append(item_count)
        bucket["count"] += 1

    return _format_report(total, by_cat, uncategorized, min_items)


def _format_report(total, by_cat, uncategorized, min_items):
    report = {
        "total_affairs": total,
        "min_items_filter": min_items,
        "per_category": {},
        "uncategorized": {},
    }

    def stats(spans, items):
        if not spans:
            return None
        return {
            "count": len(spans),
            "avg_items": round(statistics.mean(items), 1),
            "min_days": round(min(spans), 1),
            "median_days": round(statistics.median(spans), 1),
            "p75_days": round(percentile(spans, 0.75), 1),
            "p90_days": round(percentile(spans, 0.90), 1),
            "max_days": round(max(spans), 1),
            "recommended_window_days": recommend_window(spans),
            "current_default": CURRENT_DEFAULTS.get("__placeholder__"),
        }

    for cat, data in by_cat.items():
        s = stats(data["spans"], data["items"])
        if s:
            s["current_default"] = CURRENT_DEFAULTS.get(cat, "—")
            report["per_category"][cat] = s

    u = stats(uncategorized["spans"], uncategorized["items"])
    if u:
        report["uncategorized"] = u

    return report


def print_text(report):
    print("=" * 78)
    print(f"📊 ANALYSE DES DURÉES D'AFFAIRES — {report['total_affairs']} affaires au total")
    print(f"   (filtre : au moins {report['min_items_filter']} article(s) par affaire)")
    print("=" * 78)
    print()
    cols = f"{'Catégorie':<28}{'N':>5}{'⌀items':>8}{'médiane':>10}{'p75':>8}{'p90':>8}{'max':>8}{'reco':>7}{'actuel':>9}"
    print(cols)
    print("-" * len(cols))
    for cat, s in sorted(report["per_category"].items(), key=lambda kv: -kv[1]["count"]):
        print(
            f"{cat:<28}{s['count']:>5}{s['avg_items']:>8.1f}"
            f"{s['median_days']:>9.1f}j{s['p75_days']:>7.1f}j{s['p90_days']:>7.1f}j"
            f"{s['max_days']:>7.1f}j{s['recommended_window_days']:>6}j"
            f"{str(s['current_default']):>8}j"
        )
    if report.get("uncategorized") and report["uncategorized"].get("count"):
        u = report["uncategorized"]
        print("-" * len(cols))
        print(
            f"{'(non classifié)':<28}{u['count']:>5}{u['avg_items']:>8.1f}"
            f"{u['median_days']:>9.1f}j{u['p75_days']:>7.1f}j{u['p90_days']:>7.1f}j"
            f"{u['max_days']:>7.1f}j{u['recommended_window_days']:>6}j{'—':>8}"
        )
    print()
    print("💡 Légende :")
    print("   médiane = 50 % des affaires ont une durée ≤ cette valeur")
    print("   p75     = 75 % des affaires ont une durée ≤ cette valeur")
    print("   reco    = fenêtre recommandée (p75 arrondi, borné [2, 21])")
    print("   actuel  = valeur actuellement dans FUSION_WINDOW_BY_CATEGORY")
    print()
    # Alertes si écart recommandation vs actuel > 2 jours
    diffs = []
    for cat, s in report["per_category"].items():
        cur = s["current_default"]
        rec = s["recommended_window_days"]
        if isinstance(cur, int) and rec and abs(rec - cur) >= 3:
            diffs.append((cat, cur, rec))
    if diffs:
        print("⚠️  Catégories où la valeur actuelle diverge ≥ 3j du recommandé :")
        for cat, cur, rec in diffs:
            arrow = "↑" if rec > cur else "↓"
            print(f"   {arrow} {cat:<28} actuel={cur}j → reco={rec}j")
    else:
        print("✅ Les valeurs actuelles sont cohérentes avec les données observées.")


def main():
    parser = argparse.ArgumentParser(description="Analyse des cycles d'affaires")
    parser.add_argument("--json", action="store_true", help="Sortie JSON brute")
    parser.add_argument("--min-items", type=int, default=2,
                        help="Min d'articles par affaire (défaut 2)")
    args = parser.parse_args()

    report = analyze(args.min_items)
    if isinstance(report, int):
        sys.exit(report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)


if __name__ == "__main__":
    main()
