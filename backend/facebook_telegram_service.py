# backend/facebook_telegram_service.py
"""
Service de republication Facebook → Telegram.

Scrape les publications d'une page Facebook publique via mbasic.facebook.com
et les republie automatiquement sur Telegram avec un formatage spécifique.

Configuration requise (variables d'environnement) :
  FACEBOOK_PAGE_NAME  — nom de la page (slug URL, ex: "maikifoguadeloupe")
  TELEGRAM_BOT_TOKEN  — (déjà configuré dans telegram_service.py)
  TELEGRAM_CHAT_ID    — (déjà configuré dans telegram_service.py)

Aucun token Facebook nécessaire — scraping de pages publiques uniquement.
"""

import os
import logging
import urllib.request
import urllib.parse
import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from html.parser import HTMLParser

logger = logging.getLogger("veille.facebook_telegram")

# ── Configuration ──────────────────────────────────────────
FB_PAGE_NAME = os.getenv("FACEBOOK_PAGE_NAME", "")
# Optionnel : plusieurs pages séparées par des virgules
# FACEBOOK_PAGE_NAME=page1,page2,page3
FB_SCRAPE_DELAY = 3  # secondes entre chaque requête (politesse)

MBASIC_BASE = "https://mbasic.facebook.com"

# Headers pour simuler un navigateur mobile basique
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


def is_configured() -> bool:
    """Vérifie si le service Facebook est configuré."""
    return bool(FB_PAGE_NAME)


def _get_page_names() -> List[str]:
    """Retourne la liste des noms de pages à scraper."""
    if not FB_PAGE_NAME:
        return []
    return [p.strip() for p in FB_PAGE_NAME.split(",") if p.strip()]


# ── HTML Parser minimaliste ──────────────────────────────

class _MbasicPostParser(HTMLParser):
    """Parse les posts depuis le HTML de mbasic.facebook.com/{page}."""

    def __init__(self):
        super().__init__()
        self.posts: List[Dict[str, Any]] = []
        self._current_post: Optional[Dict] = None
        self._in_story_body = False
        self._in_post_div = False
        self._depth = 0
        self._post_depth = 0
        self._text_buffer = ""
        self._current_link = ""
        self._collecting_text = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self._depth += 1

        # Détecter les blocs de posts (div avec data-ft ou article)
        if tag == "article" or (tag == "div" and "data-ft" in attrs_dict):
            self._in_post_div = True
            self._post_depth = self._depth
            self._current_post = {"text": "", "link": "", "id": ""}

            # Extraire l'ID du post si possible
            data_ft = attrs_dict.get("data-ft", "")
            if "mf_story_key" in data_ft:
                try:
                    import json
                    ft = json.loads(data_ft)
                    self._current_post["id"] = str(ft.get("mf_story_key", ""))
                except Exception:
                    pass

        # Détecter le contenu textuel du post
        if self._in_post_div:
            # Les paragraphes et spans dans le post contiennent le texte
            if tag in ("p", "span") and "story_body_container" not in attrs_dict.get("class", ""):
                pass  # on collecte le texte via handle_data

            # Liens vers le post complet (permalien)
            if tag == "a":
                href = attrs_dict.get("href", "")
                if "/story.php" in href or "/permalink" in href or "/posts/" in href:
                    if self._current_post and not self._current_post["link"]:
                        if href.startswith("/"):
                            href = f"https://www.facebook.com{href}"
                        self._current_post["link"] = href

    def handle_endtag(self, tag):
        if self._in_post_div and self._depth == self._post_depth:
            if tag in ("article", "div"):
                # Fin du bloc post
                if self._current_post and self._current_post.get("text", "").strip():
                    self.posts.append(self._current_post)
                self._current_post = None
                self._in_post_div = False
        self._depth -= 1

    def handle_data(self, data):
        if self._in_post_div and self._current_post is not None:
            text = data.strip()
            if text and len(text) > 2:
                if self._current_post["text"]:
                    self._current_post["text"] += "\n" + text
                else:
                    self._current_post["text"] = text


def _fetch_page_html(page_name: str) -> Optional[str]:
    """Récupère le HTML de la page mbasic.facebook.com/{page_name}."""
    url = f"{MBASIC_BASE}/{urllib.parse.quote(page_name)}"

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP {e.code} pour {url}")
        return None
    except Exception as e:
        logger.error(f"Erreur fetch {url}: {e}")
        return None


