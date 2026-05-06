# backend/presence_routes.py
"""
Router admin pour la feature « carte de présence d'élus ».

Toutes les routes sont protégées par require_admin (cf. auth_routes.require_admin).

Endpoints :
- GET  /api/presence/communes        → agrégation par commune (pour la map)
- GET  /api/presence/entity/{name}   → détail d'un élu (communes + timeline)
- GET  /api/presence/entities        → liste des élus V1 (depuis ELECTED_ALIASES)
- GET  /api/presence/feed            → derniers événements bruts (pour debug/audit)
- POST /api/presence/backfill        → relance l'extraction sur les articles existants
                                       (idempotent grâce à idx_presence_dedup)
- POST /api/presence/extract/{id}    → force l'extraction sur un article précis (debug)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger("presence_routes")

# ── Imports locaux (fallback package vs script) ──
try:
    from backend.db import get_db  # type: ignore
except ImportError:  # pragma: no cover
    from db import get_db  # type: ignore

try:
    from backend.auth_routes import require_admin  # type: ignore
except ImportError:  # pragma: no cover
    from auth_routes import require_admin  # type: ignore

try:
    from backend.entity_aliases import ELECTED_ALIASES  # type: ignore
except ImportError:  # pragma: no cover
    from entity_aliases import ELECTED_ALIASES  # type: ignore

try:
    from backend.entity_presence_service import (  # type: ignore
        extract_presences_from_article,
        aggregate_by_commune,
        aggregate_by_entity,
        GUADELOUPE_COMMUNES,
    )
except ImportError:  # pragma: no cover
    from entity_presence_service import (  # type: ignore
        extract_presences_from_article,
        aggregate_by_commune,
        aggregate_by_entity,
        GUADELOUPE_COMMUNES,
    )


router = APIRouter(prefix="/api/presence", tags=["presence"])


# ============================================================
# Helpers
# ============================================================

def _presences_col():
    return get_db()["entity_presences"]


def _articles_col():
    return get_db()["articles_guadeloupe"]


def _serialize_dt(dt) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _insert_presences(records: List[Dict[str, Any]]) -> int:
    """Insère les présences en évitant les doublons (article_id + entity + commune)."""
    if not records:
        return 0
    col = _presences_col()
    inserted = 0
    for r in records:
        key = {
            "article_id": r["article_id"],
            "entity_canonical": r["entity_canonical"],
            "commune": r["commune"],
        }
        # upsert : on garde la première extraction, on met à jour confidence/context si plus haut
        existing = col.find_one(key)
        if existing:
            if r.get("confidence", 0) > existing.get("confidence", 0):
                col.update_one({"_id": existing["_id"]}, {"$set": {
                    "confidence": r["confidence"],
                    "context_snippet": r["context_snippet"],
                    "extracted_at": r["extracted_at"],
                }})
            continue
        col.insert_one(r)
        inserted += 1
    return inserted


# ============================================================
# Routes
# ============================================================

@router.get("/entities")
def list_entities(admin: dict = Depends(require_admin)):
    """Liste des 40 élus V1 (clés de ELECTED_ALIASES)."""
    return {
        "entities": sorted(ELECTED_ALIASES.keys()),
        "count": len(ELECTED_ALIASES),
    }


@router.get("/communes")
def presence_by_commune(
    period_days: Optional[int] = Query(None, ge=1, le=3650,
        description="Fenêtre rétroactive en jours. None = pas de filtre temporel."),
    entity: Optional[str] = Query(None, description="Filtrer sur un élu (nom canonique)."),
    admin: dict = Depends(require_admin),
):
    """Agrégation par commune — base de la choropleth admin."""
    rows = aggregate_by_commune(_presences_col(), period_days=period_days, entity=entity)
    # On joint avec la liste officielle pour que les communes sans présence apparaissent à 0
    by_name = {r["commune"]: r for r in rows}
    out = []
    for c in GUADELOUPE_COMMUNES:
        r = by_name.get(c, {"commune": c, "count": 0, "last_seen": None, "top_entities": []})
        out.append({
            "commune": r["commune"],
            "count": r["count"],
            "last_seen": _serialize_dt(r.get("last_seen")),
            "top_entities": r.get("top_entities") or [],
        })
    return {
        "period_days": period_days,
        "entity_filter": entity,
        "communes": out,
        "total_presences": sum(r["count"] for r in out),
        "active_communes": sum(1 for r in out if r["count"] > 0),
    }


@router.get("/entity/{entity_name}")
def presence_entity(
    entity_name: str,
    period_days: Optional[int] = Query(None, ge=1, le=3650),
    admin: dict = Depends(require_admin),
):
    """Vue par élu : ses communes + timeline."""
    if entity_name not in ELECTED_ALIASES:
        raise HTTPException(404, f"Entité inconnue : {entity_name}")
    summary = aggregate_by_entity(_presences_col(), entity_name, period_days=period_days)
    summary["communes"] = [
        {**c, "last_seen": _serialize_dt(c.get("last_seen"))} for c in summary["communes"]
    ]
    return summary


@router.get("/feed")
def presence_feed(
    limit: int = Query(50, ge=1, le=500),
    entity: Optional[str] = None,
    commune: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """Derniers événements (audit/debug)."""
    q: Dict[str, Any] = {}
    if entity:
        q["entity_canonical"] = entity
    if commune:
        q["commune"] = commune
    cursor = _presences_col().find(q).sort("published_at", -1).limit(limit)
    out = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["published_at"] = _serialize_dt(doc.get("published_at"))
        doc["extracted_at"] = _serialize_dt(doc.get("extracted_at"))
        out.append(doc)
    return {"items": out, "count": len(out)}


@router.post("/backfill")
def backfill(
    days: int = Query(30, ge=1, le=365, description="Profondeur du backfill en jours."),
    limit: int = Query(500, ge=1, le=5000, description="Nombre max d'articles à traiter."),
    admin: dict = Depends(require_admin),
):
    """Relance l'extraction sur les articles récents (idempotent)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = _articles_col().find({
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"date": {"$gte": cutoff}},
            {"scraped_at": {"$gte": cutoff}},
        ]
    }).limit(limit)

    processed = 0
    inserted = 0
    skipped_no_match = 0
    errors = 0

    for art in cursor:
        processed += 1
        try:
            records = extract_presences_from_article(art)
            if not records:
                skipped_no_match += 1
                continue
            inserted += _insert_presences(records)
        except Exception as e:
            logger.warning("backfill error sur article %s: %s", art.get("article_id"), e)
            errors += 1

    return {
        "ok": True,
        "days": days,
        "limit": limit,
        "processed": processed,
        "inserted": inserted,
        "skipped_no_match": skipped_no_match,
        "errors": errors,
    }


@router.post("/extract/{article_id}")
def force_extract(article_id: str, admin: dict = Depends(require_admin)):
    """Force l'extraction sur un article (debug)."""
    art = _articles_col().find_one({"article_id": article_id})
    if not art:
        raise HTTPException(404, "Article introuvable")
    records = extract_presences_from_article(art)
    inserted = _insert_presences(records)
    return {
        "article_id": article_id,
        "presences_extracted": len(records),
        "inserted": inserted,
        "records": [
            {**r, "extracted_at": _serialize_dt(r.get("extracted_at")),
             "published_at": _serialize_dt(r.get("published_at"))}
            for r in records
        ],
    }
