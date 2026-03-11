"""
Service de notifications Telegram pour Veille Média Guadeloupe.

Configuration requise (variables d'environnement) :
  TELEGRAM_BOT_TOKEN  — token du bot créé via @BotFather
  TELEGRAM_CHAT_ID    — ID du chat/groupe où envoyer les notifs

Pour obtenir le chat_id :
  1. Envoie un message au bot
  2. Appelle https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Récupère le chat.id dans la réponse
"""

import os
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger("veille.telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    """Vérifie si Telegram est configuré."""
    return bool(BOT_TOKEN and CHAT_ID)


def send_message(text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
    """Envoie un message Telegram. Retourne True si succès."""
    if not is_configured():
        logger.debug("Telegram non configuré — notification ignorée")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return True
            logger.warning(f"Telegram API erreur: {result}")
            return False
    except Exception as e:
        logger.warning(f"Telegram envoi échoué: {e}")
        return False


# ── Templates de notification ──────────────────────────────

def _gravity_emoji(gravity: float) -> str:
    if gravity >= 0.80:
        return "🔴"
    elif gravity >= 0.60:
        return "🟠"
    elif gravity >= 0.45:
        return "🟡"
    return "🟢"


def _priority_label(gravity: float) -> str:
    if gravity >= 0.75:
        return "CRITIQUE"
    elif gravity >= 0.55:
        return "IMPORTANT"
    elif gravity >= 0.40:
        return "À SUIVRE"
    return "MINEUR"


def notify_new_affair(affair: Dict[str, Any], source_type: str = "article") -> bool:
    """Notifie la création d'une nouvelle affaire."""
    title = affair.get("title", "Sans titre")[:150]
    description = affair.get("description", "")[:200]
    gravity = affair.get("gravity_score", 0)
    theme = affair.get("theme", "")
    elected = affair.get("elected", []) or []
    institutions = affair.get("institutions", []) or []
    sources = affair.get("sources", []) or []

    emoji = _gravity_emoji(gravity)
    priority = _priority_label(gravity)

    # Icône source
    source_icon = {"article": "📰", "transcription": "📻", "social": "📱"}.get(source_type, "📄")

    entities_str = ", ".join((elected + institutions)[:5]) or "—"
    source_str = ", ".join(sources[:2]) or "—"

    text = (
        f"{emoji} <b>NOUVELLE AFFAIRE — {priority}</b>\n\n"
        f"<b>{title}</b>\n"
    )
    if description:
        text += f"{description}\n"
    text += (
        f"\n"
        f"{source_icon} Source : {source_str}\n"
        f"📊 Gravité : {gravity:.0%}\n"
        f"🏷 Thème : {theme}\n"
        f"👤 Entités : {entities_str}\n"
    )

    return send_message(text)


def notify_affair_escalation(affair: Dict[str, Any], old_gravity: float, new_gravity: float) -> bool:
    """Notifie quand une affaire monte en gravité."""
    if new_gravity - old_gravity < 0.10:
        return False  # Pas assez significatif

    title = affair.get("title", "Sans titre")[:150]
    emoji = _gravity_emoji(new_gravity)
    item_count = affair.get("item_count", 0)

    text = (
        f"{emoji} <b>ESCALADE</b>\n\n"
        f"<b>{title}</b>\n"
        f"📊 Gravité : {old_gravity:.0%} → {new_gravity:.0%}\n"
        f"📎 {item_count} sources\n"
    )

    return send_message(text)


def notify_daily_summary(
    affairs_created: int,
    affairs_total: int,
    articles_enriched: int,
    top_affairs: list,
) -> bool:
    """Résumé quotidien de la veille."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    text = (
        f"📋 <b>RÉSUMÉ VEILLE — {now}</b>\n\n"
        f"🆕 {affairs_created} nouvelles affaires\n"
        f"📊 {affairs_total} affaires actives\n"
        f"📰 {articles_enriched} articles enrichis\n"
    )

    if top_affairs:
        text += "\n<b>Top affaires :</b>\n"
        for i, aff in enumerate(top_affairs[:5], 1):
            g = aff.get("gravity_score", 0)
            emoji = _gravity_emoji(g)
            text += f"{i}. {emoji} {aff.get('title', '?')[:80]} ({g:.0%})\n"

    return send_message(text)


# ── Endpoint de test ──────────────────────────────────────

def test_connection() -> Dict[str, Any]:
    """Teste la connexion Telegram."""
    if not is_configured():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID non configuré"}

    success = send_message("✅ <b>Veille Média Guadeloupe</b> — Connexion Telegram OK !")
    return {"ok": success, "bot_token_set": bool(BOT_TOKEN), "chat_id_set": bool(CHAT_ID)}
