# backend/server.py

import os
import logging
import importlib
from datetime import datetime
from typing import Optional, Iterable, Union

from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# =====================================================================
# Chargement .env (en dev uniquement : Render fournit les vars en prod)
# =====================================================================
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
if ENVIRONMENT != "production":
    _CURRENT_DIR = os.path.dirname(__file__)
    LOCAL_ENV = os.path.join(_CURRENT_DIR, ".env")
    PARENT_ENV = os.path.abspath(os.path.join(_CURRENT_DIR, "..", ".env"))
    if os.path.exists(LOCAL_ENV):
        load_dotenv(dotenv_path=LOCAL_ENV, override=True)
    elif os.path.exists(PARENT_ENV):
        load_dotenv(dotenv_path=PARENT_ENV, override=True)

# ==================
# Variables d'env
# ==================
VERSION = os.environ.get("VERSION", "dev")
MONGO_URL = os.environ.get("MONGO_URL", "").strip()
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "").strip()

def _split_list(v: str) -> list[str]:
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()]

_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*").strip()
if ENVIRONMENT == "production" and _allowed_origins_env in ("", "*"):
    raise RuntimeError("ALLOWED_ORIGINS doit être défini explicitement en production")

ALLOWED_ORIGINS = (
    ["*"]
    if (_allowed_origins_env == "*" and ENVIRONMENT != "production")
    else _split_list(_allowed_origins_env)
)

# =========
# Logging
# =========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("veille_media_backend")
logger.info("🔧 Lancement backend (env=%s, version=%s)", ENVIRONMENT, VERSION)
logger.info("CORS allow_origins=%s", ALLOWED_ORIGINS)

# =========
# FastAPI
# =========
app = FastAPI(title="Veille Média Guadeloupe API", version=VERSION)
START_TIME = datetime.utcnow()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# Connexion MongoDB
# ======================
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
        logger.error("Erreur connexion MongoDB: %s", e)
        return None

mongo_client: Optional[MongoClient] = get_mongo_client()
if ENVIRONMENT == "production" and not mongo_client:
    raise RuntimeError("Impossible de se connecter à MongoDB en production")

def get_db():
    if not mongo_client:
        raise RuntimeError("Client MongoDB non disponible")
    return mongo_client[MONGO_DB_NAME] if MONGO_DB_NAME else mongo_client.get_default_database()

# ======================
# Helpers d'import
# ======================
def include_router_safely(
    module_candidates: Union[str, Iterable[str]],
    attr_name: str,
    prefix: Optional[str] = None,
) -> bool:
    """
    Essaie un ou plusieurs chemins de module (ex: "backend.api_routes" ou ["backend.api_routes","api_routes"])
    et inclut le router si trouvé.
    """
    candidates = [module_candidates] if isinstance(module_candidates, (str, bytes)) else list(module_candidates)
    last_err: Optional[Exception] = None
    for module_path in candidates:
        try:
            module = importlib.import_module(module_path)
            router = getattr(module, attr_name)
            app.include_router(router, prefix=prefix or "")
            logger.info(
                "✅ Router '%s' importé depuis %s %s",
                attr_name, module_path, f"(prefix={prefix})" if prefix else ""
            )
            return True
        except Exception as e:
            last_err = e
            logger.warning("⚠️ Échec import %s depuis %s : %s", attr_name, module_path, e)

    logger.warning("⚠️ Impossible d'inclure '%s' depuis %s : %s", attr_name, candidates, last_err)
    return False

def route_registered(path: str) -> bool:
    for r in app.router.routes:
        if getattr(r, "path", None) == path:
            return True
    return False

# ======================
# Inclusion des routeurs métiers
# ======================
include_router_safely(["backend.auth_routes", "auth_routes"], "router", prefix="/api")
include_router_safely(["backend.api_routes", "api_routes"], "router", prefix="/api")
include_router_safely(["backend.sentiment_routes", "sentiment_routes"], "router", prefix="/api")
include_router_safely(["backend.digest_routes", "digest_routes"], "router", prefix="/api")
include_router_safely(["backend.analytics_routes", "analytics_routes"], "router", prefix="/api")
include_router_safely(["backend.social_routes", "social_routes"], "router", prefix="/api/social")
include_router_safely(["backend.telegram_routes", "telegram_routes"], "router", prefix="/api")  # 👈 Telegram

# ======================
# Scheduler (détaillé) – router + attach au startup
# ======================
try:
    from backend.scheduler_service import router as scheduler_router, attach_scheduler
    app.include_router(scheduler_router, prefix="/api/scheduler")
    logger.info("✅ Router scheduler inclus (prefix=/api/scheduler)")
except Exception as e:
    logger.warning("⚠️ scheduler_service indisponible: %s", e)
    attach_scheduler = None  # type: ignore

# --- Transcriptions : accepte module avec ou sans prefix interne
_transcription_router = None
try:
    from backend.transcription_routes import router as _transcription_router  # type: ignore
except Exception:
    try:
        from transcription_routes import router as _transcription_router  # type: ignore
    except Exception as e:
        logger.warning("⚠️ transcription_routes introuvable: %s", e)

