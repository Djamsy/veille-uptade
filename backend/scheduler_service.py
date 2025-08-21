# backend/scheduler_service.py
"""
Scheduler central (APScheduler) pour la Veille Média
- Scraping : toutes les heures (minute=0)
- Radio/TV : vérif des créneaux "due now" TOUTES LES MINUTES (heure locale)
- Digest : 12h locales
- Nettoyage cache : 2h locales
- Endpoints d'admin : /api/scheduler/status, /api/scheduler/next, /api/scheduler/run-job/{job_id}, /api/scheduler/toggle
- Verrous anti-chevauchement + démarrage unique + logs Mongo
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job

from pymongo import MongoClient
from pymongo.errors import ConfigurationError
import certifi

logger = logging.getLogger("scheduler_service")
logger.setLevel(logging.INFO)

# =========================
# Config & Fuseau horaire
# =========================
TIMEZONE_NAME = (os.environ.get("TIMEZONE") or "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TZ = ZoneInfo("UTC")
    TIMEZONE_NAME = "UTC"
    logger.warning("⚠️ TIMEZONE invalide, fallback UTC")

RUN_SCHEDULER = (os.environ.get("RUN_SCHEDULER") or "1").strip() == "1"
MONGO_URL = (os.environ.get("MONGO_URL") or "mongodb://localhost:27017").strip()

# =========================
# Connexion Mongo (logs)
# =========================
def _get_db():
    try:
        if MONGO_URL.startswith("mongodb+srv"):
            client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=20000)
        else:
            client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)
        client.admin.command("ping")
        try:
            db = client.get_default_database()
        except ConfigurationError:
            db = None
        return db if db is not None else client["veille_media"]
    except Exception as e:
        logger.warning(f"Mongo non disponible pour le scheduler: {e}")
        return None

_db = _get_db()
_logs_col = _db["scheduler_logs"] if _db is not None else None

# =========================
# État & Locks
# =========================
_scheduler: Optional[AsyncIOScheduler] = None

_scrape_lock = asyncio.Lock()
_radio_due_lock = asyncio.Lock()
_digest_lock = asyncio.Lock()
_cache_lock = asyncio.Lock()

# =========================
# Utils
# =========================
def _log_job(job_name: str, success: bool, details: str = ""):
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_local = now_utc.astimezone(TZ)
    entry = {
        "job_name": job_name,
        "success": success,
        "details": details,
        "timestamp_utc": now_utc.isoformat(),
        "timestamp_local": now_local.isoformat(),
        "date_utc": now_utc.strftime("%Y-%m-%d"),
        "date_local": now_local.strftime("%Y-%m-%d"),
        "timezone": TIMEZONE_NAME,
    }
    if _logs_col is not None:
        try:
            _logs_col.insert_one(entry)
        except Exception:
            pass
    (logger.info if success else logger.error)(
        f"[{job_name}] {'OK' if success else 'KO'} - {details} "
        f"(utc={entry['timestamp_utc']}, local={entry['timestamp_local']})"
    )

def _lazy_imports():
    """Import paresseux pour éviter les cycles et accélérer le boot."""
    scraper = radio = summary = None
    try:
        from backend.scraper_service import guadeloupe_scraper as scraper  # type: ignore
    except Exception as e:
        logger.warning(f"Scraper service indisponible: {e}")
    try:
        from backend.radio_service import radio_service as radio  # type: ignore
    except Exception as e:
        logger.warning(f"Radio service indisponible: {e}")
    try:
        from backend.summary_service import summary_service as summary  # type: ignore
    except Exception as e:
        logger.warning(f"Summary service indisponible: {e}")
    return scraper, radio, summary

# =========================
# Jobs
# =========================
async def job_scrape_articles():
    if _scrape_lock.locked():
        logger.info("⏭️ Scrape ignoré (lock actif)")
        return
    async with _scrape_lock:
        scraper, _, _ = _lazy_imports()
        if scraper is None or not hasattr(scraper, "scrape_all_sites"):
            _log_job("scrape_articles", False, "Service scraper non disponible")
            return
        try:
            logger.info("🚀 Scrape articles (horaire)")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, scraper.scrape_all_sites)
            if result and result.get("success"):
                details = f"{result.get('total_articles', 0)} articles | {result.get('sites_scraped', 0)} sites"
                _log_job("scrape_articles", True, details)
            else:
                _log_job("scrape_articles", False, f"Réponse invalide: {result}")
        except Exception as e:
            _log_job("scrape_articles", False, str(e))

async def job_radio_due_minutely():
    """
    Appelé TOUTES LES MINUTES en heure locale.
    Le radio_service s'occupe de :
      - convertir UTC -> local
      - vérifier quels flux sont 'due now'
      - dédupliquer par minute
    """
    if _radio_due_lock.locked():
        logger.info("⏭️ Radio due ignoré (lock actif)")
        return
    async with _radio_due_lock:
        _, radio, _ = _lazy_imports()
        if radio is None or not hasattr(radio, "capture_due_streams"):
            _log_job("radio_due_minutely", False, "radio_service.capture_due_streams indisponible")
            return
        try:
            logger.info("📻 Vérification des créneaux Radio/TV (minutely)")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, radio.capture_due_streams)
            details = f"due={len(result.get('due', []))} ran={len(result.get('ran', []))} errors={len(result.get('errors', []))}"
            ok = len(result.get("errors", [])) == 0
            _log_job("radio_due_minutely", ok, details)
        except Exception as e:
            _log_job("radio_due_minutely", False, str(e))

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
            articles = await loop.run_in_executor(None, getattr(scraper, "get_todays_articles", lambda: []))
            trans = await loop.run_in_executor(None, getattr(radio, "get_todays_transcriptions", lambda: []))
            digest_html = await loop.run_in_executor(None, lambda: summary.create_daily_digest(articles, trans))
            if _db is not None:
                _db["daily_digests"].update_one(
                    {"id": f"digest_{datetime.now(ZoneInfo('UTC')).strftime('%Y%m%d')}"},
                    {"$set": {
                        "date": datetime.now(TZ).strftime("%Y-%m-%d"),
                        "digest_html": digest_html,
                        "articles_count": len(articles),
                        "transcriptions_count": len(trans),
                        "created_at": datetime.now(ZoneInfo("UTC")).isoformat(),
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

# =========================
# Création / attache scheduler
# =========================
def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(
        timezone=TZ,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
    )

    # CRON en heure locale (TZ)
    _scheduler.add_job(job_scrape_articles,     CronTrigger(minute=0,               timezone=TZ), id="scrape_articles",    replace_existing=True)
    _scheduler.add_job(job_radio_due_minutely,  CronTrigger(minute="*",             timezone=TZ), id="radio_due_minutely", replace_existing=True)
    _scheduler.add_job(job_create_daily_digest, CronTrigger(hour=12,  minute=0,     timezone=TZ), id="create_digest",      replace_existing=True)
    _scheduler.add_job(job_clean_cache_24h,     CronTrigger(hour=2,   minute=0,     timezone=TZ), id="clean_cache_24h",    replace_existing=True)

    return _scheduler

def attach_scheduler(app) -> None:
    """Appelé depuis server.py (on_startup) pour démarrer UNE SEULE instance."""
    if not RUN_SCHEDULER:
        logger.info("⏸️ RUN_SCHEDULER=0 → scheduler désactivé")
        return
    if getattr(app.state, "scheduler_started", False):
        logger.info("↩️ Scheduler déjà attaché")
        return

    sched = _ensure_scheduler()
    if not sched.running:
        sched.start()
        logger.info(
            "✅ Scheduler démarré (tz=%s | now_local=%s | now_utc=%sZ)",
            TIMEZONE_NAME, datetime.now(TZ).isoformat(), datetime.now(ZoneInfo("UTC")).isoformat()
        )
    app.state.scheduler = sched
    app.state.scheduler_started = True

def stop_scheduler(app=None) -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("🛑 Scheduler arrêté")
    if app is not None:
        app.state.scheduler_started = False

# =========================
# API Router (admin)
# =========================
router = APIRouter()

def _job_info(j: Job) -> Dict[str, Any]:
    nr = j.next_run_time  # timezone-aware (APS) ou None
    try:
        next_utc = nr.astimezone(ZoneInfo("UTC")).isoformat() if nr else None
        next_local = nr.astimezone(TZ).isoformat() if nr else None
    except Exception:
        next_utc = next_local = None
    return {
        "id": j.id,
        "name": j.name or j.id,
        "next_run_time_utc": next_utc,
        "next_run_time_local": next_local,
        "trigger": str(j.trigger),
    }

@router.get("/status", tags=["scheduler"])
def scheduler_status():
    sched = _ensure_scheduler()
    jobs = [_job_info(j) for j in sched.get_jobs()]

    # tri lisible : par prochaine exécution locale (None à la fin)
    def _key(x):
        return (x["next_run_time_local"] is None, x["next_run_time_local"] or "")
    jobs_sorted = sorted(jobs, key=_key)

    return {
        "running": sched.running,
        "timezone": TIMEZONE_NAME,
        "now_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "now_local": datetime.now(TZ).isoformat(),
        "jobs": jobs_sorted,
        "note": "Si next_run_time_* est null, le job vient peut-être d'être exécuté ou est en pause.",
    }

@router.get("/next", tags=["scheduler"])
def next_runs():
    """Résumé synthétique des prochaines exécutions."""
    sched = _ensure_scheduler()
    items = []
    for j in sched.get_jobs():
        info = _job_info(j)
        items.append({
            "id": info["id"],
            "next_local": info["next_run_time_local"],
            "next_utc": info["next_run_time_utc"],
        })
    items.sort(key=lambda x: (x["next_local"] is None, x["next_local"] or ""))
    return {
        "timezone": TIMEZONE_NAME,
        "now_local": datetime.now(TZ).isoformat(),
        "now_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "next": items,
    }

@router.post("/run-job/{job_id}", tags=["scheduler"])
async def run_job(job_id: str):
    job_map = {
        "scrape_articles": job_scrape_articles,
        "radio_due_minutely": job_radio_due_minutely,
        "create_digest": job_create_daily_digest,
        "clean_cache_24h": job_clean_cache_24h,
    }
    func = job_map.get(job_id)
    if func is None:
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
