# backend/enhanced_scheduler_service.py
"""
Service de planification amélioré avec analyse de sentiment et bruit médiatique
Tâches automatisées pour maintenir les analyses à jour
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from fastapi import APIRouter, HTTPException
import pytz

# Import des services
try:
    from backend.enhanced_scraper import create_enhanced_scraper
    from backend.sentiment_analysis_service import SentimentAnalysisService
    from backend.media_noise_service import MediaNoiseService
except ImportError:
    create_enhanced_scraper = None
    SentimentAnalysisService = None
    MediaNoiseService = None

logger = logging.getLogger("enhanced_scheduler")

# Configuration
TIMEZONE = os.environ.get("TIMEZONE", "America/Guadeloupe")
ENABLE_SENTIMENT_ANALYSIS = os.environ.get("ENABLE_SENTIMENT_ANALYSIS", "1") == "1"
ENABLE_MEDIA_NOISE = os.environ.get("ENABLE_MEDIA_NOISE", "1") == "1"
RUN_SCHEDULER = os.environ.get("RUN_SCHEDULER", "1") == "1"

# Variables globales
scheduler: Optional[AsyncIOScheduler] = None
scheduler_stats = {
    "jobs_executed": 0,
    "jobs_failed": 0,
    "last_execution": {},
    "service_status": "stopped"
}

# Router pour les endpoints scheduler
router = APIRouter()

def job_listener(event):
    """Listener pour les événements de jobs"""
    global scheduler_stats
    
    if event.exception:
        scheduler_stats["jobs_failed"] += 1
        logger.error(f"Job {event.job_id} failed: {event.exception}")
    else:
        scheduler_stats["jobs_executed"] += 1
        scheduler_stats["last_execution"][event.job_id] = datetime.now().isoformat()
        logger.info(f"Job {event.job_id} executed successfully")

async def enhanced_scraping_job():
    """Tâche de scraping avec sentiment intégré"""
    logger.info("🕐 Démarrage scraping automatique avec sentiment")
    
    try:
        if not create_enhanced_scraper:
            logger.error("Enhanced scraper non disponible")
            return
        
        scraper = create_enhanced_scraper()
        result = scraper.scrape_with_sentiment()
        
        logger.info(
            f"✅ Scraping terminé: {result.get('metrics', {}).get('total_saved', 0)} articles, "
            f"{result.get('metrics', {}).get('sentiment_analyzed', 0)} avec sentiment"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Erreur scraping automatique: {e}")
        raise

async def sentiment_batch_analysis_job():
    """Analyse de sentiment en lot pour le contenu existant"""
    if not ENABLE_SENTIMENT_ANALYSIS:
        logger.info("Analyse de sentiment désactivée")
        return
    
    logger.info("🎭 Démarrage analyse sentiment batch")
    
    try:
        if not SentimentAnalysisService:
            logger.error("SentimentAnalysisService non disponible")
            return
        
        service = SentimentAnalysisService()
        
        # Mise à jour des articles sans sentiment
        result_articles = service.update_content_sentiment("articles")
        
        # Mise à jour des transcriptions sans sentiment
        result_transcriptions = service.update_content_sentiment("transcriptions")
        
        total_updated = (
            result_articles.get("updated_count", 0) + 
            result_transcriptions.get("updated_count", 0)
        )
        
        logger.info(f"✅ Sentiment batch terminé: {total_updated} contenus mis à jour")
        
        return {
            "articles_updated": result_articles.get("updated_count", 0),
            "transcriptions_updated": result_transcriptions.get("updated_count", 0),
            "total_updated": total_updated
        }
        
    except Exception as e:
        logger.error(f"Erreur analyse sentiment batch: {e}")
        raise

async def media_noise_calculation_job():
    """Calcul périodique du bruit médiatique"""
    if not ENABLE_MEDIA_NOISE:
        logger.info("Calcul bruit médiatique désactivé")
        return
    
    logger.info("📊 Démarrage calcul bruit médiatique")
    
    try:
        if not MediaNoiseService:
            logger.error("MediaNoiseService non disponible")
            return
        
        service = MediaNoiseService()
        
        # Calcul pour différentes périodes
        results = {}
        
        for period in ["24h", "7d"]:
            noise_data = service.calculate_media_noise(period=period)
            results[period] = {
                "noise_score": noise_data.get("noise_score", 0),
                "total_items": noise_data.get("details", {}).get("total_items", 0)
            }
        
        # Analyse des thèmes
        themes_analysis = service.analyze_themes(period="7d", limit=5)
        results["themes"] = {
            "total_analyzed": themes_analysis.get("total_content_analyzed", 0),
            "top_themes": list(themes_analysis.get("themes", {}).keys())[:3]
        }
        
        logger.info(
            f"✅ Bruit médiatique calculé: "
            f"24h={results.get('24h', {}).get('noise_score', 0)}, "
            f"7d={results.get('7d', {}).get('noise_score', 0)}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Erreur calcul bruit médiatique: {e}")
        raise

async def daily_digest_job():
    """Génération du digest quotidien enrichi"""
    logger.info("📋 Démarrage génération digest quotidien")
    
    try:
        # Import du service digest existant
        try:
            from backend.summary_service import SummaryService
            summary_service = SummaryService()
        except ImportError:
            logger.warning("SummaryService non disponible")
            return
        
        # Génération digest standard
        today = datetime.now().strftime("%Y-%m-%d")
        digest_result = summary_service.generate_daily_digest(date_str=today)
        
        # Enrichissement avec données sentiment/bruit médiatique
        enrichments = {}
        
        if ENABLE_SENTIMENT_ANALYSIS and SentimentAnalysisService:
            sentiment_service = SentimentAnalysisService()
            sentiment_data = sentiment_service.analyze_period_sentiment(period="24h")
            enrichments["sentiment"] = {
                "overall": sentiment_data.get("overall_sentiment", "neutral"),
                "score": sentiment_data.get("average_score", 0.0),
                "distribution": sentiment_data.get("sentiment_percentages", {})
            }
        
        if ENABLE_MEDIA_NOISE and MediaNoiseService:
            noise_service = MediaNoiseService()
            noise_data = noise_service.calculate_media_noise(period="24h")
            enrichments["media_noise"] = {
                "score": noise_data.get("noise_score", 0),
                "top_themes": list(noise_data.get("themes", {}).keys())[:3],
                "active_zones": list(noise_data.get("zones", {}).keys())[:3]
            }
        
        result = {
            "digest": digest_result,
            "enrichments": enrichments,
            "generation_time": datetime.now().isoformat()
        }
        
        logger.info("✅ Digest quotidien généré avec enrichissements")
        return result
        
    except Exception as e:
        logger.error(f"Erreur génération digest: {e}")
        raise

async def cleanup_job():
    """Nettoyage périodique des données anciennes"""
    logger.info("🧹 Démarrage nettoyage automatique")
    
    try:
        # Import des services de base
        from backend.db import get_db
        db = get_db()
        
        if db is None:
            logger.warning("Base de données non disponible")
            return
        
        cleanup_stats = {
            "old_articles_removed": 0,
            "old_transcriptions_removed": 0,
            "old_logs_removed": 0
        }
        
        # Suppression articles très anciens (>6 mois)
        cutoff_date = datetime.now() - timedelta(days=180)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        old_articles = db["articles_guadeloupe"].delete_many({
            "date": {"$lt": cutoff_str}
        })
        cleanup_stats["old_articles_removed"] = old_articles.deleted_count
        
        # Suppression transcriptions très anciennes (>3 mois)
        cutoff_transcriptions = datetime.now() - timedelta(days=90)
        old_transcriptions = db["radio_transcriptions"].delete_many({
            "captured_at": {"$lt": cutoff_transcriptions}
        })
        cleanup_stats["old_transcriptions_removed"] = old_transcriptions.deleted_count

        # ── Nettoyage audio GridFS (radio_audio.files / radio_audio.chunks) ──
        # Les transcriptions sont supprimées ci-dessus mais les fichiers audio
        # GridFS restent orphelins → stockage qui grimpe indéfiniment
        cleanup_stats["audio_files_removed"] = 0
        cleanup_stats["audio_chunks_freed_mb"] = 0
        try:
            import gridfs
            grid_fs = gridfs.GridFS(db, collection="radio_audio")
            audio_files_col = db["radio_audio.files"]
            audio_chunks_col = db["radio_audio.chunks"]

            # 1. Supprimer les fichiers audio de plus de 7 jours
            # (les transcriptions sont déjà extraites, on n'a plus besoin de l'audio)
            audio_cutoff = datetime.now() - timedelta(days=7)
            old_audio_files = list(audio_files_col.find(
                {"uploadDate": {"$lt": audio_cutoff}},
                {"_id": 1, "length": 1}
            ))

            total_bytes = 0
            for af in old_audio_files:
                total_bytes += af.get("length", 0)
                try:
                    grid_fs.delete(af["_id"])
                except Exception:
                    # Fallback : supprimer manuellement fichier + chunks
                    audio_chunks_col.delete_many({"files_id": af["_id"]})
                    audio_files_col.delete_one({"_id": af["_id"]})

            cleanup_stats["audio_files_removed"] = len(old_audio_files)
            cleanup_stats["audio_chunks_freed_mb"] = round(total_bytes / (1024 * 1024), 1)

            # 2. Nettoyer les chunks orphelins (dont le fichier parent n'existe plus)
            all_file_ids = set(
                f["_id"] for f in audio_files_col.find({}, {"_id": 1})
            )
            orphan_result = audio_chunks_col.delete_many({
                "files_id": {"$nin": list(all_file_ids)}
            }) if all_file_ids else None
            orphan_count = orphan_result.deleted_count if orphan_result else 0
            if orphan_count > 0:
                cleanup_stats["orphan_chunks_removed"] = orphan_count
                logger.info(f"   🧹 {orphan_count} chunks audio orphelins supprimés")

            logger.info(
                f"   🎙️ Audio: {len(old_audio_files)} fichiers supprimés "
                f"({cleanup_stats['audio_chunks_freed_mb']} MB libérés)"
            )
        except Exception as audio_err:
            logger.warning(f"⚠️ Nettoyage audio GridFS: {audio_err}")

        logger.info(
            f"✅ Nettoyage terminé: "
            f"{cleanup_stats['old_articles_removed']} articles, "
            f"{cleanup_stats['old_transcriptions_removed']} transcriptions, "
            f"{cleanup_stats.get('audio_files_removed', 0)} fichiers audio supprimés"
        )
        
        return cleanup_stats
        
    except Exception as e:
        logger.error(f"Erreur nettoyage: {e}")
        raise

async def affair_lifecycle_job():
    """Tâche automatique : cycle de vie des affaires (clustering, promotion, fusion, ré-affiliation)"""
    logger.info("🔄 Démarrage cycle de vie des affaires automatique")
    try:
        from backend.affair_lifecycle_service import get_affair_lifecycle_service
        svc = get_affair_lifecycle_service()
        if not svc:
            logger.warning("AffairLifecycleService non disponible")
            return
        result = svc.run_simple_cycle()
        logger.info(
            f"✅ Cycle affaires terminé: "
            f"{result.get('promoted', 0)} promues, "
            f"{result.get('inter_merged', 0)} fusionnées, "
            f"{result.get('reaffiliated', 0)} ré-affiliées"
        )
        return result
    except Exception as e:
        logger.error(f"Erreur cycle affaires: {e}")
        raise

async def telegram_morning_digest_job():
    """Briefing matinal GPT envoyé sur Telegram — résumé des affaires actives des dernières 24h."""
    logger.info("📰 Génération du digest matinal GPT pour Telegram...")
    try:
        from pymongo import MongoClient
        from backend.telegram_alerts_service import TelegramAlertsService
        from backend.ai_groq_service import _call_ai, is_available as ai_available

        mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
        if not mongo_uri:
            logger.warning("MongoDB URI manquant pour digest matinal")
            return

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
        db = client.get_default_database()

        # Récupérer les affaires actives triées par BMG
        affairs = list(db["affairs"].find(
            {"status": "active"},
            {"title": 1, "gravity_score": 1, "bmg": 1, "priority": 1,
             "sentiment": 1, "item_count": 1, "theme": 1, "elected": 1,
             "last_activity": 1, "description": 1}
        ).sort("bmg", -1).limit(15))

        if not affairs:
            logger.info("📰 Aucune affaire active → pas de digest")
            client.close()
            return

        # Récupérer les stats des dernières 24h
        cutoff = datetime.utcnow() - timedelta(hours=24)
        new_articles_24h = db["articles_guadeloupe"].count_documents({
            "scraped_at": {"$gte": cutoff}
        })
        new_transcriptions_24h = db["radio_transcriptions"].count_documents({
            "captured_at": {"$gte": cutoff}
        })

        # Construire le prompt pour GPT
        affairs_text = []
        for i, aff in enumerate(affairs[:10], 1):
            bmg = aff.get("bmg", 0)
            gravity = aff.get("gravity_score", 0)
            sentiment = aff.get("sentiment", "neutre")
            items = aff.get("item_count", 0)
            title = aff.get("title", "?")
            elected = ", ".join((aff.get("elected", []) or [])[:3])
            priority = aff.get("priority", "minor")
            desc = (aff.get("description", "") or "")[:150]

            line = (f"{i}. [{priority.upper()}] {title} "
                    f"(BMG={round(bmg*100) if bmg < 2 else round(bmg)}, "
                    f"gravity={round(gravity*100)}%, sentiment={sentiment}, "
                    f"{items} items)")
            if elected:
                line += f" — Élus: {elected}"
            if desc:
                line += f"\n   {desc}"
            affairs_text.append(line)

        affairs_block = "\n".join(affairs_text)

        gpt_prompt = f"""Tu es l'éditeur en chef de la veille médiatique Guadeloupe.
