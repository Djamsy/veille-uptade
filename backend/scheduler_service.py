"""
Service de programmation automatique des tâches
Scraping à 10H et capture radio à 7H
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import logging
from datetime import datetime
from pymongo import MongoClient
import os

# Import des services
try:
    from scraper_service import guadeloupe_scraper
    from radio_service import radio_service
    from summary_service import summary_service
except ImportError as e:
    logging.error(f"Erreur import services: {e}")

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VeilleScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        
        # MongoDB connection pour logs
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.logs_collection = self.db.scheduler_logs
        
        # Configuration des jobs
        self.setup_jobs()
        
    def log_job_execution(self, job_name: str, success: bool, details: str = ""):
        """Logger l'exécution d'un job"""
        log_entry = {
            'job_name': job_name,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        self.logs_collection.insert_one(log_entry)
        
        if success:
            logger.info(f"✅ Job {job_name} réussi: {details}")
        else:
            logger.error(f"❌ Job {job_name} échoué: {details}")

    def job_scrape_articles(self):
        """Job de scraping des articles à 10H"""
        try:
            logger.info("🚀 Début du job de scraping articles...")
            result = guadeloupe_scraper.scrape_all_sites()
            
            if result['success']:
                details = f"{result['total_articles']} articles de {result['sites_scraped']} sites"
                self.log_job_execution("scrape_articles", True, details)
            else:
                self.log_job_execution("scrape_articles", False, f"Erreurs: {result['errors']}")
                
        except Exception as e:
            self.log_job_execution("scrape_articles", False, str(e))

    def job_capture_radio(self):
        """Job de capture radio à 7H"""
        try:
            logger.info("🚀 Début du job de capture radio...")
            result = radio_service.capture_all_streams()
            
            if result['success']:
                details = f"{result['streams_success']} flux capturés sur {result['streams_processed']}"
                self.log_job_execution("capture_radio", True, details)
            else:
                self.log_job_execution("capture_radio", False, f"Erreurs: {result['errors']}")
                
        except Exception as e:
            self.log_job_execution("capture_radio", False, str(e))

    def job_clean_cache_24h(self):
        """Job de nettoyage du cache après 24H"""
        try:
            logger.info("🧹 Début du job de nettoyage du cache 24H...")
            
            # Import du service de cache
            try:
                from cache_service import intelligent_cache
                
                # Nettoyer le cache expiré
                cleaned_count = intelligent_cache.cleanup_expired_cache()
                
                details = f"Cache nettoyé: {cleaned_count} entrées expirées supprimées"
                self.log_job_execution("clean_cache_24h", True, details)
                
                # Envoyer une alerte Telegram si service disponible
                try:
                    from telegram_alerts_service import telegram_alerts
                    if telegram_alerts.bot:
                        message = f"🧹 *Nettoyage Cache Automatique*\n\n✅ {cleaned_count} entrées expirées supprimées\n⏰ {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
                        telegram_alerts.send_alert_sync(message)
                except:
                    pass  # Ignore si Telegram non disponible
                
            except ImportError:
                self.log_job_execution("clean_cache_24h", False, "Service de cache non disponible")
                
        except Exception as e:
            self.log_job_execution("clean_cache_24h", False, str(e))

    def job_create_daily_digest(self):
        """Job de création du digest quotidien à 12H"""
        try:
            logger.info("🚀 Début du job de création du digest...")
            
            # Récupérer les données du jour
            articles = guadeloupe_scraper.get_todays_articles()
            transcriptions = radio_service.get_todays_transcriptions()
            
            # Créer le digest
            digest_html = summary_service.create_daily_digest(articles, transcriptions)
            
            # Sauvegarder le digest
            digest_record = {
                'id': f"digest_{datetime.now().strftime('%Y%m%d')}",
                'date': datetime.now().strftime('%Y-%m-%d'),
                'digest_html': digest_html,
                'articles_count': len(articles),
                'transcriptions_count': len(transcriptions),
                'created_at': datetime.now().isoformat()
            }
            
            self.db.daily_digests.update_one(
                {'id': digest_record['id']},
                {'$set': digest_record},
                upsert=True
            )
            
            details = f"Digest créé: {len(articles)} articles, {len(transcriptions)} transcriptions"
            self.log_job_execution("create_digest", True, details)
            
            # Envoyer alerte Telegram pour le digest
            try:
                from telegram_alerts_service import telegram_alerts
                if telegram_alerts.bot:
                    digest_message = f"""📊 *DIGEST QUOTIDIEN CRÉÉ*

