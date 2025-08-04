import os
import logging
import importlib
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# === Chargement de la configuration (.env local > parent) ===
_current_dir = os.path.dirname(__file__)
local_env = os.path.join(_current_dir, ".env")
parent_env = os.path.abspath(os.path.join(_current_dir, "..", ".env"))
if os.path.exists(local_env):
    load_dotenv(dotenv_path=local_env, override=True)
    print(f"Chargé .env local depuis {local_env}")
elif os.path.exists(parent_env):
    load_dotenv(dotenv_path=parent_env, override=True)
    print(f"Chargé .env parent depuis {parent_env}")
else:
    print("Aucun fichier .env trouvé ni local ni parent; les variables d'environnement doivent être exportées manuellement.")

# === Configuration ===
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
MONGO_URL = os.environ.get("MONGO_URL", "").strip()
VERSION = os.environ.get("VERSION", "dev")

# CORS : en production on exige une liste explicite (ex: ALLOWED_ORIGINS=https://example.com,https://foo.com)
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
if ENVIRONMENT == "production" and _allowed_origins_env.strip() in ("", "*"):
    raise RuntimeError("ALLOWED_ORIGINS doit être défini explicitement en production pour éviter CORS trop permissif")

if _allowed_origins_env.strip() == "*" and ENVIRONMENT != "production":
    ALLOWED_ORIGINS = ["*"]
else:
    ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("veille_media_backend")

# Log loaded .env context and mongo url (mask in prod)
if os.path.exists(local_env):
    logger.info(f"Chargé .env local depuis {local_env}")
elif os.path.exists(parent_env):
    logger.info(f"Chargé .env parent depuis {parent_env}")
else:
    logger.warning("Aucun fichier .env trouvé ni local ni parent; les variables d'environnement doivent être exportées manuellement.")

if ENVIRONMENT == "production":
    if MONGO_URL:
        logger.info("MONGO_URL défini (masqué en production)")
    else:
        logger.warning("MONGO_URL non défini en production")
else:
    logger.info(f"MONGO_URL après chargement .env: {MONGO_URL!r}")

# === Application ===
app = FastAPI()
START_TIME = datetime.utcnow()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === MongoDB ===

def get_mongo_client() -> Optional[MongoClient]:
    if not MONGO_URL:
        logger.warning("MONGO_URL non défini.")
        return None
    try:
        client = MongoClient(
            MONGO_URL,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
        )
        client.admin.command("ping")
        logger.info("✅ Connexion à MongoDB réussie.")
        return client
    except Exception as e:
        logger.error(f"Erreur de connexion MongoDB: {e}")
        return None

# Initialisation du client et de la DB
mongo_client: Optional[MongoClient] = get_mongo_client()
if ENVIRONMENT == "production" and not mongo_client:
    raise RuntimeError("Impossible de se connecter à MongoDB en production au démarrage.")

def get_db():
    if not mongo_client:
        raise RuntimeError("Client MongoDB non disponible")
    return mongo_client.get_default_database()

# === Import dynamique sécurisé ===

def safe_import(module: str, symbol: str):
    try:
        mod = importlib.import_module(module)
        return getattr(mod, symbol)
    except (ImportError, AttributeError) as e:
        logger.warning(f"Échec de l'import de {symbol} depuis {module}: {e}")
        return None

# === Services externes avec fallback ===
# Scraper
try:
    from .scraper_service import guadeloupe_scraper  # type: ignore
except ImportError as e:
    logger.warning(f"scraper_service non disponible: {e}")
    guadeloupe_scraper = None  # type: ignore

# Sentiment asynchrone
ASYNC_SENTIMENT_ENABLED = False
try:
    from .async_sentiment_service import (
        async_sentiment_service,
        analyze_text_async,
        get_text_sentiment_cached,
        get_sentiment_analysis_status,
    )  # type: ignore
    ASYNC_SENTIMENT_ENABLED = True
    logger.info("✅ Service d'analyse de sentiment asynchrone activé")
except ImportError as e:
    logger.warning(f"Service async sentiment non dispo: {e}")

    def analyze_text_async(*args, **kwargs):  # type: ignore
        return {"status": "unavailable"}

    def get_text_sentiment_cached(*args, **kwargs):  # type: ignore
        return None

    def get_sentiment_analysis_status(*args, **kwargs):  # type: ignore
        return {"status": "not_available"}

# === Inclusion des routeurs avec tolérance ===

def include_router_safely(module_path: str, attr_name: str, prefix: Optional[str] = None):
    try:
        if module_path.startswith('.'):
            module = importlib.import_module(module_path, package=__package__)
        else:
            module = importlib.import_module(module_path)
        router = getattr(module, attr_name)
        if prefix:
            app.include_router(router, prefix=prefix)
            logger.info(f"✅ {attr_name} inclus avec préfixe {prefix}")
        else:
            app.include_router(router)
            logger.info(f"✅ {attr_name} inclus")
    except Exception as e:
        logger.warning(f"Impossible d'inclure {attr_name} depuis {module_path}: {e}")

# inclusion explicite (préférer chemins absolus)
include_router_safely("backend.sentiment_routes", "router")
include_router_safely("backend.api_routes", "router", prefix="/api")
include_router_safely("backend.transcription_routes", "router", prefix="/api/transcriptions")

# === Routes de base ===
@app.get("/", tags=["health"])
def root():
    return {
        "message": f"🏝️ API Veille Média Guadeloupe v2.1 (env={ENVIRONMENT}, version={VERSION}) - Cache intelligent activé !",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/health", tags=["health"])
def health():
    uptime = (datetime.utcnow() - START_TIME).total_seconds()
    status = {
        "mongo_connected": bool(mongo_client),
        "async_sentiment": ASYNC_SENTIMENT_ENABLED,
        "environment": ENVIRONMENT,
        "version": VERSION,
        "uptime_seconds": uptime,
    }
    return {"status": status}

@app.get("/scrape/manual", tags=["scraping"])
def run_scraper():
    if not guadeloupe_scraper:
        raise HTTPException(status_code=500, detail="Scraper service non disponible")
    try:
        result = guadeloupe_scraper.run()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Erreur scraping: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors du scraping")

# === Fermeture propre ===
@app.on_event("shutdown")
def shutdown_event():
    if mongo_client:
        try:
            mongo_client.close()
            logger.info("✅ Connexion MongoDB fermée proprement.")
        except Exception:
            logger.warning("Échec lors de la fermeture de la connexion MongoDB.")

# === Gestion globale des erreurs ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Erreur non gérée: {exc}")
    if ENVIRONMENT == "production":
        return JSONResponse(
            status_code=500,
            content={"detail": "Erreur interne du serveur"},
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Erreur interne du serveur", "error": str(exc)},
        )