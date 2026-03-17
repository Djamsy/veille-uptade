# backend/enhanced_scheduler_service.py
"""
Scheduler simple pour tests
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class EnhancedSchedulerService:
    """Service de planification simple"""
    
    def __init__(self, db, media_noise_service=None, sentiment_service=None, enhanced_scraper=None):
        self.db = db
        self.media_noise_service = media_noise_service
        self.sentiment_service = sentiment_service
        self.enhanced_scraper = enhanced_scraper
        self.is_running = False

    async def start(self):
        """Démarre le scheduler (version simple)"""
        self.is_running = True
        logger.info("🚀 Scheduler simple démarré")

    async def stop(self):
        """Arrête le scheduler"""
        self.is_running = False
        logger.info("🛑 Scheduler simple arrêté")

# Instance simple sans APScheduler pour éviter les erreurs
def create_enhanced_scheduler(db, **kwargs):
    """Crée le scheduler simple"""
    return EnhancedSchedulerService(db, **kwargs)