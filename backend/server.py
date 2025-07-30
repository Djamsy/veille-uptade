from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
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

# Import du cache avec fallback - Réactivé avec cache 24H

# Import du service réseaux sociaux
try:
    from social_media_service import social_scraper
    SOCIAL_MEDIA_ENABLED = True
    print("✅ Service réseaux sociaux activé")
except ImportError as e:
    print(f"⚠️ Service réseaux sociaux non disponible: {e}")
    SOCIAL_MEDIA_ENABLED = False
try:
    from sentiment_analysis_service import local_sentiment_analyzer, analyze_articles_sentiment
    SENTIMENT_ENABLED = True
    print("✅ Service d'analyse de sentiment local activé")
except ImportError as e:
    print(f"⚠️ Service d'analyse de sentiment non disponible: {e}")
    SENTIMENT_ENABLED = False
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

# MongoDB Configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
try:
    client = MongoClient(MONGO_URL)
    db = client.veille_media
    
    # Collections
    articles_collection = db.articles_guadeloupe
    transcriptions_collection = db.radio_transcriptions
    digests_collection = db.daily_digests
    logs_collection = db.scheduler_logs
    
    print("✅ Connected to MongoDB successfully")
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")

# Démarrer les services
start_scheduler()
if CACHE_ENABLED:
    start_cache_service()

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
    """Récupérer le statut du dernier scraping"""
    try:
        last_result = intelligent_cache.get_cached_data('last_scraping_result')
        if last_result:
            return {"success": True, "result": last_result}
        else:
            return {"success": False, "message": "Aucun scraping récent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut scraping: {str(e)}")

# ==================== TRANSCRIPTION ENDPOINTS ====================

@app.get("/api/transcriptions")
async def get_transcriptions():
    """Récupérer les transcriptions du jour avec cache"""
    try:
        def fetch_transcriptions():
            return radio_service.get_todays_transcriptions()
        
        # Cache de 5 minutes pour les transcriptions
        transcriptions = get_or_compute('transcriptions_today', fetch_transcriptions)
        return {"success": True, "transcriptions": transcriptions, "count": len(transcriptions)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération transcriptions: {str(e)}")

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
async def capture_radio_now():
    """Lancer la capture radio immédiatement en arrière-plan"""
    try:
        # Invalider le cache des transcriptions
        cache_invalidate('transcriptions')
        
        # Lancer la capture en arrière-plan
        import threading
        
        def capture_async():
            try:
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
        
        return {
            "success": True, 
            "message": "Capture radio démarrée en arrière-plan. Consultez les transcriptions dans quelques minutes.",
            "estimated_completion": "3-5 minutes"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lancement capture: {str(e)}")

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

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcrire un fichier audio uploadé avec Whisper"""
    try:
        if not file.filename.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
            raise HTTPException(status_code=400, detail="Format audio non supporté")
        
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name
        
        try:
            # Utiliser le service de transcription
            transcription_data = radio_service.transcribe_audio_file(temp_path)
            
            if transcription_data:
                # Sauvegarder en base
                record = {
                    "id": str(uuid.uuid4()),
                    "filename": file.filename,
                    "transcription_text": transcription_data['text'],
                    "language": transcription_data['language'],
                    "duration_seconds": transcription_data['duration'],
                    "segments": transcription_data['segments'],
                    "uploaded_at": datetime.now().isoformat(),
                    "date": datetime.now().strftime('%Y-%m-%d'),
                    "source": "upload"
                }
                
                transcriptions_collection.insert_one(record)
                
                # Invalider le cache des transcriptions
                cache_invalidate('transcriptions')
                
                return {"success": True, "transcription": record}
            else:
                raise HTTPException(status_code=500, detail="Échec de la transcription")
            
        finally:
            # Nettoyer le fichier temporaire
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur transcription: {str(e)}")

# ==================== DIGEST ENDPOINTS ====================

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

@app.get("/api/search")
async def search_content(q: str, source: str = "all", limit: int = 50, social_only: bool = False):
    """Rechercher dans les articles et posts des réseaux sociaux"""
    try:
        if not q or len(q.strip()) < 2:
            return {"success": False, "error": "Requête de recherche trop courte (minimum 2 caractères)"}
        
        search_query = q.strip().lower()
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
                            {'keyword_searched': {'$regex': search_query, '$options': 'i'}}
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
        
        stats = social_scraper.get_posts_stats()
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
                logger.info("🚀 Début scraping réseaux sociaux...")
                results = social_scraper.scrape_all_keywords()
                
                # Sauvegarder tous les posts
                all_posts = results['twitter'] + results['facebook'] + results['instagram']
                saved_count = social_scraper.save_posts_to_db(all_posts)
                
                # Sauvegarder le résultat dans le cache
                cache_result = {
                    'success': True,
                    'total_posts': results['total_posts'],
                    'saved_posts': saved_count,
                    'by_platform': {
                        'twitter': len(results['twitter']),
                        'facebook': len(results['facebook']),
                        'instagram': len(results['instagram'])
                    },
                    'keywords': results['keywords_searched'],
                    'scraped_at': results['scraped_at'],
                    'demo_mode': results.get('demo_mode', False),
                    'note': results.get('note', '')
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
            "message": "Scraping des réseaux sociaux démarré en arrière-plan",
            "estimated_completion": "3-5 minutes",
            "note": "Utilise snscrape (Twitter) et Playwright (Facebook) sans API"
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

@app.post("/api/sentiment/analyze")
async def analyze_text_sentiment_endpoint(text: str = Form(...)):
    """Analyser le sentiment d'un texte donné"""
    try:
        if not SENTIMENT_ENABLED:
            return {"success": False, "error": "Service d'analyse de sentiment non disponible"}
        
        if not text:
            return {"success": False, "error": "Texte requis"}
        
        # Analyser le sentiment du texte
        sentiment_result = local_sentiment_analyzer.analyze_sentiment(text)
        
        return {
            "success": True,
            "text": text[:200] + "..." if len(text) > 200 else text,
            "sentiment": sentiment_result
        }
        
    except Exception as e:
        logger.error(f"Erreur analyse sentiment texte: {e}")
        return {"success": False, "error": str(e)}

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)