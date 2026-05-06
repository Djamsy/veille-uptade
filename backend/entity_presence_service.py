# backend/entity_presence_service.py
"""
Service d'extraction de la présence d'entités (élus / personnalités politiques)
à partir des articles enrichis.

Pipeline :
1. Pré-filtre rapide (regex sur ELECTED_ALIASES) pour ne traiter que les articles
   qui mentionnent au moins un élu connu — évite les appels LLM inutiles.
2. Extraction structurée via OpenAI/Groq (ai_groq_service._call_ai) :
   - Quels élus de la liste V1 sont présents ?
   - Dans quelle commune ? (priorité forte sur la commune)
   - Quartier si identifiable.
   - presence_type ∈ {officiel, mandat, terrain, communication, mention}
   - mention = simple citation sans déplacement physique → on rejette en V1.
3. Stockage dans la collection `entity_presences`.

Design notes :
- V1 = élus déjà en base (ELECTED_ALIASES ⊂ entity_aliases.py — 40 entités).
- Pas d'enrichissement manuel de la liste, on travaille avec l'existant.
- Aucun TTL sur la collection (durée d'observation indéfinie).
- Service idempotent : on dédoublonne par (article_id, entity_canonical, commune).

Usage minimal :
    from entity_presence_service import extract_presences_from_article
    presences = extract_presences_from_article(article_dict)
    # → liste de dicts prêts à insérer dans la collection
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("entity_presence_service")

# ============================================================
# Imports locaux — fallbacks pour package vs script direct
# ============================================================
try:
    from backend.entity_aliases import ELECTED_ALIASES, _normalize  # type: ignore
except ImportError:  # pragma: no cover
    from entity_aliases import ELECTED_ALIASES, _normalize  # type: ignore

try:
    from backend.ai_groq_service import _call_ai, is_available as ai_is_available  # type: ignore
except ImportError:  # pragma: no cover
    from ai_groq_service import _call_ai, is_available as ai_is_available  # type: ignore


# ============================================================
# Constantes
# ============================================================

# Communes de Guadeloupe (32 communes officielles)
GUADELOUPE_COMMUNES: List[str] = [
    "Les Abymes", "Anse-Bertrand", "Baie-Mahault", "Baillif", "Basse-Terre",
    "Bouillante", "Capesterre-Belle-Eau", "Capesterre-de-Marie-Galante",
    "Deshaies", "La Désirade", "Le Gosier", "Gourbeyre", "Goyave",
    "Grand-Bourg", "Lamentin", "Morne-à-l'Eau", "Le Moule", "Petit-Bourg",
    "Petit-Canal", "Pointe-à-Pitre", "Pointe-Noire", "Port-Louis",
    "Saint-Claude", "Saint-François", "Saint-Louis", "Sainte-Anne",
    "Sainte-Rose", "Terre-de-Bas", "Terre-de-Haut", "Trois-Rivières",
    "Vieux-Fort", "Vieux-Habitants",
]

# Types de présence acceptés (politique/professionnelle uniquement)
ACCEPTED_PRESENCE_TYPES = {"officiel", "mandat", "terrain", "communication"}

# Prompt système — extraction structurée
_SYSTEM_PROMPT = """Tu es un extracteur de présence d'élus dans des articles de presse de Guadeloupe.

OBJECTIF : pour chaque article, identifier les élus de la liste fournie qui sont MENTIONNÉS COMME PRÉSENTS PHYSIQUEMENT (déplacement, événement, inauguration, conseil, terrain, communication officielle), avec la commune où ils étaient.

