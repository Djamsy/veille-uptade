# Ajouter à backend/server.py ou créer backend/transcription_sentiment_routes.py

from fastapi import APIRouter, Query, HTTPException, Body
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions-sentiment"])
logger = logging.getLogger("transcription_sentiment")

# Import des services (adapter selon votre structure)
try:
    from backend.sentiment_analysis_service import SentimentAnalyzer
    from backend.db import get_db
except:
    pass

@router.get("/without-sentiment")
def get_transcriptions_without_sentiment(limit: int = Query(10, ge=1, le=100)):
    """Lister les transcriptions sans analyse de sentiment"""
    try:
        db = get_db()
        transcriptions_col = db["radio_transcriptions"]
        
        # Transcriptions sans champ sentiment ou avec sentiment null
        query = {
            "$or": [
                {"sentiment": {"$exists": False}},
                {"sentiment": None},
                {"sentiment.polarity": {"$exists": False}}
            ]
        }
        
        transcriptions = list(
            transcriptions_col.find(query)
            .sort("captured_at", -1)
            .limit(limit)
        )
        
        for t in transcriptions:
            t["_id"] = str(t["_id"])
        
        return {
            "success": True,
            "transcriptions": transcriptions,
            "total_found": len(transcriptions)
        }
        
    except Exception as e:
        logger.error(f"Erreur transcriptions sans sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze-batch-sentiment")
