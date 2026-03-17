# backend/sentiment_service.py
"""
Service d'analyse de sentiment UNIFIÉ et SIMPLIFIÉ
- GPT si disponible et demandé
- Sinon analyse locale robuste
- Interface unique pour tout le système
"""

import os
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
from functools import lru_cache

logger = logging.getLogger(__name__)


# ============================================================================
# ANALYSEUR LOCAL (Fallback)
# ============================================================================

class LocalSentimentAnalyzer:
    """Analyseur local rapide et gratuit"""
    
    def __init__(self):
        """Initialiser l'analyseur local"""
        
        # Lexique positif optimisé
        self.positive_words = {
            'excellent': 1.5, 'formidable': 1.5, 'magnifique': 1.4,
            'bon': 1.0, 'bien': 1.0, 'succès': 1.3, 'réussi': 1.2,
            'amélioration': 1.1, 'progrès': 1.2, 'nouveau': 0.8,
            'festival': 1.2, 'victoire': 1.3, 'satisfait': 1.0
        }
        
        # Lexique négatif optimisé
        self.negative_words = {
            'catastrophe': -1.8, 'grave': -1.4, 'terrible': -1.5,
            'mauvais': -1.1, 'problème': -1.2, 'crise': -1.3,
            'accident': -1.4, 'échec': -1.3, 'danger': -1.4,
            'cyclone': -1.5, 'grève': -1.1, 'insécurité': -1.3
        }
        
        # Intensifieurs
        self.intensifiers = {
            'très': 1.3, 'vraiment': 1.2, 'extrêmement': 1.4,
            'peu': 0.7, 'légèrement': 0.8
        }
        
        # Négations
        self.negations = {'ne', "n'", 'pas', 'plus', 'jamais', 'rien', 'aucun', 'non', 'sans'}
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyser le sentiment localement"""
        
        if not text or len(text.strip()) < 10:
            return self._default_result()
        
        # Nettoyage
        text_clean = text.lower()
        text_clean = re.sub(r'[^\w\s]', ' ', text_clean)
        words = text_clean.split()
        
        if not words:
            return self._default_result()
        
        # Calcul des scores
        positive_score = 0.0
        negative_score = 0.0
        word_count = 0
        
        for i, word in enumerate(words):
            # Vérifier négation
            is_negated = any(words[j] in self.negations for j in range(max(0, i-2), i))
            
            # Score du mot
            score = 0.0
            if word in self.positive_words:
                score = self.positive_words[word]
            elif word in self.negative_words:
                score = self.negative_words[word]
            
            if score != 0:
                # Appliquer négation
                if is_negated:
                    score = -score
                
                # Appliquer intensifieur
                if i > 0 and words[i-1] in self.intensifiers:
                    score *= self.intensifiers[words[i-1]]
                
                # Accumuler
                if score > 0:
                    positive_score += score
                else:
                    negative_score += abs(score)
                
                word_count += 1
        
        # Score normalisé
        total_score = positive_score - negative_score
        normalized_score = total_score / max(len(words), 1)
        normalized_score = max(-1.0, min(1.0, normalized_score))
        
        # Polarité
        if normalized_score > 0.15:
            polarity = 'positive'
        elif normalized_score < -0.15:
            polarity = 'negative'
        else:
            polarity = 'neutral'
        
        # Intensité
        abs_score = abs(normalized_score)
        if abs_score > 0.5:
            intensity = 'strong'
        elif abs_score > 0.2:
            intensity = 'moderate'
        else:
            intensity = 'weak'
        
        return {
            'polarity': polarity,
            'score': round(normalized_score, 3),
            'intensity': intensity,
            'positive_score': round(positive_score, 2),
            'negative_score': round(negative_score, 2),
            'word_count': len(words),
            'significant_words': word_count,
            'confidence': min(0.7, 0.3 + (word_count / len(words)) * 0.4),
            'method': 'local',
            'analyzed_at': datetime.now().isoformat()
        }
    
    def _default_result(self) -> Dict[str, Any]:
        """Résultat par défaut"""
        return {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'positive_score': 0.0,
            'negative_score': 0.0,
            'word_count': 0,
            'significant_words': 0,
            'confidence': 0.3,
            'method': 'default',
            'analyzed_at': datetime.now().isoformat()
        }


# ============================================================================
# ANALYSEUR GPT (Optionnel)
# ============================================================================

class GPTSentimentAnalyzer:
    """Analyseur GPT avancé (si clé API disponible)"""
    
    def __init__(self):
        """Initialiser l'analyseur GPT"""
        self.available = False
        self.client = None
        
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if api_key:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
                self.available = True
                logger.info("✅ GPT Sentiment disponible")
            else:
                logger.warning("⚠️ OPENAI_API_KEY non configurée")
        except Exception as e:
            logger.warning(f"⚠️ GPT Sentiment non disponible: {e}")
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """Analyser avec GPT"""
        
        if not self.available or not text:
            raise Exception("GPT non disponible ou texte vide")
        
        # Limiter la longueur pour coût
        text_snippet = text[:2000]
        
        prompt = f"""Analysez le sentiment de ce texte en français (contexte Guadeloupe).

TEXTE: "{text_snippet}"

Répondez en JSON:
{{
    "sentiment": "positif|negatif|neutre",
    "score": 0.0,
    "intensite": "faible|moderee|forte",
    "emotions": ["joie", "inquietude", "colere", etc],
    "themes": ["politique", "economie", "social", etc],
    "confiance": 0.8
}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Tu es un expert en analyse de sentiment."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )
            
            import json
            gpt_text = response.choices[0].message.content.strip()
            
            # Parser le JSON
            json_match = re.search(r'\{.*\}', gpt_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return self._normalize_gpt_response(data, text)
            
            raise Exception("Pas de JSON dans la réponse GPT")
            
        except Exception as e:
            logger.error(f"❌ Erreur GPT: {e}")
            raise
    
    def _normalize_gpt_response(self, data: Dict, original_text: str) -> Dict[str, Any]:
        """Normaliser la réponse GPT"""
        
        # Mappings
        sentiment_map = {'positif': 'positive', 'negatif': 'negative', 'neutre': 'neutral'}
        intensity_map = {'faible': 'weak', 'moderee': 'moderate', 'forte': 'strong'}
        
        sentiment = data.get('sentiment', 'neutre').lower()
        polarity = sentiment_map.get(sentiment, 'neutral')
        
        score = float(data.get('score', 0.0))
        score = max(-1.0, min(1.0, score))
        
        intensite = data.get('intensite', 'faible').lower()
        intensity = intensity_map.get(intensite, 'weak')
        
        return {
            'polarity': polarity,
            'score': round(score, 3),
            'intensity': intensity,
            'positive_score': max(0, score),
            'negative_score': abs(min(0, score)),
            'word_count': len(original_text.split()),
            'significant_words': len(data.get('emotions', [])) + len(data.get('themes', [])),
            'confidence': float(data.get('confiance', 0.8)),
            'emotions': data.get('emotions', []),
            'themes': data.get('themes', []),
            'method': 'gpt',
            'analyzed_at': datetime.now().isoformat()
        }


# ============================================================================
# SERVICE UNIFIÉ
# ============================================================================

class SentimentService:
    """Service unifié de sentiment - Interface unique"""
    
    def __init__(self):
        """Initialiser le service"""
        
        # Toujours initialiser local
        self.local = LocalSentimentAnalyzer()
        logger.info("✅ Analyseur local initialisé")
        
        # Essayer GPT
        self.gpt = GPTSentimentAnalyzer()
        
        logger.info(f"📊 SentimentService prêt (GPT: {'✅' if self.gpt.available else '❌'})")
    
    def analyze(
        self, 
        text: str,
        use_gpt: bool = False,
        prefer_gpt: bool = None
    ) -> Dict[str, Any]:
        """
        Analyser le sentiment d'un texte
        
        Args:
            text: Texte à analyser
            use_gpt: Forcer l'utilisation de GPT
            prefer_gpt: Préférer GPT si disponible (None = auto selon contexte)
        
        Returns:
            Dict avec polarity, score, intensity, etc.
        """
        
        if not text or len(text.strip()) < 10:
            return self.local._default_result()
        
        # Décider quelle méthode utiliser
        should_use_gpt = False
        
        if use_gpt:
            should_use_gpt = True
        elif prefer_gpt is None:
            # Auto: GPT si disponible ET texte important (>200 chars)
            should_use_gpt = self.gpt.available and len(text) > 200
        elif prefer_gpt:
            should_use_gpt = self.gpt.available
        
        # Essayer GPT si demandé
        if should_use_gpt:
            try:
                logger.debug(f"🤖 Analyse GPT ({len(text)} chars)")
                result = self.gpt.analyze(text)
                logger.debug(f"✅ GPT: {result['polarity']} ({result['score']:.2f})")
                return result
            except Exception as e:
                logger.warning(f"⚠️ GPT échoué, fallback local: {e}")
        
        # Analyse locale
        logger.debug(f"🔍 Analyse locale ({len(text)} chars)")
        result = self.local.analyze(text)
        logger.debug(f"✅ Local: {result['polarity']} ({result['score']:.2f})")
        return result
    
    def analyze_article(
        self,
        article: Dict[str, Any],
        use_gpt: bool = False
    ) -> Dict[str, Any]:
        """
        Analyser le sentiment d'un article (titre + contenu)
        
        Args:
            article: Dict avec 'title' et 'content'
            use_gpt: Utiliser GPT pour le contenu
        
        Returns:
            Dict avec analyse combinée
        """
        
        title = article.get('title', '')
        content = article.get('content', '')
        
        if not title and not content:
            return self.local._default_result()
        
        # Analyser titre (toujours en local pour rapidité)
        title_result = None
        if title:
            title_result = self.analyze(title, use_gpt=False)
        
        # Analyser contenu (GPT si demandé)
        content_result = None
        if content:
            content_snippet = content[:1000]  # Limiter pour coût
            content_result = self.analyze(content_snippet, use_gpt=use_gpt)
        
        # Combiner les résultats
        return self._combine_results(title_result, content_result)
    
    def _combine_results(
        self,
        title_result: Optional[Dict],
        content_result: Optional[Dict]
    ) -> Dict[str, Any]:
        """Combiner les résultats titre + contenu"""
        
        # Cas où aucun résultat
        if not title_result and not content_result:
            return self.local._default_result()
        
        # Cas où un seul résultat
        if title_result and not content_result:
            return title_result
        if content_result and not title_result:
            return content_result
        
        # Combiner (titre 40%, contenu 60%)
        title_score = title_result['score']
        content_score = content_result['score']
        
        combined_score = (title_score * 0.4) + (content_score * 0.6)
        
        # Polarité combinée
        if combined_score > 0.15:
            polarity = 'positive'
        elif combined_score < -0.15:
            polarity = 'negative'
        else:
            polarity = 'neutral'
        
        # Intensité combinée
        abs_score = abs(combined_score)
        if abs_score > 0.5:
            intensity = 'strong'
        elif abs_score > 0.2:
            intensity = 'moderate'
        else:
            intensity = 'weak'
        
        return {
            'polarity': polarity,
            'score': round(combined_score, 3),
            'intensity': intensity,
            'positive_score': (title_result['positive_score'] + content_result['positive_score']) / 2,
            'negative_score': (title_result['negative_score'] + content_result['negative_score']) / 2,
            'word_count': title_result['word_count'] + content_result['word_count'],
            'significant_words': title_result['significant_words'] + content_result['significant_words'],
            'confidence': (title_result['confidence'] + content_result['confidence']) / 2,
            'method': 'combined',
            'title_sentiment': title_result,
            'content_sentiment': content_result,
            'analyzed_at': datetime.now().isoformat()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Obtenir le statut du service"""
        return {
            'status': 'operational',
            'local_available': True,
            'gpt_available': self.gpt.available,
            'default_method': 'gpt' if self.gpt.available else 'local'
        }


# ============================================================================
# INSTANCE GLOBALE ET FONCTIONS UTILITAIRES
# ============================================================================

# Instance singleton
sentiment_service = SentimentService()


# Fonctions de compatibilité
def analyze_sentiment(text: str, use_gpt: bool = False) -> Dict[str, Any]:
    """Analyser le sentiment d'un texte"""
    return sentiment_service.analyze(text, use_gpt=use_gpt)


def analyze_article_sentiment(article: Dict[str, Any], use_gpt: bool = False) -> Dict[str, Any]:
    """Analyser le sentiment d'un article"""
    return sentiment_service.analyze_article(article, use_gpt=use_gpt)


def get_sentiment_status() -> Dict[str, Any]:
    """Obtenir le statut du service"""
    return sentiment_service.get_status()


# Alias pour compatibilité avec ancien code
def analyze_text_sentiment(text: str) -> Dict[str, Any]:
    """Alias pour compatibilité"""
    return analyze_sentiment(text)


# Log au chargement
logger.info("✅ SentimentService chargé")
