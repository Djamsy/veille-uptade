# backend/apify_social_scraper.py
"""
Service de scraping réseaux sociaux via Apify — optimisé coûts.
Cibles : médias Guadeloupe (Département, Canal 10, Gpe 1ère, RCI, La Pause Sans Filtre)
Plateformes : Facebook, Instagram, TikTok
Budget : < 30€/mois sur Apify

Optimisations coût :
- 3 runs/jour (7h, 13h, 19h) au lieu de 24
- Proxy datacenter par défaut (résidentiel seulement si bloqué)
- resultsLimit réduit (5 posts/compte → seuls les récents)
- Twitter/X supprimé (cher, peu pertinent Guadeloupe)
- TikTok via clockworks/tiktok-scraper (PPE $0.004/item)
"""

import os
import logging
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient, UpdateOne
from pymongo.errors import DuplicateKeyError, BulkWriteError
import certifi

logger = logging.getLogger("apify_social")
logger.setLevel(logging.INFO)

TZ_NAME = (os.environ.get("TIMEZONE") or "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TZ_NAME)
except Exception:
    TZ = ZoneInfo("UTC")

# Accepter les deux noms de variable : APIFY_API_TOKEN (utilisé partout ailleurs)
# ou APIFY_TOKEN (ancien nom, encore dans certaines routes).
APIFY_TOKEN = (os.environ.get("APIFY_API_TOKEN") or os.environ.get("APIFY_TOKEN") or "").strip()
MONGO_URL = (os.environ.get("MONGO_URL") or "mongodb://localhost:27017").strip()

# =========================
# Actors Apify
# =========================
ACTORS = {
    "facebook": "apify/facebook-posts-scraper",
    "instagram": "apify/instagram-scraper",
    "tiktok": "clockworks/tiktok-scraper",
}

# =========================
# Cibles de veille Guadeloupe — uniquement les comptes demandés
# =========================
FACEBOOK_PAGES = [
    # Médias
    "https://www.facebook.com/RCIGUADELOUPE971",
    "https://www.facebook.com/guadeloupe.la1ere",
    "https://www.facebook.com/canal10guadeloupe",
    "https://www.facebook.com/lapausesansfiltre",
    # Institutions
    "https://www.facebook.com/DepartementGuadeloupe",
]

INSTAGRAM_ACCOUNTS = [
    "rci_guadeloupe",
    "guadeloupe.la1ere",
    "canal10guadeloupe",
    "lapausesansfiltre",
    "departaborguadeloupe",
]

TIKTOK_ACCOUNTS = [
    "rci_guadeloupe",
    "guadeloupe1ere",
    "canal10guadeloupe",
    "lapausesansfiltre",
    "departementguadeloupe",
]

# Hashtags TikTok pour capter le buzz local
TIKTOK_HASHTAGS = [
    "guadeloupe",
    "971",
    "gwada",
]

# =========================
# Proxy configs — optimisées coût
# =========================
# Facebook bloque les datacenter → proxy SHADER (moins cher que RESIDENTIAL)
PROXY_FACEBOOK = {"useApifyProxy": True, "apifyProxyGroups": ["SHADER"]}
# Instagram et TikTok fonctionnent souvent sans proxy résidentiel
PROXY_LIGHT = {"useApifyProxy": True}


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
                client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(),
                                     serverSelectionTimeoutMS=15000, maxPoolSize=5)
            else:
                client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=15000, maxPoolSize=5)
            client.admin.command("ping")
            try:
                self.db = client.get_default_database()
            except Exception:
                self.db = client["veille_media"]
            self.collection = self.db["social_media_posts"]
            # Index unique pour éviter les doublons
            self.collection.create_index("post_hash", unique=True, sparse=True)
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
            return len(val)
        if isinstance(val, dict):
            return int(val.get("count") or val.get("total_count")
                       or val.get("summary", {}).get("total_count", 0) or 0)
        return 0

    # =========================
    # Run un Actor Apify
    # =========================
    def _run_actor(self, actor_id: str, run_input: dict, timeout_secs: int = 300) -> List[Dict]:
        """Lance un actor Apify avec retry exponentiel sur erreurs transitoires.

        Retry sur : 429 (rate limit), 5xx (server errors), network timeouts.
        PAS de retry sur : 401 (token), 402 (billing), 400/404 (input error).
        """
        if not APIFY_TOKEN:
            logger.warning("⚠️ APIFY_TOKEN non configuré")
            return []

        safe_actor_id = actor_id.replace("/", "~")
        url = f"{self.api_base}/acts/{safe_actor_id}/run-sync-get-dataset-items"
        params = {"token": APIFY_TOKEN, "timeout": timeout_secs}
        headers = {"Content-Type": "application/json"}

        max_attempts = 3
        # Backoff exponentiel : 2s, 8s, 32s. Le rate limit Apify se réinitialise
        # généralement en moins d'une minute.
        backoff_base = 2.0

        for attempt in range(1, max_attempts + 1):
            try:
                if attempt == 1:
                    logger.info(f"🚀 Actor {actor_id}")
                else:
                    logger.info(f"🔁 Actor {actor_id} (tentative {attempt}/{max_attempts})")

                resp = requests.post(
                    url, json=run_input, params=params,
                    headers=headers,
                    timeout=(10, timeout_secs + 30),  # (connect, read)
                )

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        logger.error(f"❌ {actor_id}: réponse non-JSON")
                        return []
                    if isinstance(data, list):
                        logger.info(f"✅ {actor_id}: {len(data)} résultats")
                        return data
                    if isinstance(data, dict):
                        items = data.get("items") or data.get("data") or []
                        if items:
                            logger.info(f"✅ {actor_id}: {len(items)} résultats")
                            return items
                        if data.get("error") or data.get("status") == "FAILED":
                            logger.error(f"❌ {actor_id}: échoué — {str(data)[:300]}")
                    return []

                # Erreurs définitives — pas de retry
                if resp.status_code == 401:
                    logger.error(
                        f"🔐 {actor_id}: ERREUR 401 — Token Apify invalide ou expiré.\n"
                        f"   Token utilisé: {APIFY_TOKEN[:12]}...\n"
                        f"   → Vérifiez APIFY_API_TOKEN dans vos variables d'environnement.\n"
                        f"   → Régénérez le token sur https://console.apify.com/account#/integrations"
                    )
                    return []
                if resp.status_code == 402:
                    logger.error(f"💰 {actor_id}: crédits insuffisants (402) — rechargez sur https://console.apify.com/billing")
                    return []
                if resp.status_code in (400, 404):
                    logger.error(f"❌ {actor_id}: HTTP {resp.status_code} (input error) — {resp.text[:300]}")
                    return []

                # Erreurs transitoires — retry
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else backoff_base * (4 ** (attempt - 1))
                    logger.warning(f"⏳ {actor_id}: rate limit 429, retry dans {delay:.1f}s ({attempt}/{max_attempts})")
                    if attempt < max_attempts:
                        time.sleep(delay)
                        continue
                    return []

                if 500 <= resp.status_code < 600 or resp.status_code == 408:
                    delay = backoff_base * (4 ** (attempt - 1))
                    logger.warning(f"⚠️ {actor_id}: HTTP {resp.status_code}, retry dans {delay:.1f}s ({attempt}/{max_attempts})")
                    if attempt < max_attempts:
                        time.sleep(delay)
                        continue
                    return []

                # Autres codes — log et abandon
                logger.error(f"❌ {actor_id}: HTTP {resp.status_code} — {resp.text[:200]}")
                return []

            except (requests.Timeout, requests.ConnectionError) as e:
                delay = backoff_base * (4 ** (attempt - 1))
                if attempt < max_attempts:
                    logger.warning(f"⏰ {actor_id}: {type(e).__name__}, retry dans {delay:.1f}s ({attempt}/{max_attempts})")
                    time.sleep(delay)
                    continue
                logger.error(f"⏰ {actor_id}: {type(e).__name__} après {max_attempts} tentatives")
                return []
            except Exception as e:
                logger.error(f"💥 {actor_id}: {e}")
                return []

        return []

    # =========================
    # Batch upsert — remplace les N × update_one par un bulk_write
    # =========================
    def _bulk_upsert(self, docs: List[Dict]) -> tuple:
        """Upsert en batch. Retourne (saved, updated)."""
        if not docs:
            return 0, 0
        ops = []
        for doc in docs:
            ph = doc["post_hash"]
            ops.append(UpdateOne(
                {"post_hash": ph},
                {"$set": doc, "$setOnInsert": {"first_seen": datetime.now(TZ)}},
                upsert=True,
            ))
        try:
            result = self.collection.bulk_write(ops, ordered=False)
            return result.upserted_count, result.modified_count
        except BulkWriteError as e:
            details = e.details or {}
            return details.get("nUpserted", 0), details.get("nModified", 0)
        except Exception as e:
            logger.warning(f"⚠️ Bulk upsert error: {e}")
            return 0, 0

    # =========================
    # Facebook
    # =========================
    def scrape_facebook(self) -> Dict[str, Any]:
        run_input = {
            "startUrls": [{"url": u} for u in FACEBOOK_PAGES],
            "resultsLimit": 5,
            "onlyPostsNewerThan": "1 day",
            "commentsMode": "RANKED_THREADED",  # Récupérer les top commentaires
            "maxComments": 10,  # 10 commentaires max par post
            "proxyConfiguration": PROXY_FACEBOOK,
        }

        items = self._run_actor(ACTORS["facebook"], run_input)
        docs = []

        for item in items:
            try:
                text = item.get("text") or item.get("message") or ""
                author = item.get("pageName") or item.get("userName") or "unknown"
                posted_at = item.get("time") or item.get("timestamp") or ""
                post_url = item.get("url") or item.get("postUrl") or ""

                ph = self._post_hash("facebook", text, author, posted_at)
                image_url = (item.get("fullPicture") or item.get("imageUrl")
                             or item.get("picture") or "")
                media_type = item.get("type") or (
                    "video" if item.get("videoUrl")
                    else "photo" if image_url else "text"
                )

                # Extraire les commentaires texte
                raw_comments = item.get("topComments") or item.get("comments_full") or []
                comment_texts = []
                if isinstance(raw_comments, list):
                    for c in raw_comments[:10]:
                        ct = c.get("text") or c.get("comment_text") or c.get("message") or ""
                        if ct.strip():
                            comment_texts.append({
                                "author": c.get("profileName") or c.get("author") or "?",
                                "text": ct[:500],
                                "likes": self._safe_int(c.get("likesCount") or c.get("likes")),
                            })

                docs.append({
                    "platform": "facebook",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": self._safe_int(item.get("likesCount") or item.get("likes")),
                    "comments_count": self._safe_int(item.get("commentsCount") or item.get("comments")),
                    "shares": self._safe_int(item.get("sharesCount") or item.get("shares")),
                    "comment_texts": comment_texts,
                    "image_url": image_url,
                    "media_type": media_type,
                    "scraped_at": datetime.now(TZ),
                })
            except Exception as e:
                logger.warning(f"⚠️ FB parse: {e}")

        saved, updated = self._bulk_upsert(docs)
        logger.info(f"📘 Facebook: {saved} nouveaux + {updated} MAJ / {len(items)} récupérés")
        return {"platform": "facebook", "fetched": len(items), "saved": saved, "updated": updated}

    # =========================
    # Instagram
    # =========================
    def scrape_instagram(self) -> Dict[str, Any]:
        direct_urls = [f"https://www.instagram.com/{a}/" for a in INSTAGRAM_ACCOUNTS]

        run_input = {
            "directUrls": direct_urls,
            "resultsLimit": 5,
            "resultsType": "posts",
            "addParentData": True,  # Inclure les commentaires
            "proxyConfiguration": PROXY_LIGHT,
        }

        items = self._run_actor(ACTORS["instagram"], run_input)
        docs = []

        for item in items:
            try:
                text = item.get("caption") or ""
                author = item.get("ownerUsername") or item.get("owner", {}).get("username", "unknown")
                posted_at = item.get("timestamp") or item.get("takenAtTimestamp") or ""
                post_url = item.get("url") or item.get("displayUrl") or ""

                ph = self._post_hash("instagram", text, author, str(posted_at))
                image_url = (item.get("displayUrl") or item.get("thumbnailUrl")
                             or item.get("imageUrl") or "")
                media_type = item.get("type") or (
                    "video" if item.get("videoUrl")
                    else "photo" if image_url else "text"
                )

                # Commentaires Instagram
                raw_comments = item.get("latestComments") or item.get("comments") or []
                comment_texts = []
                if isinstance(raw_comments, list):
                    for c in raw_comments[:10]:
                        ct = c.get("text") or c.get("comment") or ""
                        if ct.strip():
                            comment_texts.append({
                                "author": c.get("ownerUsername") or c.get("owner", {}).get("username", "?") if isinstance(c.get("owner"), dict) else "?",
                                "text": ct[:500],
                                "likes": self._safe_int(c.get("likesCount") or c.get("likes")),
                            })

                docs.append({
                    "platform": "instagram",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": self._safe_int(item.get("likesCount") or item.get("likes")),
                    "comments_count": self._safe_int(item.get("commentsCount") or item.get("comments")),
                    "comment_texts": comment_texts,
                    "image_url": image_url,
                    "media_type": media_type,
                    "scraped_at": datetime.now(TZ),
                })
            except Exception as e:
                logger.warning(f"⚠️ IG parse: {e}")

        saved, updated = self._bulk_upsert(docs)
        logger.info(f"📸 Instagram: {saved} nouveaux + {updated} MAJ / {len(items)} récupérés")
        return {"platform": "instagram", "fetched": len(items), "saved": saved, "updated": updated}

    # =========================
    # TikTok (nouveau)
    # =========================
    def scrape_tiktok(self) -> Dict[str, Any]:
        """Scrape comptes + hashtags TikTok via clockworks/tiktok-scraper (PPE)."""
        # Profils
        profile_urls = [f"https://www.tiktok.com/@{a}" for a in TIKTOK_ACCOUNTS]
        # Hashtags
        hashtag_urls = [f"https://www.tiktok.com/tag/{h}" for h in TIKTOK_HASHTAGS]

        run_input = {
            "profiles": profile_urls,
            "hashtags": hashtag_urls,
            "resultsPerPage": 5,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "maxComments": 10,  # Top commentaires
            "proxyConfiguration": PROXY_LIGHT,
        }

        items = self._run_actor(ACTORS["tiktok"], run_input, timeout_secs=300)
        docs = []

        for item in items:
            try:
                text = item.get("text") or item.get("desc") or item.get("description") or ""
                author = (item.get("authorMeta", {}).get("name", "")
                          or item.get("author", {}).get("uniqueId", "")
                          or item.get("author") or "unknown")
                if isinstance(author, dict):
                    author = author.get("uniqueId") or author.get("nickname") or "unknown"
                posted_at = item.get("createTime") or item.get("created_at") or ""
                # Convertir timestamp Unix si nécessaire
                if isinstance(posted_at, (int, float)) and posted_at > 1000000000:
                    posted_at = datetime.fromtimestamp(posted_at, tz=TZ).isoformat()

                video_id = str(item.get("id") or item.get("videoId") or "")
                post_url = item.get("webVideoUrl") or item.get("url") or ""
                if not post_url and video_id and isinstance(author, str):
                    post_url = f"https://www.tiktok.com/@{author}/video/{video_id}"

                ph = self._post_hash("tiktok", text, str(author), str(posted_at))

                # Engagement
                stats = item.get("statsV2") or item.get("stats") or {}
                likes = self._safe_int(stats.get("diggCount") or stats.get("heart")
                                       or item.get("diggCount") or item.get("likes"))
                comments = self._safe_int(stats.get("commentCount") or stats.get("comment")
                                          or item.get("commentCount") or item.get("comments"))
                shares = self._safe_int(stats.get("shareCount") or stats.get("share")
                                        or item.get("shareCount") or item.get("shares"))
                views = self._safe_int(stats.get("playCount") or stats.get("play")
                                       or item.get("playCount") or item.get("views"))

                # Thumbnail
                image_url = (item.get("covers", {}).get("default", "")
                             if isinstance(item.get("covers"), dict) else "")
                if not image_url:
                    image_url = item.get("video", {}).get("cover", "") if isinstance(item.get("video"), dict) else ""

                # Commentaires TikTok
                raw_comments = item.get("comments") or []
                comment_texts = []
                if isinstance(raw_comments, list):
                    for c in raw_comments[:10]:
                        ct = c.get("text") or c.get("comment") or ""
                        if ct.strip():
                            comment_texts.append({
                                "author": c.get("uniqueId") or c.get("user", {}).get("uniqueId", "?") if isinstance(c.get("user"), dict) else "?",
                                "text": ct[:500],
                                "likes": self._safe_int(c.get("diggCount") or c.get("likes")),
                            })

                docs.append({
                    "platform": "tiktok",
                    "post_hash": ph,
                    "author": author,
                    "text": text,
                    "url": post_url,
                    "posted_at": posted_at,
                    "likes": likes,
                    "comments_count": comments,
                    "comment_texts": comment_texts,
                    "shares": shares,
                    "views": views,
                    "image_url": image_url,
                    "media_type": "video",
                    "scraped_at": datetime.now(TZ),
                })
            except Exception as e:
                logger.warning(f"⚠️ TikTok parse: {e}")

        saved, updated = self._bulk_upsert(docs)
        logger.info(f"🎵 TikTok: {saved} nouveaux + {updated} MAJ / {len(items)} récupérés")
        return {"platform": "tiktok", "fetched": len(items), "saved": saved, "updated": updated}

    # =========================
    # Run all platforms
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
            ("tiktok", self.scrape_tiktok),
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

        logger.info(f"📊 Social terminé: {total_saved} nouveaux, {enriched} enrichis IA")
        return {
            "success": True,
            "total_saved": total_saved,
            "enriched": enriched,
            "platforms": results,
            "timestamp": datetime.now(TZ).isoformat(),
        }

    # =========================
    # Enrichissement IA des posts
    # =========================
    def enrich_new_posts(self, limit: int = 30) -> int:
        """Enrichit les posts par IA (sentiment, thème, gravité) puis ingère dans les affaires."""
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

        unenriched = list(self.collection.find({
            "ai_enriched": {"$ne": True},
            "text": {"$exists": True, "$ne": ""},
        }).sort("scraped_at", -1).limit(limit))

        if not unenriched:
            return 0

        enriched_total = 0
        bulk_ops = []
        relevant_posts = []  # Posts pertinents pour ingestion dans les affaires

        for i in range(0, len(unenriched), 15):
            batch = unenriched[i:i + 15]
            enriched = enrich_social_posts_batch(batch, batch_size=15)

            for post in enriched:
                update_fields = {
                    "ai_enriched": post.get("ai_enriched", True),
                    "ai_relevant": post.get("ai_relevant", False),
                    "elected": post.get("elected", []),
                    "institutions": post.get("institutions", []),
                    "entities": post.get("entities", []),
                    "theme": post.get("theme", "general"),
                    "gravity_score": post.get("gravity_score", 0.1),
                    "sentiment": post.get("sentiment", "neutre"),
                    "opinion_commentaires": post.get("opinion_commentaires", ""),
                    "ai_summary": post.get("ai_summary", ""),
                    "keywords_found": post.get("keywords_found", []),
                    "_analysis_method": post.get("_analysis_method", ""),
                }
                bulk_ops.append(UpdateOne({"_id": post["_id"]}, {"$set": update_fields}))

                # Collecter les posts pertinents pour ingestion dans les affaires
                if post.get("ai_relevant") and post.get("gravity_score", 0) >= 0.15:
                    relevant_posts.append(post)

        # ⚡ Un seul bulk_write
        if bulk_ops:
            try:
                result = self.collection.bulk_write(bulk_ops, ordered=False)
                enriched_total = result.modified_count + result.upserted_count
            except BulkWriteError as e:
                enriched_total = (e.details or {}).get("nModified", 0)

        # 🔗 Ingérer les posts pertinents dans le pipeline affaires
        ingested = 0
        if relevant_posts:
            try:
                try:
                    from backend.affair_lifecycle_service import get_affair_lifecycle_service
                except ImportError:
                    from affair_lifecycle_service import get_affair_lifecycle_service
                svc = get_affair_lifecycle_service(db=self.db)
                for post in relevant_posts:
                    try:
                        r = svc.ingest_item(post, source_type="social")
                        if r.get("success") and r.get("action") != "already_exists":
                            ingested += 1
                    except Exception:
                        pass
                if ingested:
                    logger.info(f"🔗 {ingested} posts RS ingérés dans les affaires")
            except Exception as e:
                logger.warning(f"⚠️ Ingestion affaires RS: {e}")

        logger.info(f"🧠 {enriched_total}/{len(unenriched)} posts enrichis IA, {ingested} classés en affaires")
        return enriched_total

    # =========================
    # Stats (optimisées — un seul aggregate au lieu de 9 count_documents)
    # =========================
    def get_stats(self) -> Dict[str, Any]:
        if self.collection is None:
            return {"error": "Mongo indisponible"}

        now = datetime.now(TZ)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        # ⚡ Un seul aggregate pour toutes les plateformes
        pipeline = [
            {"$facet": {
                "by_platform": [
                    {"$group": {
                        "_id": "$platform",
                        "total": {"$sum": 1},
                        "recent_24h": {"$sum": {"$cond": [{"$gte": ["$scraped_at", last_24h]}, 1, 0]}},
                        "recent_7d": {"$sum": {"$cond": [{"$gte": ["$scraped_at", last_7d]}, 1, 0]}},
                        "last_scraped": {"$max": "$scraped_at"},
                    }},
                ],
            }},
        ]
        try:
            result = list(self.collection.aggregate(pipeline))
            facets = result[0] if result else {}
            stats = {}
            for entry in facets.get("by_platform", []):
                p = entry["_id"]
                ls = entry.get("last_scraped")
                stats[p] = {
                    "total": entry["total"],
                    "last_24h": entry["recent_24h"],
                    "last_7d": entry["recent_7d"],
                    "last_scraped": ls.isoformat() if hasattr(ls, "isoformat") else str(ls) if ls else None,
                }
            return {"stats": stats, "timestamp": now.isoformat()}
        except Exception as e:
            logger.warning(f"⚠️ Stats aggregate error: {e}")
            return {"stats": {}, "timestamp": now.isoformat()}

    def get_recent_posts(self, platform: Optional[str] = None, limit: int = 50) -> List[Dict]:
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
