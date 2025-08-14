# backend/social_routes.py
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body

try:
    from backend.social_media_service import social_scraper  # import absolu
except Exception:
    from social_media_service import social_scraper  # fallback si on lance depuis backend/

router = APIRouter()
logger = logging.getLogger("backend.social_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 social_routes loaded")

@router.get("/stats", tags=["social"])  # -> /api/social/stats
def get_social_stats():
    try:
        stats = social_scraper.get_posts_stats() or {}
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.exception("Erreur stats réseaux sociaux: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (stats)")

@router.post("/scrape-now", tags=["social"])  # -> /api/social/scrape-now
def scrape_now(payload: Dict[str, Any] = Body(default={})):
    try:
        keywords = payload.get("keywords") if isinstance(payload, dict) else None
        if keywords is not None and not isinstance(keywords, list):
            raise HTTPException(status_code=400, detail="'keywords' doit être une liste de chaînes")
        results = social_scraper.start_scrape(keywords)
        return {"success": True, **results}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur scrape-now: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (scrape-now)")

@router.get("/search", tags=["social"])  # -> /api/social/search?q=...&limit=...
def search_posts(q: str = Query(..., description="Texte à chercher"),
                 limit: int = Query(40, ge=1, le=200)):
    try:
        res = social_scraper.search_posts(q, limit)
        return {"success": True, **res}
    except Exception as e:
        logger.exception("Erreur search: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (search)")

@router.get("/recent", tags=["social"])  # -> /api/social/recent?days=1&platform=twitter
def recent_posts(days: int = Query(1, ge=1, le=30), platform: Optional[str] = Query(None)):
    try:
        posts = social_scraper.get_recent_posts(days=days, platform=platform)
        return {"success": True, "days": days, "platform": platform, "posts": posts}
    except Exception as e:
        logger.exception("Erreur recent: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (recent)")

@router.post("/scrape-keyword", tags=["social"])  # -> /api/social/scrape-keyword
def scrape_keyword(payload: Dict[str, Any] = Body(default={})):  # accepte {"keywords": [...] } ou {"q": "..."} / {"keyword": "..."}
    try:
        keywords = None
        if isinstance(payload, dict):
            if isinstance(payload.get("keywords"), list):
                keywords = payload["keywords"]
            elif isinstance(payload.get("q"), str):
                keywords = [payload["q"]]
            elif isinstance(payload.get("keyword"), str):
                keywords = [payload["keyword"]]
        if not keywords:
            raise HTTPException(status_code=400, detail="Fournis 'keywords' (liste) ou 'q'/'keyword' (chaîne).")
        results = social_scraper.start_scrape(keywords)
        return {"success": True, **results}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur scrape-keyword (POST): %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (scrape-keyword POST)")

@router.get("/scrape-keyword", tags=["social"])  # -> /api/social/scrape-keyword?q=...
def scrape_keyword_get(q: str = Query(..., description="Mot-clé à scraper")):
    try:
        results = social_scraper.start_scrape([q])
        return {"success": True, **results}
    except Exception as e:
        logger.exception("Erreur scrape-keyword (GET): %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (scrape-keyword GET)")


@router.delete("/cleanup-demo", tags=["social"])  # -> /api/social/cleanup-demo
def cleanup_demo():
    try:
        deleted = social_scraper.clean_demo_data_from_db()
        return {"success": True, "deleted_demo_posts": deleted}
    except Exception as e:
        logger.exception("Erreur cleanup-demo: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (cleanup-demo)")


@router.get("/health", tags=["social"])  # -> /api/social/health
def health():
    try:
        stats = social_scraper.get_posts_stats() or {}
        return {"ok": True, "has_db": True, "stats_sample": stats}
    except Exception:
        return {"ok": False}