def _scrape_posts_regex(html: str, page_name: str) -> List[Dict[str, Any]]:
    """Extraction des posts par regex (plus robuste que le parser HTML).

    mbasic.facebook.com a une structure HTML simple et stable.
    """
    posts = []

    # Pattern pour les blocs de story (chaque post est dans un div avec data-ft)
    # On cherche les blocs de texte substantiels entre les marqueurs de post
    story_pattern = re.compile(
        r'<div[^>]*data-ft=["\'](\{[^"\']*\})["\'][^>]*>(.*?)</div>\s*<div[^>]*>.*?</div>\s*</div>',
        re.DOTALL
    )

    # Approche plus simple : extraire tous les textes > 50 chars dans les story bodies
    # Les posts sur mbasic ont cette structure :
    #   <div data-ft="..."> ... texte du post ... </div>
    #   suivi de liens (like, comment, share)

    # Pattern simplifié : trouver les textes entre balises dans les story containers
    text_blocks = re.findall(
        r'<div[^>]*data-ft=["\'][^"\']*mf_story_key["\':.\s]*["\']?(\d+)[^>]*>(.+?)<div[^>]*id="like_',
        html, re.DOTALL
    )

    if not text_blocks:
        # Fallback : chercher les story bodies directement
        text_blocks_alt = re.findall(
            r'data-ft="[^"]*"[^>]*>(.*?)<footer',
            html, re.DOTALL
        )
        for i, block in enumerate(text_blocks_alt):
            clean_text = _clean_html(block)
            if len(clean_text) > 30:
                post_hash = hashlib.md5(clean_text[:200].encode()).hexdigest()[:12]
                permalink = f"https://www.facebook.com/{page_name}"
                posts.append({
                    "id": f"{page_name}_{post_hash}",
                    "text": clean_text,
                    "link": permalink,
                })
    else:
        for story_key, block in text_blocks:
            clean_text = _clean_html(block)
            if len(clean_text) > 30:
                permalink = f"https://www.facebook.com/{page_name}/posts/{story_key}"
                posts.append({
                    "id": f"{page_name}_{story_key}",
                    "text": clean_text,
                    "link": permalink,
                })

    # Dernier fallback : extraction brute des paragraphes
    if not posts:
        paragraphs = re.findall(r'<p>(.*?)</p>', html, re.DOTALL)
        seen_texts = set()
        for p in paragraphs:
            clean = _clean_html(p)
            # Filtrer le bruit (menus, boutons, etc.)
            if (len(clean) > 50
                    and clean not in seen_texts
                    and not clean.startswith("Voir plus")
                    and "Créer" not in clean[:20]
                    and "Se connecter" not in clean):
                seen_texts.add(clean)
                post_hash = hashlib.md5(clean[:200].encode()).hexdigest()[:12]
                posts.append({
                    "id": f"{page_name}_{post_hash}",
                    "text": clean,
                    "link": f"https://www.facebook.com/{page_name}",
                })

    return posts[:10]  # Max 10 posts par page


def _clean_html(html_text: str) -> str:
    """Nettoie le HTML pour obtenir du texte brut."""
    # Supprimer les balises
    text = re.sub(r'<br\s*/?\s*>', '\n', html_text)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Décoder les entités HTML
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#039;", "'").replace("&apos;", "'")
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    # Nettoyer les espaces multiples
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


