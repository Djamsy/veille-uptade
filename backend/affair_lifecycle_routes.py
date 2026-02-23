# backend/affair_lifecycle_routes.py
"""
Routes API pour le nouveau système d'affaires à cycle de vie.
"""

import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query, Body
from bson import ObjectId

logger = logging.getLogger("affair_lifecycle_routes")
router = APIRouter(prefix="/api/affairs", tags=["affairs-v2"])

_service = None


def set_service(service):
    global _service
    _service = service


def _svc():
    if _service is None:
        raise HTTPException(503, "AffairLifecycleService non disponible")
    return _service


# ============================================================
# CYCLE COMPLET
# ============================================================

@router.post("/cycle/run")
async def run_full_cycle():
    """Lance le cycle IA (priorité) ou classique (fallback).
    Le cycle IA envoie les affaires actives + nouveaux articles à l'IA
    qui décide des assignations, créations et mises à jour de gravité."""
    svc = _svc()

    # Cycle IA en priorité, fallback classique si IA indisponible
    result = svc.run_ai_managed_cycle()
    return result


@router.post("/cycle/run-classic")
async def run_classic_cycle():
    """Force le cycle classique (clustering → promotion → lifecycle)."""
    svc = _svc()
    return svc.run_full_cycle()


@router.post("/cycle/clustering")
async def run_clustering_only():
    """Lance uniquement le clustering des candidats."""
    return _svc().run_clustering()


@router.post("/cycle/promotion")
async def run_promotion_only():
    """Lance uniquement la promotion des clusters."""
    return _svc().run_promotion()


@router.post("/cycle/lifecycle")
async def run_lifecycle_only():
    """Lance uniquement la mise à jour du cycle de vie."""
    return _svc().update_affair_lifecycle()


# ============================================================
# AFFAIRES
# ============================================================

