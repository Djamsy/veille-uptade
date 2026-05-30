# backend/gpt_sentiment_validation.py
"""
Module de validation et correction des analyses GPT
Corrige les erreurs factuelles en utilisant tags_index comme référence
"""

import logging
from typing import Dict, Any, List
from backend.tags_index import ELECTED_INDEX, infer_tags_and_theme

logger = logging.getLogger(__name__)

class GPTValidationService:
    """Service de validation des analyses GPT contre la base factuelle"""
    
    def __init__(self):
        self.elected_index = ELECTED_INDEX
        
    def validate_and_correct_gpt_analysis(self, gpt_result: Dict[str, Any], original_text: str) -> Dict[str, Any]:
        """
        Valide et corrige l'analyse GPT avec les données factuelles de tags_index
        """
        # Faire l'analyse tags_index en parallèle
        tags_analysis = infer_tags_and_theme({
            "title": original_text[:100],  # Utiliser début du texte comme titre
            "content": original_text
        })
        
        # Extraire les personnalités détectées par tags_index (source de vérité)
        factual_elected = tags_analysis.get("elected", [])
        factual_theme = tags_analysis.get("theme")
        
        # Corriger les personnalités dans l'analyse GPT
        corrected_result = gpt_result.copy()
        
        # 1. Corriger les personnalités mentionnées
        gpt_personalities = gpt_result.get("analysis_details", {}).get("personalities_mentioned", [])
        
        corrections_made = []
        validated_personalities = []
        
        for gpt_personality in gpt_personalities:
            # Vérifier si la personnalité existe dans notre base
            found_in_base = False
            correct_info = None
            
            for elected_name, info in self.elected_index.items():
                # Vérifier si le nom GPT correspond à un élu connu
                if (gpt_personality.lower() in elected_name.lower() or 
                    elected_name.lower() in gpt_personality.lower()):
                    found_in_base = True
                    correct_info = {
                        "name": elected_name,
                        "function": info["function"],
                        "verified": True
                    }
                    validated_personalities.append(correct_info)
                    break
            
            if not found_in_base:
                # Personnalité non trouvée dans la base = potentielle erreur
                corrections_made.append({
                    "type": "personality_not_found",
                    "gpt_claimed": gpt_personality,
                    "action": "removed_unverified_personality"
                })
        
        # Ajouter les personnalités détectées par tags_index que GPT a manquées
        for factual_person in factual_elected:
            if not any(p.get("name") == factual_person for p in validated_personalities):
                person_info = self.elected_index.get(factual_person, {})
                validated_personalities.append({
                    "name": factual_person,
                    "function": person_info.get("function", ""),
                    "verified": True,
                    "source": "tags_index_detection"
                })
                corrections_made.append({
                    "type": "personality_added",
                    "detected_by": "tags_index",
                    "name": factual_person
                })
        
        # 2. Corriger les institutions mentionnées
        corrected_institutions = []
        gpt_institutions = gpt_result.get("analysis_details", {}).get("institutions_mentioned", [])
        
        for institution in gpt_institutions:
            # Vérifier la cohérence avec les personnalités validées
            corrected_institution = self._validate_institution(institution, validated_personalities)
            corrected_institutions.append(corrected_institution)
        
        # 3. Mettre à jour le résultat avec les corrections
        if "analysis_details" not in corrected_result:
            corrected_result["analysis_details"] = {}
            
        corrected_result["analysis_details"]["personalities_mentioned"] = [p["name"] for p in validated_personalities]
        corrected_result["analysis_details"]["validated_personalities"] = validated_personalities
        corrected_result["analysis_details"]["institutions_mentioned"] = corrected_institutions
        
        # Ajouter les informations de validation
        corrected_result["validation"] = {
            "validated_by": "tags_index",
            "corrections_made": corrections_made,
            "factual_theme_detected": factual_theme,
            "validation_timestamp": "2025-09-11T13:00:00",
            "confidence_boost": len(factual_elected) > 0  # Plus de confiance si élus détectés
        }
        
        # Ajuster le score de confiance si des corrections ont été faites
        if corrections_made:
            original_confidence = corrected_result.get("analysis_details", {}).get("confidence", 0.8)
            # Réduire légèrement la confiance si corrections importantes
            confidence_penalty = len([c for c in corrections_made if c["type"] == "personality_not_found"]) * 0.1
            corrected_result["analysis_details"]["confidence"] = max(0.3, original_confidence - confidence_penalty)
        
        return corrected_result
    
    def _validate_institution(self, institution: str, validated_personalities: List[Dict]) -> str:
        """Valide et corrige les institutions en fonction des personnalités validées"""
        institution_lower = institution.lower()
        
        # Corrections communes d'institutions
        institution_corrections = {
            "mairie de pointe-à-pitre": "Conseil départemental de la Guadeloupe",  # Si Guy Losbar mentionné
            "préfecture": "Préfecture de la Guadeloupe",
            "conseil regional": "Conseil régional de la Guadeloupe",
            "conseil departemental": "Conseil départemental de la Guadeloupe"
        }
        
        # Vérifier la cohérence avec les personnalités
        for personality in validated_personalities:
            if "guy losbar" in personality.get("name", "").lower():
                if "mairie" in institution_lower and "pointe" in institution_lower:
                    return "Conseil départemental de la Guadeloupe"
            if "ary chalus" in personality.get("name", "").lower():
                if "conseil" in institution_lower and ("regional" in institution_lower or "régional" in institution_lower):
                    return "Conseil régional de la Guadeloupe"
        
        # Corrections générales
        for wrong, correct in institution_corrections.items():
            if wrong in institution_lower:
                return correct
                
        return institution
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Statistiques de validation"""
        return {
            "elected_in_database": len(self.elected_index),
            "validation_active": True,
            "last_updated": "2025-09-11",
            "data_source": "tags_index"
        }

# Instance globale
gpt_validator = GPTValidationService()

# Fonction utilitaire
def validate_gpt_sentiment_result(gpt_result: Dict[str, Any], original_text: str) -> Dict[str, Any]:
    """Fonction utilitaire pour valider un résultat GPT"""
    return gpt_validator.validate_and_correct_gpt_analysis(gpt_result, original_text)

if __name__ == "__main__":
    # Test de validation
    test_gpt_result = {
        "polarity": "positive",
        "score": 0.6,
        "analysis_details": {
            "personalities_mentioned": ["Guy Losbar"],  # ERREUR : dit qu'il est maire
            "institutions_mentioned": ["Mairie de Pointe-à-Pitre"],  # ERREUR
            "confidence": 0.8
        }
    }
    
    test_text = "Le maire de Pointe-à-Pitre annonce de nouvelles mesures pour lutter contre les coupures d'eau"
    
    corrected = validate_gpt_sentiment_result(test_gpt_result, test_text)
    print("=== VALIDATION GPT ===")
    print(f"Personnalités validées: {corrected['analysis_details']['validated_personalities']}")
    print(f"Corrections: {corrected['validation']['corrections_made']}")
    print(f"Confiance ajustée: {corrected['analysis_details']['confidence']}")