def fetch_recent_posts(page_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Récupère les derniers posts d'une page Facebook publique.

    Args:
        page_name: Nom de la page (optionnel, utilise FACEBOOK_PAGE_NAME sinon)

    Returns:
        Liste de posts avec id, text, link.
    """
    if page_name is None:
        pages = _get_page_names()
        if not pages:
            logger.warning("FACEBOOK_PAGE_NAME non configuré — fetch ignoré")
            return []
        page_name = pages[0]

    html = _fetch_page_html(page_name)
    if not html:
        return []

    posts = _scrape_posts_regex(html, page_name)
    logger.info(f"📘 {len(posts)} posts extraits de facebook.com/{page_name}")
    return posts


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
        alpha_chars = [c for c in line if c.isalpha()]
        if len(alpha_chars) >= 5 and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.7:
            return line[:120]

    # Sinon première ligne
    first = lines[0]
    if len(first) > 120:
        return first[:117] + "..."
    return first


def _escape_html(text: str) -> str:
    """Escape les caractères spéciaux pour le mode HTML de Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_telegram_message(post: Dict[str, Any], page_name: str = "") -> str:
    """Formate un post Facebook pour Telegram.

    Format :
      <b>{titre}</b>
      🔗 Voir sur Facebook
      {texte}
    """
    message = post.get("text", "")
    permalink = post.get("link", "")

    title = _extract_title(message)

    # Texte (sans le titre si la première ligne = titre)
    body = message.strip()
    lines = body.split("\n")
    if lines and lines[0].strip() == title:
        body = "\n".join(lines[1:]).strip()

    # Tronquer le corps si trop long pour Telegram (max ~4000 chars)
    if len(body) > 1500:
        body = body[:1497] + "..."

    msg = f"📘 <b>{_escape_html(title)}</b>"
    msg += "\n"

    if permalink:
        msg += f"\n🔗 <a href=\"{permalink}\">Voir sur Facebook</a>"
    msg += "\n"

    if body:
        msg += f"\n{_escape_html(body)}"

    return msg


def sync_facebook_to_telegram(db=None) -> Dict[str, Any]:
    """Synchronise les nouveaux posts Facebook vers Telegram.

    Scrape les pages publiques configurées dans FACEBOOK_PAGE_NAME
    et envoie les nouveaux posts sur Telegram.
    Anti-doublon persistant via MongoDB (collection `facebook_posts`).

    Args:
        db: Instance MongoDB (optionnel, utilise get_db() sinon)

    Returns:
        Dict avec les stats de synchronisation.
    """
    from backend.telegram_service import send_message, is_configured as tg_configured

    if not is_configured():
        return {"ok": False, "error": "FACEBOOK_PAGE_NAME non configuré"}

    if not tg_configured():
        return {"ok": False, "error": "Telegram non configuré"}

    # Base de données pour le suivi anti-doublon
    if db is None:
        from backend.db import get_db
        db = get_db()

    fb_collection = db["facebook_posts"]

    # Créer un index unique sur fb_post_id si pas encore fait
    try:
        fb_collection.create_index("fb_post_id", unique=True, sparse=True)
    except Exception:
        pass

    pages = _get_page_names()
    total_sent = 0
    total_skipped = 0
    total_errors = 0
    total_fetched = 0

    for page_name in pages:
        logger.info(f"📘 Scraping facebook.com/{page_name}...")
        posts = fetch_recent_posts(page_name)
        total_fetched += len(posts)

        for post in posts:
            post_id = post.get("id", "")
            if not post_id:
                continue

            # Anti-doublon
            existing = fb_collection.find_one({"fb_post_id": post_id})
            if existing:
                total_skipped += 1
                continue

            text = post.get("text", "").strip()
            if not text or len(text) < 30:
                total_skipped += 1
                continue

            # Formater et envoyer
            telegram_text = _format_telegram_message(post, page_name)

            try:
                success = send_message(telegram_text, parse_mode="HTML", disable_preview=False)

                if success:
                    fb_collection.insert_one({
                        "fb_post_id": post_id,
                        "page_name": page_name,
                        "message_preview": text[:200],
                        "permalink": post.get("link", ""),
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                        "telegram_sent": True,
                    })
                    total_sent += 1
                    logger.info(f"✅ Post FB {post_id[:30]} envoyé sur Telegram")
                else:
                    total_errors += 1
                    logger.warning(f"❌ Échec envoi Telegram pour post FB {post_id[:30]}")

            except Exception as e:
                total_errors += 1
                logger.error(f"❌ Erreur envoi post FB {post_id[:30]}: {e}")

        # Pause entre les pages (politesse)
        if len(pages) > 1:
            time.sleep(FB_SCRAPE_DELAY)

    result = {
        "ok": True,
        "pages_scraped": len(pages),
        "fetched": total_fetched,
        "sent": total_sent,
        "skipped": total_skipped,
        "errors": total_errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"📘 Sync FB→TG terminée: {total_sent} envoyés, {total_skipped} ignorés, {total_errors} erreurs")
    return result
