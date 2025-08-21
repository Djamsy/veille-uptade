# backend/scheduler_service.py
"""
Scheduler central (APScheduler) pour la Veille Média
- Scraping : toutes les heures (minute=0)
- Capture radio : 7h locales
- Digest : 12h locales
- Nettoyage cache : 2h locales
- Endpoints d'admin : /api/scheduler/status, /api/scheduler/run-job/{job_id}
- Garde anti-chevauchement + démarrage unique
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job
import asyncio

from pymongo import MongoClient
import certifi

logger = logging.getLogger("scheduler_service")
logger.setLevel(logging.INFO)

# ---- Config de base ----
TIMEZONE = os.environ.get("TIMEZONE", "UTC")
RUN_SCHEDULER = os.environ.get("RUN_SCHEDULER", "1") == "1"
MONGO_URL = os.environ.get("MONGO_URL", "").strip() or "mongodb://localhost:27017"

# Connexion Mongo (pour logs + gardes DB)
def _get_db():
    try:
        client = MongoClient(MONGO_URL, tlsCAFile=certifi.where()) if MONGO_URL.startswith("mongodb+srv") else MongoClient(MONGO_URL)
        client.admin.command("ping")
        return client.get_default_database() or client["veille_media"]
    except Exception as e:
        logger.warning(f"Mongo non disponible pour le scheduler: {e}")
        return None

_db = _get_db()
_logs = _db.scheduler_logs if _db else None
_transcriptions = _db.radio_transcriptions if _db else None

# ---- État & Locks ----
_scheduler: Optional[AsyncIOScheduler] = None
_started_flag: bool = False

_scrape_lock = asyncio.Lock()
_capture_lock = asyncio.Lock()
_digest_lock = asyncio.Lock()
_cache_lock = asyncio.Lock()

# ---- Utils ----
def _log_job(job_name: str, success: bool, details: str = ""):
    entry = {
        "job_name": job_name,
        "success": success,
        "details": details,
        "timestamp": datetime.utcnow().isoformat(),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    if _logs := _logs:
        try:
            _logs.insert_one(entry)
        except Exception:
            pass
    (logger.info if success else logger.error)(f"[{job_name}] {'OK' if success else 'KO'} - {details}")

def _lazy_imports():
    """Import paresseux des services pour éviter les imports au chargement module (et reloader)."""
    scraper = radio = summary = None
    try:
        from backend.scraper_service import guadeloupe_scraper as scraper  # type: ignore
    except Exception as e:
        logger.warning(f"Scraper service indisponible: {e}")
    try:
        # Si tu utilises encore radio_service classique :
        from backend.radio_service import radio_service as radio  # type: ignore
    except Exception:
        radio = None
    try:
        from backend.summary_service import summary_service as summary  # type: ignore
    except Exception:
        summary = None
    return scraper, radio, summary

def _is_recent_capture_in_progress(max_age_min: int = 15) -> bool:
    """Garde DB : existe-t-il une capture radio 'in_progress' récente ?"""
    if not _transcriptions:
        return False
    try:
        since = (datetime.utcnow() - timedelta(minutes=max_age_min)).isoformat()
        found = _transcriptions.find_one({"status": "in_progress", "captured_at": {"$gte": since}})
        return bool(found)
    except Exception:
        return False

# ---- Jobs ----
async def job_scrape_articles():
    if _scrape_lock.locked():
        logger.info("⏭️ Scrape ignoré (lock actif)")
        return
    async with _scrape_lock:
        scraper, _, _ = _lazy_imports()
        if not scraper or not hasattr(scraper, "scrape_all_sites"):
            _log_job("scrape_articles", False, "Service scraper non disponible")
            return
        try:
            logger.info("🚀 Scrape articles (horaire)")
            # appel potentiellement bloquant => exécuter en thread
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, scraper.scrape_all_sites)
            if result and result.get("success"):
                details = f"{result.get('total_articles', 0)} articles | {result.get('sites_scraped', 0)} sites"
                _log_job("scrape_articles", True, details)
            else:
                _log_job("scrape_articles", False, f"Réponse invalide: {result}")
        except Exception as e:
            _log_job("scrape_articles", False, str(e))

async def job_capture_radio():
    if _capture_lock.locked():
        logger.info("⏭️ Capture ignorée (lock actif)")
        return
    # garde DB pour éviter chevauchement cross-process
    if _is_recent_capture_in_progress():
        logger.info("⏭️ Capture ignorée (déjà en cours selon DB)")
        return
    async with _capture_lock:
        _, radio, _ = _lazy_imports()
        # Si tu as migré vers des routes de capture, appelle-les ici (via fonction interne) au lieu de radio_service
        if not radio or not hasattr(radio, "capture_all_streams"):
            _log_job("capture_radio", False, "Service radio non disponible")
            return
        try:
            logger.info("🎙️ Capture radio planifiée (7h)")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, radio.capture_all_streams)
            if result and result.get("success"):
                details = f"{result.get('streams_success', 0)}/{result.get('streams_processed', 0)} flux"
                _log_job("capture_radio", True, details)
            else:
                _log_job("capture_radio", False, f"Réponse invalide: {result}")
        except Exception as e:
            _log_job("capture_radio", False, str(e))

async def job_create_daily_digest():
    if _digest_lock.locked():
        logger.info("⏭️ Digest ignoré (lock actif)")
        return
    async with _digest_lock:
        scraper, radio, summary = _lazy_imports()
        if not (scraper and radio and summary):
            _log_job("create_digest", False, "Services requis indisponibles")
            return
        try:
            logger.info("📰 Création digest (12h)")
            loop = asyncio.get_running_loop()
            articles = await loop.run_in_executor(None, getattr(scraper, "get_todays_articles", lambda: []) )
            trans = await loop.run_in_executor(None, getattr(radio, "get_todays_transcriptions", lambda: []) )
            digest_html = await loop.run_in_executor(None, lambda: summary.create_daily_digest(articles, trans))
            if _db:
                _db.daily_digests.update_one(
                    {"id": f"digest_{datetime.utcnow().strftime('%Y%m%d')}"},
                    {"$set": {
                        "date": datetime.utcnow().strftime("%Y-%m-%d"),
                        "digest_html": digest_html,
                        "articles_count": len(articles),
                        "transcriptions_count": len(trans),
                        "created_at": datetime.utcnow().isoformat(),
                    }},
                    upsert=True
                )
            _log_job("create_digest", True, f"{len(articles)} articles / {len(trans)} transcriptions")
        except Exception as e:
            _log_job("create_digest", False, str(e))

async def job_clean_cache_24h():
    if _cache_lock.locked():
        logger.info("⏭️ Nettoyage cache ignoré (lock actif)")
        return
    async with _cache_lock:
        try:
            logger.info("🧹 Nettoyage cache (2h)")
            # import paresseux
            try:
                from backend.cache_service import intelligent_cache  # type: ignore
            except Exception as e:
                _log_job("clean_cache_24h", False, f"cache_service indisponible: {e}")
                return
            loop = asyncio.get_running_loop()
            cleaned = await loop.run_in_executor(None, intelligent_cache.cleanup_expired_cache)
            _log_job("clean_cache_24h", True, f"{cleaned} entrées expirées supprimées")
        except Exception as e:
            _log_job("clean_cache_24h", False, str(e))

# ---- Création / attache du scheduler ----
def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler, _started_flag
    if _scheduler:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone=TIMEZONE, job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 60,
    })
    # Jobs (cron en TZ configurée)
    _scheduler.add_job(job_scrape_articles, CronTrigger(minute=0), id="scrape_articles", replace_existing=True)
    _scheduler.add_job(job_capture_radio,  CronTrigger(hour=1, minute=0), id="capture_radio", replace_existing=True)
    _scheduler.add_job(job_create_daily_digest, CronTrigger(hour=12, minute=0), id="create_digest", replace_existing=True)
    _scheduler.add_job(job_clean_cache_24h, CronTrigger(hour=2, minute=0), id="clean_cache_24h", replace_existing=True)
    return _scheduler

def attach_scheduler(app) -> None:
    """
    Appelé depuis server.py (on_startup) pour démarrer UNE SEULE instance.
    """
    global _started_flag
    if not RUN_SCHEDULER:
        logger.info("⏸️ RUN_SCHEDULER=0 → scheduler désactivé")
        return
    if getattr(app.state, "scheduler_started", False):
        logger.info("↩️ Scheduler déjà attaché")
        return
    sched = _ensure_scheduler()
    if not sched.running:
        sched.start()
        logger.info("✅ Scheduler démarré")
    app.state.scheduler = sched
    app.state.scheduler_started = True

def stop_scheduler(app=None) -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler arrêté")
    if app is not None:
        app.state.scheduler_started = False

# ---- API Router (admin) ----
router = APIRouter()

def _job_info(j: Job) -> Dict[str, Any]:
    return {
        "id": j.id,
        "name": j.name,
        "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
        "trigger": str(j.trigger),
    }

@router.get("/status", tags=["scheduler"])
def scheduler_status():
    sched = _ensure_scheduler()
    jobs = [_job_info(j) for j in sched.get_jobs()]
    return {"running": sched.running, "timezone": TIMEZONE, "jobs": jobs}

@router.post("/run-job/{job_id}", tags=["scheduler"])
async def run_job(job_id: str):
    job_map = {
        "scrape_articles": job_scrape_articles,
        "capture_radio": job_capture_radio,
        "create_digest": job_create_daily_digest,
        "clean_cache_24h": job_clean_cache_24h,
    }
    func = job_map.get(job_id)
    if not func:
        raise HTTPException(status_code=404, detail=f"Job inconnu: {job_id}")
    await func()
    return {"success": True, "message": f"Job {job_id} exécuté"}

@router.post("/toggle", tags=["scheduler"])
def toggle(enable: bool):
    sched = _ensure_scheduler()
    if enable:
        if not sched.running:
            sched.start()
            logger.info("▶️ Scheduler relancé via /toggle")
    else:
        if sched.running:
            sched.shutdown(wait=False)
            logger.info("⏹️ Scheduler stoppé via /toggle")
    return {"running": sched.running}
