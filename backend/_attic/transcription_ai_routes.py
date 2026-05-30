# backend/transcription_ai_routes.py
"""
Routes API pour la classification avancée des transcriptions avec Mistral
"""

from fastapi import APIRouter, HTTPException, Query, Body
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

# Imports du service IA et DB
try:
    from backend._attic.ai_service import ai_service
    from backend.db import get_db
except ImportError:
    from ai_service import ai_service
    from db import get_db

router = APIRouter(prefix="/api/ai", tags=["ai-transcription"])
logger = logging.getLogger("transcription_ai_routes")

@router.post("/classify-transcription")
def classify_single_transcription(
    text: str = Body(..., description="Texte de la transcription à analyser"),
    metadata: Optional[Dict] = Body(default=None, description="Métadonnées optionnelles")
):
    """
    Classification avancée d'une transcription individuelle avec Mistral
    
    Détecte automatiquement :
    - Type d'affaire (justice, politique, service public, etc.)
    - Score de gravité (0.0 à 1.0) 
    - Niveau de bruit médiatique attendu
    - Potentiel de viralité
    - Risque institutionnel
    - Acteurs clés impliqués
    """
    if not text or len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Texte insuffisant pour analyse (minimum 20 caractères)")
    
    try:
        result = ai_service.classify_transcription_advanced(text, metadata or {})
        return {
            "success": True, 
            "classification": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erreur classification transcription: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur classification: {str(e)}")

@router.post("/classify-transcriptions-batch")
def classify_transcriptions_batch(
    limit: int = Query(10, ge=1, le=50, description="Nombre max de transcriptions à traiter"),
    date_filter: Optional[str] = Query(None, description="Date spécifique (YYYY-MM-DD)"),
    only_unclassified: bool = Query(True, description="Seulement les non-classifiées")
):
    """
    Classification en lot des transcriptions existantes
    
    Traite plusieurs transcriptions MongoDB et sauvegarde les résultats.
    Utile pour rattrapage ou traitement initial.
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
                "message": "Aucune transcription à classifier avec ces critères",
                "processed": 0,
                "results": []
            }
        
        logger.info(f"Classification en lot démarrée : {len(transcriptions)} transcriptions")
        
        # Classification via le service IA
        results = ai_service.classify_transcription_batch(transcriptions, limit)
        
        # Sauvegarde des résultats en base
        classified_count = 0
        for result in results:
            if "error" not in result and result.get("classification"):
                try:
                    transcriptions_col.update_one(
                        {"id": result["transcript_id"]},
                        {
                            "$set": {
                                "advanced_classification": result["classification"],
                                "classified_at": datetime.now().isoformat(),
                                "classification_version": "2.0_mistral"
                            }
                        }
                    )
                    classified_count += 1
                except Exception as e:
                    logger.error(f"Erreur sauvegarde classification {result['transcript_id']}: {e}")
        
        return {
            "success": True,
            "message": f"{classified_count} transcriptions classifiées avec succès",
            "processed": len(transcriptions),
            "classified": classified_count,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur classification batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/affairs-detected")
def get_detected_affairs(
    days: int = Query(30, ge=1, le=365, description="Période en jours"),
    min_gravity: float = Query(0.5, ge=0.0, le=1.0, description="Score de gravité minimum"),
    risk_levels: List[str] = Query(default=["élevé", "critique"], description="Niveaux de risque")
):
    """
    Récupère les affaires détectées selon les critères
    
    Filtre par :
    - Période temporelle
    - Score de gravité minimum
    - Niveaux de risque institutionnel
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        # Période
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Construction de la requête
        query = {
            "date": {"$gte": start_date},
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
                "text_preview": (affair.get("transcription_text", "")[:200] + "...") if affair.get("transcription_text") else "",
            })
        
        return {
            "success": True,
            "period_days": days,
            "total_affairs": len(formatted_affairs),
            "criteria": {
                "min_gravity": min_gravity,
                "risk_levels": risk_levels,
                "start_date": start_date
            },
            "affairs": formatted_affairs,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération affaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/classification-dashboard")
def classification_dashboard(
    period_days: int = Query(7, ge=1, le=90, description="Période d'analyse en jours")
):
    """
    Dashboard de classification avec métriques et tendances
    
    Retourne :
    - Statistiques générales de classification
    - Distribution par type d'affaire
    - Distribution par niveau de risque
    - Top 5 des affaires les plus graves
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        start_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")
        
        # Statistiques générales
        total_transcriptions = transcriptions_col.count_documents({
            "date": {"$gte": start_date}
        })
        
        classified_transcriptions = transcriptions_col.count_documents({
            "date": {"$gte": start_date},
            "advanced_classification": {"$exists": True}
        })
        
        affairs_count = transcriptions_col.count_documents({
            "date": {"$gte": start_date},
            "advanced_classification.classification.is_affair": True
        })
        
        # Distribution par type d'affaire
        pipeline_affairs = [
            {
                "$match": {
                    "date": {"$gte": start_date},
                    "advanced_classification.classification.is_affair": True
                }
            },
            {
                "$group": {
                    "_id": "$advanced_classification.classification.affair_type",
                    "count": {"$sum": 1},
                    "avg_gravity": {"$avg": "$advanced_classification.classification.gravity_score"},
                    "max_gravity": {"$max": "$advanced_classification.classification.gravity_score"}
                }
            }
        ]
        
        affair_types = {}
        for result in transcriptions_col.aggregate(pipeline_affairs):
            affair_types[result["_id"]] = {
                "count": result["count"],
                "avg_gravity": round(result["avg_gravity"], 3),
                "max_gravity": round(result["max_gravity"], 3)
            }
        
        # Distribution par niveau de risque institutionnel
        pipeline_risks = [
            {
                "$match": {
                    "date": {"$gte": start_date},
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
        
        risk_distribution = {}
        for result in transcriptions_col.aggregate(pipeline_risks):
            risk_distribution[result["_id"]] = result["count"]
        
        # Top 5 des affaires les plus graves
        top_affairs = list(
            transcriptions_col.find({
                "date": {"$gte": start_date},
                "advanced_classification.classification.is_affair": True
            }, {
                "id": 1,
                "section": 1,
                "date": 1,
                "stream_name": 1,
                "advanced_classification.classification.affair_type": 1,
                "advanced_classification.classification.gravity_score": 1,
                "advanced_classification.classification.institutional_risk": 1,
                "advanced_classification.analysis.key_actors": 1,
                "transcription_text": 1
            }).sort("advanced_classification.classification.gravity_score", -1).limit(5)
        )
        
        # Métriques avancées
        avg_gravity_all = 0
        avg_virality_all = 0
        if classified_transcriptions > 0:
            gravity_pipeline = [
                {"$match": {"date": {"$gte": start_date}, "advanced_classification": {"$exists": True}}},
                {"$group": {
                    "_id": None,
                    "avg_gravity": {"$avg": "$advanced_classification.classification.gravity_score"},
                    "avg_virality": {"$avg": "$advanced_classification.classification.virality_potential"}
                }}
            ]
            
            avg_result = list(transcriptions_col.aggregate(gravity_pipeline))
            if avg_result:
                avg_gravity_all = round(avg_result[0]["avg_gravity"], 3)
                avg_virality_all = round(avg_result[0]["avg_virality"], 3)
        
        return {
            "success": True,
            "dashboard": {
                "period": {
                    "days": period_days,
                    "start_date": start_date,
                    "end_date": datetime.now().strftime("%Y-%m-%d")
                },
                "metrics": {
                    "total_transcriptions": total_transcriptions,
                    "classified_transcriptions": classified_transcriptions,
                    "classification_rate": round(classified_transcriptions / max(total_transcriptions, 1) * 100, 1),
                    "affairs_detected": affairs_count,
                    "affair_rate": round(affairs_count / max(classified_transcriptions, 1) * 100, 1),
                    "avg_gravity_score": avg_gravity_all,
                    "avg_virality_potential": avg_virality_all
                },
                "distributions": {
                    "affair_types": affair_types,
                    "risk_levels": risk_distribution
                },
                "top_affairs": [
                    {
                        "transcript_id": affair.get("id"),
                        "section": affair.get("section"),
                        "stream_name": affair.get("stream_name"),
                        "date": affair.get("date"),
                        "affair_type": affair.get("advanced_classification", {}).get("classification", {}).get("affair_type"),
                        "gravity_score": affair.get("advanced_classification", {}).get("classification", {}).get("gravity_score"),
                        "institutional_risk": affair.get("advanced_classification", {}).get("classification", {}).get("institutional_risk"),
                        "key_actors": affair.get("advanced_classification", {}).get("analysis", {}).get("key_actors", [])[:2],
                        "text_preview": (affair.get("transcription_text", "")[:150] + "...") if affair.get("transcription_text") else ""
                    }
                    for affair in top_affairs
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur dashboard classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/classification-trends")
def classification_trends(
    days: int = Query(30, ge=7, le=365, description="Période d'analyse"),
    group_by: str = Query("day", description="Groupement temporel: day, week")
):
    """
    Tendances de classification dans le temps
    
    Analyse l'évolution temporelle des affaires détectées :
    - Nombre d'affaires par période
    - Score de gravité moyen
    - Potentiel de viralité moyen
    """
    try:
        db = get_db()
        transcriptions_col = db.radio_transcriptions
        
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Format de groupement selon la période
        if group_by == "day":
            date_format = "$date"
            date_group_field = "$date"
        elif group_by == "week":
            # Groupement par semaine (approximatif via date)
            date_format = "$date"
            date_group_field = "$date"
        else:
            date_format = "$date"
            date_group_field = "$date"
        
        # Pipeline d'agrégation pour les tendances
        pipeline = [
            {
                "$match": {
                    "date": {"$gte": start_date},
                    "advanced_classification": {"$exists": True}
                }
            },
            {
                "$group": {
                    "_id": date_group_field,
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
                    },
                    "max_gravity": {
                        "$max": "$advanced_classification.classification.gravity_score"
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
            total = trend["total_transcriptions"]
            affairs = trend["affairs_count"]
            
            formatted_trends.append({
                "date": trend["_id"],
                "total_transcriptions": total,
                "affairs_count": affairs,
                "affair_rate": round(affairs / max(total, 1) * 100, 1),
                "avg_gravity_score": round(trend["avg_gravity"], 3) if trend["avg_gravity"] else 0,
                "avg_virality_potential": round(trend["avg_virality"], 3) if trend["avg_virality"] else 0,
                "max_gravity_score": round(trend["max_gravity"], 3) if trend["max_gravity"] else 0
            })
        
        return {
            "success": True,
            "trends": {
                "period_days": days,
                "group_by": group_by,
                "start_date": start_date,
                "data": formatted_trends
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur tendances classification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai-status")
def get_ai_status():
    """
    Status du service IA et de la classification avancée
    
    Retourne l'état de tous les composants :
    - Connexion Ollama/Mistral
    - Base de données d'entités
    - Capacités de classification
    """
    try:
        status = ai_service.health_check()
        
        # Ajout d'infos spécifiques à la classification
        status.update({
            "classification_endpoints": {
                "single_classification": "/api/ai/classify-transcription",
                "batch_classification": "/api/ai/classify-transcriptions-batch",
                "affairs_detection": "/api/ai/affairs-detected",
                "dashboard": "/api/ai/classification-dashboard",
                "trends": "/api/ai/classification-trends"
            },
            "last_check": datetime.now().isoformat()
        })
        
        return {
            "success": True,
            "ai_service": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur status AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))