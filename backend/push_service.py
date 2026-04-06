# backend/push_service.py
"""
Service de notifications push Web Push pour Veille Média Guadeloupe.

Envoie une notification push à tous les abonnés quand une nouvelle affaire est créée.

Configuration requise (variables d'environnement) :
  VAPID_PUBLIC_KEY   — clé publique VAPID (base64url)
  VAPID_PRIVATE_KEY  — clé privée VAPID (base64url)
  VAPID_CLAIMS_EMAIL — email de contact (ex: mailto:djamalloiseau@gmail.com)
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("veille.push")

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:djamalloiseau@gmail.com")


def is_configured() -> bool:
    """Vérifie si le service push est configuré."""
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def _get_subscriptions_collection(db=None):
    """Retourne la collection MongoDB des abonnements push."""
    if db is None:
        from backend.db import get_db
        db = get_db()
    return db["push_subscriptions"]


def save_subscription(subscription: Dict[str, Any], db=None) -> bool:
    """Enregistre un abonnement push en base."""
    try:
        col = _get_subscriptions_collection(db)
        endpoint = subscription.get("endpoint", "")
        if not endpoint:
            return False

        # Upsert : met à jour si l'endpoint existe déjà
        col.update_one(
            {"endpoint": endpoint},
            {"$set": {
                "endpoint": endpoint,
                "keys": subscription.get("keys", {}),
                "subscribed_at": __import__("datetime").datetime.utcnow().isoformat(),
            }},
            upsert=True,
        )
        logger.info(f"✅ Push subscription enregistrée: {endpoint[:60]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur save push subscription: {e}")
        return False


def remove_subscription(endpoint: str, db=None) -> bool:
    """Supprime un abonnement push."""
    try:
        col = _get_subscriptions_collection(db)
        result = col.delete_one({"endpoint": endpoint})
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"❌ Erreur remove push subscription: {e}")
        return False


def _send_push(subscription: Dict, payload: str) -> bool:
    """Envoie une notification push à un abonné."""
    try:
        from pywebpush import webpush, WebPushException

        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": subscription.get("keys", {}),
            },
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
        )
        return True
    except Exception as e:
        error_str = str(e)
        # 410 Gone = abonnement expiré, le supprimer
        if "410" in error_str or "404" in error_str:
            logger.info(f"🗑️ Subscription expirée, suppression: {subscription.get('endpoint', '')[:50]}")
            remove_subscription(subscription.get("endpoint", ""))
        else:
            logger.warning(f"❌ Push envoi échoué: {error_str[:100]}")
        return False


def notify_new_affair(affair: Dict[str, Any], db=None) -> int:
    """Envoie une notification push à tous les abonnés pour une nouvelle affaire.

    Returns:
        Nombre de notifications envoyées avec succès.
    """
    if not is_configured():
        logger.debug("Push non configuré — notification ignorée")
        return 0

    title = affair.get("title", "Nouvelle affaire")[:100]
    gravity = affair.get("gravity_score", 0)
    theme = affair.get("theme", "")
    communes = ", ".join((affair.get("communes", []) or [])[:3])

    # Emoji de gravité
    if gravity >= 0.80:
        icon = "🔴"
    elif gravity >= 0.60:
        icon = "🟠"
    elif gravity >= 0.45:
        icon = "🟡"
    else:
        icon = "🟢"

    body = f"{icon} {theme}"
    if communes:
        body += f" — {communes}"
    body += f" | Gravité: {gravity:.0%}"

    payload = json.dumps({
        "title": f"🔔 {title}",
        "body": body,
        "icon": "/icons/icon-192.png",
        "badge": "/icons/icon-192.png",
        "tag": f"affair-{str(affair.get('_id', ''))[:12]}",
        "url": "/",
    })

    col = _get_subscriptions_collection(db)
    subscriptions = list(col.find())

    sent = 0
    for sub in subscriptions:
        if _send_push(sub, payload):
            sent += 1

    logger.info(f"🔔 Push envoyé: {sent}/{len(subscriptions)} abonnés — '{title[:50]}'")
    return sent


def get_public_key() -> str:
    """Retourne la clé publique VAPID pour le frontend."""
    return VAPID_PUBLIC_KEY
