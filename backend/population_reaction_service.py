"""
Service d'anticipation de la réaction de la population
Analyse croisée des articles, réseaux sociaux et sentiment pour prédire les réactions
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
import os
from gpt_sentiment_service import gpt_sentiment_analyzer

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PopulationReactionPredictor:
    def __init__(self):
        """Initialiser le service de prédiction des réactions"""
        
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            
            # Collections
            self.articles_collection = self.db.articles_guadeloupe
            self.social_collection = self.db.social_posts
            self.sentiment_cache = self.db.sentiment_analysis_cache
            self.reaction_predictions = self.db.reaction_predictions
            
            logger.info("✅ Service prédiction réactions initialisé")
        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB prédiction: {e}")
            self.client = None

    def analyze_population_reaction(self, text: str, context: Dict = None) -> Dict[str, Any]:
        """Analyser et prédire la réaction de la population pour un texte donné"""
        try:
            if not self.client:
                return {'error': 'Service non disponible'}
            
            # 1. Analyse de sentiment enrichie du texte principal
            main_sentiment = gpt_sentiment_analyzer.analyze_sentiment(text)
            
            # 2. Rechercher des contenus similaires dans les articles récents
            similar_articles = self._find_similar_content(text, collection=self.articles_collection, limit=5)
            
            # 3. Rechercher des contenus similaires dans les réseaux sociaux
            similar_social = self._find_similar_content(text, collection=self.social_collection, limit=10)
            
            # 4. Analyser les tendances historiques
            historical_trends = self._analyze_historical_trends(main_sentiment)
            
            # 5. Identifier les groupes d'influence
            stakeholder_influence = self._analyze_stakeholder_influence(main_sentiment)
            
            # 6. Prédire les réactions par segment de population
            reaction_prediction = self._predict_reactions_by_segment(
                main_sentiment, similar_articles, similar_social, context
            )
            
            # 7. Générer des recommandations stratégiques
            strategic_recommendations = self._generate_strategic_recommendations(
                main_sentiment, reaction_prediction, stakeholder_influence
            )
            
            # 8. Créer la réponse complète
            result = {
                'text_analyzed': text[:200] + "..." if len(text) > 200 else text,
                'main_sentiment': main_sentiment,
                'population_reaction_forecast': {
                    'overall_reaction': reaction_prediction['overall'],
                    'by_demographic': reaction_prediction['demographics'],
                    'by_region': reaction_prediction['regions'],
                    'intensity_level': reaction_prediction['intensity'],
                    'polarization_risk': reaction_prediction['polarization_risk']
                },
                'supporting_data': {
                    'similar_articles': len(similar_articles),
                    'similar_social_posts': len(similar_social),
                    'articles_sample': similar_articles[:3],
                    'social_sample': similar_social[:5]
                },
                'historical_context': historical_trends,
                'influence_factors': stakeholder_influence,
                'strategic_recommendations': strategic_recommendations,
                'confidence_level': self._calculate_confidence(similar_articles, similar_social),
                'analysis_timestamp': datetime.now().isoformat()
            }
            
            # Sauvegarder la prédiction
            self._save_prediction(result)
            
            logger.info(f"✅ Prédiction réaction générée: {reaction_prediction['overall']} (confiance: {result['confidence_level']})")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur prédiction réaction: {e}")
            return {'error': str(e)}

    def _find_similar_content(self, text: str, collection, limit: int = 5) -> List[Dict]:
        """Trouver du contenu similaire par mots-clés"""
        try:
            # Extraire les mots-clés importants du texte
            keywords = self._extract_keywords(text)
            
            # Recherche par mots-clés dans les titres/contenus
            query = {
                '$or': [
                    {'title': {'$regex': '|'.join(keywords), '$options': 'i'}},
                    {'content': {'$regex': '|'.join(keywords), '$options': 'i'}}
                ],
                'date': {'$gte': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}
            }
            
            results = list(collection.find(query, {'_id': 0}).sort('scraped_at', -1).limit(limit))
            return results
            
        except Exception as e:
            logger.warning(f"Erreur recherche contenu similaire: {e}")
            return []

    def _extract_keywords(self, text: str) -> List[str]:
        """Extraire les mots-clés importants du texte"""
        # Mots-clés spécifiques à la Guadeloupe
        guadeloupe_keywords = [
            'Guy Losbar', 'CD971', 'Conseil Départemental', 'Guadeloupe', 
            'Pointe-à-Pitre', 'Basse-Terre', 'budget', 'route', 'école',
            'collège', 'transport', 'social', 'aide', 'famille', 'jeune'
        ]
        
        # Chercher les mots-clés présents dans le texte
        text_lower = text.lower()
        found_keywords = [kw for kw in guadeloupe_keywords if kw.lower() in text_lower]
        
        # Ajouter des mots significatifs (> 4 caractères)
        words = text.split()
        significant_words = [w.strip('.,!?()[]') for w in words if len(w.strip('.,!?()[]')) > 4]
        
        return found_keywords + significant_words[:5]

    def _analyze_historical_trends(self, sentiment: Dict) -> Dict[str, Any]:
        """Analyser les tendances historiques basées sur le sentiment"""
        try:
            # Rechercher des analyses similaires dans l'historique
            similar_sentiments = list(self.sentiment_cache.find({
                'sentiment_result.polarity': sentiment['polarity'],
                'analyzed_at': {'$gte': datetime.now() - timedelta(days=90)}
            }).limit(20))
            
            # Analyser les patterns
            if not similar_sentiments:
                return {'trend': 'insufficient_data', 'message': 'Pas assez de données historiques'}
            
            # Calculer les tendances
            avg_intensity = sum([
                1 if s['sentiment_result']['intensity'] == 'strong' else 
                0.5 if s['sentiment_result']['intensity'] == 'moderate' else 0.2
                for s in similar_sentiments
            ]) / len(similar_sentiments)
            
            return {
                'trend': 'increasing' if avg_intensity > 0.6 else 'stable' if avg_intensity > 0.3 else 'decreasing',
                'similar_cases': len(similar_sentiments),
                'average_intensity': round(avg_intensity, 2),
                'pattern': 'recurring' if len(similar_sentiments) > 10 else 'occasional'
            }
            
        except Exception as e:
            logger.warning(f"Erreur analyse tendances: {e}")
            return {'trend': 'unknown', 'error': str(e)}

    def _analyze_stakeholder_influence(self, sentiment: Dict) -> Dict[str, Any]:
        """Analyser l'influence des parties prenantes mentionnées"""
        try:
            personalities = sentiment['analysis_details'].get('personalities_mentioned', [])
            institutions = sentiment['analysis_details'].get('institutions_mentioned', [])
            
            # Base de données d'influence des personnalités guadeloupéennes
            influence_db = {
                'Guy Losbar': {'level': 'high', 'domains': ['politique', 'économie'], 'polarization': 'moderate'},
                'CD971': {'level': 'high', 'domains': ['administration', 'social'], 'polarization': 'low'},
                'Conseil Départemental': {'level': 'high', 'domains': ['politique', 'administration'], 'polarization': 'moderate'}
            }
            
            influences = []
            total_influence = 0
            
            for entity in personalities + institutions:
                if entity in influence_db:
                    info = influence_db[entity]
                    influences.append({
                        'entity': entity,
                        'influence_level': info['level'],
                        'domains': info['domains'],
                        'polarization_potential': info['polarization']
                    })
                    total_influence += 3 if info['level'] == 'high' else 2 if info['level'] == 'medium' else 1
            
            return {
                'mentioned_stakeholders': influences,
                'total_influence_score': total_influence,
                'high_influence_entities': [inf['entity'] for inf in influences if inf['influence_level'] == 'high'],
                'polarization_risk': 'high' if any(inf['polarization_potential'] == 'high' for inf in influences) else 'moderate'
            }
            
        except Exception as e:
            logger.warning(f"Erreur analyse influence: {e}")
            return {'error': str(e)}

    def _predict_reactions_by_segment(self, sentiment: Dict, articles: List, social: List, context: Dict = None) -> Dict[str, Any]:
        """Prédire les réactions par segment de population"""
        try:
            polarity = sentiment['polarity']
            intensity = sentiment['intensity']
            urgency = sentiment['analysis_details'].get('urgency_level', 'faible')
            themes = sentiment['analysis_details'].get('themes', [])
            
            # Segments de population guadeloupéenne
            segments = {
                'jeunes_18_35': self._predict_youth_reaction(polarity, intensity, themes),
                'familles': self._predict_family_reaction(polarity, intensity, themes),
                'seniors_plus_55': self._predict_senior_reaction(polarity, intensity, themes),
                'entrepreneurs': self._predict_business_reaction(polarity, intensity, themes),
                'fonctionnaires': self._predict_civil_servant_reaction(polarity, intensity, themes)
            }
            
            # Réactions par communes principales
            regions = {
                'pointe_a_pitre': self._predict_regional_reaction('Pointe-à-Pitre', polarity, themes),
                'basse_terre': self._predict_regional_reaction('Basse-Terre', polarity, themes),
                'grande_terre': self._predict_regional_reaction('Grande-Terre', polarity, themes),
                'communes_rurales': self._predict_regional_reaction('Rural', polarity, themes)
            }
            
            # Calculer la réaction globale
            overall_scores = [seg['reaction_score'] for seg in segments.values()]
            overall_reaction = sum(overall_scores) / len(overall_scores)
            
            overall_label = (
                'très positive' if overall_reaction > 0.6 else
                'positive' if overall_reaction > 0.2 else
                'neutre' if overall_reaction > -0.2 else
                'négative' if overall_reaction > -0.6 else
                'très négative'
            )
            
            # Évaluer le risque de polarisation
            score_variance = sum([(score - overall_reaction) ** 2 for score in overall_scores]) / len(overall_scores)
            polarization_risk = 'élevé' if score_variance > 0.5 else 'modéré' if score_variance > 0.2 else 'faible'
            
            return {
                'overall': overall_label,
                'overall_score': round(overall_reaction, 2),
                'demographics': segments,
                'regions': regions,
                'intensity': urgency,
                'polarization_risk': polarization_risk,
                'mobilization_potential': self._assess_mobilization_potential(intensity, urgency, themes)
            }
            
        except Exception as e:
            logger.error(f"Erreur prédiction par segment: {e}")
            return {'error': str(e)}

    def _predict_youth_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des jeunes (18-35 ans)"""
        base_score = 0.5 if polarity == 'positive' else -0.5 if polarity == 'negative' else 0
        
        # Les jeunes sont plus sensibles à l'emploi, l'éducation, l'environnement
        if any(t in themes for t in ['education', 'emploi', 'environnement']):
            base_score += 0.3 if polarity == 'positive' else -0.3
            
        intensity_multiplier = 1.5 if intensity == 'strong' else 1.2 if intensity == 'moderate' else 1.0
        
        return {
            'reaction_score': base_score * intensity_multiplier,
            'reaction_label': self._score_to_label(base_score * intensity_multiplier),
            'key_concerns': ['emploi', 'formation', 'logement', 'transport'],
            'engagement_likelihood': 'élevé' if abs(base_score * intensity_multiplier) > 0.4 else 'modéré'
        }

    def _predict_family_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des familles"""
        base_score = 0.3 if polarity == 'positive' else -0.3 if polarity == 'negative' else 0
        
        # Les familles sont sensibles à l'éducation, la santé, les aides sociales
        if any(t in themes for t in ['education', 'social', 'santé']):
            base_score += 0.4 if polarity == 'positive' else -0.4
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['éducation', 'santé', 'aide sociale', 'sécurité'],
            'engagement_likelihood': 'modéré'
        }

    def _predict_senior_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des seniors (55+ ans)"""
        base_score = 0.2 if polarity == 'positive' else -0.2 if polarity == 'negative' else 0
        
        # Les seniors sont sensibles à la santé, aux services publics
        if any(t in themes for t in ['santé', 'social', 'transport']):
            base_score += 0.3 if polarity == 'positive' else -0.3
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),  
            'key_concerns': ['santé', 'retraite', 'transport', 'services publics'],
            'engagement_likelihood': 'faible à modéré'
        }

    def _predict_business_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des entrepreneurs"""
        base_score = 0.6 if polarity == 'positive' else -0.6 if polarity == 'negative' else 0
        
        # Les entrepreneurs sont sensibles à l'économie, aux investissements
        if any(t in themes for t in ['économie', 'infrastructure', 'tourisme']):
            base_score += 0.4 if polarity == 'positive' else -0.4
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['économie', 'fiscalité', 'infrastructure', 'réglementation'],
            'engagement_likelihood': 'élevé'
        }

    def _predict_civil_servant_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des fonctionnaires"""
        base_score = 0.1 if polarity == 'positive' else -0.1 if polarity == 'negative' else 0
        
        # Les fonctionnaires sont sensibles aux réformes administratives
        if any(t in themes for t in ['administration', 'politique']):
            base_score += 0.2 if polarity == 'positive' else -0.2
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['emploi public', 'réformes', 'conditions de travail'],
            'engagement_likelihood': 'faible'
        }

    def _predict_regional_reaction(self, region: str, polarity: str, themes: List) -> Dict:
        """Prédire la réaction par région"""
        base_score = 0.3 if polarity == 'positive' else -0.3 if polarity == 'negative' else 0
        
        # Ajustements par région
        if region == 'Pointe-à-Pitre':
            # Plus urbain, plus sensible à l'économie
            if 'économie' in themes:
                base_score += 0.2 if polarity == 'positive' else -0.2
        elif region == 'Rural':
            # Plus sensible à l'agriculture, l'environnement
            if any(t in themes for t in ['environnement', 'agriculture']):
                base_score += 0.3 if polarity == 'positive' else -0.3
                
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'specific_concerns': self._get_regional_concerns(region)
        }

    def _get_regional_concerns(self, region: str) -> List[str]:
        """Obtenir les préoccupations spécifiques par région"""
        concerns = {
            'Pointe-à-Pitre': ['économie', 'emploi', 'transport', 'sécurité'],
            'Basse-Terre': ['administration', 'services publics', 'éducation'],
            'Grande-Terre': ['tourisme', 'agriculture', 'infrastructure'],
            'Rural': ['agriculture', 'environnement', 'désenclavement', 'services']
        }
        return concerns.get(region, ['général'])

    def _assess_mobilization_potential(self, intensity: str, urgency: str, themes: List) -> str:
        """Évaluer le potentiel de mobilisation sociale"""
        mobilization_score = 0
        
        # Impact de l'intensité
        if intensity == 'strong':
            mobilization_score += 3
        elif intensity == 'moderate':
            mobilization_score += 2
        else:
            mobilization_score += 1
            
        # Impact de l'urgence
        if urgency == 'élevé':
            mobilization_score += 3
        elif urgency == 'moyen':
            mobilization_score += 2
        else:
            mobilization_score += 1
            
        # Thèmes mobilisateurs
        mobilizing_themes = ['social', 'education', 'emploi', 'transport', 'environnement']
        if any(t in themes for t in mobilizing_themes):
            mobilization_score += 2
            
        if mobilization_score >= 7:
            return 'élevé'
        elif mobilization_score >= 4:
            return 'modéré'
        else:
            return 'faible'

    def _generate_strategic_recommendations(self, sentiment: Dict, reaction: Dict, influence: Dict) -> List[str]:
        """Générer des recommandations stratégiques"""
        recommendations = []
        
        polarity = sentiment['polarity']
        urgency = sentiment['analysis_details'].get('urgency_level', 'faible')
        polarization_risk = reaction.get('polarization_risk', 'faible')
        
        # Recommandations basées sur le sentiment
        if polarity == 'negative' and urgency == 'élevé':
            recommendations.append("Communication de crise recommandée")
            recommendations.append("Mise en place d'une cellule de gestion de crise")
            
        if polarization_risk == 'élevé':
            recommendations.append("Dialogue concerté avec les différents groupes")
            recommendations.append("Communication différenciée par segment de population")
            
        # Recommandations basées sur l'influence
        if influence.get('total_influence_score', 0) > 5:
            recommendations.append("Engagement direct avec les personnalités influentes")
            
        # Recommandations basées sur la mobilisation
        if reaction.get('mobilization_potential', 'faible') == 'élevé':
            recommendations.append("Anticipation des besoins logistiques et sécuritaires")
            recommendations.append("Préparation de canaux de dialogue supplémentaires")
            
        return recommendations or ["Suivi standard de la situation"]

    def _score_to_label(self, score: float) -> str:
        """Convertir un score en label"""
        if score > 0.5:
            return 'très positive'
        elif score > 0.2:
            return 'positive'
        elif score > -0.2:
            return 'neutre'
        elif score > -0.5:
            return 'négative'
        else:
            return 'très négative'

    def _calculate_confidence(self, articles: List, social: List) -> float:
        """Calculer le niveau de confiance de la prédiction"""
        # Plus il y a de données similaires, plus la confiance est élevée
        data_points = len(articles) + len(social)
        
        if data_points >= 10:
            return 0.9
        elif data_points >= 5:
            return 0.75
        elif data_points >= 2:
            return 0.6
        else:
            return 0.4

    def _save_prediction(self, prediction: Dict):
        """Sauvegarder la prédiction pour analyse future"""
        try:
            if self.client:
                prediction['_prediction_id'] = f"pred_{int(datetime.now().timestamp())}"
                self.reaction_predictions.insert_one(prediction)
        except Exception as e:
            logger.warning(f"Erreur sauvegarde prédiction: {e}")

# Instance globale
population_reaction_predictor = PopulationReactionPredictor()

# Fonction utilitaire
def predict_population_reaction(text: str, context: Dict = None) -> Dict[str, Any]:
    """Prédire la réaction de la population pour un texte donné"""
    return population_reaction_predictor.analyze_population_reaction(text, context)