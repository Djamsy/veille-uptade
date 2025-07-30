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
        """Résumer les transcriptions radio avec format HTML spécifique"""
        if not transcriptions:
            return "<p>Aucune transcription radio disponible pour cette journée.</p>"
        
        all_summaries = []
        
        for transcription in transcriptions:
            # Données de base
            stream_name = transcription.get('stream_name', transcription.get('section', 'Radio'))
            start_time = transcription.get('start_time', '')
            captured_at = transcription.get('captured_at', '')
            
            # Utiliser l'analyse IA si disponible, sinon fallback
            ai_summary = transcription.get('ai_summary', '')
            ai_keywords = transcription.get('ai_keywords', [])
            ai_relevance_score = transcription.get('ai_relevance_score', 0)
            raw_text = transcription.get('transcription_text', '')
            
            # Vérifier si on a du contenu valide
            content_to_use = ai_summary if ai_summary and ai_summary != raw_text else raw_text
            
            if content_to_use and len(content_to_use.strip()) > 10:
                # Format HTML demandé : <strong>titre</strong> + texte + <p>
                
                # Créer le titre avec horaire
                time_info = f" ({start_time})" if start_time else ""
                if captured_at:
                    date_part = captured_at[:10] if len(captured_at) >= 10 else ""
                    time_part = captured_at[11:16] if len(captured_at) >= 16 else ""
                    time_info = f" - {date_part} {time_part}"
                
                title = f"<strong>📻 {stream_name}{time_info}</strong>"
                
                # Contenu principal (résumé IA ou transcription nettoyée)
                if ai_summary and ai_summary != raw_text:
                    # Utiliser le résumé IA
                    content = ai_summary
                else:
                    # Nettoyer et raccourcir la transcription brute
                    content = self._clean_and_shorten_transcription(content_to_use, 200)
                
                # Ajouter les mots-clés si disponibles
                keywords_html = ""
                if ai_keywords and len(ai_keywords) > 0:
                    keywords_list = ", ".join(ai_keywords[:5])
                    keywords_html = f"<br><em>Mots-clés: {keywords_list}</em>"
                
                # Score de pertinence si disponible
                relevance_html = ""
                if ai_relevance_score and ai_relevance_score > 0.3:
                    stars = "⭐" * min(int(ai_relevance_score * 5), 5)
                    relevance_html = f"<br><small>Pertinence: {stars} ({int(ai_relevance_score * 100)}%)</small>"
                
                # Assembler selon le format demandé
                transcription_summary = f"""
{title}
{content}
{keywords_html}
{relevance_html}
<p></p>
""".strip()
                
                all_summaries.append(transcription_summary)
        
        if not all_summaries:
            return "<p>Aucune transcription radio valide pour cette journée.</p>"
        
        # Joindre toutes les transcriptions
        return "<br><hr><br>".join(all_summaries)

    def _clean_and_shorten_transcription(self, text: str, max_length: int = 200) -> str:
        """Nettoyer et raccourcir une transcription brute"""
        if not text:
            return "Transcription non disponible"
        
        # Nettoyer les bruits de parole courants
        import re
        clean_text = re.sub(r'\b(euh+|heu+|ben|alors|donc|voilà|quoi|hein)\b', ' ', text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Raccourcir si nécessaire
        if len(clean_text) > max_length:
            # Couper à la dernière phrase complète
            shortened = clean_text[:max_length]
            last_period = shortened.rfind('.')
            last_exclamation = shortened.rfind('!')
            last_question = shortened.rfind('?')
            
            cut_point = max(last_period, last_exclamation, last_question)
            if cut_point > max_length // 2:  # Si on trouve une fin de phrase raisonnable
                clean_text = shortened[:cut_point + 1]
            else:
                clean_text = shortened + "..."
        
        return clean_text

    def create_daily_digest(self, articles: List[Dict], transcriptions: List[Dict]) -> str:
        """Créer le digest quotidien complet avec analyse de sentiment"""
        try:
            if not articles and not transcriptions:
                return """
                <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #dc2626;">🏝️ Digest Guadeloupe - Aucun contenu disponible</h2>
                    <p>Aucune information disponible pour aujourd'hui.</p>
                </div>
                """
            
            # Import du service de sentiment
            try:
                from sentiment_analysis_service import analyze_articles_sentiment
                sentiment_enabled = True
            except ImportError:
                sentiment_enabled = False
            
            # Analyser le sentiment des articles si disponibles
            sentiment_analysis = None
            analyzed_articles = []
            if sentiment_enabled and articles:
                try:
                    sentiment_result = analyze_articles_sentiment(articles)
                    sentiment_analysis = sentiment_result.get('summary', {})
                    analyzed_articles = sentiment_result.get('articles', articles)
                except Exception as e:
                    logger.warning(f"Erreur analyse sentiment pour digest: {e}")
                    analyzed_articles = articles
            else:
                analyzed_articles = articles
            
            digest_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6;">
                <header style="text-align: center; border-bottom: 3px solid #2563eb; padding-bottom: 20px; margin-bottom: 30px;">
                    <h1 style="color: #1e40af; margin: 0; font-size: 28px;">🏝️ Digest Quotidien Guadeloupe</h1>
                    <p style="color: #6b7280; font-size: 16px; margin: 10px 0 0 0;">
                        {datetime.now().strftime('%A %d %B %Y')} • {len(articles) if articles else 0} articles analysés
                    </p>
                </header>
            """
            
            # Section analyse de sentiment
            if sentiment_analysis and sentiment_analysis.get('total_articles', 0) > 0:
                distribution = sentiment_analysis.get('sentiment_distribution', {})
                avg_score = sentiment_analysis.get('average_sentiment_score', 0)
                patterns = sentiment_analysis.get('most_common_patterns', {})
                
                # Déterminer la tendance générale
                if avg_score > 0.1:
                    tendance = "🟢 Positive"
                    couleur_tendance = "#16a34a"
                elif avg_score < -0.1:
                    tendance = "🔴 Négative"  
                    couleur_tendance = "#dc2626"
                else:
                    tendance = "🟡 Neutre"
                    couleur_tendance = "#ca8a04"
                
                digest_html += f"""
                <section style="background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border-left: 4px solid #3b82f6; padding: 25px; margin-bottom: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <h2 style="color: #1e40af; margin-top: 0; font-size: 24px; display: flex; align-items: center;">
                        📊 Analyse de Sentiment du Jour
                    </h2>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px;">
                        <div style="text-align: center; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <div style="font-size: 20px; font-weight: bold; color: {couleur_tendance}; margin-bottom: 5px;">{tendance}</div>
                            <div style="color: #6b7280; font-size: 13px;">Tendance générale</div>
                            <div style="font-size: 11px; color: #9ca3af; margin-top: 3px;">Score: {avg_score:.2f}</div>
                        </div>
                        
                        <div style="text-align: center; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <div style="font-size: 20px; font-weight: bold; color: #16a34a; margin-bottom: 5px;">😊 {distribution.get('positive', 0)}</div>
                            <div style="color: #6b7280; font-size: 13px;">Articles positifs</div>
                        </div>
                        
                        <div style="text-align: center; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <div style="font-size: 20px; font-weight: bold; color: #dc2626; margin-bottom: 5px;">😟 {distribution.get('negative', 0)}</div>
                            <div style="color: #6b7280; font-size: 13px;">Articles négatifs</div>
                        </div>
                        
                        <div style="text-align: center; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <div style="font-size: 20px; font-weight: bold; color: #6b7280; margin-bottom: 5px;">😐 {distribution.get('neutral', 0)}</div>
                            <div style="color: #6b7280; font-size: 13px;">Articles neutres</div>
                        </div>
                    </div>
                """
                
                # Patterns détectés
                if patterns:
                    top_patterns = list(patterns.items())[:4]
                    digest_html += f"""
                    <div style="margin-top: 20px;">
                        <h4 style="color: #374151; margin-bottom: 12px; font-size: 16px;">🔍 Thèmes principaux détectés:</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                    """
                    
                    pattern_labels = {
                        'événement_culturel': '🎭 Événements culturels',
                        'météo_extrême': '🌪️ Météo extrême',
                        'secteur_touristique': '🏖️ Tourisme',
                        'mouvement_social': '✊ Mouvements sociaux',
                        'secteur_économique': '💼 Économie',
                        'situation_urgente': '🚨 Urgences'
                    }
                    
                    for pattern, count in top_patterns:
                        label = pattern_labels.get(pattern, pattern.replace('_', ' ').title())
                        digest_html += f"""
                        <span style="background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); color: #3730a3; padding: 8px 12px; border-radius: 20px; font-size: 13px; font-weight: 500; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            {label} ({count})
                        </span>
                        """
                    
                    digest_html += "</div></div>"
                
                digest_html += "</section>"
            
            # 🎯 TRANSCRIPTIONS RADIO EN PREMIER (PRIORITÉ ÉLEVÉE)
            if transcriptions:
                digest_html += f"""
                <section style="margin-bottom: 40px; padding: 25px; background: linear-gradient(135deg, #fef3c7 0%, #fef7e1 100%); border-radius: 15px; border: 2px solid #f59e0b; box-shadow: 0 6px 12px rgba(245, 158, 11, 0.2);">
                    <h2 style="color: #92400e; margin-top: 0; font-size: 26px; display: flex; align-items: center; margin-bottom: 25px;">
                        🎙️ ACTUALITÉ RADIO LOCALE - PRIORITÉ ÉLEVÉE
                        <span style="background: #f59e0b; color: white; font-size: 12px; padding: 4px 8px; border-radius: 20px; margin-left: 15px;">
                            {len(transcriptions)} transcription{'s' if len(transcriptions) > 1 else ''}
                        </span>
                    </h2>
                    <div style="background: rgba(245, 158, 11, 0.1); padding: 15px; border-radius: 10px; margin-bottom: 20px;">
                        <p style="color: #92400e; margin: 0; font-weight: 500; text-align: center;">
                            📻 Informations directes des radios guadeloupéennes • Contenu analysé par IA
                        </p>
                    </div>
                """
                
                # Utiliser la nouvelle méthode avec format HTML amélioré
                transcriptions_content = self.summarize_transcriptions(transcriptions)
                digest_html += transcriptions_content
                
                digest_html += "</section>"
            
            # 📰 ARTICLES DE PRESSE (SECTION SECONDAIRE)
            if analyzed_articles:
                # Ajouter un en-tête spécial pour montrer que c'est secondaire
                digest_html += f"""
                <section style="margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border-radius: 10px; border: 1px solid #cbd5e1;">
                    <h2 style="color: #475569; margin-top: 0; font-size: 22px; display: flex; align-items: center; margin-bottom: 15px;">
                        📰 Articles de Presse - Complément d'Information
                        <span style="background: #64748b; color: white; font-size: 11px; padding: 3px 8px; border-radius: 15px; margin-left: 10px;">
                            Secondaire
                        </span>
                    </h2>
                    <div style="background: rgba(100, 116, 139, 0.1); padding: 12px; border-radius: 8px; margin-bottom: 20px;">
                        <p style="color: #475569; margin: 0; font-size: 14px; text-align: center;">
                            📊 Informations complémentaires • {len(analyzed_articles)} articles analysés
                        </p>
                    </div>
                </section>
                """
                
                sources = {}
                for article in analyzed_articles:
                    source = article.get('source', 'Source inconnue')
                    if source not in sources:
                        sources[source] = []
                    sources[source].append(article)
                
                # Trier les sources par nombre d'articles (limiter pour donner moins d'importance)
                sorted_sources = sorted(sources.items(), key=lambda x: len(x[1]), reverse=True)[:3]  # Max 3 sources
                
                for source, source_articles in sorted_sources:
                    digest_html += f"""
                    <section style="margin-bottom: 25px; background: white; padding: 15px; border-radius: 8px; border-left: 3px solid #cbd5e1;">
                        <h3 style="color: #475569; margin-top: 0; font-size: 18px; margin-bottom: 15px;">
                            📰 {source} <span style="color: #94a3b8; font-size: 14px;">({len(source_articles)} articles)</span>
                        </h3>
                    """
                    
                    # Limiter à 5 articles par source (au lieu de 8) pour réduire l'importance
                    for i, article in enumerate(source_articles[:5]):
                        title = article.get('title', 'Titre non disponible')
                        url = article.get('url', '#')
                        scraped_at = article.get('scraped_at', '')
                        
                        # Ajouter l'info de sentiment si disponible
                        sentiment_info = ""
                        if 'sentiment_summary' in article:
                            sentiment = article['sentiment_summary']
                            polarity = sentiment.get('polarity', 'neutral')
                            score = sentiment.get('score', 0)
                            
                            if polarity == 'positive':
                                sentiment_emoji = "😊"
                                sentiment_color = "#16a34a"
                            elif polarity == 'negative':
                                sentiment_emoji = "😟"
                                sentiment_color = "#dc2626"
                            else:
                                sentiment_emoji = "😐"
                                sentiment_color = "#6b7280"
                            
                            sentiment_info = f"""
                            <span style="background: {sentiment_color}15; color: {sentiment_color}; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 500; margin-left: 10px;">
                                {sentiment_emoji} {polarity.title()} ({score:+.2f})
                            </span>
                            """
                        
                        # Alternating background colors
                        bg_color = "#f9fafb" if i % 2 == 0 else "#ffffff"
                        
                        digest_html += f"""
                        <div style="margin-bottom: 12px; padding: 18px; background: {bg_color}; border-radius: 10px; border-left: 3px solid #3b82f6; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: transform 0.2s;">
                            <h4 style="margin: 0 0 10px 0; line-height: 1.4;">
                                <a href="{url}" target="_blank" style="color: #1e40af; text-decoration: none; font-weight: 600; font-size: 16px;">
                                    {title}
                                </a>
                                {sentiment_info}
                            </h4>
                            <p style="color: #6b7280; font-size: 13px; margin: 0; display: flex; align-items: center;">
                                📅 {scraped_at[:16].replace('T', ' à ') if scraped_at else 'Date inconnue'}
                            </p>
                        </div>
                        """
                    
                    digest_html += "</section>"
            

            # Footer avec informations détaillées
            digest_html += f"""
                <footer style="margin-top: 50px; padding-top: 25px; border-top: 2px solid #e5e7eb; text-align: center; background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%); border-radius: 10px; padding: 25px;">
                    <div style="margin-bottom: 15px;">
                        <h3 style="color: #1e40af; margin: 0 0 10px 0; font-size: 18px;">📊 Statistiques du Digest</h3>
                        <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap;">
                            <span style="color: #374151; font-weight: 500;">📰 {len(articles) if articles else 0} articles</span>
                            <span style="color: #374151; font-weight: 500;">📻 {len(transcriptions) if transcriptions else 0} transcriptions</span>
                            <span style="color: #374151; font-weight: 500;">🤖 Analyse sentiment: {'✅ Activée' if sentiment_enabled else '❌ Désactivée'}</span>
                        </div>
                    </div>
                    <p style="color: #6b7280; font-size: 14px; margin: 10px 0;">
                        📊 Digest généré automatiquement le {datetime.now().strftime('%d/%m/%Y à %H:%M')}
                    </p>
                    <p style="color: #9ca3af; font-size: 12px; margin: 0;">
                        🏝️ Veille média Guadeloupe • Analyse locale française • Cache intelligent
                    </p>
                </footer>
            </div>
            """
            
            return digest_html
            
        except Exception as e:
            logger.error(f"Erreur création digest avec sentiment: {e}")
            return f"""
            <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #dc2626;">❌ Erreur lors de la création du digest</h2>
                <p>Une erreur s'est produite: {str(e)}</p>
                <p>Veuillez réessayer plus tard.</p>
            </div>
            """

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