"""Service d'analyse de sentiment asynchrone avec stockage
Traite les analyses en arrière-plan pour améliorer les performances frontend"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pymongo import MongoClient
import os

# Import GPT sentiment analyzer avec fallback local (relatif)
GPT_AVAILABLE = False
# placeholder pour éviter NameError
gpt_sentiment_analyzer = None
try:
    from .gpt_sentiment_service import gpt_sentiment_analyzer as _gpt
    gpt_sentiment_analyzer = _gpt
    GPT_AVAILABLE = True
    logging.getLogger(__name__).info("✅ GPT sentiment analyzer chargé pour async_sentiment_service")
except ImportError:
    try:
        from .sentiment_analysis_service import local_sentiment_analyzer as _local
        gpt_sentiment_analyzer = _local
        GPT_AVAILABLE = True
        logging.getLogger(__name__).info("✅ Fallback: analyseur local chargé pour async_sentiment_service")
    except ImportError as e:
        logging.getLogger(__name__).warning(f"Aucun analyseur de sentiment disponible (GPT ni local): {e}")

        def gpt_sentiment_analyzer(text):  # type: ignore
            return {"error": "Aucun analyseur de sentiment disponible"}

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AsyncSentimentService:
    def __init__(self):
        """Initialiser le service de sentiment asynchrone"""

        self.initialization_failed = False

        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.sentiment_cache = self.db.sentiment_analysis_cache
            self.processing_queue = self.db.sentiment_processing_queue

            # Index pour optimiser les performances
            self.sentiment_cache.create_index("text_hash")
            self.sentiment_cache.create_index("analyzed_at")
            self.processing_queue.create_index("status")
            self.processing_queue.create_index("priority")

            logger.info("✅ Service sentiment asynchrone initialisé")
        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB sentiment async: {e}")
            self.client = None
            self.db = None
            self.sentiment_cache = None
            self.processing_queue = None
            self.initialization_failed = True

        # Variables de contrôle
        self.processing_active = False
        self.processing_thread = None

        # Statistiques
        self.stats = {
            'analyses_completed': 0,
            'analyses_cached': 0,
            'processing_errors': 0,
            'queue_size': 0
        }

    def start_async_processing(self):
        """Démarrer le traitement asynchrone en arrière-plan"""
        # pymongo Collection objects cannot be used in boolean contexts; comparer à None explicitement
        if self.initialization_failed or self.client is None or self.processing_queue is None:
            logger.error("Impossible de démarrer traitement asynchrone: service mal initialisé (pas de connexion Mongo)")
            return

        if self.processing_active:
            logger.info("⚠️ Traitement asynchrone déjà actif")
            return

        self.processing_active = True
        self.processing_thread = threading.Thread(target=self._process_queue_loop, daemon=True)
        self.processing_thread.start()
        logger.info("🚀 Traitement sentiment asynchrone démarré")

    def stop_async_processing(self):
        """Arrêter le traitement asynchrone"""
        self.processing_active = False
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        logger.info("⏹️ Traitement sentiment asynchrone arrêté")

    def get_text_hash(self, text: str) -> str:
        """Générer un hash unique pour le texte"""
        import hashlib
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def get_cached_sentiment(self, text: str) -> Optional[Dict[str, Any]]:
        """Récupérer l'analyse de sentiment depuis le cache"""
        try:
            if self.initialization_failed or self.client is None:
                return None

            text_hash = self.get_text_hash(text)
            cutoff_time = datetime.now() - timedelta(hours=24)
            cached_result = self.sentiment_cache.find_one({  # type: ignore
                'text_hash': text_hash,
                'analyzed_at': {'$gte': cutoff_time}
            })

            if cached_result:
                self.stats['analyses_cached'] += 1
                logger.info(f"🎯 Sentiment cache HIT pour hash {text_hash[:8]}...")
                result = dict(cached_result)
                result.pop('_id', None)
                result.pop('text_hash', None)
                return result.get('sentiment_result')

            return None
        except Exception as e:
            logger.warning(f"Erreur récupération cache sentiment: {e}")
            return None

    def queue_sentiment_analysis(self, text: str, priority: str = 'normal', context: Dict = None) -> Optional[str]:
        """Ajouter une analyse de sentiment à la queue de traitement"""
        try:
            if self.initialization_failed or self.client is None:
                return None

            text_hash = self.get_text_hash(text)

            # Vérifier si déjà en cache
            cached = self.get_cached_sentiment(text)
            if cached:
                return text_hash

            # Vérifier si déjà en queue
            existing = self.processing_queue.find_one({  # type: ignore
                'text_hash': text_hash,
                'status': {'$in': ['pending', 'processing']}
            })

            if existing:
                logger.info(f"📝 Texte déjà en queue: {text_hash[:8]}...")
                return text_hash

            queue_item = {
                'text_hash': text_hash,
                'text': text[:500],
                'full_text': text,
                'priority': priority,
                'context': context or {},
                'status': 'pending',
                'queued_at': datetime.now(),
                'processing_attempts': 0,
                'max_attempts': 3
            }

            self.processing_queue.insert_one(queue_item)  # type: ignore
            self.stats['queue_size'] += 1
            logger.info(f"📋 Texte ajouté à la queue sentiment: {text_hash[:8]}... (priorité: {priority})")
            return text_hash
        except Exception as e:
            logger.error(f"Erreur ajout queue sentiment: {e}")
            return None

    def get_sentiment_status(self, text_hash: str) -> Dict[str, Any]:
        """Obtenir le statut d'une analyse de sentiment par hash"""
        try:
            if self.initialization_failed or self.client is None:
                return {'status': 'error', 'message': 'Service non disponible'}

            cached_doc = self.sentiment_cache.find_one({'text_hash': text_hash})  # type: ignore
            if cached_doc:
                result = cached_doc.get('sentiment_result')
                return {'status': 'completed', 'result': result}

            queue_item = self.processing_queue.find_one({'text_hash': text_hash})  # type: ignore
            if queue_item:
                return {
                    'status': queue_item.get('status', 'pending'),
                    'queued_at': queue_item.get('queued_at'),
                    'processing_attempts': queue_item.get('processing_attempts', 0),
                    'priority': queue_item.get('priority', 'normal')
                }

            return {'status': 'not_found'}
        except Exception as e:
            logger.error(f"Erreur statut sentiment: {e}")
            return {'status': 'error', 'message': str(e)}

    def _process_queue_loop(self):
        """Boucle principale de traitement de la queue"""
        logger.info("🔄 Démarrage boucle traitement sentiment asynchrone")

        if self.processing_queue is None:
            logger.error("processing_queue absente, arrêt de la boucle sentiment asynchrone")
            return

        while self.processing_active:
            try:
                priority_order = ['high', 'normal', 'low']
                next_item = None

                for priority in priority_order:
                    next_item = self.processing_queue.find_one_and_update(  # type: ignore
                        {
                            'status': 'pending',
                            'priority': priority,
                            'processing_attempts': {'$lt': 3}
                        },
                        {
                            '$set': {
                                'status': 'processing',
                                'processing_started_at': datetime.now()
                            },
                            '$inc': {'processing_attempts': 1}
                        },
                        sort=[('queued_at', 1)]
                    )
                    if next_item:
                        break

                if next_item:
                    self._process_sentiment_item(next_item)
                else:
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Erreur boucle traitement sentiment: {e}")
                time.sleep(10)

    def _process_sentiment_item(self, item: Dict[str, Any]):
        """Traiter un élément de sentiment individuel"""
        text_hash = item['text_hash']
        full_text = item['full_text']

        try:
            logger.info(f"🤖 Traitement sentiment: {text_hash[:8]}... (priorité: {item.get('priority')})")
            start_time = time.time()
            sentiment_result = gpt_sentiment_analyzer.analyze_sentiment(full_text)  # type: ignore
            processing_time = time.time() - start_time

            cache_entry = {
                'text_hash': text_hash,
                'text_preview': full_text[:200],
                'sentiment_result': sentiment_result,
                'analyzed_at': datetime.now(),
                'processing_time': processing_time,
                'processing_context': item.get('context', {})
            }

            self.sentiment_cache.insert_one(cache_entry)  # type: ignore
            self.processing_queue.delete_one({'_id': item['_id']})  # type: ignore

            self.stats['analyses_completed'] += 1
            self.stats['queue_size'] = max(0, self.stats['queue_size'] - 1)

            logger.info(f"✅ Sentiment traité: {text_hash[:8]}... en {processing_time:.2f}s")
        except Exception as e:
            logger.error(f"❌ Erreur traitement sentiment {text_hash[:8]}...: {e}")
            self.processing_queue.update_one(  # type: ignore
                {'_id': item['_id']},
                {
                    '$set': {
                        'status': 'failed',
                        'error': str(e),
                        'failed_at': datetime.now()
                    }
                }
            )
            self.stats['processing_errors'] += 1

    def get_processing_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques du service"""
        try:
            if self.initialization_failed or self.client is None:
                return {'error': 'Service non disponible'}

            queue_stats = {
                'pending': self.processing_queue.count_documents({'status': 'pending'}),  # type: ignore
                'processing': self.processing_queue.count_documents({'status': 'processing'}),  # type: ignore
                'failed': self.processing_queue.count_documents({'status': 'failed'})  # type: ignore
            }

            cache_stats = {
                'total_cached': self.sentiment_cache.count_documents({}),  # type: ignore
                'cached_today': self.sentiment_cache.count_documents({  # type: ignore
                    'analyzed_at': {'$gte': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}
                })
            }

            return {
                'service_active': self.processing_active,
                'queue_stats': queue_stats,
                'cache_stats': cache_stats,
                'processing_stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Erreur stats sentiment async: {e}")
            return {'error': str(e)}

    def cleanup_old_data(self, days: int = 7):
        """Nettoyer les anciennes données"""
        try:
            if self.initialization_failed or self.client is None:
                return {'error': 'Service non disponible'}

            cutoff_date = datetime.now() - timedelta(days=days)
            cache_deleted = self.sentiment_cache.delete_many({  # type: ignore
                'analyzed_at': {'$lt': cutoff_date}
            }).deleted_count
            failed_deleted = self.processing_queue.delete_many({  # type: ignore
                'status': 'failed',
                'failed_at': {'$lt': cutoff_date}
            }).deleted_count

            logger.info(f"🧹 Nettoyage sentiment: {cache_deleted} cache + {failed_deleted} failed supprimés")

            return {
                'cache_deleted': cache_deleted,
                'failed_deleted': failed_deleted,
                'cleanup_date': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Erreur nettoyage sentiment: {e}")
            return {'error': str(e)}


# Instance globale
async_sentiment_service = AsyncSentimentService()

# Fonctions utilitaires

def analyze_text_async(text: str, priority: str = 'normal') -> Optional[str]:
    """Analyser un texte en mode asynchrone"""
    return async_sentiment_service.queue_sentiment_analysis(text, priority)


def get_text_sentiment_cached(text: str) -> Optional[Dict[str, Any]]:
    """Récupérer l'analyse depuis le cache ou None si pas disponible"""
    return async_sentiment_service.get_cached_sentiment(text)


def get_sentiment_analysis_status(text_hash: str) -> Dict[str, Any]:
    """Obtenir le statut d'une analyse"""
    return async_sentiment_service.get_sentiment_status(text_hash)

# Démarrer le service au démarrage du module
if __name__ != "__main__":
    async_sentiment_service.start_async_processing()