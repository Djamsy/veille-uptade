# backend/telegram_routes.py
import os
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException

# importe l'instance globale du service
try:
    from backend.telegram_alerts_service import telegram_alerts  # type: ignore
except Exception:  # fallback si exécuté différemment
    from telegram_alerts_service import telegram_alerts  # type: ignore

logger = logging.getLogger("telegram_routes")
router = APIRouter(prefix="/telegram", tags=["telegram"])

@router.post("/configure")
def configure(payload: Dict[str, Any] = Body(...)):
    """
    Configure le bot Telegram (token + chat_id).
    Body JSON: {"token": "...","chat_id": 123456789}
    """
    token = payload.get("token") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = payload.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise HTTPException(
            status_code=400,
            detail="token et chat_id requis (ou vars d'env TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)",
        )
    try:
        chat_id_int = int(chat_id)
    except Exception:
        raise HTTPException(status_code=400, detail="chat_id doit être un entier")

    ok = telegram_alerts.configure_telegram(token, chat_id_int)
    if not ok:
        raise HTTPException(status_code=500, detail="Échec configuration")
    return {"success": True, "configured": True}

@router.post("/test")
def send_test(payload: Dict[str, Any] = Body(default={})):
    """
    Envoie un message de test au chat_id configuré (ou surchargé via body).
    Body JSON (optionnel): {"chat_id": 123456789}
    """
    chat_id = payload.get("chat_id")
    chat_id_int: Optional[int] = int(chat_id) if chat_id is not None else None
    ok = telegram_alerts.send_test_alert(chat_id_int)
    return {"success": ok}

@router.post("/start")
def start_monitoring():
    telegram_alerts.start_monitoring()
    return {"success": True, "monitoring": True}

@router.post("/stop")
def stop_monitoring():
    telegram_alerts.stop_monitoring()
    return {"success": True, "monitoring": False}

@router.get("/status")
def status():
    return {"success": True, "status": telegram_alerts.get_monitoring_status()}
