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
import requests
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId

from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
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
RUN_SCHEDULER = os.environ.get("RUN_SCHEDULER", "true").lower() == "true"
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        return min(1.0, duration / 300)
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
    
    # Calculer BMG
    bmg = sum(bnp_by_canal[canal] * CANAL_WEIGHTS[canal] for canal in CANAL_WEIGHTS)
    
    # Calculer indicateurs
    total_items = sum(data['count'] for data in canal_scores.values())
    active_canals = sum(1 for data in canal_scores.values() if data['count'] > 0)
    
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
    
    return {
        'bmg': round(bmg, 3),
        'bnp_by_canal': {k: round(v, 3) for k, v in bnp_by_canal.items()},
        'niveau_alerte': niveau_alerte,
        'total_items': total_items,
        'active_canals': active_canals,
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

@app.get("/api/stats")
async def get_stats():
    """Statistiques globales"""
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

@app.get("/api/affairs")
async def get_affairs(
    status: str = Query("active", regex="^(active|closed|all)$"),
    limit: int = Query(20, ge=1, le=100)
):
    """Récupérer les affaires"""
    try:
        query = {} if status == "all" else {"status": status}
        affairs = list(
            collections['affairs']
            .find(query)
            .sort("bmg", -1)
            .limit(limit)
        )
        return {"affairs": [serialize_doc(a) for a in affairs]}
    except Exception as e:
        logger.error(f"Erreur récupération affaires: {e}")
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

        logger.info("✅ Scheduler routes ajoutées")
    except Exception as e:
        logger.warning(f"⚠️ Scheduler routes non disponibles: {e}")

# ========== ROUTES RADIO CARDS ==========
try:
    from backend.radio_cards_routes import router as radio_cards_router
    app.include_router(radio_cards_router, prefix="/api")
    logger.info("✅ Routes radio cards chargées (/api/radio/*)")
except Exception as e:
    logger.warning(f"⚠️ Routes radio cards non disponibles: {e}")

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