# backend/server.py

import os
import logging
import importlib
from datetime import datetime
from typing import Optional
# en haut, avec les imports

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# === Chargement .env (local d'abord, sinon parent) ===
if os.getenv("ENVIRONMENT", "development") != "production":
    # Dev : charge depuis .env local
    _CURRENT_DIR = os.path.dirname(__file__)
    LOCAL_ENV = os.path.join(_CURRENT_DIR, ".env")
    PARENT_ENV = os.path.abspath(os.path.join(_CURRENT_DIR, "..", ".env"))
    if os.path.exists(LOCAL_ENV):
        load_dotenv(dotenv_path=LOCAL_ENV, override=True)
    elif os.path.exists(PARENT_ENV):
        load_dotenv(dotenv_path=PARENT_ENV, override=True)

# Ensuite récupère tes variables normalement
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
# === Config de base ===
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
VERSION = os.environ.get("VERSION", "dev")
MONGO_URL = os.environ.get("MONGO_URL", "").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "").strip()

_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
if ENVIRONMENT == "production" and _allowed_origins_env.strip() in ("", "*"):
    raise RuntimeError("ALLOWED_ORIGINS doit être défini explicitement en production")
ALLOWED_ORIGINS = ["*"] if (_allowed_origins_env.strip() == "*" and ENVIRONMENT != "production") else [
    o.strip() for o in _allowed_origins_env.split(",") if o.strip()
]

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("veille_media_backend")
logger.info("🔧 Lancement backend (env=%s, version=%s)", ENVIRONMENT, VERSION)
logger.info("CORS: %s", ALLOWED_ORIGINS)

# === App FastAPI (UNE SEULE INSTANCE) ===
app = FastAPI(title="Veille Média Guadeloupe API", version=VERSION)
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
            serverSelectionTimeoutMS=20000,
        )
        client.admin.command("ping")
        logger.info("✅ Connexion à MongoDB OK")
        return client
    except Exception as e:
        logger.error(f"Erreur connexion MongoDB: {e}")
        return None

mongo_client: Optional[MongoClient] = get_mongo_client()
if ENVIRONMENT == "production" and not mongo_client:
    raise RuntimeError("Impossible de se connecter à MongoDB en production")

def get_db():
    if not mongo_client:
        raise RuntimeError("Client MongoDB non disponible")
    if MONGO_DB_NAME:
        return mongo_client[MONGO_DB_NAME]
    return mongo_client.get_default_database()

# === Import sécurisé de routeurs ===
def include_router_safely(module_path: str, attr_name: str, prefix: Optional[str] = None):
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, attr_name)
        app.include_router(router, prefix=prefix or "")
        logger.info("✅ Router %s depuis %s %s",
                    attr_name, module_path, f"avec prefix {prefix}" if prefix else "")
    except Exception as e:
        logger.warning("⚠️ Impossible d'inclure %s depuis %s: %s", attr_name, module_path, e)

# Inclure les routeurs applicatifs avec les bons préfixes
# - api_routes doit vivre sous /api
# - sentiment_routes aussi sous /api (il expose /sentiment/...)
# - transcription_routes si tu l'as, sous /api/transcriptions (ou /api selon ton fichier)
include_router_safely("backend.api_routes", "router", prefix="/api")
include_router_safely("backend.sentiment_routes", "router", prefix="/api")
include_router_safely("backend.digest_routes", "router")
include_router_safely("backend.analytics_routes", "router")

# --- Fallback /api/analytics/* endpoints if analytics router isn't available ---
def _route_registered(path: str) -> bool:
    for r in app.router.routes:
        if getattr(r, "path", None) == path:
            return True
    return False

if not _route_registered("/api/analytics/articles-by-source"):
    from datetime import datetime as _dt  # alias to avoid shadowing

    @app.get("/api/analytics/articles-by-source", tags=["analytics"])
    async def analytics_articles_by_source():
        payload = {
            "labels": [
                "France-Antilles Guadeloupe",
                "RCI Guadeloupe",
                "La 1ère Guadeloupe",
                "KaribInfo",
            ],
            "series": [12, 9, 7, 4],
        }
        return {"success": True, **payload, "data": payload}

    @app.get("/api/analytics/articles-timeline", tags=["analytics"])
    async def analytics_articles_timeline():
        payload = {
            "labels": [
                "2025-08-10",
                "2025-08-11",
                "2025-08-12",
                "2025-08-13",
                "2025-08-14",
                "2025-08-15",
                "2025-08-16",
            ],
            "series": [5, 7, 6, 9, 8, 10, 11],
        }
        return {"success": True, **payload, "data": payload}

    @app.get("/api/analytics/sentiment-by-source", tags=["analytics"])
    async def analytics_sentiment_by_source():
        payload = {
            "labels": [
                "France-Antilles Guadeloupe",
                "RCI Guadeloupe",
                "La 1ère Guadeloupe",
                "KaribInfo",
            ],
            "positive": [6, 5, 3, 2],
            "neutral": [4, 3, 3, 1],
            "negative": [2, 1, 1, 1],
        }
        return {"success": True, **payload, "data": payload}

    @app.get("/api/analytics/dashboard-metrics", tags=["analytics"])
    async def analytics_dashboard_metrics():
        payload = {
            "totals": {"articles": 32, "sources": 4, "comments": 18},
            "last_updated": _dt.utcnow().isoformat() + "Z",
        }
        return {"success": True, **payload, "data": payload}

