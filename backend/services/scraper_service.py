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
    from backend.services.tags_index import infer_tags_and_theme

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ============================================================
# Filtre de pertinence Guadeloupe — rejette les articles hors-sujet
# ============================================================
_GUADELOUPE_KEYWORDS = {
    "guadeloupe", "guadeloupeen", "guadeloupeenne", "guadeloupéen", "guadeloupéenne",
    "antilles", "antillais", "antillaise", "caraibes", "caraibe",
    "pointe-a-pitre", "pointe a pitre", "basse-terre", "basse terre",
    "les abymes", "abymes", "le gosier", "gosier", "sainte-anne", "saint-francois",
    "le moule", "petit-bourg", "baie-mahault", "lamentin", "capesterre",
    "marie-galante", "les saintes", "la desirade", "desirade", "terre-de-haut",
    "bouillante", "deshaies", "trois-rivieres", "gourbeyre", "vieux-habitants",
    "jarry", "dothémare", "grand-camp", "bergevin", "fouillole",
    "martinique", "guyane", "reunion", "mayotte", "outre-mer", "outremer",
    "dom-tom", "drom-com",
    # Institutions locales
    "smgeag", "siaeag", "chu guadeloupe", "prefecture guadeloupe",
    "conseil departemental", "conseil regional", "rectorat guadeloupe",
    # Sujets typiquement antillais
    "sargasse", "sargasses", "chlordecone", "chlordécone",
    "cyclone", "ouragan", "gwo ka", "gwoka", "carnaval",
    "canne a sucre", "campagne sucriere", "banane", "rhum",
}

