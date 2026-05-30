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
from backend.entity_aliases import ELECTED_ALIASES, _normalize

try:
    from backend.elus_database import get_mandat_commune  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from elus_database import get_mandat_commune  # type: ignore
    except ImportError:
        def get_mandat_commune(name: str):  # fallback no-op
            return None

from backend.ai_groq_service import _call_ai, is_available as ai_is_available


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

# Catégories de haut niveau (orthogonales à presence_type)
ACCEPTED_EVENT_KINDS = {"presence", "reaction"}

# Aliases trop génériques à ignorer au pré-filtre (provoquent des faux positifs)
# Si tu veux désactiver ce filtre, vide simplement ce set.
_GENERIC_ALIAS_DENYLIST = {
    "le maire", "la maire", "le président", "la présidente",
    "le president", "la presidente", "le préfet", "la préfète",
    "le prefet", "la prefete", "le procureur", "la procureure",
    "le ministre", "la ministre", "le député", "la députée",
    "le depute", "la deputee", "le sénateur", "la sénatrice",
    "le senateur", "la senatrice",
}

# Longueur minimale pour qu'un alias soit utilisé au pré-filtre (drop "jp", "mc"…)
_MIN_ALIAS_LENGTH = 5

# Distance max (en caractères) entre le nom de l'élu et la commune dans le texte source
# pour considérer le lien comme valide. ~200 chars ≈ une phrase.
_MAX_ENTITY_COMMUNE_DISTANCE = 280

# Prompt système — extraction structurée
_SYSTEM_PROMPT = """Tu es un extracteur de présence d'élus dans des articles de presse de Guadeloupe.

OBJECTIF : pour chaque article, identifier les élus de la liste fournie, et déterminer pour chacun :
A) s'il était PHYSIQUEMENT PRÉSENT quelque part (présence)
   OU s'il a seulement RÉAGI à un événement sans s'y être déplacé (réaction).
B) le lieu (commune) qui s'y rattache.

RÈGLES STRICTES :
1. Tu ne réponds QUE pour les élus de la liste « élus_v1 » fournie. Aucun autre nom. Aucun alias générique (« le maire », « le président ») ne suffit — le nom de famille doit apparaître explicitement.
2. event_kind doit être l'un de :
   - "presence" : l'élu était SUR PLACE (déplacement, événement, inauguration, conseil municipal, visite, terrain, conférence de presse SUR le terrain).
   - "reaction" : l'élu COMMENTE / réagit / déclare DEPUIS AILLEURS (tweet, communiqué, interview à distance, prise de position). Il n'est PAS sur place.
3. La commune dépend de event_kind :
   - "presence" → commune = LIEU où l'élu se trouvait physiquement.
   - "reaction" → commune = SUJET de la réaction (l'événement qui se passe ailleurs).
4. presence_type précise la nature : officiel | mandat | terrain | communication
   - officiel : cérémonie, signature, inauguration, conseil municipal/régional/départemental
   - mandat : exercice du mandat (réunion publique, commission, vote)
   - terrain : visite de quartier, rencontre habitants, déplacement local
   - communication : conférence de presse, communiqué, interview, post réseaux sociaux
5. CRITICAL : le nom de l'élu et la commune DOIVENT apparaître dans la même phrase ou dans des phrases contiguës. Sinon n'extrais rien.
6. REJETTE les présences de loisirs/vie privée (vacances, sport perso, événement familial).
7. Si l'article cite l'élu sans qu'aucune commune ne soit précisée → ne renvoie rien.
8. confidence ∈ [0.0, 1.0] — ta certitude sur le couple (élu, commune, event_kind).

FORMAT DE SORTIE — JSON strict :
{
  "presences": [
    {
      "entity": "Nom canonique de l'élu (exactement comme dans la liste)",
      "event_kind": "presence | reaction",
      "commune": "Nom de commune",
      "quartier": "Nom de quartier ou null",
      "presence_type": "officiel | mandat | terrain | communication",
      "context": "extrait textuel COMPLET (la ou les phrases) où l'élu ET la commune sont mentionnés (max 300 chars)",
      "confidence": 0.0
    }
  ]
}

Si rien d'extractible : {"presences": []}.
"""


