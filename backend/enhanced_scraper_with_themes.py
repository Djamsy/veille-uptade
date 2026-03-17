"""
Service de scraping des sites d'actualités de Guadeloupe - VERSION CORRIGÉE
Scraping avec classification automatique des thèmes et analyse de sentiment
"""

import os
import re
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse, quote_plus, parse_qs
import concurrent.futures
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

logger = logging.getLogger(__name__)

class GuadeloupeScraper:
    def __init__(self) -> None:
        """Initialise le scraper avec connexion MongoDB sécurisée"""
        self.client = None
        self.db = None
        self.articles_collection = None
        
        # Configuration MongoDB
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        
        try:
            # Connexion MongoDB avec options robustes
            if "mongodb+srv://" in MONGO_URL or "atlas" in MONGO_URL.lower():
                import certifi
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

            # Test de connexion
            self.client.admin.command("ping")
            logger.info("✅ Scraper connecté à MongoDB")

            # Configuration de la base de données
            try:
                dbname = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
                if "mongodb+srv://" in MONGO_URL and ("?" in dbname or not dbname):
                    dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            except Exception:
                dbname = os.environ.get("MONGO_DB_NAME", "veille_media")

            self.db = self.client[dbname]
            
            # Configuration de la collection
            collection_name = os.environ.get("ARTICLES_COLLECTION", "articles_guadeloupe")
            self.articles_collection = self.db[collection_name]
            
            # Vérification explicite de la collection
            if self.articles_collection is None:
                raise RuntimeError("Impossible d'initialiser la collection articles")
            
            # Test d'accès à la collection
            try:
                self.articles_collection.find_one()
                logger.info(f"✅ Collection {collection_name} accessible")
            except Exception as e:
                logger.error(f"❌ Erreur accès collection: {e}")
                raise
                
            logger.info(f"🗄️ Collection d'articles: {collection_name}")

        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB pour scraper: {e}")
            raise

        # Import du classificateur de thèmes (CORRIGÉ)
        self.theme_classifier = None
        self.classify_article_func = None
        
        try:
            from backend.enhanced_scraper_with_themes import classify_article
            self.classify_article_func = classify_article
            self.theme_classifier = True
            logger.info("✅ Classificateur de thèmes intégré au scraper")
        except ImportError:
            try:
                from enhanced_scraper_with_themes import classify_article
                self.classify_article_func = classify_article
                self.theme_classifier = True
                logger.info("✅ Classificateur de thèmes intégré au scraper (fallback)")
            except ImportError:
                logger.warning("⚠️ Classificateur de thèmes non disponible")
                self.classify_article_func = None

        # Configuration des sites
        self.sites_config = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selectors": [
                    "article h2 a", "article h3 a", ".article-title a",
                    ".title a", ".entry-title a", "h2 a", "h3 a"
                ],
                "base_url": "https://www.guadeloupe.franceantilles.fr",
                "kind": "local",
                "rss_urls": [
                    "https://www.guadeloupe.franceantilles.fr/rss.xml",
                    "https://www.guadeloupe.franceantilles.fr/actualite/rss.xml"
                ]
            },
            "rci": {
                "name": "RCI Guadeloupe",
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selectors": [
                    "a[href*='/guadeloupe/infos/']", ".post-title a",
                    ".entry-title a", "h2 a", "h3 a"
                ],
                "base_url": "https://rci.fm",
                "kind": "local",
                "rss_urls": [
                    "https://rci.fm/flux-rss/rss.xml",
                    "https://rci.fm/guadeloupe/flux-rss/rss.xml"
                ]
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selectors": [
                    "a.teaser__title", ".teaser__title a",
                    "article a[href*='/guadeloupe/']",
                    "h2 a[href*='/guadeloupe/']"
                ],
                "base_url": "https://la1ere.franceinfo.fr",
                "kind": "local",
                "rss_urls": [
                    "https://la1ere.franceinfo.fr/guadeloupe/rss"
                ]
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selectors": ["h1 a", "h2 a", "h3 a", "article a"],
                "base_url": "https://www.karibinfo.com",
                "kind": "local",
                "rss_urls": ["https://www.karibinfo.com/feed/"]
            }
        }

        # User agents pour rotation
        self.headers_list = [
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5"
            },
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.8,en-US;q=0.5"
            }
        ]
        self.current_header_index = 0

    def get_next_headers(self) -> Dict[str, str]:
        """Rotation des user agents"""
        headers = self.headers_list[self.current_header_index]
        self.current_header_index = (self.current_header_index + 1) % len(self.headers_list)
        return headers

    def clean_title(self, title: str) -> str:
        """Nettoie un titre d'article"""
        if not title:
            return ""
        title = re.sub(r"[\n\r\t]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        
        # Supprime les préfixes courants
        prefixes = ["LIRE AUSSI:", "VOIR AUSSI:", "À LIRE:", "VIDÉO:", "PHOTO:", "EN DIRECT:"]
        for prefix in prefixes:
            if title.upper().startswith(prefix):
                title = title[len(prefix):].strip()
        return title

    def make_id(self, site_key: str, url: str) -> str:
        """Génère un ID unique pour un article"""
        return f"{site_key}_{hashlib.md5(url.encode('utf-8')).hexdigest()}"

    def is_valid_article_url(self, url: str, base_domain: str, site_key: str = "") -> bool:
        """Vérifie si une URL est valide pour un article"""
        if not url:
            return False

        # Mots-clés à ignorer
        ignore_patterns = [
            "/tag/", "/category/", "/author/", "/search/", "/contact/", "/about/",
            "javascript:", "mailto:", "#", "tel:", "/videos", "/live/"
        ]
        
        for pattern in ignore_patterns:
            if pattern in url.lower():
                return False

        # Règles spécifiques par site
        if "rci.fm" in base_domain:
            return "/infos/" in url and len(url.split("/")[-1]) > 10
        elif "la1ere.franceinfo.fr" in base_domain:
            return "/guadeloupe/" in url and url.count("/") >= 4
        elif "karibinfo.com" in base_domain:
            return any(cat in url for cat in ["/news/", "/actualite/", "/politique/"])
        elif "guadeloupe.franceantilles.fr" in base_domain:
            return "/actualite/" in url.lower()

        return True

    def _classify_article(self, title: str, content: str = "", url: str = "") -> Dict[str, Any]:
        """Classifie un article par thème avec fallback"""
        if self.classify_article_func:
            try:
                return self.classify_article_func(title, content, url)
            except Exception as e:
                logger.warning(f"Erreur classification automatique: {e}")
        
        # Classification simple par mots-clés en fallback
        themes_keywords = {
            'politique': ['maire', 'conseil', 'député', 'élection', 'vote', 'politique'],
            'économie': ['emploi', 'entreprise', 'commerce', 'économie', 'budget'],
            'culture': ['festival', 'musique', 'culture', 'art', 'créole'],
            'social': ['santé', 'éducation', 'famille', 'social', 'école'],
            'environnement': ['sargasses', 'pollution', 'environnement', 'mer'],
            'sécurité': ['police', 'accident', 'violence', 'sécurité'],
            'sport': ['sport', 'football', 'basket', 'compétition']
        }
        
        text = f"{title} {content}".lower()
        detected_themes = []
        dominant_theme = 'général'
        max_matches = 0
        
        for theme, keywords in themes_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in text)
            if matches > 0:
                detected_themes.append(theme)
                if matches > max_matches:
                    max_matches = matches
                    dominant_theme = theme
        
        # Détection zones géographiques basique
        zones = []
        zone_keywords = {
            'pointe_a_pitre': ['pointe-à-pitre', 'pap'],
            'basse_terre': ['basse-terre'],
            'les_abymes': ['abymes'],
            'baie_mahault': ['baie-mahault']
        }
        
        for zone, keywords in zone_keywords.items():
            if any(keyword in text for keyword in keywords):
                zones.append(zone)
        
        return {
            'dominant_theme': dominant_theme,
            'themes': detected_themes if detected_themes else ['général'],
            'zones': zones,
            'classification_score': min(1.0, max_matches / 3),
            'classification_method': 'fallback_keywords',
            'classified_at': datetime.now().isoformat()
        }

    def scrape_rci_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour RCI Guadeloupe"""
        articles = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if (href.startswith("/guadeloupe/infos/") and 
                    len(text) > 15 and 
                    not any(x in href.lower() for x in ["toutes-les-infos", "vakans-opeyi"])):
                    
                    full_url = "https://rci.fm" + href
                    title = self.clean_title(text)
                    
                    if len(title) > 10:
                        # Classification automatique
                        classification = self._classify_article(title, "", full_url)
                        
                        article = {
                            "id": self.make_id("rci", full_url),
                            "title": title,
                            "url": full_url,
                            "source": "RCI Guadeloupe",
                            "site_key": "rci",
                            "scraped_at": datetime.now().isoformat(),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "scraped_from_page": url,
                            "kind": "local",
                            # Ajout des données de classification
                            "dominant_theme": classification['dominant_theme'],
                            "themes": classification['themes'],
                            "zones": classification['zones'],
                            "classification_score": classification['classification_score'],
                            "classification_method": classification['classification_method'],
                            "classified_at": classification['classified_at']
                        }
                        articles.append(article)

            # Déduplication
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)
            
            logger.info(f"✅ RCI Guadeloupe: {len(unique_articles)} articles trouvés")
            return unique_articles[:20]
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping RCI: {e}")
            return []

    def scrape_france_antilles_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour France-Antilles"""
        articles = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            selectors = ["article h2 a", "article h3 a", "h2 a", "h3 a"]
            for selector in selectors:
                for link in soup.select(selector):
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    
                    if (href.startswith("/actualite/") and 
                        len(text) > 15 and
                        not any(x in href.lower() for x in ["hub-economie/", "tour-de-la-guadeloupe"])):
                        
                        full_url = "https://www.guadeloupe.franceantilles.fr" + href
                        title = self.clean_title(text)
                        
                        if 10 < len(title) < 200:
                            classification = self._classify_article(title, "", full_url)
                            
                            article = {
                                "id": self.make_id("france_antilles", full_url),
                                "title": title,
                                "url": full_url,
                                "source": "France-Antilles Guadeloupe",
                                "site_key": "france_antilles",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                                "kind": "local",
                                "dominant_theme": classification['dominant_theme'],
                                "themes": classification['themes'],
                                "zones": classification['zones'],
                                "classification_score": classification['classification_score'],
                                "classification_method": classification['classification_method'],
                                "classified_at": classification['classified_at']
                            }
                            articles.append(article)

            # Déduplication
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)
            
            logger.info(f"✅ France-Antilles: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping France-Antilles: {e}")
            return []

    def scrape_la1ere_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour La 1ère Guadeloupe"""
        articles = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if ("/guadeloupe/" in href and 
                    len(text) > 15 and 
                    href.count("/") >= 4 and
                    not any(x in href.lower() for x in ["direct-tv", "replay"])):
                    
                    full_url = href if href.startswith("http") else "https://la1ere.franceinfo.fr" + href
                    title = self.clean_title(text)
                    
                    if len(title) > 10:
                        classification = self._classify_article(title, "", full_url)
                        
                        article = {
                            "id": self.make_id("la1ere", full_url),
                            "title": title,
                            "url": full_url,
                            "source": "La 1ère Guadeloupe",
                            "site_key": "la1ere",
                            "scraped_at": datetime.now().isoformat(),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "scraped_from_page": url,
                            "kind": "local",
                            "dominant_theme": classification['dominant_theme'],
                            "themes": classification['themes'],
                            "zones": classification['zones'],
                            "classification_score": classification['classification_score'],
                            "classification_method": classification['classification_method'],
                            "classified_at": classification['classified_at']
                        }
                        articles.append(article)

            # Déduplication
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)
            
            logger.info(f"✅ La 1ère Guadeloupe: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping La 1ère: {e}")
            return []

    def scrape_karibinfo_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour KaribInfo"""
        articles = []
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            selectors = ["h1 a", "h2 a", "h3 a", "article a"]
            for selector in selectors:
                for link in soup.select(selector):
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    
                    if (href.startswith("https://www.karibinfo.com/news/") and
                        len(text) > 15 and
                        "." in text and
                        not any(x in href.lower() for x in ["author/", "category/"])):
                        
                        title = self.clean_title(text)
                        
                        if 10 < len(title) < 200:
                            classification = self._classify_article(title, "", href)
                            
                            article = {
                                "id": self.make_id("karibinfo", href),
                                "title": title,
                                "url": href,
                                "source": "KaribInfo",
                                "site_key": "karibinfo",
                                "scraped_at": datetime.now().isoformat(),
                                "date": datetime.now().strftime("%Y-%m-%d"),
                                "scraped_from_page": url,
                                "kind": "local",
                                "dominant_theme": classification['dominant_theme'],
                                "themes": classification['themes'],
                                "zones": classification['zones'],
                                "classification_score": classification['classification_score'],
                                "classification_method": classification['classification_method'],
                                "classified_at": classification['classified_at']
                            }
                            articles.append(article)

            # Déduplication
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    unique_articles.append(article)
            
            logger.info(f"✅ KaribInfo: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping KaribInfo: {e}")
            return []

    def scrape_page(self, url: str, site_key: str) -> List[Dict[str, Any]]:
        """Scrape une page selon le site"""
        if site_key == "rci":
            return self.scrape_rci_articles(url)
        elif site_key == "la1ere":
            return self.scrape_la1ere_articles(url)
        elif site_key == "karibinfo":
            return self.scrape_karibinfo_articles(url)
        elif site_key == "france_antilles":
            return self.scrape_france_antilles_articles(url)
        else:
            logger.warning(f"Site non supporté: {site_key}")
            return []

    def is_duplicate_article(self, new_article: Dict[str, Any]) -> bool:
        """Vérifie si un article est un doublon"""
        try:
            if self.articles_collection is None:
                logger.warning("Collection articles non disponible")
                return False
            
            # Vérification par ID
            if self.articles_collection.find_one({"id": new_article["id"]}):
                return True
                
            # Vérification par URL
            if new_article.get("url") and self.articles_collection.find_one({"url": new_article["url"]}):
                return True

            # Vérification par hash de contenu si disponible
            if new_article.get("content"):
                content_hash = hashlib.md5(new_article["content"].encode("utf-8", errors="ignore")).hexdigest()
                if self.articles_collection.find_one({"content_hash": content_hash}):
                    return True
                new_article["content_hash"] = content_hash

            return False
            
        except Exception as e:
            logger.warning(f"Erreur vérification doublon: {e}")
            return False

    def _save_article_with_classification(self, article: Dict[str, Any]) -> bool:
        """Sauvegarde un article avec sa classification en base"""
        try:
            if self.articles_collection is None:
                logger.error("Collection non disponible pour sauvegarde")
                return False
                
            if not self.is_duplicate_article(article):
                self.articles_collection.update_one(
                    {"id": article["id"]}, 
                    {"$set": article}, 
                    upsert=True
                )
                return True
            return False
            
        except Exception as e:
            logger.warning(f"Erreur sauvegarde article: {e}")
            return False

    def _find_similar_titles(self) -> int:
        """Supprime les articles aux titres similaires"""
        try:
            if self.articles_collection is None:
                logger.warning("Collection non disponible pour nettoyage")
                return 0
                
            since = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            recent = list(
                self.articles_collection.find({"date": {"$gte": since}}).sort("scraped_at", -1)
            )
            
            removed = 0
            processed = set()

            for i, article1 in enumerate(recent):
                if article1["_id"] in processed:
                    continue
                    
                for article2 in recent[i + 1:]:
                    if article2["_id"] in processed:
                        continue
                        
                    if (article1.get("source") == article2.get("source") and 
                        article1.get("title") and article2.get("title")):
                        
                        title1 = re.sub(r"[^\w\s]", " ", article1["title"].lower())
                        title2 = re.sub(r"[^\w\s]", " ", article2["title"].lower())
                        
                        similarity = SequenceMatcher(None, title1, title2).ratio()
                        if similarity >= 0.92:
                            # Garde le plus récent
                            older = article2 if article1.get("scraped_at", "") > article2.get("scraped_at", "") else article1
                            self.articles_collection.delete_one({"_id": older["_id"]})
                            processed.add(older["_id"])
                            removed += 1
                            
            return removed
            
        except Exception as e:
            logger.warning(f"Erreur détection titres similaires: {e}")
            return 0

    def scrape_all_sites(self) -> Dict[str, Any]:
        """Scraper principal orchestrant tous les sites"""
        logger.info("🚀 Début du scraping (Guadeloupe avec classification thématique)")
        start_time = time.time()
        
        results = {
            "success": True,
            "scraped_at": datetime.now().isoformat(),
            "sites_scraped": 0,
            "total_articles": 0,
            "total_saved": 0,
            "total_duplicates": 0,
            "articles_by_site": {},
            "duplicates_by_site": {},
            "classification_stats": {
                "total_classified": 0,
                "themes_detected": {},
                "zones_detected": {}
            },
            "errors": [],
            "execution_time_seconds": 0
        }

        for site_key, config in self.sites_config.items():
            try:
                logger.info(f"🔍 Scraping {config['name']}")
                articles = self.scrape_page(config["url"], site_key)
                
                saved_count = 0
                duplicate_count = 0
                classified_count = 0
                
                for article in articles:
                    try:
                        if self._save_article_with_classification(article):
                            saved_count += 1
                            
                            # Statistiques de classification
                            if article.get('dominant_theme'):
                                classified_count += 1
                                theme = article['dominant_theme']
                                results['classification_stats']['themes_detected'][theme] = \
                                    results['classification_stats']['themes_detected'].get(theme, 0) + 1
                                
                                for zone in article.get('zones', []):
                                    results['classification_stats']['zones_detected'][zone] = \
                                        results['classification_stats']['zones_detected'].get(zone, 0) + 1
                        else:
                            duplicate_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Erreur traitement article: {e}")

                results["articles_by_site"][site_key] = saved_count
                results["duplicates_by_site"][site_key] = duplicate_count
                results["sites_scraped"] += 1
                results["total_saved"] += saved_count
                results["total_duplicates"] += duplicate_count
                results["classification_stats"]["total_classified"] += classified_count
                
                logger.info(f"✅ {config['name']}: {saved_count} sauvegardés, {duplicate_count} doublons, {classified_count} classifiés")
                time.sleep(1.0)  # Pause entre sites
                
            except Exception as e:
                error_msg = f"Erreur {config['name']}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)

        # Nettoyage des titres similaires
        try:
            removed_similar = self._find_similar_titles()
            if removed_similar:
                logger.info(f"🧹 {removed_similar} doublons supprimés par similarité")
        except Exception as e:
            logger.warning(f"Erreur nettoyage similarité: {e}")

        results["total_articles"] = results["total_saved"]
        results["execution_time_seconds"] = round(time.time() - start_time, 2)

        # Invalidation du cache si disponible
        try:
            from backend.cache_service import cache_invalidate
            cache_invalidate("articles")
            logger.info("🗑️ Cache articles invalidé")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Erreur invalidation cache: {e}")

        logger.info(
            f"📊 Scraping terminé: {results['total_saved']} articles sauvegardés, "
            f"{results['total_duplicates']} doublons évités, "
            f"{results['classification_stats']['total_classified']} classifiés en "
            f"{results['execution_time_seconds']}s"
        )
        
        return results

    def run(self) -> Dict[str, Any]:
        """Interface de compatibilité"""
        return self.scrape_all_sites()

    def get_todays_articles(self) -> List[Dict[str, Any]]:
        """Récupère les articles du jour"""
        try:
            if self.articles_collection is None:
                return []
                
            today = datetime.now().strftime("%Y-%m-%d")
            return list(
                self.articles_collection
                .find({"date": today}, {"_id": 0})
                .sort("scraped_at", -1)
                .limit(100)
            )
        except Exception as e:
            logger.error(f"Erreur récupération articles du jour: {e}")
            return []

    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Récupère les articles d'une date donnée"""
        try:
            if self.articles_collection is None:
                return []
                
            return list(
                self.articles_collection
                .find({"date": date_str}, {"_id": 0})
                .sort("scraped_at", -1)
                .limit(100)
            )
        except Exception as e:
            logger.error(f"Erreur récupération articles pour {date_str}: {e}")
            return []

    def get_scraping_stats(self) -> Dict[str, Any]:
        """Récupère les statistiques de scraping"""
        try:
            if self.articles_collection is None:
                return {"error": "Collection non disponible"}
                
            total = self.articles_collection.count_documents({})
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = self.articles_collection.count_documents({"date": today})
            
            # Statistiques par site
            pipeline = [
                {"$group": {"_id": "$site_key", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            by_site = {x["_id"]: x["count"] for x in self.articles_collection.aggregate(pipeline)}
            
            # Statistiques par thème
            theme_pipeline = [
                {"$group": {"_id": "$dominant_theme", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            by_theme = {x["_id"]: x["count"] for x in self.articles_collection.aggregate(theme_pipeline)}
            
            # Dernier scraping
            last_article = self.articles_collection.find_one({}, sort=[("scraped_at", -1)])
            
            return {
                "total_articles": total,
                "today_articles": today_count,
                "articles_by_site": by_site,
                "articles_by_theme": by_theme,
                "last_scrape": last_article["scraped_at"] if last_article else "Jamais",
                "classification_available": self.theme_classifier is not None
            }
            
        except Exception as e:
            logger.error(f"Erreur stats scraping: {e}")
            return {"error": str(e)}

    def get_theme_statistics(self) -> Dict[str, Any]:
        """Récupère les statistiques de classification par thème"""
        try:
            if self.articles_collection is None:
                return {"error": "Collection non disponible"}
                
            # Articles classifiés vs non classifiés
            total_articles = self.articles_collection.count_documents({})
            classified_articles = self.articles_collection.count_documents({
                "dominant_theme": {"$exists": True, "$ne": "général"}
            })
            
            # Répartition par thème
            theme_pipeline = [
                {"$match": {"dominant_theme": {"$exists": True}}},
                {"$group": {"_id": "$dominant_theme", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            themes_distribution = list(self.articles_collection.aggregate(theme_pipeline))
            
            # Répartition par zone
            zone_pipeline = [
                {"$unwind": "$zones"},
                {"$group": {"_id": "$zones", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            zones_distribution = list(self.articles_collection.aggregate(zone_pipeline))
            
            return {
                "total_articles": total_articles,
                "classified_articles": classified_articles,
                "classification_rate": round((classified_articles / total_articles) * 100, 1) if total_articles > 0 else 0,
                "themes_distribution": themes_distribution,
                "zones_distribution": zones_distribution,
                "classifier_available": self.theme_classifier is not None
            }
            
        except Exception as e:
            logger.error(f"Erreur statistiques thèmes: {e}")
            return {"error": str(e)}


# Instance globale
guadeloupe_scraper = GuadeloupeScraper()

def run_daily_scraping() -> Dict[str, Any]:
    """Fonction de compatibilité pour lancer le scraping quotidien"""
    logger.info("⏰ Lancement du scraping quotidien avec classification")
    return guadeloupe_scraper.scrape_all_sites()

if __name__ == "__main__":
    result = guadeloupe_scraper.scrape_all_sites()
    print(json.dumps(result, indent=2, ensure_ascii=False))