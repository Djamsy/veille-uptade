# backend/advanced_transcription_classifier.py
"""
Classification avancée des transcriptions radio/TV pour la Guadeloupe
- Détection d'affaires vs info de routine
- Calcul du bruit médiatique et viralité potentielle
- Classification fine des enjeux politico-institutionnels
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ClassificationResult:
    """Résultat de classification d'une transcription"""
    is_affair: bool
    affair_type: str
    gravity_score: float
    media_noise_level: str
    virality_potential: float
    institutional_risk: str
    key_actors: List[str]
    predicted_evolution: str
    confidence: float

class AdvancedTranscriptionClassifier:
    """
    Classificateur avancé pour transcriptions de médias locaux guadeloupéens
    """
    
    def __init__(self):
        # Indicateurs d'affaires (scandale/crise/polémique)
        self.affair_indicators = {
            'corruption_finance': {
                'keywords': ['détournement', 'corruption', 'malversation', 'enrichissement', 'favoritisme', 
                           'marché public', 'surfacturation', 'faux', 'usage de faux', 'abus de biens'],
                'weight': 0.9,
                'gravity_multiplier': 1.5
            },
            'justice_enquete': {
                'keywords': ['enquête', 'perquisition', 'mise en examen', 'garde à vue', 'procureur', 
                           'plainte', 'dépôt de plainte', 'saisine', 'tribunal', 'condamnation'],
                'weight': 0.8,
                'gravity_multiplier': 1.3
            },
            'crise_institutionnelle': {
                'keywords': ['démission', 'motion de censure', 'dissolution', 'crise', 'conflit', 
                           'blocage institutionnel', 'majorité', 'opposition', 'vote de défiance'],
                'weight': 0.7,
                'gravity_multiplier': 1.2
            },
            'scandale_mediatique': {
                'keywords': ['révélations', 'document exclusif', 'témoignage choc', 'accusation', 
                           'polémique', 'controverse', 'indignation', 'scandale'],
                'weight': 0.6,
                'gravity_multiplier': 1.1
            }
        }
        
        # Acteurs institutionnels guadeloupéens (impact élevé si impliqués)
        self.key_actors = {
            'president_cd971': {
                'names': ['guy losbar', 'losbar'],
                'impact_score': 1.0,
                'institution': 'Conseil Départemental'
            },
            'president_region': {
                'names': ['ary chalus', 'chalus'],
                'impact_score': 1.0,
                'institution': 'Région Guadeloupe'
            },
            'prefet': {
                'names': ['préfet', 'alexandre rochatte', 'rochatte'],
                'impact_score': 0.9,
                'institution': 'État'
            },
            'maires_importants': {
                'names': ['maire pointe-à-pitre', 'maire basse-terre', 'maire les abymes', 
                         'maire baie-mahault', 'maire gosier'],
                'impact_score': 0.7,
                'institution': 'Communes'
            }
        }
        
        # Thématiques sensibles (impact territorial fort)
        self.sensitive_themes = {
            'eau_publique': {
                'keywords': ['smgeag', 'coupure eau', 'distribution eau', 'eau potable', 'pénurie'],
                'population_impact': 0.9,
                'urgency_factor': 1.4
            },
            'transport_mobilite': {
                'keywords': ['transport', 'circulation', 'route fermée', 'pont gabarre', 'embouteillage'],
                'population_impact': 0.8,
                'urgency_factor': 1.2
            },
            'sante_urgence': {
                'keywords': ['chu', 'urgence', 'grève soignants', 'fermeture service', 'évacuation sanitaire'],
                'population_impact': 0.9,
                'urgency_factor': 1.5
            },
            'education_crise': {
                'keywords': ['grève enseignants', 'fermeture école', 'violence scolaire', 'occupation'],
                'population_impact': 0.7,
                'urgency_factor': 1.1
            }
        }
        
        # Indicateurs de viralité (prédiction engagement social)
        self.virality_factors = {
            'emotion_forte': {
                'patterns': [r'\b(scandaleux|révoltant|inacceptable|honteux|inadmissible)\b',
                           r'\b(colère|indignation|ras-le-bol|trop c\'est trop)\b'],
                'multiplier': 1.5
            },
            'impact_quotidien': {
                'patterns': [r'\b(tous les jours|quotidien|chaque matin|en permanence)\b',
                           r'\b(familles|parents|citoyens|usagers|habitants)\b'],
                'multiplier': 1.3
            },
            'injustice_perçue': {
                'patterns': [r'\b(pas normal|injuste|deux poids deux mesures|privilèges)\b',
                           r'\b(pendant ce temps|alors que|tandis que)\b'],
                'multiplier': 1.4
            }
        }
    
    def classify_transcription(self, text: str, metadata: Dict = None) -> ClassificationResult:
        """
        Classification complète d'une transcription
        """
        if not text or len(text.strip()) < 50:
            return self._default_classification()
        
        clean_text = text.lower().strip()
        
        # 1. Détection d'affaire
        is_affair, affair_type, gravity_score = self._detect_affair(clean_text)
        
        # 2. Identification des acteurs clés
        key_actors = self._identify_key_actors(clean_text)
        
        # 3. Calcul du bruit médiatique
        media_noise_level = self._calculate_media_noise(clean_text, key_actors)
        
        # 4. Potentiel de viralité
        virality_potential = self._calculate_virality_potential(clean_text)
        
        # 5. Risque institutionnel
        institutional_risk = self._assess_institutional_risk(clean_text, key_actors, gravity_score)
        
        # 6. Prédiction d'évolution
        predicted_evolution = self._predict_evolution(affair_type, gravity_score, key_actors)
        
        # 7. Score de confiance global
        confidence = self._calculate_confidence(text, key_actors, affair_type)
        
        return ClassificationResult(
            is_affair=is_affair,
            affair_type=affair_type,
            gravity_score=round(gravity_score, 3),
            media_noise_level=media_noise_level,
            virality_potential=round(virality_potential, 3),
            institutional_risk=institutional_risk,
            key_actors=key_actors,
            predicted_evolution=predicted_evolution,
            confidence=round(confidence, 3)
        )
    
    def _detect_affair(self, text: str) -> Tuple[bool, str, float]:
        """
        Détecter si c'est une affaire et son type
        """
        max_score = 0.0
        detected_type = "info_routine"
        
        for affair_type, config in self.affair_indicators.items():
            score = 0.0
            matches = 0
            
            for keyword in config['keywords']:
                if keyword in text:
                    matches += 1
                    # Score pondéré par la longueur du mot-clé (plus précis = plus fort)
                    word_weight = max(1.0, len(keyword.split()) * 0.5)
                    score += config['weight'] * word_weight
            
            # Bonus si plusieurs indicateurs du même type
            if matches > 1:
                score *= (1 + matches * 0.2)
            
            # Application du multiplicateur de gravité
            score *= config['gravity_multiplier']
            
            if score > max_score:
                max_score = score
                detected_type = affair_type
        
        # Seuil pour considérer que c'est une affaire
        is_affair = max_score >= 0.6
        
        return is_affair, detected_type, min(max_score, 1.0)
    
    def _identify_key_actors(self, text: str) -> List[str]:
        """
        Identifier les acteurs clés mentionnés
        """
        identified = []
        
        for actor_key, config in self.key_actors.items():
            for name in config['names']:
                if name in text:
                    identified.append({
                        'name': name.title(),
                        'role': actor_key,
                        'institution': config['institution'],
                        'impact_score': config['impact_score']
                    })
        
        # Trier par impact décroissant
        identified.sort(key=lambda x: x['impact_score'], reverse=True)
        
        return identified[:5]  # Top 5 acteurs
    
    def _calculate_media_noise(self, text: str, actors: List[Dict]) -> str:
        """
        Calculer le niveau de bruit médiatique
        """
        noise_score = 0.0
        
        # Base : longueur du contenu
        if len(text) > 1000:
            noise_score += 0.3
        elif len(text) > 500:
            noise_score += 0.2
        
        # Acteurs impliqués (plus l'acteur est important, plus le bruit)
        for actor in actors:
            noise_score += actor.get('impact_score', 0) * 0.4
        
        # Thématiques sensibles
        for theme, config in self.sensitive_themes.items():
            if any(kw in text for kw in config['keywords']):
                noise_score += config['population_impact'] * 0.3
        
        # Classification du niveau
        if noise_score >= 0.8:
            return "très_élevé"
        elif noise_score >= 0.6:
            return "élevé"
        elif noise_score >= 0.4:
            return "modéré"
        elif noise_score >= 0.2:
            return "faible"
        else:
            return "minimal"
    
    def _calculate_virality_potential(self, text: str) -> float:
        """
        Calculer le potentiel de viralité
        """
        virality_score = 0.3  # Score de base
        
        for factor_type, config in self.virality_factors.items():
            for pattern in config['patterns']:
                if re.search(pattern, text, re.IGNORECASE):
                    virality_score *= config['multiplier']
                    break  # Un seul match par facteur
        
        # Bonus si mots émotionnels forts
        emotion_words = ['scandaleux', 'révoltant', 'inacceptable', 'honteux', 'inadmissible']
        emotion_matches = sum(1 for word in emotion_words if word in text)
        if emotion_matches > 0:
            virality_score += emotion_matches * 0.1
        
        return min(virality_score, 1.0)
    
    def _assess_institutional_risk(self, text: str, actors: List[Dict], gravity_score: float) -> str:
        """
        Évaluer le risque institutionnel
        """
        risk_score = gravity_score * 0.5  # Base sur la gravité
        
        # Impact selon les acteurs impliqués
        for actor in actors:
            if actor.get('impact_score', 0) >= 0.9:  # Président CD971, Région
                risk_score += 0.4
            elif actor.get('impact_score', 0) >= 0.7:  # Préfet, gros maires
                risk_score += 0.3
        
        # Mots-clés de risque institutionnel
        risk_keywords = ['confiance', 'légitimité', 'démission', 'crise', 'gouvernance']
        risk_matches = sum(1 for kw in risk_keywords if kw in text)
        risk_score += risk_matches * 0.1
        
        # Classification du risque
        if risk_score >= 0.8:
            return "critique"
        elif risk_score >= 0.6:
            return "élevé"
        elif risk_score >= 0.4:
            return "modéré"
        elif risk_score >= 0.2:
            return "faible"
        else:
            return "minimal"
    
    def _predict_evolution(self, affair_type: str, gravity_score: float, actors: List[Dict]) -> str:
        """
        Prédire l'évolution probable de l'affaire
        """
        if affair_type == "info_routine":
            return "stabilisation_24h"
        
        # Selon le type d'affaire
        if affair_type == "corruption_finance" and gravity_score > 0.7:
            return "escalade_judiciaire_48h"
        elif affair_type == "justice_enquete":
            return "procédure_longue_suivi_requis"
        elif affair_type == "crise_institutionnelle":
            return "polarisation_politique_72h"
        elif affair_type == "scandale_mediatique":
            return "pic_médiatique_24h_puis_déclin"
        
        # Selon les acteurs impliqués
        high_profile_actors = [a for a in actors if a.get('impact_score', 0) >= 0.9]
        if high_profile_actors:
            return "communication_institutionnelle_urgente"
        
        return "surveillance_standard"
    
    def _calculate_confidence(self, text: str, actors: List[Dict], affair_type: str) -> float:
        """
        Calculer le score de confiance de la classification
        """
        confidence = 0.5  # Base
        
        # Longueur du texte (plus c'est long, plus on a d'info)
        text_length_factor = min(len(text) / 1000, 1.0) * 0.3
        confidence += text_length_factor
        
        # Acteurs identifiés (plus on identifie d'acteurs, plus c'est fiable)
        actor_factor = min(len(actors) / 3, 1.0) * 0.2
        confidence += actor_factor
        
        # Type d'affaire détecté (certains types sont plus faciles à détecter)
        if affair_type in ["corruption_finance", "justice_enquete"]:
            confidence += 0.15
        elif affair_type != "info_routine":
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _default_classification(self) -> ClassificationResult:
        """Classification par défaut pour contenus insuffisants"""
        return ClassificationResult(
            is_affair=False,
            affair_type="info_routine",
            gravity_score=0.0,
            media_noise_level="minimal",
            virality_potential=0.1,
            institutional_risk="minimal",
            key_actors=[],
            predicted_evolution="aucun_suivi_requis",
            confidence=0.2
        )

