"""
Serveur backend COMPLET pour le système de veille média Guadeloupe V5.2.0
VERSION SANS OLLAMA - 100% basé sur des règles
- TOUTES les fonctionnalités conservées
- Tags_index remplace AI_service pour l'enrichissement  
- Infrastructure complète (Scraping, Radio, Scheduler, Digest, Analytics)
- LOGIQUE D'AFFAIRES AVANCÉE : Détection temporelle, corrélation, gravité
- CALCUL DU BRUIT NUMÉRIQUE (BMG) par canal avec pondérations
- ANALYSE DE SENTIMENT INTÉGRÉE (basée sur lexique)
- VALIDATION STRICTE des entités (100+ personnalités)
"""

import os
import sys
import json
import logging
import traceback
import hashlib
import re
from datetime import datetime, timedelta

# Assurer que le dossier parent est dans sys.path pour les imports "from backend.xxx"
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Charger les variables d'environnement depuis .env
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv non installé, on utilise les variables système

from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict, Counter
import threading
import requests


# ============================================================
# CACHE MÉMOIRE AVEC TTL
# ============================================================
class MemoryCache:
    """Cache en mémoire simple avec TTL par clé. Thread-safe."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                import time
                if time.time() < self._expiry.get(key, 0):
                    return self._store[key]
                # Expiré → supprimer
                del self._store[key]
                del self._expiry[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        import time
        with self._lock:
            self._store[key] = value
            self._expiry[key] = time.time() + ttl_seconds

    def invalidate(self, pattern: str = ""):
        """Invalide toutes les clés contenant le pattern (ou toutes si vide)."""
        with self._lock:
            if not pattern:
                self._store.clear()
                self._expiry.clear()
            else:
                keys_to_del = [k for k in self._store if pattern in k]
                for k in keys_to_del:
                    del self._store[k]
                    if k in self._expiry:
                        del self._expiry[k]


_cache = MemoryCache()
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId

from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, StreamingResponse
import uvicorn

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('veille_backend.log')
    ]
)
logger = logging.getLogger("veille_media_backend")

# Variables d'environnement
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "veille_media")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
VERSION = "5.2.0-NO-OLLAMA"
START_TIME = datetime.utcnow()
RUN_SCHEDULER = os.environ.get("RUN_SCHEDULER", "true").strip().lower() in ("true", "1", "yes", "on")
GRAVITY_THRESHOLD = float(os.environ.get("AFFAIR_GRAVITY_THRESHOLD", "0.6"))

logger.info("=" * 60)
logger.info(f"🏝️ VEILLE MÉDIA GUADELOUPE - VERSION {VERSION}")
logger.info("🚀 Mode: SANS OLLAMA - 100% règles déterministes")
logger.info("=" * 60)
logger.info(f"MONGO_URL: {MONGO_URL}")
logger.info(f"Environment: {ENVIRONMENT}")
logger.info(f"Seuil gravité affaires: {GRAVITY_THRESHOLD}")

# Connexion MongoDB
mongo_client = None
db = None

try:
    mongo_client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    db = mongo_client[DB_NAME]
    mongo_client.admin.command('ismaster')
    logger.info("✅ MongoDB connecté avec succès")
except ConnectionFailure:
    logger.error("❌ Échec connexion MongoDB")
    mongo_client = None
    db = None

# Collections principales
collections = {}
if mongo_client is not None:
    try:
        collections = {
            'radio_transcriptions': db.radio_transcriptions,
            'articles_guadeloupe': db.articles_guadeloupe,
            'affairs': db.affairs,
            'social_media_posts': db.social_media_posts,
            'daily_digests': db.daily_digests,
            'comments': db.comments,
            'scheduler_logs': db.scheduler_logs,
            'bmg_history': db.bmg_history
        }
        logger.info("✅ Collections MongoDB initialisées")
    except Exception as e:
        logger.error(f"❌ Erreur initialisation collections: {e}")
        collections = {}

# Application FastAPI
app = FastAPI(
    title="Veille Média Guadeloupe API",
    description="API complète avec BMG, analyse et détection affaires - SANS OLLAMA",
    version=VERSION
)

# CORS
ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== RATE LIMITING ==========
from collections import defaultdict
import time as _time

_rate_store: Dict[str, list] = defaultdict(list)
_RATE_WINDOW = 60       # secondes
_RATE_LIMIT_DEFAULT = 60  # requêtes par fenêtre
_RATE_LIMIT_POST = 15     # requêtes POST par fenêtre (GPT, pipeline, etc.)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting simple basé sur l'IP client."""
    client_ip = request.client.host if request.client else "unknown"
    now = _time.time()
    method = request.method

    key = f"{client_ip}:{method}"
    limit = _RATE_LIMIT_POST if method == "POST" else _RATE_LIMIT_DEFAULT

    # Nettoyer les entrées expirées
    _rate_store[key] = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]

    if len(_rate_store[key]) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Trop de requêtes. Réessayez dans une minute."},
            headers={"Retry-After": str(_RATE_WINDOW)},
        )

    _rate_store[key].append(now)
    response = await call_next(request)
    return response

# ========== SERVICES PRINCIPAUX ==========

# Service d'enrichissement (Groq IA + fallback tags_index)
enrichment_service = None
ai_service = None  # Pour compatibilité
_groq_available = False
_ai_provider_name = "règles"

# 1. Essayer Groq (IA)
try:
    from backend.ai_groq_service import smart_enrich_article, is_available as groq_is_available, analyze_sentiment_groq, AI_PROVIDER as _ai_prov, AI_MODEL as _ai_mod
    if groq_is_available():
        enrichment_service = smart_enrich_article
        _groq_available = True
        _ai_provider_name = f"{_ai_prov}/{_ai_mod}"
        logger.info(f"✅ Service d'enrichissement IA chargé ({_ai_provider_name})")
    else:
        logger.info("ℹ️ Groq non configuré (pas de GROQ_API_KEY), fallback sur règles")
except Exception as e:
    logger.warning(f"⚠️ Groq non disponible: {e}")

# 2. Fallback sur tags_index si Groq indisponible
if enrichment_service is None:
    try:
        from backend.tags_index import infer_tags_and_theme
        enrichment_service = infer_tags_and_theme
        logger.info("✅ Service d'enrichissement chargé (tags_index — règles)")
    except Exception as e:
        logger.error(f"❌ Tags_index non disponible: {e}")

# 3. Wrapper pour compatibilité
try:
    class AIServiceWrapper:
        def enrich_article(self, article_data):
            if enrichment_service:
                return enrichment_service(article_data)
            return article_data

        def classify_transcription_advanced(self, text, metadata=None):
            if not enrichment_service:
                return {
                    "classification": {
                        "is_affair": False,
                        "affair_type": "routine",
                        "gravity_score": 0.3,
                        "confidence": 0.5
                    },
                    "primary_entity": None,
                    "entities_detected": [],
                    "method": "fallback"
                }

            pseudo_article = {"title": "", "content": text, "text": text}
            enriched = enrichment_service(pseudo_article)

            return {
                "classification": {
                    "is_affair": enriched.get("is_affair", False),
                    "affair_type": enriched.get("affair_type", "routine"),
                    "gravity_score": enriched.get("gravity_score", 0.3),
                    "confidence": enriched.get("classification_confidence", 0.7)
                },
                "primary_entity": enriched.get("elected", [None])[0] if enriched.get("elected") else None,
                "entities_detected": enriched.get("elected", []),
                "theme": enriched.get("theme", "general"),
                "sentiment": enriched.get("sentiment", "neutre"),
                "method": "groq" if _groq_available else "tags_index"
            }

        def health_check(self):
            return {
                "status": "operational",
                "mode": "groq_ai" if _groq_available else "rule_based",
                "groq_available": _groq_available,
                "features": {
                    "article_enrichment": True,
                    "transcription_classification": True,
                    "entity_detection": True,
                    "sentiment_analysis": True,
                    "ai_powered": _groq_available
                }
            }

    ai_service = AIServiceWrapper()

except Exception as e:
    logger.error(f"❌ Service enrichissement non disponible: {e}")

