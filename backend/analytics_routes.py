# backend/analytics_routes.py
"""
Routes Analytics pour l'analyse des articles, thèmes et personnalités
CORRIGÉ: Utilise 'elected' au lieu de 'mentioned_elus' et base 'veille_media'
"""
from fastapi import APIRouter, Query, HTTPException, Response, Depends
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
import logging
import os
from pymongo.errors import PyMongoError
from pymongo.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# ======================================================================
#                        CONNEXION DATABASE
# ======================================================================

def get_database() -> Database:
    """Récupère la connexion MongoDB depuis le contexte global"""
    try:
        # Import au runtime pour éviter les cycles
        import sys
        from pathlib import Path
        
        # Ajouter le répertoire parent au path
        backend_dir = Path(__file__).parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        
        # Importer get_db depuis server
        from server import get_db
        db = get_db()
        
        # CORRECTION: S'assurer qu'on utilise la bonne base de données
        if hasattr(db, 'name') and db.name != 'veille_media':
            # Si on n'est pas sur la bonne base, forcer veille_media
            client = db.client
            db = client['veille_media']
            logger.info(f"Base de données corrigée vers: {db.name}")
        
        return db
    except ImportError as e:
        logger.error(f"Impossible d'importer get_db: {e}")
        raise HTTPException(status_code=500, detail="Erreur de configuration serveur")

def get_articles_collection(db: Database = Depends(get_database)):
    """Récupère la collection d'articles"""
    coll_name = os.getenv("ARTICLES_COLLECTION", "articles_guadeloupe")
    
    # Vérifier si la collection existe
    if coll_name not in db.list_collection_names():
        # Fallback sur "articles" si la collection n'existe pas
        if "articles" in db.list_collection_names():
            coll_name = "articles"
        else:
            logger.warning(f"Collection {coll_name} introuvable, utilisation par défaut")
    
    logger.info(f"Utilisation collection: {db.name}.{coll_name}")
    return db[coll_name]

# ======================================================================
#                     EXPRESSIONS MONGODB RÉUTILISABLES
# ======================================================================

def source_expression() -> Dict:
    """Expression MongoDB pour extraire la source d'un article"""
    return {"$ifNull": [
        "$source",
        {"$ifNull": [
            "$source.name",
            {"$ifNull": ["$publisher", {"$ifNull": ["$origin", "Inconnu"]}]}
        ]}
    ]}

def date_expression() -> Dict:
    """Expression MongoDB pour extraire la date d'un article"""
    base = {"$ifNull": [
        "$published_at",  # Champ enrichi
        {"$ifNull": [
            "$published",
            {"$ifNull": [
                "$created_at",
                {"$ifNull": [
                    "$captured_at",
                    {"$ifNull": [
                        "$scraped_at",
                        {"$ifNull": ["$date", "$timestamp"]}
                    ]}
                ]}
            ]}
        ]}
    ]}
    
    return {
        "$let": {
            "vars": {"dateValue": base},
            "in": {
                "$cond": [
                    {"$eq": [{"$type": "$$dateValue"}, "date"]},
                    "$$dateValue",
                    {"$dateFromString": {
                        "dateString": "$$dateValue",
                        "onError": "$$NOW"
                    }}
                ]
            }
        }
    }

def sentiment_expression() -> Dict:
    """Expression MongoDB pour extraire le score de sentiment"""
    return {"$ifNull": [
        "$sentiment_score",  # Champ enrichi
        {"$ifNull": [
            "$sentiment.score",
            {"$ifNull": [
                "$reactionPrediction.population_reaction.overall_score",
                {"$ifNull": ["$analysis.sentiment.score", 0]}
            ]}
        ]}
    ]}

def themes_expression() -> Dict:
    """Expression MongoDB pour extraire les thèmes"""
    return {"$ifNull": [
        "$themes",  # Champ enrichi par votre script
        {"$cond": [
            {"$isArray": "$tags"},
            "$tags",
            []
        ]}
    ]}

def elus_expression() -> Dict:
    """Expression MongoDB pour extraire les élus mentionnés"""
    # CORRECTION: Utiliser 'elected' comme champ principal
    return {"$ifNull": [
        "$elected",  # CHAMP PRINCIPAL - détecté dans vos données
        {"$ifNull": [
            "$mentioned_elus",  # Fallback
            {"$cond": [
                {"$isArray": "$personnalites"},
                "$personnalites",
                []
            ]}
        ]}
    ]}

# ======================================================================
#                        FONCTIONS HELPERS
# ======================================================================

