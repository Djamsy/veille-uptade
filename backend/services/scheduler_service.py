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

from fastapi import APIRouter, HTTPException, Query, Depends
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
        from backend.services.scraper_service import guadeloupe_scraper
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
        from backend.services.ai_groq_service import smart_enrich_article, is_available as groq_ok
        if groq_ok():
            return smart_enrich_article, "groq"
    except Exception:
        pass
    try:
        from backend.services.tags_index import infer_tags_and_theme
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
        from backend.services.affair_lifecycle_service import get_affair_lifecycle_service
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

            # Diagnostic détaillé pour suivre l'état du pipeline
            total_col = articles_col.estimated_document_count()
            preliminary = articles_col.count_documents({"_analysis_method": "rules_preliminary"})
            ultra_strict = articles_col.count_documents({"_analysis_method": "rule_based_ultra_strict"})
            no_method = articles_col.count_documents({"_analysis_method": {"$exists": False}})
            logger.info(
                f"📊 DB: {total_col} articles total, "
                f"{preliminary} rules_preliminary, {ultra_strict} ultra_strict, "
                f"{no_method} sans méthode"
            )

            # Articles à enrichir : soit jamais enrichis, soit seulement pré-enrichis
            # Fenêtre large (30j) pour rattraper le backlog, batch 200
            cutoff_dt = datetime.now() - timedelta(days=30)
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

            articles = list(articles_col.find(query).sort("scraped_at", -1).limit(200))

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

            # ── Batch : collecter les updates puis bulk_write ──
            from pymongo import UpdateOne
            bulk_ops = []
            telegram_queue = []
            enriched_payloads = []  # pour l'extraction de présence (fait après le bulk_write)

            for article in articles:
                try:
                    article_data = {
                        "title": article.get("title", ""),
                        "content": article.get("content", "") or article.get("text", ""),
                    }

                    enriched = await loop.run_in_executor(None, enrich_fn, article_data)

                    if enriched:
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
                            # Ajouter au batch au lieu d'écrire un par un
                            bulk_ops.append(UpdateOne(
                                {"_id": article["_id"]},
                                {"$set": update_fields}
                            ))
                            enriched_count += 1
                            # Conserver la version enrichie pour l'extraction de présence
                            enriched_payloads.append({**article, **update_fields})

                            # Queue Telegram notifications
                            try:
                                gravity = update_fields.get("gravity_score", 0) or 0
                                institutions = update_fields.get("institutions", []) or []
                                is_affair = update_fields.get("is_affair", False)

                                dept_keywords = ["département", "conseil départemental", "cd971",
                                                 "région", "conseil régional", "collectivité"]
                                title_lower = article.get("title", "").lower()
                                is_dept = any(k in title_lower for k in dept_keywords)
                                has_institutions = len(institutions) > 0

                                if gravity >= 0.4 and (is_dept or has_institutions or is_affair):
                                    telegram_queue.append({**article, **update_fields})
                            except Exception:
                                pass

                except Exception as e:
                    logger.warning(f"⚠️ Erreur enrichissement article {article.get('_id')}: {e}")
                    continue

            # ── Écriture batch (1 appel réseau au lieu de N) ──
            if bulk_ops:
                try:
                    result = articles_col.bulk_write(bulk_ops, ordered=False)
                    logger.info(f"✅ bulk_write: {result.modified_count} modifiés sur {len(bulk_ops)}")
                except Exception as e:
                    logger.warning(f"⚠️ bulk_write fallback: {e}")
                    # Fallback : écriture individuelle
                    for op in bulk_ops:
                        try:
                            articles_col.update_one(op._filter, op._doc)
                        except Exception:
                            pass

            # ── Notifications Telegram (après le batch) ──
            if telegram_queue:
                try:
                    from backend.services.telegram_service import notify_new_article
                    for merged_article in telegram_queue[:10]:  # Max 10 notifs par cycle
                        merged_article["_id"] = str(merged_article.get("_id", ""))
                        notify_new_article(merged_article)
                except Exception as tg_err:
                    logger.debug(f"Telegram notif article: {tg_err}")

            logger.info(f"✅ {enriched_count}/{len(articles)} articles enrichis ({method})")

            # ── Extraction de présence (élus → commune) sur les articles enrichis ──
            # Idempotent grâce à idx_presence_dedup. N'échoue jamais le job principal.
            try:
                if enriched_payloads:
                    from backend.services.entity_presence_service import extract_presences_from_article

                    presences_col = _db["entity_presences"]
                    pres_total = 0
                    pres_inserted = 0
                    for payload in enriched_payloads:
                        try:
                            records = await loop.run_in_executor(
                                None, extract_presences_from_article, payload
                            )
                            if not records:
                                continue
                            pres_total += len(records)
                            for r in records:
                                key = {
                                    "article_id": r["article_id"],
                                    "entity_canonical": r["entity_canonical"],
                                    "commune": r["commune"],
                                }
                                if presences_col.find_one(key):
                                    continue
                                presences_col.insert_one(r)
                                pres_inserted += 1
                        except Exception as e:
                            logger.debug(f"Presence extract: {e}")
                    if pres_total or pres_inserted:
                        logger.info(
                            f"📍 Présences : {pres_inserted}/{pres_total} insérées sur {len(enriched_payloads)} articles enrichis"
                        )
            except Exception as e:
                logger.warning(f"⚠️ Pipeline présence indisponible: {e}")

            # Générer les embeddings pour les articles enrichis sans embedding
            try:
                from backend.services.embedding_service import is_available as emb_ok, enrich_batch_with_embeddings, build_text_for_embedding
                if emb_ok():
                    no_emb = list(articles_col.find({
                        "embedding": {"$exists": False},
                        "_analysis_method": {"$exists": True},
                        "$or": [
                            {"scraped_at": {"$gte": cutoff_dt}},
                            {"scraped_at": {"$gte": cutoff_str}},
                        ],
                    }).limit(200))
                    if no_emb:
                        emb_count = await loop.run_in_executor(
                            None, enrich_batch_with_embeddings,
                            no_emb, "article", articles_col
                        )
                        logger.info(f"🧮 {emb_count}/{len(no_emb)} articles enrichis avec embeddings")
            except Exception as e:
                logger.warning(f"⚠️ Embeddings: {e}")

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
            logger.warning("⚠️ job_affair_cycle: DB non disponible")
            return

        try:
            svc = _get_affair_service()
            if svc is None:
                logger.warning("⚠️ Service affaires non disponible")
                return

            loop = asyncio.get_running_loop()

            # Pré-diagnostic détaillé
            affairs_count = _db["affairs"].count_documents({"status": "active"})
            articles_total = _db["articles_guadeloupe"].estimated_document_count()
            not_processed = _db["articles_guadeloupe"].count_documents({
                "$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                ]
            })
            logger.info(f"🔄 Lancement cycle affaires — {affairs_count} actives, "
                        f"{articles_total} articles total, {not_processed} non traités")
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

    # Articles enrichis des 30 derniers jours
    cutoff_dt = datetime.now() - timedelta(days=30)
    cutoff_str = cutoff_dt.isoformat()
    enriched = list(articles_col.find({
        "_analysis_method": {"$exists": True},
        "$or": [
            {"scraped_at": {"$gte": cutoff_dt}},
            {"scraped_at": {"$gte": cutoff_str}},
        ],
    }).limit(500))

    if not enriched:
        logger.info("📥 Ingestion: 0 articles enrichis en 30j — rien à ingérer")
        return 0

    # IDs déjà ingérés
    existing_ids = set()
    for c in candidates_col.find({"source_type": "article"}, {"item_id": 1}):
        existing_ids.add(c.get("item_id", ""))

    already_exists = 0
    ingested = 0
    errors = 0
    for article in enriched:
        art_id = str(article["_id"])
        if art_id in existing_ids:
            already_exists += 1
            continue

        try:
            result = svc.ingest_item(article, source_type="article")
            if result.get("success") and result.get("action") != "already_exists":
                ingested += 1
            elif result.get("action") == "already_exists":
                already_exists += 1
        except Exception as e:
            errors += 1
            logger.debug(f"Ingestion article {art_id}: {e}")
            continue

    logger.info(f"📥 Ingestion: {ingested} nouveaux, {already_exists} déjà existants, "
                f"{errors} erreurs (sur {len(enriched)} enrichis)")
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
                logger.info("📊 MAJ affaires: 0 affaires actives, rien à mettre à jour")
                return

            # Contenus récents (3h)
            cutoff_dt = datetime.now() - timedelta(hours=3)
            cutoff_str = cutoff_dt.isoformat()
            recent_articles = articles_col.count_documents({"$or": [
                {"scraped_at": {"$gte": cutoff_dt}},
                {"scraped_at": {"$gte": cutoff_str}},
            ]})
            logger.info(f"📊 MAJ affaires: {len(active)} actives, {recent_articles} articles récents (3h)")
            updated_count = 0

            # Institutions trop génériques — ne comptent pas pour le matching
            GENERIC_INSTITUTIONS = {
                "préfecture", "prefecture", "parquet", "parquet de pointe-à-pitre",
                "tribunal", "tribunal administratif", "agence régionale de santé", "ars",
                "conseil départemental", "conseil régional", "rectorat",
                "france travail", "caisse générale de sécurité sociale", "cgss",
                "edf", "edf guadeloupe", "sdis", "sdis guadeloupe",
                "parc national", "ordre des avocats", "chambre des métiers",
                "insee", "pôle emploi", "gendarmerie", "samu", "pompiers",
                "centre régional opérationnel de surveillance et de sauvetage",
            }

            # Élus omniprésents — présents dans beaucoup de contextes différents
            GENERIC_ELECTED = {
                "victorin lurel", "ary chalus", "eric jalton", "éric jalton",
                "guy losbar", "josette borel-lincertin", "max mathiasin",
                "harry durimel", "hélène vainqueur-christophe",
                "dominique théophile", "justine bénin", "olivier serva",
            }

            for affair in active:
                # Entités de l'affaire — UNIQUEMENT elected + institutions d'ORIGINE
                # PAS le champ "entities" accumulé (effet boule de neige)
                affair_elected = set(
                    e.lower().strip() for e in affair.get("elected", []) if e and len(e) > 3
                )
                affair_institutions = set(
                    e.lower().strip() for e in affair.get("institutions", []) if e and len(e) > 3
                ) - GENERIC_INSTITUTIONS

                if not affair_elected and not affair_institutions:
                    logger.debug(f"   ⏭️ Affaire '{affair.get('title', '?')[:40]}' sans entités spécifiques, skip")
                    continue

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
                    art_institutions -= GENERIC_INSTITUTIONS

                    # Match STRICT v2 :
                    # - 1 élu SPÉCIFIQUE en commun = signal fort
                    # - OU 2 élus génériques en commun + même thème
                    # - OU 2 institutions SPÉCIFIQUES en commun + même thème
                    common_elected = affair_elected & art_elected
                    common_elected_specific = common_elected - GENERIC_ELECTED
                    common_institutions = affair_institutions & art_institutions
                    same_theme = (
                        affair.get("theme", "") == article.get("theme", "")
                        and affair.get("theme", "") not in ("", "general", "sante_social", "securite_justice")
                    )
                    match = (
                        len(common_elected_specific) >= 1
                        or (len(common_elected) >= 2 and same_theme)
                        or (len(common_institutions) >= 2 and same_theme)
                    )
                    if match:
                        matched = list(common_elected | common_institutions)[:5]
                        updates.append({
                            "type": "article",
                            "id": art_id,
                            "title": article.get("title"),
                            "matched_entities": matched,
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
                logger.info(f"✅ {updated_count}/{len(active)} affaires mises à jour (matching entités+thème)")
            else:
                logger.info(f"ℹ️ 0 affaires mises à jour — aucun nouvel article ne match les entités des affaires actives")

        except Exception as e:
            logger.error(f"❌ Erreur MAJ affaires: {e}", exc_info=True)


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
            from backend.services.radio_service import radio_service as _rs
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
# JOB 6: Health-check automatique des flux radio
# ============================================================

async def job_radio_health_check():
    """Vérifie l'accessibilité de tous les flux radio configurés."""
    try:
        from backend.routers.radio_cards_routes import run_auto_health_check

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_auto_health_check)
        ok = result.get("ok", 0)
        errors = result.get("errors", 0)
        if errors > 0:
            logger.warning(f"🩺 Radio health: {ok} OK, {errors} en erreur")
        else:
            logger.info(f"🩺 Radio health: {ok} flux OK")
        return result
    except Exception as e:
        logger.error(f"❌ Erreur health-check radio: {e}")
        return {"error": str(e)}


# ============================================================
# JOB 7: Scraping réseaux sociaux via Apify (1x/heure)
# ============================================================

async def job_social_scrape():
    """Scrape batché Facebook + Instagram + Twitter via Apify."""
    try:
        from backend.services.apify_social_scraper import get_social_scraper

        scraper = get_social_scraper()
        if not scraper.is_ready():
            logger.debug("ℹ️ Apify social: APIFY_TOKEN non configuré, skip")
            return {"success": False, "reason": "apify_not_configured"}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, scraper.scrape_all)
        total = result.get("total_saved", 0)
        if total > 0:
            logger.info(f"📱 Social scrape: {total} nouveaux posts")
        else:
            logger.info("📱 Social scrape: aucun nouveau post")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur social scrape: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# JOB Buffer Stats Sync (gratuit — 6×/jour)