# ============================================================
# Pré-filtre regex
# ============================================================

def _is_useful_alias(alias_norm: str) -> bool:
    """Filtre les alias trop courts ou trop génériques (« le maire », « le préfet »…)
    qui produisent des faux positifs en pré-filtre.
    """
    if not alias_norm:
        return False
    if len(alias_norm) < _MIN_ALIAS_LENGTH:
        return False
    if alias_norm in _GENERIC_ALIAS_DENYLIST:
        return False
    return True


def _quick_match_elected(text: str) -> List[str]:
    """Détection rapide regex : retourne les noms canoniques d'élus mentionnés.

    Bypass complet de l'IA si aucun match → économie d'API.
    Drop les alias génériques (« le maire ») et trop courts (< 5 chars).
    """
    if not text:
        return []
    norm = _normalize(text)
    found = []
    for canonical, aliases in ELECTED_ALIASES.items():
        # Match sur la forme canonique normalisée + chaque alias non-générique
        all_forms = [_normalize(canonical)] + [_normalize(a) for a in aliases]
        for form in all_forms:
            if not _is_useful_alias(form):
                continue
            # Word boundaries pour éviter les faux positifs (« losbar » dans « losbartholomew »)
            pattern = r"\b" + re.escape(form) + r"\b"
            if re.search(pattern, norm):
                found.append(canonical)
                break
    return found


def _commune_search_variants(commune: str) -> List[str]:
    """
    Génère les variantes textuelles d'une commune pour la recherche.
    « Les Abymes » → ["les abymes", "abymes"] (couvre « aux Abymes », « à Abymes »).
    « Le Gosier » → ["le gosier", "gosier"]
    """
    if not commune:
        return []
    base = _normalize(commune)
    variants = {base}
    for prefix in ("les ", "le ", "la ", "l'", "l "):
        if base.startswith(prefix):
            variants.add(base[len(prefix):])
    return [v for v in variants if v]


def _entity_commune_proximity(text: str, entity_canonical: str, commune: str) -> bool:
    """
    Vérifie que le nom de l'élu et la commune apparaissent à proximité dans le texte.

    Garde-fou contre les faux positifs : « X a réagi à l'événement de Y »
    ne doit PAS être interprété comme « X était à Y » quand X et Y sont à 1500 chars.

    Retourne True si on trouve au moins une co-occurrence dans une fenêtre de
    `_MAX_ENTITY_COMMUNE_DISTANCE` caractères. Tolère les variantes avec/sans
    article (Les Abymes ↔ Abymes, Le Gosier ↔ Gosier…).
    """
    if not text or not entity_canonical or not commune:
        return False

    norm_text = _normalize(text)

    # Collecte tous les indices de tous les alias spécifiques de l'élu + son nom canonique
    aliases = ELECTED_ALIASES.get(entity_canonical, [])
    forms = [_normalize(entity_canonical)] + [_normalize(a) for a in aliases]
    forms = [f for f in forms if _is_useful_alias(f)]

    entity_positions: List[int] = []
    for form in forms:
        for m in re.finditer(r"\b" + re.escape(form) + r"\b", norm_text):
            entity_positions.append(m.start())

    if not entity_positions:
        return False

    # Cherche toutes les variantes de la commune (avec/sans article)
    commune_positions: List[int] = []
    for variant in _commune_search_variants(commune):
        for m in re.finditer(r"\b" + re.escape(variant) + r"\b", norm_text):
            commune_positions.append(m.start())
    if not commune_positions:
        return False

    # Au moins une paire entité/commune à distance acceptable
    for ep in entity_positions:
        for cp in commune_positions:
            if abs(ep - cp) <= _MAX_ENTITY_COMMUNE_DISTANCE:
                return True
    return False


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
    # event_kind optionnel pour la rétro-compat ; on dérive si absent
    ek = p.get("event_kind")
    if ek and ek not in ACCEPTED_EVENT_KINDS:
        return False
    if not p.get("commune"):
        return False
    # La commune doit appartenir à la liste officielle (matching souple)
    commune_norm = _normalize(p["commune"])
    if not any(_normalize(c) == commune_norm for c in GUADELOUPE_COMMUNES):
        return False
    return True


