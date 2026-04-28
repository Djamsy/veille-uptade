# backend/social_stats_scraper.py
"""
Scraping des commentaires RS propres du Conseil Départemental via Apify.

Architecture :
  - STATS (likes, vues, reach) → récupérées via Buffer API (gratuit, cf campaign_service.sync_buffer_stats)
  - COMMENTAIRES → récupérés via Apify (ce module) pour analyse sentiment/thématique par GPT

Plateformes prioritaires : Facebook, Instagram, TikTok.

Configuration :
  APIFY_API_TOKEN             — token API Apify (ou APIFY_TOKEN)
  CD971_INSTAGRAM_URL         — profil Instagram du CD971
  CD971_FACEBOOK_URL          — page Facebook du CD971
  CD971_TIKTOK_URL            — profil TikTok du CD971
"""

import os
import logging
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from difflib import SequenceMatcher

logger = logging.getLogger("veille.social_stats")

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "") or os.getenv("APIFY_TOKEN", "")

# Profils RS du CD971 — focus FB / Insta / TikTok
OWN_PROFILES = {
    "instagram": os.getenv("CD971_INSTAGRAM_URL", ""),
    "facebook": os.getenv("CD971_FACEBOOK_URL", ""),
    "tiktok": os.getenv("CD971_TIKTOK_URL", ""),
}

# Actors Apify par plateforme (corrigés avril 2026)
ACTORS = {
    "instagram": "apify/instagram-scraper",           # posts + comments (pas profile-scraper !)
    "facebook": "apify/facebook-posts-scraper",        # posts + comments
    "tiktok": "clockworks/tiktok-profile-scraper",     # profil + vidéos
}


def is_configured() -> bool:
    return bool(APIFY_TOKEN) and any(OWN_PROFILES.values())


def _get_db():
    from backend.db import get_db
    return get_db()


# ── Apify runner ─────────────────────────────────────────

def _run_actor(actor_id: str, run_input: Dict, timeout: int = 120) -> List[Dict]:
    """Lance un actor Apify sync et retourne les items."""
    safe_id = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{safe_id}/run-sync-get-dataset-items?token={APIFY_TOKEN}&timeout={timeout}"

    try:
        payload = json.dumps(run_input).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", []) or data.get("data", []) or []
            return []
    except Exception as e:
        logger.error(f"Apify {actor_id}: {e}")
        return []


# ── Scrapers par plateforme ──────────────────────────────

def _scrape_instagram() -> List[Dict]:
    """Scrape les posts Instagram via apify/instagram-scraper.

    Utilise directUrls + resultsType=posts pour récupérer les posts récents
    avec commentaires.
    """
    url = OWN_PROFILES.get("instagram", "")
    if not url:
        return []

    items = _run_actor(ACTORS["instagram"], {
        "directUrls": [url],
        "resultsType": "posts",
        "resultsLimit": 20,
        "addParentData": False,
    })

    posts = []
    for item in items:
        comments_raw = item.get("latestComments") or item.get("comments") or []
        posts.append({
            "platform": "instagram",
            "external_id": item.get("id") or item.get("shortCode") or "",
            "text": item.get("caption") or item.get("alt") or "",
            "url": item.get("url") or item.get("webLink") or "",
            "media_url": item.get("displayUrl") or item.get("videoUrl") or "",
            "media_type": "video" if item.get("isVideo") or item.get("type") == "Video" else "photo",
            "published_at": item.get("timestamp") or item.get("takenAtTimestamp") or "",
            "stats": {
                "likes": _safe_int(item.get("likesCount") or item.get("likes")),
                "comments": _safe_int(item.get("commentsCount")),
                "views": _safe_int(item.get("videoViewCount") or item.get("videoPlayCount") or item.get("playCount")),
            },
            "comments": [
                {
                    "author": c.get("ownerUsername") or c.get("owner", {}).get("username", "") if isinstance(c, dict) else "",
                    "text": c.get("text", "") if isinstance(c, dict) else str(c),
                    "likes": _safe_int(c.get("likesCount", 0)) if isinstance(c, dict) else 0,
                }
                for c in (comments_raw[:30] if isinstance(comments_raw, list) else [])
            ],
        })
    return posts


