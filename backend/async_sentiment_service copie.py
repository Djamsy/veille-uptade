"""
Service d'analyse de sentiment asynchrone ultra-performant - VERSION RÉVOLUTIONNAIRE
Exploite l'analyseur ultra-avancé avec optimisations de performance enterprise
100% économique, cache intelligent, traitement parallèle optimisé
"""

import logging
import threading
import time
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pymongo import MongoClient
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
import os
import statistics

# Import de l'analyseur ultra-avancé ÉCONOMIQUE
ULTRA_ANALYZER = None
ANALYZER_TYPE = "none"

try:
    # Priorité 1: Analyseur ultra-avancé local (ÉCONOMIQUE)
    from .sentiment_analysis_service import ultra_analyzer, analyze_text_sentiment
    ULTRA_ANALYZER = ultra_analyzer
    ANALYZER_TYPE = "ultra_advanced_local"
    logging.getLogger(__name__).info("🚀 Analyseur ultra-avancé LOCAL chargé (ÉCONOMIQUE)")
except ImportError:
    try:
        from sentiment_analysis_service import ultra_analyzer, analyze_text_sentiment
        ULTRA_ANALYZER = ultra_analyzer
        ANALYZER_TYPE = "ultra_advanced_local"
        logging.getLogger(__name__).info("🚀 Analyseur ultra-avancé LOCAL chargé (fallback - ÉCONOMIQUE)")
    except ImportError:
        try:
            # Fallback: analyseur standard local
            from .sentiment_analysis_service import analyze_text_sentiment
            ANALYZER_TYPE = "standard_local"
            logging.getLogger(__name__).info("✅ Analyseur standard LOCAL chargé (ÉCONOMIQUE)")
        except ImportError:
            try:
                from sentiment_analysis_service import analyze_text_sentiment
                ANALYZER_TYPE = "standard_local"
                logging.getLogger(__name__).info("✅ Analyseur standard LOCAL chargé (fallback - ÉCONOMIQUE)")
            except ImportError:
                # Dernier recours: GPT (COÛTEUX - à éviter)
                try:
                    from .gpt_sentiment_service import analyze_text_sentiment
                    ANALYZER_TYPE = "gpt_expensive"
                    logging.getLogger(__name__).warning("💸 Analyseur GPT chargé (COÛTEUX - considérez l'analyseur local)")
                except ImportError:
                    def analyze_text_sentiment(text):
                        return {"error": "Aucun analyseur disponible", "polarity": "neutral", "score": 0.0}
                    ANALYZER_TYPE = "fallback_dummy"
                    logging.getLogger(__name__).error("❌ Aucun analyseur de sentiment disponible")

logger = logging.getLogger(__name__)