# Service global
advanced_classifier = AdvancedTranscriptionClassifier()

def classify_transcription_advanced(text: str, metadata: Dict = None) -> Dict[str, Any]:
    """
    Function utilitaire pour classification avancée
    """
    result = advanced_classifier.classify_transcription(text, metadata)
    
    return {
        'classification': {
            'is_affair': result.is_affair,
            'affair_type': result.affair_type,
            'gravity_score': result.gravity_score,
            'media_noise_level': result.media_noise_level,
            'virality_potential': result.virality_potential,
            'institutional_risk': result.institutional_risk,
        },
        'analysis': {
            'key_actors': result.key_actors,
            'predicted_evolution': result.predicted_evolution,
            'confidence': result.confidence,
        },
        'recommendations': _generate_recommendations(result),
        'metadata': {
            'classified_at': datetime.now().isoformat(),
            'classifier_version': '1.0',
            'analysis_method': 'advanced_local_classifier'
        }
    }

def _generate_recommendations(result: ClassificationResult) -> List[str]:
    """
    Générer des recommandations stratégiques
    """
    recs = []
    
    if result.is_affair and result.gravity_score > 0.7:
        recs.append("Surveillance médiatique renforcée recommandée")
        recs.append("Préparation éléments de communication institutionnelle")
    
    if result.institutional_risk in ["critique", "élevé"]:
        recs.append("Alerter la communication de crise")
        recs.append("Anticiper questions presse et réseaux sociaux")
    
    if result.virality_potential > 0.7:
        recs.append("Monitoring réseaux sociaux activé")
        recs.append("Préparer réponse rapide si nécessaire")
    
    if result.predicted_evolution == "escalade_judiciaire_48h":
        recs.append("Point situation juridique recommandé")
    
    return recs if recs else ["Suivi standard suffisant"]