from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pymongo import MongoClient
import os
from datetime import datetime
import uuid
import json
import aiofiles
import asyncio
from typing import List, Dict, Any
import tempfile
import shutil
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Import des services (avec gestion d'erreur pour le cache)
from scraper_service import guadeloupe_scraper
from radio_service import radio_service  
from summary_service import summary_service
from scheduler_service import veille_scheduler, start_scheduler
from pdf_service import pdf_digest_service
from transcription_analysis_service import transcription_analyzer

# Import du cache avec fallback - Réactivé avec cache 24H

# Import du service réseaux sociaux MODERNE
try:
    from modern_social_service import modern_social_scraper
    # Alias pour compatibilité avec le code existant
    social_scraper = modern_social_scraper
    SOCIAL_MEDIA_ENABLED = True
    print("✅ Service réseaux sociaux MODERNE activé (Twitter API v2 + Nitter + RSS)")
except ImportError as e:
    print(f"⚠️ Service réseaux sociaux moderne non disponible: {e}")
    SOCIAL_MEDIA_ENABLED = False
    # Fallback vers ancien service
    try:
        from social_media_service import social_scraper
        # Alias pour cohérence
        modern_social_scraper = social_scraper
        SOCIAL_MEDIA_ENABLED = True
        print("✅ Fallback: Service réseaux sociaux classique activé")
    except ImportError:
        print("❌ Aucun service réseaux sociaux disponible")
        modern_social_scraper = None
        social_scraper = None
# Import du service d'analyse de sentiment GPT
try:
    from gpt_sentiment_service import gpt_sentiment_analyzer, analyze_articles_sentiment
    SENTIMENT_ENABLED = True
    print("✅ Service d'analyse de sentiment GPT activé")
except ImportError as e:
    print(f"⚠️ Service d'analyse de sentiment GPT non disponible: {e}")
    SENTIMENT_ENABLED = False
    # Fallback vers service local si nécessaire
    try:
        from sentiment_analysis_service import local_sentiment_analyzer, analyze_articles_sentiment
        SENTIMENT_ENABLED = True
        print("✅ Fallback: Service d'analyse de sentiment local activé")
    except ImportError:
        print("❌ Aucun service d'analyse de sentiment disponible")

# Import du service asynchrone de sentiment
try:
    from async_sentiment_service import async_sentiment_service, analyze_text_async, get_text_sentiment_cached, get_sentiment_analysis_status
    ASYNC_SENTIMENT_ENABLED = True
    print("✅ Service d'analyse de sentiment asynchrone activé")
except ImportError as e:
    print(f"⚠️ Service d'analyse de sentiment asynchrone non disponible: {e}")
    ASYNC_SENTIMENT_ENABLED = False

# Import du service de prédiction des réactions de la population
try:
    from population_reaction_service import population_reaction_predictor, predict_population_reaction
    POPULATION_REACTION_ENABLED = True
    print("✅ Service de prédiction des réactions de la population activé")
except ImportError as e:
    print(f"⚠️ Service de prédiction des réactions non disponible: {e}")
    POPULATION_REACTION_ENABLED = False

# Import du service d'alertes Telegram
try:
    from telegram_alerts_service import telegram_alerts
    TELEGRAM_ALERTS_ENABLED = True
    print("✅ Service d'alertes Telegram activé")
except ImportError as e:
    print(f"⚠️ Service d'alertes Telegram non disponible: {e}")
    TELEGRAM_ALERTS_ENABLED = False
    telegram_alerts = None

# Fallback pour local_sentiment_analyzer en cas d'absence du service principal
class SentimentAnalyzerFallback:
    def analyze_sentiment(self, text):
        return {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'low',
            'analysis_details': {
                'confidence': 0.0,
                'detected_patterns': []
            }
        }
    
    def get_sentiment_trends(self, articles_by_date):
        return {
            'success': False,
            'error': 'Service d\'analyse de sentiment non disponible',
            'trends': []
        }

local_sentiment_analyzer = SentimentAnalyzerFallback()

def analyze_articles_sentiment(articles):
    """Analyser le sentiment des articles avec GPT en mode asynchrone"""
    try:
        if not SENTIMENT_ENABLED:
            return {
                'success': False,
                'error': 'Service d\'analyse de sentiment non disponible',
                'analyzed_articles': []
            }
        
        # Utiliser le service GPT si disponible
        if 'gpt_sentiment_analyzer' in globals():
            return gpt_sentiment_analyzer.analyze_articles_batch(articles)
        else:
            return {
                'success': False,
                'error': 'Service GPT non disponible',
                'analyzed_articles': []
            }
    except Exception as e:
        logger.error(f"Erreur analyse articles sentiment: {e}")
        return {
            'success': False,
            'error': str(e),
            'analyzed_articles': []
        }
try:
    from cache_service import intelligent_cache, get_or_compute, cache_invalidate, start_cache_service
    CACHE_ENABLED = True
    print("✅ Cache service réactivé avec cache 24H")
except ImportError as e:
    print(f"⚠️ Cache service non disponible: {e}")
    CACHE_ENABLED = False
    
    # Fonctions fallback sans cache
    def get_or_compute(key, compute_func, params=None, force_refresh=False):
        return compute_func()
    
    def cache_invalidate(pattern=None):
        pass
    
    def start_cache_service():
        pass
    
    # Fallback intelligent_cache object
    class IntelligentCacheFallback:
        def get_cache_stats(self):
            return {"status": "disabled", "message": "Cache non disponible"}
        
        def set_cached_data(self, key, data):
            pass
        
        def get_cached_data(self, key):
            return None
        
        def warm_cache(self):
            pass

    intelligent_cache = IntelligentCacheFallback()

# Initialize FastAPI
app = FastAPI(title="Veille Média Guadeloupe API", version="2.1.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB Configuration - Compatible Atlas et local
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
print(f"🔗 Connecting to MongoDB: {MONGO_URL[:50]}...")

try:
    # Configuration robuste pour MongoDB Atlas et local
    if 'mongodb+srv://' in MONGO_URL or 'atlas' in MONGO_URL.lower():
        # Configuration optimisée pour MongoDB Atlas
        client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=5000,  # 5 secondes timeout
            connectTimeoutMS=5000,
            maxPoolSize=10,
            retryWrites=True,
            w='majority'
        )
        print("🌐 Configuration MongoDB Atlas détectée")
    else:
        # Configuration pour MongoDB local
        client = MongoClient(MONGO_URL)
        print("🏠 Configuration MongoDB locale détectée")
    
    # Test de connection
    client.admin.command('ping')
    
    db = client.veille_media
    
    # Collections
    articles_collection = db.articles_guadeloupe
    transcriptions_collection = db.radio_transcriptions
    digests_collection = db.daily_digests
    logs_collection = db.scheduler_logs
    
    print("✅ Connected to MongoDB successfully")
    
    # Créer des index pour optimiser les performances
    try:
        articles_collection.create_index([("date", -1), ("scraped_at", -1)])
        articles_collection.create_index([("source", 1)])
        articles_collection.create_index([("title", "text")])
        transcriptions_collection.create_index([("date", -1)])
        print("✅ MongoDB indexes created/verified")
    except Exception as idx_error:
        print(f"⚠️ Index creation warning (non-critical): {idx_error}")
        
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")
    # En production, on peut vouloir arrêter l'application si MongoDB n'est pas disponible
    if os.environ.get('ENVIRONMENT') == 'production':
        print("🚨 MongoDB connection required in production - exiting")
        exit(1)

# Démarrer les services de manière robuste
try:
    start_scheduler()
    print("✅ Scheduler démarré")
except Exception as e:
    print(f"⚠️ Erreur démarrage scheduler (non critique): {e}")

if CACHE_ENABLED:
    try:
        start_cache_service()
        print("✅ Cache service démarré")
    except Exception as e:
        print(f"⚠️ Erreur démarrage cache (non critique): {e}")

# Health check au démarrage
@app.on_event("startup")
async def startup_event():
    """Vérifications au démarrage de l'application"""
    try:
        # Test de connection MongoDB
        client.admin.command('ping')
        print("✅ MongoDB ping successful at startup")
        
        # Test basique des collections
        articles_count = articles_collection.count_documents({})
        print(f"✅ Articles collection accessible ({articles_count} documents)")
        
    except Exception as e:
        print(f"⚠️ Startup health check warning: {e}")

@app.on_event("shutdown") 
async def shutdown_event():
    """Nettoyage à l'arrêt de l'application"""
    try:
        if client:
            client.close()
        print("✅ MongoDB connection closed")
    except Exception as e:
        print(f"⚠️ Shutdown warning: {e}")

@app.get("/")
async def root():
    return {"message": "🏝️ API Veille Média Guadeloupe v2.1 - Cache intelligent activé !"}

# ==================== DASHBOARD ENDPOINTS ====================

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    """Récupérer les statistiques du dashboard - Articles du jour seulement"""
    try:
        if CACHE_ENABLED:
            def compute_dashboard_stats():
                return _compute_dashboard_stats_today_only()
            
            # Forcer le rafraîchissement du cache si nécessaire
            stats = get_or_compute('dashboard_stats', compute_dashboard_stats, force_refresh=False)
        else:
            stats = _compute_dashboard_stats_today_only()
        
        return {"success": True, "stats": stats}
    
    except Exception as e:
        print(f"Erreur dashboard stats: {e}")
        return {"success": False, "error": str(e), "stats": {}}

def _compute_dashboard_stats_today_only():
    """Calculer les statistiques du dashboard pour les articles du jour seulement"""
    try:
        # Date d'aujourd'hui
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Compter les articles d'aujourd'hui seulement 
        today_articles = articles_collection.count_documents({
            'date': today
        })
        
        # Récupérer quelques articles récents d'aujourd'hui
        recent_articles = list(articles_collection.find(
            {'date': today}
        ).sort('scraped_at', -1).limit(5))
        
        # Articles par source (aujourd'hui seulement)
        pipeline = [
            {'$match': {'date': today}},
            {'$group': {'_id': '$source', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}}
        ]
        articles_by_source = list(articles_collection.aggregate(pipeline))
        
        # Statistiques du cache
        cache_stats = {}
        if CACHE_ENABLED:
            try:
                cache_stats = {
                    'status': 'active',
                    'stats': intelligent_cache.get_cache_stats()
                }
            except:
                cache_stats = {'status': 'error'}
        else:
            cache_stats = {'status': 'disabled'}
        
        return {
            'today_articles': today_articles,
            'total_articles': today_articles,  # Montrer seulement ceux d'aujourd'hui
            'recent_articles': [
                {
                    'title': art.get('title', '')[:100],
                    'source': art.get('source', ''),
                    'url': art.get('url', ''),
                    'scraped_at': art.get('scraped_at', '')
                }
                for art in recent_articles
            ],
            'articles_by_source': [
                {'source': item['_id'], 'count': item['count']}
                for item in articles_by_source
            ],
            'cache_stats': cache_stats,
            'last_updated': datetime.now().isoformat(),
            'showing_data_for': f"Articles du {today} uniquement"
        }
        
    except Exception as e:
        logger.error(f"Erreur calcul stats dashboard: {e}")
        return {
            'today_articles': 0,
            'total_articles': 0,
            'recent_articles': [],
            'articles_by_source': [],
            'cache_stats': {'status': 'error'},
            'last_updated': datetime.now().isoformat(),
            'error': str(e)
        }
# ==================== ARTICLES ENDPOINTS ====================

@app.get("/api/articles")
async def get_articles():
    """Récupérer les articles du jour avec cache intelligent"""
    try:
        if CACHE_ENABLED:
            def compute_articles_today():
                return _compute_articles_today_only()
            
            # Récupérer les articles d'aujourd'hui depuis le cache ou calculer
            articles_data = get_or_compute('articles_today', compute_articles_today)
        else:
            articles_data = _compute_articles_today_only()
        
        # Vérifier le format des données
        if isinstance(articles_data, dict):
            return {"success": True, "articles": articles_data.get('articles', []), "count": articles_data.get('count', 0)}
        elif isinstance(articles_data, list):
            return {"success": True, "articles": articles_data, "count": len(articles_data)}
        else:
            return {"success": False, "error": "Format de données invalide", "articles": [], "count": 0}
    
    except Exception as e:
        print(f"Erreur articles: {e}")
        return {"success": False, "error": str(e), "articles": [], "count": 0}

def _compute_articles_today_only():
    """Récupérer seulement les articles d'aujourd'hui"""
    try:
        # Date d'aujourd'hui
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Récupérer les articles d'aujourd'hui triés par date de scraping
        articles = list(articles_collection.find({
            'date': today
        }).sort('scraped_at', -1).limit(100))
        
        # Nettoyer les données (convertir ObjectId si nécessaire)
        clean_articles = []
        for article in articles:
            if '_id' in article:
                del article['_id']  # Supprimer l'ObjectId MongoDB
            clean_articles.append(article)
        
        return {
            'articles': clean_articles,
            'count': len(clean_articles),
            'date_filter': today,
            'message': f'Articles du {today} uniquement'
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération articles aujourd'hui: {e}")
        return {'articles': [], 'count': 0, 'error': str(e)}

@app.get("/api/articles/filtered")
async def get_filtered_articles(
    date_start: str = None,
    date_end: str = None,
    source: str = None,
    search_text: str = None,
    sort_by: str = "date_desc",
    limit: int = 100,
    offset: int = 0
):
    """Récupérer les articles avec filtres avancés et tri"""
    try:
        # Validation des paramètres
        limit = min(max(1, limit), 500)  # Limiter entre 1 et 500
        offset = max(0, offset)  # Pas de valeurs négatives
        
        # Valider les dates si fournies
        if date_start:
            try:
                datetime.strptime(date_start, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(status_code=400, detail="Format date_start invalide (YYYY-MM-DD)")
        
        if date_end:
            try:
                datetime.strptime(date_end, '%Y-%m-%d')
            except ValueError:
                raise HTTPException(status_code=400, detail="Format date_end invalide (YYYY-MM-DD)")
        
        # Construire la requête MongoDB
        query = {}
        
        # Filtre par date
        if date_start or date_end:
            date_filter = {}
            if date_start:
                date_filter['$gte'] = date_start
            if date_end:
                date_filter['$lte'] = date_end
            query['date'] = date_filter
        
        # Filtre par source (avec protection injection)
        if source and source != "all":
            # Nettoyer la source pour éviter les injections
            clean_source = str(source).replace('$', '').replace('.', '')[:100]
            query['source'] = {'$regex': clean_source, '$options': 'i'}
        
        # Filtre par texte de recherche (avec protection injection)
        if search_text and len(search_text.strip()) >= 2:
            # Nettoyer le texte de recherche
            clean_text = str(search_text).replace('$', '').replace('.', '')[:200]
            search_regex = {'$regex': clean_text, '$options': 'i'}
            query['$or'] = [
                {'title': search_regex},
                {'source': search_regex}
            ]
        
        # Définir l'ordre de tri (avec validation)
        valid_sort_options = {
            "date_desc": [("scraped_at", -1)],
            "date_asc": [("scraped_at", 1)],
            "source_asc": [("source", 1), ("scraped_at", -1)],
            "source_desc": [("source", -1), ("scraped_at", -1)],
            "title_asc": [("title", 1)],
            "title_desc": [("title", -1)]
        }
        
        sort_query = valid_sort_options.get(sort_by, [("scraped_at", -1)])
        
        # Exécuter la requête avec pagination
        articles_cursor = articles_collection.find(
            query,
            {'_id': 0}  # Exclure _id pour éviter les erreurs de sérialisation
        ).sort(sort_query).skip(offset).limit(limit)
        
        articles = list(articles_cursor)
        
        # Compter le total pour la pagination (avec timeout)
        total_count = articles_collection.count_documents(query)
        
        # Calculer les métadonnées de pagination
        has_more = (offset + len(articles)) < total_count
        
        return {
            "success": True,
            "articles": articles,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "returned": len(articles)
            },
            "filters_applied": {
                "date_start": date_start,
                "date_end": date_end,
                "source": source,
                "search_text": search_text,
                "sort_by": sort_by
            }
        }
        
    except HTTPException:
        raise  # Re-lancer les erreurs HTTP
    except Exception as e:
        logger.error(f"Erreur filtrage articles: {e}")
        return {
            "success": False,
            "error": "Erreur interne du serveur",
            "articles": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False, "returned": 0}
        }

@app.get("/api/articles/sources")
async def get_available_sources():
    """Récupérer la liste des sources disponibles pour les filtres"""
    try:
        # Pipeline d'agrégation pour obtenir les sources avec leur nombre d'articles
        pipeline = [
            {'$group': {
                '_id': '$source',
                'count': {'$sum': 1},
                'latest_article': {'$max': '$scraped_at'}
            }},
            {'$sort': {'count': -1}}
        ]
        
        sources = list(articles_collection.aggregate(pipeline))
        
        # Formater les résultats
        formatted_sources = [
            {
                'name': source['_id'],
                'count': source['count'],
                'latest_article': source['latest_article']
            }
            for source in sources if source['_id']  # Exclure les sources nulles
        ]
        
        return {
            "success": True,
            "sources": formatted_sources,
            "total_sources": len(formatted_sources)
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération sources: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur récupération sources: {str(e)}")

@app.post("/api/articles/scrape-now")
async def scrape_articles_now():
    """Lancer le scraping d'articles immédiatement avec vidage du cache"""
    try:
        # 1. VIDER COMPLÈTEMENT LE CACHE avant scraping
        if CACHE_ENABLED:
            logger.info("🗑️ Vidage complet du cache avant scraping...")
            cache_invalidate()  # Vider tout le cache
            intelligent_cache.cleanup_expired_cache()
        
        # 2. Lancer le scraping en arrière-plan pour éviter les timeouts
        import threading
        
        def scrape_async():
            try:
                logger.info("🚀 Démarrage du scraping avec cache vidé...")
                result = guadeloupe_scraper.scrape_all_sites()
                
                # 3. VIDER À NOUVEAU LE CACHE après scraping pour forcer refresh
                if CACHE_ENABLED:
                    logger.info("🗑️ Vidage du cache après scraping pour forcer refresh...")
                    cache_invalidate('articles')  # Vider cache articles
                    cache_invalidate('dashboard')  # Vider cache dashboard
                    
                    # Sauvegarder le résultat dans le cache
                    intelligent_cache.set_cached_data('last_scraping_result', result)
                    
                    logger.info("✅ Cache vidé et résultat scraping sauvegardé")
                else:
                    # Stocker temporairement le résultat
                    setattr(app.state, 'last_scraping_result', result)
                    
            except Exception as e:
                error_result = {
                    'success': False,
                    'error': str(e),
                    'scraped_at': datetime.now().isoformat()
                }
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data('last_scraping_result', error_result)
                else:
                    setattr(app.state, 'last_scraping_result', error_result)
                logger.error(f"❌ Erreur lors du scraping: {e}")
        
        # Démarrer le scraping en arrière-plan
        scraping_thread = threading.Thread(target=scrape_async)
        scraping_thread.daemon = True
        scraping_thread.start()
        
        return {
            "success": True, 
            "message": "Scraping démarré avec vidage du cache. Articles du jour disponibles dans quelques minutes.",
            "estimated_completion": "2-3 minutes",
            "cache_cleared": True
        }
        
    except Exception as e:
        print(f"Erreur scraping: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/articles/scrape-status")
async def get_scrape_status():
    """Obtenir le statut du dernier scraping"""
    try:
        # Récupérer depuis le cache ou l'état de l'app
        if CACHE_ENABLED:
            last_result = intelligent_cache.get_cached_data('last_scraping_result')
        else:
            last_result = getattr(app.state, 'last_scraping_result', None)
        
        if last_result:
            return last_result
        else:
            return {
                "success": True, 
                "message": "Aucun scraping récent trouvé",
                "scraped_at": "Non disponible"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Route paramétrée à la fin pour éviter les conflits avec les routes spécifiques
@app.get("/api/articles/{date}")
async def get_articles_by_date(date: str):
    """Récupérer les articles d'une date spécifique avec cache"""
    try:
        def fetch_articles():
            return guadeloupe_scraper.get_articles_by_date(date)
        
        # Cache par date
        articles = get_or_compute('articles_by_date', fetch_articles, {'date': date})
        return {"success": True, "articles": articles, "count": len(articles), "date": date}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération articles: {str(e)}")

@app.post("/api/articles/clean-duplicates")
async def clean_duplicate_articles():
    """Nettoyer les doublons existants dans la base de données"""
    try:
        logger.info("🧹 Nettoyage des doublons demandé via API")
        
        # Utiliser le scraper pour nettoyer les doublons
        scraper = guadeloupe_scraper
        result = scraper.clean_duplicate_articles()
        
        return {
            "success": True,
            "result": result,
            "message": f"Nettoyage terminé: {result.get('removed_count', 0)} doublons supprimés"
        }
        
    except Exception as e:
        logger.error(f"Erreur nettoyage doublons API: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/admin/duplicate-stats")
async def get_duplicate_statistics():
    """Obtenir des statistiques sur les doublons potentiels"""
    try:
        collection = guadeloupe_scraper.articles_collection
        
        # Statistiques générales
        total_articles = collection.count_documents({})
        
        # Articles avec URLs dupliquées
        url_duplicates = list(collection.aggregate([
            {"$group": {"_id": "$url", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$count": "total"}
        ]))
        
        # Articles sans URL (potentiellement problématiques)
        no_url_count = collection.count_documents({"url": {"$exists": False}})
        
        # Articles récents (7 derniers jours)
        from datetime import datetime, timedelta
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        recent_count = collection.count_documents({"date": {"$gte": week_ago}})
        
        # Répartition par source
        sources_stats = list(collection.aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]))
        
        return {
            "success": True,
            "statistics": {
                "total_articles": total_articles,
                "url_duplicates": url_duplicates[0]['total'] if url_duplicates else 0,
                "articles_without_url": no_url_count,
                "recent_articles_count": recent_count,
                "articles_by_source": sources_stats
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur statistiques doublons: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ==================== TRANSCRIPTION ENDPOINTS ====================

@app.get("/api/transcriptions")
async def get_transcriptions():
    """Récupérer les transcriptions du jour avec cache"""
    try:
        # TEMPORAIRE: désactiver le cache pour éviter les timeouts
        transcriptions_data = radio_service.get_todays_transcriptions()
        return {"success": True, "transcriptions": transcriptions_data, "count": len(transcriptions_data)}
        
    except Exception as e:
        print(f"Erreur transcriptions: {e}")
        return {"success": False, "error": str(e), "transcriptions": [], "count": 0}

@app.post("/api/transcriptions/reset-status")
async def reset_transcription_status(admin_key: str = None):
    """Nettoyer les statuts de transcription bloqués - ADMIN UNIQUEMENT"""
    try:
        # Vérification admin
        if admin_key != "radio_capture_admin_2025":
            return {
                "success": False,
                "error": "Nettoyage réservé à l'administration",
                "note": "Clé admin requise"
            }
        
        logger.info("🧹 Nettoyage manuel des statuts demandé par admin")
        
        # Sauvegarder les anciens statuts pour information
        old_status = radio_service.get_transcription_status()
        
        # Nettoyer
        radio_service.reset_all_transcription_status()
        
        # Nouveau statut
        new_status = radio_service.get_transcription_status()
        
        return {
            "success": True,
            "message": "Statuts de transcription nettoyés",
            "timestamp": datetime.now().isoformat(),
            "admin_action": "reset_status",
            "before": {
                "any_in_progress": old_status["global_status"]["any_in_progress"],
                "active_sections": old_status["global_status"]["active_sections"]
            },
            "after": {
                "any_in_progress": new_status["global_status"]["any_in_progress"],
                "active_sections": new_status["global_status"]["active_sections"]
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur nettoyage statuts: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/transcriptions/status")
async def get_transcription_status():
    """Récupérer le statut détaillé des transcriptions par section"""
    try:
        status = radio_service.get_transcription_status()
        return {"success": True, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut transcriptions: {str(e)}")

@app.get("/api/transcriptions/sections")
async def get_transcriptions_by_sections():
    """Récupérer les transcriptions d'aujourd'hui organisées par sections"""
    try:
        sections = radio_service.get_todays_transcriptions_by_section()
        return {"success": True, "sections": sections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur transcriptions par sections: {str(e)}")

@app.get("/api/transcriptions/capture-status")
async def get_capture_status():
    """Récupérer le statut de la dernière capture"""
    try:
        last_result = intelligent_cache.get_cached_data('last_capture_result')
        if last_result:
            return {"success": True, "result": last_result}
        else:
            return {"success": False, "message": "Aucune capture récente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut capture: {str(e)}")

@app.get("/api/transcriptions/{date}")
async def get_transcriptions_by_date(date: str):
    """Récupérer les transcriptions d'une date spécifique avec cache"""
    try:
        def fetch_transcriptions():
            return radio_service.get_transcriptions_by_date(date)
        
        # Cache par date
        transcriptions = get_or_compute('transcriptions_by_date', fetch_transcriptions, {'date': date})
        return {"success": True, "transcriptions": transcriptions, "count": len(transcriptions), "date": date}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération transcriptions: {str(e)}")

@app.post("/api/transcriptions/capture-now")
async def capture_radio_now(section: str = None, admin_key: str = None):
    """Lancer la capture radio - RÉSERVÉ aux captures programmées et admin uniquement"""
    try:
        from datetime import datetime
        current_hour = datetime.now().hour
        
        # Vérification de sécurité : captures autorisées uniquement entre 7h-8h OU avec clé admin
        authorized_hours = [7]  # Uniquement 7h du matin
        admin_authorized = admin_key == "radio_capture_admin_2025"  # Clé temporaire pour admin
        
        if current_hour not in authorized_hours and not admin_authorized:
            return {
                "success": False,
                "error": "Captures autorisées uniquement à 7h du matin pour contrôler les coûts OpenAI",
                "current_hour": current_hour,
                "authorized_hours": authorized_hours,
                "note": "Utilisation de l'API OpenAI Whisper - coûts contrôlés"
            }
        
        logger.info(f"🔒 Capture autorisée - Heure: {current_hour}h, Admin: {admin_authorized}")
        
        # Invalider le cache des transcriptions
        cache_invalidate('transcriptions')
        
        # Lancer la capture en arrière-plan
        import threading
        
        def capture_async():
            try:
                if section:
                    # Capturer une section spécifique
                    if section == "rci":
                        result = radio_service.capture_and_transcribe_stream("rci_7h")
                    elif section == "guadeloupe":
                        result = radio_service.capture_and_transcribe_stream("guadeloupe_premiere_7h")
                    else:
                        result = {"success": False, "error": "Section inconnue. Utilisez 'rci' ou 'guadeloupe'"}
                else:
                    # Capturer toutes les sections
                    result = radio_service.capture_all_streams()
                
                intelligent_cache.set_cached_data('last_capture_result', result)
            except Exception as e:
                intelligent_cache.set_cached_data('last_capture_result', {
                    'success': False,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        capture_thread = threading.Thread(target=capture_async)
        capture_thread.daemon = True
        capture_thread.start()
        
        if section:
            section_name = "7H RCI" if section == "rci" else "7H Guadeloupe Première"
            return {
                "success": True, 
                "message": f"Capture de {section_name} démarrée en arrière-plan. Consultez les transcriptions dans quelques minutes.",
                "section": section_name,
                "estimated_completion": "3-5 minutes"
            }
        else:
            return {
                "success": True, 
                "message": "Capture radio démarrée en arrière-plan. Consultez les transcriptions dans quelques minutes.",
                "sections": ["7H RCI", "7H Guadeloupe Première"],
                "estimated_completion": "3-5 minutes"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lancement capture: {str(e)}")

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcrire un fichier audio uploadé avec Whisper"""
    try:
        logger.info(f"🎵 Début transcription fichier: {file.filename}")
        
        if not file.filename.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
            raise HTTPException(status_code=400, detail="Format audio non supporté")
        
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name
        
        logger.info(f"📁 Fichier temporaire créé: {temp_path}")
        
        try:
            # Utiliser le service de transcription
            logger.info("🎤 Début transcription avec Whisper...")
            transcription_data = radio_service.transcribe_audio_file(temp_path)
            logger.info(f"✅ Transcription terminée, résultat: {transcription_data is not None}")
            
            if transcription_data:
                # Analyse intelligente de la transcription
                logger.info("🧠 Analyse intelligente de la transcription uploadée...")
                analysis = transcription_analyzer.analyze_transcription(transcription_data['text'], file.filename)
                
                # Sauvegarder en base
                record = {
                    "id": str(uuid.uuid4()),
                    "filename": file.filename,
                    
                    # Transcription brute
                    "transcription_text": transcription_data['text'],
                    "language": transcription_data['language'],
                    "duration_seconds": transcription_data['duration'],
                    "segments": transcription_data['segments'],
                    
                    # Analyse intelligente
                    "ai_summary": analysis.get('summary', transcription_data['text']),
                    "ai_key_sentences": analysis.get('key_sentences', []),
                    "ai_main_topics": analysis.get('main_topics', []),
                    "ai_keywords": analysis.get('keywords', []),
                    "ai_relevance_score": analysis.get('relevance_score', 0.5),
                    "ai_analysis_metadata": analysis.get('analysis_metadata', {}),
                    
                    # Métadonnées
                    "uploaded_at": datetime.now().isoformat(),
                    "date": datetime.now().strftime('%Y-%m-%d'),
                    "source": "upload"
                }
                
                logger.info("💾 Sauvegarde en base de données...")
                # Insérer en base de données  
                record_for_db = record.copy()
                insert_result = transcriptions_collection.insert_one(record_for_db)
                logger.info(f"✅ Sauvegarde terminée, ID: {insert_result.inserted_id}")
                
                # Le record original n'a pas d'ObjectId, pas besoin de le supprimer
                
                # Invalider le cache des transcriptions
                cache_invalidate('transcriptions')
                
                logger.info("🎯 Réponse prête à renvoyer")
                return {"success": True, "transcription": record}
            else:
                logger.error("❌ Échec de la transcription (résultat vide)")
                raise HTTPException(status_code=500, detail="Échec de la transcription")
            
        finally:
            # Nettoyer le fichier temporaire
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.info(f"🧹 Fichier temporaire nettoyé: {temp_path}")
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"❌ Erreur transcription: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur transcription: {str(e)}")

# ==================== DIGEST ENDPOINTS ====================

@app.get("/api/digest/test-order")
async def test_digest_order():
    """Test de l'ordre des transcriptions dans le digest"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Récupérer directement sans cache
        articles = list(articles_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('scraped_at', -1).limit(10))  # Limiter pour accélérer
        
        transcriptions = list(transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        # Créer le digest sans cache
        digest_html = summary_service.create_daily_digest(articles, transcriptions)
        
        return {
            "success": True,
            "articles_count": len(articles),
            "transcriptions_count": len(transcriptions),
            "digest_preview": digest_html[:500] + "...",  # Premiers 500 caractères
            "full_digest": digest_html
        }
        
    except Exception as e:
        logger.error(f"Erreur test digest: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/digest")
async def get_today_digest():
    """Récupérer le digest du jour avec cache"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        digest_id = f"digest_{datetime.now().strftime('%Y%m%d')}"
        
        def fetch_digest():
            digest = digests_collection.find_one({"id": digest_id}, {"_id": 0})
            
            if not digest:
                # Créer le digest s'il n'existe pas
                # Récupérer les articles d'aujourd'hui directement de la DB
                today = datetime.now().strftime('%Y-%m-%d')
                articles = list(articles_collection.find(
                    {'date': today}, 
                    {'_id': 0}
                ).sort('scraped_at', -1))
                
                # Récupérer les transcriptions d'aujourd'hui 
                transcriptions = list(transcriptions_collection.find(
                    {'date': today}, 
                    {'_id': 0}
                ).sort('captured_at', -1))
                
                digest_html = summary_service.create_daily_digest(articles, transcriptions)
                
                digest = {
                    'id': digest_id,
                    'date': today,
                    'digest_html': digest_html,
                    'articles_count': len(articles),
                    'transcriptions_count': len(transcriptions),
                    'created_at': datetime.now().isoformat()
                }
                
                digests_collection.insert_one(digest)
                digest.pop('_id', None)
            
            return digest
        
        # Cache de 15 minutes pour le digest
        digest = get_or_compute('digest_today', fetch_digest)
        return {"success": True, "digest": digest}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération digest: {str(e)}")

@app.get("/api/digest/{date}")
async def get_digest_by_date(date: str):
    """Récupérer le digest d'une date spécifique avec cache"""
    try:
        digest_id = f"digest_{date.replace('-', '')}"
        
        def fetch_digest():
            digest = digests_collection.find_one({"id": digest_id}, {"_id": 0})
            return digest
        
        digest = get_or_compute('digest_by_date', fetch_digest, {'date': date})
        
        if not digest:
            return {"success": False, "message": f"Aucun digest trouvé pour le {date}"}
        
        return {"success": True, "digest": digest}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération digest: {str(e)}")

@app.get("/api/digest/{date}/html", response_class=HTMLResponse)
async def get_digest_html(date: str):
    """Récupérer le digest en format HTML pur avec cache"""
    try:
        digest_id = f"digest_{date.replace('-', '')}"
        
        def fetch_digest():
            return digests_collection.find_one({"id": digest_id}, {"_id": 0})
        
        digest = get_or_compute('digest_html', fetch_digest, {'date': date})
        
        if not digest:
            return HTMLResponse("<h2>Aucun digest trouvé pour cette date</h2>")
        
        # HTML complet avec CSS
        html_content = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Digest Guadeloupe - {date}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                h2 {{ color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px; }}
                h3 {{ color: #1e40af; margin-top: 30px; }}
                strong {{ color: #1f2937; }}
                a {{ color: #2563eb; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                hr {{ border: 1px solid #e5e7eb; margin: 20px 0; }}
                .cache-info {{ background: #f3f4f6; padding: 10px; border-radius: 5px; font-size: 0.8em; color: #6b7280; }}
            </style>
        </head>
        <body>
            {digest['digest_html']}
            <div class="cache-info">
                Généré le {digest.get('created_at', 'Inconnu')} • Cache intelligent activé
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(html_content)
        
    except Exception as e:
        return HTMLResponse(f"<h2>Erreur: {str(e)}</h2>")

@app.post("/api/digest/create-now")
async def create_digest_now():
    """Créer le digest du jour immédiatement"""
    try:
        # Invalider le cache du digest
        cache_invalidate('digest')
        
        # Récupérer les articles et transcriptions d'aujourd'hui directement
        today = datetime.now().strftime('%Y-%m-%d')
        articles = list(articles_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('scraped_at', -1))
        
        transcriptions = list(transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        digest_html = summary_service.create_daily_digest(articles, transcriptions)
        
        digest_id = f"digest_{datetime.now().strftime('%Y%m%d')}"
        digest_record = {
            'id': digest_id,
            'date': today,
            'digest_html': digest_html,
            'articles_count': len(articles),
            'transcriptions_count': len(transcriptions),
            'created_at': datetime.now().isoformat()
        }
        
        digests_collection.update_one(
            {'id': digest_id},
            {'$set': digest_record},
            upsert=True
        )
        
        return {"success": True, "message": "Digest créé avec analyse de sentiment", "digest": digest_record}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur création digest: {str(e)}")

@app.get("/api/digest/{date}/pdf")
async def get_digest_pdf(date: str):
    """Télécharger le digest en format PDF"""
    try:
        digest_id = f"digest_{date.replace('-', '')}"
        
        # Récupérer le digest depuis la base
        digest = digests_collection.find_one({"id": digest_id}, {"_id": 0})
        
        if not digest:
            # Créer le digest s'il n'existe pas
            today = date
            articles = list(articles_collection.find(
                {'date': today}, 
                {'_id': 0}
            ).sort('scraped_at', -1))
            
            transcriptions = list(transcriptions_collection.find(
                {'date': today}, 
                {'_id': 0}
            ).sort('captured_at', -1))
            
            digest_html = summary_service.create_daily_digest(articles, transcriptions)
            
            digest = {
                'id': digest_id,
                'date': today,
                'digest_html': digest_html,
                'articles_count': len(articles),
                'transcriptions_count': len(transcriptions),
                'created_at': datetime.now().isoformat()
            }
            
            # Sauvegarder le digest
            digests_collection.insert_one(digest.copy())
        
        # Générer le PDF
        pdf_path = pdf_digest_service.create_pdf_digest(digest)
        
        # Nom du fichier pour le téléchargement
        filename = f"digest_guadeloupe_{date}.pdf"
        
        # Retourner le fichier PDF
        return FileResponse(
            path=pdf_path,
            media_type='application/pdf',
            filename=filename,
            background=True  # Nettoie automatiquement le fichier temporaire
        )
        
    except Exception as e:
        logger.error(f"Erreur génération PDF digest: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur génération PDF: {str(e)}")

@app.get("/api/digest/today/pdf")
async def get_today_digest_pdf():
    """Télécharger le digest d'aujourd'hui en format PDF"""
    today = datetime.now().strftime('%Y-%m-%d')
    return await get_digest_pdf(today)

# ==================== SCHEDULER ENDPOINTS ====================

@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Obtenir le statut du scheduler avec cache"""
    try:
        def fetch_scheduler_status():
            jobs = veille_scheduler.get_job_status()
            logs = veille_scheduler.get_recent_logs(10)
            
            return {
                "jobs": jobs,
                "recent_logs": logs,
                "scheduler_running": len(jobs) > 0
            }
        
        # Cache de 2 minutes pour le statut
        scheduler_data = get_or_compute('scheduler_status', fetch_scheduler_status)
        
        return {"success": True, **scheduler_data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut scheduler: {str(e)}")

@app.post("/api/scheduler/run-job/{job_id}")
async def run_job_manually(job_id: str):
    """Exécuter un job manuellement"""
    try:
        result = veille_scheduler.run_job_manually(job_id)
        
        # Invalider les caches concernés
        if job_id == 'scrape_articles':
            cache_invalidate('articles')
        elif job_id == 'capture_radio':
            cache_invalidate('transcriptions')
        elif job_id == 'create_digest':
            cache_invalidate('digest')
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur exécution job: {str(e)}")

@app.get("/api/scheduler/logs")
async def get_scheduler_logs():
    """Récupérer les logs du scheduler"""
    try:
        logs = veille_scheduler.get_recent_logs(50)
        return {"success": True, "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération logs: {str(e)}")

# ==================== CACHE MANAGEMENT ENDPOINTS ====================

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Obtenir les statistiques du cache"""
    try:
        stats = intelligent_cache.get_cache_stats()
        return {"success": True, "cache_stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur stats cache: {str(e)}")

@app.post("/api/cache/invalidate")
async def invalidate_cache(pattern: str = None):
    """Invalider le cache selon un pattern"""
    try:
        cache_invalidate(pattern)
        return {"success": True, "message": f"Cache invalidé{' pour pattern: ' + pattern if pattern else ' entièrement'}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur invalidation cache: {str(e)}")

@app.post("/api/cache/warm")
async def warm_cache():
    """Préchauffer le cache"""
    try:
        intelligent_cache.warm_cache()
        return {"success": True, "message": "Cache préchauffé avec succès"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur préchauffage cache: {str(e)}")

# ==================== ARTICLES FILTERING & ANALYTICS ENDPOINTS ====================

@app.get("/api/articles/sources")
async def get_available_sources():
    """Récupérer la liste des sources disponibles pour les filtres"""
    try:
        # Pipeline d'agrégation pour obtenir les sources avec leur nombre d'articles
        pipeline = [
            {'$group': {
                '_id': '$source',
                'count': {'$sum': 1},
                'latest_article': {'$max': '$scraped_at'}
            }},
            {'$sort': {'count': -1}}
        ]
        
        sources = list(articles_collection.aggregate(pipeline))
        
        # Formater les résultats
        formatted_sources = [
            {
                'name': source['_id'],
                'count': source['count'],
                'latest_article': source['latest_article']
            }
            for source in sources if source['_id']  # Exclure les sources nulles
        ]
        
        return {
            "success": True,
            "sources": formatted_sources,
            "total_sources": len(formatted_sources)
        }
        
    except Exception as e:
        logger.error(f"Erreur récupération sources: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur récupération sources: {str(e)}")

@app.get("/api/analytics/articles-by-source")
async def get_articles_by_source_analytics(days: int = 7):
    """Analytics: répartition des articles par source sur les X derniers jours"""
    try:
        from datetime import datetime, timedelta
        
        # Calculer la date de début
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        date_filter = start_date.strftime('%Y-%m-%d')
        
        # Pipeline d'agrégation
        pipeline = [
            {
                '$match': {
                    'date': {'$gte': date_filter}
                }
            },
            {
                '$group': {
                    '_id': '$source',
                    'count': {'$sum': 1},
                    'latest_date': {'$max': '$date'}
                }
            },
            {
                '$sort': {'count': -1}
            }
        ]
        
        results = list(articles_collection.aggregate(pipeline))
        
        # Formater pour les graphiques
        labels = [item['_id'] for item in results]
        data = [item['count'] for item in results]
        colors = [
            '#3b82f6', '#ef4444', '#10b981', '#f59e0b', 
            '#8b5cf6', '#06b6d4', '#f97316', '#84cc16'
        ]
        
        return {
            "success": True,
            "chart_data": {
                "labels": labels,
                "datasets": [{
                    "label": f"Articles ({days} derniers jours)",
                    "data": data,
                    "backgroundColor": colors[:len(data)],
                    "borderColor": colors[:len(data)],
                    "borderWidth": 1
                }]
            },
            "raw_data": results,
            "period": f"{days} derniers jours",
            "total_articles": sum(data)
        }
        
    except Exception as e:
        logger.error(f"Erreur analytics par source: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur analytics par source: {str(e)}")

@app.get("/api/analytics/articles-timeline")
async def get_articles_timeline_analytics(days: int = 14):
    """Analytics: évolution temporelle des articles"""
    try:
        from datetime import datetime, timedelta
        
        # Calculer les dates
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Pipeline d'agrégation par jour
        pipeline = [
            {
                '$match': {
                    'date': {'$gte': start_date.strftime('%Y-%m-%d')}
                }
            },
            {
                '$group': {
                    '_id': '$date',
                    'count': {'$sum': 1}
                }
            },
            {
                '$sort': {'_id': 1}
            }
        ]
        
        results = list(articles_collection.aggregate(pipeline))
        
        # Créer une série complète de dates (combler les trous)
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        # Mapper les résultats
        data_map = {item['_id']: item['count'] for item in results}
        timeline_data = [data_map.get(date, 0) for date in date_range]
        
        return {
            "success": True,
            "chart_data": {
                "labels": date_range,
                "datasets": [{
                    "label": "Articles par jour",
                    "data": timeline_data,
                    "borderColor": "#3b82f6",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "tension": 0.4,
                    "fill": True
                }]
            },
            "raw_data": results,
            "period": f"{days} derniers jours",
            "total_articles": sum(timeline_data)
        }
        
    except Exception as e:
        logger.error(f"Erreur analytics timeline: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur analytics timeline: {str(e)}")

@app.get("/api/analytics/sentiment-by-source")
async def get_sentiment_by_source_analytics():
    """Analytics: analyse de sentiment par source"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        # Récupérer les articles récents avec analyse de sentiment
        today = datetime.now().strftime('%Y-%m-%d')
        articles = list(articles_collection.find(
            {'date': today},
            {'_id': 0, 'source': 1, 'title': 1}
        ).limit(100))
        
        if not articles:
            return {
                "success": True,
                "chart_data": {
                    "labels": [],
                    "datasets": []
                },
                "message": "Aucun article à analyser aujourd'hui"
            }
        
        # Analyser le sentiment de chaque article
        from sentiment_analysis_service import local_sentiment_analyzer
        
        sentiment_by_source = {}
        
        for article in articles:
            source = article['source']
            if source not in sentiment_by_source:
                sentiment_by_source[source] = {'positive': 0, 'negative': 0, 'neutral': 0}
            
            # Analyser le sentiment du titre
            sentiment = local_sentiment_analyzer.analyze_sentiment(article['title'])
            polarity = sentiment['polarity']
            
            if polarity == 'positive':
                sentiment_by_source[source]['positive'] += 1
            elif polarity == 'negative':
                sentiment_by_source[source]['negative'] += 1
            else:
                sentiment_by_source[source]['neutral'] += 1
        
        # Formater pour les graphiques (barres empilées)
        sources = list(sentiment_by_source.keys())
        positive_data = [sentiment_by_source[source]['positive'] for source in sources]
        negative_data = [sentiment_by_source[source]['negative'] for source in sources]
        neutral_data = [sentiment_by_source[source]['neutral'] for source in sources]
        
        return {
            "success": True,
            "chart_data": {
                "labels": sources,
                "datasets": [
                    {
                        "label": "Positif",
                        "data": positive_data,
                        "backgroundColor": "#10b981",
                        "borderColor": "#059669",
                        "borderWidth": 1
                    },
                    {
                        "label": "Neutre",
                        "data": neutral_data,
                        "backgroundColor": "#6b7280",
                        "borderColor": "#4b5563",
                        "borderWidth": 1
                    },
                    {
                        "label": "Négatif",
                        "data": negative_data,
                        "backgroundColor": "#ef4444",
                        "borderColor": "#dc2626",
                        "borderWidth": 1
                    }
                ]
            },
            "raw_data": sentiment_by_source,
            "analyzed_articles": len(articles)
        }
        
    except Exception as e:
        logger.error(f"Erreur analytics sentiment: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur analytics sentiment: {str(e)}")

@app.get("/api/analytics/dashboard-metrics")
async def get_dashboard_metrics():
    """Métriques complètes pour le dashboard"""
    try:
        from datetime import datetime, timedelta
        
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Articles aujourd'hui
        articles_today = articles_collection.count_documents({'date': today})
        articles_yesterday = articles_collection.count_documents({'date': yesterday})
        articles_week = articles_collection.count_documents({'date': {'$gte': week_ago}})
        
        # Calcul des évolutions
        articles_evolution = articles_today - articles_yesterday if articles_yesterday > 0 else 0
        articles_evolution_pct = round((articles_evolution / articles_yesterday * 100), 1) if articles_yesterday > 0 else 0
        
        # Transcriptions (si disponible)
        transcriptions_today = 0
        try:
            transcriptions_today = transcriptions_collection.count_documents({'date': today})
        except:
            pass
        
        # Sources actives
        sources_pipeline = [
            {'$match': {'date': today}},
            {'$group': {'_id': '$source'}},
            {'$count': 'total'}
        ]
        sources_result = list(articles_collection.aggregate(sources_pipeline))
        active_sources = sources_result[0]['total'] if sources_result else 0
        
        # Cache stats
        cache_stats = {"efficiency": 0, "hits": 0, "total": 0}
        try:
            from cache_service import intelligent_cache
            cache_stats = intelligent_cache.get_cache_stats()
        except:
            pass
        
        return {
            "success": True,
            "metrics": {
                "articles_today": {
                    "value": articles_today,
                    "evolution": articles_evolution,
                    "evolution_pct": articles_evolution_pct,
                    "label": "Articles aujourd'hui"
                },
                "articles_week": {
                    "value": articles_week,
                    "label": "Articles (7 jours)"
                },
                "transcriptions_today": {
                    "value": transcriptions_today,
                    "label": "Transcriptions radio"
                },
                "active_sources": {
                    "value": active_sources,
                    "label": "Sources actives"
                },
                "cache_efficiency": {
                    "value": round(cache_stats.get("efficiency", 0)),
                    "label": "Efficacité cache (%)"
                }
            },
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erreur métriques dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur métriques dashboard: {str(e)}")

# ==================== SEARCH ENDPOINTS ====================

@app.get("/api/search")
async def search_content(q: str, source: str = "all", limit: int = 50, social_only: bool = False):
    """Rechercher dans les articles et posts des réseaux sociaux"""
    try:
        if not q or len(q.strip()) < 2:
            return {"success": False, "error": "Requête de recherche trop courte (minimum 2 caractères)"}
        
        search_query = q.strip().lower()
        logger.info(f"🔍 Recherche {'sociale uniquement' if social_only else 'globale'}: {q}")
        
        results = {
            'query': q,
            'articles': [],
            'social_posts': [],
            'total_results': 0,
            'searched_in': []
        }
        
        # Rechercher dans les articles si demandé et pas social_only
        if source in ['all', 'articles'] and not social_only:
            try:
                # Recherche MongoDB avec regex insensible à la casse
                article_query = {
                    '$or': [
                        {'title': {'$regex': search_query, '$options': 'i'}},
                        {'source': {'$regex': search_query, '$options': 'i'}}
                    ]
                }
                
                articles = list(articles_collection.find(
                    article_query,
                    {'_id': 0}
                ).sort('scraped_at', -1).limit(limit))
                
                results['articles'] = articles
                results['searched_in'].append('articles')
                
            except Exception as e:
                logger.warning(f"Erreur recherche articles: {e}")
        
        # Rechercher dans les posts des réseaux sociaux si demandé
        if source in ['all', 'social']:
            try:
                if SOCIAL_MEDIA_ENABLED:
                    # Recherche dans les posts sociaux
                    social_query = {
                        '$or': [
                            {'content': {'$regex': search_query, '$options': 'i'}},
                            {'author': {'$regex': search_query, '$options': 'i'}},
                            {'keyword_searched': {'$regex': search_query, '$options': 'i'}},
                            {'search_keyword': {'$regex': search_query, '$options': 'i'}}
                        ]
                    }
                    
                    social_posts = list(social_scraper.social_collection.find(
                        social_query,
                        {'_id': 0}
                    ).sort('scraped_at', -1).limit(limit))
                    
                    results['social_posts'] = social_posts
                    results['searched_in'].append('social_posts')
                    
            except Exception as e:
                logger.warning(f"Erreur recherche réseaux sociaux: {e}")
        
        # Calculer le total
        results['total_results'] = len(results['articles']) + len(results['social_posts'])
        
        # Ajouter des suggestions si pas de résultats
        if results['total_results'] == 0:
            suggestions = [
                "Guy Losbar", "Conseil Départemental", "CD971", "Guadeloupe",
                "budget", "education", "route", "social", "politique"
            ]
            results['suggestions'] = [s for s in suggestions if search_query not in s.lower()][:5]
        
        return {"success": True, **results}
        
    except Exception as e:
        logger.error(f"Erreur recherche: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/search/suggestions")
async def get_search_suggestions(q: str = ""):
    """Obtenir des suggestions de recherche basées sur les données existantes"""
    try:
        suggestions = []
        
        if len(q) >= 2:
            search_query = q.strip().lower()
            
            # Suggestions basées sur les sources d'articles
            try:
                sources_pipeline = [
                    {'$group': {'_id': '$source', 'count': {'$sum': 1}}},
                    {'$match': {'_id': {'$regex': search_query, '$options': 'i'}}},
                    {'$sort': {'count': -1}},
                    {'$limit': 3}
                ]
                sources = list(articles_collection.aggregate(sources_pipeline))
                suggestions.extend([s['_id'] for s in sources])
                
            except Exception as e:
                logger.warning(f"Erreur suggestions sources: {e}")
            
            # Suggestions basées sur les mots-clés des réseaux sociaux
            try:
                if SOCIAL_MEDIA_ENABLED:
                    keywords_pipeline = [
                        {'$group': {'_id': '$keyword_searched', 'count': {'$sum': 1}}},
                        {'$match': {'_id': {'$regex': search_query, '$options': 'i'}}},
                        {'$sort': {'count': -1}},
                        {'$limit': 3}
                    ]
                    keywords = list(social_scraper.social_collection.aggregate(keywords_pipeline))
                    suggestions.extend([k['_id'] for k in keywords])
                    
            except Exception as e:
                logger.warning(f"Erreur suggestions keywords: {e}")
        
        # Suggestions par défaut si pas de query ou pas de résultats
        if not suggestions:
            default_suggestions = [
                "Guy Losbar", "Conseil Départemental Guadeloupe", "CD971",
                "Budget départemental", "Education Guadeloupe", "Routes Guadeloupe",
                "Aide sociale", "Collèges", "Assemblée départementale"
            ]
            suggestions = default_suggestions[:5]
        
        return {"success": True, "suggestions": list(set(suggestions))[:8]}
        
    except Exception as e:
        logger.error(f"Erreur suggestions recherche: {e}")
        return {"success": False, "error": str(e), "suggestions": []}

# ==================== COMMENTS ENDPOINTS ====================

@app.get("/api/comments")
async def get_comments(article_id: str = None, limit: int = 100):
    """Récupérer les commentaires (posts des réseaux sociaux liés aux articles)"""
    try:
        if SOCIAL_MEDIA_ENABLED:
            query = {}
            if article_id:
                # Si un article spécifique est demandé, chercher les posts liés
                query = {'related_article_id': article_id}
            
            # Récupérer les posts des réseaux sociaux comme "commentaires"
            comments = list(social_scraper.social_collection.find(
                query,
                {'_id': 0}
            ).sort('scraped_at', -1).limit(limit))
            
            # Ajouter l'analyse de sentiment si pas déjà présente
            if SENTIMENT_ENABLED:
                for comment in comments:
                    if 'sentiment_summary' not in comment:
                        sentiment = local_sentiment_analyzer.analyze_sentiment(comment.get('content', ''))
                        comment['sentiment_summary'] = {
                            'polarity': sentiment['polarity'],
                            'score': sentiment['score'],
                            'intensity': sentiment['intensity']
                        }
            
            return {"success": True, "comments": comments, "count": len(comments)}
        else:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
            
    except Exception as e:
        logger.error(f"Erreur récupération commentaires: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/comments/analyze")
async def analyze_comments_sentiment():
    """Analyser le sentiment des commentaires par entité (Guy Losbar, CD971, etc.)"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        # Récupérer tous les posts récents
        posts = social_scraper.get_recent_posts(days=7)
        
        if not posts:
            return {"success": True, "analysis": {"total_comments": 0, "by_entity": {}, "overall": {}}}
        
        # Analyser par entité cible
        entities_analysis = {
            'Guy Losbar': {'posts': [], 'sentiments': []},
            'Conseil Départemental': {'posts': [], 'sentiments': []},
            'CD971': {'posts': [], 'sentiments': []},
            'Budget': {'posts': [], 'sentiments': []},
            'Education': {'posts': [], 'sentiments': []}
        }
        
        # Classifier les posts par entité mentionnée
        for post in posts:
            content = post.get('content', '').lower()
            sentiment = local_sentiment_analyzer.analyze_sentiment(post.get('content', ''))
            
            post_with_sentiment = {
                **post,
                'sentiment': sentiment
            }
            
            # Détecter les entités mentionnées
            if any(keyword in content for keyword in ['guy losbar', 'losbar']):
                entities_analysis['Guy Losbar']['posts'].append(post_with_sentiment)
                entities_analysis['Guy Losbar']['sentiments'].append(sentiment['score'])
            
            if any(keyword in content for keyword in ['conseil départemental', 'cd971', 'département']):
                entities_analysis['Conseil Départemental']['posts'].append(post_with_sentiment)
                entities_analysis['Conseil Départemental']['sentiments'].append(sentiment['score'])
            
            if 'budget' in content:
                entities_analysis['Budget']['posts'].append(post_with_sentiment)
                entities_analysis['Budget']['sentiments'].append(sentiment['score'])
            
            if any(keyword in content for keyword in ['école', 'collège', 'education', 'élève']):
                entities_analysis['Education']['posts'].append(post_with_sentiment)
                entities_analysis['Education']['sentiments'].append(sentiment['score'])
        
        # Calculer les statistiques par entité
        analysis_result = {
            'total_comments': len(posts),
            'by_entity': {},
            'overall': {
                'average_sentiment': sum([s['score'] for s in [local_sentiment_analyzer.analyze_sentiment(p.get('content', '')) for p in posts]]) / len(posts) if posts else 0,
                'total_analyzed': len(posts)
            },
            'analysis_date': datetime.now().isoformat()
        }
        
        for entity, data in entities_analysis.items():
            if data['posts']:
                avg_sentiment = sum(data['sentiments']) / len(data['sentiments'])
                sentiment_counts = {
                    'positive': len([s for s in data['sentiments'] if s > 0.1]),
                    'negative': len([s for s in data['sentiments'] if s < -0.1]),
                    'neutral': len([s for s in data['sentiments'] if -0.1 <= s <= 0.1])
                }
                
                analysis_result['by_entity'][entity] = {
                    'total_mentions': len(data['posts']),
                    'average_sentiment': round(avg_sentiment, 3),
                    'sentiment_distribution': sentiment_counts,
                    'recent_posts': data['posts'][:3]  # 3 posts les plus récents
                }
        
        return {"success": True, "analysis": analysis_result}
        
    except Exception as e:
        logger.error(f"Erreur analyse commentaires: {e}")
        return {"success": False, "error": str(e)}

# ==================== SOCIAL MEDIA ENDPOINTS ====================

@app.get("/api/social/stats")
async def get_social_media_stats():
    """Obtenir les statistiques des réseaux sociaux"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        stats = modern_social_scraper.get_posts_stats()
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"Erreur stats réseaux sociaux: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/social/posts")
async def get_social_media_posts(platform: str = None, days: int = 1):
    """Récupérer les posts des réseaux sociaux récents"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        posts = social_scraper.get_recent_posts(days=days, platform=platform)
        return {"success": True, "posts": posts, "count": len(posts)}
        
    except Exception as e:
        logger.error(f"Erreur récupération posts: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/social/scrape-now")
async def scrape_social_media_now():
    """Lancer le scraping des réseaux sociaux immédiatement"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        # Lancer le scraping en arrière-plan
        import threading
        
        def scrape_async():
            try:
                logger.info("🚀 Début scraping réseaux sociaux MODERNE...")
                
                # Utiliser le nouveau service moderne avec Twitter API v2
                results = modern_social_scraper.scrape_all_modern_sources()
                
                # Sauvegarder tous les posts
                all_posts = results['twitter_api'] + results['twitter_nitter'] + results['rss_official']
                saved_count = modern_social_scraper.save_posts_to_db(all_posts)
                
                # Résultat enrichi avec info sur les méthodes
                cache_result = {
                    'success': True,
                    'total_posts': results['total_posts'],
                    'saved_posts': saved_count,
                    'by_method': {
                        'twitter_api_v2': len(results['twitter_api']),
                        'twitter_nitter': len(results['twitter_nitter']),
                        'rss_official': len(results['rss_official'])
                    },
                    'methods_used': results['methods_used'],
                    'success_rate': results.get('success_rate', {}),
                    'keywords': results['keywords_searched'],
                    'scraped_at': results['scraped_at'],
                    'demo_mode': results.get('demo_mode', False),
                    'note': results.get('note', 'Service moderne utilisé'),
                    'service_version': 'modern_2025'
                }
                
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data('last_social_scraping_result', cache_result)
                
                logger.info(f"✅ Scraping terminé: {saved_count} posts sauvegardés")
                
            except Exception as e:
                error_result = {
                    'success': False,
                    'error': str(e),
                    'scraped_at': datetime.now().isoformat()
                }
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data('last_social_scraping_result', error_result)
                logger.error(f"❌ Erreur scraping réseaux sociaux: {e}")
        
        # Démarrer en arrière-plan
        scraping_thread = threading.Thread(target=scrape_async)
        scraping_thread.daemon = True
        scraping_thread.start()
        
        return {
            "success": True,
            "message": "Scraping moderne des réseaux sociaux démarré en arrière-plan",
            "estimated_completion": "2-3 minutes",
            "methods": "Twitter API v2 + Nitter (fallback) + RSS feeds officiels",
            "note": "Service moderne 2025 - Plus fiable que snscrape/Playwright"
        }
        
    except Exception as e:
        logger.error(f"Erreur lancement scraping social: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/social/scrape-status")
async def get_social_scrape_status():
    """Récupérer le statut du dernier scraping réseaux sociaux"""
    try:
        if CACHE_ENABLED:
            last_result = intelligent_cache.get_cached_data('last_social_scraping_result')
            if last_result:
                return {"success": True, "result": last_result}
        
        return {"success": False, "message": "Aucun scraping récent"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/social/clean-demo-data")
async def clean_demo_data():
    """Nettoyer les anciennes données de démonstration de la base"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        cleaned_count = social_scraper.clean_demo_data_from_db()
        
        # Invalider le cache social
        if CACHE_ENABLED:
            cache_invalidate('social')
            cache_invalidate('comments')
        
        return {
            "success": True,
            "message": f"{cleaned_count} posts de démonstration supprimés",
            "cleaned_count": cleaned_count
        }
        
    except Exception as e:
        logger.error(f"Erreur nettoyage données démo: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/social/scrape-keyword")
async def scrape_social_keyword(request: Request):
    """Scraper les réseaux sociaux pour un mot-clé spécifique"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        body = await request.json()
        keyword = body.get('keyword', '').strip()
        
        if not keyword or len(keyword) < 2:
            return {"success": False, "error": "Mot-clé trop court (minimum 2 caractères)"}
        
        logger.info(f"🔍 Scraping social pour mot-clé: {keyword}")
        
        # Scraper uniquement pour ce mot-clé
        def scrape_keyword_async():
            try:
                results = social_scraper.scrape_all_keywords([keyword])
                
                # Sauvegarder les posts trouvés
                all_posts = results['twitter'] + results['facebook'] + results['instagram']
                saved_count = social_scraper.save_posts_to_db(all_posts)
                
                # Marquer les posts avec le mot-clé recherché
                for post in all_posts:
                    post['search_keyword'] = keyword
                
                cache_result = {
                    'success': True,
                    'keyword': keyword,
                    'total_posts': results['total_posts'],
                    'saved_posts': saved_count,
                    'by_platform': {
                        'twitter': len(results['twitter']),
                        'facebook': len(results['facebook']),
                        'instagram': len(results['instagram'])
                    },
                    'scraped_at': results['scraped_at']
                }
                
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data(f'social_keyword_{keyword}', cache_result)
                
                logger.info(f"✅ Scraping mot-clé '{keyword}' terminé: {saved_count} posts sauvegardés")
                
            except Exception as e:
                logger.error(f"❌ Erreur scraping mot-clé '{keyword}': {e}")
        
        # Lancer en arrière-plan
        import threading
        thread = threading.Thread(target=scrape_keyword_async)
        thread.start()
        
        return {
            "success": True,
            "message": f"Scraping démarré pour le mot-clé: {keyword}",
            "keyword": keyword,
            "estimated_completion": "30-60 secondes"
        }
        
    except Exception as e:
        logger.error(f"Erreur endpoint scrape-keyword: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/social/install-dependencies")
async def install_social_dependencies():
    """Installer les dépendances pour le scraping social (snscrape, playwright)"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        # Lancer l'installation en arrière-plan
        import threading
        
        def install_deps():
            try:
                social_scraper.install_dependencies()
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data('social_deps_installed', {
                        'success': True,
                        'installed_at': datetime.now().isoformat(),
                        'dependencies': ['snscrape', 'playwright']
                    })
            except Exception as e:
                if CACHE_ENABLED:
                    intelligent_cache.set_cached_data('social_deps_installed', {
                        'success': False,
                        'error': str(e),
                        'installed_at': datetime.now().isoformat()
                    })
        
        install_thread = threading.Thread(target=install_deps)
        install_thread.daemon = True
        install_thread.start()
        
        return {
            "success": True,
            "message": "Installation des dépendances en cours (snscrape, playwright)",
            "estimated_completion": "2-3 minutes"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/social/sentiment")
async def analyze_social_sentiment():
    """Analyser le sentiment des posts des réseaux sociaux"""
    try:
        if not SOCIAL_MEDIA_ENABLED:
            return {"success": False, "error": "Service réseaux sociaux non disponible"}
        
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        if CACHE_ENABLED:
            def compute_social_sentiment():
                return _compute_social_sentiment_analysis()
            
            sentiment_data = get_or_compute('social_sentiment_today', compute_social_sentiment)
        else:
            sentiment_data = _compute_social_sentiment_analysis()
        
        return {"success": True, **sentiment_data}
        
    except Exception as e:
        logger.error(f"Erreur analyse sentiment social: {e}")
        return {"success": False, "error": str(e)}

def _compute_social_sentiment_analysis():
    """Analyser le sentiment des posts sociaux d'aujourd'hui"""
    try:
        # Récupérer les posts d'aujourd'hui
        posts = social_scraper.get_recent_posts(days=1)
        
        if not posts:
            return {
                'posts': [],
                'summary': {
                    'total_posts': 0,
                    'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
                    'average_sentiment_score': 0.0,
                    'most_common_patterns': {},
                    'by_platform': {},
                    'analysis_timestamp': datetime.now().isoformat()
                }
            }
        
        # Analyser le sentiment de tous les posts
        analyzed_posts = []
        platform_sentiments = {'twitter': [], 'facebook': [], 'instagram': []}
        
        for post in posts:
            # Analyser le sentiment du contenu
            sentiment_result = local_sentiment_analyzer.analyze_sentiment(post.get('content', ''))
            
            # Ajouter l'analyse au post
            analyzed_post = {
                **post,
                'sentiment': sentiment_result,
                'sentiment_summary': {
                    'polarity': sentiment_result['polarity'],
                    'score': sentiment_result['score'],
                    'intensity': sentiment_result['intensity'],
                    'confidence': sentiment_result['analysis_details']['confidence']
                }
            }
            analyzed_posts.append(analyzed_post)
            
            # Grouper par plateforme pour les stats
            platform = post.get('platform', 'unknown')
            if platform in platform_sentiments:
                platform_sentiments[platform].append(sentiment_result['score'])
        
        # Calculer les statistiques globales
        all_scores = [post['sentiment']['score'] for post in analyzed_posts]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        # Distribution par sentiment
        sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        for post in analyzed_posts:
            polarity = post['sentiment']['polarity']
            sentiment_counts[polarity] += 1
        
        # Patterns les plus communs
        all_patterns = []
        for post in analyzed_posts:
            all_patterns.extend(post['sentiment']['analysis_details']['detected_patterns'])
        
        from collections import Counter
        pattern_counts = Counter(all_patterns)
        
        # Stats par plateforme
        platform_stats = {}
        for platform, scores in platform_sentiments.items():
            if scores:
                platform_stats[platform] = {
                    'count': len(scores),
                    'avg_score': sum(scores) / len(scores),
                    'sentiment_distribution': {
                        'positive': len([s for s in scores if s > 0.1]),
                        'negative': len([s for s in scores if s < -0.1]),
                        'neutral': len([s for s in scores if -0.1 <= s <= 0.1])
                    }
                }
        
        return {
            'posts': analyzed_posts,
            'summary': {
                'total_posts': len(analyzed_posts),
                'sentiment_distribution': {
                    **sentiment_counts,
                    'total': len(analyzed_posts)
                },
                'average_sentiment_score': round(avg_score, 3),
                'most_common_patterns': dict(pattern_counts.most_common(5)),
                'by_platform': platform_stats,
                'analysis_timestamp': datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Erreur calcul sentiment social: {e}")
        return {
            'posts': [],
            'summary': {
                'total_posts': 0,
                'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
                'average_sentiment_score': 0.0,
                'most_common_patterns': {},
                'by_platform': {},
                'analysis_timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
        }

# ==================== SENTIMENT ANALYSIS ENDPOINTS ====================

@app.get("/api/sentiment/articles")
async def analyze_articles_sentiment():
    """Analyser le sentiment des articles du jour"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        if CACHE_ENABLED:
            def compute_sentiment_analysis():
                return _compute_sentiment_articles_today()
            
            # Cache des analyses de sentiment pour la journée
            sentiment_data = get_or_compute('sentiment_articles_today', compute_sentiment_analysis)
        else:
            sentiment_data = _compute_sentiment_articles_today()
        
        return {"success": True, **sentiment_data}
    
    except Exception as e:
        logger.error(f"Erreur analyse sentiment articles: {e}")
        return {"success": False, "error": str(e)}

def _compute_sentiment_articles_today():
    """Analyser le sentiment des articles d'aujourd'hui"""
    try:
        # Récupérer les articles d'aujourd'hui
        today = datetime.now().strftime('%Y-%m-%d')
        articles = list(articles_collection.find({
            'date': today
        }).sort('scraped_at', -1))
        
        # Nettoyer les données MongoDB
        clean_articles = []
        for article in articles:
            if '_id' in article:
                del article['_id']
            clean_articles.append(article)
        
        if not clean_articles:
            return {
                'articles': [],
                'summary': {
                    'total_articles': 0,
                    'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
                    'average_sentiment_score': 0.0,
                    'most_common_patterns': {},
                    'analysis_timestamp': datetime.now().isoformat()
                }
            }
        
        # Analyser le sentiment
        analysis_result = analyze_articles_sentiment(clean_articles)
        
        return analysis_result
        
    except Exception as e:
        logger.error(f"Erreur calcul sentiment articles: {e}")
        return {
            'articles': [],
            'summary': {
                'total_articles': 0,
                'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
                'average_sentiment_score': 0.0,
                'most_common_patterns': {},
                'analysis_timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
        }

# Ancien endpoint supprimé - utiliser le nouveau endpoint GPT ci-dessous

@app.get("/api/sentiment/trends")
async def get_sentiment_trends():
    """Récupérer les tendances de sentiment sur plusieurs jours"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        if CACHE_ENABLED:
            def compute_sentiment_trends():
                return _compute_sentiment_trends()
            
            # Cache des tendances (renouveler chaque jour)
            trends_data = get_or_compute('sentiment_trends', compute_sentiment_trends)
        else:
            trends_data = _compute_sentiment_trends()
        
        return {"success": True, **trends_data}
    
    except Exception as e:
        logger.error(f"Erreur tendances sentiment: {e}")
        return {"success": False, "error": str(e)}

def _compute_sentiment_trends():
    """Calculer les tendances de sentiment sur les 7 derniers jours"""
    try:
        from datetime import datetime, timedelta
        
        # Récupérer les articles des 7 derniers jours
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        articles_by_date = {}
        
        for i in range(7):
            date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
            articles = list(articles_collection.find({
                'date': date
            }))
            
            # Nettoyer les données MongoDB
            clean_articles = []
            for article in articles:
                if '_id' in article:
                    del article['_id']
                clean_articles.append(article)
            
            articles_by_date[date] = clean_articles
        
        # Analyser les tendances
        trends_result = local_sentiment_analyzer.get_sentiment_trends(articles_by_date)
        
        return trends_result
        
    except Exception as e:
        logger.error(f"Erreur calcul tendances sentiment: {e}")
        return {
            'trends_by_date': {},
            'analysis_period': {'start_date': None, 'end_date': None, 'total_days': 0},
            'error': str(e),
            'generated_at': datetime.now().isoformat()
        }

@app.get("/api/sentiment/stats")
async def get_sentiment_stats():
    """Obtenir les statistiques générales du sentiment"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        # Récupérer les analyses du jour
        today_analysis = _compute_sentiment_articles_today()
        
        # Statistiques du service
        service_stats = {
            'service_enabled': SENTIMENT_ENABLED,
            'analysis_method': 'local_french_sentiment',
            'features': [
                'Dictionnaire français spécialisé',
                'Détection de patterns Guadeloupe/Antilles',
                'Gestion des négations et intensificateurs',
                'Analyse contextuelle'
            ],
            'supported_languages': ['français', 'créole (partiel)'],
            'last_analysis': datetime.now().isoformat()
        }
        
        return {
            "success": True,
            "today_summary": today_analysis.get('summary', {}),
            "service_info": service_stats
        }
        
    except Exception as e:
        logger.error(f"Erreur stats sentiment: {e}")
        return {"success": False, "error": str(e)}

# ==================== GPT TEST ENDPOINTS ====================

@app.post("/api/test-gpt")
async def test_gpt_analysis(text: str = None):
    """Tester l'analyse GPT avec un échantillon de texte"""
    try:
        # Import du nouveau service GPT
        from gpt_analysis_service import analyze_transcription_with_gpt, test_gpt_connection
        
        # Tester la connexion d'abord
        connection_test = test_gpt_connection()
        if connection_test['status'] != 'success':
            return {
                "success": False,
                "error": "Connexion GPT échouée",
                "connection_test": connection_test
            }
        
        # Utiliser un texte de test si aucun n'est fourni
        if not text:
            text = """
            Bonjour, nous sommes en direct de RCI Guadeloupe pour les actualités de ce matin. 
            Au programme aujourd'hui, la réunion du Conseil Départemental avec Guy Losbar pour discuter du budget 2025. 
            Dans l'économie, le secteur du tourisme montre des signes de reprise après la période difficile. 
            En matière d'environnement, les sargasses continuent d'affecter les côtes guadeloupéennes. 
            Voilà pour ce tour d'horizon matinal, à très bientôt sur RCI.
            """
        
        # Analyser avec GPT
        start_time = datetime.now()
        analysis = analyze_transcription_with_gpt(text.strip(), "Test GPT")
        end_time = datetime.now()
        
        # Calculer le temps de traitement
        processing_time = (end_time - start_time).total_seconds()
        
        return {
            "success": True,
            "original_text": text.strip(),
            "gpt_analysis": analysis,
            "processing_time_seconds": processing_time,
            "connection_test": connection_test,
            "timestamp": datetime.now().isoformat()
        }
        
    except ImportError as e:
        return {
            "success": False,
            "error": f"Service GPT non disponible: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur test GPT: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/test-capture-long")
async def test_long_capture_segmented(minutes: int = 5, admin_key: str = None):
    """Tester la capture longue segmentée - ADMIN UNIQUEMENT"""
    try:
        # Vérification admin
        if admin_key != "radio_capture_admin_2025":
            return {
                "success": False,
                "error": "Test capture longue réservé à l'administration"
            }
        
        # Limiter à 20 minutes max pour sécurité
        if minutes > 20:
            minutes = 20
        
        # Modifier temporairement la durée pour le test
        original_duration = radio_service.radio_streams["rci_7h"]["duration_minutes"]  
        radio_service.radio_streams["rci_7h"]["duration_minutes"] = minutes
        
        try:
            logger.info(f"🧪 Test capture longue segmentée: {minutes} minutes")
            
            # Forcer l'utilisation de la méthode segmentée
            result = radio_service.capture_and_transcribe_stream("rci_7h", use_segmented=True)
            
            return {
                "success": result.get('success', False),
                "message": f"Test capture segmentée {minutes} minutes",
                "method": "segmented",
                "duration_minutes": minutes,
                "result": result,
                "segments_info": result.get('transcription', {}).get('segments_info', []),
                "timestamp": datetime.now().isoformat()
            }
            
        finally:
            # Restaurer la durée originale
            radio_service.radio_streams["rci_7h"]["duration_minutes"] = original_duration
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur test capture longue: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/test-capture-and-save")
async def test_capture_and_save(admin_key: str = None):
    """Test capture rapide 10s + sauvegarde en DB - ADMIN UNIQUEMENT"""
    try:
        # Vérification admin
        if admin_key != "radio_capture_admin_2025":
            return {
                "success": False,
                "error": "Test réservé à l'administration"
            }
        
        # Modifier temporairement la durée pour le test
        original_duration = radio_service.radio_streams["rci_7h"]["duration_minutes"]  
        radio_service.radio_streams["rci_7h"]["duration_minutes"] = 0.17  # 10 secondes
        
        try:
            # Lancer une vraie capture qui sauvegarde en DB
            result = radio_service.capture_and_transcribe_stream("rci_7h")
            
            return {
                "success": result.get('success', False),
                "message": "Test capture 10s avec sauvegarde DB",
                "result": result,
                "timestamp": datetime.now().isoformat()
            }
            
        finally:
            # Restaurer la durée originale
            radio_service.radio_streams["rci_7h"]["duration_minutes"] = original_duration
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Erreur test capture: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/test-capture-1min")
async def test_radio_capture_1min(admin_key: str = None):
    """Tester la capture radio avec échantillon de 30s et analyse GPT - ADMIN UNIQUEMENT"""
    try:
        # Vérification admin obligatoire pour les tests
        if admin_key != "radio_capture_admin_2025":
            return {
                "success": False,
                "error": "Test de capture réservé à l'administration - coûts OpenAI contrôlés",
                "note": "Utilisation API OpenAI Whisper + GPT"
            }
        
        # Capture de test 30 secondes pour RCI
        config = radio_service.radio_streams["rci_7h"]
        
        logger.info("🧪 Test admin - capture 30s avec OpenAI Whisper + GPT")
        
        # Marquer le début du test
        radio_service.update_transcription_step("rci_7h", "audio_capture", "Test admin 30s", 10)
        
        # Capturer 30 secondes (test rapide)
        audio_path = radio_service.capture_radio_stream("rci_7h", 30)
        
        if not audio_path:
            return {
                "success": False,
                "error": "Échec capture audio 30 secondes",
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            # Transcrire avec OpenAI Whisper API
            transcription = radio_service.transcribe_audio_file(audio_path, "rci_7h")
            
            if not transcription:
                return {
                    "success": False,
                    "error": "Échec transcription OpenAI Whisper",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Analyser avec GPT
            from gpt_analysis_service import analyze_transcription_with_gpt
            start_gpt = datetime.now()
            gpt_analysis = analyze_transcription_with_gpt(transcription['text'], "Test 30s RCI")
            end_gpt = datetime.now()
            
            gpt_processing_time = (end_gpt - start_gpt).total_seconds()
            
            # Marquer le test comme terminé
            radio_service.update_transcription_step("rci_7h", "completed", "Test admin terminé", 100)
            
            return {
                "success": True,
                "test_type": "admin_30s_sample",
                "audio_duration": 30,
                "transcription": {
                    "text": transcription['text'],
                    "language": transcription.get('language', 'fr'),
                    "character_count": len(transcription['text']),
                    "word_count": len(transcription['text'].split()),
                    "method": transcription.get('method', 'openai_whisper_api')
                },
                "gpt_analysis": gpt_analysis,
                "performance": {
                    "gpt_processing_time": gpt_processing_time,
                    "transcription_length": len(transcription['text']),
                    "audio_file_size": os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
                },
                "costs": {
                    "whisper_api": "~$0.006 pour 1 minute",
                    "gpt_analysis": f"~$0.001-0.003",
                    "note": "Coûts estimés OpenAI API"
                },
                "timestamp": datetime.now().isoformat()
            }
            
        finally:
            # Nettoyer le fichier temporaire
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)
                
    except Exception as e:
        radio_service.update_transcription_step("rci_7h", "error", f"Erreur test admin: {str(e)}", 0)
        return {
            "success": False,
            "error": f"Erreur test capture admin: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.get("/api/health")
async def health_check():
    """Vérification de santé globale du système"""
    try:
        health_status = {
            "status": "healthy",
            "services": {
                "mongodb": "connected",
                "cache": "active",
                "scheduler": "running" if len(veille_scheduler.get_job_status()) > 0 else "stopped",
                "scraper": "ready",
                "radio": "ready",
                "summary": "ready"
            },
            "cache_stats": intelligent_cache.get_cache_stats(),
            "timestamp": datetime.now().isoformat()
        }
        
        return {"success": True, "health": health_status}
        
    except Exception as e:
        return {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}

# ==================== TELEGRAM ALERTS ENDPOINTS ====================

@app.post("/api/telegram/configure")
async def configure_telegram_bot(request: Request):
    """Configurer le bot Telegram avec token et chat_id"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        body = await request.json()
        token = body.get('token', '').strip()
        chat_id = body.get('chat_id')
        
        if not token or not chat_id:
            return {"success": False, "error": "Token et chat_id requis"}
        
        # Configurer le bot
        success = telegram_alerts.configure_telegram(token, int(chat_id))
        
        if success:
            return {
                "success": True,
                "message": "Bot Telegram configuré avec succès",
                "chat_id": chat_id,
                "configured_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Erreur lors de la configuration du bot"
            }
    
    except Exception as e:
        logger.error(f"Erreur configuration Telegram: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/telegram/test")
async def test_telegram_alert():
    """Envoyer une alerte de test"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        success = telegram_alerts.send_test_alert()
        
        if success:
            return {
                "success": True,
                "message": "Alerte de test envoyée avec succès",
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Échec de l'envoi de l'alerte de test"
            }
    
    except Exception as e:
        logger.error(f"Erreur test alerte Telegram: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/telegram/start-monitoring")
async def start_telegram_monitoring():
    """Démarrer la surveillance automatique"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        telegram_alerts.start_monitoring()
        
        return {
            "success": True,
            "message": "Surveillance automatique démarrée",
            "monitoring_active": True,
            "started_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur démarrage surveillance: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/telegram/stop-monitoring")
async def stop_telegram_monitoring():
    """Arrêter la surveillance automatique"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        telegram_alerts.stop_monitoring()
        
        return {
            "success": True,
            "message": "Surveillance automatique arrêtée",
            "monitoring_active": False,
            "stopped_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur arrêt surveillance: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/telegram/status")
async def get_telegram_status():
    """Obtenir le statut de la surveillance Telegram"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        status = telegram_alerts.get_monitoring_status()
        
        return {
            "success": True,
            "status": status,
            "service_enabled": True,
            "checked_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur statut Telegram: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/telegram/send-alert")
async def send_manual_telegram_alert(request: Request):
    """Envoyer une alerte manuelle"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        body = await request.json()
        message = body.get('message', '').strip()
        chat_id = body.get('chat_id')
        
        if not message:
            return {"success": False, "error": "Message requis"}
        
        success = telegram_alerts.send_alert_sync(message, chat_id)
        
        if success:
            return {
                "success": True,
                "message": "Alerte envoyée avec succès",
                "sent_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": "Échec de l'envoi de l'alerte"
            }
    
    except Exception as e:
        logger.error(f"Erreur envoi alerte manuelle: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/telegram/alerts-history")
async def get_telegram_alerts_history(limit: int = 50):
    """Récupérer l'historique des alertes"""
    try:
        if not TELEGRAM_ALERTS_ENABLED:
            return {"success": False, "error": "Service d'alertes Telegram non disponible"}
        
        # Récupérer les alertes depuis MongoDB
        alerts = list(telegram_alerts.alerts_collection.find(
            {}, 
            {'_id': 0}
        ).sort('sent_at', -1).limit(limit))
        
        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts),
            "retrieved_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur historique alertes: {e}")
        return {"success": False, "error": str(e)}

# ==================== SENTIMENT ANALYSIS GPT ENDPOINTS ====================

@app.post("/api/sentiment/analyze")
async def analyze_text_sentiment_endpoint(request: Request):
    """Analyser le sentiment d'un texte avec GPT - Format enrichi pour la Guadeloupe"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        body = await request.json()
        text = body.get('text', '').strip()
        use_async = body.get('async', False)  # Option pour traitement asynchrone
        
        if not text:
            return {"success": False, "error": "Texte requis pour l'analyse"}
        
        if len(text) < 5:
            return {"success": False, "error": "Texte trop court pour une analyse fiable"}
        
        # Mode asynchrone - retour immédiat avec traitement en arrière-plan
        if use_async and ASYNC_SENTIMENT_ENABLED:
            # Vérifier d'abord le cache
            cached_result = get_text_sentiment_cached(text)
            if cached_result:
                logger.info(f"🎯 Sentiment cache hit - retour immédiat")
                return {
                    "success": True,
                    "cached": True,
                    "analysis": _format_enriched_response(cached_result, text),
                    "processing_time": "~0.1 secondes (cache)"
                }
            
            # Ajouter à la queue de traitement
            text_hash = analyze_text_async(text, priority='high')
            return {
                "success": True,
                "async": True,
                "text_hash": text_hash,
                "message": "Analyse démarrée en arrière-plan",
                "status_endpoint": f"/api/sentiment/status/{text_hash}",
                "estimated_completion": "10-20 secondes"
            }
        
        # Mode synchrone (original)
        logger.info(f"🤖 Analyse GPT sentiment enrichie pour texte de {len(text)} caractères")
        sentiment_result = gpt_sentiment_analyzer.analyze_sentiment(text)
        
        # Créer une réponse enrichie structurée
        response = _format_enriched_response(sentiment_result, text)
        
        logger.info(f"✅ Analyse GPT terminée: {sentiment_result['polarity']} (score: {sentiment_result['score']}, urgence: {sentiment_result['analysis_details'].get('urgency_level', 'faible')})")
        
        return response
    
    except Exception as e:
        logger.error(f"Erreur analyse sentiment: {e}")
        return {"success": False, "error": str(e)}

def _format_enriched_response(sentiment_result: Dict, text: str) -> Dict:
    """Formater la réponse enrichie de façon consistante"""
    return {
        "success": True,
        "analysis": {
            "basic_sentiment": {
                "polarity": sentiment_result['polarity'],
                "score": sentiment_result['score'],
                "intensity": sentiment_result['intensity'],
                "confidence": sentiment_result['analysis_details']['confidence']
            },
            "contextual_analysis": {
                "guadeloupe_relevance": sentiment_result['analysis_details']['guadeloupe_context'],
                "local_impact": sentiment_result['analysis_details'].get('impact_potential', ''),
                "urgency_level": sentiment_result['analysis_details'].get('urgency_level', 'faible'),
                "main_domain": sentiment_result['analysis_details'].get('main_domain', 'général')
            },
            "stakeholders": {
                "personalities": sentiment_result['analysis_details'].get('personalities_mentioned', []),
                "institutions": sentiment_result['analysis_details'].get('institutions_mentioned', [])
            },
            "thematic_breakdown": {
                "themes": sentiment_result['analysis_details']['themes'],
                "emotions": sentiment_result['analysis_details']['emotions'],
                "keywords": sentiment_result['analysis_details']['keywords']
            },
            "recommendations": {
                "suggested_actions": sentiment_result['analysis_details'].get('recommendations', []),
                "alerts": sentiment_result['analysis_details'].get('alerts', []),
                "follow_up_needed": sentiment_result.get('enhanced_analysis', {}).get('actionable_insights', {}).get('follow_up_needed', False)
            }
        },
        "metadata": {
            "text_length": len(text),
            "word_count": sentiment_result['word_count'],
            "analyzed_at": sentiment_result.get('analyzed_at'),
            "method": sentiment_result['analysis_details'].get('method', 'gpt-4o-mini-contextuel'),
            "processing_time": "~3-8 secondes"
        },
        "raw_sentiment": sentiment_result  # Données complètes pour debug/développement
    }

@app.get("/api/sentiment/status/{text_hash}")
async def get_sentiment_analysis_status_endpoint(text_hash: str):
    """Obtenir le statut d'une analyse de sentiment asynchrone"""
    try:
        if not ASYNC_SENTIMENT_ENABLED:
            return {"success": False, "error": "Service asynchrone non disponible"}
        
        status = get_sentiment_analysis_status(text_hash)
        
        if status['status'] == 'completed':
            # Si terminé, formater la réponse complète
            cached_result = get_text_sentiment_cached("")  # Hash sera comparé
            if cached_result:
                return {
                    "success": True,
                    "status": "completed",
                    "analysis": _format_enriched_response(cached_result, "")['analysis'],
                    "completed_at": status.get('completed_at')
                }
        
        return {"success": True, **status}
        
    except Exception as e:
        logger.error(f"Erreur statut sentiment: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/sentiment/async/stats")
async def get_async_sentiment_stats():
    """Obtenir les statistiques du service asynchrone de sentiment"""
    try:
        if not ASYNC_SENTIMENT_ENABLED:
            return {"success": False, "error": "Service asynchrone non disponible"}
        
        stats = async_sentiment_service.get_processing_stats()
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"Erreur stats sentiment async: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/sentiment/async/cleanup")
async def cleanup_async_sentiment_data(days: int = 7):
    """Nettoyer les anciennes données de sentiment asynchrone"""
    try:
        if not ASYNC_SENTIMENT_ENABLED:
            return {"success": False, "error": "Service asynchrone non disponible"}
        
        result = async_sentiment_service.cleanup_old_data(days)
        return {"success": True, "cleanup": result}
        
    except Exception as e:
        logger.error(f"Erreur nettoyage sentiment async: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/sentiment/analyze/quick")
async def analyze_text_sentiment_quick(request: Request):
    """Analyse de sentiment rapide et simplifiée - Format compact"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        body = await request.json()
        text = body.get('text', '').strip()
        
        if not text:
            return {"success": False, "error": "Texte requis pour l'analyse"}
        
        # Analyser avec GPT
        sentiment_result = gpt_sentiment_analyzer.analyze_sentiment(text)
        
        # Format compact et rapide
        return {
            "success": True,
            "polarity": sentiment_result['polarity'],
            "score": sentiment_result['score'],
            "intensity": sentiment_result['intensity'],
            "themes": sentiment_result['analysis_details']['themes'][:3],  # Top 3 themes
            "guadeloupe_context": sentiment_result['analysis_details']['guadeloupe_context'],
            "confidence": sentiment_result['analysis_details']['confidence'],
            "urgency": sentiment_result['analysis_details'].get('urgency_level', 'faible'),
            "method": "gpt-quick-analysis"
        }
    
    except Exception as e:
        logger.error(f"Erreur analyse sentiment rapide: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/sentiment/articles")
async def get_articles_with_sentiment():
    """Récupérer les articles avec analyse de sentiment GPT"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        # Récupérer les articles du jour
        articles = guadeloupe_scraper.get_todays_articles()
        
        if not articles:
            return {
                "success": True,
                "articles": [],
                "count": 0,
                "message": "Aucun article trouvé pour aujourd'hui"
            }
        
        # Analyser le sentiment (limité aux 20 premiers pour éviter les coûts)
        articles_to_analyze = articles[:20]
        logger.info(f"🤖 Analyse GPT sentiment de {len(articles_to_analyze)} articles")
        
        analyzed_result = gpt_sentiment_analyzer.analyze_articles_batch(articles_to_analyze)
        
        return {
            "success": True,
            "articles": analyzed_result['articles'],
            "count": len(analyzed_result['articles']),
            "summary": analyzed_result['summary'],
            "note": f"Analysé {len(articles_to_analyze)}/{len(articles)} articles avec GPT"
        }
    
    except Exception as e:
        logger.error(f"Erreur analyse articles sentiment: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/sentiment/test")
async def test_gpt_sentiment():
    """Tester le service d'analyse de sentiment GPT"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        # Textes de test pour la Guadeloupe
        test_texts = [
            "Excellente nouvelle pour la Guadeloupe ! Guy Losbar annonce de nouveaux investissements dans l'éducation.",
            "Grave accident sur la route de Basse-Terre, plusieurs blessés transportés au CHU.",
            "Le Conseil Départemental vote le budget 2025 pour soutenir les familles en difficulté.",
            "Festival de musique créole à Pointe-à-Pitre : une ambiance formidable !",
            "Alerte cyclone en Guadeloupe, les autorités appellent à la prudence."
        ]
        
        results = []
        for i, text in enumerate(test_texts):
            try:
                sentiment = gpt_sentiment_analyzer.analyze_sentiment(text)
                results.append({
                    'test_id': i + 1,
                    'text': text,
                    'sentiment': sentiment['polarity'],
                    'score': sentiment['score'],
                    'intensity': sentiment['intensity'],
                    'emotions': sentiment['analysis_details']['emotions'],
                    'themes': sentiment['analysis_details']['themes'],
                    'guadeloupe_context': sentiment['analysis_details']['guadeloupe_context'],
                    'confidence': sentiment['analysis_details']['confidence']
                })
            except Exception as e:
                results.append({
                    'test_id': i + 1,
                    'text': text,
                    'error': str(e)
                })
        
        return {
            "success": True,
            "test_results": results,
            "tests_count": len(test_texts),
            "successful_tests": len([r for r in results if 'error' not in r]),
            'service_method': 'gpt-4o-mini',
            "tested_at": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur test sentiment GPT: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/sentiment/predict-reaction")
async def predict_population_reaction_endpoint(request: Request):
    """Prédire la réaction de la population avec analyse croisée articles/réseaux sociaux"""
    try:
        if not POPULATION_REACTION_ENABLED:
            return {"success": False, "error": "Service de prédiction des réactions non disponible"}
        
        body = await request.json()
        text = body.get('text', '').strip()
        context = body.get('context', {})
        
        if not text:
            return {"success": False, "error": "Texte requis pour la prédiction"}
        
        if len(text) < 10:
            return {"success": False, "error": "Texte trop court pour une prédiction fiable"}
        
        logger.info(f"🔮 Prédiction réaction population pour texte de {len(text)} caractères")
        
        # Générer la prédiction complète
        prediction = predict_population_reaction(text, context)
        
        if 'error' in prediction:
            return {"success": False, "error": prediction['error']}
        
        # Formater la réponse
        response = {
            "success": True,
            "prediction": {
                "text_analyzed": prediction['text_analyzed'],
                "sentiment_analysis": {
                    "polarity": prediction['main_sentiment']['polarity'],
                    "score": prediction['main_sentiment']['score'],
                    "intensity": prediction['main_sentiment']['intensity'],
                    "urgency": prediction['main_sentiment']['analysis_details'].get('urgency_level', 'faible'),
                    "guadeloupe_context": prediction['main_sentiment']['analysis_details']['guadeloupe_context']
                },
                "population_reaction": prediction['population_reaction_forecast'],
                "data_sources": {
                    "similar_articles": prediction['supporting_data']['similar_articles'],
                    "similar_social_posts": prediction['supporting_data']['similar_social_posts'],
                    "sample_articles": prediction['supporting_data']['articles_sample'],
                    "sample_social": prediction['supporting_data']['social_sample']
                },
                "influence_analysis": prediction['influence_factors'],
                "strategic_recommendations": prediction['strategic_recommendations'],
                "confidence": prediction['confidence_level']
            },
            "metadata": {
                "analysis_timestamp": prediction['analysis_timestamp'],
                "method": "gpt-population-prediction",
                "data_sources": "articles + social_media + historical_trends"
            }
        }
        
        logger.info(f"✅ Prédiction terminée: {prediction.get('population_reaction_forecast', {}).get('overall', 'inconnue')} (confiance: {prediction.get('confidence_level', 0)})")
        
        return response
    
    except Exception as e:
        logger.error(f"Erreur prédiction réaction: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/sentiment/reaction-trends")
async def get_reaction_trends():
    """Obtenir les tendances de réactions de la population"""
    try:
        if not POPULATION_REACTION_ENABLED:
            return {"success": False, "error": "Service de prédiction des réactions non disponible"}
        
        # Obtenir les statistiques de prédictions récentes
        stats = population_reaction_predictor.get_processing_stats() if hasattr(population_reaction_predictor, 'get_processing_stats') else {}
        
        # Analyser les tendances des 30 derniers jours
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=30)
        
        try:
            recent_predictions = list(population_reaction_predictor.reaction_predictions.find({
                'analysis_timestamp': {'$gte': cutoff_date.isoformat()}
            }).sort('analysis_timestamp', -1).limit(50))
            
            if recent_predictions:
                # Calculer les tendances
                avg_polarization = sum([
                    1 if p['population_reaction_forecast']['polarization_risk'] == 'élevé' else
                    0.5 if p['population_reaction_forecast']['polarization_risk'] == 'modéré' else 0
                    for p in recent_predictions
                ]) / len(recent_predictions)
                
                most_common_reactions = {}
                for pred in recent_predictions:
                    reaction = pred['population_reaction_forecast']['overall']
                    most_common_reactions[reaction] = most_common_reactions.get(reaction, 0) + 1
                
                trends_data = {
                    'total_predictions': len(recent_predictions),
                    'average_polarization_risk': round(avg_polarization, 2),
                    'most_common_reactions': dict(sorted(most_common_reactions.items(), key=lambda x: x[1], reverse=True)),
                    'recent_predictions': recent_predictions[:10]  # 10 plus récentes
                }
            else:
                trends_data = {
                    'total_predictions': 0,
                    'message': 'Pas assez de données pour calculer les tendances'
                }
                
        except Exception as e:
            logger.warning(f"Erreur calcul tendances: {e}")
            trends_data = {'error': 'Erreur calcul tendances'}
        
        return {
            "success": True,
            "trends": trends_data,
            "service_stats": stats,
            "period": "30 derniers jours"
        }
        
    except Exception as e:
        logger.error(f"Erreur tendances réactions: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)