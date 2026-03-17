# backend/ai_service.py - VERSION MINIMALE SANS OLLAMA
"""
Service AI minimal pour compatibilité
Redirige tout vers tags_index
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class AIService:
    """Service AI minimal sans Ollama"""
    
    def __init__(self):
        self.client_available = False
        self.model_name = "rule_based"
        self.ollama_url = None
        logger.info("✅ AI Service en mode règles (sans Ollama)")
        
        # Charger tags_index pour l'enrichissement
        try:
            from backend.tags_index import infer_tags_and_theme
            self.enrichment_service = infer_tags_and_theme
        except:
            self.enrichment_service = None
    
    def enrich_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichit un article"""
        if self.enrichment_service:
            return self.enrichment_service(article_data)
        return article_data
    
    def classify_transcription_advanced(self, text: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Classifie une transcription"""
        if not self.enrichment_service:
            return {
                "classification": {
                    "is_affair": False,
                    "affair_type": "routine",
                    "gravity_score": 0.3,
                    "confidence": 0.5
                },
                "primary_entity": None,
                "entities_detected": [],
                "method": "fallback"
            }
        
        pseudo_article = {"title": "", "content": text, "text": text}
        enriched = self.enrichment_service(pseudo_article)
        
        return {
            "classification": {
                "is_affair": enriched.get("is_affair", False),
                "affair_type": enriched.get("affair_type", "routine"),
                "gravity_score": enriched.get("gravity_score", 0.3),
                "confidence": enriched.get("classification_confidence", 0.7)
            },
            "primary_entity": enriched.get("elected", [None])[0] if enriched.get("elected") else None,
            "entities_detected": enriched.get("elected", []),
            "theme": enriched.get("theme", "general"),
            "sentiment": enriched.get("sentiment", "neutre"),
            "method": "tags_index"
        }
    
    def health_check(self) -> Dict[str, Any]:
        """État du service"""
        return {
            "status": "operational",
            "ollama_available": False,
            "model": "rule_based",
            "url": None,
            "features": {
                "article_enrichment": True,
                "transcription_classification": True,
                "entity_detection": True,
                "entity_validation": True,
                "mistral_integration": False,
                "variable_scoring": True,
                "hallucination_prevention": True,
                "modular_architecture": True
            }
        }

# Instance singleton
ai_service = AIService()

# Fonctions de compatibilité
def enrich_article(article_data: Dict[str, Any]) -> Dict[str, Any]:
    return ai_service.enrich_article(article_data)

def classify_transcription_advanced(text: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    return ai_service.classify_transcription_advanced(text, metadata)

logger.info("✅ AI Service minimal chargé (sans tentative Ollama)")