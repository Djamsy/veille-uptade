# backend/publication_bot.py
"""
Bot Telegram de publication automatique sur les réseaux sociaux.

Flow classique (légende courte) :
  1. L'utilisateur envoie une photo/vidéo avec une légende sur Telegram
  2. Le bot parse la légende (titre en gras, corps, hashtags)
  3. Le média est uploadé sur Cloudinary (temporaire 24h)
  4. Le post est publié sur tous les réseaux via Buffer
  5. Le post est sauvegardé dans MongoDB avec la campagne détectée

Flow 2 messages (texte long) :
  1. L'utilisateur envoie un média SANS légende (ou légende courte = titre)
  2. Le bot répond "📝 Envoyez le texte complet maintenant"
  3. L'utilisateur envoie le texte complet dans un second message
  4. Le bot combine média + texte et publie

Configuration requise (variables d'environnement) :
  PUBLICATION_BOT_TOKEN — token du bot Telegram (@BotFather)
  BUFFER_ACCESS_TOKEN   — token Buffer API
  CLOUDINARY_*          — config Cloudinary (voir campaign_service.py)
"""

import os
import logging
import json
import re
import urllib.request
import time as _time
from typing import Dict, Any, Optional, List

logger = logging.getLogger("veille.publication_bot")

PUBLICATION_BOT_TOKEN = os.getenv("PUBLICATION_BOT_TOKEN", "")
# IDs Telegram autorisés (sécurité — seuls ces users peuvent publier)
AUTHORIZED_USERS = [int(x) for x in os.getenv("PUBLICATION_BOT_AUTHORIZED", "").split(",") if x.strip()]

TELEGRAM_API = f"https://api.telegram.org/bot{PUBLICATION_BOT_TOKEN}"

# Sessions en attente de texte (user_id → {file_id, media_type, caption, chat_id, timestamp})
_pending_sessions: Dict[int, Dict[str, Any]] = {}

# Durée max d'une session en attente (5 minutes)
SESSION_TIMEOUT = 300


def is_configured() -> bool:
    return bool(PUBLICATION_BOT_TOKEN)


# ── Parsing de la légende ──────────────────────────────

def parse_caption(text: str) -> Dict[str, Any]:
    """Parse la légende Telegram en titre, corps et hashtags."""
    if not text:
        return {"title": "", "body": "", "hashtags": [], "full_text": ""}

    title = ""
    body = text.strip()

    # Markdown bold : *titre*
    bold_match = re.match(r'^\*(.+?)\*\s*\n?', text.strip())
    if bold_match:
        title = bold_match.group(1).strip()
        body = text[bold_match.end():].strip()
    else:
        lines = text.strip().split('\n')
        if lines:
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

    hashtags = re.findall(r'#(\w+)', body)
    body_clean = re.sub(r'#\w+\s*', '', body).strip()
    full_text = text.strip()

    return {
        "title": title,
        "body": body_clean,
        "hashtags": hashtags,
        "full_text": full_text,
    }


# ── Telegram API helpers ──────────────────────────────

def _tg_api(method: str, data: Dict = None) -> Optional[Dict]:
    url = f"{TELEGRAM_API}/{method}"
    try:
        payload = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Telegram API error ({method}): {e}")
        return None


def _tg_send(chat_id: int, text: str, parse_mode: str = "HTML"):
    return _tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })


