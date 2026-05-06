# backend/affairs_monitor_routes.py
"""
Router admin pour le monitoring temps réel de la création d'affaires.

Objectif : pouvoir clear puis observer minute par minute le pipeline,
pour décider si le modèle « lifecycle continu » tient ou s'il faut basculer
sur un modèle « affaires journalières ».

Toutes les routes sont admin-only.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

logger = logging.getLogger("affairs_monitor")

try:
    from backend.db import get_db  # type: ignore
except ImportError:  # pragma: no cover
    from db import get_db  # type: ignore

try:
    from backend.auth_routes import require_admin  # type: ignore
except ImportError:  # pragma: no cover
    from auth_routes import require_admin  # type: ignore


router = APIRouter(prefix="/api/affairs/monitor", tags=["affairs-monitor"])


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for k in ("created_at", "updated_at", "timestamp", "scraped_at",
              "first_seen_at", "last_active_at", "archived_at"):
        v = out.get(k)
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


@router.get("/overview")
def overview(
    hours: int = Query(24, ge=1, le=720, description="Fenêtre rétroactive en heures."),
    admin: dict = Depends(require_admin),
):
    """
    Vue d'ensemble : ce qui s'est passé sur la fenêtre [now - hours, now].
    """
    db = get_db()
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    affairs = db["affairs"]
    timeline = db["affair_timeline"]
    articles = db["articles_guadeloupe"]

    # ── Affaires créées ──
    created_count = affairs.count_documents({"created_at": {"$gte": cutoff}})
    by_status = list(affairs.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}},
    ]))

    # ── Événements timeline ──
    events = list(timeline.aggregate([
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$event", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]))

    # ── Articles ignorés (boule-de-neige bloqué, hors-zone, etc.) ──
    ignored = list(articles.aggregate([
        {"$match": {
            "_affair_ignored": True,
            "$or": [
                {"scraped_at": {"$gte": cutoff}},
                {"scraped_at": {"$gte": cutoff.isoformat()}},
            ],
        }},
        {"$group": {"_id": "$_ignore_reason", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]))

    # ── Articles processés vs non processés ──
    proc = articles.count_documents({
        "_affair_processed": True,
        "$or": [
            {"scraped_at": {"$gte": cutoff}},
            {"scraped_at": {"$gte": cutoff.isoformat()}},
        ],
    })
    unproc = articles.count_documents({
        "_affair_processed": {"$ne": True},
        "_affair_ignored": {"$ne": True},
        "$or": [
            {"scraped_at": {"$gte": cutoff}},
            {"scraped_at": {"$gte": cutoff.isoformat()}},
        ],
    })

    # ── Distribution par thème ──
    by_theme = list(affairs.aggregate([
        {"$match": {"created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$theme", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
        {"$limit": 10},
    ]))

    return {
        "window_hours": hours,
        "since": cutoff.isoformat(),
        "now": datetime.utcnow().isoformat(),
        "affairs": {
            "created": created_count,
            "by_status": [{"status": x["_id"], "count": x["n"]} for x in by_status],
            "by_theme": [{"theme": x["_id"] or "—", "count": x["n"]} for x in by_theme],
        },
        "timeline_events": [{"event": x["_id"], "count": x["n"]} for x in events],
        "articles": {
            "processed": proc,
            "unprocessed_pending": unproc,
            "ignored_by_reason": [{"reason": x["_id"] or "—", "count": x["n"]} for x in ignored],
        },
    }


@router.get("/recent-affairs")
def recent_affairs(
    limit: int = Query(50, ge=1, le=500),
    admin: dict = Depends(require_admin),
):
    """Liste les affaires créées le plus récemment (avec leurs métadonnées)."""
    db = get_db()
    affairs = db["affairs"]
    cursor = affairs.find().sort("created_at", -1).limit(limit)
    out = []
    for a in cursor:
        a = _serialize(a)
        # Compteur d'items
        a["_items_count"] = len(a.get("items", []) or a.get("article_ids", []) or [])
        out.append({
            "_id": a["_id"],
            "title": a.get("title") or a.get("name") or "—",
            "theme": a.get("theme"),
            "status": a.get("status"),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
            "items_count": a["_items_count"],
            "gravity_score": a.get("gravity_score"),
            "bmg": a.get("bmg") or a.get("bmg_score"),
            "communes": a.get("communes") or [],
            "entities": a.get("entities") or [],
        })
    return {"items": out, "count": len(out)}


@router.get("/timeline")
def timeline_feed(
    limit: int = Query(100, ge=1, le=500),
    event: Optional[str] = Query(None, description="Filtrer sur un type d'événement"),
    admin: dict = Depends(require_admin),
):
    """Flux brut d'événements timeline (création, fusion, archivage, bmg_change)."""
    db = get_db()
    q: Dict[str, Any] = {}
    if event:
        q["event"] = event
    cursor = db["affair_timeline"].find(q).sort("timestamp", -1).limit(limit)
    out = []
    for ev in cursor:
        out.append(_serialize(ev))
    return {"items": out, "count": len(out)}