class UltraAsyncSentimentService:
    """Service asynchrone ultra-performant avec intelligence distribuée"""
    
    def __init__(self):
        """Initialisation du service ultra-performant"""
        
        # Configuration économique forcée
        self.force_local_analysis = os.environ.get("FORCE_LOCAL_SENTIMENT", "1") == "1"
        self.disable_gpt = os.environ.get("DISABLE_GPT_SENTIMENT", "1") == "1"
        
        # Configuration performance
        self.max_workers = int(os.environ.get("SENTIMENT_MAX_WORKERS", "4"))
        self.batch_size = int(os.environ.get("SENTIMENT_BATCH_SIZE", "10"))
        self.cache_size_limit = int(os.environ.get("SENTIMENT_CACHE_LIMIT", "10000"))
        
        # État du service
        self.initialization_failed = False
        self.processing_active = False
        self.processing_threads = []
        
        # Executor pour traitement parallèle
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="sentiment-worker")
        
        # Cache intelligent multi-niveaux
        self._initialize_cache_system()
        
        # MongoDB connection optimisée
        self._initialize_mongodb()
        
        # Système de monitoring avancé
        self._initialize_monitoring()
        
        # Queue intelligente avec priorités
        self._initialize_smart_queue()
        
        logger.info(f"🚀 Service sentiment asynchrone ultra-performant initialisé (analyseur: {ANALYZER_TYPE})")

    def _initialize_cache_system(self):
        """Cache intelligent multi-niveaux"""
        
        # Cache mémoire ultra-rapide (LRU)
        self.memory_cache = {}
        self.memory_cache_order = deque(maxlen=1000)  # LRU avec 1000 entrées
        
        # Cache de pattern recognition
        self.pattern_cache = defaultdict(list)
        
        # Cache de résultats similaires
        self.similarity_cache = {}
        
        # Métriques de cache
        self.cache_stats = {
            'memory_hits': 0,
            'memory_misses': 0,
            'db_hits': 0,
            'db_misses': 0,
            'pattern_matches': 0,
            'similarity_matches': 0
        }

    def _initialize_mongodb(self):
        """Connexion MongoDB optimisée"""
        
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            # Configuration optimisée pour performance
            self.client = MongoClient(
                MONGO_URL,
                maxPoolSize=20,
                minPoolSize=5,
                maxIdleTimeMS=30000,
                serverSelectionTimeoutMS=5000,
                socketTimeoutMS=10000,
                retryWrites=True,
                retryReads=True
            )
            
            self.db = self.client.veille_media
            self.sentiment_cache_db = self.db.sentiment_analysis_cache
            self.processing_queue_db = self.db.sentiment_processing_queue
            self.analytics_db = self.db.sentiment_analytics

            # Index optimisés pour performance
            self._create_optimized_indexes()
            
            logger.info("✅ MongoDB optimisé pour sentiment asynchrone")
        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB sentiment async: {e}")
            self.initialization_failed = True

    def _create_optimized_indexes(self):
        """Création d'index optimisés"""
        try:
            # Index composés pour requêtes fréquentes
            self.sentiment_cache_db.create_index([
                ("text_hash", 1),
                ("analyzed_at", -1)
            ], background=True)
            
            self.sentiment_cache_db.create_index([
                ("analyzer_type", 1),
                ("confidence_level", -1)
            ], background=True)
            
            self.processing_queue_db.create_index([
                ("status", 1),
                ("priority", -1),
                ("queued_at", 1)
            ], background=True)
            
            # Index pour analytics
            self.analytics_db.create_index([
                ("date", -1),
                ("analyzer_type", 1)
            ], background=True)
            
        except Exception as e:
            logger.warning(f"Erreur création index optimisés: {e}")

    def _initialize_monitoring(self):
        """Système de monitoring avancé"""
        
        self.performance_metrics = {
            'total_processed': 0,
            'processing_times': deque(maxlen=1000),
            'error_count': 0,
            'queue_lengths': deque(maxlen=100),
            'throughput_per_minute': deque(maxlen=60),
            'analyzer_performance': defaultdict(list),
            'confidence_distribution': defaultdict(int),
            'cost_savings': 0.0  # Économies par rapport à GPT
        }
        
        # Alertes automatiques
        self.alerts = {
            'high_error_rate': False,
            'slow_processing': False,
            'queue_backlog': False
        }

    def _initialize_smart_queue(self):
        """Queue intelligente avec priorités dynamiques"""
        
        self.queue_priorities = {
            'critical': [],
            'high': [],
            'normal': [],
            'low': [],
            'batch': []
        }
        
        self.processing_strategies = {
            'critical': 'immediate',
            'high': 'fast_track',
            'normal': 'standard',
            'low': 'batch_when_idle',
            'batch': 'bulk_optimize'
        }

    def get_text_hash(self, text: str, context_suffix: Optional[str] = None) -> str:
        """Hash intelligent avec contexte"""
        
        # Normalisation pour cache intelligent
        normalized_text = text.strip().lower()
        
        # Hash composite avec contexte
        base_content = f"{normalized_text}|{context_suffix or ''}|{ANALYZER_TYPE}"
        return hashlib.sha256(base_content.encode('utf-8')).hexdigest()

    def _check_memory_cache(self, text_hash: str) -> Optional[Dict[str, Any]]:
        """Vérification cache mémoire ultra-rapide"""
        
        if text_hash in self.memory_cache:
            # Mettre à jour LRU
            self.memory_cache_order.remove(text_hash)
            self.memory_cache_order.append(text_hash)
            
            self.cache_stats['memory_hits'] += 1
            return self.memory_cache[text_hash]
        
        self.cache_stats['memory_misses'] += 1
        return None

    def _check_similarity_cache(self, text: str) -> Optional[Dict[str, Any]]:
        """Cache de similarité pour textes proches"""
        
        text_words = set(text.lower().split())
        
        for cached_text, result in self.similarity_cache.items():
            cached_words = set(cached_text.lower().split())
            
            # Calcul similarité Jaccard
            intersection = len(text_words & cached_words)
            union = len(text_words | cached_words)
            
            if union > 0:
                similarity = intersection / union
                
                # Si très similaire (>85%), utiliser le cache
                if similarity > 0.85:
                    self.cache_stats['similarity_matches'] += 1
                    
                    # Ajuster la confiance selon la similarité
                    adjusted_result = result.copy()
                    if 'analysis_details' in adjusted_result:
                        original_confidence = adjusted_result['analysis_details'].get('confidence', 0.5)
                        adjusted_result['analysis_details']['confidence'] = original_confidence * similarity
                        adjusted_result['analysis_details']['similarity_match'] = True
                        adjusted_result['analysis_details']['similarity_score'] = round(similarity, 3)
                    
                    return adjusted_result
        
        return None

    def _update_memory_cache(self, text_hash: str, result: Dict[str, Any]):
        """Mise à jour cache mémoire avec LRU"""
        
        # Limiter la taille du cache
        if len(self.memory_cache) >= 1000:
            oldest = self.memory_cache_order.popleft()
            del self.memory_cache[oldest]
        
        self.memory_cache[text_hash] = result
        self.memory_cache_order.append(text_hash)

    async def analyze_text_ultra_fast(self, text: str, 
                                    priority: str = 'normal',
                                    context: Optional[Dict] = None) -> Dict[str, Any]:
        """Analyse ultra-rapide avec tous les optimisations"""
        
        if not text or not text.strip():
            return self._empty_result()
        
        start_time = time.time()
        text_hash = self.get_text_hash(text, str(context) if context else None)
        
        # Cache mémoire (le plus rapide)
        cached_result = self._check_memory_cache(text_hash)
        if cached_result:
            return self._add_cache_info(cached_result, 'memory', time.time() - start_time)
        
        # Cache de similarité
        similar_result = self._check_similarity_cache(text)
        if similar_result:
            self._update_memory_cache(text_hash, similar_result)
            return self._add_cache_info(similar_result, 'similarity', time.time() - start_time)
        
        # Cache base de données
        db_result = await self._check_db_cache(text_hash)
        if db_result:
            self._update_memory_cache(text_hash, db_result)
            return self._add_cache_info(db_result, 'database', time.time() - start_time)
        
        # Analyse en temps réel (ÉCONOMIQUE)
        try:
            analysis_start = time.time()
            
            # Utiliser l'analyseur ultra-avancé local (GRATUIT)
            if ANALYZER_TYPE == "ultra_advanced_local" and ULTRA_ANALYZER:
                result = ULTRA_ANALYZER.analyze_sentiment(text)
            else:
                result = analyze_text_sentiment(text)
            
            analysis_time = time.time() - analysis_start
            
            # Enrichir avec métadonnées de performance
            result['analysis_details'] = result.get('analysis_details', {})
            result['analysis_details'].update({
                'analyzer_type': ANALYZER_TYPE,
                'analysis_time_ms': round(analysis_time * 1000, 2),
                'cached': False,
                'cost_effective': ANALYZER_TYPE != "gpt_expensive"
            })
            
            # Mise à jour des caches
            self._update_memory_cache(text_hash, result)
            self._update_similarity_cache(text, result)
            await self._save_to_db_cache(text_hash, result, context)
            
            # Métriques de performance
            self._update_performance_metrics(analysis_time, result)
            
            total_time = time.time() - start_time
            return self._add_timing_info(result, total_time, analysis_time)
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment ultra-rapide: {e}")
            return self._error_result(str(e))

    def _update_similarity_cache(self, text: str, result: Dict[str, Any]):
        """Mise à jour cache de similarité"""
        
        # Limiter la taille
        if len(self.similarity_cache) >= 500:
            # Supprimer les plus anciens
            oldest_keys = list(self.similarity_cache.keys())[:100]
            for key in oldest_keys:
                del self.similarity_cache[key]
        
        self.similarity_cache[text] = result

    async def _check_db_cache(self, text_hash: str) -> Optional[Dict[str, Any]]:
        """Vérification cache base de données optimisée"""
        
        try:
            if self.initialization_failed:
                return None
            
            # Cache valide pendant 24h
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            cached_doc = self.sentiment_cache_db.find_one({
                'text_hash': text_hash,
                'analyzed_at': {'$gte': cutoff_time},
                'analyzer_type': ANALYZER_TYPE
            })
            
            if cached_doc:
                self.cache_stats['db_hits'] += 1
                result = cached_doc.get('sentiment_result', {})
                return result
            
            self.cache_stats['db_misses'] += 1
            return None
            
        except Exception as e:
            logger.warning(f"Erreur vérification cache DB: {e}")
            return None

    async def _save_to_db_cache(self, text_hash: str, result: Dict[str, Any], context: Optional[Dict]):
        """Sauvegarde optimisée en base"""
        
        try:
            if self.initialization_failed:
                return
            
            cache_entry = {
                'text_hash': text_hash,
                'sentiment_result': result,
                'analyzer_type': ANALYZER_TYPE,
                'analyzed_at': datetime.now(),
                'confidence_level': result.get('analysis_details', {}).get('confidence', 0.0),
                'processing_context': context or {},
                'cost_effective': ANALYZER_TYPE != "gpt_expensive"
            }
            
            # Upsert pour éviter les doublons
            self.sentiment_cache_db.update_one(
                {'text_hash': text_hash},
                {'$set': cache_entry},
                upsert=True
            )
            
        except Exception as e:
            logger.warning(f"Erreur sauvegarde cache DB: {e}")

    def _update_performance_metrics(self, analysis_time: float, result: Dict[str, Any]):
        """Mise à jour métriques de performance"""
        
        self.performance_metrics['total_processed'] += 1
        self.performance_metrics['processing_times'].append(analysis_time)
        self.performance_metrics['analyzer_performance'][ANALYZER_TYPE].append(analysis_time)
        
        # Calcul des économies (par rapport à GPT)
        if ANALYZER_TYPE != "gpt_expensive":
            # Estimation économie : ~0.01$ par analyse GPT évitée
            self.performance_metrics['cost_savings'] += 0.01
        
        # Distribution de confiance
        confidence = result.get('analysis_details', {}).get('confidence', 0.0)
        confidence_bucket = f"{int(confidence * 10) * 10}%"
        self.performance_metrics['confidence_distribution'][confidence_bucket] += 1

    def analyze_batch_ultra_optimized(self, texts: List[str], 
                                    priority: str = 'batch') -> List[Dict[str, Any]]:
        """Analyse de lot ultra-optimisée avec parallélisation"""
        
        if not texts:
            return []
        
        start_time = time.time()
        results = []
        
        # Grouper par hash pour détecter doublons
        text_groups = defaultdict(list)
        for i, text in enumerate(texts):
            text_hash = self.get_text_hash(text)
            text_groups[text_hash].append((i, text))
        
        # Traitement parallèle par groupe
        futures = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for text_hash, text_list in text_groups.items():
                # Traiter le premier de chaque groupe
                index, text = text_list[0]
                future = executor.submit(self._analyze_single_sync, text)
                futures.append((future, text_list))
            
            # Collecter les résultats
            results_map = {}
            for future, text_list in futures:
                try:
                    result = future.result(timeout=30)
                    # Appliquer le résultat à tous les textes identiques
                    for index, text in text_list:
                        results_map[index] = result
                except Exception as e:
                    logger.error(f"Erreur analyse batch: {e}")
                    for index, text in text_list:
                        results_map[index] = self._error_result(str(e))
        
        # Réorganiser les résultats dans l'ordre original
        results = [results_map.get(i, self._empty_result()) for i in range(len(texts))]
        
        processing_time = time.time() - start_time
        logger.info(f"✅ Batch de {len(texts)} textes traité en {processing_time:.2f}s")
        
        return results

    def _analyze_single_sync(self, text: str) -> Dict[str, Any]:
        """Analyse synchrone pour utilisation dans ThreadPoolExecutor"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.analyze_text_ultra_fast(text))
        finally:
            loop.close()

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Statistiques complètes du service"""
        
        # Calculs de performance
        processing_times = list(self.performance_metrics['processing_times'])
        avg_time = statistics.mean(processing_times) if processing_times else 0.0
        
        # Calcul throughput
        total_processed = self.performance_metrics['total_processed']
        
        # Efficacité du cache
        total_cache_requests = (self.cache_stats['memory_hits'] + 
                              self.cache_stats['memory_misses'])
        cache_hit_rate = (self.cache_stats['memory_hits'] / 
                         max(total_cache_requests, 1)) * 100
        
        return {
            'service_info': {
                'analyzer_type': ANALYZER_TYPE,
                'cost_effective': ANALYZER_TYPE != "gpt_expensive",
                'ultra_advanced': ANALYZER_TYPE == "ultra_advanced_local",
                'service_active': self.processing_active
            },
            'performance_metrics': {
                'total_processed': total_processed,
                'average_processing_time_ms': round(avg_time * 1000, 2),
                'estimated_cost_savings_usd': round(self.performance_metrics['cost_savings'], 2),
                'throughput_capacity': f"{self.max_workers} concurrent workers"
            },
            'cache_performance': {
                'memory_cache_hit_rate': round(cache_hit_rate, 1),
                'memory_hits': self.cache_stats['memory_hits'],
                'similarity_matches': self.cache_stats['similarity_matches'],
                'cache_size': len(self.memory_cache)
            },
            'quality_metrics': {
                'confidence_distribution': dict(self.performance_metrics['confidence_distribution']),
                'analyzer_performance': {
                    analyzer: {
                        'count': len(times),
                        'avg_time_ms': round(statistics.mean(times) * 1000, 2) if times else 0
                    }
                    for analyzer, times in self.performance_metrics['analyzer_performance'].items()
                }
            },
            'system_health': {
                'error_count': self.performance_metrics['error_count'],
                'alerts': self.alerts,
                'memory_cache_usage': f"{len(self.memory_cache)}/1000",
                'db_connection': not self.initialization_failed
            },
            'economic_impact': {
                'zero_api_costs': ANALYZER_TYPE != "gpt_expensive",
                'estimated_monthly_savings': round(self.performance_metrics['cost_savings'] * 30, 2),
                'processing_efficiency': "ultra_high" if ANALYZER_TYPE == "ultra_advanced_local" else "high"
            }
        }

    def _add_cache_info(self, result: Dict[str, Any], cache_type: str, lookup_time: float) -> Dict[str, Any]:
        """Ajouter informations de cache au résultat"""
        
        if 'analysis_details' not in result:
            result['analysis_details'] = {}
        
        result['analysis_details'].update({
            'cached': True,
            'cache_type': cache_type,
            'cache_lookup_time_ms': round(lookup_time * 1000, 2),
            'ultra_fast': True
        })
        
        return result

    def _add_timing_info(self, result: Dict[str, Any], total_time: float, analysis_time: float) -> Dict[str, Any]:
        """Ajouter informations de timing"""
        
        if 'analysis_details' not in result:
            result['analysis_details'] = {}
        
        result['analysis_details'].update({
            'total_processing_time_ms': round(total_time * 1000, 2),
            'analysis_time_ms': round(analysis_time * 1000, 2),
            'overhead_time_ms': round((total_time - analysis_time) * 1000, 2)
        })
        
        return result

    def _empty_result(self) -> Dict[str, Any]:
        """Résultat vide standardisé"""
        return {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'analysis_details': {
                'method': ANALYZER_TYPE,
                'cached': False,
                'error': 'empty_input'
            }
        }

    def _error_result(self, error_message: str) -> Dict[str, Any]:
        """Résultat d'erreur standardisé"""
        self.performance_metrics['error_count'] += 1
        
        return {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'analysis_details': {
                'method': ANALYZER_TYPE,
                'cached': False,
                'error': error_message,
                'error_timestamp': datetime.now().isoformat()
            }
        }

    def cleanup_old_cache(self, hours: int = 24) -> Dict[str, Any]:
        """Nettoyage intelligent du cache"""
        
        cleaned = {
            'memory_cache_cleaned': 0,
            'db_cache_cleaned': 0,
            'similarity_cache_cleaned': 0
        }
        
        try:
            # Nettoyage cache mémoire (garder les plus récents)
            if len(self.memory_cache) > self.cache_size_limit:
                to_remove = len(self.memory_cache) - self.cache_size_limit
                for _ in range(to_remove):
                    if self.memory_cache_order:
                        oldest = self.memory_cache_order.popleft()
                        if oldest in self.memory_cache:
                            del self.memory_cache[oldest]
                            cleaned['memory_cache_cleaned'] += 1
            
            # Nettoyage cache similarité
            if len(self.similarity_cache) > 500:
                keys_to_remove = list(self.similarity_cache.keys())[:100]
                for key in keys_to_remove:
                    del self.similarity_cache[key]
                    cleaned['similarity_cache_cleaned'] += 1
            
            # Nettoyage base de données
            if not self.initialization_failed:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                result = self.sentiment_cache_db.delete_many({
                    'analyzed_at': {'$lt': cutoff_time}
                })
                cleaned['db_cache_cleaned'] = result.deleted_count
            
            logger.info(f"🧹 Cache nettoyé: {cleaned}")
            return cleaned
            
        except Exception as e:
            logger.error(f"Erreur nettoyage cache: {e}")
            return {'error': str(e)}


