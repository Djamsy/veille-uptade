"""
Service de scraping des sites d'actualités de Guadeloupe - VERSION AMÉLIORÉE
Scraping automatique à 10H chaque jour avec tous les articles
"""
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from typing import List, Dict, Any
import time
from pymongo import MongoClient
import os
import logging
import concurrent.futures
from urllib.parse import urljoin, urlparse
import re
import hashlib
from difflib import SequenceMatcher

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GuadeloupeScraper:
    def __init__(self):
        # MongoDB connection - Compatible Atlas et local
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        
        try:
            if 'mongodb+srv://' in MONGO_URL or 'atlas' in MONGO_URL.lower():
                # Configuration optimisée pour MongoDB Atlas
                self.client = MongoClient(
                    MONGO_URL,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    maxPoolSize=10,
                    retryWrites=True
                )
            else:
                # Configuration pour MongoDB local
                self.client = MongoClient(MONGO_URL)
                
            self.db = self.client.veille_media
            self.articles_collection = self.db.articles_guadeloupe
            
            # Test de connection
            self.client.admin.command('ping')
            logger.info("✅ Scraper connecté à MongoDB")
            
        except Exception as e:
            logger.error(f"❌ Erreur connection MongoDB pour scraper: {e}")
            # En cas d'erreur, utiliser une configuration par défaut
            self.client = MongoClient('mongodb://localhost:27017')
            self.db = self.client.veille_media
            self.articles_collection = self.db.articles_guadeloupe
        
        # Sites à scraper avec sélecteurs multiples améliorés et testés
        self.sites_config = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selectors": [
                    "article h2 a", "article h3 a", ".article-title a", 
                    ".title a", ".entry-title a", "h2 a", "h3 a",
                    ".post-title a", ".content-title a", ".news-title a"
                ],
                "base_url": "https://www.guadeloupe.franceantilles.fr"
            },
            "rci": {
                "name": "RCI Guadeloupe", 
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selectors": [
                    "a[href*='/guadeloupe/infos/']",  # Sélecteur principal pour RCI
                    ".post-title a", ".entry-title a", "h2 a", "h3 a",
                    ".article-title a", ".content-title a", ".news-item a"
                ],
                "base_url": "https://rci.fm"
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selectors": [
                    ".teaser__title a", ".article-title a", "h2 a", "h3 a",
                    ".content-title a", ".post-title a", ".entry-title a",
                    ".news-title a", ".item-title a", "a[href*='/guadeloupe/']"
                ],
                "base_url": "https://la1ere.franceinfo.fr"
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selectors": [
                    "h1 a", "h2 a", "h3 a", "article a", ".post a",
                    ".post-title a", ".entry-title a", ".title a", 
                    ".article-title a", ".content-title a", ".news-title a",
                    "a[href*='/news/']", "a[href*='/actualite/']", "a[href*='/societe/']"
                ],
                "base_url": "https://www.karibinfo.com"
            }
        }
        
        # Headers pour éviter le blocage avec rotation
        self.headers_list = [
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none'
            },
            {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            },
            {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'fr,en-US;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br'
            }
        ]
        
        self.current_header_index = 0

    def get_next_headers(self):
        """Rotation des headers pour éviter la détection"""
        headers = self.headers_list[self.current_header_index]
        self.current_header_index = (self.current_header_index + 1) % len(self.headers_list)
        return headers

    def clean_title(self, title: str) -> str:
        """Nettoyer le titre de l'article"""
        if not title:
            return ""
        
        # Supprimer les caractères indésirables
        title = re.sub(r'[\n\r\t]+', ' ', title)
        title = re.sub(r'\s+', ' ', title)
        title = title.strip()
        
        # Supprimer les prefixes courants
        prefixes_to_remove = [
            "LIRE AUSSI:", "VOIR AUSSI:", "À LIRE:", "VIDÉO:",
            "PHOTO:", "EN DIRECT:", "BREAKING:", "URGENT:"
        ]
        
        for prefix in prefixes_to_remove:
            if title.upper().startswith(prefix):
                title = title[len(prefix):].strip()
        
        return title

    def is_valid_article_url(self, url: str, base_domain: str) -> bool:
        """Vérifier si l'URL est valide pour un article"""
        if not url:
            return False
        
        # URLs à ignorer
        ignore_patterns = [
            '/tag/', '/category/', '/author/', '/page/',
            '/search/', '/archives/', '/contact/', '/about/',
            'javascript:', 'mailto:', '#', 'tel:', '/vakans-opeyi',
            '/tour-cycliste', '/informations-pratiques'
        ]
        
        for pattern in ignore_patterns:
            if pattern in url.lower():
                return False
        
        # Vérifier que c'est bien un article du domaine
        parsed_url = urlparse(url)
        if parsed_url.netloc and base_domain not in parsed_url.netloc:
            return False
        
        # Vérifications spécifiques par site
        if 'rci.fm' in base_domain:
            # Pour RCI, accepter seulement les URLs avec /infos/ et une longueur minimum
            return '/infos/' in url and len(url.split('/')[-1]) > 10
        elif 'la1ere.franceinfo.fr' in base_domain:
            # Pour La 1ère, accepter les URLs avec /guadeloupe/
            return '/guadeloupe/' in url and url.count('/') >= 4
        elif 'karibinfo.com' in base_domain:
            # Pour KaribInfo, accepter les URLs avec news, actualite, politique, société
            return any(cat in url for cat in ['/news/', '/actualite/', '/politique/', '/societe/', '/economie/'])
        
        return True

    def scrape_rci_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour RCI Guadeloupe"""
        articles = []
        
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            
            response = session.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trouver tous les liens
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filtrer spécifiquement pour RCI
                if (href.startswith('/guadeloupe/infos/') and 
                    len(text) > 15 and 
                    not any(x in href.lower() for x in ['informations-pratiques', 'toutes-les-infos', 'vakans-opeyi', 'tour-cycliste'])):
                    
                    # Construire l'URL complète
                    full_url = 'https://rci.fm' + href
                    title = self.clean_title(text)
                    
                    if len(title) > 10:  # Titre minimum
                        article = {
                            'id': f"rci_{hash(full_url)}",
                            'title': title,
                            'url': full_url,
                            'source': 'RCI Guadeloupe',
                            'site_key': 'rci',
                            'scraped_at': datetime.now().isoformat(),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_from_page': url
                        }
                        articles.append(article)
            
            # Supprimer les doublons
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"✅ RCI Guadeloupe: {len(unique_articles)} articles trouvés")
            return unique_articles[:20]  # Limiter à 20 articles
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping RCI: {e}")
            return []

    def scrape_france_antilles_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour France-Antilles Guadeloupe"""
        articles = []
        
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            
            response = session.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trouver tous les liens dans des éléments article et h2/h3
            article_selectors = ['article h2 a', 'article h3 a', 'h2 a', 'h3 a']
            
            for selector in article_selectors:
                elements = soup.select(selector)
                for link in elements:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # Filtrer spécifiquement pour France-Antilles
                    if (href.startswith('/actualite/') and 
                        len(text) > 15 and 
                        not any(x in href.lower() for x in ['hub-economie/', 'sports/tour-de-la-guadeloupe/', 'environnement/saison-cyclonique/']) and
                        not any(x in text.lower() for x in ['hub éco', 'tour de guadeloupe', 'saison cyclonique'])):
                        
                        # Construire l'URL complète
                        full_url = 'https://www.guadeloupe.franceantilles.fr' + href
                        title = self.clean_title(text)
                        
                        if len(title) > 10 and len(title) < 200:  # Titre raisonnable
                            article = {
                                'id': f"france_antilles_{hash(full_url)}",
                                'title': title,
                                'url': full_url,
                                'source': 'France-Antilles Guadeloupe',
                                'site_key': 'france_antilles',
                                'scraped_at': datetime.now().isoformat(),
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'scraped_from_page': url
                            }
                            articles.append(article)
            
            # Supprimer les doublons
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"✅ France-Antilles Guadeloupe: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]  # Limiter à 15 articles
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping France-Antilles: {e}")
            return []

    def scrape_karibinfo_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour KaribInfo"""
        articles = []
        
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            
            response = session.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trouver tous les liens dans des éléments h1, h2, h3, article
            article_selectors = ['h1 a', 'h2 a', 'h3 a', 'article a']
            
            for selector in article_selectors:
                elements = soup.select(selector)
                for link in elements:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    # Filtrer spécifiquement pour KaribInfo - cibler les vraies nouvelles
                    if (href.startswith('https://www.karibinfo.com/news/') and 
                        len(text) > 15 and 
                        '.' in text and  # Articles ont généralement des points
                        not any(x in href.lower() for x in ['author/', 'category/', 'tag/', 'page/']) and
                        not any(x in text.lower() for x in ['karibinfo.com', 'actualité', 'newsletter'])):
                        
                        full_url = href
                        title = self.clean_title(text)
                        
                        if len(title) > 10 and len(title) < 200:  # Titre raisonnable
                            article = {
                                'id': f"karibinfo_{hash(full_url)}",
                                'title': title,
                                'url': full_url,
                                'source': 'KaribInfo',
                                'site_key': 'karibinfo',
                                'scraped_at': datetime.now().isoformat(),
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'scraped_from_page': url
                            }
                            articles.append(article)
            
            # Supprimer les doublons
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"✅ KaribInfo: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]  # Limiter à 15 articles
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping KaribInfo: {e}")
            return []

    def scrape_page(self, url: str, site_key: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """Scraper une page spécifique"""
        
        # Utilisers des scrapers spécialisés pour certains sites
        if site_key == 'rci':
            return self.scrape_rci_articles(url)
        elif site_key == 'la1ere':
            return self.scrape_la1ere_articles(url)
        elif site_key == 'karibinfo':
            return self.scrape_karibinfo_articles(url)
        elif site_key == 'france_antilles':
            return self.scrape_france_antilles_articles(url)
        
        config = self.sites_config[site_key]
        articles = []
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔍 Scraping {url} (tentative {attempt + 1})")
                
                # Session avec headers rotatifs
                session = requests.Session()
                session.headers.update(self.get_next_headers())
                
                response = session.get(url, timeout=20)
                response.raise_for_status()
                
                # Parser le HTML
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Essayer tous les sélecteurs
                all_links = []
                for selector in config['selectors']:
                    try:
                        links = soup.select(selector)
                        all_links.extend(links)
                    except Exception as e:
                        logger.debug(f"Sélecteur {selector} échoué: {e}")
                        continue
                
                # Dédupliquer les liens
                seen_urls = set()
                unique_links = []
                for link in all_links:
                    href = link.get('href')
                    if href and href not in seen_urls:
                        seen_urls.add(href)
                        unique_links.append(link)
                
                logger.info(f"📝 {len(unique_links)} liens trouvés sur {url}")
                
                # Traiter chaque lien
                for link in unique_links:
                    try:
                        title = self.clean_title(link.get_text())
                        href = link.get('href')
                        
                        if not title or not href or len(title) < 10:
                            continue
                        
                        # Construire l'URL complète
                        if href.startswith('http'):
                            full_url = href
                        else:
                            full_url = urljoin(config['base_url'], href)
                        
                        # Vérifier la validité de l'URL
                        if not self.is_valid_article_url(full_url, config['base_url']):
                            continue
                        
                        # Créer l'article
                        article = {
                            'id': f"{site_key}_{hash(full_url)}",
                            'title': title,
                            'url': full_url,
                            'source': config['name'],
                            'site_key': site_key,
                            'scraped_at': datetime.now().isoformat(),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_from_page': url
                        }
                        
                        articles.append(article)
                        
                    except Exception as e:
                        logger.warning(f"Erreur traitement lien: {e}")
                        continue
                
                logger.info(f"✅ {len(articles)} articles valides trouvés sur {url}")
                return articles
                
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout pour {url} (tentative {attempt + 1})")
                time.sleep(2 ** attempt)  # Backoff exponentiel
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 Erreur réseau pour {url}: {e}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"❌ Erreur inattendue pour {url}: {e}")
                break
        
        logger.error(f"❌ Échec scraping {url} après {max_retries} tentatives")
        return []

    def scrape_la1ere_articles(self, url: str) -> List[Dict[str, Any]]:
        """Scraper spécialisé pour La 1ère Guadeloupe"""
        articles = []
        
        try:
            session = requests.Session()
            session.headers.update(self.get_next_headers())
            
            response = session.get(url, timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trouver tous les liens
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filtrer spécifiquement pour La 1ère
                if ('/guadeloupe/' in href and 
                    len(text) > 15 and 
                    href.count('/') >= 4 and
                    not any(x in href.lower() for x in ['direct-tv', 'programme-audio', 'replay'])):
                    
                    # Construire l'URL complète si nécessaire
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = 'https://la1ere.franceinfo.fr' + href
                    
                    title = self.clean_title(text)
                    
                    if len(title) > 10:  # Titre minimum
                        article = {
                            'id': f"la1ere_{hash(full_url)}",
                            'title': title,
                            'url': full_url,
                            'source': 'La 1ère Guadeloupe',
                            'site_key': 'la1ere',
                            'scraped_at': datetime.now().isoformat(),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_from_page': url
                        }
                        articles.append(article)
            
            # Supprimer les doublons
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"✅ La 1ère Guadeloupe: {len(unique_articles)} articles trouvés")
            return unique_articles[:15]  # Limiter à 15 articles
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping La 1ère: {e}")
            return []

    def scrape_site(self, site_key: str) -> List[Dict[str, Any]]:
        """Scraper un site complet avec toutes ses pages"""
        config = self.sites_config[site_key]
        all_articles = []
        
        try:
            logger.info(f"🚀 Début scraping complet: {config['name']}")
            
            # Pages à scraper
            pages_to_scrape = [config['url']] + config.get('additional_pages', [])
            
            # Scraper en parallèle pour plus d'efficacité
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_url = {
                    executor.submit(self.scrape_page, url, site_key): url
                    for url in pages_to_scrape
                }
                
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        articles = future.result(timeout=30)
                        all_articles.extend(articles)
                        logger.info(f"📄 {len(articles)} articles de {url}")
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"⏰ Timeout pour {url}")
                    except Exception as e:
                        logger.error(f"❌ Erreur pour {url}: {e}")
            
            # Dédupliquer les articles par URL
            seen_urls = set()
            unique_articles = []
            for article in all_articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"✅ Total {config['name']}: {len(unique_articles)} articles uniques")
            return unique_articles
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping {config['name']}: {e}")
            return []

    def is_duplicate_article(self, new_article: Dict[str, Any]) -> bool:
        """
        Détection avancée de doublons d'articles
        Vérifie plusieurs critères : ID, URL, titre similaire, contenu similaire
        """
        try:
            # 1. Vérification par ID (déjà unique)
            if self.articles_collection.find_one({'id': new_article['id']}):
                logger.debug(f"Doublon détecté par ID: {new_article['id']}")
                return True
            
            # 2. Vérification par URL exacte
            if new_article.get('url') and self.articles_collection.find_one({'url': new_article['url']}):
                logger.debug(f"Doublon détecté par URL: {new_article['url']}")
                return True
            
            # 3. Vérification par titre similaire (même source, même date)
            if new_article.get('title'):
                # Rechercher des articles de la même source et date
                same_source_date = self.articles_collection.find({
                    'source': new_article.get('source'),
                    'date': new_article.get('date')
                })
                
                for existing_article in same_source_date:
                    if existing_article.get('title'):
                        # Calculer la similarité des titres (seuil 85%)
                        similarity = SequenceMatcher(None, 
                            new_article['title'].lower().strip(),
                            existing_article['title'].lower().strip()
                        ).ratio()
                        
                        if similarity > 0.85:
                            logger.debug(f"Doublon détecté par titre similaire ({similarity:.2%}): {new_article['title'][:50]}...")
                            return True
            
            # 4. Vérification par hash du contenu (si disponible)
            if new_article.get('content'):
                content_hash = hashlib.md5(
                    new_article['content'].encode('utf-8', errors='ignore')
                ).hexdigest()
                
                if self.articles_collection.find_one({'content_hash': content_hash}):
                    logger.debug(f"Doublon détecté par hash contenu: {content_hash}")
                    return True
                
                # Ajouter le hash pour les futures vérifications
                new_article['content_hash'] = content_hash
            
            return False
            
        except Exception as e:
            logger.warning(f"Erreur vérification doublon: {e}")
            return False

    def normalize_title(self, title: str) -> str:
        """Normalise un titre pour une meilleure comparaison"""
        if not title:
            return ""
        
        # Supprimer la ponctuation excessive, espaces multiples
        normalized = re.sub(r'[^\w\s]', ' ', title.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def clean_duplicate_articles(self) -> Dict[str, Any]:
        """
        Nettoie les doublons existants dans la base de données
        Garde le plus récent en cas de doublons
        """
        try:
            logger.info("🧹 Démarrage du nettoyage des doublons...")
            
            # Grouper par URL et titre similaire
            pipeline = [
                {
                    "$group": {
                        "_id": {
                            "url": "$url",
                            "source": "$source"
                        },
                        "articles": {"$push": "$$ROOT"},
                        "count": {"$sum": 1}
                    }
                },
                {
                    "$match": {"count": {"$gt": 1}}
                }
            ]
            
            duplicates_by_url = list(self.articles_collection.aggregate(pipeline))
            removed_count = 0
            
            for group in duplicates_by_url:
                articles = group['articles']
                # Garder le plus récent (par date de scraping ou _id)
                articles_sorted = sorted(articles, 
                    key=lambda x: x.get('scraped_at', x.get('_id')), 
                    reverse=True
                )
                
                # Supprimer tous sauf le plus récent
                for article_to_remove in articles_sorted[1:]:
                    self.articles_collection.delete_one({'_id': article_to_remove['_id']})
                    removed_count += 1
                    logger.debug(f"Doublon supprimé: {article_to_remove.get('title', 'Sans titre')[:50]}...")
            
            # Nettoyer aussi par titre similaire
            title_duplicates = self._find_similar_titles()
            removed_count += title_duplicates
            
            logger.info(f"🧹 Nettoyage terminé: {removed_count} doublons supprimés")
            
            return {
                'success': True,
                'removed_count': removed_count,
                'message': f"{removed_count} doublons supprimés avec succès"
            }
            
        except Exception as e:
            logger.error(f"Erreur nettoyage doublons: {e}")
            return {
                'success': False,
                'error': str(e),
                'removed_count': 0
            }

    def _find_similar_titles(self) -> int:
        """Trouve et supprime les articles avec des titres très similaires"""
        try:
            # Récupérer tous les articles récents (7 derniers jours)
            from datetime import timedelta
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            recent_articles = list(self.articles_collection.find({
                'date': {'$gte': week_ago}
            }).sort('scraped_at', -1))
            
            removed_count = 0
            processed_ids = set()
            
            for i, article1 in enumerate(recent_articles):
                if article1['_id'] in processed_ids:
                    continue
                    
                for j, article2 in enumerate(recent_articles[i+1:], i+1):
                    if article2['_id'] in processed_ids:
                        continue
                    
                    # Comparer les titres si même source
                    if (article1.get('source') == article2.get('source') and 
                        article1.get('title') and article2.get('title')):
                        
                        similarity = SequenceMatcher(None,
                            self.normalize_title(article1['title']),
                            self.normalize_title(article2['title'])
                        ).ratio()
                        
                        if similarity > 0.90:  # 90% de similarité
                            # Garder le plus récent
                            older_article = (article2 if article1.get('scraped_at', '') > article2.get('scraped_at', '') 
                                           else article1)
                            
                            self.articles_collection.delete_one({'_id': older_article['_id']})
                            processed_ids.add(older_article['_id'])
                            removed_count += 1
                            
                            logger.debug(f"Titre similaire supprimé ({similarity:.2%}): {older_article.get('title', '')[:50]}...")
            
            return removed_count
            
        except Exception as e:
            logger.warning(f"Erreur détection titres similaires: {e}")
            return 0

    def scrape_all_sites(self) -> Dict[str, Any]:
        """Scraper tous les sites de Guadeloupe - Version simplifiée et robuste"""
        logger.info("🚀 Début du scraping des sites guadeloupéens...")
        
        start_time = time.time()
        all_articles = []
        results = {
            'success': True,
            'scraped_at': datetime.now().isoformat(),
            'sites_scraped': 0,
            'total_articles': 0,
            'articles_by_site': {},
            'errors': [],
            'execution_time_seconds': 0
        }
        
        # Scraper les sites un par un (plus stable qu'en parallèle)
        for site_key in self.sites_config.keys():
            try:
                logger.info(f"🔍 Scraping {self.sites_config[site_key]['name']}...")
                
                # Scraper seulement la page principale pour éviter les erreurs 404
                config = self.sites_config[site_key]
                articles = self.scrape_page(config['url'], site_key, max_retries=2)
                
                if articles:
                    # Sauvegarder en base de données avec vérification de doublons
                    saved_count = 0
                    duplicate_count = 0
                    
                    for article in articles:
                        try:
                            # Ajouter timestamp de scraping
                            article['scraped_at'] = datetime.now().isoformat()
                            
                            # Vérifier les doublons avant sauvegarde
                            if not self.is_duplicate_article(article):
                                self.articles_collection.update_one(
                                    {'id': article['id']},
                                    {'$set': article},
                                    upsert=True
                                )
                                saved_count += 1
                            else:
                                duplicate_count += 1
                                logger.debug(f"Article dupliqué ignoré: {article.get('title', 'Sans titre')[:50]}...")
                                
                        except Exception as e:
                            logger.warning(f"Erreur sauvegarde article: {e}")
                    
                    all_articles.extend([a for a in articles if not self.is_duplicate_article(a)])
                    results['articles_by_site'][site_key] = saved_count
                    results['duplicates_by_site'] = results.get('duplicates_by_site', {})
                    results['duplicates_by_site'][site_key] = duplicate_count
                    results['sites_scraped'] += 1
                    
                    logger.info(f"✅ {config['name']}: {saved_count} articles sauvegardés, {duplicate_count} doublons ignorés")
                else:
                    error_msg = f"Aucun article trouvé sur {config['name']}"
                    results['errors'].append(error_msg)
                    logger.warning(error_msg)
                
                # Pause entre les sites pour éviter la surcharge
                time.sleep(3)
                
            except Exception as e:
                error_msg = f"Erreur {self.sites_config[site_key]['name']}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Finaliser les résultats avec statistiques de doublons
        results['total_articles'] = len(all_articles)
        results['total_duplicates'] = sum(results.get('duplicates_by_site', {}).values())
        results['articles'] = all_articles
        results['execution_time_seconds'] = round(time.time() - start_time, 2)
        
        # Invalider le cache des articles
        try:
            from cache_service import cache_invalidate
            cache_invalidate('articles')
            logger.info("🗑️ Cache articles invalidé")
        except (ImportError, Exception) as e:
            logger.warning(f"Erreur invalidation cache: {e}")
        
        # Statistiques finales avec doublons
        logger.info(f"📊 Scraping terminé: {results['total_articles']} articles uniques, "
                   f"{results['total_duplicates']} doublons évités en {results['execution_time_seconds']}s")
        logger.info(f"📊 Scraping terminé: {results['total_articles']} articles de {results['sites_scraped']}/{len(self.sites_config)} sites en {results['execution_time_seconds']}s")
        
        return results

    def get_todays_articles(self) -> List[Dict[str, Any]]:
        """Récupérer les articles d'aujourd'hui avec cache"""
        try:
            from cache_service import get_or_compute
            
            def fetch_articles():
                today = datetime.now().strftime('%Y-%m-%d')
                articles = list(self.articles_collection.find(
                    {'date': today}, 
                    {'_id': 0}
                ).sort('scraped_at', -1).limit(100))  # Augmenté à 100
                return articles
            
            # Utiliser le cache intelligent
            return get_or_compute('articles_today', fetch_articles)
            
        except (ImportError, Exception):
            # Fallback sans cache
            today = datetime.now().strftime('%Y-%m-%d')
            articles = list(self.articles_collection.find(
                {'date': today}, 
                {'_id': 0}
            ).sort('scraped_at', -1).limit(100))
            return articles

    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Récupérer les articles d'une date spécifique avec cache"""
        try:
            from cache_service import get_or_compute
            
            def fetch_articles():
                articles = list(self.articles_collection.find(
                    {'date': date_str}, 
                    {'_id': 0}
                ).sort('scraped_at', -1).limit(100))
                return articles
            
            # Utiliser le cache intelligent
            return get_or_compute('articles_by_date', fetch_articles, {'date': date_str})
            
        except (ImportError, Exception):
            # Fallback sans cache
            articles = list(self.articles_collection.find(
                {'date': date_str}, 
                {'_id': 0}
            ).sort('scraped_at', -1).limit(100))
            return articles

    def get_scraping_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques de scraping"""
        try:
            total_articles = self.articles_collection.count_documents({})
            today = datetime.now().strftime('%Y-%m-%d')
            today_articles = self.articles_collection.count_documents({'date': today})
            
            # Articles par site
            pipeline = [
                {'$group': {'_id': '$site_key', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}}
            ]
            articles_by_site = list(self.articles_collection.aggregate(pipeline))
            
            return {
                'total_articles': total_articles,
                'today_articles': today_articles,
                'articles_by_site': {item['_id']: item['count'] for item in articles_by_site},
                'last_scrape': self._get_last_scrape_time()
            }
            
        except Exception as e:
            logger.error(f"Erreur stats scraping: {e}")
            return {'error': str(e)}

    def _get_last_scrape_time(self) -> str:
        """Obtenir l'heure du dernier scraping"""
        try:
            last_article = self.articles_collection.find_one(
                {}, 
                sort=[('scraped_at', -1)]
            )
            return last_article['scraped_at'] if last_article else "Jamais"
        except:
            return "Inconnu"

# Instance globale du scraper
guadeloupe_scraper = GuadeloupeScraper()

def run_daily_scraping():
    """Fonction pour lancer le scraping quotidien"""
    logger.info("⏰ Lancement du scraping quotidien à 10H")
    return guadeloupe_scraper.scrape_all_sites()

if __name__ == "__main__":
    # Test du scraper amélioré
    result = guadeloupe_scraper.scrape_all_sites()
    print(json.dumps(result, indent=2, ensure_ascii=False))