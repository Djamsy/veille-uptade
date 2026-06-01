# backend/services/social_alerts_service.py
"""
Alertes réseaux sociaux — détection automatique + notification Telegram.

Deux détecteurs, exécutés après chaque scrape de stats/commentaires :

  • VIRAL    — un post dont les vues dépassent nettement la médiane récente
               du compte (pic de performance à valoriser).
  • BAD BUZZ — un post dont une part importante des commentaires est
               négative (à surveiller / modérer).

Chaque post n'est alerté qu'une seule fois par type (drapeaux
`viral_alerted_at` / `badbuzz_alerted_at`), pour éviter le spam.

Seuils configurables par variables d'environnement (valeurs par défaut
raisonnables) — voir constantes ci-dessous.
"""

import os
import logging
import re
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any, Dict, List

logger = logging.getLogger("veille.social_alerts")

# ── Seuils (surchargables par env) ─────────────────────────────────
VIRAL_MULTIPLIER = float(os.getenv("SOCIAL_VIRAL_MULTIPLIER", "3"))      # x médiane
VIRAL_MIN_VIEWS = int(os.getenv("SOCIAL_VIRAL_MIN_VIEWS", "1000"))       # plancher absolu
BADBUZZ_RATIO = float(os.getenv("SOCIAL_BADBUZZ_RATIO", "0.4"))          # part de comm. négatifs
BADBUZZ_MIN_COMMENTS = int(os.getenv("SOCIAL_BADBUZZ_MIN_COMMENTS", "10"))
LOOKBACK_DAYS = int(os.getenv("SOCIAL_ALERTS_LOOKBACK_DAYS", "3"))       # posts récents à examiner
BASELINE_DAYS = int(os.getenv("SOCIAL_ALERTS_BASELINE_DAYS", "30"))      # fenêtre pour la médiane

# Marqueurs de négativité (français) — heuristique légère, sans coût IA.
_NEG_MARKERS = [
    "honte", "honteux", "scandale", "scandaleux", "nul", "nulle", "inadmissible",
    "inacceptable", "incompétent", "incompetent", "mensonge", "menteur", "arnaque",
    "corruption", "corrompu", "démission", "demission", "ras-le-bol", "ras le bol",
    "marre", "dégoût", "degout", "honteuse", "catastrophe", "lamentable", "pitoyable",
    "n'importe quoi", "nimporte quoi", "foutage", "honteusement", "déçu", "decu",
    "déception", "deception", "colère", "colere", "révoltant", "revoltant", "abusé",
    "abuse", "abusif", "🤬", "😡", "👎", "honteux!", "rien à faire", "rien a faire",
]
_NEG_RE = re.compile("|".join(re.escape(m) for m in _NEG_MARKERS), re.IGNORECASE)


def _v(post: Dict, key: str) -> int:
    """Valeur agrégée d'une stat (vues/likes/commentaires)."""
    return int((post.get("stats") or {}).get(key, 0) or 0)


def _is_negative(text: str) -> bool:
    return bool(text) and bool(_NEG_RE.search(text))


def _send(text: str) -> bool:
    try:
        from backend.services.telegram_service import send_message, is_configured
        if not is_configured():
            return False
        return send_message(text)
    except Exception as e:
        logger.warning(f"Alerte Telegram échouée: {e}")
        return False


def check_social_alerts(db) -> Dict[str, Any]:
    """Examine les posts récents et envoie les alertes virales / bad buzz.

    Renvoie un récapitulatif {viral, badbuzz, checked}.
    """
    now = datetime.now(timezone.utc)
    recent_cut = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    baseline_cut = (now - timedelta(days=BASELINE_DAYS)).isoformat()

    # Baseline par plateforme : médiane des vues sur la fenêtre large.
    baseline = list(db["campaign_posts"].find(
        {"published_at": {"$gte": baseline_cut}},
        {"platform": 1, "stats": 1},
    ))
    median_views: Dict[str, float] = {}
    by_plat: Dict[str, List[int]] = {}
    for p in baseline:
        plat = p.get("platform", "")
        v = _v(p, "views")
        if v > 0:
            by_plat.setdefault(plat, []).append(v)
    for plat, vals in by_plat.items():
        median_views[plat] = median(vals) if vals else 0

    # Posts récents à examiner.
    recent = list(db["campaign_posts"].find(
        {"published_at": {"$gte": recent_cut}},
        {"title": 1, "url": 1, "platform": 1, "stats": 1, "comments_scraped": 1,
         "viral_alerted_at": 1, "badbuzz_alerted_at": 1},
    ))

    viral_sent = badbuzz_sent = 0

    for post in recent:
        pid = post.get("_id")
        plat = post.get("platform", "")
        title = (post.get("title") or "(sans titre)")[:120]
        url = post.get("url", "")
        views = _v(post, "views")

        # ── Détecteur VIRAL ────────────────────────────────────
        if not post.get("viral_alerted_at"):
            med = median_views.get(plat, 0)
            threshold = max(VIRAL_MIN_VIEWS, med * VIRAL_MULTIPLIER)
            if views >= threshold and views >= VIRAL_MIN_VIEWS and med > 0:
                ratio = views / med if med else 0
                text = (
                    f"🚀 <b>POST VIRAL — {plat.capitalize()}</b>\n"
                    f"{title}\n"
                    f"👁 {views:,} vues (×{ratio:.1f} vs médiane) · "
                    f"❤️ {_v(post, 'likes'):,} · 💬 {_v(post, 'comments'):,}"
                ).replace(",", " ")
                if url:
                    text += f"\n🔗 {url}"
                if _send(text):
                    db["campaign_posts"].update_one(
                        {"_id": pid}, {"$set": {"viral_alerted_at": now.isoformat()}})
                    viral_sent += 1

        # ── Détecteur BAD BUZZ ─────────────────────────────────
        if not post.get("badbuzz_alerted_at"):
            comments = [c for c in (post.get("comments_scraped") or [])
                        if isinstance(c, dict) and c.get("text")]
            if len(comments) >= BADBUZZ_MIN_COMMENTS:
                neg = sum(1 for c in comments if _is_negative(c.get("text", "")))
                ratio = neg / len(comments)
                if ratio >= BADBUZZ_RATIO:
                    text = (
                        f"⚠️ <b>BAD BUZZ POTENTIEL — {plat.capitalize()}</b>\n"
                        f"{title}\n"
                        f"💬 {neg}/{len(comments)} commentaires négatifs "
                        f"({ratio * 100:.0f}%)"
                    )
                    if url:
                        text += f"\n🔗 {url}"
                    if _send(text):
                        db["campaign_posts"].update_one(
                            {"_id": pid}, {"$set": {"badbuzz_alerted_at": now.isoformat()}})
                        badbuzz_sent += 1

    logger.info(f"🔔 Alertes RS — viral: {viral_sent}, bad buzz: {badbuzz_sent} (sur {len(recent)} posts récents)")
    return {"ok": True, "viral": viral_sent, "badbuzz": badbuzz_sent, "checked": len(recent)}