# ============================================================

async def job_buffer_stats_sync():
    """Synchronise les stats des publications via Buffer API (gratuit)."""
    try:
        from backend.services.campaign_service import sync_buffer_stats

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, sync_buffer_stats)
        updated = result.get("updated", 0)
        created = result.get("created", 0)
        logger.info(f"📊 Buffer sync: {updated} mis à jour, {created} créés")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur Buffer stats sync: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# JOB Apify Comments Scrape (payant — 2×/jour, ~$0.43/run)
# ============================================================

async def job_apify_comments_scrape():
    """Scrape les commentaires FB/IG/TikTok via Apify (budget $30/mois)."""
    try:
        from backend.services.social_stats_scraper import scrape_own_social_stats

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, scrape_own_social_stats)
        platforms = result.get("platforms", {})
        total_comments = sum(
            p.get("comments_count", 0) for p in platforms.values() if isinstance(p, dict)
        )
        logger.info(f"💬 Apify comments: {total_comments} commentaires récupérés sur {len(platforms)} plateformes")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur Apify comments scrape: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# JOB Observatoire social — snapshots historiques (gratuit)
# ============================================================

async def job_social_snapshot():
    """Fige l'engagement du jour par plateforme dans account_snapshots (quotidien)."""
    try:
        from backend.services.social_snapshot_service import capture_snapshots

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, capture_snapshots)
        logger.info(f"📸 Snapshot social: {result.get('captured', 0)} plateformes ({result.get('snapshot_date')})")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur snapshot social: {e}")
        return {"ok": False, "error": str(e)}


