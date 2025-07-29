"""
Service de scraping des sites d'actualités de Guadeloupe
Scraping automatique à 10H chaque jour
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
        
        # Sites à scraper
        self.sites_config = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selector": "article h2 a, .article-title a, .title a",
                "base_url": "https://www.guadeloupe.franceantilles.fr"
            },
            "rci": {
                "name": "RCI Guadeloupe", 
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selector": ".post-title a, .entry-title a, h2 a",
                "base_url": "https://rci.fm"
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selector": ".teaser__title a, .article-title a, h2 a",
                "base_url": "https://la1ere.franceinfo.fr"
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selector": ".post-title a, .entry-title a, .title a",
                "base_url": "https://www.karibinfo.com"
            }
        }
        
        # Headers pour éviter le blocage
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def scrape_site(self, site_key: str) -> List[Dict[str, Any]]:
        """Scraper un site spécifique"""
        config = self.sites_config[site_key]
        articles = []
        
        try:
            logger.info(f"🔍 Scraping {config['name']}...")
            
            # Request avec timeout et retry
            session = requests.Session()
            session.headers.update(self.headers)
            
            response = session.get(config['url'], timeout=15)
            response.raise_for_status()
            
            # Parser le HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Trouver les liens d'articles
            links = soup.select(config['selector'])
            
            for link in links[:10]:  # Limiter à 10 articles par site
                try:
                    title = link.get_text().strip()
                    href = link.get('href')
                    
                    if not title or not href:
                        continue
                    
                    # Construire l'URL complète
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('/'):
                        url = config['base_url'] + href
                    else:
                        url = config['base_url'] + '/' + href
                    
                    # Créer l'article
                    article = {
                        'id': f"{site_key}_{hash(url)}",
                        'title': title,
                        'url': url,
                        'source': config['name'],
                        'site_key': site_key,
                        'scraped_at': datetime.now().isoformat(),
                        'date': datetime.now().strftime('%Y-%m-%d')
                    }
                    
                    articles.append(article)
                    
                except Exception as e:
                    logger.warning(f"Erreur parsing article de {config['name']}: {e}")
                    continue
            
            logger.info(f"✅ {len(articles)} articles trouvés sur {config['name']}")
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping {config['name']}: {e}")
        
        return articles

    def scrape_all_sites(self) -> Dict[str, Any]:
        """Scraper tous les sites de Guadeloupe"""
        logger.info("🚀 Début du scraping des sites guadeloupéens...")
        
        all_articles = []
        results = {
            'success': True,
            'scraped_at': datetime.now().isoformat(),
            'sites_scraped': 0,
            'total_articles': 0,
            'articles_by_site': {},
            'errors': []
        }
        
        for site_key in self.sites_config.keys():
            try:
                articles = self.scrape_site(site_key)
                
                if articles:
                    # Sauvegarder en base
                    for article in articles:
                        self.articles_collection.update_one(
                            {'id': article['id']},
                            {'$set': article},
                            upsert=True
                        )
                    
                    all_articles.extend(articles)
                    results['articles_by_site'][site_key] = len(articles)
                    results['sites_scraped'] += 1
                    
                else:
                    results['errors'].append(f"Aucun article trouvé sur {self.sites_config[site_key]['name']}")
                
                # Pause entre les sites
                time.sleep(2)
                
            except Exception as e:
                error_msg = f"Erreur scraping {self.sites_config[site_key]['name']}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        results['total_articles'] = len(all_articles)
        results['articles'] = all_articles
        
        # Statistiques
        logger.info(f"📊 Scraping terminé: {results['total_articles']} articles de {results['sites_scraped']} sites")
        
        return results

    def get_todays_articles(self) -> List[Dict[str, Any]]:
        """Récupérer les articles d'aujourd'hui"""
        today = datetime.now().strftime('%Y-%m-%d')
        articles = list(self.articles_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('scraped_at', -1))
        
        return articles

    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Récupérer les articles d'une date spécifique"""
        articles = list(self.articles_collection.find(
            {'date': date_str}, 
            {'_id': 0}
        ).sort('scraped_at', -1))
        
        return articles

# Instance globale du scraper
guadeloupe_scraper = GuadeloupeScraper()

def run_daily_scraping():
    """Fonction pour lancer le scraping quotidien"""
    logger.info("⏰ Lancement du scraping quotidien à 10H")
    return guadeloupe_scraper.scrape_all_sites()

if __name__ == "__main__":
    # Test du scraper
    result = guadeloupe_scraper.scrape_all_sites()
    print(json.dumps(result, indent=2, ensure_ascii=False))