import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional, Any

from .async_sentiment_service import (
    analyze_text_async,
    get_text_sentiment_cached,
    get_sentiment_analysis_status,
)

logger = logging.getLogger("sentiment_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 sentiment_routes module loaded")

router = APIRouter()

# ---------- Schemas ----------
class AnalyzePayload(BaseModel):
    text: str
    async_: bool = Field(False, alias="async")  # le front envoie "async"

class PredictPayload(BaseModel):
    text: str
    context: Optional[Dict[str, Any]] = None

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
    }

# ---------- ENDPOINTS utilisés par le front ----------

@router.post("/sentiment/analyze", tags=["sentiment"])
async def analyze(payload: AnalyzePayload):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # On lance toujours l'analyse asynchrone et on renvoie l'ID au front
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")

    task_id = task.get("task_id") if isinstance(task, dict) else str(task)
    return {
        "success": True,
        "async": True,
        "text_hash": task_id,              # le front lit 'text_hash'
        "message": "Analyse lancée."
    }

@router.get("/sentiment/status/{task_id}", tags=["sentiment"])
async def sentiment_status(task_id: str):
    status = get_sentiment_analysis_status(task_id)

    if status == "completed":
        result = get_text_sentiment_cached(task_id)
        if result:
            # IMPORTANT: le front attend { success, status: 'completed', basic_sentiment, contextual_analysis, stakeholders }
            return {"success": True, "status": "completed", **result}
        # si pas trouvé malgré 'completed'
        return {"success": True, "status": "not_found"}

    if status in ("queued", "processing"):
        return {"success": True, "status": status}

    # inconnu
    return {"success": True, "status": "not_found"}

@router.post("/sentiment/predict-reaction", tags=["sentiment"])
async def predict_reaction(payload: PredictPayload):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")

    # Démo locale rapide. Si tu veux GPT, branche ici ton service GPT et retourne le même format.
    prediction = quick_predict(text)
    return {"success": True, "prediction": prediction}

# ---------- (Optionnel) Compat: anciennes routes alignées au format attendu ----------

@router.post("/sentiment/async", tags=["sentiment"])
async def enqueue_sentiment(payload: Dict[str, Any]):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")
    task_id = task.get("task_id") if isinstance(task, dict) else str(task)
    return {"success": True, "async": True, "text_hash": task_id, "message": "Analyse en file d'attente."}

@router.get("/sentiment/result/{task_id}", tags=["sentiment"])
async def sentiment_result(task_id: str):
    result = get_text_sentiment_cached(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Résultat non disponible")
    # On renvoie aussi 'success' pour cohérence
    return {"success": True, **result}