RÈGLES STRICTES :
1. Tu ne réponds QUE pour les élus de la liste « élus_v1 » fournie. Aucun autre nom.
2. Tu n'inventes pas. Si l'article ne précise pas la commune, tu mets commune=null (on jettera l'entrée).
3. presence_type doit être l'un de : officiel | mandat | terrain | communication
   - officiel : cérémonie, signature, inauguration, conseil municipal/régional/départemental
   - mandat : exercice du mandat (réunion publique, commission, vote)
   - terrain : visite de quartier, rencontre habitants, déplacement local
   - communication : conférence de presse, communiqué localisé
4. REJETTE les présences de loisirs/vie privée (vacances, sport perso, événement familial). Ne renvoie rien dans ce cas.
5. REJETTE les simples citations sans déplacement (ex : « le maire X a réagi sur Twitter »). Ne renvoie rien.
6. Quartier : seulement si l'article le nomme explicitement, sinon null.
7. confidence ∈ [0.0, 1.0] — ta certitude sur la commune.

FORMAT DE SORTIE — JSON strict :
{
  "presences": [
    {
      "entity": "Nom canonique de l'élu (exactement comme dans la liste)",
      "commune": "Nom de commune ou null",
      "quartier": "Nom de quartier ou null",
      "presence_type": "officiel | mandat | terrain | communication",
      "context": "extrait textuel de l'article qui justifie (max 200 chars)",
      "confidence": 0.0
    }
  ]
}

Si aucun élu de la liste n'est présent physiquement dans l'article, retourne {"presences": []}.
"""


# ============================================================
# Pré-filtre regex
# ============================================================

def _quick_match_elected(text: str) -> List[str]:
    """Détection rapide regex : retourne les noms canoniques d'élus mentionnés.

    Bypass complet de l'IA si aucun match → économie d'API.
    """
    if not text:
        return []
    norm = _normalize(text)
    found = []
    for canonical, aliases in ELECTED_ALIASES.items():
        # Match sur la forme canonique normalisée + chaque alias
        all_forms = [_normalize(canonical)] + [_normalize(a) for a in aliases]
        for form in all_forms:
            if not form:
                continue
            # Word boundaries pour éviter les faux positifs (« losbar » dans « losbartholomew »)
            pattern = r"\b" + re.escape(form) + r"\b"
            if re.search(pattern, norm):
                found.append(canonical)
                break
    return found


# ============================================================
# Extraction LLM
# ============================================================

def _build_user_prompt(article: Dict[str, Any], shortlist: List[str]) -> str:
    """Construit le prompt utilisateur en limitant la liste d'élus à la shortlist regex."""
    title = (article.get("title") or "").strip()
    summary = (article.get("ai_summary") or article.get("summary") or "").strip()
    content = (article.get("content") or "").strip()

    # On tronque pour éviter de dépasser la fenêtre de contexte / coûter cher
    if len(content) > 3000:
        content = content[:3000] + "…"

    return (
        f"élus_v1 (forme canonique exacte attendue) :\n"
        f"{', '.join(shortlist)}\n\n"
        f"Article :\n"
        f"Titre : {title}\n"
        f"Résumé : {summary}\n"
        f"Contenu : {content}\n\n"
        f"Réponds en JSON strict selon le format demandé."
    )


def _validate_presence(p: Dict[str, Any], allowed_entities: List[str]) -> bool:
    """Valide une entrée renvoyée par le LLM."""
    if not isinstance(p, dict):
        return False
    if p.get("entity") not in allowed_entities:
        return False
    if p.get("presence_type") not in ACCEPTED_PRESENCE_TYPES:
        return False
    if not p.get("commune"):
        return False
    # La commune doit appartenir à la liste officielle (matching souple)
    commune_norm = _normalize(p["commune"])
    if not any(_normalize(c) == commune_norm for c in GUADELOUPE_COMMUNES):
        return False
    return True


def _canonicalize_commune(commune: str) -> Optional[str]:
    """Retourne la forme canonique de la commune (depuis GUADELOUPE_COMMUNES)."""
    if not commune:
        return None
    target = _normalize(commune)
    for c in GUADELOUPE_COMMUNES:
        if _normalize(c) == target:
            return c
    return None


def extract_presences_from_article(article: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extrait les présences d'élus à partir d'un article.

    Args:
        article: dict avec au moins 'title' et idéalement 'content' / 'ai_summary' / 'summary'.
                 Doit avoir 'article_id' ou '_id' pour le lien.

    Returns:
        Liste de dicts prêts à insérer dans la collection `entity_presences`.
        Chaque entrée : {
            entity_canonical, entity_role,
            article_id, source, published_at,
            commune, quartier, presence_type,
            context_snippet, confidence,
            extracted_at, extraction_method
        }
        Liste vide si rien à stocker (article hors scope ou IA indispo sans match regex).
    """
    if not article:
        return []

    text = " ".join(filter(None, [
        article.get("title"),
        article.get("ai_summary"),
        article.get("summary"),
        article.get("content"),
    ]))

    # 1) Pré-filtre regex
    shortlist = _quick_match_elected(text)
    if not shortlist:
        return []  # aucun élu V1 mentionné — skip

    # 2) Si l'IA n'est pas disponible, on s'arrête là (pas de stockage sans validation LLM)
    if not ai_is_available():
        logger.warning("⚠️ IA indisponible — skip extraction présence (pré-filtre OK pour %s)", shortlist)
        return []

    # 3) Appel LLM structuré
    user_prompt = _build_user_prompt(article, shortlist)
    raw = _call_ai(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=800,
        json_mode=True,
    )
    if not raw:
        logger.warning("LLM presence extraction: pas de réponse pour article %s", article.get("article_id"))
        return []

    # 4) Parsing & validation
    import json
    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning("LLM presence: JSON invalide (%s): %s", e, raw[:200])
        return []

    candidates = data.get("presences") or []
    if not isinstance(candidates, list):
        return []

    article_id = article.get("article_id") or str(article.get("_id") or "")
    source = article.get("source") or article.get("source_name")
    pub_at = article.get("published_at") or article.get("date") or article.get("scraped_at")
    if isinstance(pub_at, str):
        try:
            pub_at = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
        except Exception:
            pub_at = None

    out: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for p in candidates:
        if not _validate_presence(p, shortlist):
            continue
        commune_canon = _canonicalize_commune(p["commune"])
        if not commune_canon:
            continue

        confidence = p.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else 0.7
        except Exception:
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        out.append({
            "entity_canonical": p["entity"],
            "entity_role": "elu",  # V1 : tous les élus de ELECTED_ALIASES
            "article_id": article_id,
            "source": source,
            "published_at": pub_at,
            "commune": commune_canon,
            "quartier": (p.get("quartier") or None) if isinstance(p.get("quartier"), str) else None,
            "presence_type": p["presence_type"],
            "context_snippet": (p.get("context") or "")[:200],
            "confidence": confidence,
            "extracted_at": now,
            "extraction_method": "llm_v1",
        })

    return out


# ============================================================
# Helpers d'agrégation (utilisés par le router admin)
# ============================================================

def aggregate_by_commune(presences_collection, period_days: Optional[int] = None,
                         entity: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Agrégation par commune sur la fenêtre [now - period_days, now].

    Args:
        presences_collection: pymongo collection `entity_presences`.
        period_days: nombre de jours rétroactifs (None = pas de filtre temporel).
        entity: nom canonique d'un élu pour filtrer (None = toutes).

    Returns:
        [{commune, count, top_entities: [{entity, count}], last_seen}]
    """
    match: Dict[str, Any] = {}
    if period_days:
        from datetime import timedelta
        match["published_at"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=period_days)}
    if entity:
        match["entity_canonical"] = entity

    pipeline: List[Dict[str, Any]] = [
        {"$match": match},
        {"$group": {
            "_id": "$commune",
            "count": {"$sum": 1},
            "last_seen": {"$max": "$published_at"},
            "entities": {"$push": "$entity_canonical"},
        }},
        {"$sort": {"count": -1}},
    ]
    out = []
    for row in presences_collection.aggregate(pipeline):
        # Top 3 entités par fréquence dans cette commune
        from collections import Counter
        top = Counter(row.get("entities") or []).most_common(3)
        out.append({
            "commune": row["_id"],
            "count": row["count"],
            "last_seen": row["last_seen"],
            "top_entities": [{"entity": e, "count": c} for e, c in top],
        })
    return out


def aggregate_by_entity(presences_collection, entity: str,
                        period_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Vue par élu : ses communes de présence et timeline.
    """
    match: Dict[str, Any] = {"entity_canonical": entity}
    if period_days:
        from datetime import timedelta
        match["published_at"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=period_days)}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$commune",
            "count": {"$sum": 1},
            "last_seen": {"$max": "$published_at"},
            "presence_types": {"$addToSet": "$presence_type"},
        }},
        {"$sort": {"count": -1}},
    ]
    communes = []
    for row in presences_collection.aggregate(pipeline):
        communes.append({
            "commune": row["_id"],
            "count": row["count"],
            "last_seen": row["last_seen"],
            "presence_types": row.get("presence_types") or [],
        })
    return {
        "entity": entity,
        "communes": communes,
        "total_presences": sum(c["count"] for c in communes),
    }


__all__ = [
    "GUADELOUPE_COMMUNES",
    "ACCEPTED_PRESENCE_TYPES",
    "extract_presences_from_article",
    "aggregate_by_commune",
    "aggregate_by_entity",
]
