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
    """Lance le cycle simplifié : créer → consolider → radio → BMG."""
    svc = _svc()
    return svc.run_simple_cycle()


@router.post("/cycle/run-ai")
async def run_ai_cycle():
    """Force le cycle IA (legacy). Fallback classique si IA indisponible."""
    svc = _svc()
    return svc.run_ai_managed_cycle()


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


@router.post("/cycle/reaffiliate")
async def reaffiliate_orphans():
    """Force la ré-affiliation des articles orphelins aux affaires actives."""
    svc = _svc()
    count = svc._reaffiliate_orphans()
    return {
        "success": True,
        "reaffiliated": count,
        "message": f"{count} articles orphelins rattachés à des affaires existantes"
    }


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


@router.get("/dashboard/enriched")
async def enriched_dashboard():
    """Dashboard enrichi avec stats détaillées, couverture, tendances."""
    svc = _svc()
    from datetime import timedelta
    from collections import Counter

    now = datetime.utcnow()

    # ── Affaires actives ──
    active_affairs = list(
        svc.affairs.find({"status": "active"}).sort("bmg", -1).limit(20)
    )
    for a in active_affairs:
        a["_id"] = str(a["_id"])
        for k in ("created_at", "last_activity", "promoted_at"):
            if k in a and hasattr(a[k], "isoformat"):
                a[k] = a[k].isoformat()

    # ── Stats de couverture (7 jours) ──
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    total_articles_7d = svc.articles.count_documents({"scraped_at": {"$gte": cutoff_7d}})
    enriched_articles_7d = svc.articles.count_documents({
        "scraped_at": {"$gte": cutoff_7d},
        "_analysis_method": {"$exists": True},
    })
    affiliated_articles_7d = svc.articles.count_documents({
        "scraped_at": {"$gte": cutoff_7d},
        "_affair_processed": True,
    })
    total_transcriptions_7d = svc.transcriptions.count_documents({
        "captured_at": {"$gte": cutoff_7d}
    })
    processed_transcriptions_7d = svc.transcriptions.count_documents({
        "captured_at": {"$gte": cutoff_7d},
        "_affair_processed": True,
    })

    # ── Taux d'affiliation ──
    affiliation_rate = round(
        (affiliated_articles_7d / total_articles_7d * 100) if total_articles_7d > 0 else 0, 1
    )
    enrichment_rate = round(
        (enriched_articles_7d / total_articles_7d * 100) if total_articles_7d > 0 else 0, 1
    )
    radio_rate = round(
        (processed_transcriptions_7d / total_transcriptions_7d * 100)
        if total_transcriptions_7d > 0 else 0, 1
    )

    # ── Répartition thématique des affaires ──
    theme_counter = Counter()
    for a in active_affairs:
        theme_counter[a.get("theme", "general")] += 1
    themes_distribution = dict(theme_counter.most_common(10))

    # ── Top entités (les plus citées dans les affaires actives) ──
    entity_counter = Counter()
    for a in active_affairs:
        for e in (a.get("elected", []) or []):
            if e and len(e) > 2:
                entity_counter[e] += 1
        for e in (a.get("institutions", []) or []):
            if e and len(e) > 2:
                entity_counter[e] += 1
    top_entities = [{"name": name, "count": count} for name, count in entity_counter.most_common(15)]

    # ── Activité par jour (7 derniers jours) ──
    daily_activity = []
    for i in range(7):
        day = now - timedelta(days=6 - i)
        day_start = day.replace(hour=0, minute=0, second=0).isoformat()
        day_end = day.replace(hour=23, minute=59, second=59).isoformat()
        articles_count = svc.articles.count_documents({
            "scraped_at": {"$gte": day_start, "$lte": day_end}
        })
        events_count = svc.timeline.count_documents({
            "timestamp": {"$gte": datetime(day.year, day.month, day.day),
                          "$lt": datetime(day.year, day.month, day.day) + timedelta(days=1)}
        })
        daily_activity.append({
            "date": day.strftime("%Y-%m-%d"),
            "label": day.strftime("%a %d"),
            "articles": articles_count,
            "events": events_count,
        })

    # ── Articles récents non affiliés (orphelins) ──
    orphan_articles = list(
        svc.articles.find({
            "scraped_at": {"$gte": cutoff_7d},
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
            ],
        })
        .sort("scraped_at", -1)
        .limit(10)
    )
    orphans_serialized = []
    for art in orphan_articles:
        orphans_serialized.append({
            "_id": str(art["_id"]),
            "title": art.get("title", "Sans titre")[:100],
            "source": art.get("source", ""),
            "theme": art.get("theme", "general"),
            "gravity_score": art.get("gravity_score", 0),
            "scraped_at": art.get("scraped_at", ""),
        })

    # ── Alertes critiques ──
    critical = [a for a in active_affairs if a.get("bmg", 0) >= 0.55]

    # ── Stats pipeline ──
    health = svc.health_check()

    # ── Dernières actions du cycle ──
    recent_timeline = list(
        svc.timeline.find({}).sort("timestamp", -1).limit(10)
    )
    for t in recent_timeline:
        t["_id"] = str(t["_id"])
        if hasattr(t.get("timestamp"), "isoformat"):
            t["timestamp"] = t["timestamp"].isoformat()

    # ── Sources actives ──
    source_counter = Counter()
    for art in svc.articles.find(
        {"scraped_at": {"$gte": cutoff_7d}},
        {"source": 1}
    ).limit(500):
        src = art.get("source", "Inconnu")
        if src:
            source_counter[src] += 1
    top_sources = [{"name": n, "count": c} for n, c in source_counter.most_common(8)]

    # ── Distribution de gravité des articles (7j) ──
    gravity_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    sentiment_counter = Counter()
    for art in svc.articles.find(
        {"scraped_at": {"$gte": cutoff_7d}, "_analysis_method": {"$exists": True}},
        {"gravity_score": 1, "sentiment": 1}
    ).limit(1000):
        g = art.get("gravity_score", 0)
        if g < 0.25:
            gravity_distribution["low"] += 1
        elif g < 0.50:
            gravity_distribution["medium"] += 1
        elif g < 0.70:
            gravity_distribution["high"] += 1
        else:
            gravity_distribution["critical"] += 1
        sent = art.get("sentiment", "neutre")
        if sent:
            sentiment_counter[sent] += 1
    avg_gravity = 0
    enriched_with_gravity = list(svc.articles.find(
        {"scraped_at": {"$gte": cutoff_7d}, "gravity_score": {"$exists": True}},
        {"gravity_score": 1}
    ).limit(500))
    if enriched_with_gravity:
        avg_gravity = round(
            sum(a.get("gravity_score", 0) for a in enriched_with_gravity) / len(enriched_with_gravity), 3
        )

    # ── Priority counts des affaires actives ──
    priority_counts = Counter()
    for a in active_affairs:
        priority_counts[a.get("priority", "minor")] += 1

    # ── Comparaison semaine courante vs semaine précédente ──
    cutoff_14d = (now - timedelta(days=14)).isoformat()
    articles_prev_week = svc.articles.count_documents({
        "scraped_at": {"$gte": cutoff_14d, "$lt": cutoff_7d}
    })
    affairs_created_7d = svc.timeline.count_documents({
        "event": "created",
        "timestamp": {"$gte": now - timedelta(days=7)}
    })
    affairs_created_prev = svc.timeline.count_documents({
        "event": "created",
        "timestamp": {"$gte": now - timedelta(days=14), "$lt": now - timedelta(days=7)}
    })

    # ── BMG moyen des affaires actives ──
    avg_bmg = 0
    if active_affairs:
        avg_bmg = round(sum(a.get("bmg", 0) for a in active_affairs) / len(active_affairs), 3)

    # ── Top affaires par BMG (top 5) ──
    top_5_affairs = active_affairs[:5]

    return {
        "top_affairs": active_affairs,
        "critical_alerts": critical,
        "stats": health,
        "coverage": {
            "total_articles_7d": total_articles_7d,
            "enriched_articles_7d": enriched_articles_7d,
            "affiliated_articles_7d": affiliated_articles_7d,
            "total_transcriptions_7d": total_transcriptions_7d,
            "processed_transcriptions_7d": processed_transcriptions_7d,
            "affiliation_rate": affiliation_rate,
            "enrichment_rate": enrichment_rate,
            "radio_rate": radio_rate,
        },
        "themes_distribution": themes_distribution,
        "top_entities": top_entities,
        "daily_activity": daily_activity,
        "orphan_articles": orphans_serialized,
        "recent_timeline": recent_timeline,
        "top_sources": top_sources,
        "gravity_distribution": gravity_distribution,
        "avg_gravity": avg_gravity,
        "sentiment_distribution": dict(sentiment_counter.most_common(10)),
        "priority_counts": dict(priority_counts),
        "avg_bmg": avg_bmg,
        "trends": {
            "articles_this_week": total_articles_7d,
            "articles_last_week": articles_prev_week,
            "articles_trend_pct": round(
                ((total_articles_7d - articles_prev_week) / articles_prev_week * 100)
                if articles_prev_week > 0 else 0, 1
            ),
            "affairs_created_this_week": affairs_created_7d,
            "affairs_created_last_week": affairs_created_prev,
        },
        "timestamp": now.isoformat(),
    }


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
