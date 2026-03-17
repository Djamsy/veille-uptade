import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Query, Body

# ✅ on force l’import depuis social_media_service (avec YouTube inclus)
try:
    from backend.social_media_service import social_scraper  # type: ignore
except Exception:
    from social_media_service import social_scraper  # type: ignore

router = APIRouter()
logger = logging.getLogger("backend.social_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 social_routes loaded (social_media_service)")

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
        # Sauvegarde en DB (assure que ça écrit bien)
        posts = (
            results.get("twitter", [])
            + results.get("facebook", [])
            + results.get("instagram", [])
            + results.get("news", [])
            + results.get("youtube", [])
        )
        saved = social_scraper.save_posts_to_db(posts)
        return {"success": True, "saved": saved, **results}
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
def scrape_keyword(payload: Dict[str, Any] = Body(default={})):  # {"keywords":[...]} ou {"q":"..."} / {"keyword":"..."}
    try:
        keywords: Optional[List[str]] = None
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
        posts = (
            results.get("twitter", [])
            + results.get("facebook", [])
            + results.get("instagram", [])
            + results.get("news", [])
            + results.get("youtube", [])
        )
        saved = social_scraper.save_posts_to_db(posts)
        return {"success": True, "saved": saved, **results}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erreur scrape-keyword (POST): %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne (scrape-keyword POST)")

@router.get("/scrape-keyword", tags=["social"])  # -> /api/social/scrape-keyword?q=...
def scrape_keyword_get(q: str = Query(..., description="Mot-clé à scraper")):
    try:
        results = social_scraper.start_scrape([q])
        posts = (
            results.get("twitter", [])
            + results.get("facebook", [])
            + results.get("instagram", [])
            + results.get("news", [])
            + results.get("youtube", [])
        )
        saved = social_scraper.save_posts_to_db(posts)
        return {"success": True, "saved": saved, **results}
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
