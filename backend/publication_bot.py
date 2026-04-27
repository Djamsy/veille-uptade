# backend/publication_bot.py
"""
Bot Telegram de publication automatique sur les réseaux sociaux.

Flow :
  1. L'utilisateur envoie une photo/vidéo avec une légende sur Telegram
  2. Le bot parse la légende (titre en gras, corps, hashtags)
  3. Le média est uploadé sur Cloudinary (temporaire 24h)
  4. Le post est publié sur tous les réseaux via Buffer
  5. Le post est sauvegardé dans MongoDB avec la campagne détectée

Configuration requise (variables d'environnement) :
  PUBLICATION_BOT_TOKEN — token du bot Telegram (@BotFather)
  BUFFER_ACCESS_TOKEN   — token Buffer API
  CLOUDINARY_*          — config Cloudinary (voir campaign_service.py)

Format de la légende :
  *Titre du post*

  Corps du texte...

  #hashtag1 #hashtag2
"""

import os
import logging
import json
import re
import urllib.request
import threading
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("veille.publication_bot")

PUBLICATION_BOT_TOKEN = os.getenv("PUBLICATION_BOT_TOKEN", "")
# IDs Telegram autorisés (sécurité — seuls ces users peuvent publier)
AUTHORIZED_USERS = [int(x) for x in os.getenv("PUBLICATION_BOT_AUTHORIZED", "").split(",") if x.strip()]

TELEGRAM_API = f"https://api.telegram.org/bot{PUBLICATION_BOT_TOKEN}"


def is_configured() -> bool:
    return bool(PUBLICATION_BOT_TOKEN)


# ── Parsing de la légende ──────────────────────────────

def parse_caption(text: str) -> Dict[str, str]:
    """Parse la légende Telegram en titre, corps et hashtags.

    Format attendu :
      *Titre en gras*
      Corps du texte...
      #hashtag1 #hashtag2
    """
    if not text:
        return {"title": "", "body": "", "hashtags": [], "full_text": ""}

    # Extraire le titre (entre * ... * ou première ligne)
    title = ""
    body = text.strip()

    # Markdown bold : *titre*
    bold_match = re.match(r'^\*(.+?)\*\s*\n?', text.strip())
    if bold_match:
        title = bold_match.group(1).strip()
        body = text[bold_match.end():].strip()
    else:
        # Première ligne comme titre
        lines = text.strip().split('\n')
        if lines:
            title = lines[0].strip()
            body = '\n'.join(lines[1:]).strip()

    # Extraire les hashtags
    hashtags = re.findall(r'#(\w+)', body)

    # Corps sans les hashtags
    body_clean = re.sub(r'#\w+\s*', '', body).strip()

    # Texte complet pour Buffer (titre + corps + hashtags)
    full_text = text.strip()

    return {
        "title": title,
        "body": body_clean,
        "hashtags": hashtags,
        "full_text": full_text,
    }


# ── Telegram API helpers ──────────────────────────────

def _tg_api(method: str, data: Dict = None) -> Optional[Dict]:
    """Appel à l'API Telegram."""
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
    """Envoie un message Telegram."""
    return _tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })


def _tg_get_file_url(file_id: str) -> Optional[str]:
    """Récupère l'URL de téléchargement d'un fichier Telegram."""
    result = _tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        file_path = result["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{PUBLICATION_BOT_TOKEN}/{file_path}"
    return None


# ── Traitement d'un message ──────────────────────────

def process_message(message: Dict) -> Dict[str, Any]:
    """Traite un message Telegram entrant (photo/vidéo + légende).

    Returns:
        Dict avec le résultat de la publication.
    """
    from backend.campaign_service import (
        detect_campaign, save_post, upload_to_cloudinary, publish_to_buffer
    )

    chat_id = message.get("chat", {}).get("id", 0)
    user_id = message.get("from", {}).get("id", 0)
    username = message.get("from", {}).get("username", "inconnu")

    # Vérification d'autorisation
    if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
        _tg_send(chat_id, "⛔ Vous n'êtes pas autorisé à publier.")
        return {"ok": False, "error": "unauthorized"}

    # Déterminer le type de média
    media_type = "photo"
    file_id = None

    if "photo" in message:
        # Prendre la plus grande résolution
        photos = message["photo"]
        file_id = photos[-1]["file_id"]
        media_type = "photo"
    elif "video" in message:
        file_id = message["video"]["file_id"]
        media_type = "video"
    elif "document" in message:
        mime = message["document"].get("mime_type", "")
        file_id = message["document"]["file_id"]
        media_type = "video" if "video" in mime else "photo"
    else:
        _tg_send(chat_id, "📎 Envoyez une photo ou vidéo avec une légende pour publier.")
        return {"ok": False, "error": "no_media"}

    caption = message.get("caption", "")
    if not caption:
        _tg_send(chat_id, "✏️ Ajoutez une légende à votre média pour publier.\n\nFormat :\n<code>*Titre*\nTexte du post\n#hashtag</code>")
        return {"ok": False, "error": "no_caption"}

    # Accusé de réception
    _tg_send(chat_id, f"⏳ Publication en cours...\n📄 {media_type.upper()} détecté")

    # 1. Parser la légende
    parsed = parse_caption(caption)
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
        # Retry 1 fois
        logger.warning(f"⚠️ Buffer 1ère tentative échouée, retry...")
        import time
        time.sleep(2)
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
            import time
            time.sleep(5)
