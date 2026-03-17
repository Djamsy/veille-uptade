# backend/advanced_classification_routes.py
"""
Routes API pour la classification avancée des transcriptions
"""

from fastapi import APIRouter, HTTPException, Query, Body
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

# Import du classificateur
try:
    from backend.advanced_transcription_classifier import classify_transcription_advanced
    from backend.db import get_db
except ImportError:
    from advanced_transcription_classifier import classify_transcription_advanced
    from db import get_db

router = APIRouter(prefix="/api/transcriptions/advanced", tags=["advanced-classification"])
logger = logging.getLogger("advanced_classification")

@router.post("/classify")
def classify_single_transcription(
    text: str = Body(..., description="Texte de la transcription à analyser"),
    metadata: Optional[Dict] = Body(default=None, description="Métadonnées optionnelles")
):
    """
    Classification avancée d'une transcription individuelle
    """
    if not text or len(text.strip()) < 10:
        raise HTTPException(status_code=400, detail="Texte insuffisant pour analyse")
    
    try:
        result = classify_transcription_advanced(text, metadata)
        return {"success": True, "classification": result}
    except Exception as e:
        logger.error(f"Erreur classification: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur classification: {str(e)}")

@router.post("/classify-batch")
def classify_transcriptions_batch(
    limit: int = Query(10, ge=1, le=50, description="Nombre de transcriptions à traiter"),
    date_filter: Optional[str] = Query(None, description="Date spécifique (YYYY-MM-DD)"),
    only_unclassified: bool = Query(True, description="Seulement les non-classifiées")
):
    """
    Classification avancée en lot des transcriptions
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        # Construction de la requête
        query = {}
        if date_filter:
            query["date"] = date_filter
        
        if only_unclassified:
            query["advanced_classification"] = {"$exists": False}
        
        # Récupération des transcriptions
        transcriptions = list(
            transcriptions_col.find(query)
            .sort("captured_at", -1)
            .limit(limit)
        )
        
        if not transcriptions:
            return {
                "success": True,
                "message": "Aucune transcription à classifier",
                "classified": 0,
                "results": []
            }
        
        results = []
        classified_count = 0
        
        for transcript in transcriptions:
            try:
                text = transcript.get("transcription_text", "")
                if not text or len(text.strip()) < 50:
                    continue
                
                # Classification avancée
                classification = classify_transcription_advanced(text, {
                    "stream_name": transcript.get("stream_name"),
                    "section": transcript.get("section"),
                    "date": transcript.get("date"),
                    "captured_at": transcript.get("captured_at")
                })
                
                # Mise à jour en base
                transcriptions_col.update_one(
                    {"_id": transcript["_id"]},
                    {
                        "$set": {
                            "advanced_classification": classification,
                            "classified_at": datetime.now().isoformat()
                        }
                    }
                )
                
                results.append({
                    "id": str(transcript["_id"]),
                    "transcript_id": transcript.get("id"),
                    "section": transcript.get("section"),
                    "is_affair": classification["classification"]["is_affair"],
                    "affair_type": classification["classification"]["affair_type"],
                    "gravity_score": classification["classification"]["gravity_score"],
                    "institutional_risk": classification["classification"]["institutional_risk"]
                })
                
                classified_count += 1
                
            except Exception as e:
                logger.error(f"Erreur classification transcription {transcript.get('id')}: {e}")
                continue
        
        return {
            "success": True,
            "message": f"{classified_count} transcriptions classifiées avec succès",
            "classified": classified_count,
            "total_processed": len(transcriptions),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Erreur classification batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/affairs")
def get_detected_affairs(
    days: int = Query(30, ge=1, le=365, description="Période en jours"),
    min_gravity: float = Query(0.5, ge=0.0, le=1.0, description="Score de gravité minimum"),
    risk_levels: List[str] = Query(default=["élevé", "critique"], description="Niveaux de risque")
):
    """
    Récupérer les affaires détectées selon les critères
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        # Période
        start_date = datetime.now() - timedelta(days=days)
        
        # Construction de la requête
        query = {
            "captured_at": {"$gte": start_date.isoformat()},
            "advanced_classification.classification.is_affair": True,
            "advanced_classification.classification.gravity_score": {"$gte": min_gravity}
        }
        
        if risk_levels:
            query["advanced_classification.classification.institutional_risk"] = {"$in": risk_levels}
        
        # Récupération et tri par gravité décroissante
        affairs = list(
            transcriptions_col.find(query, {
                "id": 1,
                "section": 1,
                "stream_name": 1,
                "date": 1,
                "captured_at": 1,
                "transcription_text": 1,
                "advanced_classification": 1
            }).sort("advanced_classification.classification.gravity_score", -1)
        )
        
        # Formatage des résultats
        formatted_affairs = []
        for affair in affairs:
            classification = affair.get("advanced_classification", {}).get("classification", {})
            analysis = affair.get("advanced_classification", {}).get("analysis", {})
            
            formatted_affairs.append({
                "transcript_id": affair.get("id"),
                "section": affair.get("section"),
                "stream_name": affair.get("stream_name"),
                "date": affair.get("date"),
                "captured_at": affair.get("captured_at"),
                "affair_type": classification.get("affair_type"),
                "gravity_score": classification.get("gravity_score"),
                "media_noise_level": classification.get("media_noise_level"),
                "virality_potential": classification.get("virality_potential"),
                "institutional_risk": classification.get("institutional_risk"),
                "key_actors": analysis.get("key_actors", []),
                "predicted_evolution": analysis.get("predicted_evolution"),
                "confidence": analysis.get("confidence"),
                "text_preview": (affair.get("transcription_text", "")[:200] + "..."),
            })
        
        return {
            "success": True,
            "period_days": days,
            "total_affairs": len(formatted_affairs),
            "criteria": {
                "min_gravity": min_gravity,
                "risk_levels": risk_levels
            },
            "affairs": formatted_affairs
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération affaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard")
def classification_dashboard(
    period_days: int = Query(7, ge=1, le=90, description="Période d'analyse")
):
    """
    Dashboard de classification avec métriques et tendances
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        start_date = datetime.now() - timedelta(days=period_days)
        
        # Statistiques générales
        total_transcriptions = transcriptions_col.count_documents({
            "captured_at": {"$gte": start_date.isoformat()}
        })
        
        classified_transcriptions = transcriptions_col.count_documents({
            "captured_at": {"$gte": start_date.isoformat()},
            "advanced_classification": {"$exists": True}
        })
        
        affairs_count = transcriptions_col.count_documents({
            "captured_at": {"$gte": start_date.isoformat()},
            "advanced_classification.classification.is_affair": True
        })
        
        # Distribution par type d'affaire
        pipeline_affairs = [
            {
                "$match": {
                    "captured_at": {"$gte": start_date.isoformat()},
                    "advanced_classification.classification.is_affair": True
                }
            },
            {
                "$group": {
                    "_id": "$advanced_classification.classification.affair_type",
                    "count": {"$sum": 1},
                    "avg_gravity": {"$avg": "$advanced_classification.classification.gravity_score"}
                }
            }
        ]
        
        affair_types = {
            result["_id"]: {
                "count": result["count"],
                "avg_gravity": round(result["avg_gravity"], 3)
            }
            for result in transcriptions_col.aggregate(pipeline_affairs)
        }
        
        # Distribution par niveau de risque institutionnel
        pipeline_risks = [
            {
                "$match": {
                    "captured_at": {"$gte": start_date.isoformat()},
                    "advanced_classification": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": "$advanced_classification.classification.institutional_risk",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        risk_distribution = {
            result["_id"]: result["count"]
            for result in transcriptions_col.aggregate(pipeline_risks)
        }
        
        # Top 5 des affaires les plus graves
        top_affairs = list(
            transcriptions_col.find({
                "captured_at": {"$gte": start_date.isoformat()},
                "advanced_classification.classification.is_affair": True
            }, {
                "section": 1,
                "date": 1,
                "advanced_classification.classification.affair_type": 1,
                "advanced_classification.classification.gravity_score": 1,
                "advanced_classification.analysis.key_actors": 1
            }).sort("advanced_classification.classification.gravity_score", -1).limit(5)
        )
        
        return {
            "success": True,
            "dashboard": {
                "period": {
                    "days": period_days,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": datetime.now().strftime("%Y-%m-%d")
                },
                "metrics": {
                    "total_transcriptions": total_transcriptions,
                    "classified_transcriptions": classified_transcriptions,
                    "classification_rate": round(classified_transcriptions / max(total_transcriptions, 1) * 100, 1),
                    "affairs_detected": affairs_count,
                    "affair_rate": round(affairs_count / max(classified_transcriptions, 1) * 100, 1)
                },
                "distributions": {
                    "affair_types": affair_types,
                    "risk_levels": risk_distribution
                },
                "top_affairs": [
                    {
                        "section": affair.get("section"),
                        "date": affair.get("date"),
                        "affair_type": affair.get("advanced_classification", {}).get("classification", {}).get("affair_type"),
                        "gravity_score": affair.get("advanced_classification", {}).get("classification", {}).get("gravity_score"),
                        "key_actors": affair.get("advanced_classification", {}).get("analysis", {}).get("key_actors", [])[:2]
                    }
                    for affair in top_affairs
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur dashboard classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trends")
def classification_trends(
    days: int = Query(30, ge=7, le=365, description="Période d'analyse"),
    group_by: str = Query("day", description="Groupement temporel: day, week")
):
    """
    Tendances de classification dans le temps
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Format de groupement selon la période
        date_format = "%Y-%m-%d" if group_by == "day" else "%Y-%W"
        
        # Pipeline d'agrégation pour les tendances
        pipeline = [
            {
                "$match": {
                    "captured_at": {"$gte": start_date.isoformat()},
                    "advanced_classification": {"$exists": True}
                }
            },
            {
                "$addFields": {
                    "date_group": {
                        "$dateToString": {
                            "format": date_format,
                            "date": {"$dateFromString": {"dateString": "$captured_at"}}
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": "$date_group",
                    "total_transcriptions": {"$sum": 1},
                    "affairs_count": {
                        "$sum": {
                            "$cond": [
                                "$advanced_classification.classification.is_affair",
                                1,
                                0
                            ]
                        }
                    },
                    "avg_gravity": {
                        "$avg": "$advanced_classification.classification.gravity_score"
                    },
                    "avg_virality": {
                        "$avg": "$advanced_classification.classification.virality_potential"
                    }
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        trends = list(transcriptions_col.aggregate(pipeline))
        
        # Formatage des résultats
        formatted_trends = []
        for trend in trends:
            formatted_trends.append({
                "date": trend["_id"],
                "total_transcriptions": trend["total_transcriptions"],
                "affairs_count": trend["affairs_count"],
                "affair_rate": round(trend["affairs_count"] / max(trend["total_transcriptions"], 1) * 100, 1),
                "avg_gravity_score": round(trend["avg_gravity"], 3),
                "avg_virality_potential": round(trend["avg_virality"], 3)
            })
        
        return {
            "success": True,
            "trends": {
                "period_days": days,
                "group_by": group_by,
                "data": formatted_trends
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur tendances classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))