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

            self.db = client.veille_media
            self.social_collection = self.db["social_media_posts"]

            # Index basique pour éviter doublons (optionnel)
            try:
                self.social_collection.create_index("id", unique=True)
            except Exception:
                pass

            logger.info("✅ Connexion MongoDB réussie pour réseaux sociaux")

        except ConfigurationError as ce:
            logger.error(f"❌ Erreur config MongoDB: {ce}")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")

    # ------------------------------------------------------------------
    # YouTube: résolution auto chaîne -> RSS
    # ------------------------------------------------------------------
    def _resolve_youtube_feeds(self):
        self.youtube_feeds = []
        for url in self.youtube_channel_urls:
            rss_url = self._get_youtube_rss_from_url(url)
            if rss_url:
                self.youtube_feeds.append(rss_url)
                logger.info(f"✅ YouTube feed: {url} -> {rss_url}")
            else:
                logger.warning(f"⚠️ Impossible de résoudre: {url}")

    def _get_youtube_rss_from_url(self, url: str) -> Optional[str]:
        """
        Résout automatiquement:
        - @handle -> RSS feed
        - /channel/UC... -> RSS feed
        - /c/CustomName -> RSS feed
        """
        if not url.strip():
            return None

        # @handle
        if "/@" in url:
            handle = url.split("/@")[-1].strip()
            return self._resolve_handle_to_rss(handle)

        # /channel/UC...
        channel_match = re.search(r"/channel/([A-Za-z0-9_-]+)", url)
        if channel_match:
            channel_id = channel_match.group(1)
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

        # /c/CustomName ou /user/Username
        custom_match = re.search(r"/(c|user)/([A-Za-z0-9_-]+)", url)
        if custom_match:
            custom_name = custom_match.group(2)
            return self._resolve_custom_name_to_rss(custom_name)

        return None

    def _resolve_handle_to_rss(self, handle: str) -> Optional[str]:
        """Résout @handle vers RSS via scraping léger de la page chaîne"""
        try:
            url = f"https://www.youtube.com/@{handle}"
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

    def _resolve_custom_name_to_rss(self, custom_name: str) -> Optional[str]:
        """Résout /c/CustomName vers RSS"""
        try:
            url = f"https://www.youtube.com/c/{custom_name}"
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
            search_query = '"Conseil Départemental" OR "CD971" OR "Département Guadeloupe" lang:fr'
        else:
            search_query = f'{keyword} (Guadeloupe OR 971 OR Gwada) lang:fr'

        try:
            # snscrape récent
            scraped_tweets = sntwitter.TwitterSearchScraper(search_query).get_items()
            
            count = 0
            for tweet in scraped_tweets:
                if count >= max_posts:
                    break

                posts.append({
                    "id": f"twitter_{tweet.id}",
                    "platform": "twitter",
                    "content": tweet.rawContent,
                    "author": tweet.user.username,
                    "created_at": tweet.date.isoformat() if tweet.date else datetime.utcnow().isoformat(),
                    "url": f"https://twitter.com/{tweet.user.username}/status/{tweet.id}",
                    "engagement": {
                        "likes": tweet.likeCount or 0,
                        "retweets": tweet.retweetCount or 0,
                        "replies": tweet.replyCount or 0,
                        "total": (tweet.likeCount or 0) + (tweet.retweetCount or 0) + (tweet.replyCount or 0)
                    },
                    "keyword_searched": keyword,
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "demo_data": False
                })
                count += 1

        except Exception as e:
            logger.warning(f"snscrape échec pour '{keyword}': {e}")

        return posts

    def _try_nitter_search(self, keyword: str, max_items: int = 20) -> List[Dict[str, Any]]:
        """Fallback Nitter pour Twitter"""
        posts = []
        
        for nitter_base in self.nitter_instances:
            try:
                # URL de recherche Nitter
                query = quote_plus(f'{keyword} Guadeloupe')
                url = f"{nitter_base}/search?q={query}"
                
                resp = self.session.get(url, timeout=REQ_TIMEOUT)
                if resp.status_code != 200:
                    continue

                # Parsing très basique des résultats Nitter
                if 'class="tweet-content"' in resp.text:
                    # Pattern simple pour extraire tweets
                    tweet_pattern = r'<div class="tweet-content[^>]*>(.*?)</div>'
                    matches = re.findall(tweet_pattern, resp.text, re.DOTALL)
                    
                    for i, content in enumerate(matches[:max_items]):
                        if len(posts) >= max_items:
                            break
                            
                        # Nettoyer le HTML basique
                        clean_content = re.sub(r'<[^>]+>', '', content).strip()
                        if len(clean_content) < 10:  # Ignore les tweets trop courts
                            continue
                            
                        posts.append({
                            "id": f"nitter_{hash(clean_content)}_{i}",
                            "platform": "twitter",
                            "content": clean_content,
                            "author": "via_nitter",
                            "created_at": datetime.utcnow().isoformat(),
                            "url": f"{nitter_base}/search?q={query}",
                            "engagement": {"likes": 0, "retweets": 0, "replies": 0, "total": 0},
                            "keyword_searched": keyword,
                            "scraped_at": datetime.utcnow().isoformat() + "Z",
                            "date": datetime.utcnow().strftime("%Y-%m-%d"),
                            "demo_data": False,
                            "source_method": "nitter_fallback"
                        })

                if posts:  # Si on a trouvé quelque chose, pas besoin d'essayer d'autres instances
                    logger.info(f"Nitter {nitter_base}: {len(posts)} posts pour '{keyword}'")
                    break
                    
            except Exception as e:
                logger.warning(f"Nitter {nitter_base} échec: {e}")
                continue

        return posts

    # ------------------------------------------------------------------
    # RSS Générique + Google News
    # ------------------------------------------------------------------
    def fetch_rss_feed(self, rss_url: str, platform_tag: str = "news", keyword: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        posts = []
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:limit]:
                title = entry.get("title", "Sans titre")
                description = entry.get("description", "") or entry.get("summary", "")
                link = entry.get("link", rss_url)
                
                # Date de publication
                pub_date = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub_date:
                    pub_datetime = datetime(*pub_date[:6])
                else:
                    pub_datetime = datetime.utcnow()

                posts.append({
                    "id": f"{platform_tag}_{hash(link)}",
                    "platform": platform_tag,
                    "content": f"{title}\n\n{description}",
                    "title": title,
                    "author": feed.feed.get("title", "RSS"),
                    "created_at": pub_datetime.isoformat(),
                    "url": link,
                    "engagement": {"likes": 0, "shares": 0, "comments": 0, "total": 0},
                    "keyword_searched": keyword,
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                    "date": datetime.utcnow().strftime("%Y-%m-%d"),
                    "demo_data": False
                })
        except Exception as e:
            logger.warning(f"RSS échec '{rss_url}': {e}")
        return posts

    def google_news_rss(self, keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Google News RSS pour un mot-clé"""
        query = quote_plus(f"{keyword} Guadeloupe")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"
        return self.fetch_rss_feed(rss_url, platform_tag="news", keyword=keyword, limit=limit)

    # ------------------------------------------------------------------
    # Méthode principale : scraper tout
    # ------------------------------------------------------------------
    def start_scrape(self, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        if not keywords:
            keywords = self.keywords_guadeloupe[:3]  # Limiter pour éviter timeout

        results = {
            "twitter": [],
            "facebook": [],
            "instagram": [],
            "news": [],
            "youtube": [],
            "keywords_searched": keywords,
            "scraped_at": datetime.utcnow().isoformat() + "Z",
            "note": ""
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
            results["note"] = "Aucun post trouvé – X/Twitter peut bloquer; RSS/YouTube ajoutés en fallback."
            logger.warning("⚠️ Aucun post récupéré. Vérifier snscrape, Nitter et RSS.")
        else:
            logger.info(f"✅ {results['total_posts']} posts récupérés au total")

        return results

    # ------------------------------------------------------------------
    # Sauvegarde & Recherche
    # ------------------------------------------------------------------
    def save_posts_to_db(self, posts: List[Dict[str, Any]]) -> int:
        if not self.social_collection or not posts:
            return 0

        saved_count = 0
        for post in posts:
            try:
                # Upsert basé sur l'id
                self.social_collection.update_one(
                    {"id": post["id"]},
                    {"$set": post},
                    upsert=True
                )
                saved_count += 1
            except Exception as e:
                logger.warning(f"Sauvegarde post {post.get('id', 'unknown')} KO: {e}")

        logger.info(f"💾 {saved_count}/{len(posts)} posts sauvegardés en DB")
        return saved_count

    def search_posts(self, q: str, limit: int = 40) -> Dict[str, Any]:
        if not self.social_collection:
            return {"query": q, "total_results": 0, "posts": [], "error": "DB indisponible"}

        try:
            # Recherche dans content et title
            docs = list(
                self.social_collection
                .find({
                    "$or": [
                        {"content": {"$regex": q, "$options": "i"}},
                        {"title": {"$regex": q, "$options": "i"}}
                    ]
                }, {"_id": 0})
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