async def job_social_followers_weekly():
    """Renseigne les followers sur le snapshot du jour (hebdomadaire)."""
    try:
        from backend.services.social_snapshot_service import capture_followers_weekly

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, capture_followers_weekly)
        logger.info(f"👥 Snapshot followers hebdo: {result.get('captured', 0)} plateformes")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur snapshot followers: {e}")
        return {"ok": False, "error": str(e)}


# ============================================================
# JOB Auto-analyse campagnes RS (tous les 2 jours)
# ============================================================

async def job_campaign_auto_analysis():
    """Re-analyse les campagnes RS dont l'analyse a expiré (>2j)."""
    try:
        from backend.services.campaign_service import auto_analyze_campaigns

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, auto_analyze_campaigns)
        analyzed = result.get("analyzed", 0)
        logger.info(f"Auto-analyse RS: {analyzed} campagnes re-analysees")
        return result

    except Exception as e:
        logger.error(f"Erreur auto-analyse campagnes: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# JOB combiné : Scrape → Enrich → Cycle affaires
# ============================================================

async def job_full_pipeline():
    """Pipeline complet : scraping → enrichissement → affaires + notif Telegram"""
    logger.info("🚀 Pipeline complet démarré")

    # 1. Scraping
    scrape_result = await job_scrape()

    # 2. Enrichissement
    enrich_result = await job_enrich()

    # 3. Cycle affaires
    affair_result = await job_affair_cycle()

    logger.info("✅ Pipeline complet terminé")

    # 4. Notification Telegram du résultat
    try:
        from backend.services.telegram_service import notify_pipeline_result
    except ImportError:
        try:
            from telegram_service import notify_pipeline_result
        except ImportError:
            notify_pipeline_result = None

    if notify_pipeline_result:
        try:
            scraped = 0
            if isinstance(scrape_result, dict):
                scraped = scrape_result.get("new_articles", 0) or scrape_result.get("total_new", 0) or 0
            enriched = 0
            if isinstance(enrich_result, dict):
                enriched = enrich_result.get("enriched", 0) or 0
            created = merged = ignored = radio = inter_merged = geo_cleaned = 0
            if isinstance(affair_result, dict):
                created = affair_result.get("created", 0) or 0
                merged = affair_result.get("merged", 0) or 0
                ignored = affair_result.get("ignored", 0) or 0
                radio = affair_result.get("radio_created", 0) or 0
                inter_merged = affair_result.get("inter_merged", 0) or 0
                geo_cleaned = affair_result.get("geo_cleaned", 0) or 0
            notify_pipeline_result(
                articles_scraped=scraped,
                articles_enriched=enriched,
                affairs_created=created,
                affairs_merged=merged + inter_merged,
                affairs_ignored=ignored + geo_cleaned,
                radio_created=radio,
            )
        except Exception as e:
            logger.debug(f"Telegram pipeline notif error: {e}")

    return {
        "scrape": scrape_result,
        "enrich": enrich_result,
        "affairs": affair_result
    }


# ============================================================
# Job: Analyse prédictive IA (toutes les heures)
# ============================================================

async def job_daily_report():
    """Génère et envoie le bilan PDF quotidien par Telegram (7h du matin)."""
    if _db is None:
        logger.warning("⚠️ Daily report: DB indisponible")
        return {"status": "skip", "reason": "no_db"}

    try:
        from backend.services.daily_report_service import generate_and_send_daily_report

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, generate_and_send_daily_report, _db)

        if result.get("success"):
            logger.info(
                f"📄 Bilan quotidien envoyé — {result.get('date')} "
                f"({result.get('pdf_size_kb')} KB), Telegram: {result.get('telegram_sent')}"
            )
        else:
            logger.warning(f"⚠️ Bilan quotidien échoué: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"❌ Erreur bilan quotidien: {e}")
        return {"status": "error", "reason": str(e)}


async def job_weekly_digest():
    """Bilan hebdomadaire RS par Telegram (lundi).

    Tente d'abord le rendu PNG serveur (Playwright) ; si indisponible,
    retombe sur le digest texte — aucune semaine sans bilan.
    """
    if _db is None:
        logger.warning("⚠️ Bilan hebdo: DB indisponible")
        return {"status": "skip", "reason": "no_db"}

    try:
        # 1) Tentative PNG (navigateur headless)
        try:
            from backend.services.report_render_service import render_weekly_png
            from backend.services.telegram_service import send_photo_bytes, is_configured as tg_ok
            png = await render_weekly_png(days=7)
            if png and tg_ok():
                from functools import partial
                sent = await asyncio.get_running_loop().run_in_executor(
                    None,
                    partial(send_photo_bytes, png, caption="📊 Bilan hebdomadaire — réseaux sociaux",
                            filename="bilan-hebdo.png", as_document=True),
                )
                if sent:
                    logger.info("📊 Bilan hebdo PNG envoyé")
                    return {"ok": True, "mode": "png", "sent": True}
        except Exception as e:
            logger.warning(f"Bilan hebdo PNG indisponible, fallback texte: {e}")

        # 2) Fallback : digest texte
        from backend.services.weekly_digest_service import send_weekly_digest
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, send_weekly_digest, 7, _db)
        result["mode"] = "text"
        logger.info(f"📊 Bilan hebdo (texte) — envoyé: {result.get('sent')}")
        return result

    except Exception as e:
        logger.error(f"❌ Erreur bilan hebdo RS: {e}")
        return {"status": "error", "reason": str(e)}


