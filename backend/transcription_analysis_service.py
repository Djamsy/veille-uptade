"""
Service d'analyse intelligente des transcriptions radio
"""
import re
from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TranscriptionAnalysisService:
    def __init__(self):
        # Mots-clés importants pour la Guadeloupe
        self.important_keywords = {
            'politique': ['conseil départemental', 'cd971', 'guy losbar', 'ary chalus', 'région guadeloupe', 'préfet', 'maire', 'élections'],
            'économie': ['emploi', 'chômage', 'entreprise', 'économique', 'développement', 'investissement', 'tourisme'],
            'social': ['santé', 'éducation', 'logement', 'transport', 'sécurité', 'violence', 'manifestation'],
            'culture': ['carnaval', 'festival', 'culture', 'musique', 'gwoka', 'créole', 'patrimoine'],
            'environnement': ['cyclone', 'ouragan', 'sargasses', 'environnement', 'pollution', 'nature'],
            'infrastructure': ['routes', 'pont', 'aéroport', 'port', 'eau', 'électricité', 'internet']
        }
        
        # Expressions à nettoyer/ignorer  
        self.noise_patterns = [
            r'\b(euh+|heu+|ben|alors|donc|voilà|quoi|hein)\b',
            r'\b(et puis|et donc|et alors|et ben)\b',
            r'\b(tu vois|vous savez|vous comprenez)\b',
            r'\b(c\'est-à-dire|en fait|en réalité)\b'
        ]
        
        # Connecteurs logiques importants à préserver
        self.important_connectors = [
            'cependant', 'néanmoins', 'toutefois', 'mais', 'pourtant',
            'par conséquent', 'donc', 'ainsi', 'en effet', 'car',
            'parce que', 'puisque', 'étant donné', 'vu que'
        ]

    def analyze_transcription(self, transcription_text: str, stream_name: str = "") -> Dict[str, Any]:
        """Analyser et résumer intelligemment une transcription"""
        try:
            # 1. Nettoyage initial
            clean_text = self._clean_transcription(transcription_text)
            
            # 2. Extraction des phrases importantes
            key_sentences = self._extract_key_sentences(clean_text)
            
            # 3. Identification des sujets principaux
            main_topics = self._identify_topics(clean_text)
            
            # 4. Création du résumé
            summary = self._create_summary(key_sentences, main_topics)
            
            # 5. Extraction des mots-clés
            keywords = self._extract_keywords(clean_text)
            
            # 6. Score de pertinence
            relevance_score = self._calculate_relevance(clean_text, main_topics)
            
            return {
                'original_text': transcription_text,
                'clean_text': clean_text,
                'summary': summary,
                'key_sentences': key_sentences[:3],  # Top 3 phrases
                'main_topics': main_topics,
                'keywords': keywords,
                'relevance_score': relevance_score,
                'analysis_metadata': {
                    'original_length': len(transcription_text),
                    'clean_length': len(clean_text),
                    'compression_ratio': round(len(summary) / max(len(transcription_text), 1), 2),
                    'analyzed_at': datetime.now().isoformat(),
                    'stream_source': stream_name
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse transcription: {e}")
            return {
                'original_text': transcription_text,
                'summary': transcription_text,  # Fallback vers texte original
                'error': str(e)
            }

    def _clean_transcription(self, text: str) -> str:
        """Nettoyer la transcription des bruits et répétitions"""
        clean = text.lower().strip()
        
        # Supprimer les bruits de parole
        for pattern in self.noise_patterns:
            clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
        
        # Nettoyer les espaces multiples
        clean = re.sub(r'\s+', ' ', clean)
        
        # Supprimer les répétitions de mots consécutifs
        words = clean.split()
        deduplicated = []
        for i, word in enumerate(words):
            if i == 0 or word != words[i-1]:
                deduplicated.append(word)
        
        return ' '.join(deduplicated).strip()

    def _extract_key_sentences(self, text: str) -> List[str]:
        """Extraire les phrases les plus importantes"""
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
        
        # Scorer chaque phrase
        scored_sentences = []
        for sentence in sentences:
            score = 0
            
            # Points pour les mots-clés importants
            for category, keywords in self.important_keywords.items():
                for keyword in keywords:
                    if keyword in sentence.lower():
                        score += 3
            
            # Points pour la longueur (ni trop courte, ni trop longue)
            length = len(sentence.split())
            if 8 <= length <= 25:
                score += 2
            
            # Points pour les connecteurs logiques
            for connector in self.important_connectors:
                if connector in sentence.lower():
                    score += 1
            
            scored_sentences.append((sentence, score))
        
        # Trier par score et retourner les meilleures
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored_sentences[:5]]

    def _identify_topics(self, text: str) -> List[Dict[str, Any]]:
        """Identifier les sujets principaux abordés"""
        topics = []
        
        for category, keywords in self.important_keywords.items():
            matches = []
            score = 0
            
            for keyword in keywords:
                if keyword in text.lower():
                    matches.append(keyword)
                    # Score plus élevé pour des mots-clés plus spécifiques
                    score += len(keyword.split())
            
            if matches:
                topics.append({
                    'category': category,
                    'keywords_found': matches,
                    'relevance_score': score,
                    'confidence': min(score / 10, 1.0)  # Normaliser entre 0 et 1
                })
        
        # Trier par pertinence
        topics.sort(key=lambda x: x['relevance_score'], reverse=True)
        return topics[:3]  # Top 3 sujets

    def _create_summary(self, key_sentences: List[str], main_topics: List[Dict]) -> str:
        """Créer un résumé intelligent"""
        if not key_sentences:
            return "Transcription non analysable - contenu insuffisant"
        
        # Commencer par identifier le contexte
        topic_context = ""
        if main_topics:
            top_topic = main_topics[0]
            if top_topic['category'] == 'politique':
                topic_context = "🏛️ Politique: "
            elif top_topic['category'] == 'économie':
                topic_context = "💼 Économie: "
            elif top_topic['category'] == 'social':
                topic_context = "👥 Social: "
            elif top_topic['category'] == 'culture':
                topic_context = "🎭 Culture: "
            elif top_topic['category'] == 'environnement':
                topic_context = "🌿 Environnement: "
            elif top_topic['category'] == 'infrastructure':
                topic_context = "🏗️ Infrastructure: "
        
        # Construire le résumé
        if len(key_sentences) == 1:
            summary = key_sentences[0]
        elif len(key_sentences) >= 2:
            # Combiner les 2 meilleures phrases intelligemment
            first = key_sentences[0].strip()
            second = key_sentences[1].strip()
            
            # Ajouter un connecteur si nécessaire
            if not any(conn in first.lower() for conn in self.important_connectors):
                summary = f"{first}. Par ailleurs, {second.lower()}"
            else:
                summary = f"{first}. {second}"
        
        # Limiter la longueur et ajouter le contexte
        summary = summary[:300] + "..." if len(summary) > 300 else summary
        return f"{topic_context}{summary}"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extraire les mots-clés pertinents"""
        keywords = []
        
        for category, keyword_list in self.important_keywords.items():
            for keyword in keyword_list:
                if keyword in text.lower():
                    keywords.append(keyword)
        
        # Supprimer les doublons et trier par longueur (plus spécifique d'abord)
        keywords = list(set(keywords))
        keywords.sort(key=len, reverse=True)
        
        return keywords[:8]  # Top 8 mots-clés

    def _calculate_relevance(self, text: str, topics: List[Dict]) -> float:
        """Calculer un score de pertinence global"""
        if not text.strip():
            return 0.0
        
        base_score = 0.3  # Score de base pour toute transcription
        
        # Bonus pour la longueur appropriée
        word_count = len(text.split())
        if 20 <= word_count <= 200:
            base_score += 0.2
        elif word_count > 10:
            base_score += 0.1
        
        # Bonus pour les sujets identifiés
        if topics:
            topic_bonus = sum(t['confidence'] for t in topics) / len(topics)
            base_score += topic_bonus * 0.5
        
        return min(base_score, 1.0)

# Instance globale du service
transcription_analyzer = TranscriptionAnalysisService()

def analyze_transcription(text: str, stream_name: str = "") -> Dict[str, Any]:
    """Fonction utilitaire pour analyser une transcription"""
    return transcription_analyzer.analyze_transcription(text, stream_name)