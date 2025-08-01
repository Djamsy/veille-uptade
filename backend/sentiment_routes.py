import logging
from fastapi import APIRouter, HTTPException
from typing import Dict

from .async_sentiment_service import (
    analyze_text_async,
    get_text_sentiment_cached,
    get_sentiment_analysis_status,
)

logger = logging.getLogger("sentiment_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 sentiment_routes module loaded")

router = APIRouter()

@router.post("/sentiment/async", tags=["sentiment"])
async def enqueue_sentiment(payload: Dict):
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")
    return task

@router.get("/sentiment/status/{task_id}", tags=["sentiment"])
async def sentiment_status(task_id: str):
    status = get_sentiment_analysis_status(task_id)
    return {"status": status}

@router.get("/sentiment/result/{task_id}", tags=["sentiment"])
async def sentiment_result(task_id: str):
    result = get_text_sentiment_cached(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Résultat non disponible")
    return {"result": result}