include_router_safely("backend.social_routes", "router", prefix="/api/social")

# --- Transcription routes (robuste: import package ou module local) ---
try:
    from backend.transcription_routes import router as transcription_router  # type: ignore
except Exception:
    try:
        from transcription_routes import router as transcription_router  # type: ignore
    except Exception as e:
        transcription_router = None  # type: ignore
        logger.warning("⚠️ transcription_routes introuvable: %s", e)

if transcription_router:
    # Évite le double préfixe si le router a déjà un prefix interne
    internal_prefix = getattr(transcription_router, "prefix", "") or ""
    if internal_prefix.startswith("/api/transcriptions"):
        app.include_router(transcription_router)  # déjà préfixé dans le module
        logger.info("✅ transcription_routes inclus (prefix interne: %s)", internal_prefix)
    else:
        app.include_router(transcription_router, prefix="/api/transcriptions")
        logger.info(
            "✅ transcription_routes inclus sous /api/transcriptions (prefix interne: %s)",
            internal_prefix or "<none>",
        )
else:
    logger.warning("⚠️ Ajout des endpoints mock /api/transcriptions/* (transcription_routes non chargé)")

    @app.get("/api/transcriptions/sections", tags=["mock"])
    def _mock_sections():
        return {"success": True, "sections": {}}

    @app.get("/api/transcriptions/status", tags=["mock"])
    def _mock_status():
        return {
            "success": True,
            "status": {
                "sections": {},
                "global_status": {
                    "any_in_progress": False,
                    "total_sections": 0,
                    "active_sections": 0,
                },
            },
        }

    @app.post("/api/transcriptions/capture-now", tags=["mock"])
    def _mock_capture_now(section: str = "", duration: int = 0):
        raise HTTPException(status_code=503, detail="transcription_routes non chargé")

# === Services optionnels (scraper) ===
try:
    from .scraper_service import guadeloupe_scraper  # type: ignore
except Exception as e:
    logger.warning("⚠️ scraper_service non disponible: %s", e)
    guadeloupe_scraper = None  # type: ignore

# === Health / Root ===
@app.get("/", tags=["health"])
def root():
    return {
        "message": f"🏝️ API Veille Média Guadeloupe (env={ENVIRONMENT}, version={VERSION})",
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/health", tags=["health"])
def health():
    uptime = (datetime.utcnow() - START_TIME).total_seconds()
    return {
        "status": {
            "mongo_connected": bool(mongo_client),
            "environment": ENVIRONMENT,
            "version": VERSION,
            "uptime_seconds": uptime,
        }
    }

# === Scraping (aligné au front) ===
@app.post("/api/articles/scrape-now", tags=["scraping"])
def scrape_now(payload: dict = Body(default={})):
    if not guadeloupe_scraper:
        raise HTTPException(status_code=500, detail="Scraper service non disponible")
    try:
        result = guadeloupe_scraper.run()
        return {"success": True, "message": "Scraping lancé", "result": result}
    except Exception as e:
        logger.error(f"Erreur scraping: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne lors du scraping")

@app.get("/api/articles/scrape-status", tags=["scraping"])
def scrape_status():
    # Placeholder simple pour éviter 404 côté front
    return {"success": True, "result": {"success": None, "progress": "running"}}

# === Shutdown propre ===
@app.on_event("shutdown")
def shutdown_event():
    if mongo_client:
        try:
            mongo_client.close()
            logger.info("✅ Connexion MongoDB fermée proprement.")
        except Exception:
            logger.warning("Échec fermeture MongoDB")

# === Gestion globale des erreurs ===
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Erreur non gérée: %s", exc)
    if ENVIRONMENT == "production":
        return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur", "error": str(exc)})