Rédige un BRIEFING MATINAL concis (max 600 mots) pour Telegram.

Données du jour :
- {len(affairs)} affaires actives, {new_articles_24h} nouveaux articles, {new_transcriptions_24h} transcriptions radio (24h)

Top affaires :
{affairs_block}

Structure ton briefing en HTML (pour Telegram) :
1. <b>🌅 Briefing du [date]</b> — accroche en 1 phrase
2. <b>🔥 Affaires prioritaires</b> — 2-3 affaires HOT/WATCH avec analyse
3. <b>📊 Tendances</b> — sentiment général, thèmes dominants
4. <b>👁️ À surveiller</b> — 1-2 points de vigilance

Sois direct, journalistique, sans blabla. Utilise des emojis sobrement.
Pas de Markdown, que du HTML (balises <b>, <i>, <u>).
Ne dépasse pas 4000 caractères."""

        # Appel GPT
        digest_text = None
        if ai_available():
            raw = _call_ai(
                messages=[
                    {"role": "system", "content": "Tu es un éditeur de veille médiatique pour la Guadeloupe. Réponds en HTML pour Telegram."},
                    {"role": "user", "content": gpt_prompt},
                ],
                temperature=0.4,
                max_tokens=1200,
                json_mode=False,
            )
            if raw:
                digest_text = raw.strip()

        if not digest_text:
            # Fallback sans GPT — juste la liste
            lines = [f"<b>📰 Briefing Veille Guadeloupe</b>\n"]
            lines.append(f"📊 {len(affairs)} affaires actives | {new_articles_24h} articles | {new_transcriptions_24h} radios (24h)\n")
            for aff in affairs[:5]:
                emoji = "🔴" if aff.get("priority") == "hot" else "🟠" if aff.get("priority") == "watch" else "🔵"
                lines.append(f"{emoji} <b>{aff.get('title', '?')[:60]}</b> — BMG {round(aff.get('bmg', 0) * 100 if aff.get('bmg', 0) < 2 else aff.get('bmg', 0))}")
            digest_text = "\n".join(lines)

        # Envoyer sur Telegram
        tg = TelegramAlertsService()
        sent = False
        if tg.bot or tg.telegram_token:
            sent = await tg.send_alert(digest_text[:4000])
        if not sent:
            tg._send_via_http(digest_text[:4000])

        # Sauvegarder le digest en DB
        db["digests"].insert_one({
            "type": "morning_telegram",
            "content": digest_text,
            "affairs_count": len(affairs),
            "articles_24h": new_articles_24h,
            "transcriptions_24h": new_transcriptions_24h,
            "generated_at": datetime.utcnow(),
            "sent": True,
        })

        client.close()
        logger.info(f"📰 Digest matinal envoyé ({len(digest_text)} chars, {len(affairs)} affaires)")
        return {"sent": True, "length": len(digest_text), "affairs": len(affairs)}

    except Exception as e:
        logger.error(f"Erreur digest matinal: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


async def gpt_affair_cleanup_job():
    """Nettoyage GPT périodique des affaires — retire les articles mal classés."""
    logger.info("🧹🧠 Nettoyage GPT des affaires...")
    try:
        from backend.affair_lifecycle_service import get_affair_lifecycle_service
        svc = get_affair_lifecycle_service()
        if not svc:
            logger.warning("AffairLifecycleService non disponible")
            return
        result = svc.cleanup_all_affairs()
        logger.info(f"🧹🧠 Cleanup GPT: {result.get('total_removed', 0)} articles retirés de {result.get('affairs_cleaned', 0)} affaires")
        return result
    except Exception as e:
        logger.error(f"Erreur cleanup GPT: {e}")
        raise


async def stale_active_crosscheck_job():
    """Cross-check GPT : compare les affaires en veille aux actives pour fusion."""
    logger.info("🔄🧠 Cross-check stale ↔ active...")
    try:
        from backend.affair_lifecycle_service import get_affair_lifecycle_service
        svc = get_affair_lifecycle_service()
        if not svc:
            logger.warning("AffairLifecycleService non disponible")
            return
        merged = svc._cross_check_stale_active()
        logger.info(f"🔄🧠 Cross-check stale↔active: {merged} affaires fusionnées")
        return {"merged": merged}
    except Exception as e:
        logger.error(f"Erreur cross-check stale↔active: {e}")
        raise


async def classify_communes_job():
    """Classifie les articles sans commune par regex + IA fallback."""
    logger.info("📍 Classification communes en cours...")
    try:
        try:
            from backend.affair_lifecycle_service import classify_article_commune
            from backend.affair_lifecycle_service import get_affair_lifecycle_service
        except ImportError:
            from affair_lifecycle_service import classify_article_commune
            from affair_lifecycle_service import get_affair_lifecycle_service
        svc = get_affair_lifecycle_service()
        if not svc:
            return
        articles = list(svc.articles.find({
            "$or": [
                {"communes": {"$exists": False}},
                {"communes": []},
                {"communes": None},
            ]
        }).limit(200))
        updated = 0
        for art in articles:
            communes = classify_article_commune(art)
            if communes:
                svc.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"communes": communes}}
                )
                updated += 1
        logger.info(f"📍 Classification communes: {updated}/{len(articles)} articles classifiés")
        return {"classified": updated, "total_checked": len(articles)}
    except Exception as e:
        logger.error(f"Erreur classification communes: {e}")
        raise


async def social_stats_scrape_job():
    """Tâche automatique : scraping stats RS propres via Apify (toutes les 48h)"""
    logger.info("📊 Scraping stats RS propres (Apify)...")
    try:
        from backend.social_stats_scraper import scrape_own_social_stats, is_configured as ss_configured
        if not ss_configured():
            logger.debug("Social stats scraper non configuré — ignoré")
            return
        result = scrape_own_social_stats()
        logger.info(f"📊 Stats RS: {result.get('updated', 0)} MAJ, {result.get('created', 0)} créés")
        return result
    except Exception as e:
        logger.error(f"Erreur scraping stats RS: {e}")


async def facebook_telegram_sync_job():
    """Tâche automatique : synchronisation Facebook → Telegram"""
    logger.info("📘 Synchronisation Facebook → Telegram...")
    try:
        from backend.facebook_telegram_service import sync_facebook_to_telegram, is_configured as fb_configured
        if not fb_configured():
            logger.debug("Facebook non configuré — sync ignorée")
            return
        result = sync_facebook_to_telegram()
        logger.info(f"📘 FB→TG: {result.get('sent', 0)} envoyés, {result.get('skipped', 0)} ignorés")
        return result
    except Exception as e:
        logger.error(f"Erreur sync Facebook→Telegram: {e}")
        raise


async def storage_monitor_job():
    """Tâche automatique : vérification stockage MongoDB Atlas (512 Mo free tier)"""
    logger.info("💾 Vérification stockage MongoDB...")
    try:
        from pymongo import MongoClient
        mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
        if not mongo_uri:
            logger.warning("MONGODB_URI non configuré pour le monitoring stockage")
            return

        client = MongoClient(mongo_uri)
        db_name = os.environ.get("MONGODB_DB", "veille_guadeloupe")
        db = client[db_name]

        # Récupérer les stats de la base
        stats = db.command("dbStats")
        data_size_mb = round(stats.get("dataSize", 0) / (1024 * 1024), 1)
        storage_size_mb = round(stats.get("storageSize", 0) / (1024 * 1024), 1)
        index_size_mb = round(stats.get("indexSize", 0) / (1024 * 1024), 1)
        total_used_mb = round(data_size_mb + index_size_mb, 1)

        # Atlas Free Tier = 512 Mo
        atlas_limit_mb = int(os.environ.get("ATLAS_STORAGE_LIMIT_MB", "512"))
        usage_pct = round((total_used_mb / atlas_limit_mb) * 100, 1) if atlas_limit_mb > 0 else 0

        # Stats par collection
        collections_stats = []
        for coll_name in db.list_collection_names():
            try:
                coll_stats = db.command("collStats", coll_name)
                coll_size = round(coll_stats.get("storageSize", 0) / (1024 * 1024), 2)
                coll_count = coll_stats.get("count", 0)
                collections_stats.append({
                    "name": coll_name,
                    "size_mb": coll_size,
                    "count": coll_count,
                })
            except Exception:
                pass

        collections_stats.sort(key=lambda x: x["size_mb"], reverse=True)
        result = {
            "data_size_mb": data_size_mb,
            "storage_size_mb": storage_size_mb,
            "index_size_mb": index_size_mb,
            "total_used_mb": total_used_mb,
            "limit_mb": atlas_limit_mb,
            "usage_pct": usage_pct,
            "collections": collections_stats[:10],
            "checked_at": datetime.now().isoformat(),
        }

        logger.info(f"💾 Stockage: {total_used_mb} Mo / {atlas_limit_mb} Mo ({usage_pct}%)")

        # Alertes Telegram si seuil dépassé
        if usage_pct >= 80:
            try:
                from backend.telegram_alerts_service import TelegramAlertsService

                tg = TelegramAlertsService()
                if tg.bot or tg.bot_token:
                    top_colls = "\n".join(
                        f"  • {c['name']}: {c['size_mb']} Mo ({c['count']} docs)"
                        for c in collections_stats[:5]
                    )

                    if usage_pct >= 95:
                        emoji = "🔴"
                        level = "CRITIQUE"
                        extra = "\n\n⚠️ <b>Action immédiate requise !</b> Le stockage est presque plein. Lancez un nettoyage ou supprimez des anciennes données."
                    elif usage_pct >= 90:
                        emoji = "🟠"
                        level = "ÉLEVÉ"
                        extra = "\n\n⚠️ Pensez à lancer un nettoyage pour libérer de l'espace."
                    else:
                        emoji = "🟡"
                        level = "ATTENTION"
                        extra = ""

                    msg = (
                        f"{emoji} <b>Alerte Stockage MongoDB — {level}</b>\n\n"
                        f"📊 <b>{total_used_mb} Mo / {atlas_limit_mb} Mo ({usage_pct}%)</b>\n"
                        f"  • Données : {data_size_mb} Mo\n"
                        f"  • Index : {index_size_mb} Mo\n\n"
                        f"📁 <b>Top collections :</b>\n{top_colls}"
                        f"{extra}"
                    )
                    await tg.send_alert(msg)
                    logger.info(f"📨 Alerte stockage Telegram envoyée ({usage_pct}%)")
            except Exception as tg_err:
                logger.warning(f"Telegram storage alert error: {tg_err}")

        client.close()
        return result

    except Exception as e:
        logger.error(f"Erreur monitoring stockage: {e}")
        raise


def setup_scheduler_jobs():
    """Configuration de toutes les tâches planifiées"""
    if not scheduler:
        logger.error("Scheduler non initialisé")
        return
    
    timezone = pytz.timezone(TIMEZONE)
    
    # 1. Scraping avec sentiment - Toutes les heures
    scheduler.add_job(
        enhanced_scraping_job,
        trigger=CronTrigger(minute=0, timezone=timezone),  # minute 0 de chaque heure
        id="enhanced_scraping",
        name="Scraping amélioré avec sentiment",
        replace_existing=True,
        max_instances=1
    )
    
    # 2. Analyse sentiment batch - Toutes les 30 minutes
    if ENABLE_SENTIMENT_ANALYSIS:
        scheduler.add_job(
            sentiment_batch_analysis_job,
            trigger=IntervalTrigger(minutes=30),
            id="sentiment_batch",
            name="Analyse sentiment batch",
            replace_existing=True,
            max_instances=1
        )
    
    # 3. Calcul bruit médiatique - Toutes les 2 heures
    if ENABLE_MEDIA_NOISE:
        scheduler.add_job(
            media_noise_calculation_job,
            trigger=CronTrigger(minute=15, hour="*/2", timezone=timezone),  # 0h15, 2h15, 4h15...
            id="media_noise_calculation",
            name="Calcul bruit médiatique",
            replace_existing=True,
            max_instances=1
        )
    
    # 4. Digest quotidien - 12h locales
    scheduler.add_job(
        daily_digest_job,
        trigger=CronTrigger(hour=12, minute=0, timezone=timezone),
        id="daily_digest",
        name="Digest quotidien enrichi",
        replace_existing=True,
        max_instances=1
    )
    
    # 5. Nettoyage - 2h du matin
    scheduler.add_job(
        cleanup_job,
        trigger=CronTrigger(hour=2, minute=0, timezone=timezone),
        id="cleanup",
        name="Nettoyage automatique",
        replace_existing=True,
        max_instances=1
    )

    # 6. Cycle de vie des affaires - Toutes les 30 min
    # Clustering, promotion, fusion doublons, ré-affiliation orphelins
    scheduler.add_job(
        affair_lifecycle_job,
        trigger=IntervalTrigger(minutes=30),
        id="affair_lifecycle",
        name="Cycle de vie des affaires (auto)",
        replace_existing=True,
        max_instances=1
    )

    # 7. Monitoring stockage — toutes les 6h
    scheduler.add_job(
        storage_monitor_job,
        trigger=CronTrigger(hour="*/6", minute=45, timezone=timezone),
        id="storage_monitor",
        name="Monitoring stockage MongoDB",
        replace_existing=True,
        max_instances=1
    )

    # 8. Digest matinal GPT Telegram — 7h du matin
    scheduler.add_job(
        telegram_morning_digest_job,
        trigger=CronTrigger(hour=7, minute=0, timezone=timezone),
        id="telegram_morning_digest",
        name="Briefing matinal GPT Telegram",
        replace_existing=True,
        max_instances=1
    )

    # 9. Nettoyage GPT des affaires — toutes les 6h
    scheduler.add_job(
        gpt_affair_cleanup_job,
        trigger=CronTrigger(hour="*/6", minute=15, timezone=timezone),
        id="gpt_affair_cleanup",
        name="Nettoyage GPT affaires (anti-pollution)",
        replace_existing=True,
        max_instances=1
    )

    # 10. Cross-check stale ↔ active (GPT) — toutes les 30 min (offset 15)
    scheduler.add_job(
        stale_active_crosscheck_job,
        trigger=IntervalTrigger(minutes=30),
        id="stale_active_crosscheck",
        name="Cross-check GPT stale↔active (fusion)",
        replace_existing=True,
        max_instances=1
    )

    # 11. Classification communes — toutes les heures
    scheduler.add_job(
        classify_communes_job,
        trigger=CronTrigger(minute=20, timezone=timezone),
        id="classify_communes",
        name="Classification articles par commune (regex+IA)",
        replace_existing=True,
        max_instances=1
    )

    # 12. Sync Facebook → Telegram — toutes les minutes
    scheduler.add_job(
        facebook_telegram_sync_job,
        trigger=IntervalTrigger(minutes=1),
        id="facebook_telegram_sync",
        name="Sync Facebook → Telegram",
        replace_existing=True,
        max_instances=1
    )

    # 13. Scraping stats RS propres via Apify — toutes les 48h
    scheduler.add_job(
        social_stats_scrape_job,
        trigger=IntervalTrigger(hours=48),
        id="social_stats_scrape",
        name="Scraping stats RS (Apify)",
        replace_existing=True,
        max_instances=1
    )

    logger.info("✅ Tâches planifiées configurées:")
    for job in scheduler.get_jobs():
        logger.info(f"   - {job.name} ({job.id}): {job.trigger}")

def attach_scheduler(app):
    """Attache le scheduler à l'application FastAPI"""
    global scheduler, scheduler_stats
    
    if not RUN_SCHEDULER:
        logger.info("Scheduler désactivé via RUN_SCHEDULER=0")
        return
    
    try:
        scheduler = AsyncIOScheduler(timezone=TIMEZONE)
        
        # Ajout du listener pour les événements
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        
        # Configuration des tâches
        setup_scheduler_jobs()
        
        # Démarrage du scheduler
        scheduler.start()
        scheduler_stats["service_status"] = "running"
        
        logger.info(f"🗓️ Scheduler démarré avec {len(scheduler.get_jobs())} tâches")
        logger.info(f"⏰ Timezone: {TIMEZONE}")
        logger.info(f"🎭 Sentiment analysis: {'✅' if ENABLE_SENTIMENT_ANALYSIS else '❌'}")
        logger.info(f"📊 Media noise: {'✅' if ENABLE_MEDIA_NOISE else '❌'}")
        
        # Exécution immédiate du scraping au démarrage (optionnel)
        if os.environ.get("RUN_SCRAPING_ON_START", "0") == "1":
            scheduler.add_job(
                enhanced_scraping_job,
                trigger="date",
                run_date=datetime.now() + timedelta(seconds=30),
                id="startup_scraping",
                name="Scraping de démarrage"
            )
            logger.info("🚀 Scraping de démarrage programmé dans 30s")
        
    except Exception as e:
        logger.error(f"Erreur démarrage scheduler: {e}")
        scheduler_stats["service_status"] = "error"
        raise

