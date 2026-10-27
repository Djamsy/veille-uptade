# backend/routers/email_routes.py
"""Alertes e-mail Brevo : état de la configuration et envoi de test (admin)."""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.routers.auth_routes import require_admin
from backend.services import email_service

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/status")
def email_status(admin: Dict[str, Any] = Depends(require_admin)):
    """Configuration Brevo (la clé API n'est jamais renvoyée)."""
    return email_service.status()


@router.post("/test")
def email_test(admin: Dict[str, Any] = Depends(require_admin)):
    """Envoie un e-mail de test aux destinataires EMAIL_ALERT_TO."""
    if not email_service.is_configured():
        raise HTTPException(400, "Brevo non configuré : BREVO_API_KEY, BREVO_SENDER_EMAIL et EMAIL_ALERT_TO requis")
    mail = email_service.build_articles_email([{
        "title": "Test des alertes e-mail Veille Média",
        "source": "Veille Média 971", "theme": "test", "gravity_score": 0,
        "content": "Si vous recevez cet e-mail, les alertes Brevo fonctionnent.",
    }])
    result = email_service.send_email("✅ Test alertes e-mail — Veille Média 971", mail["html"], mail["text"])
    if not result.get("ok"):
        raise HTTPException(502, f"Échec Brevo : {result.get('error')}")
    return result
