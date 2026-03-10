# backend/apify_social_scraper.py
"""
Service de scraping réseaux sociaux via Apify — mode batché.
- 1 run/heure par plateforme (Facebook, Instagram, Twitter/X)
- Chaque run traite N comptes + N hashtags + N mots-clés en batch
- Résultats stockés en MongoDB (collection social_posts)
- Liaison automatique aux affaires existantes
"""

import os
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import certifi

logger = logging.getLogger("apify_social")
logger.setLevel(logging.INFO)

TZ_NAME = (os.environ.get("TIMEZONE") or "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TZ_NAME)
except Exception:
    TZ = ZoneInfo("UTC")

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or "mongodb://localhost:27017").strip()

# =========================
# Configuration des scrapers Apify (Actor IDs)
# =========================
ACTORS = {
    "facebook": "apify/facebook-posts-scraper",
    "instagram": "apify/instagram-scraper",
    "twitter": "apidojo/tweet-scraper",
}

# =========================
# Cibles de veille Guadeloupe
# =========================
FACEBOOK_PAGES = [
    "https://www.facebook.com/RCIGUADELOUPE971",
    "https://www.facebook.com/RCIMARTINIQUE972",
    "https://www.facebook.com/guadeloupe.la1ere",
    "https://www.facebook.com/franceantilles.guadeloupe",
    "https://www.facebook.com/kaaborguadeloupe",
    "https://www.facebook.com/lInformGuadeloupe",
    # Élus / Institutions
    "https://www.facebook.com/RegionGuadeloupe",
    "https://www.facebook.com/DepartementGuadeloupe",
    "https://www.facebook.com/VillePointeaPitre",
    "https://www.facebook.com/VilleBasseterre",
    "https://www.facebook.com/PrefetGuadeloupe",
]

INSTAGRAM_ACCOUNTS = [
    "rci_guadeloupe",
    "guadeloupe.la1ere",
    "franceantilles_guadeloupe",
    "kaaborguadeloupe",
    "region_guadeloupe",
    "prefecture971",
]

INSTAGRAM_HASHTAGS = [
    "guadeloupe",
    "guadeloupe971",
    "gwada",
    "971",
    "pointeapitre",
    "basseterre",
    "saintfrancois",
    "lesabymes",
]

TWITTER_KEYWORDS = [
    "Guadeloupe",
    "SMGEAG",
    "eau Guadeloupe",
    "SDIS 971",
    "Guy Losbar",
    "Ary Chalus",
    "Eric Jalton",
    "CHU Guadeloupe",
    "Préfet Guadeloupe",
    "Région Guadeloupe",
    "Département Guadeloupe",
    "coupure eau 971",
    "grève Guadeloupe",
    "cyclone Guadeloupe",
    "RCI Guadeloupe",
    "Guadeloupe 1ère",
    "France Antilles Guadeloupe",
]

TWITTER_ACCOUNTS = [
    "Abororigines",
    "RCI_GP",
    "Gpe_1ere",
    "FranceAntilles",
    "Prefet971",
    "RegionGpe",
]