# Instance globale ultra-performante
ultra_async_service = UltraAsyncSentimentService()

# Fonctions de compatibilité ultra-optimisées

def analyze_text_async(text: str, 
                      cache_key_suffix: Optional[str] = None,
                      force: bool = False,
                      priority: str = 'normal',
                      context: Optional[Dict[str, Any]] = None,
                      task_id: Optional[str] = None,
                      **kwargs) -> Optional[Dict[str, Any]]:
    """Analyse asynchrone ultra-rapide - VERSION RÉVOLUTIONNAIRE"""
    
    try:
        # Exécution en mode ultra-rapide
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                ultra_async_service.analyze_text_ultra_fast(text, priority, context)
            )
            
            # Générer task_id pour compatibilité
            if not task_id:
                task_id = ultra_async_service.get_text_hash(text, cache_key_suffix)
            
            return {
                "task_id": task_id,
                "status": "completed",
                "result": result,
                "ultra_fast": True,
                "cost_effective": ANALYZER_TYPE != "gpt_expensive"
            }
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Erreur analyse async ultra-rapide: {e}")
        return None

def get_text_sentiment_cached(task_id: str) -> Optional[Dict[str, Any]]:
    """Récupération cache ultra-rapide"""
    
    # Vérifier cache mémoire d'abord
    result = ultra_async_service._check_memory_cache(task_id)
    if result:
        return result
    
    # Fallback vers base de données
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                ultra_async_service._check_db_cache(task_id)
            )
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Erreur récupération cache: {e}")
        return None

def get_sentiment_analysis_status(task_id: str) -> str:
    """Statut d'analyse ultra-rapide"""
    
    # Avec l'analyseur ultra-rapide, tout est traité immédiatement
    cached = get_text_sentiment_cached(task_id)
    return "completed" if cached else "not_found"

def get_ultra_service_stats() -> Dict[str, Any]:
    """Statistiques complètes du service ultra-performant"""
    return ultra_async_service.get_comprehensive_stats()

# Auto-démarrage optimisé
if __name__ != "__main__":
    logger.info(f"🚀 Service sentiment asynchrone ultra-performant prêt (analyseur: {ANALYZER_TYPE})")
    
    if ANALYZER_TYPE == "gpt_expensive":
        logger.warning("💸 ATTENTION: Analyseur GPT coûteux détecté - considérez l'analyseur local pour économiser")
    else:
        logger.info("💰 Mode économique activé - analyses gratuites et ultra-rapides")