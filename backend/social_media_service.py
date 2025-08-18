# backend/social_media_service.py
"""
Scraper Social minimal & robuste (sans API payantes)
- YouTube: flux RSS des chaînes (résolution auto depuis URLs @handle / /channel/…)
- Google News RSS + RSS locaux
- X/Twitter: snscrape si dispo, sinon fallback Nitter (RSS)
- Stocke dans Mongo (collection: social_media_posts)
"""

import os
import re
import time
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

import requests
import feedparser
from pymongo import MongoClient
from pymongo.errors import ConfigurationError
import certifi

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------- Defaults ---------
DEFAULT_RSS_SOURCES = [
    "https://la1ere.francetvinfo.fr/guadeloupe/rss",
    "https://www.franceantilles.fr/rss",
]

# Par défaut on ajoute tes deux chaînes YouTube
DEFAULT_YT_URLS = [
    "https://www.youtube.com/@CD971",
    "https://www.youtube.com/@ericdamaseau320",  # La Pause Sans Filtre
]

DEFAULT_NITTERS = [
    "https://nitter.net",
    "https://nitter.fdn.fr",
    "https://nitter.privacy.com.de",
    "https://nitter.poast.org",
    "https://nitter.cz",
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
REQ_TIMEOUT = 12


class SocialMediaScraper:
    def __init__(self):
        # --------- Config env ---------
        self.noapi_mode = os.environ.get("SOCIAL_NOAPI_MODE", "true").lower() == "true"

        yt_env = [x.strip() for x in os.environ.get("YOUTUBE_CHANNEL_URLS", "").split(",") if x.strip()]
        self.youtube_channel_urls = yt_env or DEFAULT_YT_URLS
        self.youtube_feeds: List[str] = []  # sera rempli après résolution

        rss_env = [x.strip() for x in os.environ.get("SOCIAL_RSS_SOURCES", "").split(",") if x.strip()]
        self.rss_sources = rss_env or DEFAULT_RSS_SOURCES

        nitters_env = [x.strip() for x in os.environ.get("NITTER_INSTANCES", "").split(",") if x.strip()]
        self.nitter_instances = nitters_env or DEFAULT_NITTERS

        # --------- Mongo ---------
        self.db = None
        self.social_collection = None
        self._init_mongo()

        # --------- Paramètres scraping ---------
        self.max_posts_per_keyword = int(os.environ.get("SOCIAL_MAX_POSTS_PER_KEYWORD", "20"))
        self.rate_limit_delay = float(os.environ.get("SOCIAL_RATE_LIMIT_DELAY", "1.5"))  # s

        # --------- Mots-clés par défaut ---------
        self.keywords_guadeloupe = [
            "Conseil Départemental Guadeloupe", "CD971", "Département Guadeloupe",
            "Guy Losbar", "Losbar", "Président conseil départemental",
            "Collectivité Guadeloupe", "Basse-Terre politique", "CD Guadeloupe",
        ]

        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})

        # Résoudre les flux YouTube maintenant
        self._resolve_youtube_feeds()

    # ------------------------------------------------------------------
    # Mongo & Indexes
    # ------------------------------------------------------------------
    def _init_mongo(self):
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip()
        try:
            if MONGO_URL.startswith("mongodb+srv"):
                client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
            else:
                client = MongoClient(MONGO_URL)

            try:
                client.admin.command("ping")
            except Exception:
                logger.warning("⚠️ Ping Mongo échoué (connexion possible mais non vérifiée)")

            try:
                db = client.get_default_database()
            except ConfigurationError:
                db = None
            self.db = db if db is not None else client["veille_media"]

            self.social_collection = self.db["social_media_posts"]
            self._ensure_indexes()
            logger.info("✅ Connexion MongoDB OK (social_media_posts)")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
            self.db = None
            self.social_collection = None  # type: ignore

    def _ensure_indexes(self):
        if not self.social_collection:
            return
        try:
            self.social_collection.create_index([("id", 1)], unique=True)
            self.social_collection.create_index([("date", 1)])
            self.social_collection.create_index([("platform", 1)])
            self.social_collection.create_index([("scraped_at", -1)])
            self.social_collection.create_index([("keyword_searched", 1)])
            try:
                self.social_collection.create_index(
                    [("content", "text"), ("author", "text")],
                    name="content_text_idx",
                )
            except Exception as ie:
                logger.warning(f"Index texte non créé: {ie}")
        except Exception as e:
            logger.warning(f"Création d'index échouée: {e}")

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------
    def _normalize_post(
        self,
        *,
        pid: str,
        platform: str,
        keyword: str,
        content: str,
        author: str,
        url: str,
        created_at: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": pid,
            "platform": platform,
            "keyword_searched": keyword,
            "content": (content or "").strip(),
            "author": author or "",
            "author_followers": 0,
            "created_at": created_at or datetime.utcnow().isoformat() + "Z",
            "engagement": {"likes": 0, "retweets": 0, "replies": 0, "comments": 0, "shares": 0, "total": 0},
            "url": url,
            "scraped_at": datetime.utcnow().isoformat() + "Z",
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "is_reply": False,
            "language": "fr",
            "demo_data": False,
        }
        if extra:
            data.update(extra)
        return data

    # ------------------------------------------------------------------
    # RSS: Google News + sources locales + YouTube
    # ------------------------------------------------------------------
    def fetch_rss_feed(self, url: str, *, platform_tag: str, keyword: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            feed = feedparser.parse(url)
            if getattr(feed, "entries", None):
                for e in feed.entries[:limit]:
                    link = getattr(e, "link", "")
                    title = getattr(e, "title", "")
                    summary = getattr(e, "summary", "")
                    published = getattr(e, "published", None) or getattr(e, "updated", None)
                    created_at = published or datetime.utcnow().isoformat() + "Z"
                    pid = f"{platform_tag}_{abs(hash((link or title) + (keyword or platform_tag)))}"
                    content = "\n".join([title, summary]).strip()
                    items.append(
                        self._normalize_post(
                            pid=pid,
                            platform=platform_tag,
                            keyword=keyword or platform_tag,
                            content=content,
                            author="",
                            url=link or url,
                            created_at=created_at,
                        )
                    )
        except Exception as e:
            logger.warning(f"RSS échec {url}: {e}")
        return items

    def google_news_rss(self, keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        q = quote_plus(keyword)
        url = f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"
        return self.fetch_rss_feed(url, platform_tag="news", keyword=keyword, limit=limit)

    # ----------------- YouTube -----------------
    def _resolve_youtube_feeds(self):
        """Depuis des URLs de chaîne (handle, /channel/, /c/…), déduire le flux RSS:
        https://www.youtube.com/feeds/videos.xml?channel_id=UCxxxx
        """
        resolved: List[str] = []
        for url in self.youtube_channel_urls:
            try:
                feed = self._youtube_channel_url_to_feed(url)
                if feed:
                    resolved.append(feed)
            except Exception as e:
                logger.warning(f"YT resolve fail {url}: {e}")
        # uniq + preserve order
        seen = set()
        self.youtube_feeds = [f for f in resolved if not (f in seen or seen.add(f))]
        if self.youtube_feeds:
            logger.info(f"✅ YouTube feeds résolus: {len(self.youtube_feeds)}")
        else:
            logger.info("ℹ️ Aucun flux YouTube résolu")

    def _youtube_channel_url_to_feed(self, url: str) -> Optional[str]:
        """Résout channel_id en scrappant la page pour 'channelId'."""
        try:
            resp = self.session.get(url, timeout=REQ_TIMEOUT)
            if resp.status_code != 200 or not resp.text:
                return None
            m = re.search(r'"channelId"\s*:\s*"([^"]+)"', resp.text)
            if not m:
                return None
            channel_id = m.group(1)
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        except Exception:
            return None

    def scrape_youtube_basic(self, limit_per_feed: int = 8) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        for feed_url in self.youtube_feeds:
            all_items.extend(
                self.fetch_rss_feed(feed_url, platform_tag="youtube", keyword="youtube", limit=limit_per_feed)
            )
        return all_items

    # ------------------------------------------------------------------
    # Twitter: snscrape (si dispo) + fallback Nitter
    # ------------------------------------------------------------------
    def scrape_twitter_keyword(self, keyword: str, max_posts: int = 20) -> List[Dict[str, Any]]:
        try:
            import snscrape.modules.twitter as sntwitter
        except Exception:
            logger.info("ℹ️ snscrape indisponible → Nitter en fallback")
            return []

        posts: List[Dict[str, Any]] = []

        # Query ciblée Guadeloupe
        if keyword.lower() in ["guy losbar", "losbar"]:
            search_query = '"Guy Losbar" OR "Losbar" OR "président conseil départemental" lang:fr'
        elif keyword.lower() in ["conseil départemental", "cd971"]:
            search_query = '"Conseil Départemental" OR "CD971" OR "département guadeloupe" lang:fr'
        else:
            search_query = f'{keyword} (guadeloupe OR gwada OR 971 OR antilles) lang:fr'

        since_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        search_query += f" since:{since_date}"
        logger.info(f"🔍 Twitter search: {search_query}")

        count = 0
        try:
            for tw in sntwitter.TwitterSearchScraper(search_query).get_items():
                if count >= max_posts:
                    break
                if not getattr(tw, "rawContent", None) or len(tw.rawContent) < 20:
                    continue

                content_lower = tw.rawContent.lower()
                if not any(s in content_lower for s in [
                    "guy losbar", "losbar", "conseil départemental", "cd971",
                    "département guadeloupe", "guadeloupe", "gwada"
                ]):
                    continue

                engagement = (tw.replyCount or 0) + (tw.retweetCount or 0) + (tw.likeCount or 0)
                pid = f"twitter_{tw.id}"
                extra = {
                    "author_followers": getattr(tw.user, "followersCount", 0) or 0,
                    "engagement": {
                        "likes": tw.likeCount or 0,
                        "retweets": tw.retweetCount or 0,
                        "replies": tw.replyCount or 0,
                        "total": engagement,
                    },
                    "is_reply": tw.inReplyToTweetId is not None,
                    "language": getattr(tw, "lang", "fr") or "fr",
                    "url": tw.url,
                }
                posts.append(
                    self._normalize_post(
                        pid=pid,
                        platform="twitter",
                        keyword=keyword,
                        content=tw.rawContent,
                        author=tw.user.username if getattr(tw, "user", None) else "",
                        url=tw.url,
                        created_at=tw.date.isoformat() if getattr(tw, "date", None) else None,
                        extra=extra,
                    )
                )
                count += 1
                time.sleep(self.rate_limit_delay * 0.5)
        except Exception as e:
            logger.warning(f"Twitter snscrape erreur '{keyword}': {e}")

        return posts

    def _try_nitter_search(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        posts: List[Dict[str, Any]] = []
        query = f'{keyword} (guadeloupe OR gwada OR 971 OR antilles)'
        q = quote_plus(query)

        for base in self.nitter_instances:
            url = f"{base}/search/rss?f=tweets&q={q}"
            try:
                feed = feedparser.parse(url)
                entries = getattr(feed, "entries", None)
                if not entries:
                    continue
                for entry in entries[:max_items]:
                    link = getattr(entry, "link", "")
                    title = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    author = getattr(entry, "author", "nitter")
                    published = getattr(entry, "published", None) or datetime.utcnow().isoformat() + "Z"
                    content = f"{title}\n{summary}".strip()
                    pid = f"nitter_{abs(hash((link or '') + content))}"
                    posts.append(
                        self._normalize_post(
                            pid=pid,
                            platform="twitter",
                            keyword=keyword,
                            content=content,
                            author=author,
                            url=link or url,
                            created_at=published,
                            extra={"source": base},
                        )
                    )
                if posts:
                    logger.info(f"✅ Nitter ok: {base} ({len(posts)} posts cumulés)")
                    break  # on garde le 1er miroir qui répond
            except Exception as e:
                logger.warning(f"Nitter fail {base}: {e}")
        return posts

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def scrape_all_keywords(self, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        if not keywords:
            keywords = self.keywords_guadeloupe[:3]

        results: Dict[str, Any] = {
            "twitter": [],
            "news": [],
            "youtube": [],
            "total_posts": 0,
            "keywords_searched": keywords,
            "scraped_at": datetime.utcnow().isoformat() + "Z",
            "demo_mode": False,
            "note": "Scraping réel (snscrape/Nitter + Google News RSS + RSS locaux + YouTube).",
        }

        logger.info(f"🚀 Social scraping pour {len(keywords)} mots-clés (noapi_mode={self.noapi_mode})")

        for kw in keywords:
            try:
                tw = self.scrape_twitter_keyword(kw, self.max_posts_per_keyword)
                results["twitter"].extend(tw)

                if self.noapi_mode or len(tw) == 0:
                    n_posts = self._try_nitter_search(kw, max_items=self.max_posts_per_keyword)
                    if n_posts:
                        logger.info(f"Nitter fallback {kw}: +{len(n_posts)} posts")
                        results["twitter"].extend(n_posts)

                # Google News + RSS locaux
                results["news"].extend(self.google_news_rss(kw, limit=15))
                for rss in self.rss_sources:
                    results["news"].extend(
                        self.fetch_rss_feed(rss, platform_tag="news", keyword=kw, limit=10)
                    )

                time.sleep(self.rate_limit_delay)
            except Exception as e:
                logger.error(f"Erreur scraping '{kw}': {e}")

        # YouTube (global)
        try:
            results["youtube"] = self.scrape_youtube_basic(limit_per_feed=8)
        except Exception as e:
            logger.warning(f"YouTube feeds erreur: {e}")
            results["youtube"] = []

        # Dédup légère par id
        for key in ("twitter", "news", "youtube"):
            seen = set()
            dedup = []
            for p in results[key]:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                dedup.append(p)
            results[key] = dedup

        results["total_posts"] = sum(len(results[k]) for k in ["twitter", "news", "youtube"])

        if results["total_posts"] == 0:
            results["note"] = "Aucun post trouvé — X/Twitter peut bloquer; RSS/YouTube ajoutés en fallback."
            logger.warning("⚠️ Aucun post récupéré. Vérifier snscrape, Nitter et RSS.")

        return results

    # ------------------------------------------------------------------
    # Persistence & requêtes
    # ------------------------------------------------------------------
    def save_posts_to_db(self, posts: List[Dict[str, Any]]) -> int:
        if not posts or not self.social_collection:
            return 0
        saved = 0
        for post in posts:
            try:
                self.social_collection.update_one({"id": post["id"]}, {"$set": post}, upsert=True)
                saved += 1
            except Exception as e:
                logger.warning(f"Save post KO: {e}")
        logger.info(f"💾 {saved} posts sauvegardés")
        return saved

    def start_scrape(self, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        res = self.scrape_all_keywords(keywords)
        posts = res.get("twitter", []) + res.get("news", []) + res.get("youtube", [])
        res["saved"] = self.save_posts_to_db(posts)
        return res

    def search_posts(self, query: str, limit: int = 40) -> Dict[str, Any]:
        q = (query or "").strip()
        if not q or not self.social_collection:
            return {"query": q, "total_results": 0, "posts": []}
        try:
            rx = re.compile(re.escape(q), re.IGNORECASE)
            mongo_filter = {"$or": [{"content": rx}, {"author": rx}, {"keyword_searched": rx}]}
            docs = list(
                self.social_collection.find(mongo_filter, {"_id": 0})
                .sort("scraped_at", -1)
                .limit(int(limit) if limit else 40)
            )
            return {"query": q, "total_results": len(docs), "posts": docs}
        except Exception as e:
            logger.error(f"Recherche KO '{q}': {e}")
            return {"query": q, "total_results": 0, "posts": [], "error": str(e)}

    def get_recent_posts(self, days: int = 1, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.social_collection:
            return []
        try:
            since_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            query: Dict[str, Any] = {"date": {"$gte": since_date}}
            if platform:
                query["platform"] = platform
            return list(
                self.social_collection.find(query, {"_id": 0}).sort("scraped_at", -1).limit(200)
            )
        except Exception as e:
            logger.error(f"Recent KO: {e}")
            return []

    def clean_demo_data_from_db(self) -> int:
        if not self.social_collection:
            return 0
        try:
            result = self.social_collection.delete_many({"demo_data": True})
            logger.info(f"🧹 {result.deleted_count} posts démo supprimés")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Clean demo KO: {e}")
            return 0

    def get_posts_stats(self) -> Dict[str, Any]:
        if not self.social_collection:
            return {}
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            twitter_count = self.social_collection.count_documents({"platform": "twitter", "date": today})
            news_count = self.social_collection.count_documents({"platform": "news", "date": today})
            yt_count = self.social_collection.count_documents({"platform": "youtube", "date": today})

            pipeline = [
                {"$match": {"date": today}},
                {"$group": {"_id": "$keyword_searched", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5},
            ]
            top_keywords = list(self.social_collection.aggregate(pipeline))
            return {
                "total_today": twitter_count + news_count + yt_count,
                "by_platform": {"twitter": twitter_count, "news": news_count, "youtube": yt_count},
                "top_keywords": [{"keyword": x["_id"], "count": x["count"]} for x in top_keywords if x.get("_id")],
                "last_updated": datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            logger.error(f"Stats KO: {e}")
            return {}


# Instance globale importable par les routes
social_scraper = SocialMediaScraper()

if __name__ == "__main__":
    print("=== Test Scraper Social ===")
    res = social_scraper.start_scrape(["Guadeloupe", "CD971"])
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}, indent=2, ensure_ascii=False))
