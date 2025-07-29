from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Initialize FastAPI
app = FastAPI(title="Veille Média API", version="1.0.0")

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
    articles_collection = db.articles
    transcriptions_collection = db.transcriptions
    social_posts_collection = db.social_posts
    sentiment_analysis_collection = db.sentiment_analysis
    
    print("✅ Connected to MongoDB successfully")
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")

@app.get("/")
async def root():
    return {"message": "🎯 API Veille Média - Prêt à surveiller les médias !"}

# ==================== ARTICLES ENDPOINTS ====================

@app.get("/api/articles")
async def get_articles():
    """Récupérer tous les articles"""
    try:
        articles = list(articles_collection.find({}, {"_id": 0}).sort("date", -1).limit(50))
        return {"success": True, "articles": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération articles: {str(e)}")

@app.post("/api/articles/fetch")
async def fetch_articles():
    """Lancer la récupération d'articles depuis les sources"""
    try:
        # Simulation pour l'instant - sera implémenté avec RSS + NewsAPI
        sample_articles = [
            {
                "id": str(uuid.uuid4()),
                "title": "Nouvelles technologies en 2025",
                "content": "Les dernières innovations technologiques...",
                "source": "TechNews",
                "url": "https://example.com/tech-news-1",
                "date": datetime.now().isoformat(),
                "author": "Jean Dupont"
            },
            {
                "id": str(uuid.uuid4()),
                "title": "IA et société : les enjeux",
                "content": "L'intelligence artificielle transforme...",
                "source": "AIToday",
                "url": "https://example.com/ai-news-1",
                "date": datetime.now().isoformat(),
                "author": "Marie Martin"
            }
        ]
        
        # Sauvegarder en base
        for article in sample_articles:
            articles_collection.update_one(
                {"id": article["id"]},
                {"$set": article},
                upsert=True
            )
        
        return {"success": True, "message": f"✅ {len(sample_articles)} articles récupérés", "articles": sample_articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur fetch articles: {str(e)}")

# ==================== TRANSCRIPTION ENDPOINTS ====================

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcrire un fichier audio avec Whisper"""
    try:
        if not file.filename.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
            raise HTTPException(status_code=400, detail="Format audio non supporté")
        
        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name
        
        try:
            # Simulation de transcription pour l'instant
            # Sera remplacé par whisper.load_model() et model.transcribe()
            transcription_text = f"[SIMULATION] Transcription du fichier {file.filename}: Ceci est une transcription simulée du contenu audio."
            
            # Sauvegarder en base
            transcription_data = {
                "id": str(uuid.uuid4()),
                "filename": file.filename,
                "transcription": transcription_text,
                "date": datetime.now().isoformat(),
                "duration": "00:02:30",  # Sera calculé par Whisper
                "language": "fr"
            }
            
            transcriptions_collection.insert_one(transcription_data)
            
            return {"success": True, "transcription": transcription_data}
            
        finally:
            # Nettoyer le fichier temporaire
            os.unlink(temp_path)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur transcription: {str(e)}")

@app.get("/api/transcriptions")
async def get_transcriptions():
    """Récupérer toutes les transcriptions"""
    try:
        transcriptions = list(transcriptions_collection.find({}, {"_id": 0}).sort("date", -1).limit(20))
        return {"success": True, "transcriptions": transcriptions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération transcriptions: {str(e)}")

# ==================== SOCIAL MEDIA ENDPOINTS ====================

@app.get("/api/social-posts")
async def get_social_posts():
    """Récupérer les posts des réseaux sociaux"""
    try:
        posts = list(social_posts_collection.find({}, {"_id": 0}).sort("date", -1).limit(30))
        return {"success": True, "posts": posts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération posts: {str(e)}")

@app.post("/api/social-posts/fetch")
async def fetch_social_posts(keywords: str = Form(...)):
    """Récupérer des posts des réseaux sociaux par mots-clés"""
    try:
        # Simulation pour l'instant - sera implémenté avec Reddit API
        sample_posts = [
            {
                "id": str(uuid.uuid4()),
                "platform": "Reddit",
                "title": f"Discussion sur {keywords}",
                "content": f"Contenu intéressant à propos de {keywords}...",
                "author": "user123",
                "date": datetime.now().isoformat(),
                "upvotes": 42,
                "url": "https://reddit.com/r/example/post1"
            },
            {
                "id": str(uuid.uuid4()),
                "platform": "Reddit",
                "title": f"Analyse de {keywords}",
                "content": f"Une analyse approfondie de {keywords}...",
                "author": "analyst456",
                "date": datetime.now().isoformat(),
                "upvotes": 28,
                "url": "https://reddit.com/r/example/post2"
            }
        ]
        
        # Sauvegarder en base
        for post in sample_posts:
            social_posts_collection.update_one(
                {"id": post["id"]},
                {"$set": post},
                upsert=True
            )
        
        return {"success": True, "message": f"✅ {len(sample_posts)} posts récupérés", "posts": sample_posts}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur fetch social posts: {str(e)}")

# ==================== SENTIMENT ANALYSIS ENDPOINTS ====================

@app.post("/api/analyze-sentiment")
async def analyze_sentiment(text: str = Form(...)):
    """Analyser le sentiment d'un texte"""
    try:
        # Simulation pour l'instant - sera implémenté avec VADER + TextBlob
        sentiment_score = 0.65  # Positif simulé
        sentiment_label = "Positif" if sentiment_score > 0.1 else "Négatif" if sentiment_score < -0.1 else "Neutre"
        
        analysis_data = {
            "id": str(uuid.uuid4()),
            "text": text[:100] + "..." if len(text) > 100 else text,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "confidence": 0.85,
            "date": datetime.now().isoformat()
        }
        
        sentiment_analysis_collection.insert_one(analysis_data)
        
        return {"success": True, "analysis": analysis_data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur analyse sentiment: {str(e)}")

@app.get("/api/sentiment-analyses")
async def get_sentiment_analyses():
    """Récupérer toutes les analyses de sentiment"""
    try:
        analyses = list(sentiment_analysis_collection.find({}, {"_id": 0}).sort("date", -1).limit(20))
        return {"success": True, "analyses": analyses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération analyses: {str(e)}")

# ==================== DASHBOARD ENDPOINT ====================

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    """Récupérer les statistiques du dashboard"""
    try:
        stats = {
            "total_articles": articles_collection.count_documents({}),
            "total_transcriptions": transcriptions_collection.count_documents({}),
            "total_social_posts": social_posts_collection.count_documents({}),
            "total_sentiment_analyses": sentiment_analysis_collection.count_documents({}),
            "last_update": datetime.now().isoformat()
        }
        return {"success": True, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur stats dashboard: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)