def analyze_transcriptions_batch_sentiment(
    batch_size: int = Query(50, ge=1, le=100),
    max_transcriptions: int = Query(500, ge=1, le=2000),
    dry_run: bool = Query(False)
):
    """Analyser le sentiment d'un lot de transcriptions en mode économique"""
    try:
        db = get_db()
        transcriptions_col = db["radio_transcriptions"]
        
        # Initialiser l'analyseur local économique
        if 'sentiment_analyzer' not in globals():
            global sentiment_analyzer
            sentiment_analyzer = SentimentAnalyzer()
        
        # Récupérer les transcriptions sans sentiment
        query = {
            "$or": [
                {"sentiment": {"$exists": False}},
                {"sentiment": None}
            ],
            "transcription_text": {"$exists": True, "$ne": "", "$ne": None}
        }
        
        transcriptions = list(
            transcriptions_col.find(query)
            .sort("captured_at", -1)
            .limit(max_transcriptions)
        )
        
        if dry_run:
            return {
                "success": True,
                "message": "Analyse batch économique terminée (mode test)",
                "data": {
                    "total_analyzed": len(transcriptions),
                    "total_saved": 0,
                    "processing_time_seconds": 0.1,
                    "average_time_per_transcription_ms": 0.1,
                    "estimated_cost": 0.0,
                    "estimated_savings": len(transcriptions) * 0.01,
                    "errors_count": 0,
                    "errors": [],
                    "dry_run": True,
                    "economic_info": {
                        "method": "local_batch_economic",
                        "total_cost": 0.0,
                        "cost_per_transcription": 0.0,
                        "savings_vs_gpt": f"{len(transcriptions) * 0.01:.2f}€"
                    }
                }
            }
        
        start_time = datetime.now()
        processed = 0
        saved = 0
        errors = []
        
        # Traiter par lots
        for i in range(0, len(transcriptions), batch_size):
            batch = transcriptions[i:i + batch_size]
            logger.info(f"📊 Traitement lot {i//batch_size + 1}: {len(batch)} transcriptions")
            
            batch_updates = []
            
            for transcription in batch:
                try:
                    # Analyser le texte de la transcription
                    text = transcription.get("transcription_text", "")
                    if not text or len(text.strip()) < 10:
                        continue
                    
                    # Utiliser l'analyseur local économique
                    start_analysis = datetime.now()
                    sentiment_result = sentiment_analyzer.analyze_text_sentiment(text)
                    analysis_time = (datetime.now() - start_analysis).total_seconds() * 1000
                    
                    if sentiment_result:
                        # Ajouter les infos économiques
                        sentiment_result["economic_info"] = {
                            "method": "local_ultra_fast",
                            "cost": 0.0,
                            "processing_time_ms": round(analysis_time, 2),
                            "estimated_savings": 0.01,
                            "mode": "economic"
                        }
                        
                        # Préparer la mise à jour
                        batch_updates.append(
                            UpdateOne(
                                {"_id": transcription["_id"]},
                                {
                                    "$set": {
                                        "sentiment": sentiment_result,
                                        "sentiment_analyzed_at": datetime.now(),
                                        "sentiment_analysis_method": "local_economic"
                                    }
                                }
                            )
                        )
                        
                        processed += 1
                        saved += 1
                    
                except Exception as e:
                    error_msg = f"Erreur transcription {transcription.get('id', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            # Sauvegarder le lot
            if batch_updates:
                try:
                    result = transcriptions_col.bulk_write(batch_updates)
                    logger.info(f"💰 {processed} analysés | Temps moyen: {analysis_time:.1f}ms | Économies: {processed * 0.01:.2f}€")
                except Exception as e:
                    logger.error(f"Erreur sauvegarde lot: {e}")
                    errors.append(f"Erreur sauvegarde lot: {str(e)}")
        
        total_time = (datetime.now() - start_time).total_seconds()
        avg_time = (total_time * 1000 / processed) if processed > 0 else 0
        
        logger.info(f"💰 Analyse batch terminée: {processed} transcriptions en {total_time:.2f}s")
        logger.info(f"💰 Économies réalisées: {processed * 0.01:.2f}€")
        
        return {
            "success": True,
            "message": "Analyse batch économique terminée",
            "data": {
                "total_analyzed": processed,
                "total_saved": saved,
                "processing_time_seconds": round(total_time, 2),
                "average_time_per_transcription_ms": round(avg_time, 2),
                "estimated_cost": 0.0,
                "estimated_savings": round(processed * 0.01, 2),
                "errors_count": len(errors),
                "errors": errors[:10],  # Limiter à 10 erreurs
                "dry_run": False,
                "economic_info": {
                    "method": "local_batch_economic",
                    "total_cost": 0.0,
                    "cost_per_transcription": 0.0,
                    "savings_vs_gpt": f"{processed * 0.01:.2f}€"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur analyse batch transcriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment-stats")
def get_transcriptions_sentiment_stats():
    """Statistiques du sentiment des transcriptions"""
    try:
        db = get_db()
        transcriptions_col = db["radio_transcriptions"]
        
        # Stats générales
        total_transcriptions = transcriptions_col.count_documents({})
        with_sentiment = transcriptions_col.count_documents({"sentiment.polarity": {"$exists": True}})
        without_sentiment = total_transcriptions - with_sentiment
        
        # Distribution des sentiments
        pipeline = [
            {"$match": {"sentiment.polarity": {"$exists": True}}},
            {"$group": {
                "_id": "$sentiment.polarity",
                "count": {"$sum": 1},
                "avg_score": {"$avg": "$sentiment.score"}
            }}
        ]
        
        sentiment_distribution = {}
        for result in transcriptions_col.aggregate(pipeline):
            polarity = result["_id"]
            sentiment_distribution[polarity] = {
                "count": result["count"],
                "percentage": round((result["count"] / with_sentiment) * 100, 1) if with_sentiment > 0 else 0,
                "avg_score": round(result["avg_score"], 3) if result["avg_score"] else 0
            }
        
        # Stats par section/station radio
        pipeline_by_section = [
            {"$match": {"sentiment.polarity": {"$exists": True}}},
            {"$group": {
                "_id": {"section": "$section", "polarity": "$sentiment.polarity"},
                "count": {"$sum": 1}
            }}
        ]
        
        by_section = {}
        for result in transcriptions_col.aggregate(pipeline_by_section):
            section = result["_id"]["section"] or "unknown"
            polarity = result["_id"]["polarity"]
            
            if section not in by_section:
                by_section[section] = {"positive": 0, "negative": 0, "neutral": 0}
            
            by_section[section][polarity] = result["count"]
        
        return {
            "success": True,
            "data": {
                "total_transcriptions": total_transcriptions,
                "with_sentiment": with_sentiment,
                "without_sentiment": without_sentiment,
                "coverage_percentage": round((with_sentiment / total_transcriptions) * 100, 1) if total_transcriptions > 0 else 0,
                "sentiment_distribution": sentiment_distribution,
                "by_section": by_section,
                "analysis_methods": {
                    "local_economic": transcriptions_col.count_documents({"sentiment_analysis_method": "local_economic"}),
                    "gpt": transcriptions_col.count_documents({"sentiment_analysis_method": "gpt"}),
                    "other": transcriptions_col.count_documents({
                        "sentiment.polarity": {"$exists": True},
                        "sentiment_analysis_method": {"$nin": ["local_economic", "gpt"]}
                    })
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur stats sentiment transcriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment-rankings")
def get_transcriptions_sentiment_rankings(
    period_hours: int = Query(24, ge=1, le=168),  # 1h à 1 semaine
    limit: int = Query(10, ge=1, le=50)
):
    """Classement sentiment des transcriptions par section/thème"""
    try:
        db = get_db()
        transcriptions_col = db["radio_transcriptions"]
        
        # Période de recherche
        start_time = datetime.now() - timedelta(hours=period_hours)
        
        # Classement par section radio
        pipeline = [
            {
                "$match": {
                    "captured_at": {"$gte": start_time},
                    "sentiment.polarity": {"$exists": True},
                    "sentiment.score": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": "$section",
                    "total_transcriptions": {"$sum": 1},
                    "avg_sentiment_score": {"$avg": "$sentiment.score"},
                    "positive_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment.polarity", "positive"]}, 1, 0]}
                    },
                    "negative_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment.polarity", "negative"]}, 1, 0]}
                    },
                    "neutral_count": {
                        "$sum": {"$cond": [{"$eq": ["$sentiment.polarity", "neutral"]}, 1, 0]}
                    }
                }
            },
            {"$sort": {"avg_sentiment_score": -1}},
            {"$limit": limit}
        ]
        
        ranking = []
        for result in transcriptions_col.aggregate(pipeline):
            section = result["_id"] or "unknown"
            total = result["total_transcriptions"]
            
            ranking.append({
                "section": section,
                "total_transcriptions": total,
                "avg_sentiment_score": round(result["avg_sentiment_score"], 3),
                "sentiment_distribution": {
                    "positive": result["positive_count"],
                    "negative": result["negative_count"],
                    "neutral": result["neutral_count"]
                },
                "sentiment_percentages": {
                    "positive": round((result["positive_count"] / total) * 100, 1),
                    "negative": round((result["negative_count"] / total) * 100, 1),
                    "neutral": round((result["neutral_count"] / total) * 100, 1)
                }
            })
        
        # Trouver les plus positif/négatif
        most_positive = ranking[0] if ranking else None
        most_negative = ranking[-1] if ranking else None
        most_active = max(ranking, key=lambda x: x["total_transcriptions"]) if ranking else None
        
        return {
            "success": True,
            "ranking": {
                "period": {
                    "start": start_time.isoformat(),
                    "end": datetime.now().isoformat(),
                    "duration_hours": period_hours
                },
                "total_transcriptions": sum(r["total_transcriptions"] for r in ranking),
                "sections_analyzed": len(ranking),
                "ranking": ranking,
                "summary": {
                    "most_positive_section": most_positive["section"] if most_positive else None,
                    "most_negative_section": most_negative["section"] if most_negative else None,
                    "most_active_section": most_active["section"] if most_active else None
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur classement sentiment transcriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Ajouter ces imports dans server.py si pas déjà fait
from pymongo import UpdateOne