if _transcription_router:
    internal_prefix = getattr(_transcription_router, "prefix", "") or ""
    if internal_prefix.startswith("/api/transcriptions"):
        app.include_router(_transcription_router)
        logger.info("✅ transcription_routes inclus (prefix interne: %s)", internal_prefix)
    else:
        app.include_router(_transcription_router, prefix="/api/transcriptions")
        logger.info("✅ transcription_routes inclus sous /api/transcriptions (prefix interne: %s)", internal_prefix or "<none>")
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
                "global_status": {"any_in_progress": False, "total_sections": 0, "active_sections": 0},
            },
        }

    @app.post("/api/transcriptions/capture-now", tags=["mock"])
    def _mock_capture_now(section: str = "", duration: int = 0):
        raise HTTPException(status_code=503, detail="transcription_routes non chargé")

# ======================
# Fallbacks utiles si routers absents (compat front)
# ======================
if not route_registered("/api/analytics/articles-by-source"):
    @app.get("/api/analytics/articles-by-source", tags=["analytics"])
    async def analytics_articles_by_source():
        payload = {"labels": ["France-Antilles", "RCI", "La 1ère", "KaribInfo"], "series": [12, 9, 7, 4]}
        return {"success": True, **payload, "data": payload}

if not route_registered("/api/analytics/articles-timeline"):
    @app.get("/api/analytics/articles-timeline", tags=["analytics"])
    async def analytics_articles_timeline():
        payload = {
            "labels": ["2025-08-10", "2025-08-11", "2025-08-12", "2025-08-13", "2025-08-14", "2025-08-15", "2025-08-16"],
            "series": [5, 7, 6, 9, 8, 10, 11],
        }
        return {"success": True, **payload, "data": payload}

if not route_registered("/api/analytics/sentiment-by-source"):
    @app.get("/api/analytics/sentiment-by-source", tags=["analytics"])
    async def analytics_sentiment_by_source():
        payload = {
            "labels": ["France-Antilles", "RCI", "La 1ère", "KaribInfo"],
            "positive": [6, 5, 3, 2],
            "neutral": [4, 3, 3, 1],
            "negative": [2, 1, 1, 1],
        }
        return {"success": True, **payload, "data": payload}

if not route_registered("/api/analytics/dashboard-metrics"):
    @app.get("/api/analytics/dashboard-metrics", tags=["analytics"])
    async def analytics_dashboard_metrics():
        return {
            "success": True,
            "totals": {"articles": 32, "sources": 4, "comments": 18},
            "last_updated": datetime.utcnow().isoformat() + "Z",
        }

# Sources & articles (placeholders)
if not route_registered("/api/articles/sources"):
    @app.get("/api/articles/sources", tags=["articles"])
    async def articles_sources():
        return {"success": True, "sources": ["France-Antilles", "RCI", "La 1ère", "KaribInfo"]}

if not route_registered("/api/articles"):
    @app.get("/api/articles", tags=["articles"])
    async def articles_list():
        return {"success": True, "articles": []}

if not route_registered("/api/search"):
    @app.get("/api/search", tags=["search"])
    async def search(q: str = ""):
        return {"success": True, "query": q, "results": []}

if not route_registered("/api/search/suggestions"):
    @app.get("/api/search/suggestions", tags=["search"])
    async def search_suggestions(q: str = ""):
        return {"success": True, "query": q, "suggestions": []}

# ======================
# Scraper optionnel
# ======================
try:
    from .scraper_service import guadeloupe_scraper  # type: ignore
except Exception:
    try:
        from backend.scraper_service import guadeloupe_scraper  # type: ignore
    except Exception as e:
        logger.warning("⚠️ scraper_service non disponible: %s", e)
        guadeloupe_scraper = None  # type: ignore

@app.post("/api/articles/scrape-now", tags=["scraping"])
def scrape_now(payload: dict = Body(default={})):
    if not guadeloupe_scraper:
        raise HTTPException(status_code=500, detail="Scraper service non disponible")
    try:
        result = guadeloupe_scraper.run()
        return {"success": True, "message": "Scraping lancé", "result": result}
    except Exception as e:
        logger.error("Erreur scraping: %s", e)
        raise HTTPException(status_code=500, detail="Erreur interne lors du scraping")

@app.get("/api/articles/scrape-status", tags=["scraping"])
def scrape_status():
    return {"success": True, "result": {"success": None, "progress": "running"}}

# ======================
# Health & root
# ======================
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

# ======================
# Startup / Shutdown / erreurs
# ======================
@app.on_event("startup")
async def _on_startup():
    # Démarre le scheduler détaillé si présent
    if callable(globals().get("attach_scheduler")):
        try:
            attach_scheduler(app)  # type: ignore
        except Exception as e:
            logger.warning("⚠️ attach_scheduler a échoué: %s", e)

@app.on_event("shutdown")
def shutdown_event():
    if mongo_client:
        try:
            mongo_client.close()
            logger.info("✅ Connexion MongoDB fermée proprement.")
        except Exception:
            logger.warning("Échec fermeture MongoDB")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Erreur non gérée: %s", exc)
    if ENVIRONMENT == "production":
        return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur", "error": str(exc)})
