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

# Import des services
from scraper_service import guadeloupe_scraper
from radio_service import radio_service  
from summary_service import summary_service
from scheduler_service import veille_scheduler, start_scheduler

# Initialize FastAPI
app = FastAPI(title="Veille Média Guadeloupe API", version="2.0.0")

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

# Démarrer le scheduler automatique
start_scheduler()

@app.get("/")
async def root():
    return {"message": "🏝️ API Veille Média Guadeloupe - Prêt à surveiller l'actualité !"}

# ==================== DASHBOARD ENDPOINTS ====================

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    """Récupérer les statistiques du dashboard"""
    try:
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
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur stats dashboard: {str(e)}")

# ==================== ARTICLES ENDPOINTS ====================

@app.get("/api/articles")
async def get_articles():
    """Récupérer les articles du jour"""
    try:
        articles = guadeloupe_scraper.get_todays_articles()
        return {"success": True, "articles": articles, "count": len(articles)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération articles: {str(e)}")

@app.get("/api/articles/{date}")
async def get_articles_by_date(date: str):
    """Récupérer les articles d'une date spécifique (YYYY-MM-DD)"""
    try:
        articles = guadeloupe_scraper.get_articles_by_date(date)
        return {"success": True, "articles": articles, "count": len(articles), "date": date}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération articles: {str(e)}")

@app.post("/api/articles/scrape-now")
async def scrape_articles_now():
    """Lancer le scraping d'articles immédiatement"""
    try:
        result = guadeloupe_scraper.scrape_all_sites()
        return {"success": True, "message": "Scraping terminé", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur scraping: {str(e)}")

# ==================== TRANSCRIPTION ENDPOINTS ====================

@app.get("/api/transcriptions")
async def get_transcriptions():
    """Récupérer les transcriptions du jour"""
    try:
        transcriptions = radio_service.get_todays_transcriptions()
        return {"success": True, "transcriptions": transcriptions, "count": len(transcriptions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération transcriptions: {str(e)}")

@app.get("/api/transcriptions/{date}")
async def get_transcriptions_by_date(date: str):
    """Récupérer les transcriptions d'une date spécifique"""
    try:
        transcriptions = radio_service.get_transcriptions_by_date(date)
        return {"success": True, "transcriptions": transcriptions, "count": len(transcriptions), "date": date}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération transcriptions: {str(e)}")

@app.post("/api/transcriptions/capture-now")
async def capture_radio_now():
    """Lancer la capture radio immédiatement"""
    try:
        result = radio_service.capture_all_streams()
        return {"success": True, "message": "Capture terminée", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur capture radio: {str(e)}")

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
    """Récupérer le digest du jour"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        digest_id = f"digest_{datetime.now().strftime('%Y%m%d')}"
        
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
        
        return {"success": True, "digest": digest}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération digest: {str(e)}")

@app.get("/api/digest/{date}")
async def get_digest_by_date(date: str):
    """Récupérer le digest d'une date spécifique"""
    try:
        digest_id = f"digest_{date.replace('-', '')}"
        digest = digests_collection.find_one({"id": digest_id}, {"_id": 0})
        
        if not digest:
            return {"success": False, "message": f"Aucun digest trouvé pour le {date}"}
        
        return {"success": True, "digest": digest}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération digest: {str(e)}")

@app.get("/api/digest/{date}/html", response_class=HTMLResponse)
async def get_digest_html(date: str):
    """Récupérer le digest en format HTML pur"""
    try:
        digest_id = f"digest_{date.replace('-', '')}"
        digest = digests_collection.find_one({"id": digest_id}, {"_id": 0})
        
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
            </style>
        </head>
        <body>
            {digest['digest_html']}
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
    """Obtenir le statut du scheduler"""
    try:
        jobs = veille_scheduler.get_job_status()
        logs = veille_scheduler.get_recent_logs(10)
        
        return {
            "success": True,
            "jobs": jobs,
            "recent_logs": logs,
            "scheduler_running": len(jobs) > 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur statut scheduler: {str(e)}")

@app.post("/api/scheduler/run-job/{job_id}")
async def run_job_manually(job_id: str):
    """Exécuter un job manuellement"""
    try:
        result = veille_scheduler.run_job_manually(job_id)
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

# ==================== LEGACY ENDPOINTS (pour compatibilité) ====================

@app.get("/api/articles-old")
async def get_articles_old():
    """Ancien endpoint articles pour compatibilité"""
    return await get_articles()

@app.get("/api/transcriptions-old") 
async def get_transcriptions_old():
    """Ancien endpoint transcriptions pour compatibilité"""
    return await get_transcriptions()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)