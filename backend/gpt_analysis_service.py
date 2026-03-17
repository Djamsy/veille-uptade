"""
Service d'analyse intelligente des transcriptions radio avec GPT-4.1-mini
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import openai
from openai import OpenAI
from dotenv import load_dotenv

# Charger explicitement le fichier .env
load_dotenv()

logger = logging.getLogger(__name__)

class GPTAnalysisService:
    def __init__(self):
        self.client = None
        self._initialize_client()
        
        # Prompt journalistique spécialisé pour la Guadeloupe
        self.journalism_prompt = """Tu es un journaliste spécialisé en veille médiatique pour la Guadeloupe. À partir de cette transcription brute d'un journal radio, tu dois produire une veille synthétique en français clair, organisée par sujet.

**Ta mission :**
- Liste les **grands titres abordés**, sous forme de bullet points
- Pour chaque titre, ajoute une **courte description** en une ou deux phrases
- Ne reformule pas tout le journal. **Ne conserve que les informations principales.**
- Si le contenu est confus, indique "contenu inaudible ou ambigu"
- Structure ton retour comme un **bilan de veille quotidienne**
- Utilise des emojis appropriés pour les catégories (🏛️ Politique, 💼 Économie, 👥 Social, 🎭 Culture, 🌿 Environnement, 🏗️ Infrastructure)

