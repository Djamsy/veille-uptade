# backend/analytics_routes.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import PyMongoError

from backend.db import get_db

logger = logging.getLogger("backend.analytics_routes")
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# ---------- Helpers DB ----------

def _get_articles_coll():
    db = get_db()
    # essaie plusieurs noms possibles, puis fallback "articles"
    names = set(db.list_collection_names())
    for n in ["articles", "news_articles", "rss_articles"]:
        if n in names:
            return db[n]
    return db["articles"]

def _source_expr():
    # source peut être "source" ou un objet {name: "..."}
    # -> on fabrique une expression MongoDB équivalente à: source.name || source || "Inconnu"
    return {
        "$ifNull": [
            {"$ifNull": ["$source.name", "$source"]},
            "Inconnu"
        ]
    }

def _sentiment_expr():
    # on prend un score si présent : sentiment.compound || ai_sentiment.score || ai_sentiment_score || textblob.polarity
    return {
        "$ifNull": [
            {"$ifNull": ["$sentiment.compound", "$ai_sentiment.score"]},
            {"$ifNull": ["$ai_sentiment_score", "$textblob.polarity"]}
        ]
    }

def _date_expr():
    # published || created_at || captured_at || now
    return {
        "$ifNull": [
            "$published",
            {"$ifNull": ["$created_at", {"$ifNull": ["$captured_at", datetime.utcnow()]}]}
        ]
    }

# ---------- Routes ----------

@router.get("/articles-by-source")
def articles_by_source(days: int = Query(30, ge=1, le=365)):
    """
    Compte d’articles par source sur N jours.
    """
    try:
        coll = _get_articles_coll()
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"$or": [
                {"published": {"$gte": since}},
                {"created_at": {"$gte": since}},
                {"captured_at": {"$gte": since}},
            ]}},
            {"$group": {
                "_id": _source_expr(),
                "count": {"$sum": 1}
            }},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        return {"success": True, "items": items, "days": days}
    except PyMongoError as e:
        logger.exception("articles_by_source: %s", e)
        return {"success": True, "items": [], "days": days}  # éviter de faire planter le front


@router.get("/articles-timeline")
def articles_timeline(days: int = Query(30, ge=1, le=365)):
    """
    Volume d’articles par jour (timeline) sur N jours.
    """
    try:
        coll = _get_articles_coll()
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"$or": [
                {"published": {"$gte": since}},
                {"created_at": {"$gte": since}},
                {"captured_at": {"$gte": since}},
            ]}},
            {"$addFields": {"_when": _date_expr()}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_when"}},
                "count": {"$sum": 1}
            }},
            {"$project": {"_id": 0, "date": "$_id", "count": 1}},
            {"$sort": {"date": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        return {"success": True, "items": items, "days": days}
    except PyMongoError as e:
        logger.exception("articles_timeline: %s", e)
        return {"success": True, "items": [], "days": days}


@router.get("/sentiment-by-source")
def sentiment_by_source(days: int = Query(30, ge=1, le=365)):
    """
    Sentiment moyen par source (score entre -1 et 1 si dispo).
    """
    try:
        coll = _get_articles_coll()
        since = datetime.utcnow() - timedelta(days=days)
        pipeline = [
            {"$match": {"$or": [
                {"published": {"$gte": since}},
                {"created_at": {"$gte": since}},
                {"captured_at": {"$gte": since}},
            ]}},
            {"$addFields": {"_score": _sentiment_expr()}},
            {"$group": {
                "_id": _source_expr(),
                "n": {"$sum": 1},
                "avg_sentiment": {"$avg": "$_score"}
            }},
            {"$project": {"_id": 0, "source": "$_id", "n": 1, "avg_sentiment": 1}},
            {"$sort": {"avg_sentiment": -1, "source": 1}},
        ]
        items = list(coll.aggregate(pipeline))
        # Remplace None par 0 pour lisibilité front
        for it in items:
            if it.get("avg_sentiment") is None:
                it["avg_sentiment"] = 0
        return {"success": True, "items": items, "days": days}
    except PyMongoError as e:
        logger.exception("sentiment_by_source: %s", e)
        return {"success": True, "items": [], "days": days}


@router.get("/dashboard-metrics")
def dashboard_metrics(days: int = Query(30, ge=1, le=365)):
    """
    Quelques KPI : total, nb de sources, articles aujourd’hui, top sources…
    """
    try:
        coll = _get_articles_coll()
        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")
        since = now - timedelta(days=days)

        # total articles
        total = coll.count_documents({})

        # sources distinctes
        distinct_sources = coll.distinct("source")
        if not distinct_sources:
            # si source est un objet, récupère source.name
            distinct_sources = coll.distinct("source.name")
        sources_count = len([s for s in distinct_sources if s])

        # articles aujourd’hui (sur published/created_at/captured_at)
        today_count = coll.count_documents({
            "$or": [
                {"published": {"$gte": datetime.fromisoformat(today_str + "T00:00:00")}},
                {"created_at": {"$gte": datetime.fromisoformat(today_str + "T00:00:00")}},
                {"captured_at": {"$gte": datetime.fromisoformat(today_str + "T00:00:00")}},
            ]
        })

        # top sources (sur N jours)
        pipeline = [
            {"$match": {"$or": [
                {"published": {"$gte": since}},
                {"created_at": {"$gte": since}},
                {"captured_at": {"$gte": since}},
            ]}},
            {"$group": {"_id": _source_expr(), "count": {"$sum": 1}}},
            {"$project": {"_id": 0, "source": "$_id", "count": 1}},
            {"$sort": {"count": -1, "source": 1}},
            {"$limit": 5},
        ]
        top_sources = list(coll.aggregate(pipeline))

        metrics = {
            "total_articles": total,
            "distinct_sources": sources_count,
            "today_articles": today_count,
            "top_sources": top_sources,
            "window_days": days,
        }
        return {"success": True, "metrics": metrics}
    except PyMongoError as e:
        logger.exception("dashboard_metrics: %s", e)
        return {"success": True, "metrics": {
            "total_articles": 0,
            "distinct_sources": 0,
            "today_articles": 0,
            "top_sources": [],
            "window_days": days,
        }}