async def job_predictive_analysis():
    """Lance l'analyse prédictive IA sur les affaires actives et stocke le résultat."""
    if _db is None:
        logger.warning("⚠️ Predictive: DB indisponible")
        return {"status": "skip", "reason": "no_db"}

    try:
        # Import du service IA
        from backend.services.ai_groq_service import analyze_trends_predictive

        affairs_col = _db.get_collection("affairs")
        active = list(affairs_col.find({"status": "active"}).sort("bmg", -1).limit(30))

        if not active:
            logger.info("🔮 Predictive: aucune affaire active")
            return {"status": "skip", "reason": "no_affairs"}

        # Exécuter l'analyse (appel synchrone dans executor)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyze_trends_predictive, active)

        if result:
            # Stocker le résultat en cache dans MongoDB
            cache_col = _db.get_collection("predictive_cache")
            cache_col.update_one(
                {"_id": "latest"},
                {"$set": {
                    "analysis": result,
                    "affairs_analyzed": len(active),
                    "generated_at": datetime.now().isoformat(),
                }},
                upsert=True,
            )
            logger.info(f"🔮 Analyse prédictive IA terminée — {len(active)} affaires analysées")
            return {"status": "ok", "affairs_analyzed": len(active)}
        else:
            logger.warning("⚠️ Predictive: résultat vide")
            return {"status": "error", "reason": "empty_result"}

    except Exception as e:
        logger.error(f"❌ Predictive IA erreur: {e}")
        return {"status": "error", "reason": str(e)}


