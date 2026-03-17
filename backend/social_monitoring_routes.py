# backend/social_monitoring_routes.py
"""
Routes FastAPI pour le système de monitoring social intelligent
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["social-monitoring"])

# Imports des services
try:
    from backend.intelligent_social_monitor import intelligent_social_monitor
    from backend.sentiment_metrics_dashboard import sentiment_dashboard
except ImportError:
    try:
        from intelligent_social_monitor import intelligent_social_monitor
        from sentiment_metrics_dashboard import sentiment_dashboard
    except ImportError:
        logger.error("Impossible d'importer les services de monitoring social")
        intelligent_social_monitor = None
        sentiment_dashboard = None

# Modèles Pydantic
class AffairThresholdCheck(BaseModel):
    affair_id: str

class SentimentAnalysisRequest(BaseModel):
    affair_id: str
    days_back: Optional[int] = 7

class MonitoringStatsResponse(BaseModel):
    success: bool
    data: Dict[str, Any]

# ========== ENDPOINTS MONITORING ==========

@router.post("/monitor/run", response_model=MonitoringStatsResponse)
async def run_intelligent_monitoring():
    """Lance un cycle de monitoring intelligent complet"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        result = intelligent_social_monitor.monitor_affairs_intelligent()
        
        return MonitoringStatsResponse(
            success=True,
            data=result
        )
        
    except Exception as e:
        logger.error(f"Erreur monitoring social: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du monitoring social: {str(e)}"
        )

