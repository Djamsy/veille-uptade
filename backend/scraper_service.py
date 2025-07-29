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

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GuadeloupeScraper:
    def __init__(self):
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.articles_collection = self.db.articles_guadeloupe
        
        # Sites à scraper avec sélecteurs multiples améliorés
        self.sites_config = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selectors": [
                    "article h2 a", "article h3 a", ".article-title a", 
                    ".title a", ".entry-title a", "h2 a", "h3 a",
                    ".post-title a", ".content-title a", ".news-title a"
                ],
                "base_url": "https://www.guadeloupe.franceantilles.fr",
                "additional_pages": [
                    "https://www.guadeloupe.franceantilles.fr/actualite/politique",
                    "https://www.guadeloupe.franceantilles.fr/actualite/economie",
                    "https://www.guadeloupe.franceantilles.fr/actualite/societe"
                ]
            },
            "rci": {
                "name": "RCI Guadeloupe", 
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selectors": [
                    ".post-title a", ".entry-title a", "h2 a", "h3 a",
                    ".article-title a", ".content-title a", ".news-item a",
                    ".post-item h2 a", ".post-item h3 a"
                ],
                "base_url": "https://rci.fm",
                "additional_pages": [
                    "https://rci.fm/guadeloupe/infos/politique",
                    "https://rci.fm/guadeloupe/infos/economie",
                    "https://rci.fm/guadeloupe/infos/societe"
                ]
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selectors": [
                    ".teaser__title a", ".article-title a", "h2 a", "h3 a",
                    ".content-title a", ".post-title a", ".entry-title a",
                    ".news-title a", ".item-title a"
                ],
                "base_url": "https://la1ere.franceinfo.fr",
                "additional_pages": [
                    "https://la1ere.franceinfo.fr/guadeloupe/politique",
                    "https://la1ere.franceinfo.fr/guadeloupe/economie", 
                    "https://la1ere.franceinfo.fr/guadeloupe/societe"
                ]
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selectors": [
                    ".post-title a", ".entry-title a", ".title a", "h2 a", "h3 a",
                    ".article-title a", ".content-title a", ".news-title a",
                    ".post-item h2 a", ".post-item h3 a", ".item-title a"
                ],
                "base_url": "https://www.karibinfo.com",
                "additional_pages": [
                    "https://www.karibinfo.com/category/actualites",
                    "https://www.karibinfo.com/category/politique",
                    "https://www.karibinfo.com/category/economie"
                ]
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
            'javascript:', 'mailto:', '#', 'tel:'
        ]
        
        for pattern in ignore_patterns:
            if pattern in url.lower():
                return False
        
        # Vérifier que c'est bien un article du domaine
        parsed_url = urlparse(url)
        if parsed_url.netloc and base_domain not in parsed_url.netloc:
            return False
        
        return True

    def scrape_page(self, url: str, site_key: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        """Scraper une page spécifique"""
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
                    # Sauvegarder en base de données
                    saved_count = 0
                    for article in articles:
                        try:
                            self.articles_collection.update_one(
                                {'id': article['id']},
                                {'$set': article},
                                upsert=True
                            )
                            saved_count += 1
                        except Exception as e:
                            logger.warning(f"Erreur sauvegarde article: {e}")
                    
                    all_articles.extend(articles)
                    results['articles_by_site'][site_key] = saved_count
                    results['sites_scraped'] += 1
                    
                    logger.info(f"✅ {config['name']}: {saved_count} articles sauvegardés")
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
        
        # Finaliser les résultats
        results['total_articles'] = len(all_articles)
        results['articles'] = all_articles
        results['execution_time_seconds'] = round(time.time() - start_time, 2)
        
        # Invalider le cache des articles
        try:
            from cache_service import cache_invalidate
            cache_invalidate('articles')
            logger.info("🗑️ Cache articles invalidé")
        except (ImportError, Exception) as e:
            logger.warning(f"Erreur invalidation cache: {e}")
        
        # Statistiques finales
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