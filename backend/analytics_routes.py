from fastapi import APIRouter, Query, HTTPException, Response
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import logging
import os
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------- Helpers de secours (si non fournis par un service dédié) ----------
try:
    _get_articles_coll  # type: ignore  # noqa: F401
except NameError:
    def _get_articles_coll():
        """Retourne la collection Mongo d'articles.
        Priorité: env ARTICLES_COLLECTION -> 'articles_guadeloupe' -> 'articles'.
        """
        try:
            # Import paresseux pour éviter les imports circulaires
            from .server import get_db  # type: ignore
        except Exception:
            from backend.server import get_db  # type: ignore
        db = get_db()
        coll_name = os.getenv("ARTICLES_COLLECTION", "").strip() or "articles_guadeloupe"
        if coll_name not in db.list_collection_names():
            coll_name = "articles"
        return db[coll_name]

try:
    _source_expr  # type: ignore  # noqa: F401
except NameError:
    def _source_expr() -> Any:
        """Expr Mongo pour la source (compat 'source'/'source.name'/'publisher'/'origin')."""
        return {"$ifNull": [
            "$source",
            {"$ifNull": [
                "$source.name",
                {"$ifNull": ["$publisher", {"$ifNull": ["$origin", "Inconnu"]}]}
            ]}
        ]}

try:
    _date_expr  # type: ignore  # noqa: F401
except NameError:
    def _date_expr() -> Any:
        """Expr Mongo pour la date de référence avec conversion sûre (string -> date)."""
        base = {"$ifNull": [
            "$published",
            {"$ifNull": [
                "$created_at",
                {"$ifNull": [
                    "$captured_at",
                    {"$ifNull": [
                        "$ingested_at",
                        {"$ifNull": [
                            "$scraped_at",
                            {"$ifNull": [
                                "$date",
                                {"$ifNull": [
                                    "$timestamp",
                                    None
                                ]}
                            ]}
                        ]}
                    ]}
                ]}
            ]}
        ]}
        return {
            "$let": {
                "vars": {"b": base},
                "in": {
                    "$cond": [
                        {"$eq": [{"$type": "$$b"}, "date"]},
                        "$$b",
                        {"$ifNull": [{"$toDate": "$$b"}, "$$NOW"]}
                    ]
                }
            }
        }

try:
    _sentiment_expr  # type: ignore  # noqa: F401
except NameError:
    def _sentiment_expr() -> Any:
        """Expr Mongo pour récupérer un score de sentiment normalisé si présent."""
        return {"$ifNull": [
            "$sentiment.score",
            {"$ifNull": [
                "$reactionPrediction.population_reaction.overall_score",
                {"$ifNull": ["$analysis.sentiment.score", 0]}
            ]}
        ]}

