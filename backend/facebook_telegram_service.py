# backend/facebook_telegram_service.py
"""
Service de republication Facebook → Telegram.

Récupère les publications d'une page Facebook via Graph API
et les republie automatiquement sur Telegram avec un formatage spécifique.

Configuration requise (variables d'environnement) :
  FACEBOOK_PAGE_ACCESS_TOKEN  — token d'accès de la page Facebook
  FACEBOOK_PAGE_ID            — ID numérique de la page Facebook
  TELEGRAM_BOT_TOKEN          — (déjà configuré dans telegram_service.py)
  TELEGRAM_CHAT_ID            — (déjà configuré dans telegram_service.py)

Pour obtenir le token Facebook :
  1. Aller sur https://developers.facebook.com
  2. Créer une App (type Business)
  3. Ajouter le produit "Facebook Login" ou "Pages API"
  4. Obtenir un Page Access Token via Graph API Explorer
     - Permissions nécessaires : pages_read_engagement, pages_read_user_content
  5. Convertir en token longue durée (60 jours) via :
     GET /oauth/access_token?grant_type=fb_exchange_token
       &client_id={APP_ID}&client_secret={APP_SECRET}
       &fb_exchange_token={SHORT_TOKEN}
"""

import os
import logging
import urllib.request
import urllib.parse
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger("veille.facebook_telegram")

# ── Configuration ──────────────────────────────────────────
FB_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Nombre max de posts à récupérer par requête
FB_POSTS_LIMIT = 10


def is_configured() -> bool:
    """Vérifie si le service Facebook est configuré."""
    return bool(FB_PAGE_TOKEN and FB_PAGE_ID)


def _graph_get(endpoint: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict]:
    """Appel GET à l'API Graph Facebook."""
    if not params:
        params = {}
    params["access_token"] = FB_PAGE_TOKEN

    url = f"{GRAPH_API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VeilleMedia/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"Graph API HTTP {e.code}: {body[:300]}")
        return None
    except Exception as e:
        logger.error(f"Graph API erreur: {e}")
        return None


def fetch_recent_posts(limit: int = FB_POSTS_LIMIT) -> List[Dict[str, Any]]:
    """Récupère les derniers posts de la page Facebook.

    Returns:
        Liste de posts avec id, message, created_time, permalink_url, etc.
    """
    if not is_configured():
        logger.warning("Facebook non configuré — fetch ignoré")
        return []

    data = _graph_get(
        f"{FB_PAGE_ID}/posts",
        {
            "fields": "id,message,created_time,permalink_url,full_picture,attachments{title,description,url}",
            "limit": str(limit),
        },
    )

    if not data or "data" not in data:
        logger.warning("Aucun post retourné par Graph API")
        return []

    return data["data"]


def _extract_title(message: str) -> str:
    """Extrait le titre d'un post Facebook.

    Stratégie :
      1. Si une ligne est en MAJUSCULES → c'est le titre
      2. Sinon, la première ligne (tronquée à 120 chars)
    """
    if not message:
        return "Publication Facebook"

    lines = [l.strip() for l in message.strip().split("\n") if l.strip()]
    if not lines:
        return "Publication Facebook"

    # Chercher une ligne en majuscules (souvent le titre dans les posts FB)
    for line in lines[:3]:
        # Au moins 5 caractères et majorité de majuscules
        alpha_chars = [c for c in line if c.isalpha()]
        if len(alpha_chars) >= 5 and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.7:
            return line[:120]

    # Sinon première ligne
    first = lines[0]
    if len(first) > 120:
        return first[:117] + "..."
    return first


def _format_telegram_message(post: Dict[str, Any]) -> str:
    """Formate un post Facebook pour Telegram.

    Format :
      *{titre}*
      🔗 {lien}
      {texte}
    """
    message = post.get("message", "")
    permalink = post.get("permalink_url", "")

    # Titre
    title = _extract_title(message)

    # Texte (sans le titre si la première ligne = titre)
    body = message.strip()
    lines = body.split("\n")
    if lines and lines[0].strip() == title:
        body = "\n".join(lines[1:]).strip()

    # Tronquer le corps si trop long pour Telegram (max ~4000 chars)
    if len(body) > 1500:
        body = body[:1497] + "..."

    # Escape HTML special chars pour le parse_mode HTML du Telegram service
    def escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    parts = [f"<b>{escape_html(title)}</b>"]

    if permalink:
        parts.append(f"🔗 <a href=\"{permalink}\">Voir sur Facebook</a>")

    if body:
        parts.append(f"\n{escape_html(body)}")

    # Horodatage
    created = post.get("created_time", "")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("+0000", "+00:00"))
            parts.append(f"\n📅 {dt.strftime('%d/%m/%Y %H:%M')}")
        except Exception:
            pass

    return "\n".join(parts)


def sync_facebook_to_telegram(db=None) -> Dict[str, Any]:
    """Synchronise les nouveaux posts Facebook vers Telegram.

    Utilise la collection `facebook_posts` dans MongoDB pour le suivi
    des posts déjà envoyés (anti-doublon persistant).

    Args:
        db: Instance MongoDB (optionnel, utilise get_db() sinon)

    Returns:
        Dict avec les stats de synchronisation.
    """
    from backend.telegram_service import send_message, is_configured as tg_configured

    if not is_configured():
        return {"ok": False, "error": "Facebook non configuré (FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID manquant)"}

    if not tg_configured():
        return {"ok": False, "error": "Telegram non configuré"}

    # Base de données pour le suivi anti-doublon
    if db is None:
        from backend.db import get_db
        db = get_db()

    fb_collection = db["facebook_posts"]

    # Récupérer les posts récents
    posts = fetch_recent_posts()
    if not posts:
        logger.info("Aucun nouveau post Facebook trouvé")
        return {"ok": True, "fetched": 0, "sent": 0, "skipped": 0}

    sent = 0
    skipped = 0
    errors = 0

    for post in posts:
        post_id = post.get("id", "")
        if not post_id:
            continue

        # Anti-doublon : vérifier si déjà envoyé
        existing = fb_collection.find_one({"fb_post_id": post_id})
        if existing:
            skipped += 1
            continue

        # Ignorer les posts sans message (partages, photos sans texte, etc.)
        if not post.get("message", "").strip():
            skipped += 1
            continue

        # Formater et envoyer
        telegram_text = _format_telegram_message(post)

        try:
            success = send_message(telegram_text, parse_mode="HTML", disable_preview=False)

            if success:
                # Sauvegarder en base pour anti-doublon
                fb_collection.insert_one({
                    "fb_post_id": post_id,
                    "message_preview": (post.get("message", ""))[:200],
                    "permalink": post.get("permalink_url", ""),
                    "fb_created_time": post.get("created_time", ""),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "telegram_sent": True,
                })
                sent += 1
                logger.info(f"✅ Post FB {post_id} envoyé sur Telegram")
            else:
                errors += 1
                logger.warning(f"❌ Échec envoi Telegram pour post FB {post_id}")

        except Exception as e:
            errors += 1
            logger.error(f"❌ Erreur envoi post FB {post_id}: {e}")

    result = {
        "ok": True,
        "fetched": len(posts),
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"📘 Sync FB→TG terminée: {sent} envoyés, {skipped} ignorés, {errors} erreurs")
    return result
