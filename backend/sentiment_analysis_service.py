"""
Service d'analyse de sentiment local pour les articles de Guadeloupe
Utilise des méthodes locales sans API externes
"""
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from collections import Counter

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalSentimentAnalyzer:
    def __init__(self):
        """Initialiser l'analyseur de sentiment local"""
        
        # Dictionnaires de mots positifs et négatifs en français
        self.positive_words = {
            # Mots très positifs
            'excellent', 'fantastique', 'merveilleux', 'génial', 'parfait', 'superbe', 
            'formidable', 'exceptionnel', 'remarquable', 'magnifique', 'splendide',
            'incroyable', 'extraordinaire', 'fabuleux', 'sublime', 'éblouissant',
            
            # Mots modérément positifs  
            'bon', 'bien', 'mieux', 'beau', 'belle', 'réussi', 'succès', 'progrès',
            'amélioration', 'avancée', 'développement', 'croissance', 'victoire',
            'gagner', 'réussir', 'accomplir', 'célébrer', 'féliciter', 'bravo',
            'content', 'heureux', 'joie', 'sourire', 'rire', 'plaisir', 'fier',
            'nouveau', 'nouvelle', 'innovation', 'créer', 'construire', 'ouvrir',
            
            # Contexte Guadeloupe et réseaux sociaux
            'festival', 'culture', 'patrimoine', 'tradition', 'créole', 'carnaval',
            'tourisme', 'plage', 'soleil', 'investissement', 'école', 'éducation',
            'spectacle', 'ambiance', 'talent', 'artiste', 'musique', 'paradis',
            'coucher', 'lever', 'paysage', 'nature', 'biodiversité', 'retour'
        }
        
        self.negative_words = {
            # Mots très négatifs
            'terrible', 'horrible', 'catastrophe', 'désastre', 'tragique', 'grave',
            'dangereux', 'inquiétant', 'alarme', 'crise', 'scandale', 'corruption',
            'insupportable', 'inacceptable', 'révoltant', 'choquant', 'dramatique',
            
            # Mots modérément négatifs
            'problème', 'difficulté', 'échec', 'perte', 'baisse', 'diminution',
            'fermeture', 'licenciement', 'grève', 'manifestation', 'protestation',
            'accident', 'blessé', 'mort', 'décès', 'maladie', 'pollution',
            'panne', 'coupure', 'manque', 'pénurie', 'retard', 'annulation',
            'difficile', 'dur', 'compliqué', 'impossible', 'échec', 'erreur',
            
            # Contexte Guadeloupe/Antilles
            'cyclone', 'ouragan', 'séisme', 'sargasse', 'chlordécane', 'violence',
            'délinquance', 'drogue', 'sécheresse', 'pénurie', 'conflit', 'évacuation',
            'alerte', 'risque', 'danger', 'vigilant', 'préparation', 'provisions'
        }
        
        # Mots neutres importants (pour pondération)
        self.neutral_words = {
            'information', 'nouvelles', 'article', 'rapport', 'étude', 'recherche',
            'analyse', 'discussion', 'débat', 'réunion', 'rencontre', 'conférence',
            'présentation', 'annonce', 'déclaration', 'communiqué'
        }
        
        # Intensificateurs (multiplient le score)
        self.intensifiers = {
            'très': 1.5, 'vraiment': 1.4, 'extrêmement': 1.8, 'particulièrement': 1.3,
            'totalement': 1.6, 'complètement': 1.5, 'absolument': 1.7, 'énormément': 1.6
        }
        
        # Négations (inversent le sentiment)
        self.negations = {
            'ne', 'pas', 'point', 'jamais', 'rien', 'aucun', 'aucune', 'sans',
            'non', 'nullement', 'guère'
        }
        
        logger.info("✅ Analyseur de sentiment local initialisé")

    def clean_text(self, text: str) -> str:
        """Nettoyer et normaliser le texte"""
        if not text:
            return ""
        
        # Convertir en minuscules
        text = text.lower()
        
        # Mapper les emojis à leur sentiment
        emoji_positive = ['😊', '😀', '😃', '😄', '😁', '😆', '🙂', '😉', '😍', '🥰', '😘', '🤗', 
                         '🎉', '🎊', '👏', '👍', '❤️', '💕', '💖', '🌟', '⭐', '✨', '🌞', '🌅', '🏖️']
        emoji_negative = ['😟', '😞', '😔', '😢', '😭', '😰', '😨', '😱', '😤', '😡', '🤬', '💔',
                         '⚠️', '🚨', '❌', '💥', '🌪️', '⛈️', '😷', '🤒', '🤢']
        
        # Remplacer les emojis par des mots
        for emoji in emoji_positive:
            if emoji in text:
                text = text.replace(emoji, ' positif ')
        
        for emoji in emoji_negative:
            if emoji in text:
                text = text.replace(emoji, ' négatif ')
        
        # Supprimer les autres emojis restants
        import re
        emoji_pattern = re.compile("["
                                   u"\U0001F600-\U0001F64F"  # emoticons
                                   u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                                   u"\U0001F680-\U0001F6FF"  # transport & map symbols
                                   u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
                                   u"\U00002700-\U000027BF"  # dingbats
                                   u"\U0001f926-\U0001f937"
                                   u"\U00010000-\U0010ffff"
                                   u"\u2640-\u2642" 
                                   u"\u2600-\u2B55"
                                   u"\u200d"
                                   u"\u23cf"
                                   u"\u23e9"
                                   u"\u231a"
                                   u"\ufe0f"  # dingbats
                                   u"\u3030"
                                   "]+", flags=re.UNICODE)
        text = emoji_pattern.sub(r' ', text)
        
        # Supprimer les hashtags mais garder le mot
        text = re.sub(r'#(\w+)', r'\1', text)
        
        # Supprimer les mentions mais garder la structure
        text = re.sub(r'@\w+', '', text)
        
        # Supprimer les URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Supprimer les caractères spéciaux mais garder les accents
        text = re.sub(r'[^\w\sàâäéèêëïîôöùûüÿç]', ' ', text)
        
        # Remplacer les points d'exclamation multiples par le mot "exclamation"
        text = re.sub(r'!+', ' exclamation ', text)
        
        # Supprimer les espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyser le sentiment d'un texte"""
        try:
            if not text:
                return self._default_sentiment()
            
            # Nettoyer le texte
            clean_text = self.clean_text(text)
            words = clean_text.split()
            
            if not words:
                return self._default_sentiment()
            
            # Calculer les scores
            positive_score = 0
            negative_score = 0
            word_details = []
            
            for i, word in enumerate(words):
                # Vérifier les intensificateurs
                intensity = 1.0
                if i > 0 and words[i-1] in self.intensifiers:
                    intensity = self.intensifiers[words[i-1]]
                
                # Vérifier les négations dans les 2 mots précédents
                is_negated = False
                for j in range(max(0, i-2), i):
                    if words[j] in self.negations:
                        is_negated = True
                        break
                
                # Calculer le score du mot
                word_score = 0
                sentiment_type = 'neutral'
                
                if word in self.positive_words:
                    word_score = 1.0 * intensity
                    sentiment_type = 'positive'
                elif word in self.negative_words:
                    word_score = -1.0 * intensity
                    sentiment_type = 'negative'
                
                # Appliquer la négation
                if is_negated and word_score != 0:
                    word_score = -word_score
                    sentiment_type = 'positive' if sentiment_type == 'negative' else 'negative'
                
                # Ajouter au score total
                if word_score > 0:
                    positive_score += word_score
                elif word_score < 0:
                    negative_score += abs(word_score)
                
                # Enregistrer les détails des mots significatifs
                if word_score != 0:
                    word_details.append({
                        'word': word,
                        'score': word_score,
                        'type': sentiment_type,
                        'intensity': intensity,
                        'negated': is_negated
                    })
            
            # Calculer le score final
            total_score = positive_score - negative_score
            total_words = len(words)
            
            # Normaliser le score (-1 à 1)
            if total_words > 0:
                normalized_score = max(-1, min(1, total_score / total_words))
            else:
                normalized_score = 0
            
            # Déterminer la polarité
            if normalized_score > 0.1:
                polarity = 'positive'
            elif normalized_score < -0.1:
                polarity = 'negative'
            else:
                polarity = 'neutral'
            
            # Déterminer l'intensité
            abs_score = abs(normalized_score)
            if abs_score > 0.5:
                intensity_level = 'strong'
            elif abs_score > 0.2:
                intensity_level = 'moderate'
            else:
                intensity_level = 'weak'
            
            return {
                'polarity': polarity,
                'score': round(normalized_score, 3),
                'intensity': intensity_level,
                'positive_score': round(positive_score, 2),
                'negative_score': round(negative_score, 2),
                'word_count': total_words,
                'significant_words': len(word_details),
                'analysis_details': {
                    'words_analyzed': word_details[:10],  # Limiter à 10 mots
                    'detected_patterns': self._detect_patterns(clean_text),
                    'confidence': self._calculate_confidence(word_details, total_words)
                },
                'analyzed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment: {e}")
            return self._default_sentiment(error=str(e))

    def _detect_patterns(self, text: str) -> List[str]:
        """Détecter des patterns contextuels"""
        patterns = []
        
        # Patterns spécifiques à la Guadeloupe
        if any(word in text for word in ['cyclone', 'ouragan', 'tempête']):
            patterns.append('météo_extrême')
        
        if any(word in text for word in ['festival', 'carnaval', 'culture']):
            patterns.append('événement_culturel')
        
        if any(word in text for word in ['tourisme', 'hôtel', 'plage']):
            patterns.append('secteur_touristique')
        
        if any(word in text for word in ['grève', 'manifestation', 'protestation']):
            patterns.append('mouvement_social')
        
        if any(word in text for word in ['économie', 'investissement', 'entreprise']):
            patterns.append('secteur_économique')
        
        # Patterns d'urgence
        if any(word in text for word in ['urgent', 'alerte', 'danger', 'évacuation']):
            patterns.append('situation_urgente')
        
        return patterns

    def _calculate_confidence(self, word_details: List[Dict], total_words: int) -> float:
        """Calculer la confiance de l'analyse"""
        if total_words == 0:
            return 0.0
        
        # Base sur le ratio de mots significatifs
        significant_ratio = len(word_details) / total_words
        
        # Ajuster selon la longueur du texte
        length_factor = min(1.0, total_words / 50)  # Meilleure confiance avec plus de mots
        
        # Ajuster selon la diversité des sentiments
        if word_details:
            sentiment_types = [w['type'] for w in word_details]
            type_diversity = len(set(sentiment_types)) / len(sentiment_types)
            diversity_factor = 1.0 - (type_diversity * 0.3)  # Moins de confiance si sentiments mixtes
        else:
            diversity_factor = 0.5
        
        confidence = significant_ratio * length_factor * diversity_factor
        return round(min(1.0, confidence), 3)

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
                'words_analyzed': [],
                'detected_patterns': [],
                'confidence': 0.0
            },
            'analyzed_at': datetime.now().isoformat()
        }
        
        if error:
            result['error'] = error
        
        return result

    def analyze_articles_batch(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyser le sentiment d'un lot d'articles"""
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
            all_patterns = []
            
            for article in articles:
                # Analyser le titre (plus important)
                title = article.get('title', '')
                title_sentiment = self.analyze_sentiment(title)
                
                # Créer l'article analysé
                analyzed_article = {
                    **article,
                    'sentiment': title_sentiment,
                    'sentiment_summary': {
                        'polarity': title_sentiment['polarity'],
                        'score': title_sentiment['score'],
                        'intensity': title_sentiment['intensity'],
                        'confidence': title_sentiment['analysis_details']['confidence']
                    }
                }
                
                analyzed_articles.append(analyzed_article)
                
                # Mettre à jour le résumé
                sentiment_summary[title_sentiment['polarity']] += 1
                all_scores.append(title_sentiment['score'])
                all_patterns.extend(title_sentiment['analysis_details']['detected_patterns'])
            
            # Calculer les statistiques globales
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            pattern_counts = Counter(all_patterns)
            
            overall_summary = {
                'total_articles': len(articles),
                'sentiment_distribution': sentiment_summary,
                'average_sentiment_score': round(avg_score, 3),
                'most_common_patterns': dict(pattern_counts.most_common(5)),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
            return {
                'articles': analyzed_articles,
                'summary': overall_summary
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse batch: {e}")
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
            'most_common_patterns': {},
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        if error:
            summary['error'] = error
        
        return summary

    def get_sentiment_trends(self, articles_by_date: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Analyser les tendances de sentiment par date"""
        try:
            trends = {}
            
            for date, articles in articles_by_date.items():
                if articles:
                    batch_analysis = self.analyze_articles_batch(articles)
                    trends[date] = {
                        'date': date,
                        'total_articles': len(articles),
                        'average_score': batch_analysis['summary']['average_sentiment_score'],
                        'distribution': batch_analysis['summary']['sentiment_distribution'],
                        'top_patterns': list(batch_analysis['summary']['most_common_patterns'].keys())[:3]
                    }
            
            return {
                'trends_by_date': trends,
                'analysis_period': {
                    'start_date': min(trends.keys()) if trends else None,
                    'end_date': max(trends.keys()) if trends else None,
                    'total_days': len(trends)
                },
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse tendances: {e}")
            return {
                'trends_by_date': {},
                'analysis_period': {'start_date': None, 'end_date': None, 'total_days': 0},
                'error': str(e),
                'generated_at': datetime.now().isoformat()
            }

# Instance globale
local_sentiment_analyzer = LocalSentimentAnalyzer()

# Fonctions utilitaires
def analyze_text_sentiment(text: str) -> Dict[str, Any]:
    """Analyser le sentiment d'un texte (fonction utilitaire)"""
    return local_sentiment_analyzer.analyze_sentiment(text)

def analyze_articles_sentiment(articles: List[Dict]) -> Dict[str, Any]:
    """Analyser le sentiment d'une liste d'articles (fonction utilitaire)"""
    return local_sentiment_analyzer.analyze_articles_batch(articles)

if __name__ == "__main__":
    # Tests
    test_texts = [
        "Excellent festival de musique créole à Pointe-à-Pitre !",
        "Grave accident de la route en Guadeloupe, plusieurs blessés",
        "Nouvelle école construite à Basse-Terre",
        "Alerte cyclone très dangereuse pour les Antilles"
    ]
    
    for text in test_texts:
        result = analyze_text_sentiment(text)
        print(f"Texte: {text}")
        print(f"Sentiment: {result['polarity']} (score: {result['score']}, intensité: {result['intensity']})")
        print(f"Patterns: {result['analysis_details']['detected_patterns']}")
        print("---")