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
# Test brut — 1 seule page Facebook, réponse raw
# =========================
@router.get("/test-raw")
async def social_test_raw(platform: str = Query("facebook", description="facebook, instagram, twitter")):
    """Teste un scrape minimal avec proxy résidentiel et retourne la réponse brute d'Apify."""
    import os, requests as req

    token = (os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN") or "").strip()
    if not token:
        return {"error": "APIFY_API_TOKEN non configuré"}

    # Config par plateforme
    configs = {
        "facebook": {
            "actor": "apify~facebook-posts-scraper",
            "input": {
                "startUrls": [{"url": "https://www.facebook.com/guadeloupe.la1ere"}],
                "resultsLimit": 3,
                "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
            },
        },
        "instagram": {
            "actor": "apify~instagram-scraper",
            "input": {
                "directUrls": ["https://www.instagram.com/guadeloupe.la1ere/"],
                "resultsLimit": 3,
                "resultsType": "posts",
                "searchType": "hashtag",
                "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
            },
        },
        "twitter": {
            "actor": "apidojo~tweet-scraper",
            "input": {
                "searchTerms": ["Guadeloupe"],
                "maxItems": 5,
                "sort": "Latest",
                "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
            },
        },
    }

    if platform not in configs:
        return {"error": f"Plateforme invalide: {platform}. Choix: facebook, instagram, twitter"}

    cfg = configs[platform]
    url = f"https://api.apify.com/v2/acts/{cfg['actor']}/run-sync-get-dataset-items"

    try:
        resp = req.post(
            url,
            json=cfg["input"],
            params={"token": token, "timeout": 120},
            headers={"Content-Type": "application/json"},
            timeout=180,
        )
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000]

        result = {
            "platform": platform,
            "actor": cfg["actor"],
            "http_status": resp.status_code,
            "content_length": len(resp.content),
            "response_type": type(body).__name__,
            "proxy_config": "RESIDENTIAL",
        }

        if isinstance(body, list):
            result["item_count"] = len(body)
            if body:
                result["first_item_keys"] = list(body[0].keys())[:15]
                # Aperçu du premier item (texte tronqué)
                first = body[0]
                preview = {}
                for k in ["text", "message", "caption", "full_text", "content"]:
                    if first.get(k):
                        preview["text_field"] = k
                        preview["text_preview"] = str(first[k])[:200]
                        break
                for k in ["pageName", "ownerUsername", "author", "user"]:
                    if first.get(k):
                        preview["author_field"] = k
                        preview["author"] = str(first[k])[:100] if not isinstance(first[k], dict) else str(first[k])[:200]
                        break
                result["first_item_preview"] = preview
            else:
                result["note"] = "Liste vide — l'actor a tourné mais n'a trouvé aucun post"
        elif isinstance(body, dict):
            result["response_keys"] = list(body.keys())[:15]
            if body.get("error"):
                result["apify_error"] = str(body.get("error"))[:500]
            if body.get("status"):
                result["run_status"] = body.get("status")
            result["response_preview"] = str(body)[:800]
        else:
            result["response_preview"] = str(body)[:800]

        return result

    except req.Timeout:
        return {"error": f"Timeout après 180s pour {platform}"}
    except Exception as e:
        return {"error": str(e)}