def _derive_event_kind(presence_type: str) -> str:
    """Fallback : si le LLM n'a pas renseigné event_kind, on dérive du presence_type."""
    return "reaction" if presence_type == "communication" else "presence"


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

        # Garde-fou : entité + commune doivent être en proximité dans le texte source.
        # Empêche les associations « Jalton ailleurs dans l'article, commune ailleurs aussi ».
        if not _entity_commune_proximity(text, p["entity"], commune_canon):
            logger.debug(
                "presence rejetée (entité/commune trop éloignées) : %s ↔ %s [%s]",
                p["entity"], commune_canon, article_id,
            )
            continue

        confidence = p.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else 0.7
        except Exception:
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        event_kind = p.get("event_kind") or _derive_event_kind(p["presence_type"])
        if event_kind not in ACCEPTED_EVENT_KINDS:
            event_kind = "presence"

        # Flag de cohérence mandat : la commune assignée correspond-elle à la
        # commune de mandat de l'élu ? (purement informatif, ne bloque pas)
        mandat_commune = get_mandat_commune(p["entity"])
        commune_in_mandat = (
            mandat_commune is not None
            and _normalize(mandat_commune) == _normalize(commune_canon)
        )

        out.append({
            "entity_canonical": p["entity"],
            "entity_role": "elu",  # V1 : tous les élus de ELECTED_ALIASES
            "article_id": article_id,
            "source": source,
            "published_at": pub_at,
            "commune": commune_canon,
            "quartier": (p.get("quartier") or None) if isinstance(p.get("quartier"), str) else None,
            "presence_type": p["presence_type"],
            "event_kind": event_kind,
            "context_snippet": (p.get("context") or "")[:300],
            "confidence": confidence,
            "mandat_commune": mandat_commune,
            "commune_in_mandat": commune_in_mandat,
            "extracted_at": now,
            "extraction_method": "llm_v3_official_db",
        })

    return out


# ============================================================
# Helpers d'agrégation (utilisés par le router admin)
# ============================================================

def aggregate_by_commune(presences_collection, period_days: Optional[int] = None,
                         entity: Optional[str] = None,
                         event_kind: Optional[str] = "presence") -> List[Dict[str, Any]]:
    """
    Agrégation par commune sur la fenêtre [now - period_days, now].

    Args:
        presences_collection: pymongo collection `entity_presences`.
        period_days: nombre de jours rétroactifs (None = pas de filtre temporel).
        entity: nom canonique d'un élu pour filtrer (None = toutes).
        event_kind: "presence" (défaut, le plus pertinent pour la carte) | "reaction" | None (les deux).

    Returns:
        [{commune, count, top_entities: [{entity, count}], last_seen}]
    """
    match: Dict[str, Any] = {}
    if period_days:
        from datetime import timedelta
        match["published_at"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=period_days)}
    if entity:
        match["entity_canonical"] = entity
    if event_kind in ACCEPTED_EVENT_KINDS:
        # On accepte aussi les docs anciens sans event_kind (rétro-compat)
        match["$or"] = [
            {"event_kind": event_kind},
            {"event_kind": {"$exists": False}},
        ] if event_kind == "presence" else [{"event_kind": event_kind}]

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
                        period_days: Optional[int] = None,
                        event_kind: Optional[str] = "presence") -> Dict[str, Any]:
    """
    Vue par élu : ses communes de présence et timeline.
    """
    match: Dict[str, Any] = {"entity_canonical": entity}
    if period_days:
        from datetime import timedelta
        match["published_at"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=period_days)}
    if event_kind in ACCEPTED_EVENT_KINDS:
        match["$or"] = [
            {"event_kind": event_kind},
            {"event_kind": {"$exists": False}},
        ] if event_kind == "presence" else [{"event_kind": event_kind}]

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