# =========================
# Service principal
# =========================
class ApifySocialScraper:

    def __init__(self):
        self.api_base = "https://api.apify.com/v2"
        self.db = None
        self.collection = None
        self._connect_mongo()

    def _connect_mongo(self):
        try:
            if MONGO_URL.startswith("mongodb+srv"):
                client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=30000)
            else:
                client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=30000)
            client.admin.command("ping")
            try:
                self.db = client.get_default_database()
            except Exception:
                self.db = client["veille_media"]
            # Même collection que affair_lifecycle_service.social
            self.collection = self.db["social_media_posts"]
            # Index unique pour éviter les doublons
            self.collection.create_index("post_hash", unique=True, sparse=True)
            self.collection.create_index("platform")
            self.collection.create_index("scraped_at")
            self.collection.create_index([("platform", 1), ("scraped_at", -1)])
            logger.info("🔗 Apify Social: Mongo connecté")
        except Exception as e:
            logger.error(f"💥 Apify Social: Mongo indisponible: {e}")

    def is_ready(self) -> bool:
        return bool(APIFY_TOKEN) and self.collection is not None

    def _post_hash(self, platform: str, text: str, author: str, posted_at: str) -> str:
        raw = f"{platform}:{author}:{text[:200]}:{posted_at}"
        return hashlib.md5(raw.encode()).hexdigest()

    # =========================
    # Run un Actor Apify et récupère les résultats
    # =========================
    def _run_actor(self, actor_id: str, run_input: dict, timeout_secs: int = 300) -> List[Dict]:
        """Lance un Actor Apify en mode synchrone et retourne les résultats."""
        if not APIFY_TOKEN:
            logger.warning("⚠️ APIFY_TOKEN non configuré")
            return []

        url = f"{self.api_base}/acts/{actor_id}/run-sync-get-dataset-items"
        params = {"token": APIFY_TOKEN, "timeout": timeout_secs}
        headers = {"Content-Type": "application/json"}

        try:
            logger.info(f"🚀 Lancement Actor {actor_id}...")
            resp = requests.post(url, json=run_input, params=params, headers=headers, timeout=timeout_secs + 30)

            if resp.status_code == 200:
                items = resp.json() if isinstance(resp.json(), list) else []
                logger.info(f"✅ {actor_id}: {len(items)} résultats")
                return items
            elif resp.status_code == 402:
                logger.error(f"❌ {actor_id}: crédits Apify insuffisants (402)")
                return []
            else:
                logger.error(f"❌ {actor_id}: HTTP {resp.status_code} — {resp.text[:200]}")
                return []

        except requests.Timeout:
            logger.error(f"⏰ {actor_id}: timeout après {timeout_secs}s")
            return []
        except Exception as e:
            logger.error(f"💥 {actor_id}: {e}")
            return []

    # =========================
    # Facebook
    # =========================
    def scrape_facebook(self) -> Dict[str, Any]:
        """Scrape toutes les pages Facebook en un seul run batché."""
        run_input = {
            "startUrls": [{"url": u} for u in FACEBOOK_PAGES],
            "resultsLimit": 10,  # 10 posts max par page
        }

        items = self._run_actor(ACTORS["facebook"], run_input)
        saved = 0

        for item in items:
            try:
                text = item.get("text") or item.get("message") or ""
                author = item.get("pageName") or item.get("userName") or "unknown"
                posted_at = item.get("time") or item.get("timestamp") or ""
                post_url = item.get("url") or item.get("postUrl") or ""

                doc = {
                    "platform": "facebook",
                    "post_hash": self._post_hash("facebook", text, author, posted_at),
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": item.get("likes") or item.get("likesCount") or 0,
                    "comments": item.get("comments") or item.get("commentsCount") or 0,
                    "shares": item.get("shares") or item.get("sharesCount") or 0,
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                self.collection.insert_one(doc)
                saved += 1
            except DuplicateKeyError:
                pass  # Déjà vu
            except Exception as e:
                logger.warning(f"⚠️ FB save error: {e}")

        logger.info(f"📘 Facebook: {saved} nouveaux posts / {len(items)} récupérés")
        return {"platform": "facebook", "fetched": len(items), "saved": saved}

    # =========================
    # Instagram
    # =========================
    def scrape_instagram(self) -> Dict[str, Any]:
        """Scrape comptes + hashtags Instagram en un seul run batché."""
        direct_urls = [f"https://www.instagram.com/{a}/" for a in INSTAGRAM_ACCOUNTS]
        hashtag_urls = [f"https://www.instagram.com/explore/tags/{h}/" for h in INSTAGRAM_HASHTAGS]

        run_input = {
            "directUrls": direct_urls + hashtag_urls,
            "resultsLimit": 10,
            "resultsType": "posts",
        }

        items = self._run_actor(ACTORS["instagram"], run_input)
        saved = 0

        for item in items:
            try:
                text = item.get("caption") or ""
                author = item.get("ownerUsername") or item.get("owner", {}).get("username", "unknown")
                posted_at = item.get("timestamp") or item.get("takenAtTimestamp") or ""
                post_url = item.get("url") or item.get("displayUrl") or ""

                doc = {
                    "platform": "instagram",
                    "post_hash": self._post_hash("instagram", text, author, str(posted_at)),
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": item.get("likesCount") or 0,
                    "comments": item.get("commentsCount") or 0,
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                self.collection.insert_one(doc)
                saved += 1
            except DuplicateKeyError:
                pass
            except Exception as e:
                logger.warning(f"⚠️ IG save error: {e}")

        logger.info(f"📸 Instagram: {saved} nouveaux posts / {len(items)} récupérés")
        return {"platform": "instagram", "fetched": len(items), "saved": saved}

    # =========================
    # Twitter / X
    # =========================
    def scrape_twitter(self) -> Dict[str, Any]:
        """Scrape mots-clés + comptes Twitter/X en un seul run batché."""
        # Combine keywords et comptes dans les search terms
        search_terms = TWITTER_KEYWORDS + [f"from:{a}" for a in TWITTER_ACCOUNTS]

        run_input = {
            "searchTerms": search_terms,
            "maxTweets": 100,
            "sort": "Latest",
        }

        items = self._run_actor(ACTORS["twitter"], run_input, timeout_secs=300)
        saved = 0

        for item in items:
            try:
                text = item.get("full_text") or item.get("text") or ""
                author = item.get("user", {}).get("screen_name", "") or item.get("author", "unknown")
                posted_at = item.get("created_at") or ""
                tweet_id = item.get("id_str") or item.get("id") or ""
                post_url = f"https://x.com/{author}/status/{tweet_id}" if tweet_id else ""

                doc = {
                    "platform": "twitter",
                    "post_hash": self._post_hash("twitter", text, author, str(posted_at)),
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": item.get("favorite_count") or item.get("likeCount") or 0,
                    "retweets": item.get("retweet_count") or item.get("retweetCount") or 0,
                    "replies": item.get("reply_count") or item.get("replyCount") or 0,
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                self.collection.insert_one(doc)
                saved += 1
            except DuplicateKeyError:
                pass
            except Exception as e:
                logger.warning(f"⚠️ TW save error: {e}")

        logger.info(f"🐦 Twitter: {saved} nouveaux posts / {len(items)} récupérés")
        return {"platform": "twitter", "fetched": len(items), "saved": saved}

    # =========================
    # Run all platforms (appelé par le scheduler)
    # =========================
    def scrape_all(self) -> Dict[str, Any]:
        """Lance le scraping batché sur les 3 plateformes."""
        if not self.is_ready():
            return {"success": False, "reason": "APIFY_TOKEN manquant ou Mongo indisponible"}

        results = {}
        total_saved = 0

        for platform, method in [
            ("facebook", self.scrape_facebook),
            ("instagram", self.scrape_instagram),
            ("twitter", self.scrape_twitter),
        ]:
            try:
                r = method()
                results[platform] = r
                total_saved += r.get("saved", 0)
            except Exception as e:
                logger.error(f"❌ Erreur scraping {platform}: {e}")
                results[platform] = {"platform": platform, "error": str(e)}

        logger.info(f"📊 Scraping social terminé: {total_saved} nouveaux posts au total")
        return {"success": True, "total_saved": total_saved, "platforms": results, "timestamp": datetime.now(TZ).isoformat()}

    # =========================
    # Stats
    # =========================
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les stats du scraping social."""
        if self.collection is None:
            return {"error": "Mongo indisponible"}

        now = datetime.now(TZ)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        stats = {}
        for platform in ["facebook", "instagram", "twitter"]:
            total = self.collection.count_documents({"platform": platform})
            recent_24h = self.collection.count_documents({"platform": platform, "scraped_at": {"$gte": last_24h}})
            recent_7d = self.collection.count_documents({"platform": platform, "scraped_at": {"$gte": last_7d}})

            # Dernier scrape
            last = self.collection.find_one({"platform": platform}, sort=[("scraped_at", -1)])
            last_scraped = last["scraped_at"].isoformat() if last and "scraped_at" in last else None

            stats[platform] = {
                "total": total,
                "last_24h": recent_24h,
                "last_7d": recent_7d,
                "last_scraped": last_scraped,
            }

        return {"stats": stats, "timestamp": now.isoformat()}

    def get_recent_posts(self, platform: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Retourne les posts récents."""
        if self.collection is None:
            return []

        query = {}
        if platform:
            query["platform"] = platform

        cursor = self.collection.find(query, {"raw": 0}).sort("scraped_at", -1).limit(limit)
        posts = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("scraped_at"), datetime):
                doc["scraped_at"] = doc["scraped_at"].isoformat()
            posts.append(doc)
        return posts


# Singleton
_scraper = None

def get_social_scraper() -> ApifySocialScraper:
    global _scraper
    if _scraper is None:
        _scraper = ApifySocialScraper()
    return _scraper
