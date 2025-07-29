"""
Service de cache intelligent pour éviter les chargements intempestifs
Cache en mémoire avec mise à jour automatique
"""
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import threading
import logging
from pymongo import MongoClient
import os

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntelligentCache:
    def __init__(self):
        self.cache_data = {}
        self.cache_timestamps = {}
        self.cache_locks = {}
        self.cache_expiry = {
            'dashboard_stats': 86400,  # 24 heures
            'articles_today': 86400,  # 24 heures
            'transcriptions_today': 86400,  # 24 heures
            'digest_today': 86400,  # 24 heures
            'scheduler_status': 86400,  # 24 heures
        }
        
        # MongoDB connection pour le cache persistant
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.cache_collection = self.db.app_cache
            logger.info("✅ Cache service connecté à MongoDB")
        except Exception as e:
            logger.error(f"❌ Erreur connexion cache MongoDB: {e}")
            self.cache_collection = None

    def _get_cache_key(self, key: str, params: Dict = None) -> str:
        """Générer une clé de cache unique"""
        if params:
            param_str = "_".join([f"{k}:{v}" for k, v in sorted(params.items())])
            return f"{key}_{param_str}"
        return key

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Vérifier si le cache est encore valide"""
        if cache_key not in self.cache_timestamps:
            return False
        
        timestamp = self.cache_timestamps[cache_key]
        expiry_seconds = self.cache_expiry.get(cache_key.split('_')[0], 300)  # Default 5 min
        
        return time.time() - timestamp < expiry_seconds

    def get_cached_data(self, key: str, params: Dict = None) -> Optional[Any]:
        """Récupérer des données du cache"""
        cache_key = self._get_cache_key(key, params)
        
        # Vérifier le cache mémoire
        if cache_key in self.cache_data and self._is_cache_valid(cache_key):
            logger.info(f"🎯 Cache HIT (mémoire): {cache_key}")
            return self.cache_data[cache_key]
        
        # Vérifier le cache persistant
        if self.cache_collection is not None:
            try:
                cached_item = self.cache_collection.find_one({'cache_key': cache_key})
                if cached_item and self._is_persistent_cache_valid(cached_item):
                    logger.info(f"🎯 Cache HIT (persistant): {cache_key}")
                    # Restaurer en cache mémoire
                    self.cache_data[cache_key] = cached_item['data']
                    self.cache_timestamps[cache_key] = cached_item['timestamp']
                    return cached_item['data']
            except Exception as e:
                logger.warning(f"Erreur lecture cache persistant: {e}")
        
        logger.info(f"❌ Cache MISS: {cache_key}")
        return None

    def set_cached_data(self, key: str, data: Any, params: Dict = None):
        """Sauvegarder des données en cache"""
        cache_key = self._get_cache_key(key, params)
        current_time = time.time()
        
        # Cache mémoire
        self.cache_data[cache_key] = data
        self.cache_timestamps[cache_key] = current_time
        
        # Cache persistant
        if self.cache_collection:
            try:
                cache_item = {
                    'cache_key': cache_key,
                    'data': data,
                    'timestamp': current_time,
                    'created_at': datetime.now().isoformat(),
                    'expires_at': (datetime.now() + timedelta(seconds=self.cache_expiry.get(key, 300))).isoformat()
                }
                
                self.cache_collection.update_one(
                    {'cache_key': cache_key},
                    {'$set': cache_item},
                    upsert=True
                )
                logger.info(f"💾 Cache SAVED: {cache_key}")
            except Exception as e:
                logger.warning(f"Erreur sauvegarde cache persistant: {e}")

    def _is_persistent_cache_valid(self, cached_item: Dict) -> bool:
        """Vérifier si le cache persistant est valide"""
        try:
            expires_at = datetime.fromisoformat(cached_item['expires_at'])
            return datetime.now() < expires_at
        except:
            return False

    def invalidate_cache(self, pattern: str = None):
        """Invalider le cache selon un pattern"""
        if pattern:
            # Invalider les clés qui matchent le pattern
            keys_to_remove = [k for k in self.cache_data.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache_data[key]
                del self.cache_timestamps[key]
                
            # Invalider dans le cache persistant
            if self.cache_collection:
                try:
                    self.cache_collection.delete_many({'cache_key': {'$regex': pattern}})
                except Exception as e:
                    logger.warning(f"Erreur invalidation cache persistant: {e}")
                    
            logger.info(f"🗑️ Cache invalidé pour pattern: {pattern}")
        else:
            # Invalider tout le cache
            self.cache_data.clear()
            self.cache_timestamps.clear()
            if self.cache_collection:
                try:
                    self.cache_collection.delete_many({})
                except Exception as e:
                    logger.warning(f"Erreur vidage cache persistant: {e}")
            logger.info("🗑️ Tout le cache a été vidé")

    def get_or_compute(self, key: str, compute_func: Callable, params: Dict = None, force_refresh: bool = False) -> Any:
        """Récupérer du cache ou calculer si nécessaire"""
        cache_key = self._get_cache_key(key, params)
        
        # Vérifier le lock pour éviter les calculs simultanés
        if cache_key in self.cache_locks:
            logger.info(f"⏳ Attente du calcul en cours: {cache_key}")
            self.cache_locks[cache_key].wait()
        
        # Essayer le cache d'abord (sauf si force_refresh)
        if not force_refresh:
            cached_data = self.get_cached_data(key, params)
            if cached_data is not None:
                return cached_data
        
        # Créer un lock pour ce calcul
        self.cache_locks[cache_key] = threading.Event()
        
        try:
            logger.info(f"🔄 Calcul en cours: {cache_key}")
            start_time = time.time()
            
            # Exécuter la fonction de calcul
            result = compute_func()
            
            # Sauvegarder en cache
            self.set_cached_data(key, result, params)
            
            calculation_time = time.time() - start_time
            logger.info(f"✅ Calcul terminé: {cache_key} ({calculation_time:.2f}s)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur calcul: {cache_key} - {e}")
            raise e
        finally:
            # Libérer le lock
            if cache_key in self.cache_locks:
                self.cache_locks[cache_key].set()
                del self.cache_locks[cache_key]

    def warm_cache(self):
        """Préchauffer le cache avec les données essentielles"""
        logger.info("🔥 Préchauffage du cache...")
        
        try:
            # Importer les services nécessaires
            from scraper_service import guadeloupe_scraper
            from radio_service import radio_service
            
            # Préchauffer les articles d'aujourd'hui
            def get_articles():
                return guadeloupe_scraper.get_todays_articles()
            
            # Préchauffer les transcriptions d'aujourd'hui
            def get_transcriptions():
                return radio_service.get_todays_transcriptions()
            
            # Exécuter en parallèle
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                executor.submit(lambda: self.get_or_compute('articles_today', get_articles))
                executor.submit(lambda: self.get_or_compute('transcriptions_today', get_transcriptions))
            
            logger.info("✅ Préchauffage du cache terminé")
            
        except Exception as e:
            logger.error(f"❌ Erreur préchauffage cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques du cache"""
        total_keys = len(self.cache_data)
        valid_keys = len([k for k in self.cache_data.keys() if self._is_cache_valid(k)])
        
        return {
            'total_cached_keys': total_keys,
            'valid_cached_keys': valid_keys,
            'expired_keys': total_keys - valid_keys,
            'cache_hit_ratio': (valid_keys / max(total_keys, 1)) * 100,
            'cache_keys': list(self.cache_data.keys()),
            'memory_usage_mb': sum([len(str(v)) for v in self.cache_data.values()]) / (1024*1024)
        }

    def cleanup_expired_cache(self):
        """Nettoyer le cache expiré"""
        expired_keys = [k for k in self.cache_data.keys() if not self._is_cache_valid(k)]
        
        for key in expired_keys:
            del self.cache_data[key]
            del self.cache_timestamps[key]
        
        # Nettoyer le cache persistant
        if self.cache_collection:
            try:
                self.cache_collection.delete_many({
                    'expires_at': {'$lt': datetime.now().isoformat()}
                })
            except Exception as e:
                logger.warning(f"Erreur nettoyage cache persistant: {e}")
        
        if expired_keys:
            logger.info(f"🧹 {len(expired_keys)} clés expirées nettoyées")

