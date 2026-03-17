# backend/viral_escalation_predictor.py
"""
Service de prédiction d'escalade virale
Analyse les patterns historiques pour prédire si un contenu va devenir viral
Version refaite - sécurisée et optimisée
"""

import os
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
import hashlib
import json

logger = logging.getLogger(__name__)

class ViralEscalationPredictor:
    """Service de prédiction d'escalade virale basé sur l'analyse des patterns"""
    
    def __init__(self, db=None):
        """
        Initialise le prédicteur d'escalade virale
        
        Args:
            db: Instance de base de données MongoDB (optionnelle)
        """
        self.db = db
        self.patterns = {}
        self.viral_keywords = self._init_viral_keywords()
        self.escalation_indicators = self._init_escalation_indicators()
        self.temporal_patterns = {}
        self.source_patterns = {}
        
        # Charger les patterns historiques si DB disponible
        if self.db is not None:
            try:
                self.load_historical_patterns()
            except Exception as e:
                logger.warning(f"Impossible de charger les patterns historiques: {e}")
    
    def _init_viral_keywords(self) -> Dict[str, float]:
        """Mots-clés viraux avec leurs poids pour la Guadeloupe"""
        return {
            # Urgence et émotion
            'urgent': 2.0, 'breaking': 2.0, 'alerte': 2.0, 'attention': 1.5,
            'choc': 2.5, 'scandale': 2.5, 'incroyable': 1.8, 'exclusif': 1.7,
            
            # Politique locale
            'cd971': 2.0, 'conseil départemental': 1.8, 'guy losbar': 2.2,
            'région guadeloupe': 1.8, 'préfet': 1.5, 'maire': 1.3,
            
            # Infrastructures critiques
            'eau': 2.0, 'électricité': 1.8, 'route': 1.5, 'aéroport': 1.7,
            'hôpital': 2.0, 'chu': 1.8, 'école': 1.5, 'collège': 1.5,
            
            # Crises environnementales
            'sargasses': 2.5, 'cyclone': 3.0, 'séisme': 2.8, 'inondation': 2.0,
            'sécheresse': 1.8, 'pollution': 1.7,
            
            # Social et économique
            'grève': 2.0, 'manifestation': 1.8, 'blocage': 2.2, 'conflit': 1.7,
            'fermeture': 1.8, 'licenciement': 1.5, 'augmentation': 1.3,
            
            # Négativité générale
            'problème': 1.2, 'difficultés': 1.3, 'inquiétude': 1.5,
            'colère': 1.8, 'indignation': 2.0, 'protestation': 1.7
        }
    
    def _init_escalation_indicators(self) -> Dict[str, Any]:
        """Indicateurs d'escalade virale"""
        return {
            'temporal_velocity': {
                'keywords': ['maintenant', 'immédiatement', 'ce soir', 'aujourd\'hui'],
                'weight': 1.5
            },
            'call_to_action': {
                'keywords': ['partagez', 'diffusez', 'alertez', 'prévenez', 'mobilisons'],
                'weight': 2.0
            },
            'emotional_amplifiers': {
                'keywords': ['inadmissible', 'intolérable', 'révoltant', 'honteux'],
                'weight': 1.8
            },
            'authority_challenge': {
                'keywords': ['incompétence', 'mensonge', 'corruption', 'scandale'],
                'weight': 2.2
            }
        }
    
    def load_historical_patterns(self):
        """Charge les patterns historiques depuis la base de données"""
        try:
            # ✅ Correction : vérification correcte de la DB
            if self.db is None:
                logger.warning("Base de données non disponible pour charger les patterns")
                return
            
            # Charger les articles récents avec scores viraux
            one_month_ago = datetime.utcnow() - timedelta(days=30)
            
            articles = list(self.db.articles.find({
                "published_at": {"$gte": one_month_ago},
                "viral_score": {"$exists": True, "$gt": 0.3}
            }).limit(500))
            
            logger.info(f"Analyse de {len(articles)} articles pour extraction des patterns")
            
            # Analyser les patterns temporels
            self._analyze_temporal_patterns(articles)
            
            # Analyser les patterns par source
            self._analyze_source_patterns(articles)
            
            # Analyser les patterns de contenu
            self._analyze_content_patterns(articles)
            
            logger.info("Patterns historiques chargés avec succès")
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement des patterns: {e}")
    
    def _analyze_temporal_patterns(self, articles: List[Dict[str, Any]]):
        """Analyse les patterns temporels de viralité"""
        try:
            hourly_viral = defaultdict(list)
            daily_viral = defaultdict(list)
            
            for article in articles:
                try:
                    pub_date = article.get('published_at')
                    if isinstance(pub_date, str):
                        pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                    
                    if pub_date:
                        hour = pub_date.hour
                        day_of_week = pub_date.weekday()
                        viral_score = article.get('viral_score', 0)
                        
                        hourly_viral[hour].append(viral_score)
                        daily_viral[day_of_week].append(viral_score)
                        
                except Exception as e:
                    logger.debug(f"Erreur analyse temporelle article: {e}")
                    continue
            
            # Calculer les moyennes
            self.temporal_patterns = {
                'hourly_avg': {h: sum(scores)/len(scores) for h, scores in hourly_viral.items() if scores},
                'daily_avg': {d: sum(scores)/len(scores) for d, scores in daily_viral.items() if scores},
                'peak_hours': sorted(hourly_viral.keys(), key=lambda h: sum(hourly_viral[h])/len(hourly_viral[h]) if hourly_viral[h] else 0, reverse=True)[:3],
                'peak_days': sorted(daily_viral.keys(), key=lambda d: sum(daily_viral[d])/len(daily_viral[d]) if daily_viral[d] else 0, reverse=True)[:3]
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse patterns temporels: {e}")
    
    def _analyze_source_patterns(self, articles: List[Dict[str, Any]]):
        """Analyse les patterns par source médiatique"""
        try:
            source_viral = defaultdict(list)
            
            for article in articles:
                source = article.get('source', 'unknown')
                viral_score = article.get('viral_score', 0)
                source_viral[source].append(viral_score)
            
            self.source_patterns = {
                source: {
                    'avg_viral': sum(scores) / len(scores),
                    'max_viral': max(scores),
                    'count': len(scores),
                    'viral_ratio': len([s for s in scores if s > 0.5]) / len(scores)
                }
                for source, scores in source_viral.items() if len(scores) >= 3
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse patterns sources: {e}")
    
    def _analyze_content_patterns(self, articles: List[Dict[str, Any]]):
        """Analyse les patterns de contenu viral"""
        try:
            viral_phrases = defaultdict(int)
            viral_lengths = []
            
            for article in articles:
                content = article.get('content', '') + ' ' + article.get('title', '')
                viral_score = article.get('viral_score', 0)
                
                if viral_score > 0.6:  # Contenu hautement viral
                    # Extraire des phrases courtes (2-4 mots)
                    words = re.findall(r'\b\w+\b', content.lower())
                    for i in range(len(words) - 1):
                        phrase = ' '.join(words[i:i+2])
                        viral_phrases[phrase] += 1
                        if i < len(words) - 2:
                            phrase3 = ' '.join(words[i:i+3])
                            viral_phrases[phrase3] += 1
                    
                    viral_lengths.append(len(content))
            
            # Garder les phrases les plus fréquentes
            self.patterns['viral_phrases'] = dict(sorted(viral_phrases.items(), key=lambda x: x[1], reverse=True)[:50])
            self.patterns['avg_viral_length'] = sum(viral_lengths) / len(viral_lengths) if viral_lengths else 0
            
        except Exception as e:
            logger.error(f"Erreur analyse patterns contenu: {e}")
    
    def predict_escalation(self, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prédit l'escalade virale d'un contenu
        
        Args:
            content_data: Dictionnaire avec 'content', 'title', 'source', etc.
            
        Returns:
            Prédiction avec probabilité d'escalade et recommandations
        """
        try:
            content = str(content_data.get('content', ''))
            title = str(content_data.get('title', ''))
            source = str(content_data.get('source', ''))
            
            full_text = f"{title} {content}".lower()
            
            # Scores de base
            keyword_score = self._calculate_keyword_score(full_text)
            escalation_score = self._calculate_escalation_score(full_text)
            temporal_score = self._calculate_temporal_score()
            source_score = self._calculate_source_score(source)
            length_score = self._calculate_length_score(len(content))
            
            # Score composite
            weights = {
                'keywords': 0.25,
                'escalation': 0.25,
                'temporal': 0.15,
                'source': 0.20,
                'length': 0.15
            }
            
            total_score = (
                keyword_score * weights['keywords'] +
                escalation_score * weights['escalation'] +
                temporal_score * weights['temporal'] +
                source_score * weights['source'] +
                length_score * weights['length']
            )
            
            # Probabilité d'escalade
            escalation_probability = min(total_score / 10.0, 1.0)  # Normaliser sur 10 points max
            
            # Niveau de confiance basé sur la disponibilité des données
            confidence = self._calculate_confidence(content_data)
            
            # Classification du risque
            risk_level = self._classify_risk_level(escalation_probability)
            
            # Recommandations
            recommendations = self._generate_recommendations(escalation_probability, content_data)
            
            # Facteurs détaillés
            factors = {
                'keyword_score': round(keyword_score, 2),
                'escalation_indicators': round(escalation_score, 2),
                'temporal_advantage': round(temporal_score, 2),
                'source_credibility': round(source_score, 2),
                'content_length_optimal': round(length_score, 2)
            }
            
            result = {
                'escalation_probability': round(escalation_probability, 3),
                'risk_level': risk_level,
                'confidence': round(confidence, 3),
                'factors': factors,
                'total_score': round(total_score, 2),
                'recommendations': recommendations,
                'predicted_at': datetime.utcnow().isoformat(),
                'prediction_id': self._generate_prediction_id(content_data)
            }
            
            # Sauvegarder la prédiction si DB disponible
            if self.db is not None:
                self.save_prediction({**result, 'content_hash': self._hash_content(full_text)})
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur prédiction escalade: {e}")
            return {
                'escalation_probability': 0.0,
                'risk_level': 'unknown',
                'confidence': 0.0,
                'error': str(e)
            }
    
    def _calculate_keyword_score(self, text: str) -> float:
        """Calcule le score basé sur les mots-clés viraux"""
        score = 0.0
        text_words = re.findall(r'\b\w+\b', text.lower())
        
        for keyword, weight in self.viral_keywords.items():
            count = text.lower().count(keyword.lower())
            if count > 0:
                # Score diminue avec la répétition excessive
                effective_count = min(count, 3)
                score += weight * effective_count * 0.5  # Facteur de modération
        
        return min(score, 5.0)  # Score max de 5
    
    def _calculate_escalation_score(self, text: str) -> float:
        """Calcule le score des indicateurs d'escalade"""
        score = 0.0
        
        for indicator_type, config in self.escalation_indicators.items():
            keywords = config['keywords']
            weight = config['weight']
            
            found_keywords = sum(1 for kw in keywords if kw in text)
            if found_keywords > 0:
                score += weight * min(found_keywords, 2)  # Max 2 par catégorie
        
        return min(score, 3.0)  # Score max de 3
    
    def _calculate_temporal_score(self) -> float:
        """Calcule le score basé sur le moment de publication"""
        now = datetime.now()
        current_hour = now.hour
        current_day = now.weekday()
        
        hour_score = 0.0
        day_score = 0.0
        
        # Score basé sur les heures de pointe
        if hasattr(self, 'temporal_patterns') and self.temporal_patterns:
            peak_hours = self.temporal_patterns.get('peak_hours', [])
            peak_days = self.temporal_patterns.get('peak_days', [])
            
            if current_hour in peak_hours[:2]:  # Top 2 heures
                hour_score = 1.0
            elif current_hour in peak_hours:
                hour_score = 0.5
            
            if current_day in peak_days[:2]:  # Top 2 jours
                day_score = 0.5
            elif current_day in peak_days:
                day_score = 0.3
        else:
            # Valeurs par défaut basées sur l'observation
            if 7 <= current_hour <= 9 or 17 <= current_hour <= 20:  # Heures de pointe
                hour_score = 1.0
            elif 12 <= current_hour <= 14:  # Pause déjeuner
                hour_score = 0.7
            
            if current_day < 5:  # Jours de semaine
                day_score = 0.5
        
        return hour_score + day_score
    
    def _calculate_source_score(self, source: str) -> float:
        """Calcule le score basé sur la crédibilité de la source"""
        if not source:
            return 0.0
        
        source_lower = source.lower()
        
        # Sources reconnues en Guadeloupe
        if any(trusted in source_lower for trusted in ['france-antilles', 'rci', 'la 1ère']):
            base_score = 1.5
        elif any(local in source_lower for local in ['karibinfo', 'domactu']):
            base_score = 1.2
        else:
            base_score = 0.8
        
        # Bonus si on a des patterns historiques
        if hasattr(self, 'source_patterns') and source in self.source_patterns:
            pattern = self.source_patterns[source]
            viral_ratio = pattern.get('viral_ratio', 0)
            base_score += viral_ratio * 0.5
        
        return min(base_score, 2.0)
    
    def _calculate_length_score(self, content_length: int) -> float:
        """Calcule le score basé sur la longueur optimale du contenu"""
        # Longueur optimale pour la viralité : 150-800 caractères
        if 150 <= content_length <= 800:
            return 1.0
        elif 800 < content_length <= 1500:
            return 0.7
        elif 100 <= content_length < 150:
            return 0.5
        else:
            return 0.2
    
    def _calculate_confidence(self, content_data: Dict[str, Any]) -> float:
        """Calcule le niveau de confiance de la prédiction"""
        confidence = 0.5  # Base
        
        # Disponibilité des données
        if content_data.get('content'):
            confidence += 0.2
        if content_data.get('title'):
            confidence += 0.1
        if content_data.get('source'):
            confidence += 0.1
        
        # Patterns historiques disponibles
        if hasattr(self, 'temporal_patterns') and self.temporal_patterns:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _classify_risk_level(self, probability: float) -> str:
        """Classifie le niveau de risque d'escalade"""
        if probability >= 0.8:
            return "critique"
        elif probability >= 0.6:
            return "élevé"
        elif probability >= 0.4:
            return "modéré"
        elif probability >= 0.2:
            return "faible"
        else:
            return "minimal"
    
    def _generate_recommendations(self, probability: float, content_data: Dict[str, Any]) -> List[str]:
        """Génère des recommandations basées sur la probabilité d'escalade"""
        recommendations = []
        
        if probability >= 0.8:
            recommendations.extend([
                "🚨 Risque viral critique : surveillance renforcée requise",
                "📞 Alerter immédiatement l'équipe de communication de crise",
                "📝 Préparer une réponse officielle dans l'heure",
                "👥 Mobiliser les porte-paroles et relais institutionnels"
            ])
        elif probability >= 0.6:
            recommendations.extend([
                "⚠️ Risque viral élevé : monitoring actif recommandé",
                "📊 Analyser l'évolution des métriques d'engagement",
                "💬 Préparer des éléments de réponse factuels",
                "🎯 Identifier les influenceurs locaux pour contre-narratif"
            ])
        elif probability >= 0.4:
            recommendations.extend([
                "📈 Potentiel viral modéré : surveillance normale",
                "📋 Documenter pour analyse des tendances",
                "🔍 Vérifier les faits avant diffusion plus large"
            ])
        else:
            recommendations.extend([
                "✅ Risque viral faible : diffusion normale",
                "📚 Archiver pour référence future"
            ])
        
        return recommendations
    
    def _generate_prediction_id(self, content_data: Dict[str, Any]) -> str:
        """Génère un ID unique pour la prédiction"""
        content = str(content_data.get('content', ''))
        title = str(content_data.get('title', ''))
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        hash_input = f"{title}_{content[:100]}_{timestamp}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    def _hash_content(self, content: str) -> str:
        """Hash du contenu pour éviter les doublons"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def save_prediction(self, prediction_data: Dict[str, Any]) -> bool:
        """Sauvegarde une prédiction en base"""
        try:
            # ✅ Correction : vérification correcte de la DB
            if self.db is None:
                logger.warning("Impossible de sauvegarder - base de données non disponible")
                return False
            
            # Ajouter timestamp et métadonnées
            prediction_data.update({
                'created_at': datetime.utcnow(),
                'version': '2.0',
                'model': 'viral_escalation_predictor'
            })
            
            result = self.db.viral_predictions.insert_one(prediction_data)
            return bool(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde prédiction: {e}")
            return False
    
    def get_recent_predictions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Récupère les prédictions récentes"""
        try:
            # ✅ Correction : vérification correcte de la DB
            if self.db is None:
                logger.warning("Base de données non disponible")
                return []
            
            predictions = list(
                self.db.viral_predictions
                .find({}, {'_id': 0})
                .sort('created_at', -1)
                .limit(limit)
            )
            
            return predictions
            
        except Exception as e:
            logger.error(f"Erreur récupération prédictions: {e}")
            return []
    
    def analyze_prediction_accuracy(self) -> Dict[str, Any]:
        """Analyse la précision des prédictions passées"""
        try:
            # ✅ Correction : vérification correcte de la DB
            if self.db is None:
                return {"error": "Base de données non disponible"}
            
            # Récupérer les prédictions des 7 derniers jours
            week_ago = datetime.utcnow() - timedelta(days=7)
            predictions = list(
                self.db.viral_predictions.find({
                    'created_at': {'$gte': week_ago}
                })
            )
            
            if not predictions:
                return {"message": "Pas assez de données pour l'analyse"}
            
            # Analyser la distribution des prédictions
            risk_distribution = defaultdict(int)
            probability_sum = 0
            
            for pred in predictions:
                risk_level = pred.get('risk_level', 'unknown')
                risk_distribution[risk_level] += 1
                probability_sum += pred.get('escalation_probability', 0)
            
            avg_probability = probability_sum / len(predictions)
            
            return {
                'total_predictions': len(predictions),
                'average_escalation_probability': round(avg_probability, 3),
                'risk_distribution': dict(risk_distribution),
                'analysis_period': '7_days'
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse précision: {e}")
            return {"error": str(e)}

# ✅ Pas d'instanciation automatique au niveau module
# Factory function pour créer une instance
def create_viral_predictor(db=None) -> Optional[ViralEscalationPredictor]:
    """
    Factory function pour créer une instance du prédicteur viral
    
    Args:
        db: Instance de base de données MongoDB
        
    Returns:
        Instance du prédicteur ou None en cas d'erreur
    """
    try:
        return ViralEscalationPredictor(db)
    except Exception as e:
        logger.error(f"Impossible de créer le prédicteur viral: {e}")
        return None

# Pour compatibilité avec l'ancien code
def get_escalation_predictor(db=None) -> Optional[ViralEscalationPredictor]:
    """Alias pour create_viral_predictor"""
    return create_viral_predictor(db)

if __name__ == "__main__":
    # Test du service
    print("=== Test du prédicteur d'escalade virale ===")
    
    predictor = ViralEscalationPredictor()
    
    # Test avec un contenu d'exemple
    test_content = {
        'content': "URGENT: Nouvelle coupure d'eau prévue dans plusieurs communes. Les habitants s'indignent face à cette situation récurrente qui devient intolérable.",
        'title': "Coupure d'eau: la colère monte en Guadeloupe",
        'source': "France-Antilles Guadeloupe"
    }
    
    prediction = predictor.predict_escalation(test_content)
    print(f"Prédiction: {prediction}")
    
    print("✅ Test terminé")
