# backend/sentiment_routes.py
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any
import json
import hashlib

logger = logging.getLogger("sentiment_routes")
logger.setLevel(logging.INFO)
logger.info("📌 sentiment_routes module loaded")

# ✅ DÉFINIR LE ROUTER (c'était ça le problème !)
router = APIRouter()

# Essai d'import de l'analyseur local pour un score réel
try:
    from backend.sentiment_analysis_service import analyze_text_sentiment as local_analyze_sentiment
except Exception:
    try:
        from sentiment_analysis_service import analyze_text_sentiment as local_analyze_sentiment
    except Exception:
        local_analyze_sentiment = None

# Essai d'import du prédicteur de réaction population locale (si dispo)
try:
    from backend.sentiment_analysis_service import predict_population_reaction as local_predict_population_reaction
except Exception:
    try:
        from sentiment_analysis_service import predict_population_reaction as local_predict_population_reaction
    except Exception:
        local_predict_population_reaction = None

# Essai d'import du prédicteur GPT (comparaison historique)
try:
    from backend.gpt_sentiment_service import predict_population_reaction as gpt_predict_population_reaction
except Exception:
    try:
        from gpt_sentiment_service import predict_population_reaction as gpt_predict_population_reaction
    except Exception:
        gpt_predict_population_reaction = None

# ---------- Schemas ----------
class AnalyzePayload(BaseModel):
    text: str
    async_: bool = Field(False, alias="async")  # le front envoie "async"

class AnalyzeWithFrontendPayload(BaseModel):
    text: str
    frontend_snapshot: Optional[Dict[str, Any]] = None
    async_: bool = Field(False, alias="async")  # cohérent avec AnalyzePayload
    force: bool = False  # bypass cache si nécessaire

class PredictPayload(BaseModel):
    text: str
    context: Optional[Dict[str, Any]] = None
    frontend_snapshot: Optional[Dict[str, Any]] = None
    history_limit: int = 150  # nombre d'articles historiques à considérer (150 derniers)

# ---------- Petit heuristique pour /predict-reaction ----------
POS = {
    "bien","super","excellent","positif","gagne","succès","bon",
    "satisfait","favorable","bravo","fiers","fières"
}
NEG = {
    "mauvais","horrible","négatif","perdu","échec","scandale",
    "colère","triste","grave","crise","tendu","polémique"
}

def quick_predict(text: str) -> Dict[str, Any]:
    import re
    tokens = re.findall(r"\w+", (text or "").lower())
    pos = sum(t in POS for t in tokens)
    neg = sum(t in NEG for t in tokens)
    if pos > neg:
        overall, risk = "favorable", "low"
    elif neg > pos:
        overall, risk = "tendu", "high"
    else:
        overall, risk = "mitigé", "medium"
    conf = min(0.95, 0.55 + abs(pos - neg) / (pos + neg + 1))
    return {
        "overall_reaction": overall,
        "risk_level": risk,
        "likely_discussion_channels": ["Facebook", "X/Twitter", "Commentaires médias"],
        "confidence": round(conf, 2),
        "reasoning": "Heuristique simple (démo).",
        "data_sources": {"similar_articles": 0, "similar_social_posts": 0},
        "strategic_recommendations": [],
        "by_demographic": {}
    }

# Seuils d'alerte
ALERT_THRESHOLDS = {
    "critical": {"score": -0.50, "confidence": 0.55},
    "high":     {"score": -0.35, "confidence": 0.50},
    "medium":   {"score": -0.20, "confidence": 0.45},
}

