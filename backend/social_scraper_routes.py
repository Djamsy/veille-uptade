# backend/social_scraper_routes.py
"""
Routes API pour le scraping réseaux sociaux via Apify.
- GET  /api/social/stats        → stats par plateforme
- GET  /api/social/posts        → posts récents
- POST /api/social/scrape       → lancer un scrape manuel (toutes plateformes)
- POST /api/social/scrape/{platform} → scrape une seule plateforme
- GET  /api/social/config       → voir la config actuelle (comptes, hashtags, mots-clés)
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
import logging

logger = logging.getLogger("social_routes")
router = APIRouter(prefix="/social", tags=["social"])

_scraper = None


def set_scraper(scraper):
    global _scraper
    _scraper = scraper


def _get_scraper():
    if _scraper is None:
        raise HTTPException(status_code=503, detail="Service social non disponible")
    return _scraper


# =========================
# Stats
# =========================
@router.get("/stats")
async def social_stats():
    """Stats de scraping par plateforme."""
    scraper = _get_scraper()
    return scraper.get_stats()


# =========================
# Posts récents
# =========================
@router.get("/posts")
async def social_posts(
    platform: str = Query(None, description="facebook, instagram, twitter"),
    limit: int = Query(50, ge=1, le=200),
):
    """Posts récents (tous ou par plateforme)."""
    scraper = _get_scraper()
    posts = scraper.get_recent_posts(platform=platform, limit=limit)
    return {"posts": posts, "count": len(posts)}


# =========================
# Scrape manuel — toutes plateformes
# =========================
@router.post("/scrape")
async def social_scrape_all():
    """Lance un scraping batché sur FB + IG + X."""
    scraper = _get_scraper()
    if not scraper.is_ready():
        raise HTTPException(
            status_code=503,
            detail="APIFY_TOKEN non configuré ou Mongo indisponible. "
                   "Ajoutez APIFY_TOKEN dans les variables d'environnement Render."
        )
    result = scraper.scrape_all()
    return result


# =========================
# Scrape manuel — une plateforme
# =========================
@router.post("/scrape/{platform}")
async def social_scrape_single(platform: str):
    """Lance un scraping batché sur une seule plateforme."""
    scraper = _get_scraper()
    if not scraper.is_ready():
        raise HTTPException(status_code=503, detail="APIFY_TOKEN non configuré")

    if platform not in ("facebook", "instagram", "twitter"):
        raise HTTPException(status_code=400, detail="Plateforme invalide. Choix: facebook, instagram, twitter")

    method_map = {
        "facebook": scraper.scrape_facebook,
        "instagram": scraper.scrape_instagram,
        "twitter": scraper.scrape_twitter,
    }

    result = method_map[platform]()
    return result


# =========================
# Config actuelle
# =========================
@router.get("/config")
async def social_config():
    """Retourne la configuration actuelle des cibles de scraping."""
    try:
        from apify_social_scraper import (
            FACEBOOK_PAGES, INSTAGRAM_ACCOUNTS, INSTAGRAM_HASHTAGS,
            TWITTER_KEYWORDS, TWITTER_ACCOUNTS, APIFY_TOKEN,
        )
    except ImportError:
        from backend.apify_social_scraper import (
            FACEBOOK_PAGES, INSTAGRAM_ACCOUNTS, INSTAGRAM_HASHTAGS,
            TWITTER_KEYWORDS, TWITTER_ACCOUNTS, APIFY_TOKEN,
        )

    return {
        "apify_configured": bool(APIFY_TOKEN),
        "facebook": {
            "pages": FACEBOOK_PAGES,
            "count": len(FACEBOOK_PAGES),
        },
        "instagram": {
            "accounts": INSTAGRAM_ACCOUNTS,
            "hashtags": INSTAGRAM_HASHTAGS,
            "count": len(INSTAGRAM_ACCOUNTS) + len(INSTAGRAM_HASHTAGS),
        },
        "twitter": {
            "keywords": TWITTER_KEYWORDS,
            "accounts": TWITTER_ACCOUNTS,
            "count": len(TWITTER_KEYWORDS) + len(TWITTER_ACCOUNTS),
        },
    }
