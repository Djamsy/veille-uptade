#!/usr/bin/env python3
"""
Service IA unifié pour l'analyse de contenu média
Optimisé pour détecter les affaires dans l'actualité guadeloupéenne
"""

import os
import re
import logging
import hashlib
import time
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)

class UnifiedAIService:
    """Service IA centralisé pour analyse complète de contenu"""
    
    def __init__(self):
        """Initialisation avec détection automatique des services disponibles"""
        
        # Configuration
        self.use_gpt_fallback = os.environ.get("USE_GPT_FALLBACK", "1") == "1"
        self.gpt_threshold = float(os.environ.get("GPT_THRESHOLD", "0.7"))
        self.cache_enabled = os.environ.get("AI_CACHE_ENABLED", "1") == "1"
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.mistral_model = os.environ.get("OLLAMA_MODEL", "mistral:7b")
        
        # Cache local
        self._cache = {} if self.cache_enabled else None
        
        # Services disponibles
        self.mistral_service = None
        self.gpt_service = None
        self.local_sentiment = None
        self.tags_service = None
        
        # Initialisation des services
        self._initialize_services()
        
        # Statistiques
        self.stats = {
            'total_analyses': 0,
            'mistral_used': 0,
            'gpt_used': 0,
            'cache_hits': 0,
            'errors': 0
        }
        
        logger.info(f"Service IA unifié initialisé - Mistral: {bool(self.mistral_service)}, GPT: {bool(self.gpt_service)}")

    def _initialize_services(self):
        """Initialisation des services d'IA avec fallbacks"""
        
        # 1. Service Mistral local (priorité haute)
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if any('mistral' in m.get('name', '').lower() for m in models):
                    self.mistral_service = True
                    logger.info("✅ Mistral/Ollama détecté et activé")
                else:
                    logger.warning("Ollama disponible mais Mistral non installé")
        except Exception as e:
            logger.info(f"Mistral/Ollama non disponible: {e}")
        
        # 2. Service GPT (fallback)
        if self.use_gpt_fallback:
            try:
                from gpt_sentiment_service import gpt_sentiment_analyzer
                self.gpt_service = gpt_sentiment_analyzer
                logger.info("Service GPT chargé comme fallback")
            except ImportError:
                logger.warning("Service GPT non disponible")
        
        # 3. Service sentiment local
        try:
            from sentiment_analysis_service import analyze_text_sentiment
            self.local_sentiment = analyze_text_sentiment
            logger.info("Service sentiment local chargé")
        except ImportError:
            logger.warning("Service sentiment local non disponible")
        
        # 4. Service tags/entités
        try:
            from tags_index import infer_tags_and_theme
            self.tags_service = infer_tags_and_theme
            logger.info("Service tags/entités chargé")
        except ImportError:
            logger.warning("Service tags non disponible")

    def _analyze_with_mistral(self, text: str, analysis_type: str, **kwargs) -> Dict[str, Any]:
        """Analyse avec Mistral local via Ollama - version optimisée"""
        
        if not self.mistral_service:
            raise NotImplementedError("Mistral non disponible")
        
        try:
            # Prompts optimisés pour l'actualité guadeloupéenne
            if analysis_type == "classification":
                prompt = f"""Analyse cet article de presse de Guadeloupe.
                IMPORTANT: Détecte TOUTES les personnes et organisations mentionnées.
                
                Cherche en priorité:
                - Guy Losbar (président CD971/conseil départemental)
                - Membres du gouvernement français (ministres, secrétaires d'État)  
                - Élus locaux (maires, conseillers, députés, sénateurs)
                - Préfet de Guadeloupe
                - CHU, ARS, Rectorat, autres institutions
                
                Réponds en JSON:
                {{"theme": "politique|economie|social|environnement|culture|faits_divers",
                  "entities": ["liste", "des", "personnes", "et", "organisations"],
                  "confidence": 0.8}}
                
                Texte: {text[:1000]}
                
                JSON:"""
            
            elif analysis_type == "sentiment":
                prompt = f"""Analyse le sentiment. JSON:
                {{"polarity": "positif|neutre|negatif", "score": -1 à 1, "confidence": 0 à 1}}
                
                Texte: {text[:500]}
                
                JSON:"""
            
            # Appel Ollama avec timeout réduit
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.mistral_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 150
                    }
                },
                timeout=10  # Réduit de 30 à 10 secondes
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')
                
                # Parser JSON
                try:
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = response_text[json_start:json_end]
                        parsed = json.loads(json_str)
                        
                        if analysis_type == "classification":
                            entities = parsed.get("entities", [])
                            # Nettoyer les entités
                            entities = [e.strip() for e in entities if e and e.strip() and e.lower() != "aucune"]
                            
                            return {
                                "dominant_theme": parsed.get("theme", "général"),
                                "themes": [parsed.get("theme", "général")],
                                "elected": entities,
                                "confidence": float(parsed.get("confidence", 0.7)),
                                "tags": []
                            }
                        
                        elif analysis_type == "sentiment":
                            return {
                                "polarity": parsed.get("polarity", "neutre"),
                                "score": float(parsed.get("score", 0.0)),
                                "confidence": float(parsed.get("confidence", 0.7)),
                                "analysis_details": {
                                    "confidence": float(parsed.get("confidence", 0.7)),
                                    "method": "mistral"
                                }
                            }
                            
                except json.JSONDecodeError:
                    logger.warning(f"Parse JSON échoué: {response_text[:100]}")
                
                # Fallback extraction par regex si JSON échoue
                return self._extract_entities_fallback(response_text, text, analysis_type)
                
        except requests.exceptions.Timeout:
            logger.warning("Timeout Mistral - passage au fallback")
            raise
        except Exception as e:
            logger.warning(f"Erreur Mistral: {e}")
            raise

    def _extract_entities_fallback(self, response_text: str, original_text: str, analysis_type: str) -> Dict[str, Any]:
        """Extraction d'entités par patterns si Mistral échoue"""
        
        text_lower = original_text.lower()
        entities = []
        
        # Patterns pour détecter les personnes importantes
        patterns = [
            r"guy losbar",
            r"président.*conseil.*départemental",
            r"préfet.*(?:de.*)?(?:la.*)?guadeloupe",
            r"ministre\s+\w+",
            r"maire.*(?:de\s+)?(\w+)",
            r"député.*(\w+)",
            r"sénateur.*(\w+)",
            r"(\w+)\s+barnier",  # Gouvernement Barnier
            r"gabriel\s+attal",
            r"emmanuel\s+macron"
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            entities.extend(matches)
        
        # Noms propres (mots capitalisés consécutifs)
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', original_text)
        entities.extend(proper_nouns)
        
        # Nettoyer et dédupliquer
        entities = list(set([e.strip() for e in entities if len(e) > 3]))
        
        # Détecter le thème
        theme = "général"
        if any(word in text_lower for word in ["élection", "vote", "conseil", "maire", "ministre"]):
            theme = "politique"
        elif any(word in text_lower for word in ["entreprise", "emploi", "économie", "budget"]):
            theme = "economie"
        elif any(word in text_lower for word in ["école", "santé", "hôpital", "chu"]):
            theme = "social"
        
        return {
            "dominant_theme": theme,
            "themes": [theme],
            "elected": entities[:10],  # Limiter à 10 entités
            "confidence": 0.5,
            "tags": []
        }

    def correlate_articles_intelligent(self, articles: List[Dict[str, Any]], 
                                     similarity_threshold: float = 0.4) -> List[Dict[str, Any]]:
        """Corrélation d'articles avec seuil abaissé pour détecter plus d'affaires"""
        
        if not articles or len(articles) < 2:
            return []
        
        correlations = []
        
        # Analyser les corrélations par paires
        for i, article1 in enumerate(articles):
            for j, article2 in enumerate(articles[i+1:], i+1):
                
                correlation = self._calculate_correlation_fast(article1, article2)
                
                # Seuil abaissé à 0.4 pour capturer plus de corrélations
                if correlation['similarity_score'] >= similarity_threshold:
                    correlations.append({
                        'article1_id': str(article1.get('_id', article1.get('id', i))),
                        'article2_id': str(article2.get('_id', article2.get('id', j))),
                        'similarity_score': correlation['similarity_score'],
                        'correlation_type': correlation['type'],
                        'common_elements': correlation['common_elements'],
                        'confidence': correlation['confidence'],
                        'should_group': True
                    })
        
        return correlations

    def _calculate_correlation_fast(self, article1: Dict, article2: Dict) -> Dict[str, Any]:
        """Calcul rapide de corrélation basé sur les données existantes"""
        
        try:
            # Utiliser directement les champs MongoDB
            theme1 = article1.get('theme_principal', 'général')
            theme2 = article2.get('theme_principal', 'général')
            
            entities1 = set(article1.get('entites', []))
            entities2 = set(article2.get('entites', []))
            
            # Nettoyer les entités vides
            entities1 = {e for e in entities1 if e and e != "Aucune"}
            entities2 = {e for e in entities2 if e and e != "Aucune"}
            
            # Score de thème (boost si même thème)
            theme_score = 1.0 if theme1 == theme2 else 0.2
            
            # Score d'entités (très important)
            entity_score = 0.0
            if entities1 and entities2:
                common = entities1 & entities2
                if common:
                    entity_score = len(common) / min(len(entities1), len(entities2))
            
            # Score temporel (articles du même jour = boost)
            date1 = article1.get('date', article1.get('scraped_at', ''))
            date2 = article2.get('date', article2.get('scraped_at', ''))
            temporal_score = 1.0 if date1[:10] == date2[:10] else 0.3
            
            # Score textuel simple (mots en commun dans les titres)
            title1_words = set(article1.get('title', '').lower().split())
            title2_words = set(article2.get('title', '').lower().split())
            text_score = 0.0
            if title1_words and title2_words:
                common_words = title1_words & title2_words
                # Ignorer les mots courts
                common_words = {w for w in common_words if len(w) > 3}
                if common_words:
                    text_score = len(common_words) / min(len(title1_words), len(title2_words))
            
            # Score combiné avec poids ajustés
            similarity_score = (
                theme_score * 0.25 +      # Thème compte pour 25%
                entity_score * 0.35 +      # Entités compte pour 35%
                temporal_score * 0.20 +    # Temporel compte pour 20%
                text_score * 0.20          # Texte compte pour 20%
            )
            
            # Déterminer le type de corrélation
            correlation_type = "general"
            if entity_score > 0.5:
                correlation_type = "same_entities"
            elif theme_score > 0.8 and temporal_score > 0.8:
                correlation_type = "same_theme_same_day"
            elif text_score > 0.5:
                correlation_type = "similar_content"
            
            return {
                'similarity_score': round(similarity_score, 3),
                'type': correlation_type,
                'common_elements': list(entities1 & entities2) if entities1 and entities2 else [],
                'confidence': min(0.9, similarity_score),
                'factors': {
                    'theme': theme_score,
                    'entity': entity_score,
                    'temporal': temporal_score,
                    'textual': text_score
                }
            }
            
        except Exception as e:
            logger.warning(f"Erreur calcul corrélation: {e}")
            return {
                'similarity_score': 0.0,
                'type': 'error',
                'common_elements': [],
                'confidence': 0.0
            }

    def analyze_content_complete(self, title: str, content: str = "", url: str = "") -> Dict[str, Any]:
        """Analyse complète mais optimisée pour la vitesse"""
        
        # Si déjà analysé (cache), retourner rapidement
        cache_key = self._get_cache_key(f"{title}:{content[:200]}", "complete")
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        # Analyse basique rapide si pas Mistral
        if not self.mistral_service:
            result = self._quick_analysis(title, content, url)
        else:
            # Analyse Mistral mais limitée en taille
            full_text = f"{title}. {content[:500]}".strip()  # Limiter le contenu
            
            sentiment_result = self._quick_sentiment(full_text)
            classification_result = self.classify_themes_intelligent(full_text, url)
            
            result = {
                'title': title,
                'sentiment_polarity': sentiment_result.get('polarity', 'neutral'),
                'sentiment_score': sentiment_result.get('score', 0.0),
                'dominant_theme': classification_result.get('dominant_theme', 'général'),
                'elected': classification_result.get('elected', []),
                'themes': classification_result.get('themes', []),
                'analysis_complete': True,
                'analyzed_at': datetime.now().isoformat()
            }
        
        self._save_to_cache(cache_key, result)
        return result

    def _quick_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyse de sentiment rapide par mots-clés"""
        
        text_lower = text.lower()
        
        # Mots positifs/négatifs pour l'actualité
        positive_words = ["succès", "amélioration", "victoire", "nouveau", "inauguration", "création"]
        negative_words = ["crise", "problème", "fermeture", "accident", "grève", "violence"]
        
        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)
        
        if pos_count > neg_count:
            return {"polarity": "positif", "score": 0.5, "confidence": 0.6}
        elif neg_count > pos_count:
            return {"polarity": "negatif", "score": -0.5, "confidence": 0.6}
        else:
            return {"polarity": "neutre", "score": 0.0, "confidence": 0.5}

    def _quick_analysis(self, title: str, content: str, url: str) -> Dict[str, Any]:
        """Analyse rapide sans IA pour fallback"""
        
        full_text = f"{title} {content}".lower()
        
        # Détection thème basique
        theme = "général"
        if any(word in full_text for word in ["élection", "conseil", "maire", "ministre"]):
            theme = "politique"
        elif any(word in full_text for word in ["entreprise", "emploi", "économie"]):
            theme = "economie"
        
        # Extraction d'entités basique
        entities = []
        if "guy losbar" in full_text or "cd971" in full_text:
            entities.append("Guy Losbar")
        if "préfet" in full_text:
            entities.append("Préfet de Guadeloupe")
        
        return {
            'title': title,
            'sentiment_polarity': 'neutre',
            'sentiment_score': 0.0,
            'dominant_theme': theme,
            'elected': entities,
            'themes': [theme],
            'analysis_complete': True,
            'analyzed_at': datetime.now().isoformat()
        }

    # Conserver les autres méthodes existantes...
    def _get_cache_key(self, text: str, analysis_type: str) -> str:
        content = f"{analysis_type}:{text[:500]}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if not self.cache_enabled or not self._cache:
            return None
        result = self._cache.get(cache_key)
        if result:
            self.stats['cache_hits'] += 1
        return result

    def _save_to_cache(self, cache_key: str, result: Dict[str, Any]):
        if not self.cache_enabled or not self._cache:
            return
        if len(self._cache) > 1000:
            oldest_keys = list(self._cache.keys())[:100]
            for key in oldest_keys:
                del self._cache[key]
        self._cache[cache_key] = result

    def analyze_sentiment_intelligent(self, text: str) -> Dict[str, Any]:
        """Conservé pour compatibilité"""
        return self._quick_sentiment(text)

    def classify_themes_intelligent(self, text: str, url: str = "") -> Dict[str, Any]:
        """Classification avec cache et optimisations"""
        
        cache_key = self._get_cache_key(f"{text}:{url}", "themes")
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached
        
        result = None
        
        # Essayer Mistral si disponible
        if self.mistral_service:
            try:
                result = self._analyze_with_mistral(text[:1000], "classification", url=url)
            except Exception as e:
                logger.warning(f"Mistral échoué, fallback: {e}")
        
        # Fallback sur extraction basique
        if not result:
            result = self._extract_entities_fallback("", text, "classification")
        
        self._save_to_cache(cache_key, result)
        return result

    def get_service_stats(self) -> Dict[str, Any]:
        return {
            'services_available': {
                'mistral_local': bool(self.mistral_service),
                'gpt_fallback': bool(self.gpt_service),
                'local_sentiment': bool(self.local_sentiment),
                'tags_service': bool(self.tags_service)
            },
            'usage_stats': self.stats.copy(),
            'cache_enabled': self.cache_enabled,
            'cache_size': len(self._cache) if self._cache else 0
        }

    def clear_cache(self):
        if self._cache:
            self._cache.clear()
            logger.info("Cache vidé")


# Instance globale
unified_ai = UnifiedAIService()

# Fonctions d'interface
def analyze_article_complete(title: str, content: str = "", url: str = "") -> Dict[str, Any]:
    return unified_ai.analyze_content_complete(title, content, url)

def correlate_articles(articles: List[Dict], threshold: float = 0.4) -> List[Dict]:
    return unified_ai.correlate_articles_intelligent(articles, threshold)

def analyze_sentiment_smart(text: str) -> Dict[str, Any]:
    return unified_ai.analyze_sentiment_intelligent(text)

def classify_themes_smart(text: str, url: str = "") -> Dict[str, Any]:
    return unified_ai.classify_themes_intelligent(text, url)