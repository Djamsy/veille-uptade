# Remplacez le contenu de backend/async_sentiment_service.py par ce code simplifié

"""
Service d'analyse de sentiment asynchrone SIMPLIFIÉ - SANS CONFLITS EVENT LOOP
Version corrigée pour éviter les blocages et conflicts asyncio
"""

import logging
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pymongo import MongoClient
import os

logger = logging.getLogger(__name__)

# Import de l'analyseur local (synchrone)
try:
    from .sentiment_analysis_service import analyze_text_sentiment
    ANALYZER_AVAILABLE = True
    logger.info("✅ Analyseur local chargé")
except ImportError:
    try:
        from sentiment_analysis_service import analyze_text_sentiment
        ANALYZER_AVAILABLE = True
        logger.info("✅ Analyseur local chargé (fallback)")
    except ImportError:
        ANALYZER_AVAILABLE = False
        logger.error("❌ Aucun analyseur disponible")
        def analyze_text_sentiment(text):
            return {"polarity": "neutral", "score": 0.0, "intensity": "weak"}

class SimpleAsyncSentimentService:
    """Service de sentiment simplifié sans conflits asyncio"""
    
    def __init__(self):
        self.initialization_failed = False
        self.memory_cache = {}
        
        # Stats simples
        self.stats = {
            'total_processed': 0,
            'cache_hits': 0,
            'errors': 0
        }
        
        # MongoDB connection simple
        self._init_mongodb()
    
    def _init_mongodb(self):
        """Connexion MongoDB simple"""
        try:
            MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
            self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
            self.db = self.client.veille_media
            self.sentiment_cache = self.db.sentiment_analysis_cache
            logger.info("✅ MongoDB connecté pour sentiment")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB sentiment: {e}")
            self.initialization_failed = True
    
    def get_text_hash(self, text: str, suffix: str = None) -> str:
        """Hash simple pour le texte"""
        content = f"{text.strip()}{suffix or ''}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def analyze_text_sync(self, text: str, context: Dict = None) -> Dict[str, Any]:
        """Analyse synchrone simple"""
        try:
            if not ANALYZER_AVAILABLE:
                return self._fallback_result(text)
            
            # Cache mémoire
            text_hash = self.get_text_hash(text)
            if text_hash in self.memory_cache:
                self.stats['cache_hits'] += 1
                return self.memory_cache[text_hash]
            
            # Analyse directe
            start_time = time.time()
            result = analyze_text_sentiment(text)
            analysis_time = time.time() - start_time
            
            # Enrichir le résultat
            if 'analysis_details' not in result:
                result['analysis_details'] = {}
            
            result['analysis_details'].update({
                'method': 'local_sync',
                'analysis_time_ms': round(analysis_time * 1000, 2),
                'cached': False,
                'timestamp': datetime.now().isoformat()
            })
            
            # Cache en mémoire (limité à 500 entrées)
            if len(self.memory_cache) > 500:
                # Supprimer les plus anciens
                old_keys = list(self.memory_cache.keys())[:100]
                for key in old_keys:
                    del self.memory_cache[key]
            
            self.memory_cache[text_hash] = result
            self.stats['total_processed'] += 1
            
            # Sauvegarder en DB si disponible
            self._save_to_db(text_hash, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment: {e}")
            self.stats['errors'] += 1
            return self._error_result(str(e))
    
    def _save_to_db(self, text_hash: str, result: Dict[str, Any]):
        """Sauvegarde simple en DB"""
        try:
            if self.initialization_failed:
                return
            
            self.sentiment_cache.update_one(
                {'text_hash': text_hash},
                {
                    '$set': {
                        'text_hash': text_hash,
                        'sentiment_result': result,
                        'analyzed_at': datetime.now(),
                        'method': 'simple_sync'
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.warning(f"Erreur sauvegarde DB: {e}")
    
    def get_cached_sentiment(self, text_hash: str) -> Optional[Dict[str, Any]]:
        """Récupération cache sans asyncio"""
        
        # Cache mémoire d'abord
        if text_hash in self.memory_cache:
            return self.memory_cache[text_hash]
        
        # Cache DB
        try:
            if self.initialization_failed:
                return None
            
            cutoff_time = datetime.now() - timedelta(hours=24)
            doc = self.sentiment_cache.find_one({
                'text_hash': text_hash,
                'analyzed_at': {'$gte': cutoff_time}
            })
            
            if doc:
                result = doc.get('sentiment_result')
                # Ajouter au cache mémoire
                self.memory_cache[text_hash] = result
                return result
                
        except Exception as e:
            logger.warning(f"Erreur récupération cache DB: {e}")
        
        return None
    
    def get_sentiment_status(self, text_hash: str) -> Dict[str, Any]:
        """Statut sans asyncio"""
        cached = self.get_cached_sentiment(text_hash)
        if cached:
            return {'status': 'completed', 'result': cached}
        else:
            return {'status': 'not_found'}
    
    def _fallback_result(self, text: str) -> Dict[str, Any]:
        """Résultat de base si pas d'analyseur"""
        positive_words = ['bien', 'bon', 'excellent', 'super', 'parfait']
        negative_words = ['mal', 'mauvais', 'terrible', 'problème', 'grave']
        
        text_lower = text.lower()
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            polarity, score = 'positive', 0.5
        elif neg_count > pos_count:
            polarity, score = 'negative', -0.5
        else:
            polarity, score = 'neutral', 0.0
        
        return {
            'polarity': polarity,
            'score': score,
            'intensity': 'moderate' if abs(score) > 0.3 else 'weak',
            'analysis_details': {
                'method': 'fallback_basic',
                'confidence': 0.6
            }
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """Résultat d'erreur"""
        return {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'analysis_details': {
                'method': 'error_fallback',
                'error': error_msg,
                'confidence': 0.0
            }
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques simples"""
        return {
            'service_active': True,
            'analyzer_available': ANALYZER_AVAILABLE,
            'memory_cache_size': len(self.memory_cache),
            'stats': self.stats,
            'db_connected': not self.initialization_failed
        }

# Instance globale simplifiée
async_sentiment_service = SimpleAsyncSentimentService()

# Fonctions de compatibilité

def analyze_text_async(text: str, 
                      cache_key_suffix: Optional[str] = None,
                      force: bool = False,
                      priority: str = 'normal',
                      context: Optional[Dict[str, Any]] = None,
                      task_id: Optional[str] = None,
                      **kwargs) -> Optional[Dict[str, Any]]:
    """Analyse 'asynchrone' en mode synchrone pour éviter les conflits"""
    
    try:
        # En réalité synchrone pour éviter les problèmes d'event loop
        result = async_sentiment_service.analyze_text_sync(text, context)
        task_id = task_id or async_sentiment_service.get_text_hash(text, cache_key_suffix)
        
        return {
            "task_id": task_id,
            "status": "completed",
            "result": result
        }
    except Exception as e:
        logger.error(f"Erreur analyse: {e}")
        return None

def get_text_sentiment_cached(task_id: str) -> Optional[Dict[str, Any]]:
    """Récupération cache synchrone"""
    return async_sentiment_service.get_cached_sentiment(task_id)

def get_sentiment_analysis_status(task_id: str) -> Dict[str, Any]:
    """Statut synchrone"""
    return async_sentiment_service.get_sentiment_status(task_id)

# Démarrage automatique
logger.info("🚀 Service sentiment asynchrone SIMPLIFIÉ prêt")
if ANALYZER_AVAILABLE:
    logger.info("💰 Mode économique activé - analyses gratuites et ultra-rapides")
else:
    logger.warning("⚠️ Mode fallback basique - analyseur principal indisponible")