def stop_scheduler(app):
    """Arrête proprement le scheduler"""
    global scheduler, scheduler_stats
    
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=True)
            scheduler_stats["service_status"] = "stopped"
            logger.info("🛑 Scheduler arrêté proprement")
        except Exception as e:
            logger.error(f"Erreur arrêt scheduler: {e}")
            scheduler_stats["service_status"] = "error"

# ======================
# Endpoints API Scheduler
# ======================

@router.get("/status")
def get_scheduler_status():
    """Statut du scheduler et des tâches"""
    if not scheduler:
        return {
            "scheduler_running": False,
            "service_status": scheduler_stats["service_status"],
            "error": "Scheduler non initialisé"
        }
    
    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
            "enabled": True
        })
    
    return {
        "scheduler_running": scheduler.running if scheduler else False,
        "service_status": scheduler_stats["service_status"],
        "timezone": TIMEZONE,
        "features_enabled": {
            "sentiment_analysis": ENABLE_SENTIMENT_ANALYSIS,
            "media_noise": ENABLE_MEDIA_NOISE,
            "run_scheduler": RUN_SCHEDULER
        },
        "stats": {
            "jobs_executed": scheduler_stats["jobs_executed"],
            "jobs_failed": scheduler_stats["jobs_failed"],
            "total_jobs": len(jobs_info)
        },
        "jobs": jobs_info,
        "last_executions": scheduler_stats["last_execution"]
    }