def _scrape_facebook() -> List[Dict]:
    """Scrape les posts Facebook via apify/facebook-posts-scraper."""
    url = OWN_PROFILES.get("facebook", "")
    if not url:
        return []

    items = _run_actor(ACTORS["facebook"], {
        "startUrls": [{"url": url}],
        "resultsLimit": 20,
        "commentsMode": "RANKED_THREADED",
        "maxComments": 30,
    })

    posts = []
    for item in items:
        comments_raw = item.get("topComments") or item.get("comments_full") or item.get("comments") or []
        posts.append({
            "platform": "facebook",
            "external_id": item.get("postId", "") or item.get("id", ""),
            "text": item.get("text", "") or item.get("message", ""),
            "url": item.get("url", "") or item.get("postUrl", ""),
            "media_url": item.get("fullPicture", "") or item.get("videoUrl", ""),
            "media_type": "video" if item.get("videoUrl") else "photo",
            "published_at": item.get("time", "") or item.get("timestamp", ""),
            "stats": {
                "likes": _safe_int(item.get("likesCount") or item.get("likes")),
                "comments": _safe_int(item.get("commentsCount") or item.get("comments")),
                "shares": _safe_int(item.get("sharesCount") or item.get("shares")),
            },
            "comments": [
                {
                    "author": c.get("profileName") or c.get("name", "") if isinstance(c, dict) else "",
                    "text": c.get("text", "") if isinstance(c, dict) else str(c),
                    "likes": _safe_int(c.get("likesCount", 0)) if isinstance(c, dict) else 0,
                }
                for c in (comments_raw[:30] if isinstance(comments_raw, list) else [])
            ],
        })
    return posts


def _scrape_tiktok() -> List[Dict]:
    """Scrape les vidéos TikTok via clockworks/tiktok-profile-scraper."""
    url = OWN_PROFILES.get("tiktok", "")
    if not url:
        return []

    # Extraire le username depuis l'URL
    username = url.rstrip("/").split("/")[-1].lstrip("@")

    items = _run_actor(ACTORS["tiktok"], {
        "profiles": [username],
        "resultsPerPage": 20,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
    }, timeout=180)

    posts = []
    for item in items:
        comments_raw = item.get("comments") or []
        posts.append({
            "platform": "tiktok",
            "external_id": item.get("id") or item.get("videoId") or "",
            "text": item.get("text") or item.get("desc") or item.get("description") or "",
            "url": item.get("webVideoUrl") or item.get("url") or "",
            "media_url": item.get("videoUrl") or item.get("coverUrl") or "",
            "media_type": "video",
            "published_at": item.get("createTimeISO") or item.get("createTime") or "",
            "stats": {
                "likes": _safe_int(item.get("diggCount") or item.get("likes") or item.get("likesCount")),
                "comments": _safe_int(item.get("commentCount") or item.get("comments")),
                "shares": _safe_int(item.get("shareCount") or item.get("shares")),
                "views": _safe_int(item.get("playCount") or item.get("views")),
            },
            "comments": [
                {
                    "author": c.get("uniqueId") or c.get("user", {}).get("uniqueId", "") if isinstance(c, dict) else "",
                    "text": c.get("text", "") if isinstance(c, dict) else str(c),
                    "likes": _safe_int(c.get("diggCount", 0)) if isinstance(c, dict) else 0,
                }
                for c in (comments_raw[:30] if isinstance(comments_raw, list) else [])
            ],
        })
    return posts


def _safe_int(val) -> int:
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


# ── Matching scrapé → base ───────────────────────────────

def _match_to_db_post(scraped: Dict, db_posts: List[Dict]) -> Optional[Dict]:
    """Match un post scrapé avec un post existant dans campaign_posts."""
    s_text = scraped.get("text", "").strip()[:200].lower()

    for dbp in db_posts:
        # Match par external_id
        if scraped.get("external_id") and dbp.get("platform_post_id") == scraped["external_id"]:
            return dbp
        # Match par URL
        if scraped.get("url") and dbp.get("url") == scraped["url"]:
            return dbp
        # Match par texte similaire
        db_text = (dbp.get("title", "") + " " + dbp.get("body", "")).strip()[:200].lower()
        if s_text and db_text and SequenceMatcher(None, s_text, db_text).ratio() >= 0.55:
            return dbp

    return None