def create_chart_data(labels: List[str], values: List[float], label: str = "Valeurs") -> Dict:
    """Crée un objet de données pour les graphiques frontend"""
    return {
        "chart_data": {
            "labels": labels,
            "datasets": [{
                "label": label,
                "data": values
            }]
        }
    }

def handle_db_error(operation: str, error: Exception) -> Dict:
    """Gère les erreurs MongoDB de manière uniforme"""
    logger.error(f"Erreur MongoDB dans {operation}: {error}")
    return {
        "success": False,
        "error": str(error),
        "message": f"Erreur lors de l'opération: {operation}"
    }

# ======================================================================
#                     ENDPOINTS PRINCIPAUX
# ======================================================================

@router.get("/api/dashboard-stats")
async def dashboard_stats(db: Database = Depends(get_database)):
    """ENDPOINT PRINCIPAL pour le dashboard - remplace /api/stats/dashboard"""
    try:
        coll = get_articles_collection(db)
        
        # Métriques de base
        total_articles = coll.count_documents({})
        
        # Articles enrichis (avec thèmes)
        enriched_themes = coll.count_documents({"themes": {"$exists": True, "$ne": []}})
        
        # Articles avec élus (CORRECTION: utiliser 'elected')
        enriched_elus = coll.count_documents({"elected": {"$exists": True, "$ne": []}})
        
        # Articles d'aujourd'hui
        today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
        today_count = coll.count_documents({
            "$expr": {
                "$gte": [date_expression(), today_start]
            }
        })
        
        # Sources distinctes
        sources = coll.distinct("source")
        
        # Thèmes uniques
        all_themes = []
        for doc in coll.find({"themes": {"$exists": True, "$ne": []}}, {"themes": 1}):
            if doc.get("themes"):
                all_themes.extend(doc["themes"])
        unique_themes = len(set(all_themes))
        
        # Élus uniques (CORRECTION: utiliser 'elected')
        all_elus = []
        for doc in coll.find({"elected": {"$exists": True, "$ne": []}}, {"elected": 1}):
            if doc.get("elected"):
                all_elus.extend(doc["elected"])
        unique_elus = len(set(all_elus))
        
        return {
            "success": True,
            "total_articles": total_articles,
            "enriched_articles": enriched_themes,
            "articles_with_elus": enriched_elus,
            "today_articles": today_count,
            "unique_sources": len(sources),
            "unique_themes": unique_themes,
            "unique_elus": unique_elus,
            "enrichment_rate": f"{(enriched_themes/total_articles*100 if total_articles > 0 else 0):.1f}%"
        }
        
    except Exception as e:
        return handle_db_error("dashboard_stats", e)

@router.get("/api/themes")
async def get_themes(db: Database = Depends(get_database)):
    """ENDPOINT pour récupérer tous les thèmes avec compteurs"""
    try:
        coll = get_articles_collection(db)
        
        pipeline = [
            {"$match": {"themes": {"$exists": True, "$ne": []}}},
            {"$unwind": "$themes"},
            {"$group": {
                "_id": "$themes",
                "count": {"$sum": 1},
                "articles": {"$push": {
                    "_id": {"$toString": "$_id"},
                    "title": "$title",
                    "published_at": "$published_at"
                }}
            }},
            {"$project": {
                "name": "$_id",
                "count": 1,
                "recent_articles": {"$slice": ["$articles", 3]},
                "_id": 0
            }},
            {"$sort": {"count": -1}}
        ]
        
        themes = list(coll.aggregate(pipeline))
        
        return {
            "success": True,
            "themes": themes,
            "total": len(themes)
        }
        
    except Exception as e:
        return handle_db_error("get_themes", e)

@router.get("/api/elus")
async def get_elus(db: Database = Depends(get_database)):
    """ENDPOINT pour récupérer tous les élus avec compteurs"""
    try:
        coll = get_articles_collection(db)
        
        # CORRECTION: Utiliser 'elected' au lieu de 'mentioned_elus'
        pipeline = [
            {"$match": {"elected": {"$exists": True, "$ne": []}}},
            {"$unwind": "$elected"},
            {"$group": {
                "_id": "$elected",
                "article_count": {"$sum": 1},
                "themes": {"$push": "$themes"},
                "articles": {"$push": {
                    "_id": {"$toString": "$_id"},
                    "title": "$title",
                    "published_at": "$published_at"
                }}
            }},
            {"$project": {
                "name": "$_id",
                "article_count": 1,
                "themes": {
                    "$reduce": {
                        "input": "$themes",
                        "initialValue": [],
                        "in": {"$setUnion": ["$$value", "$$this"]}
                    }
                },
                "recent_articles": {"$slice": ["$articles", 3]},
                "_id": 0
            }},
            {"$sort": {"article_count": -1}}
        ]
        
        elus = list(coll.aggregate(pipeline))
        
        return {
            "success": True,
            "elus": elus,
            "total": len(elus)
        }
        
    except Exception as e:
        return handle_db_error("get_elus", e)