@router.get("/monitor/stats", response_model=MonitoringStatsResponse)
async def get_monitoring_stats():
    """Récupère les statistiques du monitoring intelligent"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        stats = intelligent_social_monitor.get_monitoring_stats()
        
        return MonitoringStatsResponse(
            success=True,
            data=stats
        )
        
    except Exception as e:
        logger.error(f"Erreur récupération stats monitoring: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur stats monitoring: {str(e)}"
        )

@router.post("/monitor/check-thresholds", response_model=MonitoringStatsResponse)
async def check_affair_thresholds(request: AffairThresholdCheck):
    """Vérifie les seuils d'une affaire spécifique"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        # Vérifier conditions IA
        affair_data = intelligent_social_monitor.affaires_collection.find_one({
            "affaire_id": request.affair_id
        })
        
        if not affair_data:
            raise HTTPException(
                status_code=404,
                detail=f"Affaire {request.affair_id} non trouvée"
            )
        
        threshold_check = intelligent_social_monitor.check_affair_thresholds(request.affair_id)
        ai_conditions = intelligent_social_monitor.check_ai_triggered_conditions(affair_data)
        
        return MonitoringStatsResponse(
            success=True,
            data={
                "affair_id": request.affair_id,
                "threshold_check": threshold_check,
                "ai_conditions": ai_conditions,
                "affair_info": {
                    "primary_entity": affair_data.get("primary_entity"),
                    "importance_score": affair_data.get("importance_score"),
                    "mistral_called": affair_data.get("mistral_called"),
                    "theme": affair_data.get("theme")
                }
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur vérification seuils: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur vérification seuils: {str(e)}"
        )

@router.post("/monitor/trigger-scan/{affair_id}")
async def trigger_manual_scan(
    affair_id: str,
    scan_type: str = Query("ai_triggered", description="Type de scan: basic_scan, ai_triggered_scan, deep_crisis_scan")
):
    """Déclenche manuellement un scan pour une affaire"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        # Récupérer données affaire
        affair_data = intelligent_social_monitor.affaires_collection.find_one({
            "affaire_id": affair_id
        })
        
        if not affair_data:
            raise HTTPException(
                status_code=404,
                detail=f"Affaire {affair_id} non trouvée"
            )
        
        # Exécuter le scan approprié
        if scan_type == "basic_scan":
            result = intelligent_social_monitor.execute_basic_scan(affair_data)
        elif scan_type == "ai_triggered_scan":
            result = intelligent_social_monitor.execute_ai_triggered_scan(affair_data)
        elif scan_type == "deep_crisis_scan":
            result = intelligent_social_monitor.execute_deep_crisis_scan(affair_data)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Type de scan invalide: {scan_type}"
            )
        
        return MonitoringStatsResponse(
            success=True,
            data={
                "scan_triggered": True,
                "scan_type": scan_type,
                "affair_id": affair_id,
                "result": result
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur déclenchement scan manuel: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur scan manuel: {str(e)}"
        )

# ========== ENDPOINTS SENTIMENT ANALYSIS ==========

@router.post("/sentiment/analyze", response_model=MonitoringStatsResponse)
async def analyze_affair_sentiment(request: SentimentAnalysisRequest):
    """Lance l'analyse de sentiment pour une affaire"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        # Récupérer données affaire
        affair_data = intelligent_social_monitor.affaires_collection.find_one({
            "affaire_id": request.affair_id
        })
        
        if not affair_data:
            raise HTTPException(
                status_code=404,
                detail=f"Affaire {request.affair_id} non trouvée"
            )
        
        # Générer dashboard sentiment
        dashboard = intelligent_social_monitor.generate_sentiment_dashboard(
            request.affair_id, 
            request.days_back
        )
        
        return MonitoringStatsResponse(
            success=True,
            data={
                "affair_id": request.affair_id,
                "sentiment_dashboard": dashboard
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur analyse sentiment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur analyse sentiment: {str(e)}"
        )

@router.get("/sentiment/dashboard/{affair_id}")
async def get_sentiment_dashboard(
    affair_id: str,
    days_back: int = Query(7, description="Nombre de jours d'historique")
):
    """Récupère le dashboard de sentiment pour une affaire"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        dashboard = sentiment_dashboard.generate_sentiment_report(affair_id, days_back)
        
        return MonitoringStatsResponse(
            success=True,
            data=dashboard
        )
        
    except Exception as e:
        logger.error(f"Erreur dashboard sentiment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur dashboard sentiment: {str(e)}"
        )

# ========== ENDPOINTS VISUALISATIONS ==========

@router.get("/charts/sentiment/{affair_id}")
async def generate_sentiment_chart(
    affair_id: str,
    days_back: int = Query(7, description="Nombre de jours d'historique")
):
    """Génère un graphique de sentiment pour une affaire"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        chart_result = sentiment_dashboard.generate_affair_sentiment_chart(affair_id, days_back)
        
        return MonitoringStatsResponse(
            success=True,
            data=chart_result
        )
        
    except Exception as e:
        logger.error(f"Erreur génération graphique sentiment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur graphique sentiment: {str(e)}"
        )

@router.get("/charts/crisis/{affair_id}")
async def generate_crisis_chart(affair_id: str):
    """Génère un graphique des indicateurs de crise"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        chart_result = sentiment_dashboard.generate_crisis_indicators_chart(affair_id)
        
        return MonitoringStatsResponse(
            success=True,
            data=chart_result
        )
        
    except Exception as e:
        logger.error(f"Erreur génération graphique crise: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur graphique crise: {str(e)}"
        )

@router.get("/charts/comparative")
async def generate_comparative_dashboard(
    days_back: int = Query(7, description="Nombre de jours d'historique")
):
    """Génère un dashboard comparatif de toutes les affaires"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        dashboard_result = sentiment_dashboard.generate_comparative_dashboard(days_back)
        
        return MonitoringStatsResponse(
            success=True,
            data=dashboard_result
        )
        
    except Exception as e:
        logger.error(f"Erreur génération dashboard comparatif: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur dashboard comparatif: {str(e)}"
        )

@router.get("/charts/heatmap/{affair_id}")
async def generate_activity_heatmap(
    affair_id: str,
    days_back: int = Query(7, description="Nombre de jours d'historique")
):
    """Génère une heatmap d'activité pour une affaire"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        heatmap_result = sentiment_dashboard.generate_hourly_heatmap(affair_id, days_back)
        
        return MonitoringStatsResponse(
            success=True,
            data=heatmap_result
        )
        
    except Exception as e:
        logger.error(f"Erreur génération heatmap: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur heatmap: {str(e)}"
        )

# ========== ENDPOINTS ADMINISTRATION ==========

@router.get("/affairs/monitored")
async def get_monitored_affairs(
    days_back: int = Query(7, description="Nombre de jours d'historique")
):
    """Liste les affaires actuellement surveillées"""
    
    if not intelligent_social_monitor:
        raise HTTPException(
            status_code=503,
            detail="Service de monitoring social indisponible"
        )
    
    try:
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        # Récupérer affaires avec analyse IA récente
        monitored_affairs = list(
            intelligent_social_monitor.affaires_collection.find({
                "last_updated": {"$gte": since_date},
                "mistral_called": True
            }).sort("importance_score", -1)
        )
        
        # Enrichir avec informations de seuils
        enriched_affairs = []
        for affair in monitored_affairs:
            threshold_check = intelligent_social_monitor.check_affair_thresholds(affair["affaire_id"])
            ai_conditions = intelligent_social_monitor.check_ai_triggered_conditions(affair)
            
            enriched_affairs.append({
                "affair_id": affair["affaire_id"],
                "primary_entity": affair.get("primary_entity"),
                "theme": affair.get("theme"),
                "importance_score": affair.get("importance_score"),
                "last_updated": affair.get("last_updated"),
                "threshold_status": threshold_check["action"],
                "ai_trigger_eligible": ai_conditions["should_trigger"],
                "monitoring_level": threshold_check["action"]
            })
        
        return MonitoringStatsResponse(
            success=True,
            data={
                "total_monitored": len(enriched_affairs),
                "affairs": enriched_affairs,
                "period": f"{days_back} derniers jours"
            }
        )
        
    except Exception as e:
        logger.error(f"Erreur récupération affaires surveillées: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur affaires surveillées: {str(e)}"
        )

@router.delete("/charts/cleanup")
async def cleanup_old_charts(
    days_to_keep: int = Query(7, description="Nombre de jours de graphiques à conserver")
):
    """Nettoie les anciens graphiques"""
    
    if not sentiment_dashboard:
        raise HTTPException(
            status_code=503,
            detail="Service de dashboard sentiment indisponible"
        )
    
    try:
        sentiment_dashboard.cleanup_old_charts(days_to_keep)
        
        return MonitoringStatsResponse(
            success=True,
            data={
                "cleanup_completed": True,
                "days_kept": days_to_keep
            }
        )
        
    except Exception as e:
        logger.error(f"Erreur nettoyage graphiques: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur nettoyage: {str(e)}"
        )

# ========== ENDPOINTS HEALTH CHECK ==========

@router.get("/health")
async def health_check():
    """Vérifie l'état des services de monitoring social"""
    
    return {
        "success": True,
        "services": {
            "intelligent_social_monitor": intelligent_social_monitor is not None,
            "sentiment_dashboard": sentiment_dashboard is not None
        },
        "status": "operational" if (intelligent_social_monitor and sentiment_dashboard) else "degraded",
        "timestamp": datetime.now().isoformat()
    }