@router.get("/jobs")
def get_scheduler_jobs():
    """Liste détaillée des tâches"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler non disponible")
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "func": job.func.__name__,
            "trigger": str(job.trigger),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "last_execution": scheduler_stats["last_execution"].get(job.id),
            "max_instances": job.max_instances,
            "coalesce": job.coalesce,
            "misfire_grace_time": job.misfire_grace_time
        })
    
    return {
        "success": True,
        "total_jobs": len(jobs),
        "jobs": jobs
    }

@router.post("/jobs/{job_id}/run")
def run_job_now(job_id: str):
    """Exécute immédiatement une tâche"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler non disponible")
    
    try:
        job = scheduler.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Tâche {job_id} non trouvée")
        
        # Programmer l'exécution immédiate
        scheduler.add_job(
            job.func,
            trigger="date",
            run_date=datetime.now() + timedelta(seconds=2),
            id=f"{job_id}_manual_{datetime.now().strftime('%H%M%S')}",
            name=f"Exécution manuelle de {job.name}",
            replace_existing=True
        )
        
        return {
            "success": True,
            "message": f"Tâche {job_id} programmée pour exécution immédiate",
            "job_name": job.name
        }
        
    except Exception as e:
        logger.error(f"Erreur exécution manuelle job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str):
    """Met en pause une tâche"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler non disponible")
    
    try:
        scheduler.pause_job(job_id)
        return {
            "success": True,
            "message": f"Tâche {job_id} mise en pause"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):
    """Reprend une tâche en pause"""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler non disponible")
    
    try:
        scheduler.resume_job(job_id)
        return {
            "success": True,
            "message": f"Tâche {job_id} reprise"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
def get_scheduler_stats():
    """Statistiques détaillées du scheduler"""
    if not scheduler:
        return {"error": "Scheduler non disponible"}
    
    # Stats par job
    job_stats = {}
    for job in scheduler.get_jobs():
        job_stats[job.id] = {
            "name": job.name,
            "last_execution": scheduler_stats["last_execution"].get(job.id),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "is_enabled": True  # APScheduler n'a pas de statut enabled/disabled direct
        }
    
    # Prochaines exécutions (24h)
    upcoming = []
    now = datetime.now()
    for job in scheduler.get_jobs():
        if job.next_run_time and job.next_run_time <= now + timedelta(hours=24):
            upcoming.append({
                "job_id": job.id,
                "job_name": job.name,
                "next_run": job.next_run_time.isoformat(),
                "time_until": str(job.next_run_time - now)
            })
    
    upcoming.sort(key=lambda x: x["next_run"])
    
    return {
        "success": True,
        "scheduler_status": scheduler_stats["service_status"],
        "global_stats": {
            "total_jobs": len(scheduler.get_jobs()),
            "jobs_executed": scheduler_stats["jobs_executed"],
            "jobs_failed": scheduler_stats["jobs_failed"],
            "success_rate": round(
                (scheduler_stats["jobs_executed"] / 
                 max(scheduler_stats["jobs_executed"] + scheduler_stats["jobs_failed"], 1)) * 100, 
                1
            )
        },
        "job_stats": job_stats,
        "upcoming_executions": upcoming[:10],  # 10 prochaines
        "features": {
            "sentiment_analysis": ENABLE_SENTIMENT_ANALYSIS,
            "media_noise": ENABLE_MEDIA_NOISE,
            "timezone": TIMEZONE
        }
    }

@router.post("/test-services")
async def test_services():
    """Test des services sentiment et bruit médiatique"""
    results = {}
    
    # Test sentiment analysis
    if ENABLE_SENTIMENT_ANALYSIS and SentimentAnalysisService:
        try:
            service = SentimentAnalysisService()
            test_result = service.analyze_sentiment("Test de sentiment positif pour la Guadeloupe")
            results["sentiment_analysis"] = {
                "status": "ok",
                "test_result": test_result
            }
        except Exception as e:
            results["sentiment_analysis"] = {
                "status": "error",
                "error": str(e)
            }
    else:
        results["sentiment_analysis"] = {
            "status": "disabled",
            "reason": "Service désactivé ou non disponible"
        }
    
    # Test media noise
    if ENABLE_MEDIA_NOISE and MediaNoiseService:
        try:
            service = MediaNoiseService()
            test_result = service.calculate_media_noise(period="24h")
            results["media_noise"] = {
                "status": "ok",
                "test_result": {
                    "noise_score": test_result.get("noise_score", 0),
                    "total_items": test_result.get("details", {}).get("total_items", 0)
                }
            }
        except Exception as e:
            results["media_noise"] = {
                "status": "error",
                "error": str(e)
            }
    else:
        results["media_noise"] = {
            "status": "disabled",
            "reason": "Service désactivé ou non disponible"
        }
    
    # Test enhanced scraper
    if create_enhanced_scraper:
        try:
            scraper = create_enhanced_scraper()
            stats = scraper.get_stats()
            results["enhanced_scraper"] = {
                "status": "ok",
                "stats": stats
            }
        except Exception as e:
            results["enhanced_scraper"] = {
                "status": "error",
                "error": str(e)
            }
    else:
        results["enhanced_scraper"] = {
            "status": "unavailable",
            "reason": "Enhanced scraper non disponible"
        }
    
    return {
        "success": True,
        "test_time": datetime.now().isoformat(),
        "services": results
    }

# ======================
# Fonctions utilitaires pour compatibilité
# ======================

def get_scheduler_instance():
    """Retourne l'instance du scheduler pour usage externe"""
    return scheduler

def is_scheduler_running():
    """Vérifie si le scheduler est en cours d'exécution"""
    return scheduler and scheduler.running

def get_job_next_run(job_id: str):
    """Retourne la prochaine exécution d'une tâche"""
    if not scheduler:
        return None
    
    job = scheduler.get_job(job_id)
    return job.next_run_time if job else None