@router.get("/blocked-articles")
def blocked_articles(
    limit: int = Query(50, ge=1, le=500),
    hours: int = Query(48, ge=1, le=720),
    admin: dict = Depends(require_admin),
):
    """Articles que le pipeline a refusé d'absorber dans une affaire (audit boule-de-neige)."""
    db = get_db()
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    cursor = db["articles_guadeloupe"].find({
        "_affair_ignored": True,
        "$or": [
            {"scraped_at": {"$gte": cutoff}},
            {"scraped_at": {"$gte": cutoff.isoformat()}},
        ],
    }).sort("scraped_at", -1).limit(limit)

    out = []
    for art in cursor:
        out.append({
            "_id": str(art["_id"]),
            "article_id": art.get("article_id"),
            "title": art.get("title"),
            "source": art.get("source"),
            "scraped_at": art.get("scraped_at") if isinstance(art.get("scraped_at"), str)
                          else (art.get("scraped_at").isoformat() if art.get("scraped_at") else None),
            "_ignore_reason": art.get("_ignore_reason"),
            "_affair_attempts": art.get("_affair_attempts", 0),
            "theme": art.get("theme"),
        })
    return {"items": out, "count": len(out), "window_hours": hours}


@router.post("/reset")
def reset_pipeline(
    confirm: str = Query(..., description='Doit valoir "yes-reset-affairs"'),
    admin: dict = Depends(require_admin),
):
    """
    Ultime clear : supprime affairs/timeline/clusters/candidates et réinitialise les flags
    sur articles_guadeloupe. ⚠️ Action destructive.
    """
    if confirm != "yes-reset-affairs":
        return {"ok": False, "error": "confirm parameter required (yes-reset-affairs)"}

    db = get_db()
    affairs_deleted = db["affairs"].delete_many({}).deleted_count
    timeline_deleted = db["affair_timeline"].delete_many({}).deleted_count
    candidates_deleted = db["topic_candidates"].delete_many({}).deleted_count
    clusters_deleted = db["topic_clusters"].delete_many({}).deleted_count
    articles_reset = db["articles_guadeloupe"].update_many(
        {"$or": [
            {"_affair_processed": True},
            {"_affair_ignored": True},
            {"_affair_id": {"$exists": True}},
            {"_affair_attempts": {"$exists": True}},
        ]},
        {"$set": {
            "_affair_processed": False,
            "_affair_ignored": False,
            "_affair_id": None,
            "_affair_attempts": 0,
        }, "$unset": {"_ignore_reason": ""}},
    ).modified_count

    logger.warning(
        f"🧹 RESET pipeline affaires by {admin.get('email')} — "
        f"affairs={affairs_deleted} timeline={timeline_deleted} "
        f"candidates={candidates_deleted} clusters={clusters_deleted} "
        f"articles_reset={articles_reset}"
    )

    return {
        "ok": True,
        "affairs_deleted": affairs_deleted,
        "timeline_deleted": timeline_deleted,
        "candidates_deleted": candidates_deleted,
        "clusters_deleted": clusters_deleted,
        "articles_reset": articles_reset,
        "by": admin.get("email"),
        "at": datetime.utcnow().isoformat(),
    }