# =========================
# Diagnostic — test connexion Apify
# =========================
@router.get("/diagnostic")
async def social_diagnostic():
    """Teste la connexion Apify et retourne les infos de compte."""
    import os, requests as req
    token = (os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN") or "").strip()
    if not token:
        return {"success": False, "error": "APIFY_API_TOKEN non configuré"}

    diag = {"token_set": True, "token_preview": f"{token[:8]}..."}

    # Test: vérifier le compte Apify
    try:
        r = req.get(f"https://api.apify.com/v2/users/me?token={token}", timeout=10)
        if r.status_code == 200:
            user_data = r.json().get("data", {})
            diag["account"] = {
                "username": user_data.get("username"),
                "plan": user_data.get("plan", {}).get("id") if isinstance(user_data.get("plan"), dict) else user_data.get("plan"),
                "usageUsd": user_data.get("proxy", {}).get("usageUsd") if isinstance(user_data.get("proxy"), dict) else None,
            }
        else:
            diag["account_error"] = f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        diag["account_error"] = str(e)

    # Test: vérifier chaque actor
    actors = {
        "facebook": "apify/facebook-posts-scraper",
        "instagram": "apify/instagram-scraper",
        "twitter": "apidojo/tweet-scraper",
    }
    diag["actors"] = {}
    for name, actor_id in actors.items():
        try:
            safe_id = actor_id.replace("/", "~")
            r = req.get(f"https://api.apify.com/v2/acts/{safe_id}?token={token}", timeout=10)
            if r.status_code == 200:
                act = r.json().get("data", {})
                diag["actors"][name] = {
                    "id": actor_id,
                    "found": True,
                    "title": act.get("title", ""),
                    "isDeprecated": act.get("isDeprecated", False),
                }
            else:
                diag["actors"][name] = {"id": actor_id, "found": False, "http": r.status_code}
        except Exception as e:
            diag["actors"][name] = {"id": actor_id, "error": str(e)}

    return {"success": True, "diagnostic": diag}


# =========================
# Détail d'un post (pour le popup)
# =========================
@router.get("/posts/{post_id}")
async def social_post_detail(post_id: str):
    """Retourne le détail complet d'un post social, incluant le raw Apify."""
    from bson import ObjectId
    scraper = _get_scraper()
    if scraper.collection is None:
        raise HTTPException(status_code=503, detail="Mongo indisponible")
    try:
        doc = scraper.collection.find_one({"_id": ObjectId(post_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")
    if not doc:
        raise HTTPException(status_code=404, detail="Post introuvable")

    doc["_id"] = str(doc["_id"])
    if hasattr(doc.get("scraped_at"), "isoformat"):
        doc["scraped_at"] = doc["scraped_at"].isoformat()
    if hasattr(doc.get("first_seen"), "isoformat"):
        doc["first_seen"] = doc["first_seen"].isoformat()

    return {"post": doc}


# =========================
# Analyse sentiment global
# =========================
@router.get("/sentiment")
async def social_sentiment():
    """Analyse sentiment global des posts sociaux (7 derniers jours)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    import os

    scraper = _get_scraper()
    if scraper.collection is None:
        raise HTTPException(status_code=503, detail="Mongo indisponible")

    tz_name = (os.environ.get("TIMEZONE") or "America/Guadeloupe").strip()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    since_7d = now - timedelta(days=7)

    pipeline = [
        {"$match": {"scraped_at": {"$gte": since_7d}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "total_likes": {"$sum": {"$ifNull": ["$likes", 0]}},
            "total_comments": {"$sum": {"$ifNull": ["$comments", 0]}},
            "total_shares": {"$sum": {"$ifNull": ["$shares", 0]}},
            "total_retweets": {"$sum": {"$ifNull": ["$retweets", 0]}},
            "avg_gravity": {"$avg": {"$ifNull": ["$gravity_score", 0]}},
            "enriched_count": {"$sum": {"$cond": [{"$eq": ["$ai_enriched", True]}, 1, 0]}},
            "relevant_count": {"$sum": {"$cond": [{"$eq": ["$ai_relevant", True]}, 1, 0]}},
        }},
    ]
    agg = list(scraper.collection.aggregate(pipeline))
    global_stats = agg[0] if agg else {}

    # Sentiment par plateforme
    plat_pipeline = [
        {"$match": {"scraped_at": {"$gte": since_7d}}},
        {"$group": {
            "_id": "$platform",
            "count": {"$sum": 1},
            "likes": {"$sum": {"$ifNull": ["$likes", 0]}},
            "comments": {"$sum": {"$ifNull": ["$comments", 0]}},
            "avg_gravity": {"$avg": {"$ifNull": ["$gravity_score", 0]}},
        }},
    ]
    plat_agg = {d["_id"]: d for d in scraper.collection.aggregate(plat_pipeline)}

    # Top thèmes
    theme_pipeline = [
        {"$match": {"scraped_at": {"$gte": since_7d}, "theme": {"$exists": True, "$ne": "general", "$ne": ""}}},
        {"$group": {"_id": "$theme", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 8},
    ]
    themes = [{"theme": d["_id"], "count": d["count"]} for d in scraper.collection.aggregate(theme_pipeline)]

    # Top élus mentionnés
    elected_pipeline = [
        {"$match": {"scraped_at": {"$gte": since_7d}, "elected": {"$exists": True, "$ne": []}}},
        {"$unwind": "$elected"},
        {"$group": {"_id": "$elected", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top_elected = [{"name": d["_id"], "count": d["count"]} for d in scraper.collection.aggregate(elected_pipeline)]

    # Posts les plus engageants
    top_posts_cursor = scraper.collection.find(
        {"scraped_at": {"$gte": since_7d}},
        {"raw": 0}
    ).sort("likes", -1).limit(5)
    top_posts = []
    for doc in top_posts_cursor:
        doc["_id"] = str(doc["_id"])
        if hasattr(doc.get("scraped_at"), "isoformat"):
            doc["scraped_at"] = doc["scraped_at"].isoformat()
        top_posts.append(doc)

    return {
        "period": "7d",
        "global": {
            "total_posts": global_stats.get("total", 0),
            "total_engagement": (
                global_stats.get("total_likes", 0) +
                global_stats.get("total_comments", 0) +
                global_stats.get("total_shares", 0) +
                global_stats.get("total_retweets", 0)
            ),
            "total_likes": global_stats.get("total_likes", 0),
            "total_comments": global_stats.get("total_comments", 0),
            "total_shares": global_stats.get("total_shares", 0),
            "avg_gravity": round(global_stats.get("avg_gravity", 0), 2),
            "enriched": global_stats.get("enriched_count", 0),
            "relevant": global_stats.get("relevant_count", 0),
        },
        "by_platform": plat_agg,
        "top_themes": themes,
        "top_elected": top_elected,
        "top_posts": top_posts,
        "timestamp": now.isoformat(),
    }


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
        from backend.services.apify_social_scraper import (
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