# ============================================================
# BRIEFING MATINAL + WATCHLIST
# ============================================================

async def job_morning_briefing():
    """Envoie le briefing matinal Telegram (7h15, après captures radio 7h)."""
    if _db is None:
        logger.warning("⚠️ Morning briefing: DB indisponible")
        return {"status": "skip", "reason": "no_db"}

    try:
        from backend.services.briefing_service import send_telegram_briefing

        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, send_telegram_briefing, _db, 24)

        if success:
            logger.info("☀️ Briefing matinal envoyé sur Telegram")
        else:
            logger.info("☀️ Briefing matinal: Telegram non configuré ou vide")

        return {"status": "ok", "telegram_sent": success}

    except Exception as e:
        logger.error(f"❌ Morning briefing erreur: {e}")
        return {"status": "error", "reason": str(e)}


async def job_watchlist_check():
    """Vérifie les mots-clés watchlist et envoie les alertes Telegram."""
    if _db is None:
        logger.warning("⚠️ Watchlist check: DB indisponible")
        return {"status": "skip", "reason": "no_db"}

    try:
        from backend.services.briefing_service import _check_watchlist, send_watchlist_alerts_telegram

        articles_col = _db["articles_guadeloupe"]
        radio_col = _db["radio_transcriptions"]

        # Articles de la dernière heure
        cutoff = datetime.now() - timedelta(hours=1)
        cutoff_iso = cutoff.isoformat()

        recent_articles = list(
            articles_col.find(
                {"$or": [
                    {"scraped_at": {"$gte": cutoff}},
                    {"scraped_at": {"$gte": cutoff_iso}},
                ]},
                {"title": 1, "source": 1, "ai_summary": 1, "gravity_score": 1},
            ).limit(100)
        )

        recent_radio = list(
            radio_col.find(
                {"$or": [
                    {"captured_at": {"$gte": cutoff}},
                    {"captured_at": {"$gte": cutoff_iso}},
                ]},
                {"stream_name": 1, "section": 1, "topic_title": 1,
                 "ai_summary": 1, "gpt_analysis": 1, "topic_summary": 1},
            ).limit(30)
        )

        if not recent_articles and not recent_radio:
            return {"status": "ok", "reason": "no_recent_content"}

        loop = asyncio.get_running_loop()
        hits = await loop.run_in_executor(
            None, _check_watchlist, _db, recent_articles, recent_radio
        )

        sent = 0
        if hits:
            sent = await loop.run_in_executor(
                None, send_watchlist_alerts_telegram, _db, hits
            )
            logger.info(f"🔔 Watchlist: {len(hits)} alertes, {sent} envoyées Telegram")

        return {"status": "ok", "hits": len(hits), "telegram_sent": sent}

    except Exception as e:
        logger.error(f"❌ Watchlist check erreur: {e}")
        return {"status": "error", "reason": str(e)}


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

    # Pipeline complet toutes les 5 min — réactivité conservée
    # ⚡ Coût réduit PAR CYCLE (insert_many, dedup $or, pas de count_documents)
    _scheduler.add_job(
        job_full_pipeline,
        CronTrigger(minute="*/5", timezone=TZ),
        id="full_pipeline",
        name="Pipeline complet (scrape → enrich → affaires) 12x/h"
    )

    # Mise à jour des affaires toutes les 15 min
    _scheduler.add_job(
        job_update_affairs,
        CronTrigger(minute="*/15", timezone=TZ),
        id="update_affairs",
        name="MAJ affaires actives"
    )

    # Enrichissement standalone supprimé — déjà inclus dans full_pipeline

    # 🎙️ Capture radio toutes les 5 min
    _scheduler.add_job(
        job_radio_capture,
        CronTrigger(minute="*/5", timezone=TZ),
        id="radio_capture",
        name="Capture radio/TV (flux planifiés)"
    )

    # 🩺 Health-check des flux radio toutes les 30 min
    _scheduler.add_job(
        job_radio_health_check,
        CronTrigger(minute="5,35", timezone=TZ),
        id="radio_health_check",
        name="Health-check flux radio"
    )

    # 📱 Scraping RS veille/monitoring 3×/jour (7h10, 13h10, 19h10)
    _scheduler.add_job(
        job_social_scrape,
        CronTrigger(hour="7,13,19", minute="10", timezone=TZ),
        id="social_scrape",
        name="Scraping RS veille (FB + IG + TikTok) 3x/jour"
    )

    # 📊 Buffer Stats Sync 6×/jour (gratuit) — 6h, 10h, 13h, 16h, 22h, 23h
    _scheduler.add_job(
        job_buffer_stats_sync,
        CronTrigger(hour="6,10,13,16,22,23", minute="0", timezone=TZ),
        id="buffer_stats_sync",
        name="Buffer stats sync (gratuit) 6x/jour"
    )

    # 💬 Apify Comments Scrape 2×/jour (payant ~$0.43/run) — 8h, 19h
    _scheduler.add_job(
        job_apify_comments_scrape,
        CronTrigger(hour="8,19", minute="0", timezone=TZ),
        id="apify_comments_scrape",
        name="Apify comments (FB+IG+TK) 2x/jour — budget $30/mois"
    )

    # 📸 Snapshot social quotidien à 23h50 — après tous les syncs de la journée
    _scheduler.add_job(
        job_social_snapshot,
        CronTrigger(hour=23, minute=50, timezone=TZ),
        id="social_snapshot",
        name="Snapshot engagement social (quotidien, gratuit)"
    )

    # 👥 Snapshot followers hebdomadaire — lundi 0h05
    _scheduler.add_job(
        job_social_followers_weekly,
        CronTrigger(day_of_week="mon", hour=0, minute=5, timezone=TZ),
        id="social_followers_weekly",
        name="Snapshot followers (hebdomadaire)"
    )

    # Auto-analyse campagnes RS tous les 2 jours a 9h
    _scheduler.add_job(
        job_campaign_auto_analysis,
        CronTrigger(day="*/2", hour="9", minute="0", timezone=TZ),
        id="campaign_auto_analysis",
        name="Auto-analyse campagnes RS (tous les 2j)"
    )

    # Analyse predictive IA toutes les heures (minute 30)
    _scheduler.add_job(
        job_predictive_analysis,
        # Coût IA : une affaire n'évolue pas d'heure en heure. 4×/jour suffit
        # (était minute="30" = 24×/jour → ~-70€/mois sur les appels GPT).
        CronTrigger(hour="6,12,18,0", minute="30", timezone=TZ),
        id="predictive_analysis",
        name="Analyse prédictive IA (GPT) — 4×/jour"
    )

    # 📄 Bilan PDF quotidien à 7h du matin (heure Guadeloupe)
    _scheduler.add_job(
        job_daily_report,
        CronTrigger(hour=7, minute=0, timezone=TZ),
        id="daily_report",
        name="Bilan PDF quotidien (Telegram)"
    )

    # 📊 Bilan hebdomadaire RS (digest Telegram) — lundi 8h
    _scheduler.add_job(
        job_weekly_digest,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=TZ),
        id="weekly_digest",
        name="Bilan hebdomadaire RS (Telegram, lundi 8h)"
    )

    # ☀️ Briefing matinal à 7h15 (après les captures radio de 7h)
    _scheduler.add_job(
        job_morning_briefing,
        CronTrigger(hour=7, minute=15, timezone=TZ),
        id="morning_briefing",
        name="Briefing matinal Telegram (7h15)"
    )

    # 🔔 Check watchlist toutes les heures (minute 20)
    _scheduler.add_job(
        job_watchlist_check,
        CronTrigger(minute="20", timezone=TZ),
        id="watchlist_check",
        name="Vérification watchlist (alertes)"
    )

    return _scheduler