# ---------- Endpoints agrégés / charts ----------
@router.get("/api/analytics/dashboard", operation_id="analytics_dashboard_v1")
def analytics_dashboard(days: int = Query(365, ge=1, le=365)):
    """Retourne le payload complet attendu par le front Analytics.
    Inclut: dashboardMetrics, sourceChart, timelineChart, sentimentChart.
    Les structures sont *toujours présentes* (objets vides valides si aucune donnée).
    """
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        since = now - timedelta(days=days)

        # ---- Dashboard metrics ----
        total = coll.count_documents({})
        distinct_sources = coll.distinct("source") or coll.distinct("source.name")
        sources_count = len([s for s in distinct_sources if s])
        today_floor = datetime.fromisoformat(now.strftime("%Y-%m-%d") + "T00:00:00")
        today_count = coll.count_documents({
            "$or": [
                {"published": {"$gte": today_floor}},
                {"created_at": {"$gte": today_floor}},
                {"captured_at": {"$gte": today_floor}},
            ]
        })
        pipeline_top = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": _source_expr(), "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
            {"$limit": 5},
        ]
        top_sources = list(coll.aggregate(pipeline_top))
        dashboard_metrics = {
            "metrics": {
                "total_articles": {"label": "Articles", "value": total},
                "distinct_sources": {"label": "Sources", "value": sources_count},
                "today_articles": {"label": "Aujourd'hui", "value": today_count},
                "window_days": {"label": "Fenêtre (jours)", "value": days},
            },
            "top_sources": top_sources,
        }

        # ---- Articles par source ----
        pipeline_src = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": _source_expr(), "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
        ]
        src_items = list(coll.aggregate(pipeline_src))
        src_labels = [it.get("source") or "Inconnu" for it in src_items]
        src_counts = [int(it.get("count", 0)) for it in src_items]
        source_chart = {
            "chart_data": {
                "labels": src_labels,
                "datasets": [{"label": "Articles", "data": src_counts}],
            },
            "total_articles": sum(src_counts) if src_counts else 0,
            "period": f"{days} jours",
        }

        # ---- Timeline (par jour) ----
        pipeline_time = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_when"}}, "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "date": "$_id", "count": 1}},
            {"$sort": {"date": 1}},
        ]
        time_items = list(coll.aggregate(pipeline_time))
        # Normaliser en labels/datasets pour le front (Chart.js)
        time_labels = [x.get("date") for x in time_items]
        time_counts = [int(x.get("count", 0)) for x in time_items]
        timeline_chart = {
            "chart_data": {
                "labels": time_labels,
                "datasets": [{"label": "Articles/jour", "data": time_counts}],
            },
            "total_articles": sum(time_counts) if time_counts else 0,
            "period": f"{days} jours",
        }

        # ---- Sentiment moyen par source ----
        pipeline_sent = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$addFields": {"_score": _sentiment_expr()}},
            {"$group": {"_id": _source_expr(), "n": {"$sum": 1}, "avg_sentiment": {"$avg": "$_score"}}},
            {"$project": {"_id": 0, "source": "$_id", "n": 1, "avg_sentiment": 1}},
            {"$sort": {"avg_sentiment": -1, "source": 1}},
        ]
        sent_items = list(coll.aggregate(pipeline_sent))
        for it in sent_items:
            if it.get("avg_sentiment") is None:
                it["avg_sentiment"] = 0
        sent_labels = [it.get("source") or "Inconnu" for it in sent_items]
        sent_values = [float(it.get("avg_sentiment") or 0) for it in sent_items]
        sentiment_chart = {
            "chart_data": {
                "labels": sent_labels,
                "datasets": [{"label": "Score moyen", "data": sent_values}],
            },
            "analyzed_articles": sum(int(it.get("n", 0)) for it in sent_items) if sent_items else 0,
        }

        return {
            "success": True,
            "dashboardMetrics": dashboard_metrics,
            "sourceChart": source_chart,
            "timelineChart": timeline_chart,
            "sentimentChart": sentiment_chart,
        }

    except PyMongoError as e:
        logger.exception("analytics_dashboard: %s", e)
        return {
            "success": True,
            "dashboardMetrics": {"metrics": {}, "top_sources": []},
            "sourceChart": {"chart_data": {"labels": [], "datasets": []}, "total_articles": 0, "period": f"{days} jours"},
            "timelineChart": {"chart_data": [], "total_articles": 0, "period": f"{days} jours"},
            "sentimentChart": {"chart_data": {"labels": [], "datasets": []}, "analyzed_articles": 0},
        }


@router.get("/api/analytics/articles-by-source", operation_id="analytics_articles_by_source_v1")
def analytics_articles_by_source(days: int = Query(365, ge=1, le=365)):
    """Histogramme des articles par source (labels/datasets)."""
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        since = now - timedelta(days=days)
        pipeline = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": _source_expr(), "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        labels = [it.get("source") or "Inconnu" for it in items]
        counts = [int(it.get("count", 0)) for it in items]
        return {
            "success": True,
            "chart_data": {"labels": labels, "datasets": [{"label": "Articles", "data": counts}]},
            "total_articles": sum(counts) if counts else 0,
            "period": f"{days} jours",
        }
    except PyMongoError as e:
        logger.exception("articles-by-source: %s", e)
        return {"success": True, "chart_data": {"labels": [], "datasets": []}, "total_articles": 0, "period": f"{days} jours"}