def _create_external_post(scraped: Dict, db) -> str:
    """Crée un post en base pour un post publié hors bot."""
    from backend.campaign_service import detect_campaign

    text = scraped.get("text", "")
    lines = text.strip().split('\n')
    title = lines[0][:100] if lines else "Post externe"
    body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
    hashtags = re.findall(r'#(\w+)', text)

    campaign = detect_campaign(text)
    campaign_name = campaign.get("name", "Institutionnel") if campaign else "Institutionnel"
    campaign_id = str(campaign.get("_id", "")) if campaign else ""

    post = {
        "title": title,
        "body": body,
        "hashtags": hashtags,
        "media_url": scraped.get("media_url", ""),
        "media_type": scraped.get("media_type", "photo"),
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "platform": scraped["platform"],
        "platform_post_id": scraped.get("external_id", ""),
        "url": scraped.get("url", ""),
        "stats": scraped.get("stats", {}),
        "platform_stats": {scraped["platform"]: scraped.get("stats", {})},
        "comments_scraped": scraped.get("comments", []),
        "published_at": scraped.get("published_at", datetime.now(timezone.utc).isoformat()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "apify_own_scrape",
        "telegram_user": "",
        "buffer_ids": [],
    }

    result = db["campaign_posts"].insert_one(post)
    logger.info(f"📥 Post externe créé ({scraped['platform']}): '{title[:50]}'")
    return str(result.inserted_id)


def _update_post_stats(post_id, scraped: Dict, db):
    """Met à jour les stats et commentaires d'un post existant."""
    from bson import ObjectId

    platform = scraped["platform"]
    stats = scraped.get("stats", {})
    comments = scraped.get("comments", [])

    # Recalculer les stats agrégées
    post = db["campaign_posts"].find_one({"_id": ObjectId(post_id)})
    if not post:
        return

    all_ps = post.get("platform_stats", {})
    all_ps[platform] = stats

    total = {"likes": 0, "comments": 0, "views": 0, "shares": 0}
    for ps in all_ps.values():
        for k in total:
            total[k] += (ps.get(k, 0) or 0)

    update = {
        f"platform_stats.{platform}": stats,
        "stats": total,
        "stats_updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Mettre à jour les commentaires (priorité Apify car plus riches)
    if comments:
        update["comments_scraped"] = comments
        update["comments_scraped_at"] = datetime.now(timezone.utc).isoformat()

    db["campaign_posts"].update_one({"_id": ObjectId(post_id)}, {"$set": update})


def _update_campaign_totals(db):
    """Recalcule les totaux par campagne."""
    from bson import ObjectId

    for camp in db["campaigns"].find({}, {"_id": 1}):
        cid = str(camp["_id"])
        posts = list(db["campaign_posts"].find({"campaign_id": cid}, {"stats": 1}))
        totals = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
        for p in posts:
            for k in totals:
                totals[k] += (p.get("stats", {}).get(k, 0) or 0)

        db["campaigns"].update_one(
            {"_id": camp["_id"]},
            {"$set": {
                "total_views": totals["views"],
                "total_likes": totals["likes"],
                "total_comments": totals["comments"],
                "total_shares": totals["shares"],
                "total_posts": len(posts),
                "stats_updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )


# ── Configuration suivi des commentaires ──────────────────
COMMENT_TRACKING_DAYS = int(os.getenv("COMMENT_TRACKING_DAYS", "14"))


# ── Scraping ciblé (post spécifique) ─────────────────────

def scrape_single_post(post_id: str) -> Dict[str, Any]:
    """Scrape les commentaires d'un post spécifique (appel manuel, cas viral)."""
    if not APIFY_TOKEN:
        return {"ok": False, "error": "APIFY_TOKEN non configuré"}

    from bson import ObjectId
    db = _get_db()

    try:
        post = db["campaign_posts"].find_one({"_id": ObjectId(post_id)})
    except Exception:
        return {"ok": False, "error": "ID de post invalide"}

    if not post:
        return {"ok": False, "error": "Post non trouvé"}

    # Déterminer la plateforme du post
    platform = post.get("platform", "")
    post_url = post.get("url", "")

    if not platform:
        ps = post.get("platform_stats", {})
        if ps:
            platform = list(ps.keys())[0]

    if not platform and post_url:
        if "instagram.com" in post_url:
            platform = "instagram"
        elif "facebook.com" in post_url:
            platform = "facebook"
        elif "tiktok.com" in post_url:
            platform = "tiktok"

    if not platform:
        return {"ok": False, "error": "Plateforme non identifiable"}

    scraper_map = {
        "instagram": _scrape_instagram,
        "facebook": _scrape_facebook,
        "tiktok": _scrape_tiktok,
    }

    scraper = scraper_map.get(platform)
    if not scraper:
        return {"ok": False, "error": f"Scraping non supporté pour {platform}"}

    if not OWN_PROFILES.get(platform):
        return {"ok": False, "error": f"CD971_{platform.upper()}_URL non configurée"}

    logger.info(f"🔍 Scraping ciblé pour post {post_id} ({platform})")
    scraped_posts = scraper()

    # Matcher avec le post demandé
    db_posts = [post]
    for sp in scraped_posts:
        match = _match_to_db_post(sp, db_posts)
        if match:
            _update_post_stats(post_id, sp, db)
            logger.info(f"✅ Stats mises à jour pour post {post_id}: {sp.get('stats', {})}")
            return {
                "ok": True,
                "post_id": post_id,
                "platform": platform,
                "stats": sp.get("stats", {}),
                "comments_count": len(sp.get("comments", [])),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

    return {"ok": False, "error": f"Post non trouvé dans le scraping {platform}"}


# ── Job principal (appelé par le scheduler) ──────────────

def scrape_own_social_stats() -> Dict[str, Any]:
    """Scrape les RS propres du CD971 — focus sur les commentaires.

    Les stats (likes, vues, reach) sont gérées par Buffer sync.
    Apify récupère les commentaires + stats complémentaires.

    - Posts existants → mise à jour stats + commentaires
    - Posts inconnus  → création comme post externe
    - Totaux campagnes recalculés à la fin
    """
    if not is_configured():
        logger.warning("Social stats scraper non configuré (APIFY_TOKEN + CD971_*_URL)")
        return {"ok": False, "error": "not_configured"}

    db = _get_db()
    results = {
        "ok": True, "platforms": {}, "updated": 0, "created": 0,
        "comment_tracking_days": COMMENT_TRACKING_DAYS,
    }

    # Posts récents en base (60 jours pour le matching)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    db_posts = list(db["campaign_posts"].find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 1, "title": 1, "body": 1, "platform_post_id": 1, "url": 1,
         "platform_stats": 1, "stats": 1, "created_at": 1}
    ))

    scrapers = {
        "instagram": _scrape_instagram,
        "facebook": _scrape_facebook,
        "tiktok": _scrape_tiktok,
    }

    for platform, fn in scrapers.items():
        if not OWN_PROFILES.get(platform):
            continue

        logger.info(f"🔍 Scraping commentaires {platform}...")
        try:
            scraped_posts = fn()
            pstats = {"scraped": len(scraped_posts), "updated": 0, "created": 0}

            for sp in scraped_posts:
                match = _match_to_db_post(sp, db_posts)
                if match:
                    _update_post_stats(match["_id"], sp, db)
                    pstats["updated"] += 1
                    results["updated"] += 1
                else:
                    _create_external_post(sp, db)
                    pstats["created"] += 1
                    results["created"] += 1

            results["platforms"][platform] = pstats
            logger.info(f"✅ {platform}: {pstats['updated']} MAJ, {pstats['created']} créés, {sum(len(sp.get('comments', [])) for sp in scraped_posts)} commentaires")

        except Exception as e:
            logger.error(f"❌ {platform}: {e}")
            results["platforms"][platform] = {"error": str(e)}

    # Recalculer les totaux campagnes
    _update_campaign_totals(db)

    logger.info(f"📊 Scraping terminé: {results['updated']} MAJ, {results['created']} créés")
    return results