Voici la transcription :"""

    def _initialize_client(self):
        """Initialiser le client OpenAI"""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            logger.info(f"🔑 Vérification clé API: {'trouvée' if api_key else 'MANQUANTE'}")
            
            if not api_key:
                logger.error("OPENAI_API_KEY non trouvée dans les variables d'environnement")
                logger.info(f"Variables d'environnement disponibles: {list(os.environ.keys())}")
                return
            
            # Masquer la clé dans les logs pour sécurité
            key_preview = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "clé_courte"
            logger.info(f"🔑 Utilisation clé API: {key_preview}")
            
            self.client = OpenAI(api_key=api_key)
            logger.info("✅ Client OpenAI initialisé avec succès")
            
        except Exception as e:
            logger.error(f"❌ Erreur initialisation OpenAI: {e}")
            self.client = None

    def analyze_transcription(self, transcription_text: str, stream_name: str = "") -> Dict[str, Any]:
        """Analyser une transcription avec GPT-4.1-mini"""
        try:
            if not self.client:
                return self._fallback_analysis(transcription_text, "Client OpenAI non disponible")
            
            if not transcription_text or len(transcription_text.strip()) < 10:
                return self._fallback_analysis(transcription_text, "Transcription trop courte")
            
            # Appel à GPT-4.1-mini
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # GPT-4.1-mini équivalent
                messages=[
                    {"role": "system", "content": "Tu es un journaliste expert en veille médiatique pour la Guadeloupe. Tu analyses les transcriptions radio pour produire des synthèses claires et structurées."},
                    {"role": "user", "content": f"{self.journalism_prompt}\n\n{transcription_text}"}
                ],
                max_tokens=800,
                temperature=0.3,  # Réponse plus cohérente
                timeout=30
            )
            
            gpt_analysis = response.choices[0].message.content.strip()
            
            # Extraction des métadonnées basiques
            analysis_metadata = self._extract_metadata(transcription_text, gpt_analysis, stream_name)
            
            return {
                'original_text': transcription_text,
                'gpt_analysis': gpt_analysis,
                'summary': gpt_analysis,  # Le résumé GPT est la synthèse complète
                'analysis_method': 'gpt-4o-mini',
                'analysis_metadata': analysis_metadata,
                'status': 'success',
                'processed_at': datetime.now().isoformat()
            }
            
        except openai.RateLimitError as e:
            logger.error(f"Limite de taux OpenAI atteinte: {e}")
            return self._fallback_analysis(transcription_text, "Limite de taux API atteinte")
            
        except openai.APITimeoutError as e:
            logger.error(f"Timeout OpenAI: {e}")
            return self._fallback_analysis(transcription_text, "Timeout API")
            
        except Exception as e:
            logger.error(f"Erreur analyse GPT: {e}")
            return self._fallback_analysis(transcription_text, f"Erreur GPT: {str(e)}")

    def _extract_metadata(self, original_text: str, gpt_analysis: str, stream_name: str) -> Dict[str, Any]:
        """Extraire les métadonnées d'analyse"""
        return {
            'original_length': len(original_text),
            'analysis_length': len(gpt_analysis),
            'compression_ratio': round(len(gpt_analysis) / max(len(original_text), 1), 2),
            'stream_source': stream_name,
            'word_count_original': len(original_text.split()),
            'word_count_analysis': len(gpt_analysis.split()),
            'processed_at': datetime.now().isoformat()
        }

    def _fallback_analysis(self, transcription_text: str, error_reason: str) -> Dict[str, Any]:
        """Analyse de fallback en cas d'erreur GPT"""
        logger.warning(f"Utilisation du fallback d'analyse: {error_reason}")
        
        # Analyse basique locale
        basic_summary = self._create_basic_summary(transcription_text)
        
        return {
            'original_text': transcription_text,
            'summary': basic_summary,
            'analysis_method': 'fallback_local',
            'error_reason': error_reason,
            'status': 'fallback',
            'processed_at': datetime.now().isoformat(),
            'analysis_metadata': {
                'original_length': len(transcription_text),
                'processed_locally': True,
                'fallback_reason': error_reason
            }
        }

    def _create_basic_summary(self, text: str) -> str:
        """Créer un résumé basique local"""
        if not text or len(text.strip()) < 10:
            return "📻 Transcription radio - contenu insuffisant pour analyse"
        
        # Nettoyer le texte
        clean_text = text.strip()
        words = clean_text.split()
        
        if len(words) <= 30:
            return f"📻 Transcription courte: {clean_text}"
        
        # Prendre les premières phrases significatives
        sentences = clean_text.split('.')
        summary_sentences = []
        
        for sentence in sentences[:3]:
            sentence = sentence.strip()
            if len(sentence) > 10:  # Ignorer les phrases trop courtes
                summary_sentences.append(sentence)
        
        if summary_sentences:
            summary = '. '.join(summary_sentences) + '.'
            return f"📻 Journal radio: {summary}"
        else:
            # Fallback ultime
            return f"📻 Transcription radio ({len(words)} mots): {' '.join(words[:50])}..."

    def test_connection(self) -> Dict[str, Any]:
        """Tester la connexion à l'API OpenAI"""
        try:
            if not self.client:
                return {'status': 'error', 'message': 'Client OpenAI non initialisé'}
            
            # Test simple avec GPT
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Réponds simplement 'Test OK'"}],
                max_tokens=10,
                timeout=10
            )
            
            return {
                'status': 'success',
                'message': 'Connexion OpenAI opérationnelle',
                'model': 'gpt-4o-mini',
                'response': response.choices[0].message.content.strip()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Erreur test OpenAI: {str(e)}'
            }

    def predict_reaction(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Prédit la réaction du public guadeloupéen à un texte.
        Retourne un dict avec les clés:
        - overall_reaction: "favorable" | "mitigé" | "tendu"
        - risk_level: "low" | "medium" | "high"
        - likely_discussion_channels: [str, ...]
        - confidence: float 0..1
        - reasoning: str
        """
        try:
            if not text or len(text.strip()) < 5:
                return {
                    "overall_reaction": "mitigé",
                    "risk_level": "medium",
                    "likely_discussion_channels": ["Facebook", "X/Twitter"],
                    "confidence": 0.5,
                    "reasoning": "Texte trop court pour une analyse fiable."
                }

            if not self.client:
                # Heuristique locale si pas de client OpenAI
                tokens = text.lower().split()
                pos = sum(w in {"bien","positif","succès","bonne","approuvé","excellent"} for w in tokens)
                neg = sum(w in {"scandale","crise","tendu","grave","échec","colère"} for w in tokens)
                if pos > neg:
                    return {"overall_reaction":"favorable","risk_level":"low","likely_discussion_channels":["Facebook","X/Twitter"],"confidence":0.6,"reasoning":"Heuristique locale (pas d'API OpenAI)"}
                elif neg > pos:
                    return {"overall_reaction":"tendu","risk_level":"high","likely_discussion_channels":["Facebook","X/Twitter"],"confidence":0.65,"reasoning":"Heuristique locale (pas d'API OpenAI)"}
                else:
                    return {"overall_reaction":"mitigé","risk_level":"medium","likely_discussion_channels":["Facebook","X/Twitter"],"confidence":0.55,"reasoning":"Heuristique locale (pas d'API OpenAI)"}

            system = (
                "Tu es un analyste d'opinion publique en Guadeloupe. "
                "Rends STRICTEMENT un JSON avec les clés: "
                "overall_reaction (favorable|mitigé|tendu), "
                "risk_level (low|medium|high), "
                'likely_discussion_channels (liste courte de chaînes, ex: ["Facebook","X/Twitter"]), '
                "confidence (0..1), reasoning (phrase courte)."
            )
            user = (
                f"Texte à évaluer:\n{text}\n\n"
                f"Contexte: {context or {}}"
            )

            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
                temperature=0.2,
                max_tokens=250,
                timeout=30
            )
            raw = (resp.choices[0].message.content or "").strip()

            import json
            try:
                data = json.loads(raw)
            except Exception:
                # Si le modèle ne renvoie pas un JSON strict, on fournit un repli propre
                data = {
                    "overall_reaction": "mitigé",
                    "risk_level": "medium",
                    "likely_discussion_channels": ["Facebook","X/Twitter"],
                    "confidence": 0.6,
                    "reasoning": "Sortie non-JSON, valeurs par défaut."
                }

            # Normalisation
            return {
                "overall_reaction": data.get("overall_reaction", "mitigé"),
                "risk_level": data.get("risk_level", "medium"),
                "likely_discussion_channels": data.get("likely_discussion_channels", ["Facebook","X/Twitter"]),
                "confidence": float(data.get("confidence", 0.6)),
                "reasoning": data.get("reasoning", "Analyse générée.")
            }
        except Exception as e:
            logger.exception("Erreur predict_reaction")
            return {
                "overall_reaction": "mitigé",
                "risk_level": "medium",
                "likely_discussion_channels": ["Facebook","X/Twitter"],
                "confidence": 0.5,
                "reasoning": f"Fallback suite à erreur: {str(e)[:120]}"
            }

# Instance globale du service GPT
gpt_analyzer = GPTAnalysisService()

def analyze_transcription_with_gpt(text: str, stream_name: str = "") -> Dict[str, Any]:
    """Fonction utilitaire pour analyser une transcription avec GPT"""
    return gpt_analyzer.analyze_transcription(text, stream_name)

def test_gpt_connection() -> Dict[str, Any]:
    """Fonction utilitaire pour tester la connexion GPT"""
    return gpt_analyzer.test_connection()