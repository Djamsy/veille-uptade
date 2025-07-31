import os
import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pymongo import MongoClient
import certifi

# Charger .env si utilisé
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("veille_media_backend")

# === App ===
app = FastAPI()
start_time = datetime.utcnow()

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
db = None
if mongo_client:
    try:
        db = mongo_client.get_default_database()
    except Exception:
        pass

# === Import des services avec fallbacks ===

# Scraper / radio / résumé / PDF / transcription
try:
    from .scraper_service import guadeloupe_scraper
except ImportError as e:
    logger.warning(f"scraper_service non disponible: {e}")
    guadeloupe_scraper = None

try:
    from .radio_service import radio_service
except ImportError as e:
    logger.warning(f"radio_service non disponible: {e}")
    radio_service = None

try:
    from .summary_service import summary_service
except ImportError as e:
    logger.warning(f"summary_service non disponible: {e}")
    summary_service = None

try:
    from .pdf_service import pdf_digest_service
except ImportError as e:
    logger.warning(f"pdf_digest_service non disponible: {e}")
    pdf_digest_service = None

try:
    from .transcription_analysis_service import transcription_analyzer
except ImportError as e:
    logger.warning(f"transcription_analysis_service non disponible: {e}")
    transcription_analyzer = None

# Scheduler
try:
    from .scheduler_service import veille_scheduler, start_scheduler

    SCHEDULER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"scheduler_service non disponible: {e}")
    veille_scheduler = None
    start_scheduler = None
    SCHEDULER_AVAILABLE = False

# Réseaux sociaux moderne / fallback
SOCIAL_MEDIA_ENABLED = False
modern_social_scraper = None
social_scraper = None
try:
    from .modern_social_service import modern_social_scraper

    social_scraper = modern_social_scraper
    SOCIAL_MEDIA_ENABLED = True
    logger.info("✅ Service réseaux sociaux MODERNE activé")
except ImportError as e:
    logger.warning(f"Service réseaux sociaux moderne non disponible: {e}")
    try:
        from .social_media_service import social_scraper

        modern_social_scraper = social_scraper
        SOCIAL_MEDIA_ENABLED = True
        logger.info("✅ Fallback: Service réseaux sociaux classique activé")
    except ImportError as e2:
        logger.error(f"Aucun service réseaux sociaux disponible: {e2}")
        modern_social_scraper = None
        social_scraper = None

# Sentiment GPT avec fallback local
SENTIMENT_ENABLED = False
try:
    from .gpt_sentiment_service import gpt_sentiment_analyzer, analyze_articles_sentiment

    SENTIMENT_ENABLED = True
    logger.info("✅ Service d'analyse de sentiment GPT activé")
except ImportError as e:
    logger.warning(f"Service d'analyse de sentiment GPT non disponible: {e}")
    try:
        from .sentiment_analysis_service import local_sentiment_analyzer, analyze_articles_sentiment

        gpt_sentiment_analyzer = local_sentiment_analyzer
        SENTIMENT_ENABLED = True
        logger.info("✅ Fallback: Service de sentiment local activé")
    except ImportError as e2:
        logger.error(f"Aucun service de sentiment disponible: {e2}")

# Sentiment asynchrone avec stubs
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
    logger.warning(f"Service d'analyse de sentiment asynchrone non disponible: {e}")
    async_sentiment_service = None

    def analyze_text_async(*args, **kwargs):
        return None

    def get_text_sentiment_cached(*args, **kwargs):
        return None

    def get_sentiment_analysis_status(*args, **kwargs):
        return None


# === Startup ===
@app.on_event("startup")
async def on_startup():
    if SCHEDULER_AVAILABLE and start_scheduler:
        try:
            start_scheduler()
            logger.info("Scheduler démarré.")
        except Exception as e:
            logger.error(f"Erreur du scheduler: {e}")
    else:
        logger.info("Scheduler non disponible ou non démarré.")


# === Routes ===
@app.get("/", tags=["health"])
def root():
    return {
        "message": "🏝️ API Veille Média Guadeloupe v2.1 - Cache intelligent activé !",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", tags=["health"])
def health():
    try:
        uptime = (datetime.utcnow() - start_time).total_seconds()
        status = {
            "mongo_connected": bool(mongo_client),
            "sentiment_gpt": globals().get("SENTIMENT_ENABLED", False),
            "async_sentiment": globals().get("ASYNC_SENTIMENT_ENABLED", False),
            "social_media": globals().get("SOCIAL_MEDIA_ENABLED", False),
            "scheduler": globals().get("SCHEDULER_AVAILABLE", False),
            "environment": globals().get("ENVIRONMENT", None),
            "uptime_seconds": uptime,
        }
        return {"status": status}
    except Exception:
        logger.exception("Erreur dans /health")
        raise


# === Global error handler ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Erreur non gérée: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur", "error": str(exc)},
    )