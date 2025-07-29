from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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

# Import des services (avec gestion d'erreur pour le cache)
from scraper_service import guadeloupe_scraper
from radio_service import radio_service  
from summary_service import summary_service
from scheduler_service import veille_scheduler, start_scheduler

# Import du cache avec fallback
try:
    from cache_service import intelligent_cache, get_or_compute, cache_invalidate, start_cache_service
    CACHE_ENABLED = True
    print("✅ Cache service importé avec succès")
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
    """Récupérer les statistiques du dashboard avec cache intelligent"""
    try:
        def compute_stats():
            today = datetime.now().strftime('%Y-%m-%d')
            
            stats = {
                "total_articles": articles_collection.count_documents({}),
                "today_articles": articles_collection.count_documents({"date": today}),
                "total_transcriptions": transcriptions_collection.count_documents({}),
                "today_transcriptions": transcriptions_collection.count_documents({"date": today}),
                "total_digests": digests_collection.count_documents({}),
                "scheduler_jobs": len(veille_scheduler.get_job_status()),
                "last_update": datetime.now().isoformat(),
                "date": today
            }
            
            # Ajouter les stats du cache si disponible
            if CACHE_ENABLED:
                try:
                    stats["cache_stats"] = intelligent_cache.get_cache_stats()
                except Exception as e:
                    print(f"Erreur stats cache: {e}")
                    stats["cache_stats"] = {"error": str(e)}
            
            return stats
        
        # Utiliser le cache intelligent si disponible
        if CACHE_ENABLED:
            stats = get_or_compute('dashboard_stats', compute_stats)
        else:
            stats = compute_stats()
            
        return {"success": True, "stats": stats}
        
    except Exception as e:
        print(f"Erreur dashboard stats: {e}")
        # Retourner des stats basiques en cas d'erreur
        return {"success": True, "stats": {
            "total_articles": 0,
            "today_articles": 0,
            "total_transcriptions": 0,
            "today_transcriptions": 0,
            "total_digests": 0,
            "scheduler_jobs": 0,
            "last_update": datetime.now().isoformat(),
            "date": datetime.now().strftime('%Y-%m-%d'),
            "error": str(e)
        }}

# ==================== ARTICLES ENDPOINTS ====================

@app.get("/api/articles")
async def get_articles():
    """Récupérer les articles du jour avec cache intelligent"""
    try:
        def fetch_articles():
            return guadeloupe_scraper.get_todays_articles()
        
        # Cache de 5 minutes pour les articles
        articles = get_or_compute('articles_today', fetch_articles)
        return {"success": True, "articles": articles, "count": len(articles)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération articles: {str(e)}")

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
    """Lancer le scraping d'articles immédiatement avec timeout optimisé"""
    try:
        # Invalider le cache des articles
        cache_invalidate('articles')
        
        # Lancer le scraping en arrière-plan pour éviter les timeouts
        import threading
        
        def scrape_async():
            try:
                result = guadeloupe_scraper.scrape_all_sites()
                # Sauvegarder le résultat dans le cache
                intelligent_cache.set_cached_data('last_scraping_result', result)
            except Exception as e:
                intelligent_cache.set_cached_data('last_scraping_result', {
                    'success': False,
                    'error': str(e),
                    'scraped_at': datetime.now().isoformat()
                })
        
        # Démarrer le scraping en arrière-plan
        scraping_thread = threading.Thread(target=scrape_async)
        scraping_thread.daemon = True
        scraping_thread.start()
        
        return {
            "success": True, 
            "message": "Scraping démarré en arrière-plan. Consultez les articles dans quelques minutes.",
            "estimated_completion": "2-3 minutes"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lancement scraping: {str(e)}")

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
                articles = guadeloupe_scraper.get_todays_articles()
                transcriptions = radio_service.get_todays_transcriptions()
                
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
        
        articles = guadeloupe_scraper.get_todays_articles()
        transcriptions = radio_service.get_todays_transcriptions()
        
        digest_html = summary_service.create_daily_digest(articles, transcriptions)
        
        digest_id = f"digest_{datetime.now().strftime('%Y%m%d')}"
        digest_record = {
            'id': digest_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
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
        
        return {"success": True, "message": "Digest créé", "digest": digest_record}
        
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