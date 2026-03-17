import logging
import hashlib
import re
from fastapi import APIRouter, HTTPException
from typing import Dict
from .async_sentiment_service import (
    async_sentiment_service,
    analyze_text_async,
    get_text_sentiment_cached,
    get_sentiment_analysis_status,
)
from bson.objectid import ObjectId

logger = logging.getLogger("sentiment_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 sentiment_routes module loaded")

router = APIRouter()

def _status_from_queue_entry(entry):
    if not entry:
        return {"status": "not_queued"}
    return {
        "status": entry.get("status"),
        "attempts": entry.get("attempts", 0),
        "queued_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "result": entry.get("result") if entry.get("status") in ["done", "error"] else None,
    }

@router.post("/sentiment/async", tags=["sentiment"])
async def enqueue_sentiment(payload: Dict):
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Champ 'text' requis")
    task = analyze_text_async(text)
    if not task:
        raise HTTPException(status_code=503, detail="Service async indisponible")

    # déterminer task_id et status
    task_id = None
    status = None
    result = None
    if isinstance(task, dict):
        status = task.get("status")
        if "id" in task:
            task_id = task["id"]
        elif status == "cached":
            task_id = hashlib.md5(text.encode("utf-8")).hexdigest()
            result = task.get("result")
    elif isinstance(task, str):  # backward compatibility: plain hash string
        task_id = task
        status = "cached"
        result = get_text_sentiment_cached(text) or None

    response = {"task_id": task_id, "status": status}
    if result is not None:
        response["result"] = result
    return response

@router.get("/sentiment/status/{task_id}", tags=["sentiment"])
async def sentiment_status(task_id: str):
    # try queue id (ObjectId)
    if re.fullmatch(r"[0-9a-fA-F]{24}", task_id):
        try:
            entry = async_sentiment_service.queue.find_one({"_id": ObjectId(task_id)})
            return {"status": _status_from_queue_entry(entry)}
        except Exception:
            pass
    # if looks like md5 hash (32 hex) treat as text_hash
    if re.fullmatch(r"[0-9a-f]{32}", task_id):
        entry = async_sentiment_service.queue.find_one({"text_hash": task_id})
        if entry:
            return {"status": _status_from_queue_entry(entry)}
        cached = async_sentiment_service.cache.find_one({"text_hash": task_id})
        if cached:
            return {"status": {"status": "done", "result": cached.get("result")}}
        return {"status": {"status": "not_queued"}}
    # else assume raw text
    return {"status": get_sentiment_analysis_status(task_id)}

@router.get("/sentiment/result/{task_id}", tags=["sentiment"])
async def sentiment_result(task_id: str):
    # queue id
    if re.fullmatch(r"[0-9a-fA-F]{24}", task_id):
        try:
            entry = async_sentiment_service.queue.find_one({"_id": ObjectId(task_id)})
            if entry and entry.get("status") in ["done", "error"]:
                return {"result": entry.get("result")}
        except Exception:
            pass
    # hash
    if re.fullmatch(r"[0-9a-f]{32}", task_id):
        cached = async_sentiment_service.cache.find_one({"text_hash": task_id})
        if cached:
            return {"result": cached.get("result")}
        entry = async_sentiment_service.queue.find_one({"text_hash": task_id})
        if entry and entry.get("status") in ["done", "error"]:
            return {"result": entry.get("result")}
        raise HTTPException(status_code=404, detail="Résultat non disponible")
    # raw text
    result = get_text_sentiment_cached(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Résultat non disponible")
    return {"result": result}