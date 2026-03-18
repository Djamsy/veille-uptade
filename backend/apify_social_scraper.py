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

    @staticmethod
    def _safe_int(val) -> int:
        """Extrait un entier depuis un champ Apify qui peut être int, str, list, dict ou None."""
        if val is None:
            return 0
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return 0
        if isinstance(val, list):
            return len(val)  # liste de commentaires → compter
        if isinstance(val, dict):
            # dict avec un champ 'count' ou 'summary'
            return int(val.get("count") or val.get("total_count") or val.get("summary", {}).get("total_count", 0) or 0)
        return 0

    # =========================
    # Run un Actor Apify et récupère les résultats
    # =========================
    def _run_actor(self, actor_id: str, run_input: dict, timeout_secs: int = 300) -> List[Dict]:
        """Lance un Actor Apify en mode synchrone et retourne les résultats."""
        if not APIFY_TOKEN:
            logger.warning("⚠️ APIFY_TOKEN non configuré")
            return []

        # Apify API exige ~ au lieu de / dans les actor IDs pour les chemins URL
        safe_actor_id = actor_id.replace("/", "~")
        url = f"{self.api_base}/acts/{safe_actor_id}/run-sync-get-dataset-items"
        params = {"token": APIFY_TOKEN, "timeout": timeout_secs}
        headers = {"Content-Type": "application/json"}

        try:
            logger.info(f"🚀 Lancement Actor {actor_id} avec input: {list(run_input.keys())}")
            logger.debug(f"   Input complet: {run_input}")
            resp = requests.post(url, json=run_input, params=params, headers=headers, timeout=timeout_secs + 30)

            logger.info(f"   {actor_id}: HTTP {resp.status_code} — Content-Length: {len(resp.content)}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    logger.error(f"❌ {actor_id}: réponse non-JSON — {resp.text[:300]}")
                    return []

                if isinstance(data, list):
                    logger.info(f"✅ {actor_id}: {len(data)} résultats")
                    return data
                elif isinstance(data, dict):
                    # Certains actors retournent un objet avec une clé 'items' ou 'data'
                    items = data.get("items") or data.get("data") or []
                    if items:
                        logger.info(f"✅ {actor_id}: {len(items)} résultats (via clé items/data)")
                        return items
                    # Si c'est un objet d'erreur
                    if data.get("error") or data.get("status") == "FAILED":
                        logger.error(f"❌ {actor_id}: Actor échoué — {data.get('error', data.get('statusMessage', str(data)[:300]))}")
                        return []
                    logger.warning(f"⚠️ {actor_id}: réponse dict inattendue — clés: {list(data.keys())[:10]}")
                    return []
                else:
                    logger.warning(f"⚠️ {actor_id}: type réponse inattendu: {type(data)}")
                    return []

            elif resp.status_code == 402:
                logger.error(f"❌ {actor_id}: crédits Apify insuffisants (402)")
                return []
            elif resp.status_code == 400:
                logger.error(f"❌ {actor_id}: Bad Request (400) — input invalide? Réponse: {resp.text[:500]}")
                return []
            elif resp.status_code == 404:
                logger.error(f"❌ {actor_id}: Actor introuvable (404) — vérifier l'ID")
                return []
            elif resp.status_code == 408:
                logger.error(f"❌ {actor_id}: Timeout côté Apify (408)")
                return []
            else:
                logger.error(f"❌ {actor_id}: HTTP {resp.status_code} — {resp.text[:500]}")
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
            "onlyPostsNewerThan": "2 days",  # Limiter aux posts récents
            # Facebook bloque les IPs datacenter → proxy résidentiel obligatoire
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }

        items = self._run_actor(ACTORS["facebook"], run_input)
        saved = 0
        updated = 0

        for item in items:
            try:
                text = item.get("text") or item.get("message") or ""
                author = item.get("pageName") or item.get("userName") or "unknown"
                posted_at = item.get("time") or item.get("timestamp") or ""
                post_url = item.get("url") or item.get("postUrl") or ""

                ph = self._post_hash("facebook", text, author, posted_at)
                likes = self._safe_int(item.get("likesCount") or item.get("likes"))
                comments = self._safe_int(item.get("commentsCount") or item.get("comments"))
                shares = self._safe_int(item.get("sharesCount") or item.get("shares"))

                doc = {
                    "platform": "facebook",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": likes,
                    "comments": comments,
                    "shares": shares,
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                # Upsert: met à jour si déjà existant, insère sinon
                result = self.collection.update_one(
                    {"post_hash": ph},
                    {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(TZ)}},
                    upsert=True,
                )
                if result.upserted_id:
                    saved += 1
                elif result.modified_count > 0:
                    updated += 1
            except Exception as e:
                logger.warning(f"⚠️ FB save error: {e}")

        logger.info(f"📘 Facebook: {saved} nouveaux + {updated} mis à jour / {len(items)} récupérés")
        return {"platform": "facebook", "fetched": len(items), "saved": saved, "updated": updated}

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
            "searchType": "hashtag",
            # Instagram bloque les IPs datacenter → proxy résidentiel obligatoire
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }

        items = self._run_actor(ACTORS["instagram"], run_input)
        saved = 0
        updated = 0

        for item in items:
            try:
                text = item.get("caption") or ""
                author = item.get("ownerUsername") or item.get("owner", {}).get("username", "unknown")
                posted_at = item.get("timestamp") or item.get("takenAtTimestamp") or ""
                post_url = item.get("url") or item.get("displayUrl") or ""

                ph = self._post_hash("instagram", text, author, str(posted_at))
                likes = self._safe_int(item.get("likesCount") or item.get("likes"))
                comments = self._safe_int(item.get("commentsCount") or item.get("comments"))

                doc = {
                    "platform": "instagram",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": likes,
                    "comments": comments,
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                result = self.collection.update_one(
                    {"post_hash": ph},
                    {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(TZ)}},
                    upsert=True,
                )
                if result.upserted_id:
                    saved += 1
                elif result.modified_count > 0:
                    updated += 1
            except Exception as e:
                logger.warning(f"⚠️ IG save error: {e}")

        logger.info(f"📸 Instagram: {saved} nouveaux + {updated} mis à jour / {len(items)} récupérés")
        return {"platform": "instagram", "fetched": len(items), "saved": saved, "updated": updated}

    # =========================
    # Twitter / X
    # =========================
    def scrape_twitter(self) -> Dict[str, Any]:
        """Scrape mots-clés + comptes Twitter/X en un seul run batché."""
        run_input = {
            "searchTerms": TWITTER_KEYWORDS,
            "twitterHandles": TWITTER_ACCOUNTS,
            "maxItems": 100,
            "sort": "Latest",
            # Proxy résidentiel pour fiabilité
            "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }

        items = self._run_actor(ACTORS["twitter"], run_input, timeout_secs=300)
        saved = 0
        updated = 0

        for item in items:
            try:
                # Tweet Scraper V2 peut retourner des formats variés
                text = (item.get("full_text") or item.get("text")
                        or item.get("tweet_text") or item.get("content") or "")
                # Champ auteur selon version de l'actor
                author = (item.get("author", {}).get("userName", "") if isinstance(item.get("author"), dict)
                          else item.get("user", {}).get("screen_name", "") if isinstance(item.get("user"), dict)
                          else item.get("author") or item.get("screen_name") or "unknown")
                posted_at = item.get("created_at") or item.get("createdAt") or item.get("date") or ""
                tweet_id = str(item.get("id_str") or item.get("id") or item.get("tweetId") or "")
                post_url = item.get("url") or item.get("tweetUrl") or ""
                if not post_url and tweet_id and author:
                    post_url = f"https://x.com/{author}/status/{tweet_id}"

                ph = self._post_hash("twitter", text, author, str(posted_at))
                likes = self._safe_int(item.get("likeCount") or item.get("favorite_count") or item.get("likes"))
                retweets = self._safe_int(item.get("retweetCount") or item.get("retweet_count") or item.get("retweets"))
                replies = self._safe_int(item.get("replyCount") or item.get("reply_count") or item.get("replies"))

                doc = {
                    "platform": "twitter",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                    "comments": replies,  # Twitter: replies = comments
                    "scraped_at": datetime.now(TZ),
                    "raw": item,
                }
                result = self.collection.update_one(
                    {"post_hash": ph},
                    {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(TZ)}},
                    upsert=True,
                )
                if result.upserted_id:
                    saved += 1
                elif result.modified_count > 0:
                    updated += 1
            except Exception as e:
                logger.warning(f"⚠️ TW save error: {e}")

        logger.info(f"🐦 Twitter: {saved} nouveaux + {updated} mis à jour / {len(items)} récupérés")
        return {"platform": "twitter", "fetched": len(items), "saved": saved, "updated": updated}

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

        # Enrichir les nouveaux posts via IA
        enriched = 0
        if total_saved > 0:
            enriched = self.enrich_new_posts()

        logger.info(f"📊 Scraping social terminé: {total_saved} nouveaux posts, {enriched} enrichis par IA")
        return {"success": True, "total_saved": total_saved, "enriched": enriched, "platforms": results, "timestamp": datetime.now(TZ).isoformat()}

    # =========================
    # Enrichissement IA des posts
    # =========================
    def enrich_new_posts(self, limit: int = 50) -> int:
        """Enrichit les posts non encore analysés par IA (batch de 15)."""
        if self.collection is None:
            return 0

        try:
            try:
                from backend.ai_groq_service import enrich_social_posts_batch
            except ImportError:
                from ai_groq_service import enrich_social_posts_batch
        except Exception:
            logger.warning("⚠️ enrich_social_posts_batch non disponible")
            return 0

        # Posts non enrichis
        unenriched = list(self.collection.find({
            "ai_enriched": {"$ne": True},
            "text": {"$exists": True, "$ne": ""},
        }).sort("scraped_at", -1).limit(limit))

        if not unenriched:
            return 0

        enriched_total = 0
        # Traiter par batch de 15
        for i in range(0, len(unenriched), 15):
            batch = unenriched[i:i + 15]
            enriched = enrich_social_posts_batch(batch, batch_size=15)

            for post in enriched:
                try:
                    self.collection.update_one(
                        {"_id": post["_id"]},
                        {"$set": {
                            "ai_enriched": post.get("ai_enriched", True),
                            "ai_relevant": post.get("ai_relevant", False),
                            "elected": post.get("elected", []),
                            "institutions": post.get("institutions", []),
                            "entities": post.get("entities", []),
                            "theme": post.get("theme", "general"),
                            "gravity_score": post.get("gravity_score", 0.1),
                            "ai_summary": post.get("ai_summary", ""),
                            "keywords_found": post.get("keywords_found", []),
                            "_analysis_method": post.get("_analysis_method", ""),
                        }}
                    )
                    enriched_total += 1
                except Exception as e:
                    logger.warning(f"⚠️ Update enriched post: {e}")

        logger.info(f"🧠 {enriched_total}/{len(unenriched)} posts enrichis par IA")
        return enriched_total

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
