# backend/strategic_response_service.py
"""
Service de recommandations stratégiques et storytelling avec GPT
Génère des réponses adaptées pour la communication territoriale
Uniquement si le phénomène touche directement la collectivité départementale
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import openai
from dotenv import load_dotenv
load_dotenv() 

logger = logging.getLogger(__name__)

class StrategicResponseService:
    """Service de recommandations stratégiques pour la communication territoriale"""
    
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY manquant - Service de recommandations désactivé")
            self.available = False
        else:
            openai.api_key = self.openai_api_key
            self.available = True
            logger.info("Service de recommandations stratégiques GPT activé")
        
        # Seuils pour déclencher les recommandations stratégiques
        self.intervention_thresholds = {
            "importance_minimum": 0.65,  # Seuls les sujets importants
            "themes_prioritaires": [
                "politique_institutions",
                "sante_social", 
                "infrastructure_transport",
                "securite_justice",
                "environnement_agriculture",
                "economie_emploi"
            ],
            "entities_strategiques": [
                "Guy Losbar", "CD971", "CHUG", "SMGEAG", 
                "Préfet", "Conseil Départemental"
            ]
        }
        
        # Contexte territorial spécifique Guadeloupe
        self.territorial_context = {
            "institution": "Conseil Départemental de la Guadeloupe (CD971)",
            "population": 400000,
            "statut": "Collectivité départementale d'outre-mer",
            "compétences_cd": [
                "Action sociale et solidarité",
                "Collèges et éducation", 
                "Routes départementales",
                "Développement économique",
                "Aménagement du territoire",
                "Environnement et cadre de vie"
            ],
            "contraintes_insulaires": [
                "Insularité et éloignement géographique",
                "Dépendance aux importations",
                "Vulnérabilité climatique (cyclones, sécheresse)",
                "Marché de l'emploi restreint",
                "Services publics sans alternative"
            ]
        }
    
    def should_generate_recommendations(self, article_data: Dict[str, Any]) -> bool:
        """Détermine si l'article nécessite des recommandations stratégiques"""
        if not self.available:
            return False
        
        # Critère 1: Importance suffisante
        importance = article_data.get("importance_score", 0)
        if importance < self.intervention_thresholds["importance_minimum"]:
            return False
        
        # Critère 2: Thème prioritaire pour le CD
        theme = article_data.get("theme_principal", "")
        if theme not in self.intervention_thresholds["themes_prioritaires"]:
            return False
        
        # Critère 3: Entité stratégique impliquée
        entity = article_data.get("primary_entity", "")
        entities_list = article_data.get("entites", [])
        
        strategic_entity_involved = (
            entity in self.intervention_thresholds["entities_strategiques"] or
            any(ent in self.intervention_thresholds["entities_strategiques"] 
                for ent in entities_list)
        )
        
        # Critère 4: Impact territorial élevé
        impact_territorial = article_data.get("impact_territorial", "low")
        territorial_impact = impact_territorial in ["high", "medium"]
        
        return strategic_entity_involved or territorial_impact
    
    def generate_strategic_response(self, article_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Génère des recommandations stratégiques pour un article donné"""
        if not self.should_generate_recommendations(article_data):
            logger.debug("Article ne nécessite pas de recommandations stratégiques")
            return None
        
        try:
            theme = article_data.get("theme_principal", "general")
            entity = article_data.get("primary_entity", "Aucune")
            sentiment = article_data.get("sentiment", {}).get("sentiment", "neutre")
            importance = article_data.get("importance_score", 0.5)
            title = article_data.get("title", "")
            content_preview = article_data.get("content", "")[:500]
            calibrage = article_data.get("calibrage_applique", "")
            
            # Prompt spécialisé pour recommandations stratégiques CD971
            prompt = f"""
            Tu es un conseiller en communication stratégique du Conseil Départemental de la Guadeloupe (CD971).
            
            CONTEXTE TERRITORIAL :
            - Population : 400 000 habitants
            - Collectivité départementale d'outre-mer insulaire
            - Compétences CD : action sociale, collèges, routes, développement économique
            - Contraintes : insularité, dépendance imports, vulnérabilité climatique
            
            ARTICLE À ANALYSER :
            - Titre : "{title}"
            - Thème : {theme}
            - Entité principale : {entity}
            - Impact/Sentiment : {sentiment}
            - Importance territoriale : {importance} ({calibrage})
            - Extrait : {content_preview}
            
            GÉNÈRE des recommandations stratégiques CONCRÈTES et ACTIONNABLES pour le CD971 :
            
            1. ANALYSE STRATÉGIQUE (en 2 phrases max) :
               - Enjeu principal pour la collectivité
               - Risques/opportunités identifiés
            
            2. RECOMMANDATIONS D'ACTION (3 actions maximum) :
               - Actions concrètes à mener par le CD971
               - Partenaires à mobiliser
               - Calendrier suggéré
            
            3. STORYTELLING/COMMUNICATION (2-3 angles) :
               - Messages clés à porter
               - Bénéfices pour la population à mettre en avant
               - Éléments de langage positifs
            
            EXEMPLE de réponse structurée :
            {{
                "analyse": "Le dysfonctionnement du CHU menace l'accès aux soins pour 400k habitants. Opportunité de renforcer le rôle du CD dans la coordination sanitaire.",
                "actions": [
                    "Mobiliser immédiatement les services du CD pour identifier les besoins sociaux urgents",
                    "Convoquer une réunion de crise avec ARS et Préfecture sous 48h",
                    "Activer le dispositif départemental d'aide aux familles en difficulté"
                ],
                "storytelling": [
                    "Le CD971 au côté des Guadeloupéens dans l'épreuve",
                    "Nos services sociaux mobilisés pour ne laisser personne au bord du chemin",
                    "La solidarité territoriale comme réponse à la crise"
                ],
                "urgence": "haute|moyenne|basse",
                "partenaires": ["ARS", "Préfecture", "Communes"],
                "budget_estime": "50k€ - 200k€"
            }}
            
            Réponds UNIQUEMENT en JSON structuré. Soit CONCRET et RÉALISTE.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "Tu es un expert en communication territoriale spécialisé dans les collectivités d'outre-mer. Tu donnes des conseils stratégiques concrets et réalistes."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.3
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parser la réponse JSON
            try:
                strategic_recommendations = json.loads(response_text)
                strategic_recommendations.update({
                    "generated_at": datetime.now().isoformat(),
                    "article_id": article_data.get("id", ""),
                    "importance_trigger": importance,
                    "theme_trigger": theme,
                    "model_used": "gpt-4o-mini"
                })
                
                logger.info(f"Recommandations stratégiques générées pour: {title[:50]}...")
                return strategic_recommendations
                
            except json.JSONDecodeError:
                logger.warning("Réponse GPT non-JSON, traitement en texte brut")
                return {
                    "analyse": "Analyse non structurée disponible",
                    "raw_response": response_text,
                    "generated_at": datetime.now().isoformat(),
                    "article_id": article_data.get("id", ""),
                    "model_used": "gpt-4o-mini"
                }
            
        except Exception as e:
            logger.error(f"Erreur génération recommandations stratégiques: {e}")
            return None
    
    def generate_bulk_recommendations(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Génère des recommandations pour plusieurs articles prioritaires"""
        if not self.available:
            return {"error": "Service indisponible"}
        
        high_priority_articles = [
            art for art in articles 
            if self.should_generate_recommendations(art)
        ]
        
        if not high_priority_articles:
            return {"message": "Aucun article ne nécessite de recommandations stratégiques"}
        
        recommendations_batch = {}
        
        for article in high_priority_articles[:5]:  # Limiter à 5 pour éviter coûts
            article_id = article.get("id", "unknown")
            recommendations = self.generate_strategic_response(article)
            
            if recommendations:
                recommendations_batch[article_id] = recommendations
        
        return {
            "total_articles_analyzed": len(articles),
            "high_priority_detected": len(high_priority_articles),
            "recommendations_generated": len(recommendations_batch),
            "recommendations": recommendations_batch,
            "generated_at": datetime.now().isoformat()
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Vérifie la santé du service"""
        return {
            "service_available": self.available,
            "openai_key_configured": bool(self.openai_api_key),
            "intervention_thresholds": self.intervention_thresholds,
            "territorial_context": self.territorial_context["institution"]
        }


# Instance globale
strategic_response_service = StrategicResponseService()

# Intégration dans ai_service.py
def enrich_with_strategic_recommendations(article_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit un article avec des recommandations stratégiques si nécessaire"""
    recommendations = strategic_response_service.generate_strategic_response(article_data)
    
    if recommendations:
        article_data["strategic_recommendations"] = recommendations
        logger.info(f"Recommandations stratégiques ajoutées pour: {article_data.get('title', '')[:50]}")
    
    return article_data