def _tg_get_file_url(file_id: str) -> Optional[str]:
    result = _tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        file_path = result["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{PUBLICATION_BOT_TOKEN}/{file_path}"
    return None


# ── Publication commune ──────────────────────────────

def _publish(chat_id: int, username: str, file_id: str, media_type: str, text: str) -> Dict[str, Any]:
    """Publie un média + texte sur tous les RS via Buffer."""
    from backend.campaign_service import (
        detect_campaign, save_post, upload_to_cloudinary, publish_to_buffer
    )

    # Accusé de réception
    _tg_send(chat_id, f"⏳ Publication en cours...\n📄 {media_type.upper()} détecté")

    # 1. Parser le texte
    parsed = parse_caption(text)
    logger.info(f"📝 Post de @{username}: '{parsed['title'][:50]}' ({media_type})")

    # 2. Détecter la campagne
    campaign = detect_campaign(parsed["full_text"])
    campaign_name = campaign.get("name", "Institutionnel") if campaign else "Institutionnel"
    campaign_id = str(campaign.get("_id", "")) if campaign else ""

    # 3. Upload sur Cloudinary
    tg_file_url = _tg_get_file_url(file_id)
    if not tg_file_url:
        _tg_send(chat_id, "❌ Impossible de récupérer le fichier. Réessayez.")
        return {"ok": False, "error": "file_download_failed"}

    resource_type = "video" if media_type == "video" else "image"
    cloudinary_url = upload_to_cloudinary(tg_file_url, resource_type)
    if not cloudinary_url:
        _tg_send(chat_id, "❌ Upload Cloudinary échoué. Vérifiez la configuration.")
        return {"ok": False, "error": "cloudinary_failed"}

    # 4. Publier via Buffer
    buffer_result = publish_to_buffer(
        text=parsed["full_text"],
        media_urls=[cloudinary_url],
    )

    if not buffer_result.get("ok"):
        logger.warning("⚠️ Buffer 1ère tentative échouée, retry...")
        _time.sleep(2)
        buffer_result = publish_to_buffer(
            text=parsed["full_text"],
            media_urls=[cloudinary_url],
        )

    # 5. Sauvegarder le post
    post = save_post({
        "title": parsed["title"],
        "body": parsed["body"],
        "hashtags": parsed["hashtags"],
        "media_url": cloudinary_url,
        "media_type": media_type,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "buffer_ids": buffer_result.get("buffer_ids", []),
        "telegram_user": username,
    })

    # 6. Réponse Telegram
    if buffer_result.get("ok"):
        _tg_send(chat_id,
            f"✅ <b>Publié !</b>\n\n"
            f"📢 Campagne : <b>{campaign_name}</b>\n"
            f"📄 Format : {media_type}\n"
            f"🌐 {buffer_result.get('profiles_count', 0)} plateformes\n"
            f"🏷 {', '.join('#' + h for h in parsed['hashtags'][:5]) or '—'}"
        )
    else:
        error_msg = buffer_result.get("error", "inconnue")
        _tg_send(chat_id,
            f"⚠️ <b>Publication partielle</b>\n\n"
            f"Le média a été sauvegardé mais Buffer a échoué.\n"
            f"Erreur : {str(error_msg)[:200]}\n\n"
            f"📢 Campagne : {campaign_name}\n"
            f"Vous pouvez publier manuellement depuis Buffer."
        )

    return {
        "ok": buffer_result.get("ok", False),
        "post_id": str(post.get("_id", "")),
        "campaign": campaign_name,
        "platforms": buffer_result.get("profiles_count", 0),
    }


# ── Traitement d'un message ──────────────────────────

def _cleanup_expired_sessions():
    """Supprime les sessions expirées."""
    now = _time.time()
    expired = [uid for uid, s in _pending_sessions.items() if now - s["timestamp"] > SESSION_TIMEOUT]
    for uid in expired:
        session = _pending_sessions.pop(uid)
        _tg_send(session["chat_id"], "⏰ Session expirée. Renvoyez votre média pour recommencer.")


def _extract_media(message: Dict) -> tuple:
    """Extrait le file_id et media_type d'un message. Retourne (file_id, media_type) ou (None, None)."""
    if "photo" in message:
        return message["photo"][-1]["file_id"], "photo"
    if "video" in message:
        return message["video"]["file_id"], "video"
    if "document" in message:
        mime = message["document"].get("mime_type", "")
        return message["document"]["file_id"], "video" if "video" in mime else "photo"
    return None, None


def process_message(message: Dict) -> Dict[str, Any]:
    """Traite un message Telegram entrant.

    Gère deux flows :
      A) Média + légende complète → publie directement
      B) Média sans/courte légende → attend le texte dans un 2e message
      C) Texte seul (après un média) → combine avec le média en attente
    """
    _cleanup_expired_sessions()

    chat_id = message.get("chat", {}).get("id", 0)
    user_id = message.get("from", {}).get("id", 0)
    username = message.get("from", {}).get("username", "inconnu")

    # Vérification d'autorisation
    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        _tg_send(chat_id, "⛔ Vous n'êtes pas autorisé à publier.")
        return {"ok": False, "error": "unauthorized"}

    # Commande /cancel
    text_msg = message.get("text", "")
    if text_msg.strip().lower() in ("/cancel", "/annuler"):
        if user_id in _pending_sessions:
            del _pending_sessions[user_id]
            _tg_send(chat_id, "❌ Publication annulée.")
            return {"ok": True, "action": "cancelled"}
        _tg_send(chat_id, "Rien à annuler.")
        return {"ok": True, "action": "nothing_to_cancel"}

    # Commande /help
    if text_msg.strip().lower() in ("/help", "/start", "/aide"):
        _tg_send(chat_id,
            "📢 <b>Bot Publication RS</b>\n\n"
            "<b>Option 1 — Tout en un :</b>\n"
            "Envoyez un média avec une légende complète :\n"
            "<code>*Titre*\nTexte du post\n#hashtag</code>\n\n"
            "<b>Option 2 — Texte long :</b>\n"
            "1️⃣ Envoyez le média (avec un titre court en légende ou sans légende)\n"
            "2️⃣ Envoyez le texte complet dans le message suivant\n\n"
            "<b>Commandes :</b>\n"
            "/cancel — Annuler la publication en cours\n"
            "/help — Afficher cette aide"
        )
        return {"ok": True, "action": "help"}

    file_id, media_type = _extract_media(message)
    caption = message.get("caption", "")

    # ── CAS A : Média avec légende longue (> 50 chars) → publication directe
    if file_id and caption and len(caption) > 50:
        return _publish(chat_id, username, file_id, media_type, caption)

    # ── CAS B : Média sans légende ou légende courte → stocker et attendre le texte
    if file_id:
        _pending_sessions[user_id] = {
            "file_id": file_id,
            "media_type": media_type,
            "caption": caption,  # Titre court éventuel
            "chat_id": chat_id,
            "username": username,
            "timestamp": _time.time(),
        }

        if caption:
            _tg_send(chat_id,
                f"📷 Média reçu ! Titre détecté : <b>{caption[:80]}</b>\n\n"
                f"📝 Envoyez maintenant le <b>texte complet</b> du post.\n"
                f"(ou /cancel pour annuler)"
            )
        else:
            _tg_send(chat_id,
                "📷 Média reçu !\n\n"
                "📝 Envoyez maintenant le <b>texte complet</b> du post.\n"
                "Format :\n<code>*Titre*\nTexte du post\n#hashtag</code>\n\n"
                "(ou /cancel pour annuler)"
            )
        return {"ok": True, "action": "waiting_for_text"}

    # ── CAS C : Texte seul → vérifier s'il y a une session en attente
    if text_msg and user_id in _pending_sessions:
        session = _pending_sessions.pop(user_id)

        # Si le média avait une légende courte (= titre), la combiner avec le texte
        if session["caption"]:
            # La légende courte = titre, le texte = corps
            full_text = f"*{session['caption']}*\n\n{text_msg}"
        else:
            full_text = text_msg

        return _publish(
            chat_id,
            session["username"],
            session["file_id"],
            session["media_type"],
            full_text,
        )

    # ── Ni média ni texte en attente
    if text_msg and user_id not in _pending_sessions:
        _tg_send(chat_id,
            "📎 Envoyez d'abord une <b>photo ou vidéo</b>, puis le texte.\n\n"
            "Tapez /help pour voir les formats acceptés."
        )
        return {"ok": False, "error": "no_media"}

    _tg_send(chat_id, "📎 Envoyez une photo ou vidéo pour publier. Tapez /help pour l'aide.")
    return {"ok": False, "error": "no_media"}


# ── Webhook handler (appelé par FastAPI) ──────────────

def handle_webhook(update: Dict) -> Dict:
    """Traite un webhook Telegram."""
    if "message" in update:
        return process_message(update["message"])
    return {"ok": True, "action": "ignored"}


# ── Polling mode (pour dev/test) ──────────────────────

def start_polling():
    """Démarre le bot en mode polling (dev uniquement)."""
    if not is_configured():
        logger.error("PUBLICATION_BOT_TOKEN non configuré")
        return

    logger.info("🤖 Bot publication démarré en mode polling...")
    offset = 0

    while True:
        try:
            result = _tg_api("getUpdates", {"offset": offset, "timeout": 30})
            if not result or not result.get("ok"):
                continue

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    try:
                        process_message(update["message"])
                    except Exception as e:
                        logger.error(f"Erreur traitement message: {e}")

        except Exception as e:
            logger.error(f"Polling error: {e}")
            _time.sleep(5)