📰 Articles: {len(articles)}
📻 Transcriptions: {len(transcriptions)}
📄 Digest généré avec succès

🕛 Créé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"""
                    
                    telegram_alerts.send_alert_sync(digest_message)
            except:
                pass  # Ignore si Telegram non disponible
            
        except Exception as e:
            self.log_job_execution("create_digest", False, str(e))

    def setup_jobs(self):
        """Configurer les tâches programmées"""
        
        # Job scraping articles TOUTES LES HEURES (au lieu de 10H seulement)
        self.scheduler.add_job(
            func=self.job_scrape_articles,
            trigger=CronTrigger(minute=0),  # Toutes les heures à la minute 0
            id='scrape_articles',
            name='Scraping Articles Horaire',
            replace_existing=True,
            max_instances=1
        )
        
        # Job capture radio à 7H00 tous les jours
        self.scheduler.add_job(
            func=self.job_capture_radio,
            trigger=CronTrigger(hour=7, minute=0),
            id='capture_radio',
            name='Capture Radio 7H',
            replace_existing=True,
            max_instances=1
        )
        
        # Job création digest à 12H00 tous les jours
        self.scheduler.add_job(
            func=self.job_create_daily_digest,
            trigger=CronTrigger(hour=12, minute=0),
            id='create_digest',
            name='Digest Quotidien 12H',
            replace_existing=True,
            max_instances=1
        )
        
        # Job nettoyage cache après 24H (tous les jours à 2H du matin)
        self.scheduler.add_job(
            func=self.job_clean_cache_24h,
            trigger=CronTrigger(hour=2, minute=0),
            id='clean_cache_24h',
            name='Nettoyage Cache 24H',
            replace_existing=True,
            max_instances=1
        )
        
        logger.info("📅 Jobs programmés configurés:")
        logger.info("   - Scraping articles: TOUTES LES HEURES")
        logger.info("   - Capture radio: 7H00")
        logger.info("   - Digest quotidien: 12H00")
        logger.info("   - Nettoyage cache: 2H00 (après 24H)")

    def start(self):
        """Démarrer le scheduler"""
        try:
            self.scheduler.start()
            logger.info("✅ Scheduler démarré")
            
            # Log de démarrage
            self.log_job_execution("scheduler_start", True, "Scheduler démarré avec succès")
            
        except Exception as e:
            logger.error(f"❌ Erreur démarrage scheduler: {e}")
            self.log_job_execution("scheduler_start", False, str(e))

    def stop(self):
        """Arrêter le scheduler"""
        self.scheduler.shutdown()
        logger.info("🛑 Scheduler arrêté")

    def get_job_status(self):
        """Obtenir le statut des jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs

    def get_recent_logs(self, limit: int = 20):
        """Récupérer les logs récents"""
        logs = list(self.logs_collection.find({}, {'_id': 0}).sort('timestamp', -1).limit(limit))
        return logs

    def run_job_manually(self, job_id: str):
        """Exécuter un job manuellement"""
        try:
            if job_id == 'scrape_articles':
                self.job_scrape_articles()
            elif job_id == 'capture_radio':
                self.job_capture_radio()
            elif job_id == 'create_digest':
                self.job_create_daily_digest()
            else:
                raise ValueError(f"Job ID inconnu: {job_id}")
            
            return {"success": True, "message": f"Job {job_id} exécuté manuellement"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}

# Instance globale du scheduler
veille_scheduler = VeilleScheduler()

# Démarrage automatique
def start_scheduler():
    """Démarrer le scheduler au démarrage de l'application"""
    veille_scheduler.start()
    
    # Arrêt propre à la fermeture
    atexit.register(lambda: veille_scheduler.stop())

if __name__ == "__main__":
    # Test du scheduler
    start_scheduler()
    
    # Maintenir le programme en vie
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Arrêt manuel du scheduler")
        veille_scheduler.stop()