# backend/server.py

import os
import logging
import importlib
from datetime import datetime
from typing import Optional, Iterable

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
RUN_SCHEDULER = (os.environ.get("RUN_SCHEDULER", "1").strip() == "1")

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
def include_router_safely(module_candidates: Iterable[str], attr_name: str, prefix: Optional[str] = None):
    """
    Essaie plusieurs chemins de module (ex: ["backend.api_routes", "api_routes"])
    et inclut router si trouvé.
    """
    last_err: Optional[Exception] = None
    for module_path in module_candidates:
        try:
            module = importlib.import_module(module_path)
            router = getattr(module, attr_name)
            app.include_router(router, prefix=prefix or "")
            logger.info("✅ Router '%s' importé depuis %s %s",
                        attr_name, module_path, f"(prefix={prefix})" if prefix else "")
            return
        except Exception as e:
            last_err = e
    logger.warning("⚠️ Impossible d'inclure '%s' depuis %s : %s",
                   attr_name, list(module_candidates), last_err)

def route_registered(path: str) -> bool:
    for r in app.router.routes:
        if getattr(r, "path", None) == path:
            return True
    return False

# ======================
# Inclusion des routeurs (core)
# ======================
include_router_safely(["backend.api_routes", "api_routes"], "router", prefix="/api")
include_router_safely(["backend.sentiment_routes", "sentiment_routes"], "router", prefix="/api")
include_router_safely(["backend.digest_routes", "digest_routes"], "router")  # le fichier peut définir son propre prefix
include_router_safely(["backend.analytics_routes", "analytics_routes"], "router")
include_router_safely(["backend.social_routes", "social_routes"], "router", prefix="/api/social")

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
# Routeurs additionnels (radio cards, PDF, scheduler)
# ======================

# Radio cards (encarts pour transcriptions)
include_router_safely(
    ["backend.radio_cards_routes", "radio_cards_routes"],
    "router",
    prefix="/api"  # les endpoints commencent en général par /radio/...
)

# PDF digest (expose /api/digest/pdf/...)
include_router_safely(
    ["backend.pdf_routes", "pdf_routes"],
    "router"
)

# Scheduler admin (/api/scheduler/…)
include_router_safely(
    ["backend.scheduler_service", "scheduler_service"],
    "router",
    prefix="/api/scheduler"
)

# ======================
# Scraper optionnel
# ======================
try:
    # si démarré via `uvicorn backend.server:app`, l'import relatif suffit
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
# Startup / Shutdown : Scheduler attach/detach
# ======================
_scheduler_attached = False

@app.on_event("startup")
def _on_startup():
    global _scheduler_attached
    if not RUN_SCHEDULER:
        logger.info("⏸️ RUN_SCHEDULER=0 → scheduler désactivé (pas d'attache)")
        return
    try:
        try:
            # import robuste
            from backend.scheduler_service import attach_scheduler  # type: ignore
        except Exception:
            from scheduler_service import attach_scheduler  # type: ignore

        attach_scheduler(app)
        _scheduler_attached = True
        logger.info("🗓️ Scheduler attaché au démarrage")
    except Exception as e:
        logger.warning("⚠️ Impossible d'attacher le scheduler: %s", e)

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
# Shutdown & erreurs
# ======================
@app.on_event("shutdown")
def shutdown_event():
    # stop scheduler proprement
    if _scheduler_attached:
        try:
            try:
                from backend.scheduler_service import stop_scheduler  # type: ignore
            except Exception:
                from scheduler_service import stop_scheduler  # type: ignore
            stop_scheduler(app)
            logger.info("🛑 Scheduler arrêté proprement.")
        except Exception as e:
            logger.warning("⚠️ Arrêt du scheduler: %s", e)

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