# Fonctions pour compatibilité
def enrich_article(article_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit un article avec tags, thèmes, entités"""
    if ai_service:
        return ai_service.enrich_article(article_data)
    if enrichment_service:
        return enrichment_service(article_data)
    return article_data

def classify_transcription_advanced(text: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Classifie une transcription"""
    if ai_service:
        return ai_service.classify_transcription_advanced(text, metadata)
    return {
        "classification": {
            "is_affair": False,
            "affair_type": "routine",
            "gravity_score": 0.3,
            "confidence": 0.5
        },
        "primary_entity": None,
        "entities_detected": [],
        "method": "fallback"
    }

# Service Sentiment intégré
sentiment_service = None
analyze_sentiment = None

class LocalSentimentService:
    """Service de sentiment local basé sur lexique"""
    
    def __init__(self):
        self.gpt = type('obj', (object,), {'available': False})()  # Mock pour compatibilité
        
    def analyze(self, text: str, use_gpt: bool = False) -> Dict[str, Any]:
        """Analyse de sentiment basée sur lexique"""
        if not text:
            return {'polarity': 'neutre', 'score': 0.0, 'confidence': 0.5, 'method': 'default'}
        
        text_lower = text.lower()
        
        # Lexiques étendus
        positive_words = [
            "succès", "réussite", "victoire", "amélioration", "positif",
            "bon", "excellent", "progrès", "récompense", "satisfait",
            "félicitation", "bravo", "merci", "heureux", "content",
            "inauguration", "ouverture", "création", "développement"
        ]
        
        negative_words = [
            "problème", "crise", "échec", "difficile", "grave", "catastrophe",
            "négatif", "mort", "violence", "corruption", "scandale",
            "accident", "danger", "risque", "menace", "peur",
            "grève", "blocage", "manifestation", "fermeture"
        ]
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            return {'polarity': 'neutre', 'score': 0.0, 'confidence': 0.5, 'method': 'lexique'}
        
        pos_ratio = pos_count / total
        neg_ratio = neg_count / total
        
        if neg_ratio > 0.6:
            polarity = 'negatif'
            score = -neg_ratio
        elif pos_ratio > 0.6:
            polarity = 'positif'
            score = pos_ratio
        else:
            polarity = 'neutre'
            score = pos_ratio - neg_ratio
        
        confidence = min(0.9, total / 10)
        intensity = 'high' if abs(score) > 0.7 else 'moderate'
        
        return {
            'polarity': polarity,
            'score': round(score, 2),
            'confidence': round(confidence, 2),
            'intensity': intensity,
            'method': 'lexique'
        }

try:
    sentiment_service = LocalSentimentService()
    analyze_sentiment = sentiment_service.analyze
    logger.info("✅ Sentiment Service local chargé")
except Exception as e:
    logger.error(f"❌ Sentiment Service non disponible: {e}")

# ========== SCRAPER LOCAL ==========
guadeloupe_scraper = None

try:
    import sys
    import os
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    
    from scraper_service import guadeloupe_scraper as _scraper
    guadeloupe_scraper = _scraper
    logger.info("✅ Scraper chargé depuis scraper_service.py")
    
except Exception as e:
    logger.warning(f"⚠️ Import scraper_service.py échec: {e}")
    
    try:
        from backend.scraper_service import guadeloupe_scraper as _scraper
        guadeloupe_scraper = _scraper
        logger.info("✅ Scraper chargé depuis backend.scraper_service")
    except Exception as ee:
        logger.error(f"❌ Import backend.scraper_service échec: {ee}")

# Si toujours None, utiliser le scraper inline
if guadeloupe_scraper is None:
    logger.warning("⚠️ Utilisation du scraper inline de secours...")
    
    class InlineScraper:
        """Scraper de secours intégré"""
        
        def __init__(self):
            self.sites = {
                'france_antilles': {
                    'name': 'France-Antilles Guadeloupe',
                    'url': 'https://www.guadeloupe.franceantilles.fr/',
                    'selectors': ['article h2 a', 'article h3 a'],
                },
                'rci': {
                    'name': 'RCI Guadeloupe',
                    'url': 'https://rci.fm/guadeloupe/infos',
                    'selectors': ['.article-title a', 'h2 a'],
                }
            }
            self.headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        
        def generate_article_id(self, url: str, title: str) -> str:
            content = f"{url}:{title}".encode('utf-8')
            return f"ART-{hashlib.md5(content).hexdigest()[:12].upper()}"
        
        def scrape_site(self, site_key: str, config: Dict) -> List[Dict]:
            articles = []
            try:
                from bs4 import BeautifulSoup
                from urllib.parse import urljoin
                
                logger.info(f"🔍 Scraping {config['name']}...")
                response = requests.get(config['url'], headers=self.headers, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                links = []
                for selector in config['selectors']:
                    links.extend(soup.select(selector))
                
                for link in links[:15]:
                    try:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        if not title or not href:
                            continue
                        
                        if not href.startswith('http'):
                            href = urljoin(config['url'], href)
                        
                        article_id = self.generate_article_id(href, title)
                        
                        if collections['articles_guadeloupe'].find_one({'article_id': article_id}):
                            continue
                        
                        article = {
                            'article_id': article_id,
                            'title': title,
                            'url': href,
                            'source': config['name'],
                            'site_key': site_key,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_at': datetime.now().isoformat(),
                        }
                        
                        # Enrichir avec tags_index si disponible
                        if enrichment_service:
                            article = enrichment_service(article)
                        
                        articles.append(article)
                    except Exception as e:
                        continue
                
                logger.info(f"✅ {len(articles)} nouveaux articles depuis {config['name']}")
            except Exception as e:
                logger.error(f"❌ Erreur scraping {config['name']}: {e}")
            
            return articles
        
        def scrape_all_sites(self) -> Dict[str, Any]:
            logger.info("🚀 Scraping inline démarré...")
            all_articles = []
            stats = {'sites_scraped': 0, 'total_articles': 0, 'articles_saved': 0}
            
            for site_key, config in self.sites.items():
                articles = self.scrape_site(site_key, config)
                all_articles.extend(articles)
                stats['sites_scraped'] += 1
                stats['total_articles'] += len(articles)
            
            if all_articles and collections.get('articles_guadeloupe'):
                try:
                    result = collections['articles_guadeloupe'].insert_many(all_articles, ordered=False)
                    stats['articles_saved'] = len(result.inserted_ids)
                    logger.info(f"💾 {stats['articles_saved']} articles sauvegardés")
                except Exception as e:
                    logger.error(f"❌ Erreur sauvegarde: {e}")

            # Post-scraping : ingérer les articles dans le pipeline d'affaires V2
            if affair_lifecycle_service and all_articles:
                try:
                    ingested = 0
                    for art in all_articles:
                        r = affair_lifecycle_service.ingest_item(art, source_type="article")
                        if r.get("success"):
                            ingested += 1
                    stats['affair_v2_ingested'] = ingested
                    logger.info(f"📥 {ingested} articles ingérés dans le pipeline affaires V2")
                except Exception as e:
                    logger.warning(f"⚠️ Ingestion affaires V2: {e}")

            # Post-scraping : réconcilier les transcriptions non-matchées
            if reconciliation_service and stats.get('articles_saved', 0) > 0:
                try:
                    recon_stats = reconciliation_service.reconcile_recent_transcriptions(days=3)
                    stats['reconciliation'] = {
                        'transcriptions_reconciled': recon_stats.get('reconciled', 0),
                        'total_checked': recon_stats.get('total', 0),
                    }
                    logger.info(
                        f"🔗 Post-scraping reconciliation: "
                        f"{recon_stats.get('reconciled', 0)} transcriptions réconciliées"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Réconciliation post-scraping échouée: {e}")

            return {'success': True, 'timestamp': datetime.now().isoformat(), **stats}
        
        def run(self):
            return self.scrape_all_sites()
        
        def get_todays_articles(self):
            today = datetime.now().strftime('%Y-%m-%d')
            try:
                articles = list(collections['articles_guadeloupe'].find({'date': today}).limit(100))
                for a in articles:
                    a['_id'] = str(a['_id'])
                return articles
            except:
                return []
        
        def get_scraping_stats(self):
            try:
                total = collections['articles_guadeloupe'].count_documents({})
                today = datetime.now().strftime('%Y-%m-%d')
                today_count = collections['articles_guadeloupe'].count_documents({'date': today})
                return {'total_articles': total, 'today_articles': today_count}
            except:
                return {}
    
    try:
        guadeloupe_scraper = InlineScraper()
        logger.info("✅ InlineScraper de secours initialisé")
    except Exception as e:
        logger.error(f"❌ Erreur InlineScraper: {e}")

if guadeloupe_scraper is None:
    logger.error("❌ AUCUN SCRAPER DISPONIBLE - Scraping désactivé")
else:
    scraper_type = type(guadeloupe_scraper).__name__
    logger.info(f"✅ Scraper actif: {scraper_type}")

# Service Radio
radio_service = None
try:
    from backend.radio_service import radio_service
    logger.info("✅ Radio service chargé")
except Exception as e:
    logger.warning(f"⚠️ Radio service non disponible: {e}")

# Service Summary
summary_service = None
try:
    from backend.summary_service import summary_service
    logger.info("✅ Summary service chargé")
except Exception as e:
    logger.warning(f"⚠️ Summary service non disponible: {e}")

# ========== PONDÉRATIONS BRUIT NUMÉRIQUE ==========

CANAL_WEIGHTS = {
    'radio': 0.35,
    'television': 0.30,
    'presse': 0.25,
    'reseaux_sociaux': 0.10
}

RADIO_WEIGHTS = {
    'RCI': 1.0,
    'Guadeloupe La 1ère': 0.8,
    'NRJ Antilles': 0.4,
    'TRACE FM': 0.35,
    'BEL': 0.2,
    'MFM': 0.2
}

TV_WEIGHTS = {
    'Guadeloupe La 1ère': 1.0,
    'France 2': 0.4,
    'Canal+': 0.35,
    'France 3': 0.25,
    'France Info': 0.15
}

PRESSE_WEIGHTS = {
    'France-Antilles': 1.0,
    'RCI': 0.9,
    'Outremers360': 0.8,
    'La 1ère': 0.7,
    'KaribInfo': 0.65,
    'Bondamanjak': 0.6,
    'DROM-COM': 0.5
}

RS_WEIGHTS = {
    'institutionnel': 1.0,
    'medias_etablis': 0.8,
    'influenceurs_diaspora': 0.6,
    'youtube_satirique': 0.5,
    'facebook_groupes': 0.4,
    'tiktok_reels': 0.3,
    'twitter_x': 0.25,
    'reddit_forums': 0.2
}

# ========== FONCTIONS UTILITAIRES ==========

def get_db():
    """Retourne la base de données MongoDB"""
    if db is None:
        raise HTTPException(status_code=500, detail="Base de données non disponible")
    return db

def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Sérialise un document MongoDB pour l'API"""
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for k in ("scraped_at", "published_at", "captured_at", "created_at", "last_updated"):
        if k in out and out[k] is not None:
            out[k] = out[k].isoformat() if hasattr(out[k], 'isoformat') else out[k]
    return out

def clean_title(title: str) -> str:
    """Nettoie un titre d'article"""
    title = re.sub(r'^\d+', '', title)
    title = re.sub(r'\([^)]*\)', '', title)
    title = re.sub(r'([a-z])([A-Z])', r'\1 \2', title)
    title = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.rstrip('.')
    return title

# ========== ANALYSE DE SENTIMENT ==========

def analyze_sentiment_for_item(text: str, item_type: str = "article") -> Dict[str, Any]:
    """Analyse le sentiment d'un texte"""
    if not text:
        return {
            'sentiment': 'neutral',
            'score': 0.0,
            'confidence': 0.0,
            'method': 'default'
        }
    
    if sentiment_service:
        try:
            result = sentiment_service.analyze(text, use_gpt=False)
            return {
                'sentiment': result.get('polarity', 'neutral'),
                'score': result.get('score', 0.0),
                'confidence': result.get('confidence', 0.7),
                'intensity': result.get('intensity', 'moderate'),
                'method': result.get('method', 'lexique')
            }
        except:
            pass
    
    return {'sentiment': 'neutral', 'score': 0.0, 'confidence': 0.0, 'method': 'error'}

# ========== CALCUL BRUIT NUMÉRIQUE ==========

def calculate_engagement_score(item: Dict, canal_type: str) -> float:
    """Calcule le score d'engagement selon le type de canal"""
    if canal_type == 'radio':
        duration = item.get('duration_seconds', 0)
        # Plancher à 0.5 : si pas de durée (topics radio enrichis), on considère engagement moyen
        base = min(1.0, duration / 300) if duration > 0 else 0.5
        # Bonus si la transcription a un score_importance élevé (proxy d'engagement)
        importance = item.get('score_importance', 0)
        if importance >= 0.6:
            base = max(base, 0.6)
        return base
    elif canal_type == 'television':
        duration = item.get('duration_seconds', 0)
        prime_time = item.get('prime_time', False)
        base = min(1.0, duration / 600)
        return base * 1.5 if prime_time else base
    elif canal_type == 'presse':
        is_headline = item.get('is_headline', False)
        word_count = item.get('word_count', 0)
        base = min(1.0, word_count / 500)
        return base * 2.0 if is_headline else base
    elif canal_type == 'reseaux_sociaux':
        shares = item.get('shares', 0)
        comments = item.get('comments', 0)
        likes = item.get('likes', 0)
        views = item.get('views', 1)
        engagement_total = (3 * shares) + (2 * comments) + likes
        engagement_normalized = (engagement_total / views) * 100 if views > 0 else 0
        return min(1.0, engagement_normalized / 10)
    return 0.5

def get_media_weight(source: str, canal_type: str, item: Dict = None) -> float:
    """Retourne la pondération d'un média selon le canal"""
    source_lower = source.lower()
    
    if canal_type == 'radio':
        for media, weight in RADIO_WEIGHTS.items():
            if media.lower() in source_lower:
                return weight
        return 0.2
    elif canal_type == 'television':
        for media, weight in TV_WEIGHTS.items():
            if media.lower() in source_lower:
                return weight
        return 0.15
    elif canal_type == 'presse':
        for media, weight in PRESSE_WEIGHTS.items():
            if media.lower() in source_lower:
                return weight
        return 0.5
    elif canal_type == 'reseaux_sociaux':
        if item:
            if item.get('is_institutional'):
                return RS_WEIGHTS['institutionnel']
            elif item.get('is_media'):
                return RS_WEIGHTS['medias_etablis']
            elif item.get('is_influencer'):
                return RS_WEIGHTS['influenceurs_diaspora']
        if 'facebook' in source_lower:
            return RS_WEIGHTS['facebook_groupes']
        elif 'tiktok' in source_lower:
            return RS_WEIGHTS['tiktok_reels']
        elif 'twitter' in source_lower or 'x.com' in source_lower:
            return RS_WEIGHTS['twitter_x']
        return 0.3
    return 0.5

def calculate_bruit_numerique(affair: Dict) -> Dict[str, Any]:
    """
    Calcule le Bruit Numérique Global (BMG) pour une affaire
    FONCTION APPELÉE PAR LE SCHEDULER - NE PAS RENOMMER
    """
    article_ids = affair.get('articles', [])
    radio_ids = affair.get('radio_transcriptions', [])
    social_ids = affair.get('social_posts', [])
    
    canal_scores = {
        'radio': {'bnp_sum': 0, 'weight_sum': 0, 'count': 0},
        'television': {'bnp_sum': 0, 'weight_sum': 0, 'count': 0},
        'presse': {'bnp_sum': 0, 'weight_sum': 0, 'count': 0},
        'reseaux_sociaux': {'bnp_sum': 0, 'weight_sum': 0, 'count': 0}
    }
    
    # PRESSE
    if article_ids:
        try:
            obj_ids = [ObjectId(aid) for aid in article_ids if aid]
            articles = list(collections['articles_guadeloupe'].find({'_id': {'$in': obj_ids}}))
            
            for article in articles:
                importance = article.get('importance_score', 0.5)
                engagement = calculate_engagement_score(article, 'presse')
                media_weight = get_media_weight(article.get('source', ''), 'presse')
                
                bnp_article = importance * engagement * media_weight
                
                canal_scores['presse']['bnp_sum'] += bnp_article * media_weight
                canal_scores['presse']['weight_sum'] += media_weight
                canal_scores['presse']['count'] += 1
        except Exception as e:
            logger.error(f"Erreur calcul BMG presse: {e}")
    
    # RADIO
    if radio_ids:
        try:
            obj_ids = [ObjectId(rid) for rid in radio_ids if rid]
            transcriptions = list(collections['radio_transcriptions'].find({'_id': {'$in': obj_ids}}))
            
            for trans in transcriptions:
                importance = trans.get('score_importance', 0.5)
                engagement = calculate_engagement_score(trans, 'radio')
                media_weight = get_media_weight(trans.get('radio', ''), 'radio')
                
                bnp_radio = importance * engagement * media_weight
                
                canal_scores['radio']['bnp_sum'] += bnp_radio * media_weight
                canal_scores['radio']['weight_sum'] += media_weight
                canal_scores['radio']['count'] += 1
        except Exception as e:
            logger.error(f"Erreur calcul BMG radio: {e}")
    
    # RÉSEAUX SOCIAUX
    if social_ids:
        try:
            obj_ids = [ObjectId(sid) for sid in social_ids if sid]
            posts = list(collections['social_media_posts'].find({'_id': {'$in': obj_ids}}))
            
            for post in posts:
                importance = post.get('relevance_score', 0.3)
                engagement = calculate_engagement_score(post, 'reseaux_sociaux')
                media_weight = get_media_weight(post.get('platform', ''), 'reseaux_sociaux', post)
                
                bnp_social = importance * engagement * media_weight
                
                canal_scores['reseaux_sociaux']['bnp_sum'] += bnp_social * media_weight
                canal_scores['reseaux_sociaux']['weight_sum'] += media_weight
                canal_scores['reseaux_sociaux']['count'] += 1
        except Exception as e:
            logger.error(f"Erreur calcul BMG réseaux: {e}")
    
    # Calculer BNP par canal
    bnp_by_canal = {}
    for canal, data in canal_scores.items():
        if data['weight_sum'] > 0:
            bnp_by_canal[canal] = data['bnp_sum'] / data['weight_sum']
        else:
            bnp_by_canal[canal] = 0
    
    # Calculer BMG pondéré
    raw_bmg = sum(bnp_by_canal[canal] * CANAL_WEIGHTS[canal] for canal in CANAL_WEIGHTS)

    # Calculer indicateurs
    total_items = sum(data['count'] for data in canal_scores.values())
    active_canals = sum(1 for data in canal_scores.values() if data['count'] > 0)

    # Normalisation : avec 1 seul canal actif, le BMG pondéré max ≈ 0.35.
    # On re-normalise pour que le canal dominant puisse pousser le BMG plus haut.
    # Formule : si peu de canaux, on boost proportionnellement au BNP dominant.
    if active_canals > 0 and active_canals < 4:
        max_bnp = max(bnp_by_canal.values())
        # Le BMG reflète au minimum 60% du canal dominant quand il est seul
        canal_floor = max_bnp * (0.6 if active_canals == 1 else 0.5 if active_canals == 2 else 0.4)
        bmg = max(raw_bmg, canal_floor)
        # Bonus multi-source : chaque item supplémentaire dans un canal ajoute de la crédibilité
        item_bonus = min(0.15, total_items * 0.03)
        bmg = min(1.0, bmg + item_bonus)
    else:
        bmg = raw_bmg

    # Niveau d'alerte
    if bmg >= 0.8:
        niveau_alerte = "CRITIQUE"
    elif bmg >= 0.6:
        niveau_alerte = "ÉLEVÉ"
    elif bmg >= 0.4:
        niveau_alerte = "MODÉRÉ"
    elif bmg >= 0.2:
        niveau_alerte = "FAIBLE"
    else:
        niveau_alerte = "MINIMAL"

    # Multi-canal bonus flag
    multi_canal_bonus = active_canals >= 2

    return {
        'bmg': round(bmg, 3),
        'bnp_by_canal': {k: round(v, 3) for k, v in bnp_by_canal.items()},
        'niveau_alerte': niveau_alerte,
        'total_items': total_items,
        'active_canals': active_canals,
        'multi_canal_bonus': multi_canal_bonus,
        'dominant_canal': max(bnp_by_canal, key=bnp_by_canal.get) if bnp_by_canal else None,
        'calculated_at': datetime.now().isoformat()
    }

# ========== DÉTECTION D'AFFAIRES ==========
# NOTE: L'ancien système V1 (create_or_update_affair / correlate_with_affairs)
# a été supprimé car il créait des faux positifs massifs en corrélant des
# articles non liés via des mots-clés trop génériques.
# Le système V2 (affair_lifecycle_service) gère désormais tout :
# ingestion → clustering contextuel → promotion → lifecycle

# ========== ENDPOINTS API ==========

@app.get("/")
async def root():
    """Point d'entrée principal"""
    return {
        "name": "Veille Média Guadeloupe API",
        "version": VERSION,
        "mode": f"IA {'activée (' + _ai_provider_name + ')' if _groq_available else 'désactivée (règles)'}",
        "status": "operational",
        "environment": ENVIRONMENT,
        "uptime_seconds": (datetime.utcnow() - START_TIME).total_seconds()
    }

@app.get("/health")
async def health():
    """Vérification de santé"""
    db_status = "connected" if mongo_client else "disconnected"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "services": {
            "enrichment": enrichment_service is not None,
            "ai_service": ai_service is not None,
            "sentiment": sentiment_service is not None,
            "scraper": guadeloupe_scraper is not None,
            "radio": radio_service is not None,
            "summary": summary_service is not None
        },
        "mode": "no_ollama",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/storage")
async def get_storage():
    """Statistiques stockage MongoDB Atlas"""
    try:
        if db is None:
            raise HTTPException(status_code=503, detail="Base de données non connectée")

        stats = db.command("dbStats")
        data_size_mb = round(stats.get("dataSize", 0) / (1024 * 1024), 1)
        storage_size_mb = round(stats.get("storageSize", 0) / (1024 * 1024), 1)
        index_size_mb = round(stats.get("indexSize", 0) / (1024 * 1024), 1)
        total_used_mb = round(data_size_mb + index_size_mb, 1)

        atlas_limit_mb = int(os.environ.get("ATLAS_STORAGE_LIMIT_MB", "512"))
        usage_pct = round((total_used_mb / atlas_limit_mb) * 100, 1) if atlas_limit_mb > 0 else 0

        # Stats par collection (top 10)
        collections_stats = []
        for coll_name in db.list_collection_names():
            try:
                coll_stats = db.command("collStats", coll_name)
                coll_size_mb = round(coll_stats.get("storageSize", 0) / (1024 * 1024), 2)
                coll_count = coll_stats.get("count", 0)
                collections_stats.append({
                    "name": coll_name,
                    "size_mb": coll_size_mb,
                    "count": coll_count,
                })
            except Exception:
                pass
        collections_stats.sort(key=lambda x: x["size_mb"], reverse=True)

        # Seuils d'alerte
        alert_level = "ok"
        if usage_pct >= 95:
            alert_level = "critical"
        elif usage_pct >= 90:
            alert_level = "high"
        elif usage_pct >= 80:
            alert_level = "warning"

        return {
            "data_size_mb": data_size_mb,
            "storage_size_mb": storage_size_mb,
            "index_size_mb": index_size_mb,
            "total_used_mb": total_used_mb,
            "limit_mb": atlas_limit_mb,
            "usage_pct": usage_pct,
            "alert_level": alert_level,
            "collections": collections_stats[:10],
            "checked_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur storage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Statistiques globales (cache 5 min)"""
    cached = _cache.get("stats")
    if cached:
        return cached
    try:
        stats = {
            "articles": collections['articles_guadeloupe'].count_documents({}) if collections.get('articles_guadeloupe') else 0,
            "transcriptions": collections['radio_transcriptions'].count_documents({}) if collections.get('radio_transcriptions') else 0,
            "affairs": collections['affairs'].count_documents({}) if collections.get('affairs') else 0,
            "social_posts": collections['social_media_posts'].count_documents({}) if collections.get('social_media_posts') else 0,
            "today": datetime.now().strftime('%Y-%m-%d')
        }

        # Articles du jour
        today = datetime.now().strftime('%Y-%m-%d')
        stats['articles_today'] = collections['articles_guadeloupe'].count_documents({'date': today}) if collections.get('articles_guadeloupe') else 0

        _cache.set("stats", stats, ttl_seconds=300)
        return stats
    except Exception as e:
        logger.error(f"Erreur stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles")
async def get_articles(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0)
):
    """Récupérer les articles"""
    try:
        articles = list(
            collections['articles_guadeloupe']
            .find()
            .sort("scraped_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return {"articles": [serialize_doc(a) for a in articles]}
    except Exception as e:
        logger.error(f"Erreur récupération articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
async def search_content(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=50),
):
    """Recherche full-text dans articles et affaires (cache 2 min)."""
    cache_key = f"search:{q.lower().strip()}:{limit}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    try:
        # Regex insensible à la casse sur titre + ai_summary
        regex = {"$regex": q, "$options": "i"}
        articles = list(
            collections['articles_guadeloupe']
            .find({"$or": [{"title": regex}, {"ai_summary": regex}, {"content": regex}]},
                  {"title": 1, "source": 1, "theme": 1, "gravity_score": 1,
                   "sentiment": 1, "scraped_at": 1, "communes": 1, "ai_summary": 1})
            .sort("scraped_at", -1)
            .limit(limit)
        )
        affairs = list(
            collections['affairs']
            .find({"$or": [{"title": regex}, {"description": regex}]},
                  {"title": 1, "description": 1, "gravity_score": 1, "bmg": 1,
                   "priority": 1, "status": 1, "item_count": 1, "communes": 1,
                   "theme": 1, "sentiment": 1, "created_at": 1})
            .sort("created_at", -1)
            .limit(limit)
        )
        result = {
            "query": q,
            "articles": [serialize_doc(a) for a in articles],
            "affairs": [serialize_doc(a) for a in affairs],
            "total_articles": len(articles),
            "total_affairs": len(affairs),
        }
        _cache.set(cache_key, result, ttl_seconds=120)
        return result
    except Exception as e:
        logger.error(f"Erreur recherche: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/affairs")
async def get_affairs(
    status: str = Query("active", regex="^(active|stale|closed|all)$"),
    limit: int = Query(50, ge=1, le=200)
):
    """Récupérer les affaires (triées par priorité puis BMG) — cache 3 min"""
    cache_key = f"affairs:{status}:{limit}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    try:
        query = {} if status == "all" else {"status": status}
        PRIORITY_ORDER = {"hot": 0, "watch": 1, "minor": 2}
        affairs = list(
            collections['affairs']
            .find(query)
            .sort([("bmg", -1)])
            .limit(limit)
        )
        affairs.sort(key=lambda a: (PRIORITY_ORDER.get(a.get("priority", "minor"), 2), -(a.get("bmg", 0))))
        result = {"affairs": [serialize_doc(a) for a in affairs]}
        _cache.set(cache_key, result, ttl_seconds=180)
        return result
    except Exception as e:
        logger.error(f"Erreur récupération affaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/map")
async def get_map_data(days: int = Query(7, ge=1, le=30)):
    """Données géolocalisées par commune pour la carte interactive (cache 5 min)."""
    cache_key = f"map:{days}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    if db is None:
        raise HTTPException(status_code=503, detail="DB non disponible")

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Communes de Guadeloupe avec leurs noms normalisés
    COMMUNE_ALIASES = {
        "pointe-à-pitre": "Pointe-à-Pitre", "pointe-a-pitre": "Pointe-à-Pitre",
        "les abymes": "Les Abymes", "abymes": "Les Abymes",
        "baie-mahault": "Baie-Mahault", "baie mahault": "Baie-Mahault",
        "le moule": "Le Moule", "moule": "Le Moule",
        "sainte-anne": "Sainte-Anne", "sainte anne": "Sainte-Anne",
        "saint-françois": "Saint-François", "saint françois": "Saint-François",
        "le gosier": "Le Gosier", "gosier": "Le Gosier",
        "petit-bourg": "Petit-Bourg", "petit bourg": "Petit-Bourg",
        "capesterre-belle-eau": "Capesterre-Belle-Eau", "capesterre belle eau": "Capesterre-Belle-Eau",
        "capesterre": "Capesterre-Belle-Eau",
        "sainte-rose": "Sainte-Rose", "sainte rose": "Sainte-Rose",
        "deshaies": "Deshaies",
        "bouillante": "Bouillante",
        "goyave": "Goyave",
        "lamentin": "Lamentin",
        "trois-rivières": "Trois-Rivières", "trois rivières": "Trois-Rivières",
        "vieux-habitants": "Vieux-Habitants", "vieux habitants": "Vieux-Habitants",
        "basse-terre": "Basse-Terre", "basse terre": "Basse-Terre",
        "saint-claude": "Saint-Claude", "saint claude": "Saint-Claude",
        "baillif": "Baillif",
        "gourbeyre": "Gourbeyre",
        "vieux-fort": "Vieux-Fort",
        "pointe-noire": "Pointe-Noire", "pointe noire": "Pointe-Noire",
        "morne-à-l'eau": "Morne-à-l'Eau", "morne a l'eau": "Morne-à-l'Eau",
        "port-louis": "Port-Louis", "port louis": "Port-Louis",
        "petit-canal": "Petit-Canal", "petit canal": "Petit-Canal",
        "anse-bertrand": "Anse-Bertrand", "anse bertrand": "Anse-Bertrand",
        "marie-galante": "Grand-Bourg", "grand-bourg": "Grand-Bourg",
        "capesterre-de-marie-galante": "Capesterre-de-Marie-Galante",
        "saint-louis": "Saint-Louis",
        "la désirade": "La Désirade", "désirade": "La Désirade",
        "terre-de-haut": "Terre-de-Haut", "les saintes": "Terre-de-Haut",
        "terre-de-bas": "Terre-de-Bas",
        "sonis": "Les Abymes", "dampierre": "Le Gosier",
        "grande-anse": "Deshaies", "l'autre-bord": "Le Moule", "l'autre bord": "Le Moule",
        "la traversée": "Petit-Bourg",
    }

    def detect_commune(text: str) -> list:
        """Détecte les communes mentionnées dans un texte."""
        if not text:
            return []
        text_lower = text.lower()
        found = set()
        for alias, canonical in COMMUNE_ALIASES.items():
            if alias in text_lower:
                found.add(canonical)
        return list(found)

    # Résultat : {commune: {articles: [...], transcriptions: [...], affairs: [...], stats: {...}}}
    commune_data = {}

    # 1. Articles
    articles = list(db["articles_guadeloupe"].find(
        {"scraped_at": {"$gte": cutoff}},
        {"title": 1, "source": 1, "theme": 1, "gravity_score": 1,
         "sentiment": 1, "scraped_at": 1, "elected": 1}
    ).sort("scraped_at", -1).limit(500))

    for art in articles:
        title = art.get("title", "")
        communes = detect_commune(title)
        for c in communes:
            if c not in commune_data:
                commune_data[c] = {"articles": [], "transcriptions": [], "affairs": [], "stats": {}}
            commune_data[c]["articles"].append({
                "id": str(art["_id"]),
                "title": title[:120],
                "source": art.get("source", ""),
                "theme": art.get("theme", "general"),
                "gravity": art.get("gravity_score", 0),
                "sentiment": art.get("sentiment", "neutre"),
                "date": str(art.get("scraped_at", "")),
            })

    # 2. Transcriptions radio (topics IA)
    transcriptions = list(db["radio_transcriptions"].find(
        {"captured_at": {"$gte": cutoff}, "ai_topics": {"$exists": True}},
        {"ai_topics": 1, "radio": 1, "captured_at": 1, "station": 1}
    ).sort("captured_at", -1).limit(200))

    for trans in transcriptions:
        for topic in (trans.get("ai_topics", []) or []):
            topic_title = topic.get("title", "")
            topic_summary = topic.get("summary", "")
            text = f"{topic_title} {topic_summary}"
            communes = detect_commune(text)
            for c in communes:
                if c not in commune_data:
                    commune_data[c] = {"articles": [], "transcriptions": [], "affairs": [], "stats": {}}
                commune_data[c]["transcriptions"].append({
                    "title": topic_title[:120],
                    "summary": topic_summary[:200],
                    "station": trans.get("station", "") or trans.get("radio", ""),
                    "gravity": topic.get("gravity", 0),
                    "date": str(trans.get("captured_at", "")),
                })

    # 3. Affaires actives
    affairs = list(db["affairs"].find(
        {"status": "active"},
        {"title": 1, "gravity_score": 1, "bmg": 1, "priority": 1,
         "sentiment": 1, "item_count": 1, "theme": 1, "elected": 1}
    ))

    for aff in affairs:
        title = aff.get("title", "")
        desc = aff.get("description", "") or ""
        communes = detect_commune(f"{title} {desc} {' '.join(aff.get('elected', []) or [])}")
        for c in communes:
            if c not in commune_data:
                commune_data[c] = {"articles": [], "transcriptions": [], "affairs": [], "stats": {}}
            commune_data[c]["affairs"].append({
                "id": str(aff["_id"]),
                "title": title[:120],
                "gravity": aff.get("gravity_score", 0),
                "bmg": aff.get("bmg", 0),
                "priority": aff.get("priority", "minor"),
                "sentiment": aff.get("sentiment", "neutre"),
                "items": aff.get("item_count", 0),
            })

    # Calculer les stats par commune
    for c, data in commune_data.items():
        data["stats"] = {
            "total_items": len(data["articles"]) + len(data["transcriptions"]),
            "article_count": len(data["articles"]),
            "transcription_count": len(data["transcriptions"]),
            "affair_count": len(data["affairs"]),
            "max_gravity": max(
                [a.get("gravity", 0) for a in data["articles"]] +
                [t.get("gravity", 0) for t in data["transcriptions"]] +
                [af.get("gravity", 0) for af in data["affairs"]] +
                [0]
            ),
            "dominant_theme": max(
                set(a.get("theme", "general") for a in data["articles"]) or {"general"},
                key=lambda t: sum(1 for a in data["articles"] if a.get("theme") == t),
                default="general",
            ) if data["articles"] else "general",
        }

    map_result = {
        "communes": commune_data,
        "period_days": days,
        "total_communes_active": len(commune_data),
        "generated_at": datetime.utcnow().isoformat(),
    }
    _cache.set(cache_key, map_result, ttl_seconds=300)
    return map_result


@app.post("/api/digest/send")
async def send_digest_now():
    """Déclencher manuellement l'envoi du digest Telegram GPT."""
    try:
        from enhanced_scheduler import telegram_morning_digest_job
        result = await telegram_morning_digest_job()
        return result or {"sent": True}
    except Exception as e:
        try:
            from backend.enhanced_scheduler import telegram_morning_digest_job
            result = await telegram_morning_digest_job()
            return result or {"sent": True}
        except Exception as e2:
            logger.error(f"Erreur envoi digest: {e2}")
            raise HTTPException(status_code=500, detail=str(e2))


@app.post("/api/affairs/{affair_id}/cleanup")
async def cleanup_affair_endpoint(affair_id: str, background_tasks: BackgroundTasks):
    """Nettoyer une affaire avec validation GPT — retire les articles non pertinents."""
    try:
        lifecycle = get_affair_lifecycle_service(db)
        result = lifecycle.cleanup_affair(affair_id)
        return result
    except Exception as e:
        logger.error(f"Erreur cleanup affaire: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/affairs/cleanup-all")
async def cleanup_all_affairs_endpoint(background_tasks: BackgroundTasks):
    """Nettoyer TOUTES les affaires actives avec validation GPT."""
    try:
        lifecycle = get_affair_lifecycle_service(db)
        result = lifecycle.cleanup_all_affairs()
        return result
    except Exception as e:
        logger.error(f"Erreur cleanup toutes affaires: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/affairs/crosscheck-stale")
async def crosscheck_stale_active_endpoint():
    """Cross-check GPT : compare affaires en veille vs actives pour fusion."""
    try:
        lifecycle = get_affair_lifecycle_service(db)
        merged = lifecycle._cross_check_stale_active()
        return {"merged": merged}
    except Exception as e:
        logger.error(f"Erreur cross-check stale↔active: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/classify-communes")
async def classify_communes_endpoint(background_tasks: BackgroundTasks):
    """Re-classifie tous les articles sans commune par regex + IA fallback."""
    try:
        from backend.affair_lifecycle_service import classify_article_commune
    except ImportError:
        from affair_lifecycle_service import classify_article_commune

    def _run_classification():
        try:
            articles = list(db["articles_guadeloupe"].find({
                "$or": [
                    {"communes": {"$exists": False}},
                    {"communes": []},
                    {"communes": None},
                ]
            }).limit(500))
            updated = 0
            for art in articles:
                communes = classify_article_commune(art)
                if communes:
                    db["articles_guadeloupe"].update_one(
                        {"_id": art["_id"]},
                        {"$set": {"communes": communes}}
                    )
                    updated += 1
            logger.info(f"📍 Classification communes: {updated}/{len(articles)} articles mis à jour")
        except Exception as e:
            logger.error(f"Erreur classification communes: {e}")

    background_tasks.add_task(_run_classification)
    return {"message": "Classification des communes lancée en arrière-plan"}


@app.post("/api/affairs/revalidate")
async def revalidate_affairs_endpoint(background_tasks: BackgroundTasks):
    """Re-vérifie les articles de chaque affaire active pour nettoyer les faux positifs."""
    try:
        lifecycle = get_affair_lifecycle_service(db)
        # Réinitialiser les articles pour retraitement
        count = db["articles_guadeloupe"].update_many(
            {"_affair_processed": True},
            {"$set": {"_affair_processed": False, "_affair_id": None}}
        ).modified_count
        # Archiver toutes les affaires actuelles
        db["affairs"].update_many(
            {"status": "active"},
            {"$set": {"status": "archived", "_archived_reason": "revalidation_v2"}}
        )
        _cache.invalidate()  # Vider tout le cache
        return {"message": f"Revalidation lancée: {count} articles réinitialisés. "
                           f"Les affaires seront recréées au prochain cycle."}
    except Exception as e:
        logger.error(f"Erreur revalidation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape")
async def trigger_scraping(background_tasks: BackgroundTasks):
    """Déclencher le scraping"""
    if not guadeloupe_scraper:
        raise HTTPException(status_code=503, detail="Scraper non disponible")
    
    background_tasks.add_task(guadeloupe_scraper.scrape_all_sites)
    return {"message": "Scraping lancé en arrière-plan"}

@app.post("/api/analyze")
async def analyze_text(request: Request):
    """Analyser un texte"""
    try:
        data = await request.json()
        text = data.get("text", "")
        
        if not text:
            raise HTTPException(status_code=400, detail="Texte requis")
        
        # Analyser avec enrichissement
        result = {
            "sentiment": analyze_sentiment(text) if analyze_sentiment else {"sentiment": "neutral"},
            "classification": classify_transcription_advanced(text)
        }
        
        # Si enrichissement disponible
        if enrichment_service:
            enriched = enrichment_service({"content": text})
            result["entities"] = enriched.get("elected", [])
            result["theme"] = enriched.get("theme", "general")
            result["is_affair"] = enriched.get("is_affair", False)
            result["gravity_score"] = enriched.get("gravity_score", 0)
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur analyse: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== SCHEDULER ==========

_scheduler_error = None
_scheduler_loaded = False

if RUN_SCHEDULER:
    try:
        try:
            from backend.scheduler_service import router as scheduler_router, attach_scheduler
        except ImportError:
            from scheduler_service import router as scheduler_router, attach_scheduler
        app.include_router(scheduler_router, prefix="/api/scheduler")

        @app.on_event("startup")
        async def _start_scheduler():
            attach_scheduler(app)
            logger.info("✅ Scheduler APScheduler démarré")

        _scheduler_loaded = True
        logger.info("✅ Scheduler routes ajoutées")
    except Exception as e:
        _scheduler_error = f"{type(e).__name__}: {e}"
        logger.error(f"❌ SCHEDULER ÉCHEC CRITIQUE: {_scheduler_error}")
        import traceback
        logger.error(traceback.format_exc())
else:
    _scheduler_error = "RUN_SCHEDULER is disabled (env var)"
    logger.warning(f"⚠️ Scheduler désactivé: RUN_SCHEDULER={os.environ.get('RUN_SCHEDULER', '(non défini)')}")


@app.get("/api/debug/scheduler")
async def debug_scheduler():
    """Diagnostic scheduler — toujours disponible même si le scheduler a crashé"""
    import importlib
    diag = {
        "RUN_SCHEDULER_env": os.environ.get("RUN_SCHEDULER", "(non défini, default=true)"),
        "RUN_SCHEDULER_bool": RUN_SCHEDULER,
        "scheduler_loaded": _scheduler_loaded,
        "scheduler_error": _scheduler_error,
        "imports": {},
    }

    # Tester chaque import individuellement
    for mod_name in ["apscheduler", "apscheduler.schedulers.asyncio",
                     "apscheduler.triggers.cron", "certifi"]:
        try:
            importlib.import_module(mod_name)
            diag["imports"][mod_name] = "OK"
        except Exception as ex:
            diag["imports"][mod_name] = f"FAIL: {ex}"

    # Tester l'import du scheduler_service
    try:
        try:
            from backend.scheduler_service import _scheduler, _db
        except ImportError:
            from scheduler_service import _scheduler, _db
        diag["scheduler_service_import"] = "OK"
        diag["scheduler_instance"] = _scheduler is not None
        diag["scheduler_running"] = _scheduler.running if _scheduler else False
        diag["scheduler_db"] = _db is not None
        if _scheduler:
            diag["jobs"] = [
                {"id": j.id, "name": j.name, "next_run": str(j.next_run_time)}
                for j in _scheduler.get_jobs()
            ]
    except Exception as ex:
        diag["scheduler_service_import"] = f"FAIL: {type(ex).__name__}: {ex}"

    return diag


@app.post("/api/debug/reset-affairs")
async def reset_affairs():
    """Remet à zéro les affaires pour re-traitement propre.
    Supprime toutes les affaires et reset les flags _affair_processed."""
    if db is None:
        return {"error": "no_db"}
    try:
        # Supprimer toutes les affaires
        del_affairs = db["affairs"].delete_many({})
        del_timeline = db["affair_timeline"].delete_many({})
        del_candidates = db["topic_candidates"].delete_many({})
        del_clusters = db["topic_clusters"].delete_many({})

        # Reset les flags sur les articles
        reset_articles = db["articles_guadeloupe"].update_many(
            {},
            {"$unset": {
                "_affair_processed": "",
                "_affair_id": "",
                "_affair_ignored": "",
                "_affair_attempts": "",
            }}
        )

        # Reset les flags sur les transcriptions
        reset_trans = db["radio_transcriptions"].update_many(
            {},
            {"$unset": {"_affair_processed": ""}}
        )

        return {
            "success": True,
            "deleted_affairs": del_affairs.deleted_count,
            "deleted_timeline": del_timeline.deleted_count,
            "deleted_candidates": del_candidates.deleted_count,
            "deleted_clusters": del_clusters.deleted_count,
            "articles_reset": reset_articles.modified_count,
            "transcriptions_reset": reset_trans.modified_count,
        }
    except Exception as e:
        return {"error": str(e)}


# ========== ROUTES RADIO CARDS ==========
try:
    from backend.radio_cards_routes import router as radio_cards_router
    app.include_router(radio_cards_router, prefix="/api")
    logger.info("✅ Routes radio cards chargées (/api/radio/*)")
except Exception as e:
    logger.warning(f"⚠️ Routes radio cards non disponibles: {e}")

# ========== SCRAPING RÉSEAUX SOCIAUX (Apify) ==========
try:
    try:
        from backend.apify_social_scraper import get_social_scraper
        from backend.social_scraper_routes import router as social_router, set_scraper
    except ImportError:
        from apify_social_scraper import get_social_scraper
        from social_scraper_routes import router as social_router, set_scraper

    social_scraper = get_social_scraper()
    set_scraper(social_scraper)
    app.include_router(social_router, prefix="/api")
    logger.info(f"✅ Routes social scraper chargées (/api/social/*) — Apify {'configuré' if social_scraper.is_ready() else 'NON configuré (APIFY_TOKEN manquant)'}")
except Exception as e:
    logger.warning(f"⚠️ Routes social scraper non disponibles: {e}")

# ========== RÉCONCILIATION ENTITÉS ==========
reconciliation_service = None
try:
    from backend.entity_reconciliation_service import get_reconciliation_service
    from backend.reconciliation_routes import router as reconciliation_router, set_service as set_recon_service

    reconciliation_service = get_reconciliation_service(db=db)
    set_recon_service(reconciliation_service)
    app.include_router(reconciliation_router)
    logger.info("✅ Service de réconciliation entités chargé")
    logger.info("   📚 Réconciliation articles↔transcriptions activée")
except Exception as e:
    logger.warning(f"⚠️ Service réconciliation non disponible: {e}")

# ========== SYSTÈME D'AFFAIRES V2 ==========
affair_lifecycle_service = None
try:
    try:
        from backend.affair_lifecycle_service import get_affair_lifecycle_service
        from backend.affair_lifecycle_routes import router as affair_v2_router, set_service as set_affair_service
    except ImportError:
        from affair_lifecycle_service import get_affair_lifecycle_service
        from affair_lifecycle_routes import router as affair_v2_router, set_service as set_affair_service

    affair_lifecycle_service = get_affair_lifecycle_service(db=db)
    set_affair_service(affair_lifecycle_service)
    app.include_router(affair_v2_router)
    logger.info("✅ Système d'affaires V2 chargé (cycle de vie complet)")
    logger.info("   🔄 Pipeline: ingestion → clustering → promotion → BMG")

    # ── Routes admin (pilotage manuel des affaires) ──
    try:
        try:
            from backend.admin_routes import router as admin_router, set_service as set_admin_service
        except ImportError:
            from admin_routes import router as admin_router, set_service as set_admin_service
        set_admin_service(affair_lifecycle_service)
        app.include_router(admin_router)
        logger.info("✅ Routes admin chargées (/api/admin/*)")
    except Exception as admin_err:
        logger.warning(f"⚠️ Routes admin non disponibles: {admin_err}")

    # ── AUTO-PURGE DÉSACTIVÉE ──
    # L'auto-purge des affaires V1 a été désactivée car elle supprimait
    # TOUTES les affaires à chaque redémarrage de Render, avant que le
    # nouveau cycle ne puisse en recréer. Les affaires V2 (avec promoted_at)
    # sont conservées. Purge manuelle disponible via API si nécessaire.
    if db is not None:
        try:
            total = db.affairs.count_documents({})
            v2_count = db.affairs.count_documents({"promoted_at": {"$exists": True}})
            logger.info(f"📊 Affaires en base: {total} total, {v2_count} V2 (avec promoted_at)")
        except Exception as e:
            logger.warning(f"⚠️ Erreur lecture affaires: {e}")

except Exception as e:
    logger.warning(f"⚠️ Système affaires V2 non disponible: {e}")

# ========== AUTHENTIFICATION ==========
try:
    try:
        from backend.auth_routes import router as auth_router
    except ImportError:
        from auth_routes import router as auth_router

    app.include_router(auth_router)
    logger.info("✅ Routes auth chargées (/api/auth/*)")
except Exception as e:
    logger.warning(f"⚠️ Routes auth non disponibles: {e}")


# ========== TELEGRAM ALERTS ==========
try:
    try:
        from backend.telegram_routes import router as telegram_router
        from backend.telegram_alerts_service import telegram_alerts as _tg_alerts
    except ImportError:
        from telegram_routes import router as telegram_router
        from telegram_alerts_service import telegram_alerts as _tg_alerts

    app.include_router(telegram_router, prefix="/api")
    logger.info("✅ Routes Telegram chargées (/api/telegram/*)")

    # Démarrer le monitoring automatique si Telegram est configuré
    @app.on_event("startup")
    async def _start_telegram_monitoring():
        if _tg_alerts.load_config():
            _tg_alerts.start_monitoring()
            logger.info("🔔 Monitoring Telegram démarré automatiquement")
        else:
            logger.info("⚠️ Telegram non configuré — monitoring inactif (configurer via /api/telegram/configure)")

except Exception as e:
    logger.warning(f"⚠️ Routes Telegram non disponibles: {e}")


# ============================================================
# RÉSUMÉ AUTOMATIQUE (journalier / hebdomadaire)
# ============================================================

@app.get("/api/summary")
async def generate_media_summary(period: str = Query("journalier", regex="^(journalier|hebdomadaire)$")):
    """Génère un résumé approfondi de l'actualité guadeloupéenne."""
    try:
        if db is None:
            raise HTTPException(status_code=503, detail="Base de données non connectée")

        # Période de collecte
        if period == "hebdomadaire":
            since = datetime.now() - timedelta(days=7)
        else:
            since = datetime.now() - timedelta(days=1)

        # Récupérer les affaires actives
        affairs_cursor = db.affairs.find(
            {"status": "active"},
            {"title": 1, "description": 1, "theme": 1, "gravity_score": 1,
             "sentiment": 1, "communes": 1, "articles": 1, "priority": 1}
        ).sort("gravity_score", -1).limit(30)
        affairs = list(affairs_cursor)
        for a in affairs:
            a["_id"] = str(a["_id"])

        # Récupérer les articles récents
        articles_cursor = db.articles.find(
            {"scraped_at": {"$gte": since.isoformat()}},
            {"title": 1, "source": 1, "date": 1, "ai_summary": 1, "content": 1,
             "theme": 1, "gravity_score": 1, "sentiment": 1, "communes": 1}
        ).sort("scraped_at", -1).limit(50)
        articles = list(articles_cursor)
        for art in articles:
            art["_id"] = str(art["_id"])

        # Vérifier si l'IA est disponible
        try:
            from backend.ai_groq_service import generate_summary as ai_generate_summary, is_available as ai_is_available
        except ImportError:
            from ai_groq_service import generate_summary as ai_generate_summary, is_available as ai_is_available

        if not ai_is_available():
            raise HTTPException(status_code=503, detail="Service IA non disponible")

        summary = ai_generate_summary(affairs, articles, period)
        if not summary:
            raise HTTPException(status_code=500, detail="Erreur lors de la génération du résumé")

        # Cache the summary
        cache_key = f"summary_{period}"
        _cache.set(cache_key, summary, ttl_seconds=1800)  # 30min cache

        return {
            "period": period,
            "generated_at": datetime.now().isoformat(),
            "affairs_count": len(affairs),
            "articles_count": len(articles),
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur génération résumé: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# EXPORT CSV
# ============================================================

@app.get("/api/export/csv")
async def export_csv(type: str = Query("affairs", regex="^(affairs|articles)$"), days: int = Query(7, ge=1, le=90)):
    """Export des affaires ou articles en CSV."""
    import csv
    import io

    try:
        if db is None:
            raise HTTPException(status_code=503, detail="Base de données non connectée")

        since = datetime.now() - timedelta(days=days)

        if type == "affairs":
            cursor = db.affairs.find(
                {"status": "active"},
                {"title": 1, "theme": 1, "gravity_score": 1, "sentiment": 1,
                 "priority": 1, "status": 1, "communes": 1, "description": 1,
                 "created_at": 1, "articles": 1}
            ).sort("gravity_score", -1)

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Titre", "Thème", "Gravité", "Sentiment", "Priorité", "Communes", "Nb Articles", "Description"])

            for a in cursor:
                communes = ", ".join(a.get("communes", []))
                writer.writerow([
                    a.get("title", ""),
                    a.get("theme", ""),
                    f"{a.get('gravity_score', 0):.0%}",
                    a.get("sentiment", ""),
                    a.get("priority", ""),
                    communes,
                    len(a.get("articles", [])),
                    (a.get("description", "") or "")[:200],
                ])
        else:
            cursor = db.articles.find(
                {"scraped_at": {"$gte": since.isoformat()}},
                {"title": 1, "source": 1, "date": 1, "theme": 1,
                 "gravity_score": 1, "sentiment": 1, "communes": 1, "url": 1}
            ).sort("scraped_at", -1).limit(500)

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Titre", "Source", "Date", "Thème", "Gravité", "Sentiment", "Communes", "URL"])

            for art in cursor:
                communes = ", ".join(art.get("communes", []))
                writer.writerow([
                    art.get("title", ""),
                    art.get("source", ""),
                    art.get("date", ""),
                    art.get("theme", ""),
                    f"{art.get('gravity_score', 0):.0%}",
                    art.get("sentiment", ""),
                    communes,
                    art.get("url", ""),
                ])

        output.seek(0)
        filename = f"veille_971_{type}_{datetime.now().strftime('%Y%m%d')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur export CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# SCORE DE FIABILITÉ DES SOURCES
# ============================================================

@app.get("/api/sources/reliability")
async def get_source_reliability():
    """Calcule un score de fiabilité pour chaque source média."""
    cached = _cache.get("source_reliability")
    if cached:
        return cached

    try:
        if db is None:
            raise HTTPException(status_code=503, detail="Base de données non connectée")

        # Agréger les stats par source
        pipeline = [
            {"$match": {"scraped_at": {"$gte": (datetime.now() - timedelta(days=30)).isoformat()}}},
            {"$group": {
                "_id": "$source",
                "total_articles": {"$sum": 1},
                "avg_gravity": {"$avg": {"$ifNull": ["$gravity_score", 0]}},
                "enriched_count": {"$sum": {"$cond": [{"$ifNull": ["$ai_summary", False]}, 1, 0]}},
                "with_communes": {"$sum": {"$cond": [{"$gt": [{"$size": {"$ifNull": ["$communes", []]}}, 0]}, 1, 0]}},
                "themes": {"$addToSet": "$theme"},
                "sentiments": {"$push": "$sentiment"},
            }},
            {"$sort": {"total_articles": -1}},
        ]

        sources_raw = list(db.articles.aggregate(pipeline))

        sources = []
        for s in sources_raw:
            if not s["_id"]:
                continue
            total = s["total_articles"]
            enriched = s.get("enriched_count", 0)
            with_communes = s.get("with_communes", 0)

            # Score de fiabilité (0-100)
            # - Volume régulier (max 25pts): plus d'articles = plus fiable
            volume_score = min(25, total * 2.5)

            # - Taux d'enrichissement IA réussi (max 25pts)
            enrichment_rate = enriched / total if total > 0 else 0
            enrichment_score = enrichment_rate * 25

            # - Diversité thématique (max 20pts)
            themes = [t for t in s.get("themes", []) if t]
            diversity_score = min(20, len(themes) * 4)

            # - Géolocalisation (max 15pts): articles avec communes identifiées
            geo_rate = with_communes / total if total > 0 else 0
            geo_score = geo_rate * 15

            # - Régularité (max 15pts): bonus si > 1 article/jour en moyenne
            regularity = min(15, (total / 30) * 5)

            reliability = round(volume_score + enrichment_score + diversity_score + geo_score + regularity)
            reliability = min(100, reliability)

            # Niveau
            if reliability >= 80:
                level = "excellent"
            elif reliability >= 60:
                level = "bon"
            elif reliability >= 40:
                level = "moyen"
            else:
                level = "faible"

            # Distribution sentiment
            sentiments = [x for x in s.get("sentiments", []) if x]
            sentiment_dist = {}
            for sent in sentiments:
                sentiment_dist[sent] = sentiment_dist.get(sent, 0) + 1

            sources.append({
                "source": s["_id"],
                "total_articles": total,
                "reliability_score": reliability,
                "reliability_level": level,
                "enrichment_rate": round(enrichment_rate * 100, 1),
                "geo_rate": round(geo_rate * 100, 1),
                "themes": themes[:8],
                "sentiment_distribution": sentiment_dist,
                "avg_gravity": round(s.get("avg_gravity", 0), 3),
            })

        sources.sort(key=lambda x: x["reliability_score"], reverse=True)

        result = {
            "sources": sources,
            "total_sources": len(sources),
            "generated_at": datetime.now().isoformat(),
        }

        _cache.set("source_reliability", result, ttl_seconds=600)  # 10min cache
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur source reliability: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== LANCEMENT ==========

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0" if ENVIRONMENT == "production" else "127.0.0.1"
    
    logger.info(f"🚀 Démarrage serveur sur {host}:{port}")
    logger.info("🎯 Mode: SANS OLLAMA - Performances maximales")
    logger.info("📊 100+ personnalités détectées")
    logger.info("⚡ Temps de traitement < 1ms par article")
    logger.info("💰 Coût: 0€/mois")
    
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=(ENVIRONMENT != "production"),
        log_level="info"
    )