def attach_scheduler(app):
    sched = _ensure_scheduler()
    if not sched.running:
        sched.start()
        logger.info("✅ Scheduler démarré (pipeline 15min + MAJ 15min + enrichissement 30min + radio 5min + health 30min + social 1h)")
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

# ── Auth dependencies ──
_sched_auth = {}

def _get_sched_auth():
    if not _sched_auth:
        from backend.routers.admin_routes import get_current_user, require_role
        _sched_auth["get_current_user"] = get_current_user
        _sched_auth["require_role"] = require_role
    return _sched_auth

def _sched_admin():
    return _get_sched_auth()["require_role"]("admin")

def _sched_auth_any():
    return _get_sched_auth()["require_role"]("admin", "editor", "viewer", "user")


@router.get("/dashboard")
async def scheduler_dashboard(user: dict = Depends(_sched_auth_any)):
    """Dashboard du scheduler"""
    if _db is None:
        raise HTTPException(503, "DB indisponible")

    articles_col = _db["articles_guadeloupe"]
    affairs_col = _db.get_collection("affairs")

    # Stats articles
    total_articles = articles_col.estimated_document_count()
    enriched_articles = articles_col.count_documents({"_analysis_method": {"$exists": True}})

    cutoff_24h_dt = datetime.now() - timedelta(hours=24)
    cutoff_24h_str = cutoff_24h_dt.isoformat()
    recent_articles = articles_col.count_documents({"$or": [
        {"scraped_at": {"$gte": cutoff_24h_dt}},
        {"scraped_at": {"$gte": cutoff_24h_str}},
    ]})

    # Stats affaires
    total_affairs = affairs_col.estimated_document_count()
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
async def run_pipeline_now(user: dict = Depends(_sched_admin)):
    """Lance le pipeline complet maintenant (Admin)"""
    result = await job_full_pipeline()
    return {"success": True, "result": result}


