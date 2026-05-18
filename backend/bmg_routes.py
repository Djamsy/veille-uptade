# backend/bmg_routes.py
"""
Routes API pour le Bruit Médiatique Guadeloupe (BMG) — VUE GLOBALE.

⚠️  Ne pas confondre avec le BMG **par affaire** calculé dans
   `affair_lifecycle_service.AffairLifecycleService.calculate_bmg()`, qui
   est la source utilisée par le dashboard et la liste des affaires (champ
   `affair.bmg` ∈ [0,1]).

Ces routes calculent un buzz global agrégé sur tous les articles d'une
période (concentration top-thème + diversité), retourné en échelle 0-100.
Conservé pour cas d'usage analytiques mais NON utilisé pour le tri/affichage
des affaires. Le frontend lit `affair.bmg * 100`, pas cet endpoint.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query
from pymongo import DESCENDING

from backend.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def calculate_media_buzz(
    hours: int = 24,
    min_articles: int = 3
) -> Dict[str, Any]:
    """
    Calculer le bruit médiatique (BMG) pour les dernières N heures
    
    Args:
        hours: Période d'analyse en heures
        min_articles: Nombre minimum d'articles pour considérer un sujet
    
    Returns:
        Dict avec les thèmes et entités les plus médiatisés
    """
    try:
        db = get_db()
        articles_coll = db.articles_guadeloupe
        
        # Période d'analyse
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Agrégation par thème
        theme_pipeline = [
            {"$match": {
                "scraped_at": {"$gte": cutoff},
                "theme": {"$exists": True, "$ne": None}
            }},
            {"$group": {
                "_id": "$theme",
                "count": {"$sum": 1},
                "sources": {"$addToSet": "$source"},
                "avg_importance": {"$avg": "$importance"}
            }},
            {"$match": {"count": {"$gte": min_articles}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        
        themes = list(articles_coll.aggregate(theme_pipeline))
        
        # Agrégation par entité principale
        entity_pipeline = [
            {"$match": {
                "scraped_at": {"$gte": cutoff},
                "main_entity": {"$exists": True, "$ne": None}
            }},
            {"$group": {
                "_id": "$main_entity",
                "count": {"$sum": 1},
                "sources": {"$addToSet": "$source"},
                "themes": {"$addToSet": "$theme"},
                "avg_importance": {"$avg": "$importance"}
            }},
            {"$match": {"count": {"$gte": min_articles}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        
        entities = list(articles_coll.aggregate(entity_pipeline))
        
        # Calcul du score BMG global (0-100)
        # scraped_at peut être stocké en datetime ou en string ISO selon le scraper
        # — interroger les 2 formats pour éviter total_articles=0 silencieux.
        cutoff_str = cutoff.isoformat()
        total_articles = articles_coll.count_documents({
            "$or": [
                {"scraped_at": {"$gte": cutoff}},
                {"scraped_at": {"$gte": cutoff_str}},
            ]
        })
        
        # Score basé sur la concentration et la diversité
        bmg_score = 0
        if total_articles > 0 and themes:
            # Concentration: top thème / total
            top_theme_count = themes[0]['count'] if themes else 0
            concentration = (top_theme_count / total_articles) * 100
            
            # Diversité: nombre de sources distinctes
            all_sources = set()
            for theme in themes:
                all_sources.update(theme['sources'])
            diversity = len(all_sources) * 5  # 5 points par source
            
            # Score final (pondéré)
            bmg_score = min(100, (concentration * 0.6) + (diversity * 0.4))
        
        return {
            "period_hours": hours,
            "total_articles": total_articles,
            "bmg_score": round(bmg_score, 1),
            "intensity_level": (
                "très élevé" if bmg_score >= 70 else
                "élevé" if bmg_score >= 50 else
                "modéré" if bmg_score >= 30 else
                "faible"
            ),
            "top_themes": [
                {
                    "theme": t["_id"],
                    "article_count": t["count"],
                    "source_count": len(t["sources"]),
                    "avg_importance": round(t.get("avg_importance", 0), 2)
                }
                for t in themes
            ],
            "top_entities": [
                {
                    "entity": e["_id"],
                    "article_count": e["count"],
                    "source_count": len(e["sources"]),
                    "theme_count": len(e["themes"]),
                    "avg_importance": round(e.get("avg_importance", 0), 2)
                }
                for e in entities
            ],
            "calculated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur calcul BMG: {e}")
        raise


@router.get("/calculate")
async def get_media_buzz(
    hours: int = Query(24, ge=1, le=168, description="Période en heures"),
    min_articles: int = Query(3, ge=1, description="Seuil minimum d'articles")
) -> Dict[str, Any]:
    """
    Calculer le bruit médiatique actuel
    
    - **hours**: Période d'analyse (1-168h, défaut: 24h)
    - **min_articles**: Nombre minimum d'articles (défaut: 3)
    """
    try:
        return calculate_media_buzz(hours=hours, min_articles=min_articles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_bmg_history(
    days: int = Query(7, ge=1, le=30, description="Nombre de jours")
) -> Dict[str, Any]:
    """
    Historique du BMG sur N jours
    """
    try:
        db = get_db()
        history_coll = db.bmg_history
        
        # Récupérer l'historique
        cutoff = datetime.utcnow() - timedelta(days=days)
        history = list(history_coll.find(
            {"calculated_at": {"$gte": cutoff}},
            {"_id": 0}
        ).sort("calculated_at", DESCENDING))
        
        return {
            "days": days,
            "data_points": len(history),
            "history": history
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-snapshot")
async def save_bmg_snapshot() -> Dict[str, Any]:
    """
    Sauvegarder un snapshot BMG dans l'historique
    """
    try:
        bmg_data = calculate_media_buzz(hours=24)
        
        db = get_db()
        history_coll = db.bmg_history
        
        # Sauvegarder
        history_coll.insert_one(bmg_data)
        
        return {
            "success": True,
            "bmg_score": bmg_data["bmg_score"],
            "saved_at": bmg_data["calculated_at"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


logger.info("✅ Routes BMG chargées")
