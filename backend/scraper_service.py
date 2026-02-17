# backend/scraper_service.py
"""
Service de scraping Guadeloupe - V2
- Extraction des 3000 premiers mots du contenu
- Enrichissement avec tags_index
- Ingestion dans pipeline V2 (clustering contextuel → promotion)
- NOTE: Détection d'affaires V1 SUPPRIMÉE (faux positifs massifs)
"""

import os
import re
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
# SequenceMatcher supprimé - plus de matching V1

import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

# Import tags_index pour enrichissement
try:
    from tags_index import infer_tags_and_theme
except:
    from backend.tags_index import infer_tags_and_theme

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class GuadeloupeScraper:
    def __init__(self) -> None:
        # Connexion MongoDB
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        
        try:
            if "mongodb+srv://" in MONGO_URL or "atlas" in MONGO_URL.lower():
                try:
                    import certifi
                    self.client = MongoClient(
                        MONGO_URL,
                        tlsCAFile=certifi.where(),
                        serverSelectionTimeoutMS=20000,
                    )
                except ImportError:
                    self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)
            else:
                self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)
            
            self.client.admin.command("ping")
            logger.info("✅ Scraper connecté à MongoDB")
            
            # Résolution DB
            try:
                dbname = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
                if "mongodb+srv://" in MONGO_URL and ("?" in dbname or not dbname):
                    dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            except Exception:
                dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            
            self.db = self.client[dbname]
            self.articles_collection = self.db["articles_guadeloupe"]
            
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
            raise
        
        # Configuration sites
        self.sites_config = {
            "france_antilles": {
                "name": "France-Antilles Guadeloupe",
                "url": "https://www.guadeloupe.franceantilles.fr/",
                "selectors": ["article h2 a", "article h3 a", ".article-title a", "h2 a"],
                "content_selectors": [".article-content", ".article-body", ".content", "article"],
                "base_url": "https://www.guadeloupe.franceantilles.fr",
            },
            "rci": {
                "name": "RCI Guadeloupe",
                "url": "https://rci.fm/guadeloupe/infos/toutes-les-infos",
                "selectors": ["a[href*='/guadeloupe/infos/']", ".post-title a", "h2 a"],
                "content_selectors": [".post-content", ".article-text", ".content"],
                "base_url": "https://rci.fm",
            },
            "la1ere": {
                "name": "La 1ère Guadeloupe",
                "url": "https://la1ere.franceinfo.fr/guadeloupe/",
                "selectors": ["a.teaser__title", "article a[href*='/guadeloupe/']"],
                "content_selectors": [".article__content", ".text", ".content"],
                "base_url": "https://la1ere.franceinfo.fr",
            },
            "karibinfo": {
                "name": "KaribInfo",
                "url": "https://www.karibinfo.com/",
                "selectors": ["h1 a", "h2 a", "h3 a", "article a"],
                "content_selectors": [".entry-content", ".post-content", "article"],
                "base_url": "https://www.karibinfo.com",
            }
        }
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        }
    
    def extract_article_content(self, url: str, site_config: Dict) -> str:
        """
        Extrait le contenu complet d'un article (3000 premiers mots)
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Essayer différents sélecteurs de contenu
            content = ""
            for selector in site_config.get('content_selectors', []):
                elements = soup.select(selector)
                if elements:
                    # Prendre tous les paragraphes
                    paragraphs = []
                    for element in elements:
                        for p in element.find_all(['p', 'div']):
                            text = p.get_text(strip=True)
                            if text and len(text) > 20:  # Ignorer les petits textes
                                paragraphs.append(text)
                    
                    content = " ".join(paragraphs)
                    if content:
                        break
            
            # Si pas de contenu avec sélecteurs, prendre tout le texte
            if not content:
                # Enlever scripts et styles
                for script in soup(["script", "style"]):
                    script.decompose()
                content = soup.get_text()
            
            # Nettoyer et limiter à 3000 mots
            content = re.sub(r'\s+', ' ', content).strip()
            words = content.split()[:3000]
            content = " ".join(words)
            
            logger.info(f"   📄 Contenu extrait: {len(words)} mots")
            return content
            
        except Exception as e:
            logger.warning(f"   ⚠️ Erreur extraction contenu: {e}")
            return ""
    
    def clean_title(self, title: str) -> str:
        """Nettoie un titre"""
        if not title:
            return ""
        title = re.sub(r"[\n\r\t]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        prefixes = ["LIRE AUSSI:", "VOIR AUSSI:", "À LIRE:", "VIDÉO:", "EN IMAGES."]
        for p in prefixes:
            if title.upper().startswith(p):
                title = title[len(p):].strip()
        return title
    
    # NOTE: Les méthodes V1 (detect_affair, create_affair, calculate_bmg)
    # ont été supprimées car elles créaient des affaires garbage avec
    # du keyword matching faible. Le système V2 (affair_lifecycle_service)
    # gère désormais tout via clustering contextuel → promotion.
    
    def scrape_site(self, site_key: str, config: Dict) -> List[Dict]:
        """Scrape un site avec extraction de contenu"""
        articles = []
        
        try:
            logger.info(f"🔍 Scraping {config['name']}...")
            response = requests.get(config['url'], headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = []
            
            for selector in config['selectors']:
                links.extend(soup.select(selector))
            
            logger.info(f"   🔗 {len(links)} liens trouvés")
            
            for i, link in enumerate(links[:20], 1):  # Limiter à 20 articles
                try:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    
                    if not title or not href:
                        continue
                    
                    title = self.clean_title(title)
                    
                    if not href.startswith('http'):
                        href = urljoin(config['url'], href)
                    
                    # Vérifier si l'article existe déjà
                    article_id = hashlib.md5(f"{href}:{title}".encode()).hexdigest()[:12]
                    if self.articles_collection.find_one({'article_id': article_id}):
                        logger.info(f"   ⏭️  Article {i}/{len(links)}: Déjà en base")
                        continue
                    
                    logger.info(f"   📰 Article {i}/{len(links)}: {title[:50]}...")
                    
                    # EXTRAIRE LE CONTENU
                    content = self.extract_article_content(href, config)
                    
                    article = {
                        'article_id': article_id,
                        'title': title,
                        'url': href,
                        'content': content,  # CONTENU AJOUTÉ
                        'text': content,  # Pour compatibilité
                        'source': config['name'],
                        'site_key': site_key,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'scraped_at': datetime.now(),
                        'word_count': len(content.split()) if content else 0
                    }
                    
                    # ENRICHIR AVEC TAGS_INDEX
                    logger.info(f"   🔬 Enrichissement avec tags_index...")
                    enriched = infer_tags_and_theme(article)
                    article.update(enriched)
                    
                    logger.info(f"   ✅ Enrichi: {enriched.get('theme')} | {enriched.get('elected', [])} | Affaire: {enriched.get('is_affair')}")
                    
                    articles.append(article)
                    
                except Exception as e:
                    logger.warning(f"   ❌ Erreur article {i}: {e}")
                    continue
            
            logger.info(f"✅ {config['name']}: {len(articles)} articles extraits et enrichis")
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping {config['name']}: {e}")
        
        return articles
    
    def scrape_all_sites(self) -> Dict[str, Any]:
        """
        Scrape tous les sites avec détection d'affaires
        """
        logger.info("=" * 80)
        logger.info("🚀 SCRAPING GUADELOUPE - MODE SANS OLLAMA")
        logger.info("=" * 80)
        
        start = time.time()
        
        results = {
            "success": True,
            "scraped_at": datetime.now().isoformat(),
            "sites_scraped": 0,
            "total_articles": 0,
            "articles_saved": 0,
            "articles_enriched": 0,
            "v2_ingested": 0,
            "articles_by_site": {},
            "errors": [],
        }
        
        all_articles = []
        
        for site_key, cfg in self.sites_config.items():
            try:
                articles = self.scrape_site(site_key, cfg)

                saved = 0

                for article in articles:
                    try:
                        # Sauvegarder l'article en base
                        self.articles_collection.insert_one(article)
                        saved += 1
                        all_articles.append(article)
                    except Exception as e:
                        logger.warning(f"   ⚠️ Erreur sauvegarde: {e}")

                results["articles_by_site"][site_key] = saved
                results["sites_scraped"] += 1
                results["articles_saved"] += saved
                results["articles_enriched"] += saved

                logger.info(f"📈 {cfg['name']}: {saved} sauvegardés")

                time.sleep(1.0)  # Pause entre sites

            except Exception as e:
                msg = f"Erreur {cfg['name']}: {str(e)}"
                results["errors"].append(msg)
                logger.error(msg)

        results["total_articles"] = results["articles_saved"]
        results["execution_time_seconds"] = round(time.time() - start, 2)

        # Ingérer les articles dans le pipeline V2 (clustering contextuel)
        v2_ingested = 0
        try:
            from backend.affair_lifecycle_service import get_affair_lifecycle_service
            svc = get_affair_lifecycle_service(db=self.db)
            for art in all_articles:
                try:
                    r = svc.ingest_item(art, source_type="article")
                    if r.get("success") and r.get("action") != "already_exists":
                        v2_ingested += 1
                except Exception:
                    pass
            if v2_ingested:
                logger.info(f"📥 {v2_ingested} articles ingérés dans pipeline V2")
        except Exception as e:
            logger.warning(f"⚠️ Ingestion V2: {e}")
        results["v2_ingested"] = v2_ingested
        
        # Rapport final
        logger.info("=" * 80)
        logger.info(f"📊 SCRAPING TERMINÉ")
        logger.info(f"  • Articles: {results['total_articles']}")
        logger.info(f"  • Ingérés V2: {results.get('v2_ingested', 0)}")
        logger.info(f"  • Temps: {results['execution_time_seconds']}s")
        logger.info("=" * 80)
        
        return results
    
    def run(self) -> Dict[str, Any]:
        """Alias pour compatibilité"""
        return self.scrape_all_sites()
    
    def get_todays_articles(self) -> List[Dict[str, Any]]:
        """Récupère les articles du jour"""
        today = datetime.now().strftime("%Y-%m-%d")
        articles = list(
            self.articles_collection.find({"date": today})
            .sort("scraped_at", -1)
            .limit(100)
        )
        for a in articles:
            if "_id" in a:
                a["_id"] = str(a["_id"])
        return articles
    
    def get_scraping_stats(self) -> Dict[str, Any]:
        """Statistiques de scraping"""
        try:
            total = self.articles_collection.count_documents({})
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = self.articles_collection.count_documents({"date": today})

            return {
                "total_articles": total,
                "today_articles": today_count,
            }
        except Exception as e:
            logger.error(f"❌ Erreur stats: {e}")
            return {"error": str(e)}


# Instance globale
guadeloupe_scraper = GuadeloupeScraper()

def run_daily_scraping() -> Dict[str, Any]:
    """Point d'entrée pour scraping quotidien"""
    return guadeloupe_scraper.scrape_all_sites()

if __name__ == "__main__":
    result = run_daily_scraping()
    print(f"\n✅ Résultat: {result}")