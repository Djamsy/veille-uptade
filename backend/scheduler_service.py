"""
Scheduler central V2 pour Veille Média Guadeloupe
- Scraping automatique des articles
- Enrichissement IA via Groq (fallback règles tags_index)
- Cycle V2 affaires : clustering → promotion → lifecycle
- Mise à jour automatique des affaires actives
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from collections import Counter

from fastapi import APIRouter, HTTPException, Query
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pymongo import MongoClient
from pymongo.errors import ConfigurationError
import certifi

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("scheduler_service")
logger.setLevel(logging.INFO)

TIMEZONE_NAME = os.environ.get("TIMEZONE", "America/Guadeloupe").strip()
try:
    TZ = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TZ = ZoneInfo("UTC")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip()
GRAVITY_THRESHOLD = float(os.environ.get("GRAVITY_THRESHOLD", "0.6"))

# ============================================================
# MongoDB
# ============================================================

def _get_db():
    try:
        if MONGO_URL.startswith("mongodb+srv"):
            client = MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=15000)
        else:
            client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=15000)
        try:
            db = client.get_default_database()
        except ConfigurationError:
            db = client["veille_media"]
        return db
    except Exception as e:
        logger.warning(f"MongoDB non disponible: {e}")
        return None

_db = _get_db()
_scheduler = None
_locks = {
    'scrape': asyncio.Lock(),
    'enrich': asyncio.Lock(),
    'affairs': asyncio.Lock(),
    'update': asyncio.Lock()
}

# ============================================================
# Lazy imports des services
# ============================================================

def _get_scraper():
    try:
        from backend.scraper_service import guadeloupe_scraper
        return guadeloupe_scraper
    except Exception:
        try:
            from scraper_service import guadeloupe_scraper
            return guadeloupe_scraper
        except Exception:
            return None


def _get_enrichment():
    """Retourne la fonction d'enrichissement (Groq > tags_index)"""
    try:
        from backend.ai_groq_service import smart_enrich_article, is_available as groq_ok
        if groq_ok():
            return smart_enrich_article, "groq"
    except Exception:
        pass
    try:
        from backend.tags_index import infer_tags_and_theme
        return infer_tags_and_theme, "rules"
    except Exception:
        pass
    try:
        from tags_index import infer_tags_and_theme
        return infer_tags_and_theme, "rules"
    except Exception:
        return None, "none"


def _get_affair_service():
    """Retourne le service d'affaires V2"""
    try:
        from backend.affair_lifecycle_service import get_affair_lifecycle_service
        return get_affair_lifecycle_service(db=_db)
    except Exception:
        try:
            from affair_lifecycle_service import get_affair_lifecycle_service
            return get_affair_lifecycle_service(db=_db)
        except Exception:
            return None


# ============================================================
# JOB 1: Scraping articles
# ============================================================

