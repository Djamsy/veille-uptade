import os
import logging
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# Charger .env local (si présent)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("veille_media_backend")

# === App ===
app = FastAPI()
START_TIME = datetime.utcnow()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en dev ; restreindre en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Config ===
MONGO_URL = os.environ.get("MONGO_URL")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

# === MongoDB ===
def get_mongo_client():
    if not MONGO_URL:
        logger.warning("MONGO_URL non défini.")
        return None
    try:
        client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        logger.info("✅ Connexion à MongoDB réussie.")
        return client
    except Exception as e:
        logger.error(f"Erreur de connexion MongoDB: {e}")
        return None

mongo_client = get_mongo_client()
db = mongo_client.get_default_database() if mongo_client else None

# === Import des services (fallbacks tolérés) ===
def safe_import(module: str, symbol: str):
    try:
        mod = __import__(module, fromlist=[symbol])
        return getattr(mod, symbol)
    except ImportError as e:
        logger.warning(f"{symbol} non disponible depuis {module}: {e}")
        return None

# Exemple : scraper (utilisé plus bas)
guadeloupe_scraper = None
try:
    from .scraper_service import guadeloupe_scraper
except ImportError as e:
    logger.warning(f"scraper_service non disponible: {e}")
    guadeloupe_scraper = None

# Sentiment asynchrone router + fallback pour que les endpoints existent même si service absent
ASYNC_SENTIMENT_ENABLED = False
try:
    from .async_sentiment_service import (
        async_sentiment_service,
        analyze_text_async,
        get_text_sentiment_cached,
        get_sentiment_analysis_status,
    )
    ASYNC_SENTIMENT_ENABLED = True
    logger.info("✅ Service d'analyse de sentiment asynchrone activé")
except ImportError as e:
    logger.warning(f"Service async sentiment non dispo: {e}")

# Inclusion des routes
try:
    from .sentiment_routes import router as sentiment_router
    app.include_router(sentiment_router)
    logger.info("✅ sentiment_routes inclus")
except Exception as e:
    logger.warning(f"Impossible d'inclure sentiment_routes: {e}")

# === Routes de base ===
@app.get("/", tags=["health"])
def root():
    return {
        "message": "🏝️ API Veille Média Guadeloupe v2.1 - Cache intelligent activé !",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/health", tags=["health"])
def health():
    uptime = (datetime.utcnow() - START_TIME).total_seconds()
    status = {
        "mongo_connected": bool(mongo_client),
        "async_sentiment": ASYNC_SENTIMENT_ENABLED,
        "environment": ENVIRONMENT,
        "uptime_seconds": uptime,
    }
    return {"status": status}

@app.get("/scrape/manual", tags=["scraping"])
def run_scraper():
    if not guadeloupe_scraper:
        raise HTTPException(status_code=500, detail="Scraper service non disponible")
    try:
        result = guadeloupe_scraper.run()  # adapte si la signature diffère
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Erreur scraping: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === Gestion globale des erreurs ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Erreur non gérée: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur", "error": str(exc)},
    )