"""
Service de scraping des sites d'actualités de Guadeloupe - VERSION AMÉLIORÉE
Scraping manuel via guadeloupe_scraper.run() et utilitaires.
"""

import os
import re
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
import concurrent.futures
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class GuadeloupeScraper:
    def __init__(self) -> None:
        # Connexion MongoDB (Atlas ou local)
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")

        try:
            if "mongodb+srv://" in MONGO_URL or "atlas" in MONGO_URL.lower():
                import certifi  # important pour Atlas
                self.client = MongoClient(
                    MONGO_URL,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000,
                    maxPoolSize=20,
                    retryWrites=True,
                    retryReads=True,
                )
            else:
                self.client = MongoClient(
                    MONGO_URL,
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000,
                    maxPoolSize=20,
                    retryWrites=True,
                    retryReads=True,
                )

            # Ping
            self.client.admin.command("ping")
            logger.info("✅ Scraper connecté à MongoDB")

            # Résolution nom de base
            try:
                # si l’URL contient le nom de DB
                dbname = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
                if "mongodb+srv://" in MONGO_URL and ("?" in dbname or not dbname):
                    dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            except Exception:
                dbname = os.environ.get("MONGO_DB_NAME", "veille_media")

            self.db = self.client[dbname]
            self.articles_collection = self.db["articles"]
        except Exception as e:
            logger.error(f"❌ Erreur connection MongoDB pour scraper: {e}")
            raise

        # Config des sites
        self.sites_config: Dict[str, Dict[str, Any]] = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selectors": [
                    "article h2 a",
                    "article h3 a",
                    ".article-title a",
                    ".title a",
                    ".entry-title a",
                    "h2 a",
                    "h3 a",
                    ".post-title a",
                    ".content-title a",
                    ".news-title a",
                ],
                "base_url": "https://www.guadeloupe.franceantilles.fr",
            },
            "rci": {
                "name": "RCI Guadeloupe",
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selectors": [
                    "a[href*='/guadeloupe/infos/']",
                    ".post-title a",
                    ".entry-title a",
                    "h2 a",
                    "h3 a",
                    ".article-title a",
                    ".content-title a",
                    ".news-item a",
                ],
                "base_url": "https://rci.fm",
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selectors": [
                    ".teaser__title a",
                    ".article-title a",
                    "h2 a",
                    "h3 a",
                    ".content-title a",
                    ".post-title a",
                    ".entry-title a",
                    ".news-title a",
                    ".item-title a",
                    "a[href*='/guadeloupe/']",
                ],
                "base_url": "https://la1ere.franceinfo.fr",
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selectors": [
                    "h1 a",
                    "h2 a",
                    "h3 a",
                    "article a",
                    ".post a",
                    ".post-title a",
                    ".entry-title a",
                    ".title a",
                    ".article-title a",
                    ".content-title a",
                    ".news-title a",
                    "a[href*='/news/']",
                    "a[href*='/actualite/']",
                    "a[href*='/societe/']",
                ],
                "base_url": "https://www.karibinfo.com",
            },
        }

        # Rotation d’user-agents
        self.headers_list: List[Dict[str, str]] = [
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            },
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "fr,en-US;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
            },
        ]
        self.current_header_index = 0

    # ----------------------- Utils -----------------------

    def get_next_headers(self) -> Dict[str, str]:
        headers = self.headers_list[self.current_header_index]
        self.current_header_index = (self.current_header_index + 1) % len(self.headers_list)
        return headers

    def clean_title(self, title: str) -> str:
        if not title:
            return ""
        title = re.sub(r"[\n\r\t]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        prefixes = ["LIRE AUSSI:", "VOIR AUSSI:", "À LIRE:", "VIDÉO:", "PHOTO:", "EN DIRECT:", "BREAKING:", "URGENT:"]
        for p in prefixes:
            if title.upper().startswith(p):
                title = title[len(p) :].strip()
        return title

    def normalize_title(self, title: str) -> str:
        if not title:
            return ""
        normalized = re.sub(r"[^\w\s]", " ", title.lower())
        return re.sub(r"\s+", " ", normalized).strip()

    def is_valid_article_url(self, url: str, base_domain: str) -> bool:
        if not url:
            return False

        ignore = [
            "/tag/",
            "/category/",
            "/author/",
            "/page/",
            "/search/",
            "/archives/",
            "/contact/",
            "/about/",
            "javascript:",
            "mailto:",
            "#",
            "tel:",
            "/vakans-opeyi",
            "/tour-cycliste",
            "/informations-pratiques",
        ]
        for pat in ignore:
            if pat in url.lower():
                return False

        parsed = urlparse(url)
        if parsed.netloc and base_domain not in parsed.netloc:
            return False

        if "rci.fm" in base_domain:
            return "/infos/" in url and len(url.split("/")[-1]) > 10
        if "la1ere.franceinfo.fr" in base_domain:
            return "/guadeloupe/" in url and url.count("/") >= 4
        if "karibinfo.com" in base_domain:
            return any(cat in url for cat in ["/news/", "/actualite/", "/politique/", "/societe/", "/economie/"])

        return True

    # ----------------- Scrapers spécialisés -----------------

    def scrape_rci_articles(self, url: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if (
                    href.startswith("/guadeloupe/infos/")
                    and len(text) > 15
                    and not any(x in href.lower() for x in ["informations-pratiques", "toutes-les-infos", "vakans-opeyi", "tour-cycliste"])
                ):
                    full_url = "https://rci.fm" + href
                    title = self.clean_title(text)
                    if len(title) > 10:
                        articles.append(
                            {
                                "id": f"rci_{hash(full_url)}",
                                "title": title,
                                "url": full_url,
                                "source": "RCI Guadeloupe",
                                "site_key": "rci",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                            }
                        )

            # unique par URL
            seen, unique = set(), []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)
            logger.info(f"✅ RCI Guadeloupe: {len(unique)} articles trouvés")
            return unique[:20]
        except Exception as e:
            logger.error(f"❌ Erreur scraping RCI: {e}")
            return []

    def scrape_france_antilles_articles(self, url: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            selectors = ["article h2 a", "article h3 a", "h2 a", "h3 a"]
            links = []
            for sel in selectors:
                links.extend(soup.select(sel))

            for link in links:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if (
                    href.startswith("/actualite/")
                    and len(text) > 15
                    and not any(x in href.lower() for x in ["hub-economie/", "sports/tour-de-la-guadeloupe/", "environnement/saison-cyclonique/"])
                    and not any(x in text.lower() for x in ["hub éco", "tour de guadeloupe", "saison cyclonique"])
                ):
                    full_url = "https://www.guadeloupe.franceantilles.fr" + href
                    title = self.clean_title(text)
                    if 10 < len(title) < 200:
                        articles.append(
                            {
                                "id": f"france_antilles_{hash(full_url)}",
                                "title": title,
                                "url": full_url,
                                "source": "France-Antilles Guadeloupe",
                                "site_key": "france_antilles",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                            }
                        )

            seen, unique = set(), []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)
            logger.info(f"✅ France-Antilles Guadeloupe: {len(unique)} articles trouvés")
            return unique[:15]
        except Exception as e:
            logger.error(f"❌ Erreur scraping France-Antilles: {e}")
            return []

    def scrape_la1ere_articles(self, url: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/guadeloupe/" in href and len(text) > 15 and href.count("/") >= 4 and not any(
                    x in href.lower() for x in ["direct-tv", "programme-audio", "replay"]
                ):
                    full_url = href if href.startswith("http") else "https://la1ere.franceinfo.fr" + href
                    title = self.clean_title(text)
                    if len(title) > 10:
                        articles.append(
                            {
                                "id": f"la1ere_{hash(full_url)}",
                                "title": title,
                                "url": full_url,
                                "source": "La 1ère Guadeloupe",
                                "site_key": "la1ere",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                            }
                        )

            seen, unique = set(), []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)
            logger.info(f"✅ La 1ère Guadeloupe: {len(unique)} articles trouvés")
            return unique[:15]
        except Exception as e:
            logger.error(f"❌ Erreur scraping La 1ère: {e}")
            return []

    def scrape_karibinfo_articles(self, url: str) -> List[Dict[str, Any]]:
        articles: List[Dict[str, Any]] = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            selectors = ["h1 a", "h2 a", "h3 a", "article a"]
            links = []
            for sel in selectors:
                links.extend(soup.select(sel))

            for link in links:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if (
                    href.startswith("https://www.karibinfo.com/news/")
                    and len(text) > 15
                    and "." in text
                    and not any(x in href.lower() for x in ["author/", "category/", "tag/", "page/"])
                    and not any(x in text.lower() for x in ["karibinfo.com", "actualité", "newsletter"])
                ):
                    full_url = href
                    title = self.clean_title(text)
                    if 10 < len(title) < 200:
                        articles.append(
                            {
                                "id": f"karibinfo_{hash(full_url)}",
                                "title": title,
                                "url": full_url,
                                "source": "KaribInfo",
                                "site_key": "karibinfo",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                            }
                        )

            seen, unique = set(), []
            for art in articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)
            logger.info(f"✅ KaribInfo: {len(unique)} articles trouvés")
            return unique[:15]
        except Exception as e:
            logger.error(f"❌ Erreur scraping KaribInfo: {e}")
            return []

    # --------------------- Scraping générique ---------------------

    def scrape_page(self, url: str, site_key: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        # Délègue aux scrapers spécialisés
        if site_key == "rci":
            return self.scrape_rci_articles(url)
        if site_key == "la1ere":
            return self.scrape_la1ere_articles(url)
        if site_key == "karibinfo":
            return self.scrape_karibinfo_articles(url)
        if site_key == "france_antilles":
            return self.scrape_france_antilles_articles(url)

        config = self.sites_config[site_key]
        articles: List[Dict[str, Any]] = []

        for attempt in range(max_retries):
            try:
                logger.info(f"🔍 Scraping {url} (tentative {attempt + 1})")
                session = requests.Session()
                session.headers.update(self.get_next_headers())
                resp = session.get(url, timeout=20)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.content, "html.parser")

                all_links = []
                for selector in config["selectors"]:
                    try:
                        all_links.extend(soup.select(selector))
                    except Exception as e:
                        logger.debug(f"Sélecteur {selector} échoué: {e}")

                seen_urls, unique_links = set(), []
                for link in all_links:
                    href = link.get("href")
                    if href and href not in seen_urls:
                        seen_urls.add(href)
                        unique_links.append(link)

                logger.info(f"📝 {len(unique_links)} liens trouvés sur {url}")

                for link in unique_links:
                    try:
                        title = self.clean_title(link.get_text())
                        href = link.get("href")
                        if not title or not href or len(title) < 10:
                            continue
                        full_url = href if href.startswith("http") else urljoin(config["base_url"], href)
                        if not self.is_valid_article_url(full_url, config["base_url"]):
                            continue
                        articles.append(
                            {
                                "id": f"{site_key}_{hash(full_url)}",
                                "title": title,
                                "url": full_url,
                                "source": config["name"],
                                "site_key": site_key,
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Erreur traitement lien: {e}")

                logger.info(f"✅ {len(articles)} articles valides trouvés sur {url}")
                return articles
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout pour {url} (tentative {attempt + 1})")
                time.sleep(2**attempt)
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 Erreur réseau pour {url}: {e}")
                time.sleep(2**attempt)
            except Exception as e:
                logger.error(f"❌ Erreur inattendue pour {url}: {e}")
                break

        logger.error(f"❌ Échec scraping {url} après {max_retries} tentatives")
        return []

    def scrape_site(self, site_key: str) -> List[Dict[str, Any]]:
        config = self.sites_config[site_key]
        all_articles: List[Dict[str, Any]] = []

        try:
            logger.info(f"🚀 Début scraping complet: {config['name']}")
            pages = [config["url"]] + config.get("additional_pages", [])
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                future_to_url = {pool.submit(self.scrape_page, u, site_key): u for u in pages}
                for fut in concurrent.futures.as_completed(future_to_url):
                    u = future_to_url[fut]
                    try:
                        arts = fut.result(timeout=30)
                        all_articles.extend(arts)
                        logger.info(f"📄 {len(arts)} articles de {u}")
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"⏰ Timeout pour {u}")
                    except Exception as e:
                        logger.error(f"❌ Erreur pour {u}: {e}")

            seen, unique = set(), []
            for art in all_articles:
                if art["url"] not in seen:
                    seen.add(art["url"])
                    unique.append(art)

            logger.info(f"✅ Total {config['name']}: {len(unique)} articles uniques")
            return unique
        except Exception as e:
            logger.error(f"❌ Erreur scraping {config['name']}: {e}")
            return []

    # ---------------------- Doublons & Sauvegarde ----------------------

    def is_duplicate_article(self, new_article: Dict[str, Any]) -> bool:
        try:
            if self.articles_collection.find_one({"id": new_article["id"]}):
                return True
            if new_article.get("url") and self.articles_collection.find_one({"url": new_article["url"]}):
                return True

            if new_article.get("content"):
                content_hash = hashlib.md5(new_article["content"].encode("utf-8", errors="ignore")).hexdigest()
                if self.articles_collection.find_one({"content_hash": content_hash}):
                    return True
                new_article["content_hash"] = content_hash

            return False
        except Exception as e:
            logger.warning(f"Erreur vérification doublon: {e}")
            return False

    def _find_similar_titles(self) -> int:
        """Supprime les articles aux titres très similaires (même source) sur 2 jours."""
        try:
            since = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            recent = list(
                self.articles_collection.find({"date": {"$gte": since}}).sort("scraped_at", -1)
            )
            removed = 0
            processed = set()

            for i, a1 in enumerate(recent):
                if a1["_id"] in processed:
                    continue
                for a2 in recent[i + 1 :]:
                    if a2["_id"] in processed:
                        continue
                    if a1.get("source") == a2.get("source") and a1.get("title") and a2.get("title"):
                        t1 = self.normalize_title(a1["title"])
                        t2 = self.normalize_title(a2["title"])
                        similarity = SequenceMatcher(None, t1, t2).ratio()
                        if similarity >= 0.92:
                            # garde le plus récent
                            older = a2 if a1.get("scraped_at", "") > a2.get("scraped_at", "") else a1
                            self.articles_collection.delete_one({"_id": older["_id"]})
                            processed.add(older["_id"])
                            removed += 1
            return removed
        except Exception as e:
            logger.warning(f"Erreur détection titres similaires: {e}")
            return 0

    # ------------------------ Orchestrateur ------------------------

    def scrape_all_sites(self) -> Dict[str, Any]:
        logger.info("🚀 Début du scraping des sites guadeloupéens...")
        start = time.time()
        all_articles: List[Dict[str, Any]] = []
        results: Dict[str, Any] = {
            "success": True,
            "scraped_at": datetime.now().isoformat(),
            "sites_scraped": 0,
            "total_articles": 0,
            "articles_by_site": {},
            "duplicates_by_site": {},
            "errors": [],
            "execution_time_seconds": 0,
        }

        for site_key, cfg in self.sites_config.items():
            try:
                logger.info(f"🔍 Scraping {cfg['name']}...")
                arts = self.scrape_page(cfg["url"], site_key, max_retries=2)
                saved, dups = 0, 0
                for a in arts:
                    try:
                        a["scraped_at"] = datetime.now().isoformat()
                        if not self.is_duplicate_article(a):
                            self.articles_collection.update_one(
                                {"id": a["id"]}, {"$set": a}, upsert=True
                            )
                            saved += 1
                        else:
                            dups += 1
                    except Exception as e:
                        logger.warning(f"Erreur sauvegarde article: {e}")

                results["articles_by_site"][site_key] = saved
                results["duplicates_by_site"][site_key] = dups
                results["sites_scraped"] += 1

                all_articles.extend([x for x in arts if not self.is_duplicate_article(x)])
                logger.info(f"✅ {cfg['name']}: {saved} sauvegardés, {dups} doublons ignorés")
                time.sleep(2)
            except Exception as e:
                msg = f"Erreur {cfg['name']}: {str(e)}"
                results["errors"].append(msg)
                logger.error(msg)

        # Nettoyage titres proches (optionnel)
        try:
            removed_sim = self._find_similar_titles()
            if removed_sim:
                logger.info(f"🧹 {removed_sim} doublons supprimés par similarité de titre")
        except Exception:
            pass

        results["total_articles"] = len(all_articles)
        results["total_duplicates"] = sum(results["duplicates_by_site"].values())
        results["articles"] = all_articles
        results["execution_time_seconds"] = round(time.time() - start, 2)

        # Invalidation du cache
        try:
            from .cache_service import cache_invalidate
            cache_invalidate("articles")
            logger.info("🗑️ Cache articles invalidé")
        except Exception as e:
            logger.warning(f"Erreur invalidation cache: {e}")

        logger.info(
            f"📊 Scraping terminé: {results['total_articles']} articles uniques, "
            f"{results['total_duplicates']} doublons évités en {results['execution_time_seconds']}s"
        )
        logger.info(
            f"📊 Scraping terminé: {results['total_articles']} articles de "
            f"{results['sites_scraped']}/{len(self.sites_config)} sites en "
            f"{results['execution_time_seconds']}s"
        )
        return results

    # Compat backend
    def run(self) -> Dict[str, Any]:
        return self.scrape_all_sites()

    # --------- Helpers lecture ---------

    def get_todays_articles(self) -> List[Dict[str, Any]]:
        today = datetime.now().strftime("%Y-%m-%d")
        return list(self.articles_collection.find({"date": today}, {"_id": 0}).sort("scraped_at", -1).limit(100))

    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        return list(self.articles_collection.find({"date": date_str}, {"_id": 0}).sort("scraped_at", -1).limit(100))

    def get_scraping_stats(self) -> Dict[str, Any]:
        try:
            total = self.articles_collection.count_documents({})
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = self.articles_collection.count_documents({"date": today})
            pipeline = [{"$group": {"_id": "$site_key", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
            by_site = {x["_id"]: x["count"] for x in self.articles_collection.aggregate(pipeline)}
            last = self.articles_collection.find_one({}, sort=[("scraped_at", -1)])
            return {
                "total_articles": total,
                "today_articles": today_count,
                "articles_by_site": by_site,
                "last_scrape": last["scraped_at"] if last else "Jamais",
            }
        except Exception as e:
            logger.error(f"Erreur stats scraping: {e}")
            return {"error": str(e)}


# Instance globale
guadeloupe_scraper = GuadeloupeScraper()


def run_daily_scraping() -> Dict[str, Any]:
    logger.info("⏰ Lancement du scraping quotidien (manuel)")
    return guadeloupe_scraper.scrape_all_sites()


if __name__ == "__main__":
    result = guadeloupe_scraper.scrape_all_sites()
    print(json.dumps(result, indent=2, ensure_ascii=False))