@router.head("/api/analytics/articles-by-source")
def head_analytics_articles_by_source():
    return Response(status_code=200)


@router.get("/api/analytics/articles-timeline", operation_id="analytics_articles_timeline_v1")
def analytics_articles_timeline(days: int = Query(365, ge=1, le=365)):
    """Tableau {date,count} pour l'évolution quotidienne des articles."""
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        since = now - timedelta(days=days)
        pipeline = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_when"}}, "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "date": "$_id", "count": 1}},
            {"$sort": {"date": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        labels = [x.get("date") for x in items]
        counts = [int(x.get("count", 0)) for x in items]
        return {
            "success": True,
            "chart_data": {"labels": labels, "datasets": [{"label": "Articles/jour", "data": counts}]},
            "total_articles": sum(counts) if counts else 0,
            "period": f"{days} jours",
        }
    except PyMongoError as e:
        logger.exception("articles-timeline: %s", e)
        return {"success": True, "chart_data": [], "total_articles": 0, "period": f"{days} jours"}


@router.head("/api/analytics/articles-timeline")
def head_analytics_articles_timeline():
    return Response(status_code=200)


@router.get("/api/analytics/sentiment-by-source", operation_id="analytics_sentiment_by_source_v1")
def analytics_sentiment_by_source(days: int = Query(365, ge=1, le=365)):
    """Score de sentiment moyen par source (labels/datasets)."""
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        since = now - timedelta(days=days)
        pipeline = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$addFields": {"_score": _sentiment_expr()}},
            {"$group": {"_id": _source_expr(), "n": {"$sum": 1}, "avg_sentiment": {"$avg": "$_score"}}},
            {"$project": {"_id": 0, "source": "$_id", "n": 1, "avg_sentiment": 1}},
            {"$sort": {"avg_sentiment": -1, "source": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        for it in items:
            if it.get("avg_sentiment") is None:
                it["avg_sentiment"] = 0
        labels = [it.get("source") or "Inconnu" for it in items]
        scores = [float(it.get("avg_sentiment") or 0) for it in items]
        return {
            "success": True,
            "chart_data": {"labels": labels, "datasets": [{"label": "Score moyen", "data": scores}]},
            "analyzed_articles": sum(int(it.get("n", 0)) for it in items) if items else 0,
        }
    except PyMongoError as e:
        logger.exception("sentiment-by-source: %s", e)
        return {"success": True, "chart_data": {"labels": [], "datasets": []}, "analyzed_articles": 0}


@router.head("/api/analytics/sentiment-by-source")
def head_analytics_sentiment_by_source():
    return Response(status_code=200)


@router.get("/api/analytics/dashboard-metrics", operation_id="analytics_dashboard_metrics_v1")
def analytics_dashboard_metrics(days: int = Query(365, ge=1, le=365)):
    """Retourne uniquement le bloc dashboardMetrics (compat)."""
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        since = now - timedelta(days=days)
        total = coll.count_documents({})
        distinct_sources = coll.distinct("source") or coll.distinct("source.name")
        sources_count = len([s for s in distinct_sources if s])
        today_floor = datetime.fromisoformat(now.strftime("%Y-%m-%d") + "T00:00:00")
        today_count = coll.count_documents({
            "$or": [
                {"published": {"$gte": today_floor}},
                {"created_at": {"$gte": today_floor}},
                {"captured_at": {"$gte": today_floor}},
            ]
        })
        pipeline_top = [
            {"$addFields": {"_when": _date_expr()}},
            {"$match": {"$expr": {"$gte": ["$_when", since]}}},
            {"$group": {"_id": _source_expr(), "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
            {"$limit": 5},
        ]
        top_sources = list(coll.aggregate(pipeline_top))
        return {
            "success": True,
            "dashboardMetrics": {
                "metrics": {
                    "total_articles": {"label": "Articles", "value": total},
                    "distinct_sources": {"label": "Sources", "value": sources_count},
                    "today_articles": {"label": "Aujourd'hui", "value": today_count},
                    "window_days": {"label": "Fenêtre (jours)", "value": days},
                },
                "top_sources": top_sources,
            }
        }
    except PyMongoError as e:
        logger.exception("dashboard-metrics: %s", e)
        return {"success": True, "dashboardMetrics": {"metrics": {}, "top_sources": []}}


@router.head("/api/analytics/dashboard-metrics")
def head_analytics_dashboard_metrics():
    return Response(status_code=200)


# ---------- Debug endpoint ----------
@router.get("/api/analytics/_debug/sample", operation_id="analytics_debug_sample")
def analytics_debug_sample():
    """Retourne un document d'exemple avec ses champs de date/source/sentiment pour debug rapide."""
    coll = _get_articles_coll()
    doc = coll.find_one({}, {
        "_id": 0,
        "title": 1,
        "source": 1,
        "publisher": 1,
        "origin": 1,
        "published": 1,
        "created_at": 1,
        "captured_at": 1,
        "ingested_at": 1,
        "scraped_at": 1,
        "date": 1,
        "timestamp": 1,
        "sentiment": 1,
        "reactionPrediction": 1,
        "analysis": 1,
    }) or {}
    return {"success": True, "sample": doc}


# ---------- Alias (snake/kebab, avec/sans trailing slash) ----------
@router.get("/api/analytics/articles_timeline", operation_id="analytics_articles_timeline_alias_snake")
@router.get("/api/analytics/articles-timeline/", operation_id="analytics_articles_timeline_alias_kebab_slash")
@router.get("/api/analytics/articles_timeline/", operation_id="analytics_articles_timeline_alias_snake_slash")
def analytics_articles_timeline_alias(days: int = Query(365, ge=1, le=365)):
    return analytics_articles_timeline(days)

@router.get("/api/analytics/sentiment_by_source", operation_id="analytics_sentiment_by_source_alias_snake")
@router.get("/api/analytics/sentiment-by-source/", operation_id="analytics_sentiment_by_source_alias_kebab_slash")
@router.get("/api/analytics/sentiment_by_source/", operation_id="analytics_sentiment_by_source_alias_snake_slash")
def analytics_sentiment_by_source_alias(days: int = Query(365, ge=1, le=365)):
    return analytics_sentiment_by_source(days)

@router.get("/api/analytics/dashboard_metrics", operation_id="analytics_dashboard_metrics_alias_snake")
@router.get("/api/analytics/dashboard-metrics/", operation_id="analytics_dashboard_metrics_alias_kebab_slash")
@router.get("/api/analytics/dashboard_metrics/", operation_id="analytics_dashboard_metrics_alias_snake_slash")
def analytics_dashboard_metrics_alias(days: int = Query(365, ge=1, le=365)):
    return analytics_dashboard_metrics(days)


# ---------- Dispatcher de compatibilité ----------
@router.get("/api/analytics/{slug}")
def analytics_dispatch(slug: str, days: int = Query(365, ge=1, le=365)):
    slug = (slug or "").strip().lower().rstrip("/")
    mapping = {
        "articles-by-source": analytics_articles_by_source,
        "articles_timeline": analytics_articles_timeline,
        "articles-timeline": analytics_articles_timeline,
        "sentiment-by-source": analytics_sentiment_by_source,
        "sentiment_by_source": analytics_sentiment_by_source,
        "dashboard-metrics": analytics_dashboard_metrics,
        "dashboard_metrics": analytics_dashboard_metrics,
        "dashboard": analytics_dashboard,
    }
    func = mapping.get(slug)
    if func is None:
        raise HTTPException(status_code=404, detail=f"analytics endpoint '{slug}' inconnu")
    return func(days)