def _is_guadeloupe_relevant(title: str, content: str, url: str = "") -> bool:
    """
    Vérifie si un article concerne la Guadeloupe / Antilles.
    - Rejette d'abord les articles clairement internationaux (même sur sites locaux)
    - Puis vérifie la présence de mots-clés locaux
    - Les sites locaux sont acceptés par défaut (sauf contenu international)
    """
    import unicodedata

    title_lower = title.lower().strip()
    text = f"{title} {content[:1500]}".lower()
    text_norm = unicodedata.normalize("NFKD", text)
    text_norm = "".join(ch for ch in text_norm if not unicodedata.combining(ch))

    # 1. EXCLUSION FORTE — articles clairement internationaux
    #    Même sur un site local, ces articles ne sont pas pertinents
    _INTL_EXCLUSIONS = [
        "ukraine", "russie", "gaza", "israel", "palestine", "liban",
        "venezuela", "mexique", "philippines", "japon", "chine",
        "iran", "irak", "syrie", "afghanistan", "coree du nord",
        "trump", "biden", "poutine", "zelensky", "macron",
        "premier league", "champions league", "liga", "bundesliga", "serie a",
        "ambassade americaine", "guerre contre",
    ]
    # Si le TITRE contient un mot-clé international → rejet immédiat
    title_norm = unicodedata.normalize("NFKD", title_lower)
    title_norm = "".join(ch for ch in title_norm if not unicodedata.combining(ch))
    title_intl = sum(1 for kw in _INTL_EXCLUSIONS if kw in title_norm)
    if title_intl >= 1:
        return False

    # Si le contenu contient 2+ mots-clés internationaux → rejet
    intl_count = sum(1 for kw in _INTL_EXCLUSIONS if kw in text_norm)
    if intl_count >= 2:
        return False

    # 2. MOTS-CLÉS LOCAUX — si trouvés, c'est pertinent
    for kw in _GUADELOUPE_KEYWORDS:
        kw_norm = unicodedata.normalize("NFKD", kw)
        kw_norm = "".join(ch for ch in kw_norm if not unicodedata.combining(ch))
        if kw_norm in text_norm:
            return True

    # 3. SITES LOCAUX — accepter par défaut (contenu local implicite)
    local_domains = ["guadeloupe.franceantilles.fr", "rci.fm/guadeloupe",
                     "la1ere.franceinfo.fr/guadeloupe", "karibinfo.com"]
    for domain in local_domains:
        if domain in url:
            return True

    return False


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
                "url": "https://la1ere.franceinfo.fr/guadeloupe",
                "selectors": [
                    "a[href*='/guadeloupe/']",
                    "a.card__link", "a.teaser__link", "a.teaser__title",
                    ".card a", "article a", "h2 a", "h3 a",
                ],
                "content_selectors": [".article__content", ".article-body", ".text", ".content", "article"],
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

    @staticmethod
    def _clean_url(url: str) -> str:
        """Nettoie une URL en supprimant les paramètres de tracking (utm_*, fbclid, etc.)"""
        parsed = urlparse(url)
        # Supprimer les query params de tracking
        if parsed.query:
            from urllib.parse import parse_qs, urlencode
            params = parse_qs(parsed.query)
            clean_params = {k: v for k, v in params.items()
                           if not k.startswith("utm_") and k not in ("fbclid", "gclid", "ref", "source")}
            clean_query = urlencode(clean_params, doseq=True)
            url = parsed._replace(query=clean_query, fragment="").geturl()
        else:
            url = parsed._replace(fragment="").geturl()
        # Supprimer le trailing slash
        return url.rstrip("/")
    
    def extract_article_content(self, url: str, site_config: Dict) -> str:
        """
        Extrait le contenu ÉDITORIAL d'un article (3000 premiers mots).
        Exclut : navigation, sidebar, footer, bylines auteur, publicités.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # 1. Supprimer les éléments non-éditoriaux AVANT extraction
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "iframe", "noscript", "form"]):
                tag.decompose()

            # Supprimer les blocs auteur/byline/signature/publicité
            for cls_pattern in ["author", "byline", "signature", "credit",
                                "pub", "advert", "social", "share", "comment",
                                "related", "sidebar", "widget", "menu", "breadcrumb",
                                "newsletter", "footer", "nav"]:
                for el in soup.find_all(class_=re.compile(cls_pattern, re.I)):
                    el.decompose()
                for el in soup.find_all(id=re.compile(cls_pattern, re.I)):
                    el.decompose()

            # 2. Essayer les sélecteurs de contenu éditorial
            content = ""
            for selector in site_config.get('content_selectors', []):
                elements = soup.select(selector)
                if elements:
                    paragraphs = []
                    for element in elements:
                        # Uniquement les paragraphes (pas les divs qui peuvent
                        # contenir du bruit)
                        for p in element.find_all('p'):
                            text = p.get_text(strip=True)
                            if text and len(text) > 30:
                                paragraphs.append(text)

                    content = " ".join(paragraphs)
                    if len(content) > 100:
                        break

            # 3. Fallback : tous les <p> du body
            if not content or len(content) < 100:
                paragraphs = []
                for p in soup.find_all('p'):
                    text = p.get_text(strip=True)
                    if text and len(text) > 30:
                        paragraphs.append(text)
                content = " ".join(paragraphs)

            # 4. Nettoyer et limiter à 3000 mots
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
                    # Nettoyer l'URL (supprimer utm_*, fbclid, etc.)
                    href = self._clean_url(href)

                    # Vérifier si l'article existe déjà (URL nettoyée + titre + contenu)
                    article_id = hashlib.md5(f"{href}:{title}".encode()).hexdigest()[:12]
                    # Aussi vérifier par titre seul (même article, URL différente)
                    title_hash = hashlib.md5(title.encode()).hexdigest()[:12]
                    # ⚡ Un seul find_one avec $or au lieu de 2 requêtes séparées
                    if self.articles_collection.find_one(
                        {'$or': [{'article_id': article_id}, {'title_hash': title_hash}]},
                        {'_id': 1}  # projection minimale
                    ):
                        logger.info(f"   ⏭️  Article {i}/{len(links)}: Déjà en base")
                        continue
                    
                    logger.info(f"   📰 Article {i}/{len(links)}: {title[:50]}...")

                    # EXTRAIRE LE CONTENU
                    content = self.extract_article_content(href, config)

                    # FILTRE GUADELOUPE — rejeter les articles hors-zone
                    if not _is_guadeloupe_relevant(title, content, href):
                        logger.info(f"   🌍 HORS-ZONE ignoré: {title[:60]}")
                        continue

                    # Hash du contenu (premiers 500 chars) pour détecter les reprises
                    content_normalized = (content or "")[:500].strip().lower()
                    content_hash = hashlib.md5(content_normalized.encode()).hexdigest()[:12] if content_normalized else None

                    # Vérifier doublon par contenu (même texte, URL/titre différent)
                    if content_hash and self.articles_collection.find_one(
                        {'content_hash': content_hash}, {'_id': 1}
                    ):
                        logger.info(f"   ⏭️  Article {i}/{len(links)}: Contenu dupliqué")
                        continue

                    article = {
                        'article_id': article_id,
                        'title_hash': title_hash,
                        'content_hash': content_hash,
                        'title': title,
                        'url': href,
                        'content': content,
                        'text': content,
                        'source': config['name'],
                        'site_key': site_key,
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'scraped_at': datetime.now(),
                        'word_count': len(content.split()) if content else 0
                    }

                    # ENRICHIR AVEC TAGS_INDEX (pré-enrichissement léger)
                    # On marque comme "rules_preliminary" pour que job_enrich
                    # puisse ré-enrichir avec l'IA plus tard
                    logger.info(f"   🔬 Pré-enrichissement avec tags_index...")
                    enriched = infer_tags_and_theme(article)
                    article.update(enriched)
                    # Marquer comme pré-enrichissement (pas définitif)
                    article["_analysis_method"] = "rules_preliminary"

                    logger.info(f"   ✅ Enrichi: {enriched.get('theme')} | gravity: {enriched.get('gravity_score')} | {enriched.get('elected', [])}")

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

                # ⚡ Batch insert au lieu de N × insert_one (÷N ops MongoDB)
                if articles:
                    try:
                        insert_result = self.articles_collection.insert_many(
                            articles, ordered=False  # continue même si un doublon
                        )
                        saved = len(insert_result.inserted_ids)
                    except Exception as e:
                        # BulkWriteError si doublons — compter les succès
                        if hasattr(e, 'details'):
                            saved = e.details.get('nInserted', 0)
                        else:
                            saved = 0
                            logger.warning(f"   ⚠️ Erreur batch insert: {e}")
                    all_articles.extend(articles[:saved] if saved else [])
                else:
                    saved = 0

                results["articles_by_site"][site_key] = saved
                results["sites_scraped"] += 1
                results["articles_saved"] += saved
                results["articles_enriched"] += saved

                logger.info(f"📈 {cfg['name']}: {saved} sauvegardés (batch)")

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
            from backend.services.affair_lifecycle_service import get_affair_lifecycle_service
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


# Instance globale — initialisation paresseuse (lazy) pour éviter crash au module load
_scraper_instance = None

def _get_or_create_scraper():
    global _scraper_instance
    if _scraper_instance is None:
        try:
            _scraper_instance = GuadeloupeScraper()
        except Exception as e:
            logger.error(f"❌ Impossible d'initialiser le scraper: {e}")
            return None
    return _scraper_instance

# Alias pour compatibilité avec les imports existants
class _LazyScraperProxy:
    """Proxy qui initialise le scraper au premier appel, pas à l'import du module."""
    def __getattr__(self, name):
        scraper = _get_or_create_scraper()
        if scraper is None:
            raise RuntimeError("Scraper non disponible (connexion MongoDB échouée)")
        return getattr(scraper, name)

guadeloupe_scraper = _LazyScraperProxy()

def run_daily_scraping() -> Dict[str, Any]:
    """Point d'entrée pour scraping quotidien"""
    scraper = _get_or_create_scraper()
    if scraper is None:
        return {"error": "Scraper non disponible"}
    return scraper.scrape_all_sites()

if __name__ == "__main__":
    result = run_daily_scraping()
    print(f"\n✅ Résultat: {result}")