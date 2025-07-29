"""
Service de résumé automatique gratuit
Utilise spaCy et des techniques extractives pour résumer les contenus
"""
import spacy
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer
from sumy.summarizers.lex_rank import LexRankSummarizer
import re
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FreeSummaryService:
    def __init__(self):
        # Charger le modèle spaCy français
        try:
            self.nlp = spacy.load("fr_core_news_sm")
            logger.info("✅ Modèle spaCy français chargé")
        except OSError:
            logger.warning("⚠️ Modèle spaCy français non trouvé, installation...")
            try:
                import subprocess
                subprocess.run(["python", "-m", "spacy", "download", "fr_core_news_sm"], check=True)
                self.nlp = spacy.load("fr_core_news_sm")
                logger.info("✅ Modèle spaCy français installé et chargé")
            except Exception as e:
                logger.error(f"❌ Impossible de charger spaCy: {e}")
                self.nlp = None
        
        # Initialiser les summarizers
        self.textrank_summarizer = TextRankSummarizer()
        self.lexrank_summarizer = LexRankSummarizer()

    def extract_key_sentences(self, text: str, max_sentences: int = 3) -> List[str]:
        """Extraire les phrases clés d'un texte avec spaCy"""
        if not self.nlp or not text.strip():
            return []
        
        try:
            # Traitement du texte
            doc = self.nlp(text)
            
            # Extraire les phrases
            sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.strip()) > 20]
            
            if len(sentences) <= max_sentences:
                return sentences
            
            # Scoring basé sur les entités nommées et les mots-clés
            sentence_scores = {}
            
            for i, sentence in enumerate(sentences):
                score = 0
                sent_doc = self.nlp(sentence)
                
                # Points pour les entités nommées
                score += len(sent_doc.ents) * 2
                
                # Points pour les mots importants
                important_pos = ['NOUN', 'PROPN', 'ADJ']
                score += sum(1 for token in sent_doc if token.pos_ in important_pos)
                
                # Bonus si en début de texte
                if i < len(sentences) * 0.3:
                    score += 2
                
                sentence_scores[sentence] = score
            
            # Retourner les meilleures phrases
            top_sentences = sorted(sentence_scores.items(), key=lambda x: x[1], reverse=True)
            return [sent[0] for sent in top_sentences[:max_sentences]]
            
        except Exception as e:
            logger.error(f"Erreur extraction phrases clés: {e}")
            return []

    def summarize_with_textrank(self, text: str, sentence_count: int = 2) -> str:
        """Résumer avec TextRank"""
        try:
            parser = PlaintextParser.from_string(text, Tokenizer("french"))
            summary = self.textrank_summarizer(parser.document, sentence_count)
            
            return " ".join([str(sentence) for sentence in summary])
        except Exception as e:
            logger.error(f"Erreur TextRank: {e}")
            return ""

    def summarize_with_lexrank(self, text: str, sentence_count: int = 2) -> str:
        """Résumer avec LexRank"""
        try:
            parser = PlaintextParser.from_string(text, Tokenizer("french"))
            summary = self.lexrank_summarizer(parser.document, sentence_count)
            
            return " ".join([str(sentence) for sentence in summary])
        except Exception as e:
            logger.error(f"Erreur LexRank: {e}")
            return ""

    def extract_title_from_text(self, text: str) -> str:
        """Extraire un titre potentiel du texte"""
        if not text.strip():
            return "Information"
        
        # Prendre la première phrase courte ou le début
        sentences = text.split('.')
        
        for sentence in sentences[:3]:
            sentence = sentence.strip()
            if 10 <= len(sentence) <= 80:
                return sentence
        
        # Fallback: premiers mots
        words = text.split()
        if len(words) > 8:
            return " ".join(words[:8]) + "..."
        else:
            return " ".join(words)

    def create_formatted_summary(self, text: str, max_points: int = 5) -> str:
        """Créer un résumé formaté en HTML"""
        if not text.strip():
            return "<p>Aucun contenu à résumer.</p>"
        
        try:
            # Méthode 1: Extraction de phrases clés
            key_sentences = self.extract_key_sentences(text, max_points)
            
            # Méthode 2: TextRank comme backup
            if not key_sentences:
                textrank_summary = self.summarize_with_textrank(text, max_points)
                if textrank_summary:
                    key_sentences = textrank_summary.split('. ')
            
            # Méthode 3: Fallback simple
            if not key_sentences:
                sentences = text.split('.')
                key_sentences = [s.strip() for s in sentences[:max_points] if s.strip() and len(s.strip()) > 20]
            
            # Formater en HTML
            formatted_points = []
            
            for sentence in key_sentences:
                sentence = sentence.strip().rstrip('.')
                if not sentence:
                    continue
                
                # Extraire un titre de la phrase
                title = self.extract_title_from_text(sentence)
                
                # Créer une courte explication
                explanation = sentence
                if len(explanation) > 150:
                    explanation = explanation[:147] + "..."
                
                # Format HTML demandé
                formatted_point = f"<strong>{title}</strong><br>{explanation}"
                formatted_points.append(formatted_point)
            
            if formatted_points:
                return "<br><br>".join(formatted_points)
            else:
                return f"<strong>Information</strong><br>{text[:200]}{'...' if len(text) > 200 else ''}"
                
        except Exception as e:
            logger.error(f"Erreur création résumé formaté: {e}")
            return f"<strong>Information</strong><br>{text[:200]}{'...' if len(text) > 200 else ''}"

    def summarize_articles(self, articles: List[Dict[str, Any]]) -> str:
        """Résumer une liste d'articles"""
        if not articles:
            return "<p>Aucun article à résumer.</p>"
        
        summaries = []
        
        for article in articles[:10]:  # Limiter à 10 articles
            title = article.get('title', 'Article')
            url = article.get('url', '#')
            source = article.get('source', 'Source inconnue')
            
            # Créer un lien cliquable
            summary_point = f'<strong><a href="{url}" target="_blank">{title}</a></strong><br>Source: {source}'
            summaries.append(summary_point)
        
        return "<br><br>".join(summaries)

    def summarize_transcriptions(self, transcriptions: List[Dict[str, Any]]) -> str:
        """Résumer les transcriptions radio"""
        if not transcriptions:
            return "<p>Aucune transcription à résumer.</p>"
        
        all_summaries = []
        
        for transcription in transcriptions:
            stream_name = transcription.get('stream_name', 'Radio')
            text = transcription.get('transcription_text', '')
            timestamp = transcription.get('captured_at', '')
            
            if text and len(text.strip()) > 50:
                # Résumer le contenu de la transcription
                content_summary = self.create_formatted_summary(text, 3)
                
                # Ajouter le header
                header = f"<strong>📻 {stream_name}</strong> - {timestamp[:16] if timestamp else ''}"
                full_summary = f"{header}<br>{content_summary}"
                
                all_summaries.append(full_summary)
        
        return "<br><br><hr><br>".join(all_summaries) if all_summaries else "<p>Aucune transcription valide.</p>"

    def create_daily_digest(self, articles: List[Dict], transcriptions: List[Dict]) -> str:
        """Créer le digest quotidien complet"""
        digest_parts = []
        
        # Header
        today = datetime.now().strftime('%d/%m/%Y')
        digest_parts.append(f"<h2>📰 Digest Quotidien - {today}</h2>")
        
        # Articles
        if articles:
            digest_parts.append("<h3>📰 Articles de Presse</h3>")
            articles_summary = self.summarize_articles(articles)
            digest_parts.append(articles_summary)
        
        # Transcriptions
        if transcriptions:
            digest_parts.append("<h3>📻 Transcriptions Radio</h3>")
            transcriptions_summary = self.summarize_transcriptions(transcriptions)
            digest_parts.append(transcriptions_summary)
        
        if not articles and not transcriptions:
            digest_parts.append("<p>Aucune information disponible pour aujourd'hui.</p>")
        
        return "<br><br>".join(digest_parts)

# Instance globale du service de résumé
summary_service = FreeSummaryService()

if __name__ == "__main__":
    # Test du service
    test_text = """
    La Guadeloupe connaît une nouvelle vague de développement économique. 
    Plusieurs entreprises locales ont annoncé des investissements importants dans le secteur touristique.
    Le gouvernement local soutient ces initiatives par des mesures fiscales avantageuses.
    Les emplois créés devraient bénéficier à plus de 500 personnes sur l'archipel.
    """
    
    result = summary_service.create_formatted_summary(test_text)
    print("Résumé formaté:")
    print(result)