def _assess_alert_level(score: float, confidence: float, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Évalue le niveau d'alerte basé sur le score de sentiment"""
    if score <= ALERT_THRESHOLDS["critical"]["score"] and confidence >= ALERT_THRESHOLDS["critical"]["confidence"]:
        return {
            "level": "critical",
            "message": "Sentiment très négatif détecté - Action immédiate recommandée",
            "actions": [
                "Activer cellule de crise (porte-parole désigné).",
                "Publier un message d'empathie + faits vérifiés dans l'heure.",
                "Programmer un point presse / Q&A modéré."
            ]
        }
    elif score <= ALERT_THRESHOLDS["high"]["score"] and confidence >= ALERT_THRESHOLDS["high"]["confidence"]:
        return {
            "level": "high",
            "message": "Sentiment négatif détecté - Surveillance renforcée",
            "actions": [
                "Répondre publiquement avec éléments factuels.",
                "Mobiliser relais (assos, partenaires) pour relayer la clarification.",
                "Préparer FAQ courte pour réseaux sociaux."
            ]
        }
    elif score <= ALERT_THRESHOLDS["medium"]["score"] and confidence >= ALERT_THRESHOLDS["medium"]["confidence"]:
        return {
            "level": "medium",
            "message": "Sentiment modérément négatif - Monitoring actif",
            "actions": [
                "Surveiller l'évolution des réactions.",
                "Préparer des éléments de réponse préventifs."
            ]
        }
    else:
        return {
            "level": "normal",
            "message": "Niveau de sentiment normal",
            "actions": []
        }

def _map_prediction_to_front(pred: Dict[str, Any]) -> Dict[str, Any]:
    """Mappe la sortie de quick_predict vers le schéma attendu par le front."""
    overall = pred.get("overall_reaction", "neutre")
    # Harmoniser les libellés FR si nécessaire
    if overall in {"favorable", "positif", "positive"}: 
        overall = "positive"
    if overall in {"tendu", "négatif", "negative"}: 
        overall = "négative"
    
    risk = pred.get("risk_level", "medium")
    conf = float(pred.get("confidence", 0))
    
    return {
        "population_reaction": {
            "overall_reaction": overall,
            "overall_score": pred.get("overall_score", 0),
            "polarization_risk": {"low": "faible", "medium": "modéré", "high": "élevé"}.get(risk, "modéré"),
            "by_demographic": pred.get("by_demographic", {}),
        },
        "confidence": conf,
        "data_sources": pred.get("data_sources", {"similar_articles": 0, "similar_social_posts": 0}),
        "strategic_recommendations": pred.get("strategic_recommendations", []),
    }

# ---------- Routes principales ----------

@router.post("/sentiment/analyze", tags=["sentiment"])
async def analyze_sentiment(payload: AnalyzePayload):
    """Analyse de sentiment simple"""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Texte requis")
    
    if local_analyze_sentiment:
        try:
            result = local_analyze_sentiment(text)
            return {"success": True, "sentiment": result}
        except Exception as e:
            logger.error(f"Erreur analyse sentiment: {e}")
    
    # Fallback simple
    return {
        "success": True,
        "sentiment": {
            "polarity": "neutral",
            "score": 0.0,
            "confidence": 0.5,
            "method": "fallback"
        }
    }

@router.post("/sentiment/predict-reaction", tags=["sentiment"])
async def predict_reaction(payload: PredictPayload):
    """Prédiction de réaction de la population"""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # Contexte fusionné
    ctx: Dict[str, Any] = {}
    if isinstance(payload.frontend_snapshot, dict):
        ctx.update(payload.frontend_snapshot)
    if isinstance(payload.context, dict):
        ctx.update(payload.context)
    ctx.setdefault("history_limit", int(payload.history_limit or 150))
    ctx.setdefault("history_scope", "recent_articles")

    # 1) Chemin privilégié: prédiction GPT basée sur comparaison à l'historique réduit
    if callable(gpt_predict_population_reaction):
        try:
            gpt_result = gpt_predict_population_reaction(text, context=ctx)
            if gpt_result and isinstance(gpt_result, dict):
                mapped = _map_prediction_to_front(gpt_result)
                mapped["alert"] = _assess_alert_level(
                    gpt_result.get("overall_score", 0), 
                    float(mapped.get("confidence", 0.5)), 
                    payload.frontend_snapshot
                )
                return {"success": True, "reactionPrediction": mapped, "prediction": gpt_result}
        except Exception as e:
            logger.warning(f"GPT predictor failed, fallback to local: {e}")

    # 2) Fallback: prédicteur local
    if callable(local_predict_population_reaction):
        try:
            local_result = local_predict_population_reaction(text, ctx)
            if local_result and isinstance(local_result, dict):
                mapped = _map_prediction_to_front(local_result)
                mapped["alert"] = _assess_alert_level(
                    local_result.get("overall_score", 0), 
                    float(mapped.get("confidence", 0.5)), 
                    payload.frontend_snapshot
                )
                return {"success": True, "reactionPrediction": mapped, "prediction": local_result}
        except Exception as e:
            logger.warning(f"Local predictor failed: {e}")

    # 3) Fallback ultime: heuristique simple
    base_pred = quick_predict(text)
    mapped = _map_prediction_to_front(base_pred)
    
    # Analyse de sentiment pour score
    score = 0.0
    if local_analyze_sentiment:
        try:
            sentiment_result = local_analyze_sentiment(text)
            score = sentiment_result.get("score", 0.0) if sentiment_result else 0.0
        except Exception:
            pass
    
    mapped["population_reaction"]["overall_score"] = round(score, 3)
    mapped["alert"] = _assess_alert_level(score, float(mapped.get("confidence", 0.5)), payload.frontend_snapshot)

    # Recommandations stratégiques
    recs = []
    if score <= -0.35:
        recs = [
            "Répondre vite avec un message d'empathie.",
            "Partager des faits vérifiés et des sources fiables.",
            "Proposer une action corrective concrète.",
        ]
    elif score >= 0.35:
        recs = [
            "Amplifier les retours positifs sur les réseaux.",
            "Remercier publiquement les soutiens.",
            "Transformer en témoignages / cas d'usage.",
        ]
    mapped["strategic_recommendations"] = recs

    return {"success": True, "reactionPrediction": mapped, "prediction": base_pred}

@router.post("/sentiment/assess-alert", tags=["sentiment"])
async def assess_alert(payload: Dict[str, Any]):
    """Évaluation du niveau d'alerte"""
    text = (payload.get("text") or "").strip()
    snap = payload.get("frontend_snapshot")

    score = float(payload.get("score") or 0.0)
    conf = float(payload.get("confidence") or 0.5)

    if not payload.get("score") and text:
        try:
            if callable(local_analyze_sentiment):
                local_res = local_analyze_sentiment(text) or {}
                score = float(local_res.get("score", 0.0) or 0.0)
        except Exception:
            pass

    alert = _assess_alert_level(score, conf, snap)
    return {"success": True, "alert": alert, "inputs": {"score": score, "confidence": conf}}

# ---------- Routes de compatibilité ----------

@router.get("/sentiment/status", tags=["sentiment"])
async def sentiment_service_status():
    """Status du service de sentiment"""
    return {
        "success": True,
        "status": "operational",
        "services": {
            "local_analyzer": bool(local_analyze_sentiment),
            "local_predictor": bool(local_predict_population_reaction),
            "gpt_predictor": bool(gpt_predict_population_reaction)
        }
    }

logger.info("✅ sentiment_routes chargé avec succès")