async def job_scrape():
    """Scrape les sites d'actualité guadeloupéens"""
    async with _locks['scrape']:
        scraper = _get_scraper()
        if not scraper:
            logger.warning("⚠️ Scraper non disponible")
            return

        try:
            logger.info("🌐 Lancement scraping...")
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, scraper.scrape_all_sites)
            if result and result.get("success"):
                total = result.get("total_articles", 0)
                logger.info(f"✅ {total} articles scrapés")
                return {"success": True, "articles": total}
            else:
                logger.warning("⚠️ Scraping terminé sans succès")
                return {"success": False}
        except Exception as e:
            logger.error(f"❌ Erreur scraping: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# JOB 2: Enrichissement IA des articles non enrichis
# ============================================================

async def job_enrich():
    """Enrichit les articles récents qui n'ont pas encore été analysés"""
    async with _locks['enrich']:
        if _db is None:
            return

        enrich_fn, method = _get_enrichment()
        if enrich_fn is None:
            logger.warning("⚠️ Aucun service d'enrichissement disponible")
            return

        try:
            articles_col = _db["articles_guadeloupe"]

            # Diagnostic : compter les articles par _analysis_method
            total_col = articles_col.count_documents({})
            preliminary = articles_col.count_documents({"_analysis_method": "rules_preliminary"})
            ultra_strict = articles_col.count_documents({"_analysis_method": "rule_based_ultra_strict"})
            no_method = articles_col.count_documents({"_analysis_method": {"$exists": False}})
            logger.info(
                f"📊 DB: {total_col} articles total, "
                f"{preliminary} rules_preliminary, {ultra_strict} ultra_strict, "
                f"{no_method} sans méthode"
            )

            # Articles à enrichir : soit jamais enrichis, soit seulement pré-enrichis
            cutoff_dt = datetime.now() - timedelta(days=3)
            cutoff_str = cutoff_dt.isoformat()

            # Requête simple — chercher les articles à ré-enrichir
            # On utilise $and explicite pour combiner les conditions proprement
            query = {"$and": [
                {"$or": [
                    {"_analysis_method": {"$exists": False}},
                    {"_analysis_method": "rules_preliminary"},
                    {"_analysis_method": "rule_based_ultra_strict"},
                ]},
                {"$or": [
                    {"scraped_at": {"$gte": cutoff_dt}},
                    {"scraped_at": {"$gte": cutoff_str}},
                ]}
            ]}

            articles = list(articles_col.find(query).limit(50))

            if not articles:
                # Diagnostic supplémentaire
                any_preliminary = articles_col.find_one({"_analysis_method": "rules_preliminary"})
                if any_preliminary:
                    logger.warning(
                        f"⚠️ {preliminary} articles rules_preliminary en base mais "
                        f"aucun ne match la requête ! scraped_at type: "
                        f"{type(any_preliminary.get('scraped_at'))}, "
                        f"valeur: {any_preliminary.get('scraped_at')}"
                    )
                else:
                    logger.info("ℹ️ Pas d'articles à enrichir (aucun rules_preliminary)")
                return {"enriched": 0}

            logger.info(f"🧠 Enrichissement de {len(articles)} articles via {method}...")

            enriched_count = 0
            loop = asyncio.get_running_loop()

            for article in articles:
                try:
                    # Copier pour ne pas modifier l'original
                    article_data = {
                        "title": article.get("title", ""),
                        "content": article.get("content", "") or article.get("text", ""),
                    }

                    # Exécuter l'enrichissement (peut être lent si Groq)
                    enriched = await loop.run_in_executor(None, enrich_fn, article_data)

                    if enriched:
                        # Sauvegarder les champs enrichis
                        update_fields = {}
                        for key in ["theme", "elected", "institutions", "entities",
                                     "sentiment", "is_affair", "affair_type",
                                     "gravity_score", "importance_score", "keywords_found",
                                     "ai_summary", "classification_confidence",
                                     "_analysis_method", "_tags"]:
                            if key in enriched:
                                update_fields[key] = enriched[key]

                        if update_fields:
                            update_fields["enriched_at"] = datetime.now().isoformat()
                            articles_col.update_one(
                                {"_id": article["_id"]},
                                {"$set": update_fields}
                            )
                            enriched_count += 1

                except Exception as e:
                    logger.warning(f"⚠️ Erreur enrichissement article {article.get('_id')}: {e}")
                    continue

            logger.info(f"✅ {enriched_count}/{len(articles)} articles enrichis ({method})")
            return {"enriched": enriched_count, "method": method}

        except Exception as e:
            logger.error(f"❌ Erreur enrichissement batch: {e}")
            return {"error": str(e)}


# ============================================================
# JOB 3: Cycle V2 affaires (clustering → promotion → lifecycle)
# ============================================================

async def job_affair_cycle():
    """Lance le cycle simplifié des affaires :
    1. Chaque article enrichi → crée une affaire (ou fusionne si similaire)
    2. Consolide 24h (multi-source)
    3. Lie les transcriptions radio
    4. Lifecycle + BMG
    """
    async with _locks['affairs']:
        if _db is None:
            return

        try:
            svc = _get_affair_service()
            if svc is None:
                logger.warning("⚠️ Service affaires non disponible")
                return

            loop = asyncio.get_running_loop()

            # Cycle simplifié : créer → consolider → radio → BMG
            logger.info("🔄 Lancement cycle simplifié affaires...")
            result = await loop.run_in_executor(None, svc.run_simple_cycle)

            if result:
                created = result.get("created", 0)
                merged = result.get("merged", 0)
                consolidated = result.get("consolidated", 0)
                radio = result.get("radio_linked", 0)
                logger.info(
                    f"✅ Cycle affaires: {created} créées, {merged} fusionnées, "
                    f"{consolidated} consolidées, {radio} radio liées"
                )
            return result or {}

        except Exception as e:
            logger.error(f"❌ Erreur cycle affaires: {e}")
            return {"error": str(e)}


def _ingest_enriched_articles(svc) -> int:
    """Ingère dans topic_candidates les articles enrichis
    qui n'ont pas encore été ingérés (pas de candidate existant)."""
    if _db is None:
        return 0

    articles_col = _db["articles_guadeloupe"]
    candidates_col = _db["topic_candidates"]

    # Articles enrichis des 3 derniers jours
    cutoff_dt = datetime.now() - timedelta(days=3)
    cutoff_str = cutoff_dt.isoformat()
    enriched = list(articles_col.find({
        "_analysis_method": {"$exists": True},
        "$or": [
            {"scraped_at": {"$gte": cutoff_dt}},
            {"scraped_at": {"$gte": cutoff_str}},
        ],
    }).limit(200))

    if not enriched:
        return 0

    # IDs déjà ingérés
    existing_ids = set()
    for c in candidates_col.find({"source_type": "article"}, {"item_id": 1}):
        existing_ids.add(c.get("item_id", ""))

    ingested = 0
    for article in enriched:
        art_id = str(article["_id"])
        if art_id in existing_ids:
            continue

        try:
            result = svc.ingest_item(article, source_type="article")
            if result.get("success") and result.get("action") != "already_exists":
                ingested += 1
        except Exception as e:
            logger.debug(f"Ingestion article {art_id}: {e}")
            continue

    if ingested:
        logger.info(f"📥 {ingested} articles ingérés dans topic_candidates")
    return ingested


# ============================================================
# JOB 4: Mise à jour automatique des affaires actives
# ============================================================

async def job_update_affairs():
    """Met à jour les affaires avec nouveaux contenus liés.
    MATCHING STRICT : exige au moins 2 entités nommées en commun
    (personnalités ou institutions). Les mots-clés génériques seuls
    ne suffisent JAMAIS à lier un article."""
    async with _locks['update']:
        if _db is None:
            return

        try:
            affairs_col = _db["affairs"]
            articles_col = _db["articles_guadeloupe"]

            # Affaires actives
            active = list(affairs_col.find({"status": "active"}))
            if not active:
                return

            # Contenus récents (3h)
            cutoff_dt = datetime.now() - timedelta(hours=3)
            cutoff_str = cutoff_dt.isoformat()
            updated_count = 0

            for affair in active:
                # Entités de l'affaire (noms de personnes + institutions)
                affair_elected = set(
                    e.lower().strip() for e in affair.get("elected", []) if e and len(e) > 3
                )
                affair_institutions = set(
                    e.lower().strip() for e in affair.get("institutions", []) if e and len(e) > 3
                )
                affair_entities = affair_elected | affair_institutions
                # Aussi utiliser le champ "entities" générique
                for e in affair.get("entities", []):
                    if e and len(e) > 3:
                        affair_entities.add(e.lower().strip())

                if not affair_entities:
                    continue  # Pas d'entités → pas de matching possible

                existing_ids = set(str(a) for a in affair.get("articles", []))
                updates = []

                # Nouveaux articles liés
                for article in articles_col.find({"$or": [
                    {"scraped_at": {"$gte": cutoff_dt}},
                    {"scraped_at": {"$gte": cutoff_str}},
                ]}):
                    art_id = str(article["_id"])
                    if art_id in existing_ids:
                        continue

                    # Entités de l'article (séparées par type)
                    art_elected = set()
                    art_institutions = set()
                    for e in (article.get("elected", []) or []):
                        if e and len(e) > 3:
                            art_elected.add(e.lower().strip())
                    for e in (article.get("institutions", []) or []):
                        if e and len(e) > 3:
                            art_institutions.add(e.lower().strip())
                    for e in (article.get("entities", []) or []):
                        if e and len(e) > 3:
                            art_elected.add(e.lower().strip())
                    art_entities = art_elected | art_institutions

                    # Match assoupli :
                    # - 2 entités en commun (toujours OK), OU
                    # - 1 personne en commun + même thème
                    common_entities = affair_entities & art_entities
                    common_elected = affair_elected & art_elected
                    same_theme = (
                        affair.get("theme", "") == article.get("theme", "")
                        and affair.get("theme", "") not in ("", "general")
                    )
                    match = (
                        len(common_entities) >= 2
                        or (len(common_elected) >= 1 and same_theme)
                    )
                    if match:
                        updates.append({
                            "type": "article",
                            "id": art_id,
                            "title": article.get("title"),
                            "matched_entities": list(common_entities)[:5],
                            "time": datetime.now().isoformat()
                        })

                if updates:
                    new_article_ids = [u["id"] for u in updates if u["type"] == "article"]
                    affairs_col.update_one(
                        {"_id": affair["_id"]},
                        {
                            "$addToSet": {"articles": {"$each": new_article_ids}},
                            "$set": {
                                "last_activity": datetime.now().isoformat(),
                                "item_count": affair.get("item_count", 0) + len(updates)
                            },
                            "$push": {"timeline_events": {"$each": [{
                                "event": f"+{len(updates)} contenus liés",
                                "details": {"matched": [u.get("matched_entities", []) for u in updates]},
                                "timestamp": datetime.now().isoformat()
                            }]}}
                        }
                    )
                    updated_count += 1
                    logger.info(f"📈 MAJ: {affair.get('title', '?')} (+{len(updates)} via entités)")

            if updated_count:
                logger.info(f"✅ {updated_count} affaires mises à jour (matching entités+thème)")

        except Exception as e:
            logger.error(f"❌ Erreur MAJ affaires: {e}")


# ============================================================
# JOB 5: Capture radio (transcription flux radio/TV)
# ============================================================

async def job_radio_capture():
    """Capture les flux radio/TV qui sont dus maintenant.
    Le radio_service vérifie lui-même si un flux est planifié
    à l'heure actuelle (fenêtre de ±2min).
    """
    try:
        radio_svc = None
        try:
            from backend.radio_service import radio_service as _rs
            radio_svc = _rs
        except Exception:
            try:
                from radio_service import radio_service as _rs
                radio_svc = _rs
            except Exception:
                pass

        if radio_svc is None or not radio_svc.is_ready():
            logger.debug("ℹ️ Radio service non disponible, skip capture")
            return {"success": False, "reason": "radio_service_unavailable"}

        # Appeler capture_due_streams_async (ou sync via executor)
        if hasattr(radio_svc, 'capture_due_streams_async'):
            result = await radio_svc.capture_due_streams_async(window_min=3)
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, radio_svc.capture_due_streams)

        ran = result.get("ran", [])
        errors = result.get("errors", [])
        if ran:
            logger.info(f"🎙️ Radio capture: {len(ran)} flux capturés ({', '.join(ran)})")
        if errors:
            logger.warning(f"⚠️ Radio erreurs: {errors}")

        return result

    except Exception as e:
        logger.error(f"❌ Erreur capture radio: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# JOB combiné : Scrape → Enrich → Cycle affaires
# ============================================================

async def job_full_pipeline():
    """Pipeline complet : scraping → enrichissement → affaires"""
    logger.info("🚀 Pipeline complet démarré")

    # 1. Scraping
    scrape_result = await job_scrape()

    # 2. Enrichissement
    enrich_result = await job_enrich()

    # 3. Cycle affaires
    affair_result = await job_affair_cycle()

    logger.info("✅ Pipeline complet terminé")
    return {
        "scrape": scrape_result,
        "enrich": enrich_result,
        "affairs": affair_result
    }


# ============================================================
# Scheduler APScheduler
# ============================================================

def _ensure_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler

    _scheduler = AsyncIOScheduler(
        timezone=TZ,
        job_defaults={"coalesce": True, "max_instances": 1}
    )

    # Pipeline complet toutes les heures (scrape + enrich + affaires)
    _scheduler.add_job(
        job_full_pipeline,
        CronTrigger(minute="0", timezone=TZ),
        id="full_pipeline",
        name="Pipeline complet (scrape → enrich → affaires)"
    )

    # Mise à jour des affaires toutes les 15 min
    _scheduler.add_job(
        job_update_affairs,
        CronTrigger(minute="*/15", timezone=TZ),
        id="update_affairs",
        name="MAJ affaires actives"
    )

    # Enrichissement seul toutes les 30 min (rattrape les articles manqués)
    _scheduler.add_job(
        job_enrich,
        CronTrigger(minute="15,45", timezone=TZ),
        id="enrich_only",
        name="Enrichissement articles non traités"
    )

    # 🎙️ Capture radio toutes les 5 min (le service vérifie si un flux est dû)
    _scheduler.add_job(
        job_radio_capture,
        CronTrigger(minute="*/5", timezone=TZ),
        id="radio_capture",
        name="Capture radio/TV (flux planifiés)"
    )

    return _scheduler


def attach_scheduler(app):
    sched = _ensure_scheduler()
    if not sched.running:
        sched.start()
        logger.info("✅ Scheduler démarré (pipeline 1h + MAJ 15min + enrichissement 30min + radio 5min)")
    app.state.scheduler = sched


def stop_scheduler(app=None):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("⏹ Scheduler arrêté")


# ============================================================
# Routes API
# ============================================================

router = APIRouter()


@router.get("/dashboard")
async def scheduler_dashboard():
    """Dashboard du scheduler"""
    if _db is None:
        raise HTTPException(503, "DB indisponible")

    articles_col = _db["articles_guadeloupe"]
    affairs_col = _db.get_collection("affairs")

    # Stats articles
    total_articles = articles_col.count_documents({})
    enriched_articles = articles_col.count_documents({"_analysis_method": {"$exists": True}})

    cutoff_24h_dt = datetime.now() - timedelta(hours=24)
    cutoff_24h_str = cutoff_24h_dt.isoformat()
    recent_articles = articles_col.count_documents({"$or": [
        {"scraped_at": {"$gte": cutoff_24h_dt}},
        {"scraped_at": {"$gte": cutoff_24h_str}},
    ]})

    # Stats affaires
    total_affairs = affairs_col.count_documents({})
    active_affairs = affairs_col.count_documents({"status": "active"})

    # Méthode d'enrichissement
    _, method = _get_enrichment()

    # Jobs programmés
    jobs = []
    if _scheduler:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None
            })

    return {
        "stats": {
            "total_articles": total_articles,
            "enriched_articles": enriched_articles,
            "unenriched_articles": total_articles - enriched_articles,
            "recent_articles_24h": recent_articles,
            "total_affairs": total_affairs,
            "active_affairs": active_affairs,
        },
        "enrichment_method": method,
        "scheduler_running": _scheduler.running if _scheduler else False,
        "jobs": jobs,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/run-pipeline")
async def run_pipeline_now():
    """Lance le pipeline complet maintenant"""
    result = await job_full_pipeline()
    return {"success": True, "result": result}


@router.post("/scrape-now")
async def scrape_now():
    """Lance le scraping maintenant"""
    result = await job_scrape()
    return {"success": True, "result": result}


@router.post("/enrich-now")
async def enrich_now():
    """Lance l'enrichissement maintenant"""
    result = await job_enrich()
    return {"success": True, "result": result}


@router.post("/detect-affairs-now")
async def detect_now():
    """Lance le cycle affaires V2 maintenant"""
    result = await job_affair_cycle()
    return {"success": True, "result": result}


@router.post("/radio-capture-now")
async def radio_capture_now():
    """Lance la capture radio maintenant"""
    result = await job_radio_capture()
    return {"success": True, "result": result}


__all__ = ['router', 'attach_scheduler', 'stop_scheduler', 'job_full_pipeline']