@router.post("/scrape-now")
async def scrape_now(user: dict = Depends(_sched_admin)):
    """Lance le scraping maintenant (Admin)"""
    result = await job_scrape()
    return {"success": True, "result": result}


@router.post("/enrich-now")
async def enrich_now(user: dict = Depends(_sched_admin)):
    """Lance l'enrichissement maintenant (Admin)"""
    result = await job_enrich()
    return {"success": True, "result": result}


@router.post("/detect-affairs-now")
async def detect_now(user: dict = Depends(_sched_admin)):
    """Lance le cycle affaires V2 maintenant (Admin)"""
    result = await job_affair_cycle()
    return {"success": True, "result": result}


@router.post("/radio-capture-now")
async def radio_capture_now(user: dict = Depends(_sched_admin)):
    """Lance la capture radio maintenant (Admin)"""
    result = await job_radio_capture()
    return {"success": True, "result": result}


@router.post("/radio-health-check-now")
async def radio_health_check_now(user: dict = Depends(_sched_admin)):
    """Lance le health-check radio maintenant (Admin)"""
    result = await job_radio_health_check()
    return {"success": True, "result": result}


@router.post("/social-scrape-now")
async def social_scrape_now(user: dict = Depends(_sched_admin)):
    """Lance le scraping social maintenant (Admin)"""
    result = await job_social_scrape()
    return {"success": True, "result": result}


@router.post("/buffer-sync-now")
async def buffer_sync_now(user: dict = Depends(_sched_admin)):
    """Lance la sync Buffer stats maintenant (Admin) — gratuit"""
    result = await job_buffer_stats_sync()
    return {"success": True, "result": result}


@router.post("/apify-comments-now")
async def apify_comments_now(user: dict = Depends(_sched_admin)):
    """Lance le scraping commentaires Apify maintenant (Admin) — ~$0.43"""
    result = await job_apify_comments_scrape()
    return {"success": True, "result": result}


