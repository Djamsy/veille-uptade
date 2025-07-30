"""
Service d'analyse de sentiment intelligent avec GPT-4.1-mini
Remplace l'analyse locale par une analyse contextuelle et précise
Optimisé pour le contexte français et guadeloupéen
"""
import logging
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from openai import OpenAI

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GptSentimentAnalyzer:
    def __init__(self):
        """Initialiser l'analyseur de sentiment GPT"""
        
        # Configuration OpenAI
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not self.openai_api_key:
            logger.error("❌ OPENAI_API_KEY non configurée")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.openai_api_key)
                logger.info("✅ Client OpenAI initialisé pour analyse de sentiment")
            except Exception as e:
                logger.error(f"❌ Erreur initialisation OpenAI: {e}")
                self.client = None
        
        # Template de prompt pour l'analyse de sentiment
        self.sentiment_prompt_template = """Analysez le sentiment de ce texte en français dans le contexte de la Guadeloupe et des Antilles.

TEXTE À ANALYSER:
"{text}"

INSTRUCTIONS:
1. Analysez le sentiment global (positif, négatif, neutre)
2. Donnez un score précis de -1.0 (très négatif) à +1.0 (très positif) 
3. Évaluez l'intensité (faible, modérée, forte)
4. Identifiez les émotions principales
5. Expliquez les raisons du sentiment
6. Détectez les sujets/thèmes abordés
7. Contextualisez pour la Guadeloupe si pertinent

RÉPONDEZ UNIQUEMENT EN JSON VALIDE:
{{
    "sentiment": "positif|négatif|neutre",
    "score": 0.0,
    "intensite": "faible|modérée|forte", 
    "emotions": ["joie", "espoir", "inquiétude", "colère", "surprise", "tristesse"],
    "raisons": "Explication du sentiment détectée",
    "themes": ["politique", "économie", "social", "culture", "environnement"],
    "contexte_guadeloupe": "Pertinence pour la Guadeloupe",
    "mots_cles": ["mot1", "mot2", "mot3"],
    "confiance": 0.0
}}"""

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyser le sentiment d'un texte avec GPT"""
        try:
            if not text or not text.strip():
                return self._default_sentiment()
            
            if not self.client:
                logger.warning("⚠️ Client OpenAI non disponible, utilisation du fallback")
                return self._fallback_sentiment_analysis(text)
            
            # Nettoyer et préparer le texte
            clean_text = self._clean_text(text)
            if len(clean_text) > 3000:  # Limiter pour les coûts
                clean_text = clean_text[:3000] + "..."
            
            # Créer le prompt
            prompt = self.sentiment_prompt_template.format(text=clean_text)
            
            # Appel à GPT
            logger.info(f"🤖 Analyse GPT sentiment pour texte de {len(clean_text)} caractères")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "Tu es un expert en analyse de sentiment spécialisé dans le contexte français et antillais. Tu réponds toujours en JSON valide."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.1  # Peu de créativité pour la consistance
            )
            
            # Extraire et parser la réponse
            gpt_response = response.choices[0].message.content.strip()
            
            try:
                # Parser le JSON
                sentiment_data = json.loads(gpt_response)
                
                # Normaliser et valider les données
                analyzed_sentiment = self._normalize_gpt_response(sentiment_data, text)
                
                logger.info(f"✅ Analyse GPT terminée: {analyzed_sentiment['polarity']} (score: {analyzed_sentiment['score']})")
                return analyzed_sentiment
                
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ Erreur parsing JSON GPT: {e}")
                logger.warning(f"Réponse GPT: {gpt_response}")
                return self._fallback_sentiment_analysis(clean_text)
                
        except Exception as e:
            logger.error(f"❌ Erreur analyse GPT sentiment: {e}")
            return self._fallback_sentiment_analysis(text)

    def _clean_text(self, text: str) -> str:
        """Nettoyer le texte pour l'analyse"""
        if not text:
            return ""
        
        # Supprimer les caractères de contrôle
        import re
        clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
        
        # Remplacer les espaces multiples
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        return clean_text.strip()

    def _normalize_gpt_response(self, gpt_data: Dict, original_text: str) -> Dict[str, Any]:
        """Normaliser la réponse GPT au format attendu"""
        
        # Mapping des sentiments
        sentiment_mapping = {
            'positif': 'positive',
            'négatif': 'negative', 
            'negatif': 'negative',
            'neutre': 'neutral'
        }
        
        # Mapping des intensités
        intensity_mapping = {
            'faible': 'weak',
            'modérée': 'moderate',  
            'moderee': 'moderate',
            'modéré': 'moderate',
            'modere': 'moderate',
            'forte': 'strong'
        }
        
        # Extraire et normaliser les données
        sentiment = gpt_data.get('sentiment', 'neutre').lower()
        polarity = sentiment_mapping.get(sentiment, 'neutral')
        
        score = float(gpt_data.get('score', 0.0))
        score = max(-1.0, min(1.0, score))  # Clamp entre -1 et 1
        
        intensite = gpt_data.get('intensite', 'faible').lower()
        intensity = intensity_mapping.get(intensite, 'weak')
        
        emotions = gpt_data.get('emotions', [])
        if not isinstance(emotions, list):
            emotions = []
        
        themes = gpt_data.get('themes', [])
        if not isinstance(themes, list):
            themes = []
        
        mots_cles = gpt_data.get('mots_cles', [])
        if not isinstance(mots_cles, list):
            mots_cles = []
        
        confiance = float(gpt_data.get('confiance', 0.8))
        confiance = max(0.0, min(1.0, confiance))
        
        return {
            'polarity': polarity,
            'score': round(score, 3),
            'intensity': intensity,
            'positive_score': max(0, score) if score > 0 else 0.0,
            'negative_score': abs(min(0, score)) if score < 0 else 0.0,
            'word_count': len(original_text.split()),
            'significant_words': len(mots_cles),
            'analysis_details': {
                'emotions': emotions,
                'themes': themes,
                'keywords': mots_cles,
                'explanation': gpt_data.get('raisons', ''),
                'guadeloupe_context': gpt_data.get('contexte_guadeloupe', ''),
                'confidence': confiance,
                'method': 'gpt-4o-mini'
            },
            'analyzed_at': datetime.now().isoformat()
        }

    def _fallback_sentiment_analysis(self, text: str) -> Dict[str, Any]:
        """Analyse de fallback basique en cas d'échec GPT"""
        logger.info("🔄 Utilisation analyse fallback (mots-clés)")
        
        if not text:
            return self._default_sentiment()
        
        # Mots-clés simples pour le fallback
        positive_keywords = ['bon', 'bien', 'excellent', 'réussi', 'succès', 'progrès', 'amélioration', 'nouveau', 'projet', 'développement']
        negative_keywords = ['mauvais', 'problème', 'échec', 'crise', 'accident', 'mort', 'danger', 'panne', 'difficile', 'grave']
        
        text_lower = text.lower()
        positive_count = sum(1 for word in positive_keywords if word in text_lower)
        negative_count = sum(1 for word in negative_keywords if word in text_lower)
        
        if positive_count > negative_count:
            polarity = 'positive'
            score = 0.3
        elif negative_count > positive_count:
            polarity = 'negative'  
            score = -0.3
        else:
            polarity = 'neutral'
            score = 0.0
        
        return {
            'polarity': polarity,
            'score': score,
            'intensity': 'weak',
            'positive_score': max(0, score),
            'negative_score': abs(min(0, score)),
            'word_count': len(text.split()),
            'significant_words': positive_count + negative_count,
            'analysis_details': {
                'emotions': [],
                'themes': [],
                'keywords': [],
                'explanation': 'Analyse basique par mots-clés (fallback)',
                'guadeloupe_context': '',
                'confidence': 0.5,
                'method': 'keyword_fallback'
            },
            'analyzed_at': datetime.now().isoformat()
        }

    def _default_sentiment(self, error: str = None) -> Dict[str, Any]:
        """Retourner un sentiment par défaut"""
        result = {
            'polarity': 'neutral',
            'score': 0.0,
            'intensity': 'weak',
            'positive_score': 0.0,
            'negative_score': 0.0,
            'word_count': 0,
            'significant_words': 0,
            'analysis_details': {
                'emotions': [],
                'themes': [],
                'keywords': [],
                'explanation': '',
                'guadeloupe_context': '',
                'confidence': 0.0,
                'method': 'default'
            },
            'analyzed_at': datetime.now().isoformat()
        }
        
        if error:
            result['error'] = error
        
        return result

    def analyze_articles_batch(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyser le sentiment d'un lot d'articles avec GPT"""
        try:
            if not articles:
                return {'articles': [], 'summary': self._empty_summary()}
            
            analyzed_articles = []
            sentiment_summary = {
                'positive': 0,
                'negative': 0,
                'neutral': 0,
                'total': len(articles)
            }
            
            all_scores = []
            all_themes = []
            all_emotions = []
            
            # Limiter le nombre d'articles pour contrôler les coûts
            max_articles = 50  # Limite pour éviter des coûts élevés
            articles_to_analyze = articles[:max_articles]
            
            logger.info(f"🤖 Analyse GPT batch de {len(articles_to_analyze)} articles")
            
            for i, article in enumerate(articles_to_analyze):
                try:
                    # Analyser le titre (plus important et moins coûteux)
                    title = article.get('title', '')
                    content_snippet = article.get('content', '')[:200]  # Premiers 200 caractères
                    text_to_analyze = f"{title}. {content_snippet}"
                    
                    title_sentiment = self.analyze_sentiment(text_to_analyze)
                    
                    # Créer l'article analysé
                    analyzed_article = {
                        **article,
                        'sentiment': title_sentiment,
                        'sentiment_summary': {
                            'polarity': title_sentiment['polarity'],
                            'score': title_sentiment['score'],
                            'intensity': title_sentiment['intensity'],
                            'confidence': title_sentiment['analysis_details']['confidence'],
                            'themes': title_sentiment['analysis_details']['themes'],
                            'emotions': title_sentiment['analysis_details']['emotions']
                        }
                    }
                    
                    analyzed_articles.append(analyzed_article)
                    
                    # Mettre à jour le résumé
                    sentiment_summary[title_sentiment['polarity']] += 1
                    all_scores.append(title_sentiment['score'])
                    all_themes.extend(title_sentiment['analysis_details']['themes'])
                    all_emotions.extend(title_sentiment['analysis_details']['emotions'])
                    
                    # Pause pour éviter les limits de taux
                    if i > 0 and i % 10 == 0:
                        import time
                        time.sleep(1)
                        
                except Exception as e:
                    logger.warning(f"Erreur analyse article {i}: {e}")
                    # Ajouter l'article sans analyse en cas d'erreur
                    analyzed_articles.append({
                        **article,
                        'sentiment': self._default_sentiment(str(e))
                    })
            
            # Calculer les statistiques globales
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            
            from collections import Counter
            theme_counts = Counter(all_themes)
            emotion_counts = Counter(all_emotions)
            
            overall_summary = {
                'total_articles': len(articles_to_analyze),
                'sentiment_distribution': sentiment_summary,
                'average_sentiment_score': round(avg_score, 3),
                'most_common_themes': dict(theme_counts.most_common(5)),
                'most_common_emotions': dict(emotion_counts.most_common(5)),
                'analysis_method': 'gpt-4o-mini',
                'analysis_timestamp': datetime.now().isoformat(),
                'cost_optimization': f'Analysé {len(articles_to_analyze)}/{len(articles)} articles'
            }
            
            logger.info(f"✅ Analyse GPT batch terminée: {len(analyzed_articles)} articles")
            
            return {
                'articles': analyzed_articles,
                'summary': overall_summary
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse batch GPT: {e}")
            return {
                'articles': articles,  # Retourner les articles originaux
                'summary': self._empty_summary(error=str(e))
            }

    def _empty_summary(self, error: str = None) -> Dict[str, Any]:
        """Retourner un résumé vide"""
        summary = {
            'total_articles': 0,
            'sentiment_distribution': {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0},
            'average_sentiment_score': 0.0,
            'most_common_themes': {},
            'most_common_emotions': {},
            'analysis_method': 'gpt-4o-mini',
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        if error:
            summary['error'] = error
        
        return summary

# Instance globale
gpt_sentiment_analyzer = GptSentimentAnalyzer()

# Fonctions utilitaires pour compatibilité
def analyze_text_sentiment(text: str) -> Dict[str, Any]:
    """Analyser le sentiment d'un texte avec GPT (fonction utilitaire)"""
    return gpt_sentiment_analyzer.analyze_sentiment(text)

def analyze_articles_sentiment(articles: List[Dict]) -> Dict[str, Any]:
    """Analyser le sentiment d'une liste d'articles avec GPT (fonction utilitaire)"""
    return gpt_sentiment_analyzer.analyze_articles_batch(articles)

if __name__ == "__main__":
    # Tests
    test_texts = [
        "Excellent festival de musique créole à Pointe-à-Pitre ! L'ambiance était formidable.",
        "Grave accident de la route en Guadeloupe, plusieurs blessés dans un état critique.",
        "Nouvelle école construite à Basse-Terre pour améliorer l'éducation des jeunes.",
        "Guy Losbar annonce de nouveaux investissements pour le développement durable.",
        "Le Conseil Départemental vote le budget pour soutenir les familles en difficulté."
    ]
    
    print("=== Test du service d'analyse de sentiment GPT ===")
    for text in test_texts:
        result = analyze_text_sentiment(text)
        print(f"\nTexte: {text}")
        print(f"Sentiment: {result['polarity']} (score: {result['score']}, intensité: {result['intensity']})")
        print(f"Émotions: {result['analysis_details']['emotions']}")
        print(f"Thèmes: {result['analysis_details']['themes']}")
        print(f"Contexte: {result['analysis_details']['guadeloupe_context']}")
        print("---")