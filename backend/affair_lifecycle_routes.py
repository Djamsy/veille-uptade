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

    # Radio transcriptions — utiliser radio_topics si disponible pour un affichage précis
    radio_topics = affair.get("radio_topics", [])
    radio_ids = affair.get("radio_transcriptions", [])
    if radio_topics:
        # Affichage enrichi : chaque topic radio avec son titre et résumé
        for rt in radio_topics:
            captured = rt.get("captured_at", "")
            if hasattr(captured, "isoformat"):
                captured = captured.isoformat()
            linked_radio.append({
                "_id": rt.get("transcription_id", ""),
                "radio": rt.get("radio", ""),
                "text": rt.get("topic_summary", "")[:300],
                "captured_at": captured,
                "summary": f"{rt.get('topic_title', '')} — {rt.get('topic_summary', '')}",
                "topic_title": rt.get("topic_title", ""),
                "topic_summary": rt.get("topic_summary", ""),
                "gravity": rt.get("gravity", 0),
            })
    elif radio_ids:
        # Fallback : affichage classique depuis les transcriptions brutes
        try:
            obj_ids = [ObjectId(r) for r in radio_ids if r and len(str(r)) == 24]
            if obj_ids:
                for doc in svc.transcriptions.find({"_id": {"$in": obj_ids}}):
                    # Chercher le meilleur résumé dans ai_topics
                    ai_summary = ""
                    ai_topics = doc.get("ai_topics", []) or []
                    if ai_topics:
                        summaries = [f"{t.get('title', '')} — {t.get('summary', '')}"
                                     for t in ai_topics if t.get("title")]
                        ai_summary = " | ".join(summaries[:3])
                    linked_radio.append({
                        "_id": str(doc["_id"]),
                        "radio": doc.get("radio", "") or doc.get("stream_name", ""),
                        "text": (doc.get("text", "") or doc.get("transcription", ""))[:200],
                        "captured_at": doc.get("captured_at", ""),
                        "summary": ai_summary or doc.get("ai_summary", "") or doc.get("summary", ""),
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


@router.post("/cleanup/{affair_id}")
async def cleanup_affair(affair_id: str):
    """Nettoie une affaire en retirant les articles sans lien réel.
    Compare chaque article au titre/entités de référence et retire ceux qui ne matchent pas."""
    svc = _svc()
    result = svc.cleanup_affair(affair_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/cleanup-all")
async def cleanup_all_affairs():
    """Nettoie TOUTES les affaires actives en retirant les articles mal groupés."""
    svc = _svc()
    return svc.cleanup_all_affairs()


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
# ANALYSE PRÉDICTIVE IA
# ============================================================

@router.get("/analytics/predictive")
async def get_predictive_analysis(force: bool = Query(default=False)):
    """
    Analyse prédictive IA : tendances, anticipations, recommandations.
    Sert le cache (mis à jour toutes les heures par le scheduler).
    Ajouter ?force=true pour forcer un recalcul immédiat.
    """
    svc = _svc()

    # Vérifier le cache d'abord (sauf si force=true)
    if not force:
        try:
            cache_col = svc.db.get_collection("predictive_cache")
            cached = cache_col.find_one({"_id": "latest"})
            if cached and cached.get("analysis"):
                return {
                    "success": True,
                    "analysis": cached["analysis"],
                    "affairs_analyzed": cached.get("affairs_analyzed", 0),
                    "generated_at": cached.get("generated_at"),
                    "from_cache": True,
                }
        except Exception:
            pass  # Pas de cache, on recalcule

    active = list(svc.affairs.find({"status": {"$in": ["active", "stale"]}}).sort("gravity_score", -1).limit(30))

    if not active:
        return {"success": False, "error": "Aucune affaire active pour l'analyse"}

    # Sérialiser pour le service IA
    for a in active:
        a["_id"] = str(a["_id"])

    try:
        from backend.ai_groq_service import analyze_trends_predictive
    except ImportError:
        try:
            from ai_groq_service import analyze_trends_predictive
        except ImportError:
            raise HTTPException(503, "Service IA non disponible")

    result = analyze_trends_predictive(active)
    if result is None:
        return {"success": False, "error": "Analyse IA échouée (clé API manquante ou erreur)"}

    # Mettre en cache
    try:
        from datetime import datetime as dt
        cache_col = svc.db.get_collection("predictive_cache")
        cache_col.update_one(
            {"_id": "latest"},
            {"$set": {
                "analysis": result,
                "affairs_analyzed": len(active),
                "generated_at": dt.now().isoformat(),
            }},
            upsert=True,
        )
    except Exception:
        pass

    return {
        "success": True,
        "analysis": result,
        "affairs_analyzed": len(active),
        "from_cache": False,
    }


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


@router.post("/recalculate-priorities")
async def recalculate_all_priorities():
    """Recalcule la priorité de TOUTES les affaires actives/stale avec les nouveaux seuils."""
    svc = _svc()
    updated = 0
    distribution = {"hot": 0, "watch": 0, "minor": 0}
    for affair in svc.affairs.find({"status": {"$in": ["active", "stale"]}}):
        gravity = affair.get("gravity_score", 0)
        bmg = affair.get("bmg", 0)
        item_count = affair.get("item_count", 1)
        new_priority = svc.compute_priority(gravity, bmg, item_count)
        old_priority = affair.get("priority", "unknown")
        svc.affairs.update_one(
            {"_id": affair["_id"]},
            {"$set": {"priority": new_priority}}
        )
        distribution[new_priority] = distribution.get(new_priority, 0) + 1
        if old_priority != new_priority:
            updated += 1
    return {
        "success": True,
        "updated": updated,
        "distribution": distribution,
    }


@router.post("/clean-parasites")
async def clean_parasitic_articles():
    """Nettoie les affaires existantes :
    1. Supprime les articles parasites (pas assez liés à l'affaire d'origine)
    2. Fusionne les affaires doublons (titres quasi-identiques)
    3. Supprime les affaires vides après nettoyage
    """
    svc = _svc()
    from difflib import SequenceMatcher

    stats = {"articles_removed": 0, "affairs_merged": 0, "affairs_deleted": 0, "affairs_cleaned": 0}

    active = list(svc.affairs.find({"status": {"$in": ["active", "stale"]}}))

    # ── Phase 1 : Nettoyer les articles parasites de chaque affaire ──
    for affair in active:
        original_elected = set(
            e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
        )
        original_institutions = set(
            e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
        ) - svc.GENERIC_INSTITUTIONS
        affair_theme = affair.get("theme", "general")
        affair_title = affair.get("title", "")

        # Titre : mots discriminants
        affair_title_words = set(
            w.lower() for w in affair_title.split()
            if len(w) > 7 and w.lower() not in svc.GENERIC_TITLE_WORDS
        )

        articles_to_keep = []
        articles_removed = []

        for art_id in (affair.get("articles", []) or []):
            try:
                art = svc.articles.find_one({"_id": ObjectId(art_id)}) if len(str(art_id)) == 24 else None
            except Exception:
                art = None

            if not art:
                articles_to_keep.append(art_id)  # Garder — on ne peut pas vérifier
                continue

            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            ) - svc.GENERIC_INSTITUTIONS
            art_title = art.get("title", "")

            # Vérifier : l'article est-il lié par au moins 1 entité spécifique
            # OU par un titre très similaire ?
            common_elected = art_elected & original_elected
            common_elected_specific = common_elected - svc.GENERIC_ELECTED
            common_institutions = art_institutions & original_institutions

            # Titre similaire ?
            title_ratio = SequenceMatcher(None, affair_title.lower(), art_title.lower()).ratio()

            keep = (
                len(common_elected_specific) >= 1
                or len(common_institutions) >= 1
                or title_ratio >= 0.5
                or (len(common_elected) >= 1 and affair_theme == art.get("theme", ""))
            )

            if keep:
                articles_to_keep.append(art_id)
            else:
                articles_removed.append(art_id)
                stats["articles_removed"] += 1

        if articles_removed:
            svc.affairs.update_one(
                {"_id": affair["_id"]},
                {
                    "$set": {
                        "articles": articles_to_keep,
                        "item_count": len(articles_to_keep) + len(affair.get("radio_transcriptions", [])),
                    }
                }
            )
            # Remettre les articles comme non-traités pour qu'ils soient re-évalués
            for art_id in articles_removed:
                try:
                    svc.articles.update_one(
                        {"_id": ObjectId(art_id)},
                        {"$set": {"_affair_processed": False, "_affair_id": None, "_affair_ignored": False}}
                    )
                except Exception:
                    pass
            stats["affairs_cleaned"] += 1

    # ── Phase 2 : Fusionner les affaires doublons ──
    # Recharger après nettoyage
    active = list(svc.affairs.find({"status": {"$in": ["active", "stale"]}}))
    merged_ids = set()

    for i, aff_a in enumerate(active):
        if str(aff_a["_id"]) in merged_ids:
            continue
        title_a = aff_a.get("title", "").lower()
        for j in range(i + 1, len(active)):
            aff_b = active[j]
            if str(aff_b["_id"]) in merged_ids:
                continue
            title_b = aff_b.get("title", "").lower()

            ratio = SequenceMatcher(None, title_a, title_b).ratio()
            if ratio >= 0.65:
                # Fusionner B dans A (garder le plus ancien ou le plus fourni)
                keep = aff_a if aff_a.get("item_count", 0) >= aff_b.get("item_count", 0) else aff_b
                absorb = aff_b if keep == aff_a else aff_a

                svc.affairs.update_one(
                    {"_id": keep["_id"]},
                    {
                        "$addToSet": {
                            "articles": {"$each": absorb.get("articles", [])},
                            "radio_transcriptions": {"$each": absorb.get("radio_transcriptions", [])},
                            "sources": {"$each": absorb.get("sources", [])},
                        },
                        "$max": {"gravity_score": absorb.get("gravity_score", 0)},
                        "$set": {"last_activity": datetime.utcnow()},
                    }
                )
                # Recalculer item_count
                updated_keep = svc.affairs.find_one({"_id": keep["_id"]})
                if updated_keep:
                    new_count = (
                        len(updated_keep.get("articles", []))
                        + len(updated_keep.get("radio_transcriptions", []))
                    )
                    svc.affairs.update_one({"_id": keep["_id"]}, {"$set": {"item_count": new_count}})

                # Supprimer le doublon
                svc.affairs.delete_one({"_id": absorb["_id"]})
                merged_ids.add(str(absorb["_id"]))
                stats["affairs_merged"] += 1

    # ── Phase 3 : Supprimer les affaires vides ──
    empty = svc.affairs.delete_many({
        "status": {"$in": ["active", "stale"]},
        "$or": [
            {"articles": {"$size": 0}, "radio_transcriptions": {"$size": 0}},
            {"articles": {"$exists": False}},
        ]
    })
    stats["affairs_deleted"] = empty.deleted_count

    return {"success": True, "stats": stats}


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


GUADELOUPE_COMMUNES = [
    "Les Abymes", "Anse-Bertrand", "Baie-Mahault", "Baillif", "Basse-Terre",
    "Bouillante", "Capesterre-Belle-Eau", "Capesterre-de-Marie-Galante",
    "Deshaies", "Gourbeyre", "Goyave", "Grand-Bourg", "La Désirade",
    "Lamentin", "Le Gosier", "Le Moule", "Morne-à-l'Eau", "Petit-Bourg",
    "Petit-Canal", "Pointe-à-Pitre", "Pointe-Noire", "Port-Louis",
    "Saint-Claude", "Saint-François", "Saint-Louis", "Sainte-Anne",
    "Sainte-Rose", "Terre-de-Bas", "Terre-de-Haut", "Trois-Rivières",
    "Vieux-Fort", "Vieux-Habitants",
]

# Mots-clés associant affaires aux communes
COMMUNE_KEYWORDS = {c.lower(): c for c in GUADELOUPE_COMMUNES}
# Ajout variantes sans accents/tirets
COMMUNE_KEYWORDS.update({
    "abymes": "Les Abymes", "les abymes": "Les Abymes",
    "anse bertrand": "Anse-Bertrand", "baie mahault": "Baie-Mahault",
    "basse terre": "Basse-Terre", "capesterre belle eau": "Capesterre-Belle-Eau",
    "capesterre belle-eau": "Capesterre-Belle-Eau",
    "grand bourg": "Grand-Bourg", "la desirade": "La Désirade",
    "le gosier": "Le Gosier", "gosier": "Le Gosier",
    "le moule": "Le Moule", "moule": "Le Moule",
    "morne a l'eau": "Morne-à-l'Eau", "morne-a-l'eau": "Morne-à-l'Eau",
    "petit bourg": "Petit-Bourg", "petit canal": "Petit-Canal",
    "pointe a pitre": "Pointe-à-Pitre", "pointe-a-pitre": "Pointe-à-Pitre",
    "pointe noire": "Pointe-Noire", "port louis": "Port-Louis",
    "saint claude": "Saint-Claude", "saint francois": "Saint-François",
    "saint-francois": "Saint-François", "saint louis": "Saint-Louis",
    "sainte anne": "Sainte-Anne", "sainte rose": "Sainte-Rose",
    "terre de bas": "Terre-de-Bas", "terre de haut": "Terre-de-Haut",
    "trois rivieres": "Trois-Rivières", "trois-rivieres": "Trois-Rivières",
    "vieux fort": "Vieux-Fort", "vieux habitants": "Vieux-Habitants",
})


def _detect_communes(affair: dict) -> list:
    """Détecte les communes liées à une affaire via titre, entités, description."""
    found = set()
    text_parts = [
        (affair.get("title", "") or "").lower(),
        (affair.get("description", "") or "").lower(),
        " ".join((affair.get("entities", []) or [])).lower(),
        " ".join((affair.get("elected", []) or [])).lower(),
        " ".join((affair.get("institutions", []) or [])).lower(),
    ]
    full_text = " ".join(text_parts)

    for keyword, commune in COMMUNE_KEYWORDS.items():
        if keyword in full_text:
            found.add(commune)
    return list(found)


@router.get("/by-commune")
async def affairs_by_commune():
    """Retourne les affaires groupées par commune pour la carte."""
    svc = _svc()
    affairs = list(svc.affairs.find({"status": "active"}).sort("gravity_score", -1))

    commune_map: dict = {}
    for affair in affairs:
        communes = _detect_communes(affair)
        for commune in communes:
            if commune not in commune_map:
                commune_map[commune] = {"count": 0, "maxGravity": 0, "affairs": []}
            commune_map[commune]["count"] += 1
            commune_map[commune]["maxGravity"] = max(
                commune_map[commune]["maxGravity"],
                affair.get("gravity_score", 0)
            )
            commune_map[commune]["affairs"].append({
                "_id": str(affair["_id"]),
                "title": affair.get("title", "")[:100],
                "gravity_score": affair.get("gravity_score", 0),
                "sentiment": affair.get("sentiment", "neutre"),
                "theme": affair.get("theme", ""),
            })

    return {"communes": commune_map, "total_affairs": len(affairs)}


@router.get("/elections")
async def elections_affairs():
    """Retourne les affaires liées aux élections municipales 2026."""
    svc = _svc()

    # Chercher par mots-clés électoraux dans le titre et la description
    election_keywords = [
        "élection", "election", "municipale", "candidat", "scrutin",
        "campagne", "liste", "vote", "maire", "premier tour", "second tour",
        "ballottage",
    ]
    regex = "|".join(election_keywords)

    affairs = list(svc.affairs.find({
        "status": "active",
        "$or": [
            {"title": {"$regex": regex, "$options": "i"}},
            {"description": {"$regex": regex, "$options": "i"}},
            {"theme": "politique"},
        ]
    }).sort("gravity_score", -1))

    # Sérialiser
    result = []
    for a in affairs:
        a["_id"] = str(a["_id"])
        for k in ("created_at", "last_activity", "promoted_at"):
            if k in a and hasattr(a.get(k), "isoformat"):
                a[k] = a[k].isoformat()
        # Détecter les communes associées
        a["communes"] = _detect_communes(a)
        # Supprimer les champs lourds
        a.pop("embedding", None)
        a.pop("sentiment_history", None)
        a.pop("bmg_history", None)
        result.append(a)

    return {"affairs": result, "total": len(result)}


# ============================================================
# COMPÉTENCES INSTITUTIONNELLES (Département / Région)
# ============================================================

# Compétences du Département de la Guadeloupe
DEPARTEMENT_COMPETENCES = {
    "Social & Solidarité": {
        "keywords": [
            "ase", "aide sociale", "enfance", "pmi", "protection maternelle",
            "mdph", "handicap", "mda", "autonomie", "rsa", "insertion",
            "cohésion sociale", "foyer", "dics", "cnas", "solidarité",
            "personnes âgées", "dépendance", "aide aux familles",
        ],
        "color": "#818cf8",
    },
    "Éducation (Collèges)": {
        "keywords": [
            "collège", "college", "collégien", "cantine scolaire",
            "transport scolaire", "brevet", "éducation",
        ],
        "color": "#c084fc",
    },
    "Routes & Infrastructures": {
        "keywords": [
            "route départementale", "rd ", "voirie", "pont", "ouvrage d'art",
            "chaussée", "routes", "infrastructure routière", "epfag", "foncier",
        ],
        "color": "#fbbf24",
    },
    "Sécurité (SDIS)": {
        "keywords": [
            "sdis", "pompier", "sapeur", "incendie", "secours",
            "caserne", "intervention", "feu",
        ],
        "color": "#f87171",
    },
    "Culture & Patrimoine": {
        "keywords": [
            "bibliothèque", "archives", "patrimoine", "musée",
            "mémorial", "culture", "archéologie", "lecture publique",
        ],
        "color": "#f9a8d4",
    },
    "Santé & Prévention": {
        "keywords": [
            "epsm", "santé mentale", "lda", "laboratoire",
            "prévention santé", "vaccination", "dépistage", "pmsi",
        ],
        "color": "#34d399",
    },
    "Environnement & Eau": {
        "keywords": [
            "smgeag", "eau potable", "assainissement", "espace naturel",
            "zone humide", "littoral", "déchets", "environnement",
            "biodiversité", "mangrove",
        ],
        "color": "#67e8f9",
    },
    "Aménagement du Territoire": {
        "keywords": [
            "intercommunalité", "cangt", "carl", "cap excellence",
            "grand sud", "marie-galante", "communauté d'agglomération",
            "aménagement", "urbanisme", "sig 971", "plan local",
        ],
        "color": "#fb923c",
    },
}

# Compétences de la Région Guadeloupe
REGION_COMPETENCES = {
    "Économie & Emploi": {
        "keywords": [
            "économie", "emploi", "entreprise", "pme", "artisan",
            "commerce", "industrie", "sucre", "banane", "rhum",
            "tourisme", "agriculture", "pêche", "croissance",
            "chômage", "formation professionnelle", "apprentissage",
            "chambre de commerce", "cci", "chambre des métiers",
        ],
        "color": "#34d399",
    },
    "Transports & Mobilité": {
        "keywords": [
            "transport", "bus", "réseau", "aéroport", "pôle caraïbes",
            "port autonome", "maritime", "ferry", "liaison",
            "mobilité", "train", "tramway", "navette",
        ],
        "color": "#818cf8",
    },
    "Lycées & Formation": {
        "keywords": [
            "lycée", "lyceen", "baccalauréat", "formation",
            "campus", "université", "uag", "crous", "bts",
            "enseignement supérieur", "rectorat",
        ],
        "color": "#c084fc",
    },
    "Énergie & Transition": {
        "keywords": [
            "énergie", "edf", "électricité", "photovoltaïque",
            "éolien", "géothermie", "transition énergétique",
            "carburant", "essence", "sara",
        ],
        "color": "#fbbf24",
    },
    "Santé (ARS)": {
        "keywords": [
            "ars", "agence régionale", "hôpital", "chu",
            "clinique", "urgence", "désert médical", "médecin",
            "dengue", "sargasse", "chlordécone", "épidémie",
        ],
        "color": "#f87171",
    },
    "Logement & Habitat": {
        "keywords": [
            "logement", "habitat", "hlm", "sem", "sig",
            "construction", "rénovation", "social",
            "deal", "urbanisme",
        ],
        "color": "#fb923c",
    },
    "Coopération Caribéenne": {
        "keywords": [
            "caraïbe", "caricom", "oecs", "coopération régionale",
            "antilles", "martinique", "guyane", "outre-mer",
            "dom", "ultramarin", "interreg",
        ],
        "color": "#67e8f9",
    },
    "Sécurité & Justice": {
        "keywords": [
            "préfecture", "préfet", "police", "gendarmerie",
            "tribunal", "justice", "procureur", "délinquance",
            "criminalité", "trafic", "drogue", "violence",
            "sécurité", "garde à vue", "prison",
        ],
        "color": "#fca5a5",
    },
}


def _match_competences(affair: dict, competences: dict) -> list:
    """Retourne la liste des compétences matchées pour une affaire."""
    text_parts = [
        (affair.get("title", "") or "").lower(),
        (affair.get("description", "") or "").lower(),
        " ".join((affair.get("keywords", []) or [])).lower(),
        " ".join((affair.get("entities", []) or [])).lower(),
        " ".join((affair.get("institutions", []) or [])).lower(),
        (affair.get("theme", "") or "").lower(),
    ]
    full_text = " ".join(text_parts)
    matched = []
    for comp_name, comp_data in competences.items():
        for kw in comp_data["keywords"]:
            if kw in full_text:
                matched.append(comp_name)
                break
    return matched


def _serialize_affair_light(a: dict, competences: list = None) -> dict:
    """Sérialise une affaire pour les pages institutionnelles."""
    out = {
        "_id": str(a["_id"]),
        "title": a.get("title", "")[:150],
        "description": (a.get("description", "") or "")[:200],
        "gravity_score": a.get("gravity_score", 0),
        "sentiment": a.get("sentiment", "neutre"),
        "theme": a.get("theme", ""),
        "item_count": a.get("item_count", 0),
        "priority": a.get("priority", "minor"),
        "bmg": a.get("bmg", 0),
    }
    for k in ("created_at", "last_activity"):
        val = a.get(k)
        if val and hasattr(val, "isoformat"):
            out[k] = val.isoformat()
        elif val:
            out[k] = str(val)
        else:
            out[k] = ""
    if competences:
        out["competences"] = competences
    out["communes"] = _detect_communes(a)
    return out


def _is_affair_guadeloupe(affair: dict) -> bool:
    """Filtre Guadeloupe pour les affaires (département/région)."""
    MARQUEURS = {
        "guadeloupe", "pointe-à-pitre", "pointe-a-pitre", "basse-terre",
        "les abymes", "baie-mahault", "le moule", "sainte-anne",
        "saint-françois", "le gosier", "petit-bourg", "capesterre",
        "sainte-rose", "deshaies", "bouillante", "goyave", "lamentin",
        "trois-rivières", "vieux-habitants", "petit-canal",
        "port-louis", "anse-bertrand", "morne-à-l'eau",
        "marie-galante", "les saintes", "la désirade",
        "971", "gwadloup", "smgeag",
    }
    EXCLUSIONS = {
        "martinique", "ducos", "fort-de-france",
        "guyane", "cayenne", "réunion", "mayotte",
        "haïti", "haiti", "port-au-prince", "jovenel moïse",
        "israël", "israel", "gaza", "liban", "ukraine", "russie",
        "palestine", "syrie", "iran", "irak",
    }
    text_parts = [
        (affair.get("title", "") or "").lower(),
        (affair.get("description", "") or "")[:300].lower(),
        " ".join((affair.get("elected", []) or [])[:10]).lower(),
        " ".join((affair.get("institutions", []) or [])[:10]).lower(),
    ]
    full = " ".join(text_parts)

    for m in MARQUEURS:
        if m in full:
            return True
    for lieu in EXCLUSIONS:
        if lieu in full:
            return False
    return True  # sources locales → par défaut local


@router.get("/by-institution")
async def affairs_by_institution(
    institution: str = Query(default="departement", description="departement|region"),
):
    """Retourne les affaires groupées par compétence institutionnelle."""
    svc = _svc()
    competences = DEPARTEMENT_COMPETENCES if institution == "departement" else REGION_COMPETENCES

    all_affairs = list(svc.affairs.find({"status": "active"}).sort("gravity_score", -1))
    # Filtre Guadeloupe — exclut les affaires hors périmètre sauf gravité >= 0.70
    affairs = [a for a in all_affairs if _is_affair_guadeloupe(a) or a.get("gravity_score", 0) >= 0.70]

    # Grouper par compétence
    groups: dict = {}
    for comp_name, comp_data in competences.items():
        groups[comp_name] = {
            "color": comp_data["color"],
            "count": 0,
            "max_gravity": 0,
            "affairs": [],
        }

    unmatched = []
    for affair in affairs:
        matched = _match_competences(affair, competences)
        if not matched:
            unmatched.append(_serialize_affair_light(affair))
            continue
        serialized = _serialize_affair_light(affair, matched)
        for comp in matched:
            groups[comp]["count"] += 1
            groups[comp]["max_gravity"] = max(
                groups[comp]["max_gravity"], affair.get("gravity_score", 0)
            )
            groups[comp]["affairs"].append(serialized)

    # Trier les groupes par nombre d'affaires desc
    sorted_groups = dict(
        sorted(groups.items(), key=lambda x: x[1]["count"], reverse=True)
    )

    return {
        "institution": institution,
        "groups": sorted_groups,
        "total_matched": sum(g["count"] for g in groups.values()),
        "total_unmatched": len(unmatched),
        "unmatched": unmatched[:10],
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