@router.get("/list")
async def list_affairs(
    status: str = Query(default="active", description="active|stale|archived|all"),
    limit: int = Query(default=30, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    sort_by: str = Query(default="bmg", description="bmg|gravity_score|created_at|last_activity"),
):
    """Liste les affaires avec filtres et pagination."""
    svc = _svc()
    query = {}
    if status != "all":
        query["status"] = status

    sort_field = sort_by if sort_by in {"bmg", "gravity_score", "created_at", "last_activity"} else "bmg"

    affairs = list(
        svc.affairs
        .find(query)
        .sort(sort_field, -1)
        .skip(skip)
        .limit(limit)
    )

    total = svc.affairs.count_documents(query)

    for a in affairs:
        a["_id"] = str(a["_id"])
        for k in ("created_at", "last_activity", "promoted_at", "archived_at"):
            if k in a and hasattr(a[k], "isoformat"):
                a[k] = a[k].isoformat()

    return {"affairs": affairs, "total": total, "skip": skip, "limit": limit}


@router.get("/detail/{affair_id}")
async def get_affair_detail(affair_id: str):
    """Détail complet d'une affaire avec timeline, BMG et items liés."""
    svc = _svc()
    try:
        affair = svc.affairs.find_one({"_id": ObjectId(affair_id)})
    except Exception:
        raise HTTPException(400, "ID invalide")

    if not affair:
        raise HTTPException(404, "Affaire non trouvée")

    # ── Récupérer les items liés ────────────────────────────
    linked_articles = []
    linked_radio = []
    linked_social = []

    # Articles
    art_ids = affair.get("articles", [])
    if art_ids:
        try:
            obj_ids = [ObjectId(a) for a in art_ids if a and len(str(a)) == 24]
            if obj_ids:
                for doc in svc.articles.find({"_id": {"$in": obj_ids}}):
                    linked_articles.append({
                        "_id": str(doc["_id"]),
                        "title": doc.get("title", "Sans titre"),
                        "source": doc.get("source", ""),
                        "url": doc.get("url", ""),
                        "date": doc.get("date", ""),
                        "scraped_at": doc.get("scraped_at", ""),
                        "theme": doc.get("theme", ""),
                        "gravity_score": doc.get("gravity_score", 0),
                        "sentiment": doc.get("sentiment", "neutre"),
                    })
        except Exception as e:
            logger.debug(f"Fetch articles liés: {e}")

    # Radio transcriptions
    radio_ids = affair.get("radio_transcriptions", [])
    if radio_ids:
        try:
            obj_ids = [ObjectId(r) for r in radio_ids if r and len(str(r)) == 24]
            if obj_ids:
                for doc in svc.transcriptions.find({"_id": {"$in": obj_ids}}):
                    linked_radio.append({
                        "_id": str(doc["_id"]),
                        "radio": doc.get("radio", "") or doc.get("stream_name", ""),
                        "text": (doc.get("text", "") or doc.get("transcription", ""))[:200],
                        "captured_at": doc.get("captured_at", ""),
                        "summary": doc.get("summary", ""),
                    })
        except Exception as e:
            logger.debug(f"Fetch radio liés: {e}")

    # Social posts
    social_ids = affair.get("social_posts", [])
    if social_ids:
        try:
            obj_ids = [ObjectId(s) for s in social_ids if s and len(str(s)) == 24]
            if obj_ids:
                for doc in svc.social.find({"_id": {"$in": obj_ids}}):
                    linked_social.append({
                        "_id": str(doc["_id"]),
                        "platform": doc.get("platform", ""),
                        "text": (doc.get("text", "") or doc.get("content", ""))[:200],
                        "author": doc.get("author", ""),
                        "url": doc.get("url", ""),
                        "created_at": doc.get("created_at", ""),
                    })
        except Exception as e:
            logger.debug(f"Fetch social liés: {e}")

    # ── Sérialiser l'affaire ────────────────────────────────
    affair["_id"] = str(affair["_id"])
    for k in ("created_at", "last_activity", "promoted_at", "archived_at"):
        if k in affair and hasattr(affair[k], "isoformat"):
            affair[k] = affair[k].isoformat()

    # ── Timeline ────────────────────────────────────────────
    timeline = list(
        svc.timeline
        .find({"affair_id": affair_id})
        .sort("timestamp", -1)
        .limit(50)
    )
    for t in timeline:
        t["_id"] = str(t["_id"])
        if hasattr(t.get("timestamp"), "isoformat"):
            t["timestamp"] = t["timestamp"].isoformat()

    # ── BMG live ────────────────────────────────────────────
    raw_affair = svc.affairs.find_one({"_id": ObjectId(affair_id)})
    bmg_live = svc.calculate_bmg(raw_affair) if raw_affair else {}

    return {
        "affair": affair,
        "timeline": timeline,
        "bmg_live": bmg_live,
        "linked_articles": linked_articles,
        "linked_radio": linked_radio,
        "linked_social": linked_social,
    }


@router.post("/recalculate-bmg/{affair_id}")
async def recalculate_affair_bmg(affair_id: str):
    """Recalcule le BMG d'une affaire spécifique."""
    svc = _svc()
    try:
        affair = svc.affairs.find_one({"_id": ObjectId(affair_id)})
    except Exception:
        raise HTTPException(400, "ID invalide")
    if not affair:
        raise HTTPException(404, "Affaire non trouvée")

    bmg = svc.calculate_bmg(affair)
    svc.affairs.update_one(
        {"_id": ObjectId(affair_id)},
        {"$set": {"bmg": bmg["bmg"], "bmg_details": bmg}}
    )
    return {"success": True, "bmg": bmg}


# ============================================================
# CLUSTERS
# ============================================================

@router.get("/clusters")
async def list_clusters(
    status: str = Query(default="active"),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Liste les clusters de sujets."""
    svc = _svc()
    query = {"status": status} if status != "all" else {}
    clusters = list(svc.clusters.find(query).sort("created_at", -1).limit(limit))
    for c in clusters:
        c["_id"] = str(c["_id"])
        for k in ("created_at", "last_activity", "promoted_at"):
            if k in c and hasattr(c[k], "isoformat"):
                c[k] = c[k].isoformat()
    return {"clusters": clusters, "count": len(clusters)}


# ============================================================
# CANDIDATS
# ============================================================

@router.get("/candidates/stats")
async def candidates_stats():
    """Statistiques sur les candidats."""
    svc = _svc()
    total = svc.candidates.count_documents({})
    unclustered = svc.candidates.count_documents({"cluster_id": None})
    by_type = {}
    for t in ["article", "transcription", "social"]:
        by_type[t] = svc.candidates.count_documents({"source_type": t})
    return {
        "total": total,
        "unclustered": unclustered,
        "by_source_type": by_type,
    }


# ============================================================
# DASHBOARD
# ============================================================

@router.get("/dashboard")
async def affairs_dashboard():
    """
    Vue dashboard : top affaires, alertes, stats globales.
    """
    svc = _svc()

    # Top affaires par BMG
    top_affairs = list(
        svc.affairs
        .find({"status": "active"})
        .sort("bmg", -1)
        .limit(10)
    )
    for a in top_affairs:
        a["_id"] = str(a["_id"])
        for k in ("created_at", "last_activity"):
            if k in a and hasattr(a[k], "isoformat"):
                a[k] = a[k].isoformat()

    # Alertes (BMG élevé)
    critical = [a for a in top_affairs if a.get("bmg", 0) >= 0.55]

    # Stats
    health = svc.health_check()

    return {
        "top_affairs": top_affairs,
        "critical_alerts": critical,
        "stats": health,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health")
async def affair_system_health():
    """Santé du système d'affaires."""
    return _svc().health_check()


@router.post("/purge-v1")
async def purge_v1_affairs():
    """Supprime les affaires créées par le V1 (sans promoted_at)
    et vide les topic_candidates/clusters pour repartir proprement."""
    svc = _svc()

    # Affaires V1 = celles qui n'ont PAS de champ promoted_at (créées par l'ancien système)
    v1_result = svc.affairs.delete_many({"promoted_at": {"$exists": False}})

    # Vider les candidats et clusters pour repartir de zéro
    cand_result = svc.candidates.delete_many({})
    clust_result = svc.clusters.delete_many({})
    timeline_result = svc.timeline.delete_many({})

    return {
        "success": True,
        "purged": {
            "v1_affairs_deleted": v1_result.deleted_count,
            "candidates_cleared": cand_result.deleted_count,
            "clusters_cleared": clust_result.deleted_count,
            "timeline_cleared": timeline_result.deleted_count,
        },
        "message": "Base affaires nettoyée. Relancez /cycle/run pour recréer les affaires via V2."
    }


@router.get("/debug/radio-transcriptions")
async def debug_radio_transcriptions():
    """Debug: voir les transcriptions radio récentes et leur état."""
    svc = _svc()
    from datetime import timedelta
    try:
        from zoneinfo import ZoneInfo
        cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=7)
    except Exception:
        cutoff = datetime.utcnow() - timedelta(days=7)

    # Toutes les transcriptions récentes
    total = svc.transcriptions.count_documents({})
    recent = list(
        svc.transcriptions.find({})
        .sort("captured_at", -1)
        .limit(10)
    )

    # Transcriptions non traitées (celles que le cycle cherche)
    unprocessed = list(
        svc.transcriptions.find({
            "captured_at": {"$gte": cutoff.isoformat()},
            "_affair_processed": {"$ne": True},
        })
        .sort("captured_at", -1)
        .limit(10)
    )

    def _serialize(doc):
        return {
            "_id": str(doc.get("_id", "")),
            "radio": doc.get("radio", ""),
            "name": doc.get("name", ""),
            "stream_name": doc.get("stream_name", ""),
            "captured_at": doc.get("captured_at", ""),
            "date": doc.get("date", ""),
            "text_length": len(doc.get("text", "") or doc.get("transcription", "") or ""),
            "_affair_processed": doc.get("_affair_processed"),
            "ai_topics_count": doc.get("ai_topics_count"),
            "has_text": bool(doc.get("text") or doc.get("transcription")),
        }

    return {
        "total_transcriptions": total,
        "cutoff_used": cutoff.isoformat(),
        "recent_10": [_serialize(d) for d in recent],
        "unprocessed_7days": [_serialize(d) for d in unprocessed],
        "unprocessed_count": len(unprocessed),
    }


@router.post("/reset")
async def full_reset():
    """RESET COMPLET — Vide toutes les collections (articles, affaires,
    candidats, clusters, timeline, transcriptions). Repart de zéro."""
    svc = _svc()

    results = {}
    for name, col in [
        ("affairs", svc.affairs),
        ("topic_candidates", svc.candidates),
        ("topic_clusters", svc.clusters),
        ("affair_timeline", svc.timeline),
        ("articles_guadeloupe", svc.articles),
        ("radio_transcriptions", svc.transcriptions),
        ("social_media_posts", svc.social),
    ]:
        try:
            r = col.delete_many({})
            results[name] = r.deleted_count
        except Exception as e:
            results[name] = f"error: {e}"

    logger.info(f"🔥 RESET COMPLET: {results}")
    return {
        "success": True,
        "deleted": results,
        "message": "Base vidée. Le prochain scraping + cycle créera tout depuis zéro."
    }