@router.get("/api/analytics/dashboard")
async def analytics_dashboard(
    days: int = Query(30, ge=1, le=365),
    db: Database = Depends(get_database)
):
    """Dashboard analytique détaillé"""
    try:
        coll = get_articles_collection(db)
        now = datetime.utcnow()
        since = now - timedelta(days=days)
        
        # Métriques de base
        total_articles = coll.count_documents({})
        
        # Articles enrichis (CORRECTION: avec thèmes ET/OU élus)
        enriched_count = coll.count_documents({
            "$or": [
                {"themes": {"$exists": True, "$ne": []}},
                {"elected": {"$exists": True, "$ne": []}}  # CORRECTION: elected au lieu de mentioned_elus
            ]
        })
        
        # Articles d'aujourd'hui
        today_start = datetime.combine(now.date(), datetime.min.time())
        today_count = coll.count_documents({
            "$expr": {
                "$gte": [date_expression(), today_start]
            }
        })
        
        # Sources distinctes
        sources = coll.distinct("source")
        
        # Pipeline pour top sources
        pipeline_sources = [
            {"$addFields": {"_date": date_expression(), "_source": source_expression()}},
            {"$match": {"$expr": {"$gte": ["$_date", since]}}},
            {"$group": {"_id": "$_source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
            {"$project": {"source": "$_id", "count": 1, "_id": 0}}
        ]
        top_sources = list(coll.aggregate(pipeline_sources))
        
        # Métriques dashboard
        metrics = {
            "total_articles": {"label": "Total Articles", "value": total_articles},
            "enriched_articles": {"label": "Articles Enrichis", "value": enriched_count},
            "enrichment_rate": {"label": "Taux d'enrichissement", "value": f"{(enriched_count/total_articles*100 if total_articles > 0 else 0):.1f}%"},
            "today_articles": {"label": "Articles Aujourd'hui", "value": today_count},
            "distinct_sources": {"label": "Sources", "value": len(sources)},
            "window_days": {"label": "Période (jours)", "value": days}
        }
        
        return {
            "success": True,
            "metrics": metrics,
            "top_sources": top_sources,
            "period": {
                "start": since.isoformat(),
                "end": now.isoformat(),
                "days": days
            }
        }
        
    except Exception as e:
        return handle_db_error("analytics_dashboard", e)

@router.get("/api/analytics/top-themes")
async def get_top_themes(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: Database = Depends(get_database)
):
    """Retourne les thèmes les plus fréquents"""
    try:
        coll = get_articles_collection(db)
        since = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {
                "themes": {"$exists": True, "$ne": []},
                "$expr": {"$gte": [date_expression(), since]}
            }},
            {"$unwind": "$themes"},
            {"$group": {
                "_id": "$themes",
                "count": {"$sum": 1},
                "articles": {"$push": {
                    "title": "$title",
                    "published_at": "$published_at",
                    "_id": {"$toString": "$_id"}
                }}
            }},
            {"$project": {
                "theme": "$_id",
                "count": 1,
                "recent_articles": {"$slice": ["$articles", 3]},
                "_id": 0
            }},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        themes = list(coll.aggregate(pipeline))
        
        return {
            "success": True,
            "items": themes,
            "total": len(themes),
            "period_days": days
        }
        
    except Exception as e:
        return handle_db_error("top_themes", e)

@router.get("/api/analytics/top-elected")
async def get_top_elected(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(15, ge=1, le=100),
    db: Database = Depends(get_database)
):
    """Retourne les personnalités les plus mentionnées"""
    try:
        coll = get_articles_collection(db)
        since = datetime.utcnow() - timedelta(days=days)
        
        # CORRECTION: Utiliser 'elected' au lieu de 'mentioned_elus'
        pipeline = [
            {"$match": {
                "elected": {"$exists": True, "$ne": []},  # CORRECTION ICI
                "$expr": {"$gte": [date_expression(), since]}
            }},
            {"$unwind": "$elected"},  # CORRECTION ICI
            {"$group": {
                "_id": "$elected",  # CORRECTION ICI
                "count": {"$sum": 1},
                "sentiment_scores": {"$push": "$sentiment_score"},
                "themes": {"$push": "$themes"},
                "articles": {"$push": {
                    "title": "$title",
                    "published_at": "$published_at"
                }}
            }},
            {"$project": {
                "elected": "$_id",
                "count": 1,
                "avg_sentiment": {"$avg": "$sentiment_scores"},
                "themes": {
                    "$reduce": {
                        "input": "$themes",
                        "initialValue": [],
                        "in": {"$setUnion": ["$$value", "$$this"]}
                    }
                },
                "recent_articles": {"$slice": ["$articles", 3]},
                "_id": 0
            }},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        elected = list(coll.aggregate(pipeline))
        
        # Calculer la distribution des sentiments si disponible
        for person in elected:
            if person.get("avg_sentiment") is not None:
                person["sentiment_distribution"] = {
                    "positive": sum(1 for s in person.get("sentiment_scores", []) if s and s > 0.3),
                    "neutral": sum(1 for s in person.get("sentiment_scores", []) if s and -0.3 <= s <= 0.3),
                    "negative": sum(1 for s in person.get("sentiment_scores", []) if s and s < -0.3)
                }
        
        return {
            "success": True,
            "items": elected,
            "total": len(elected),
            "period_days": days
        }
        
    except Exception as e:
        return handle_db_error("top_elected", e)

@router.get("/api/articles/by-theme/{theme}")
async def get_articles_by_theme(theme: str, db: Database = Depends(get_database)):
    """Récupérer les articles d'un thème spécifique"""
    try:
        coll = get_articles_collection(db)
        
        articles = list(coll.find(
            {"themes": theme},
            {
                "_id": 0,
                "title": 1,
                "source": 1,
                "published_at": 1,
                "themes": 1,
                "elected": 1,  # CORRECTION: elected au lieu de mentioned_elus
                "url": 1
            }
        ).sort("published_at", -1).limit(50))
        
        return {
            "success": True,
            "articles": articles,
            "theme": theme,
            "total": len(articles)
        }
        
    except Exception as e:
        return handle_db_error("articles_by_theme", e)

@router.get("/api/articles/by-elu/{elu_name}")
async def get_articles_by_elu(elu_name: str, db: Database = Depends(get_database)):
    """Récupérer les articles mentionnant un élu spécifique"""
    try:
        coll = get_articles_collection(db)
        
        # CORRECTION: Chercher dans 'elected' au lieu de 'mentioned_elus'
        articles = list(coll.find(
            {"elected": elu_name},
            {
                "_id": 0,
                "title": 1,
                "source": 1,
                "published_at": 1,
                "themes": 1,
                "elected": 1,  # CORRECTION: elected au lieu de mentioned_elus
                "url": 1
            }
        ).sort("published_at", -1).limit(50))
        
        return {
            "success": True,
            "articles": articles,
            "elu": elu_name,
            "total": len(articles)
        }
        
    except Exception as e:
        return handle_db_error("articles_by_elu", e)

# ======================================================================
#                      ENDPOINTS DE SANTÉ ET DEBUG
# ======================================================================

@router.head("/api/analytics/health")
async def health_check():
    """Health check pour les analytics"""
    return Response(status_code=200)

@router.get("/api/analytics/_debug/sample")
async def debug_sample(db: Database = Depends(get_database)):
    """Retourne un échantillon de document pour debug"""
    try:
        coll = get_articles_collection(db)
        
        # Échantillon avec thèmes
        sample_themes = coll.find_one({"themes": {"$exists": True, "$ne": []}}, {
            "_id": 0,
            "title": 1,
            "source": 1,
            "published_at": 1,
            "themes": 1
        })
        
        # Échantillon avec élus (CORRECTION: elected)
        sample_elus = coll.find_one({"elected": {"$exists": True, "$ne": []}}, {
            "_id": 0,
            "title": 1,
            "source": 1,
            "published_at": 1,
            "elected": 1
        })
        
        # Compteurs de vérification
        stats = {
            "total_articles": coll.count_documents({}),
            "with_themes": coll.count_documents({"themes": {"$exists": True, "$ne": []}}),
            "with_elected": coll.count_documents({"elected": {"$exists": True, "$ne": []}}),
            "with_mentioned_elus": coll.count_documents({"mentioned_elus": {"$exists": True, "$ne": []}})
        }
        
        return {
            "success": True,
            "database": db.name,
            "collection": coll.name,
            "stats": stats,
            "sample_with_themes": sample_themes,
            "sample_with_elected": sample_elus
        }
        
    except Exception as e:
        return handle_db_error("debug_sample", e)