@router.post("/bulk-enrich")
async def bulk_enrich(
    batch_size: int = Query(default=100, ge=10, le=500),
    days: int = Query(default=90, ge=1, le=365),
    user: dict = Depends(_sched_admin),
):
    """Rattrapage massif : enrichit les vieux articles. (Admin)"""
    if _db is None:
        raise HTTPException(503, "DB indisponible")

    enrich_fn, method = _get_enrichment()
    if enrich_fn is None:
        raise HTTPException(503, "Aucun service d'enrichissement disponible")

    articles_col = _db["articles_guadeloupe"]
    cutoff_dt = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_dt.isoformat()

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

    remaining = articles_col.count_documents(query)
    articles = list(articles_col.find(query).sort("scraped_at", -1).limit(batch_size))

    if not articles:
        return {"success": True, "enriched": 0, "remaining": 0, "message": "Aucun article à enrichir"}

    logger.info(f"🔄 Bulk enrich: {len(articles)} articles (sur {remaining} restants) via {method}")

    enriched_count = 0
    loop = asyncio.get_running_loop()

    for article in articles:
        try:
            article_data = {
                "title": article.get("title", ""),
                "content": article.get("content", "") or article.get("text", ""),
            }
            enriched = await loop.run_in_executor(None, enrich_fn, article_data)
            if enriched:
                update_fields = {}
                for key in ["theme", "elected", "institutions", "entities",
                             "sentiment", "is_affair", "affair_type",
                             "gravity_score", "importance_score", "keywords_found",
                             "ai_summary", "classification_confidence",
                             "_analysis_method", "_tags",
                             "event_structured"]:
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
            logger.warning(f"⚠️ Bulk enrich erreur {article.get('_id')}: {e}")
            continue

    # Embeddings pour les articles fraîchement enrichis
    emb_count = 0
    try:
        from backend.services.embedding_service import is_available as emb_ok, enrich_batch_with_embeddings
        if emb_ok():
            no_emb = list(articles_col.find({
                "embedding": {"$exists": False},
                "_analysis_method": {"$exists": True},
            }).sort("enriched_at", -1).limit(batch_size))
            if no_emb:
                emb_count = await loop.run_in_executor(
                    None, enrich_batch_with_embeddings,
                    no_emb, "article", articles_col
                )
    except Exception as e:
        logger.warning(f"⚠️ Bulk embeddings: {e}")

    remaining_after = articles_col.count_documents(query)
    logger.info(f"✅ Bulk enrich: {enriched_count}/{len(articles)} enrichis, "
                f"{emb_count} embeddings, {remaining_after} restants")

    return {
        "success": True,
        "enriched": enriched_count,
        "embeddings": emb_count,
        "remaining": remaining_after,
        "method": method,
        "message": f"{enriched_count} articles enrichis. {remaining_after} restants à traiter."
    }


@router.post("/daily-report-now")
async def daily_report_now(user: dict = Depends(_sched_admin)):
    """Génère et envoie le bilan quotidien maintenant (Admin)"""
    result = await job_daily_report()
    return {"success": True, "result": result}


@router.get("/daily-report/latest")
async def download_latest_report(user: dict = Depends(_sched_auth_any)):
    """Télécharge le dernier bilan PDF depuis MongoDB."""
    if _db is None:
        raise HTTPException(503, "DB indisponible")

    reports_col = _db.get_collection("daily_reports")
    report = reports_col.find_one(sort=[("generated_at", -1)])

    if not report or not report.get("pdf_data"):
        raise HTTPException(404, "Aucun rapport disponible")

    from fastapi.responses import Response
    date_str = report.get("date", "unknown")
    filename = f"bilan_veille_{date_str}.pdf"

    return Response(
        content=bytes(report["pdf_data"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily-report/{date}")
async def download_report_by_date(date: str, user: dict = Depends(_sched_auth_any)):
    """Télécharge un bilan PDF par date (format YYYY-MM-DD)."""
    if _db is None:
        raise HTTPException(503, "DB indisponible")

    reports_col = _db.get_collection("daily_reports")
    report = reports_col.find_one({"date": date})

    if not report or not report.get("pdf_data"):
        raise HTTPException(404, f"Aucun rapport pour le {date}")

    from fastapi.responses import Response
    filename = f"bilan_veille_{date}.pdf"

    return Response(
        content=bytes(report["pdf_data"]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/telegram-test")
async def telegram_test(user: dict = Depends(_sched_admin)):
    """Teste la connexion Telegram. (Admin)"""
    try:
        from backend.services.telegram_service import test_connection
    except ImportError:
        try:
            from telegram_service import test_connection
        except ImportError:
            raise HTTPException(503, "telegram_service non disponible")
    result = test_connection()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Échec"))
    return {"success": True, "message": "Notification Telegram envoyée !"}


__all__ = ['router', 'attach_scheduler', 'stop_scheduler', 'job_full_pipeline']
