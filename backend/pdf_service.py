"""
Service de génération de PDF pour le digest quotidien
"""
import os
from datetime import datetime
from typing import Dict, Any, List
import tempfile
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import logging

logger = logging.getLogger(__name__)

class PDFDigestService:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Configurer les styles personnalisés pour le PDF"""
        # Style pour le titre principal
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2563eb'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Style pour les sections
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.HexColor('#1e40af'),
            fontName='Helvetica-Bold'
        ))
        
        # Style pour le contenu
        self.styles.add(ParagraphStyle(
            name='CustomBodyText',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
            fontName='Helvetica'
        ))
        
        # Style pour les sous-titres
        self.styles.add(ParagraphStyle(
            name='SubTitle',
            parent=self.styles['Normal'],
            fontSize=13,
            spaceAfter=8,
            spaceBefore=10,
            textColor=colors.HexColor('#374151'),
            fontName='Helvetica-Bold'
        ))
    
    def create_pdf_digest(self, digest_data: Dict[str, Any], output_path: str = None) -> str:
        """Créer un PDF du digest quotidien"""
        try:
            # Créer un fichier temporaire si pas de chemin spécifié
            if not output_path:
                temp_file = tempfile.NamedTemporaryFile(
                    suffix='.pdf', 
                    delete=False,
                    prefix=f"digest_{datetime.now().strftime('%Y%m%d')}_"
                )
                output_path = temp_file.name
                temp_file.close()
            
            # Créer le document PDF
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            # Construire le contenu
            story = []
            
            # Titre principal
            date_formatted = digest_data.get('date', datetime.now().strftime('%Y-%m-%d'))
            title = f"Digest Quotidien Guadeloupe - {self._format_date_french(date_formatted)}"
            story.append(Paragraph(title, self.styles['CustomTitle']))
            story.append(Spacer(1, 20))
            
            # Informations générales
            articles_count = digest_data.get('articles_count', 0)
            transcriptions_count = digest_data.get('transcriptions_count', 0)
            created_at = digest_data.get('created_at', datetime.now().isoformat())
            
            info_text = f"""
            <b>Articles analysés:</b> {articles_count} articles<br/>
            <b>Transcriptions radio:</b> {transcriptions_count} transcriptions<br/>
            <b>Généré le:</b> {self._format_datetime_french(created_at)}<br/>
            <b>Source:</b> Veille Média Guadeloupe
            """
            story.append(Paragraph(info_text, self.styles['CustomBodyText']))
            story.append(Spacer(1, 20))
            
            # Contenu principal du digest
            digest_html = digest_data.get('digest_html', '')
            if digest_html:
                # Convertir le HTML en contenu PDF
                self._add_html_content_to_story(story, digest_html)
            else:
                story.append(Paragraph("Aucun contenu disponible pour ce digest.", self.styles['CustomBodyText']))
            
            # Pied de page
            story.append(Spacer(1, 30))
            footer_text = """
            <i>Ce document a été généré automatiquement par le système de veille média de la Guadeloupe. 
            Les informations proviennent de sources publiques et sont analysées par intelligence artificielle locale.</i>
            """
            story.append(Paragraph(footer_text, self.styles['CustomBodyText']))
            
            # Générer le PDF
            doc.build(story)
            
            logger.info(f"✅ PDF digest généré: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Erreur génération PDF: {e}")
            raise
    
    def _add_html_content_to_story(self, story: List, html_content: str):
        """Convertir le contenu HTML en éléments PDF"""
        try:
            # Nettoyer et structurer le HTML
            # Cette fonction peut être étendue pour un parsing HTML plus sophistiqué
            
            # Pour l'instant, on extrait le texte principal et on le structure
            lines = html_content.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Détecter les titres HTML
                if '<h2>' in line and '</h2>' in line:
                    title = line.replace('<h2>', '').replace('</h2>', '').strip()
                    story.append(Paragraph(title, self.styles['SectionHeader']))
                    current_section = title
                
                elif '<h3>' in line and '</h3>' in line:
                    subtitle = line.replace('<h3>', '').replace('</h3>', '').strip()
                    story.append(Paragraph(subtitle, self.styles['SubTitle']))
                
                elif '<strong>' in line and '</strong>' in line:
                    # Texte en gras
                    text = line.replace('<strong>', '<b>').replace('</strong>', '</b>')
                    story.append(Paragraph(text, self.styles['CustomBodyText']))
                
                elif '<a href=' in line:
                    # Liens - les garder mais nettoyer
                    text = self._clean_html_links(line)
                    story.append(Paragraph(text, self.styles['CustomBodyText']))
                
                elif '<p>' in line or any(tag in line for tag in ['<div>', '<span>']):
                    # Paragraphes et autres contenus
                    text = self._clean_html_tags(line)
                    if len(text.strip()) > 10:  # Éviter les lignes trop courtes
                        story.append(Paragraph(text, self.styles['CustomBodyText']))
                
                elif len(line) > 20 and not line.startswith('<'):
                    # Texte brut suffisamment long
                    story.append(Paragraph(line, self.styles['CustomBodyText']))
            
        except Exception as e:
            logger.warning(f"Erreur parsing HTML pour PDF: {e}")
            # Fallback: ajouter le contenu brut
            clean_text = self._clean_html_tags(html_content)
            story.append(Paragraph(clean_text, self.styles['CustomBodyText']))
    
    def _clean_html_tags(self, text: str) -> str:
        """Nettoyer les tags HTML et garder le formatage basique"""
        import re
        
        # Remplacer les tags de formatage par des équivalents ReportLab
        text = re.sub(r'<strong>(.*?)</strong>', r'<b>\1</b>', text)
        text = re.sub(r'<em>(.*?)</em>', r'<i>\1</i>', text)
        text = re.sub(r'<br\s*/?>', '<br/>', text)
        
        # Supprimer les autres tags HTML
        text = re.sub(r'<[^>]+>', '', text)
        
        # Nettoyer les espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _clean_html_links(self, text: str) -> str:
        """Extraire et formater les liens HTML"""
        import re
        
        # Extraire les liens et les formater
        link_pattern = r'<a href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(link_pattern, text)
        
        result = text
        for url, link_text in matches:
            # Formater comme: "Texte du lien (URL)"
            formatted_link = f'<b>{link_text}</b> ({url})'
            result = re.sub(
                r'<a href="' + re.escape(url) + r'"[^>]*>' + re.escape(link_text) + r'</a>', 
                formatted_link, 
                result
            )
        
        return self._clean_html_tags(result)
    
    def _format_date_french(self, date_str: str) -> str:
        """Formater une date en français"""
        try:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if 'T' in date_str else datetime.strptime(date_str, '%Y-%m-%d')
            
            months = [
                'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
            ]
            
            return f"{date_obj.day} {months[date_obj.month - 1]} {date_obj.year}"
        except:
            return date_str
    
    def _format_datetime_french(self, datetime_str: str) -> str:
        """Formater un datetime en français"""
        try:
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            return f"{self._format_date_french(dt.strftime('%Y-%m-%d'))} à {dt.strftime('%H:%M')}"
        except:
            return datetime_str

# Instance globale du service PDF
pdf_digest_service = PDFDigestService()

def create_digest_pdf(digest_data: Dict[str, Any], output_path: str = None) -> str:
    """Fonction utilitaire pour créer un PDF du digest"""
    return pdf_digest_service.create_pdf_digest(digest_data, output_path)