# Instance globale du cache
intelligent_cache = IntelligentCache()

# Fonctions utilitaires
def cache_get(key: str, params: Dict = None) -> Optional[Any]:
    """Récupérer du cache (fonction utilitaire)"""
    return intelligent_cache.get_cached_data(key, params)

def cache_set(key: str, data: Any, params: Dict = None):
    """Sauvegarder en cache (fonction utilitaire)"""
    intelligent_cache.set_cached_data(key, data, params)

def cache_invalidate(pattern: str = None):
    """Invalider le cache (fonction utilitaire)"""
    intelligent_cache.invalidate_cache(pattern)

def get_or_compute(key: str, compute_func: Callable, params: Dict = None, force_refresh: bool = False) -> Any:
    """Get or compute avec cache (fonction utilitaire)"""
    return intelligent_cache.get_or_compute(key, compute_func, params, force_refresh)

# Démarrage automatique
def start_cache_service():
    """Démarrer le service de cache"""
    logger.info("🚀 Service de cache intelligent démarré")
    
    # Préchauffer le cache
    intelligent_cache.warm_cache()
    
    # Programmer le nettoyage automatique
    import threading
    import time
    
    def periodic_cleanup():
        while True:
            try:
                time.sleep(3600)  # Toutes les heures
                intelligent_cache.cleanup_expired_cache()
            except Exception as e:
                logger.error(f"Erreur nettoyage périodique: {e}")
    
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()

if __name__ == "__main__":
    # Test du cache
    start_cache_service()
    
    # Test simple
    def test_compute():
        return {"test": "data", "timestamp": time.time()}
    
    # Premier appel (calcul)
    result1 = get_or_compute("test_key", test_compute)
    print(f"Premier appel: {result1}")
    
    # Deuxième appel (cache)
    result2 = get_or_compute("test_key", test_compute)
    print(f"Deuxième appel: {result2}")
    
    # Statistiques
    stats = intelligent_cache.get_cache_stats()
    print(f"Stats cache: {stats}")