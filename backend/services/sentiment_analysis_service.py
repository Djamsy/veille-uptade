"""
Analyseur de sentiment LOCAL robuste pour la Guadeloupe
Version corrigée pour éviter les erreurs mathématiques
100% économique, performances fiables
"""

import os
import re
import logging
import math
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import Counter, defaultdict
import unicodedata
import json
from functools import lru_cache

logger = logging.getLogger(__name__)

class RobustSentimentAnalyzer:
    """Analyseur de sentiment robuste avec protection contre les erreurs mathématiques"""
    
    def __init__(self):
        """Initialisation sécurisée"""
        
        # Cache pour performances
        self._analysis_cache = {}
        
        # Lexiques avec protection contre les erreurs
        self._initialize_lexicons()
        
        # Patterns contextuels simples mais efficaces
        self._initialize_patterns()
        
        logger.info("Analyseur de sentiment ultra-avancé initialisé")

    def _initialize_lexicons(self):
        """Lexiques optimisés pour la Guadeloupe avec scores sécurisés"""
        
        # Lexique positif (scores entre 0.1 et 2.0)
        self.positive_words = {
            # Ultra-positif
            'extraordinaire': 2.0, 'exceptionnel': 1.9, 'magnifique': 1.8,
            'formidable': 1.8, 'fantastique': 1.9, 'merveilleux': 1.8,
            
            # Très positif
            'excellent': 1.6, 'parfait': 1.5, 'superbe': 1.5, 'génial': 1.6,
            'remarquable': 1.4, 'admirable': 1.4, 'splendide': 1.5,
            
            # Positif
            'bon': 1.0, 'bien': 1.1, 'beau': 1.2, 'content': 1.1, 'heureux': 1.2,
            'satisfait': 1.0, 'réussi': 1.3, 'succès': 1.3, 'victoire': 1.3,
            
            # Modérément positif
            'intéressant': 0.7, 'correct': 0.6, 'acceptable': 0.5, 'convenable': 0.6,
            
            # Créole positif
            'bèl': 1.4, 'dous': 1.3, 'agrèab': 1.2, 'kontan': 1.4,
            'cho': 1.5, 'douvan': 1.2,
            
            # Contexte Guadeloupe
            'festival': 1.4, 'carnaval': 1.5, 'créole': 1.2, 'patrimoine': 1.3,
            'tourisme': 1.1, 'paradis': 1.6, 'développement': 1.2, 'investissement': 1.1
        }
        
        # Lexique négatif (scores entre -0.1 et -2.0)
        self.negative_words = {
            # Ultra-négatif
            'catastrophique': -2.0, 'dramatique': -1.9, 'épouvantable': -1.8,
            'atroce': -1.9, 'horrible': -1.8, 'tragique': -1.8,
            
            # Très négatif
            'terrible': -1.6, 'grave': -1.5, 'dangereux': -1.4, 'alarmant': -1.4,
            'désastreux': -1.6, 'effroyable': -1.7,
            
            # Négatif
            'mauvais': -1.1, 'mal': -1.0, 'problème': -1.2, 'difficulté': -1.1,
            'échec': -1.3, 'perte': -1.2, 'crise': -1.3,
            
            # Modérément négatif
            'inquiétant': -0.8, 'préoccupant': -0.7, 'regrettable': -0.6,
            
            # Créole négatif
            'move': -1.2, 'danjé': -1.4, 'pwoblèm': -1.2,
            'grav': -1.5, 'malèrèz': -1.6,
            
            # Contexte Guadeloupe négatif
            'cyclone': -1.6, 'sargasses': -1.3, 'embouteillage': -0.8,
            'grève': -1.1, 'insécurité': -1.4, 'pollution': -1.2
        }
        
        # Intensifieurs sécurisés
        self.intensifiers = {
            'très': 1.3, 'vraiment': 1.2, 'extrêmement': 1.4, 'assez': 1.1,
            'plutôt': 1.05, 'beaucoup': 1.2, 'énormément': 1.4,
            'peu': 0.7, 'légèrement': 0.8, 'faiblement': 0.6
        }
        
        # Négations
        self.negations = {
            'ne', "n'", 'pas', 'plus', 'jamais', 'rien', 'aucun', 'aucune',
            'non', 'sans', 'guère', 'point'
        }

    def _initialize_patterns(self):
        """Patterns contextuels sécurisés"""
        
        # Thèmes guadeloupéens
        self.themes = {
            'culture': ['festival', 'carnaval', 'créole', 'culture', 'tradition', 'patrimoine'],
            'économie': ['emploi', 'entreprise', 'investissement', 'commerce', 'économie'],
            'sécurité': ['police', 'gendarmerie', 'violence', 'accident', 'sécurité'],
            'environnement': ['mer', 'plage', 'nature', 'pollution', 'cyclone', 'sargasses'],
            'transport': ['route', 'bus', 'ferry', 'circulation', 'embouteillage'],
            'tourisme': ['tourisme', 'hôtel', 'visite', 'croisière', 'vacances']
        }
        
        # Émotions de base
        self.emotion_patterns = {
            'joie': ['joie', 'bonheur', 'content', 'heureux', 'gai'],
            'colère': ['colère', 'énervé', 'furieux', 'irrité'],
            'tristesse': ['tristesse', 'triste', 'malheureux', 'peine'],
            'peur': ['peur', 'inquiet', 'anxieux', 'préoccupé'],
            'surprise': ['surprise', 'étonné', 'stupéfait']
        }

    def _safe_text_preprocessing(self, text: str) -> Tuple[str, Dict[str, Any]]:
        """Préprocessing sécurisé avec métadonnées"""
        
        if not text or not isinstance(text, str):
            return "", {'original_length': 0, 'processed_length': 0}
        
        original_text = text
        metadata = {
            'original_length': len(text),
            'exclamation_count': text.count('!'),
            'question_count': text.count('?'),
            'caps_count': len(re.findall(r'[A-Z]', text)),
        }
        
        try:
            # Nettoyage sécurisé
            text = re.sub(r'http[s]?://\S+', ' ', text)  # URLs
            text = re.sub(r'@\w+', ' ', text)  # Mentions
            text = re.sub(r'#\w+', ' ', text)  # Hashtags
            
            # Normalisation Unicode sécurisée
            try:
                text = unicodedata.normalize('NFD', text)
                text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
            except:
                pass  # Garder le texte original si erreur
            
            # Nettoyage final
            text = re.sub(r'[^\w\s\'!?.,;:-]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip().lower()
            
            metadata['processed_length'] = len(text)
            
        except Exception as e:
            logger.warning(f"Erreur preprocessing, utilisation texte original: {e}")
            text = original_text.lower()
            metadata['processed_length'] = len(text)
        
        return text, metadata

    def _safe_calculate_confidence(self, word_details: List[Dict], total_words: int, 
                                 exclamations: int, caps_count: int) -> float:
        """Calcul de confiance avec protection totale contre les erreurs math"""
        
        try:
            # Protection contre les valeurs invalides
            if not isinstance(total_words, (int, float)) or total_words <= 0:
                return 0.5
            
            if not isinstance(word_details, list):
                return 0.5
            
            # Calculs sécurisés
            significant_words = len(word_details)
            sig_ratio = min(1.0, max(0.0, significant_words / total_words))
            
            # Protection contre les valeurs None ou négatives
            exclamations = max(0, exclamations or 0)
            caps_count = max(0, caps_count or 0)
            
            # Facteur de longueur sécurisé
            length_factor = min(1.0, max(0.0, total_words / 50.0))
            
            # Calcul de l'emphase sécurisé
            caps_ratio = min(1.0, max(0.0, caps_count / max(total_words, 1)))
            emphasis_penalty = min(0.3, 0.02 * exclamations + 0.2 * caps_ratio)
            
            # Calcul final avec contraintes strictes
            raw_confidence = 0.6 * sig_ratio + 0.4 * length_factor
            final_confidence = max(0.0, min(1.0, raw_confidence * (1.0 - emphasis_penalty)))
            
            # Vérification finale de validité
            if not isinstance(final_confidence, (int, float)) or math.isnan(final_confidence) or math.isinf(final_confidence):
                return 0.5
            
            return round(final_confidence, 3)
            
        except Exception as e:
            logger.warning(f"Erreur calcul confiance: {e}")
            return 0.5

    def _detect_themes_safe(self, words: List[str]) -> List[str]:
        """Détection de thèmes sécurisée"""
        
        detected_themes = []
        
        try:
            for theme, keywords in self.themes.items():
                for word in words:
                    if word in keywords:
                        detected_themes.append(theme)
                        break
        except Exception as e:
            logger.warning(f"Erreur détection thèmes: {e}")
        
        return list(set(detected_themes))  # Éliminer doublons

    def _detect_emotions_safe(self, word_details: List[Dict]) -> List[str]:
        """Détection d'émotions sécurisée"""
        
        emotions = []
        
        try:
            # Émotions basées sur les scores
            scores = [wd.get('score', 0) for wd in word_details if isinstance(wd, dict)]
            
            if scores:
                avg_score = sum(scores) / len(scores)
                
                if avg_score > 0.5:
                    emotions.append('joie')
                elif avg_score < -0.5:
                    emotions.append('tristesse')
                
                # Recherche patterns spécifiques
                words = [wd.get('word', '') for wd in word_details if isinstance(wd, dict)]
                
                for emotion, patterns in self.emotion_patterns.items():
                    for word in words:
                        if word in patterns:
                            emotions.append(emotion)
                            break
        
        except Exception as e:
            logger.warning(f"Erreur détection émotions: {e}")
        
        return list(set(emotions))

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyse de sentiment ultra-robuste"""
        
        if not text or not isinstance(text, str) or not text.strip():
            return self._default_sentiment()
        
        try:
            # Hash pour cache
            text_hash = hashlib.md5(text.encode('utf-8', errors='ignore')).hexdigest()
            if text_hash in self._analysis_cache:
                return self._analysis_cache[text_hash]
            
            start_time = datetime.now()
            
            # Préprocessing sécurisé
            processed_text, metadata = self._safe_text_preprocessing(text)
            words = processed_text.split()
            
            if not words:
                return self._default_sentiment()
            
            # Analyse lexicale sécurisée
            positive_score = 0.0
            negative_score = 0.0
            word_details = []
            
            for i, word in enumerate(words):
                try:
                    # Détection de négation dans une fenêtre de 3 mots
                    is_negated = False
                    for j in range(max(0, i-3), i):
                        if j < len(words) and words[j] in self.negations:
                            is_negated = True
                            break
                    
                    # Score de base du mot
                    base_score = 0.0
                    word_type = 'neutral'
                    
                    if word in self.positive_words:
                        base_score = self.positive_words[word]
                        word_type = 'positive'
                    elif word in self.negative_words:
                        base_score = self.negative_words[word]
                        word_type = 'negative'
                    
                    # Application sécurisée de la négation
                    if is_negated and base_score != 0:
                        base_score = -base_score
                        word_type = 'positive' if word_type == 'negative' else 'negative'
                    
                    # Intensification sécurisée
                    intensifier = 1.0
                    if i > 0 and words[i-1] in self.intensifiers:
                        intensifier = self.intensifiers[words[i-1]]
                    
                    final_score = base_score * intensifier
                    
                    # Accumulation sécurisée
                    if final_score > 0:
                        positive_score += final_score
                    elif final_score < 0:
                        negative_score += abs(final_score)
                    
                    # Enregistrement des détails
                    if final_score != 0:
                        word_details.append({
                            'word': word,
                            'score': round(final_score, 3),
                            'type': word_type,
                            'negated': is_negated,
                            'intensifier': intensifier
                        })
                
                except Exception as e:
                    logger.warning(f"Erreur analyse mot '{word}': {e}")
                    continue
            
            # Calcul du score final sécurisé
            total_words = len(words)
            
            try:
                if total_words > 0:
                    total_score = positive_score - negative_score
                    normalized_score = total_score / total_words
                    
                    # Contrainte stricte [-1, 1]
                    normalized_score = max(-1.0, min(1.0, normalized_score))
                else:
                    normalized_score = 0.0
                
                # Vérification de validité
                if not isinstance(normalized_score, (int, float)) or math.isnan(normalized_score) or math.isinf(normalized_score):
                    normalized_score = 0.0
                
            except Exception as e:
                logger.warning(f"Erreur calcul score: {e}")
                normalized_score = 0.0
            
            # Classification sécurisée
            if normalized_score > 0.1:
                polarity = 'positive'
            elif normalized_score < -0.1:
                polarity = 'negative'
            else:
                polarity = 'neutral'
            
            # Intensité sécurisée
            abs_score = abs(normalized_score)
            if abs_score > 0.5:
                intensity = 'strong'
            elif abs_score > 0.2:
                intensity = 'moderate'
            else:
                intensity = 'weak'
            
            # Confiance sécurisée
            confidence = self._safe_calculate_confidence(
                word_details, total_words, 
                metadata.get('exclamation_count', 0),
                metadata.get('caps_count', 0)
            )
            
            # Détections contextuelles sécurisées
            themes = self._detect_themes_safe(words)
            emotions = self._detect_emotions_safe(word_details)
            
            # Temps de traitement
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Assemblage du résultat
            result = {
                'polarity': polarity,
                'score': round(normalized_score, 4),
                'intensity': intensity,
                'positive_score': round(positive_score, 3),
                'negative_score': round(negative_score, 3),
                'word_count': total_words,
                'significant_words': len(word_details),
                'analysis_details': {
                    'words_analyzed': word_details[:10],  # Limiter pour performance
                    'detected_patterns': themes,
                    'emotions': emotions,
                    'confidence': confidence,
                    'explanation': f"Sentiment {polarity} détecté avec intensité {intensity}",
                    'guadeloupe_context': f"Analyse contextuelle: {', '.join(themes) if themes else 'contexte général'}",
                    'method': 'robust_local_analyzer',
                    'processing_time_ms': round(processing_time * 1000, 2)
                },
                'analyzed_at': datetime.now().isoformat()
            }
            
            # Mise en cache sécurisée
            if len(self._analysis_cache) < 1000:  # Limiter la taille du cache
                self._analysis_cache[text_hash] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur globale analyse sentiment: {e}")
            return self._default_sentiment(error=str(e))

    def _default_sentiment(self, error: str = None) -> Dict[str, Any]:
        """Sentiment par défaut sécurisé"""
        
        result = {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'positive_score': 0.0,
            'negative_score': 0.0,
            'word_count': 0,
            'significant_words': 0,
            'analysis_details': {
                'words_analyzed': [],
                'detected_patterns': [],
                'emotions': [],
                'confidence': 0.5,
                'explanation': 'Analyse par défaut (texte vide ou erreur)',
                'guadeloupe_context': 'Contexte non déterminé',
                'method': 'robust_local_analyzer',
                'processing_time_ms': 0.0
            },
            'analyzed_at': datetime.now().isoformat()
        }
        
        if error:
            result['analysis_details']['error'] = error
            result['analysis_details']['explanation'] = f'Erreur durant l\'analyse: {error}'
        
        return result

    def predict_population_reaction(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Prédiction de réaction robuste"""
        
        try:
            sentiment = self.analyze_sentiment(text)
            
            # Logique de prédiction basée sur le sentiment
            score = sentiment['score']
            polarity = sentiment['polarity']
            
            if polarity == 'positive':
                overall_reaction = 'favorable'
                risk_level = 'low'
            elif polarity == 'negative':
                overall_reaction = 'défavorable'
                risk_level = 'high' if abs(score) > 0.5 else 'medium'
            else:
                overall_reaction = 'mitigé'
                risk_level = 'medium'
            
            return {
                'overall_reaction': overall_reaction,
                'overall_score': round(score, 3),
                'risk_level': risk_level,
                'confidence': sentiment['analysis_details']['confidence'],
                'polarization_risk': risk_level,
                'strategic_recommendations': [
                    f"Surveiller les réactions {overall_reaction}s",
                    "Préparer une communication adaptée",
                    "Analyser les retours du public"
                ],
                'guadeloupe_context': sentiment['analysis_details']['guadeloupe_context'],
                'method': 'robust_prediction'
            }
            
        except Exception as e:
            logger.error(f"Erreur prédiction: {e}")
            return {
                'overall_reaction': 'indéterminé',
                'overall_score': 0.0,
                'risk_level': 'medium',
                'confidence': 0.5,
                'error': str(e)
            }

    def analyze_articles_batch(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyse batch sécurisée"""
        
        try:
            if not articles:
                return {'articles': [], 'summary': self._empty_summary()}
            
            analyzed_articles = []
            sentiment_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
            all_scores = []
            
            for article in articles:
                try:
                    # Extraction sécurisée du texte
                    title = str(article.get('title', ''))
                    content = str(article.get('content', ''))[:300]  # Limiter pour performance
                    text = f"{title}. {content}".strip()
                    
                    if text:
                        sentiment = self.analyze_sentiment(text)
                        analyzed_articles.append({
                            **article,
                            'sentiment_analysis': sentiment
                        })
                        
                        sentiment_counts[sentiment['polarity']] += 1
                        all_scores.append(sentiment['score'])
                    
                except Exception as e:
                    logger.warning(f"Erreur analyse article: {e}")
                    # Garder l'article sans sentiment
                    analyzed_articles.append(article)
            
            # Résumé sécurisé
            total = len(analyzed_articles)
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
            
            summary = {
                'total_articles': total,
                'sentiment_distribution': {
                    'positive': sentiment_counts['positive'],
                    'negative': sentiment_counts['negative'],
                    'neutral': sentiment_counts['neutral'],
                    'total': total
                },
                'average_sentiment_score': round(avg_score, 3),
                'analysis_timestamp': datetime.now().isoformat(),
                'method': 'robust_batch_analysis'
            }
            
            return {
                'articles': analyzed_articles,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse batch: {e}")
            return {
                'articles': articles,  # Retourner les articles originaux
                'summary': self._empty_summary(error=str(e))
            }

    def _empty_summary(self, error: str = None) -> Dict[str, Any]:
        """Résumé vide sécurisé"""
        
        summary = {
            'total_articles': 0,
            'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
            'average_sentiment_score': 0.0,
            'analysis_timestamp': datetime.now().isoformat(),
            'method': 'robust_batch_analysis'
        }
        
        if error:
            summary['error'] = error
        
        return summary

    def get_system_stats(self) -> Dict[str, Any]:
        """Statistiques système sécurisées"""
        
        return {
            'analyzer_type': 'robust_sentiment_analyzer',
            'cache_size': len(self._analysis_cache),
            'lexicon_size': {
                'positive': len(self.positive_words),
                'negative': len(self.negative_words),
                'intensifiers': len(self.intensifiers)
            },
            'themes_supported': len(self.themes),
            'emotions_supported': len(self.emotion_patterns),
            'performance': 'high_reliability',
            'cost': 'zero_api_cost',
            'math_safety': 'protected_against_range_errors'
        }


# Instance globale sécurisée
ultra_analyzer = RobustSentimentAnalyzer()

# Fonctions d'interface principales
def analyze_text_sentiment(text: str) -> Dict[str, Any]:
    """Interface principale - VERSION ROBUSTE"""
    return ultra_analyzer.analyze_sentiment(text)

def predict_population_reaction(text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Prédiction de réaction robuste"""
    return ultra_analyzer.predict_population_reaction(text, context)

def analyze_articles_sentiment(articles: List[Dict]) -> Dict[str, Any]:
    """Analyse batch robuste"""
    return ultra_analyzer.analyze_articles_batch(articles)

# Instance pour compatibilité
local_sentiment_analyzer = ultra_analyzer

if __name__ == "__main__":
    # Tests de robustesse
    test_cases = [
        "Excellent festival de musique créole à Pointe-à-Pitre !",
        "Grave accident de la route en Guadeloupe, plusieurs blessés",
        "Nouvelle école construite à Basse-Terre",
        "Cyclone dangereux s'approche des Antilles",
        "",  # Cas vide
        "!!!",  # Cas problématique
        "Texte très court",
        "Un texte vraiment très très très long avec beaucoup de mots qui pourraient causer des problèmes mathématiques si l'analyseur n'est pas bien protégé contre les erreurs de calcul."
    ]
    
    print("=== Tests Analyseur Robuste ===")
    for i, text in enumerate(test_cases):
        try:
            result = analyze_text_sentiment(text)
            print(f"\nTest {i+1}: {text[:50]}{'...' if len(text) > 50 else ''}")
            print(f"Résultat: {result['polarity']} ({result['score']:.3f})")
            print(f"Confiance: {result['analysis_details']['confidence']:.3f}")
            print(f"Temps: {result['analysis_details']['processing_time_ms']:.1f}ms")
        except Exception as e:
            print(f"ERREUR Test {i+1}: {e}")
    
    print(f"\nStats système: {ultra_analyzer.get_system_stats()}")
