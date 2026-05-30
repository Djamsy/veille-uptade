# backend/pdf_digest_service.py
"""
PDF Digest (look & feel Département de la Guadeloupe)
- Couleurs brand, en-tête avec logo, pied de page + pagination
- Badges KPI (articles / transcriptions)
- Rendu des sections "Articles" et "Transcriptions" en cartes
- Parseur HTML minimal pour digest_html si fourni
"""

import os
import re
import tempfile
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable, PageBreak
)
from reportlab.lib.units import mm

logger = logging.getLogger(__name__)

# =======================
# Palette "Département"
# =======================
BRAND_PRIMARY      = colors.HexColor("#177670")  # teal profond
BRAND_PRIMARY_LITE = colors.HexColor("#66C0BE")  # lagoon
BRAND_ACCENT       = colors.HexColor("#5EAF9C")  # teal-vert
BRAND_YELLOW       = colors.HexColor("#F8B902")  # jaune
INK_DARK           = colors.HexColor("#202C38")  # ardoise
INK_MUTED          = colors.HexColor("#6B7280")  # gris
BORDER             = colors.HexColor("#E5E7EB")  # gris clair
CARD_BG            = colors.HexColor("#F8FAFC")  # fond carte

DEFAULT_LOGO_PATH = os.environ.get("DIGEST_LOGO_PATH", "")  # ex: "assets/logo-departement.svg/png"


# ===== Petit séparateur "brand" =====
class BrandDivider(Flowable):
    def __init__(self, width=450, height=6):
        super().__init__()
        self.width = width
        self.height = height
    def draw(self):
        c = self.canv
        # bande teal + liseré jaune
        c.setFillColor(BRAND_PRIMARY)
        c.rect(0, 2, self.width, 4, stroke=0, fill=1)
        c.setFillColor(BRAND_YELLOW)
        c.rect(0, 0, self.width * 0.25, 2, stroke=0, fill=1)


class PDFDigestService:
    def __init__(self, logo_path: Optional[str] = None):
        self.logo_path = logo_path or DEFAULT_LOGO_PATH or ""
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    # ---------- Styles ----------
    def _setup_styles(self):
        self.styles.add(ParagraphStyle(
            name="BrandTitle",
            parent=self.styles["Heading1"],
            fontSize=22, leading=26,
            textColor=BRAND_PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=12
        ))
        self.styles.add(ParagraphStyle(
            name="SubHeading",
            parent=self.styles["Heading2"],
            fontSize=15, leading=19,
            textColor=BRAND_PRIMARY_LITE,
            spaceBefore=12, spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name="CardHeader",
            parent=self.styles["Heading3"],
            fontSize=12.5, leading=15,
            textColor=INK_DARK,
            spaceAfter=4
        ))
        self.styles.add(ParagraphStyle(
            name="Body",
            parent=self.styles["Normal"],
            fontSize=10.5, leading=14,
            textColor=INK_DARK,
            alignment=TA_JUSTIFY,
        ))
        self.styles.add(ParagraphStyle(
            name="Muted",
            parent=self.styles["Normal"],
            fontSize=9.5, leading=12,
            textColor=INK_MUTED
        ))
        self.styles.add(ParagraphStyle(
            name="KpiNumber",
            parent=self.styles["Heading2"],
            fontSize=18, leading=22,
            textColor=BRAND_PRIMARY,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name="KpiLabel",
            parent=self.styles["Normal"],
            fontSize=9.5, textColor=INK_MUTED,
            alignment=TA_CENTER
        ))

    # ---------- Header / Footer ----------
    def _header_footer(self, canvas, doc):
        canvas.saveState()

        # Bandeau haut teal
        canvas.setFillColor(BRAND_PRIMARY)
        canvas.rect(0, A4[1]-20*mm, A4[0], 20*mm, stroke=0, fill=1)

        # Liseré jaune
        canvas.setFillColor(BRAND_YELLOW)
        canvas.rect(0, A4[1]-20*mm, 60*mm, 2.5*mm, stroke=0, fill=1)

        # Logo (si présent)
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                canvas.drawImage(self.logo_path, 15*mm, A4[1]-17*mm, width=28*mm, height=12*mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Titre dans le bandeau
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.white)
        canvas.drawString(50*mm, A4[1]-11*mm, "Veille Média Guadeloupe — Digest Quotidien")

        # Pied de page
        canvas.setStrokeColor(BORDER)
        canvas.line(15*mm, 15*mm, A4[0]-15*mm, 15*mm)
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(INK_MUTED)
        canvas.drawString(15*mm, 10*mm, "Sources publiques | Analyse assistée par IA locale")
        canvas.drawRightString(A4[0]-15*mm, 10*mm, f"Page {doc.page}")

        canvas.restoreState()

    # ---------- API publique ----------
    def create_pdf_digest(self, digest_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        try:
            if not output_path:
                fd = tempfile.NamedTemporaryFile(prefix=f"digest_{datetime.now().strftime('%Y%m%d')}_", suffix=".pdf", delete=False)
                output_path = fd.name
                fd.close()

            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                leftMargin=18*mm, rightMargin=18*mm,
                topMargin=30*mm, bottomMargin=20*mm
            )

            story: List[Any] = []

            # En-tête de la page (titre + date)
            date_str = digest_data.get("date") or datetime.now().strftime("%Y-%m-%d")
            title = f"Digest Quotidien — {self._date_fr(date_str)}"
            story.append(Spacer(1, 4*mm))
            story.append(Paragraph(title, self.styles["BrandTitle"]))
            story.append(BrandDivider(width=440))

            # KPI
            story.append(Spacer(1, 6*mm))
            story.extend(self._build_kpi_row(
                articles_count=digest_data.get("articles_count", 0),
                transcriptions_count=digest_data.get("transcriptions_count", 0),
                created_at=digest_data.get("created_at", datetime.now().isoformat())
            ))
            story.append(Spacer(1, 6*mm))

            # Contenu HTML si présent
            digest_html = (digest_data.get("digest_html") or "").strip()
            if digest_html:
                story.append(Paragraph("Résumé éditorial", self.styles["SubHeading"]))
                self._add_html_to_story(story, digest_html)
                story.append(Spacer(1, 6*mm))

            # Cartes Articles
            articles = digest_data.get("articles") or []
            if articles:
                story.append(Paragraph("Articles marquants", self.styles["SubHeading"]))
                story.extend(self._build_article_cards(articles))
                story.append(Spacer(1, 4*mm))

            # Cartes Transcriptions
            trans = digest_data.get("transcriptions") or digest_data.get("transcriptions_list") or []
            if trans:
                story.append(Paragraph("Transcriptions radio", self.styles["SubHeading"]))
                story.extend(self._build_transcription_cards(trans))

            # Build
            doc.build(
                story,
                onFirstPage=self._header_footer,
                onLaterPages=self._header_footer
            )
            logger.info(f"✅ PDF digest généré: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"❌ Erreur génération PDF: {e}")
            raise

    # ---------- Blocs / cartes ----------
    def _build_kpi_row(self, articles_count: int, transcriptions_count: int, created_at: str) -> List[Any]:
        k1 = self._kpi_card(str(articles_count), "Articles analysés")
        k2 = self._kpi_card(str(transcriptions_count), "Transcriptions radio")
        k3 = self._kpi_card(self._dt_fr(created_at), "Généré le")

        table = Table([[k1, k2, k3]], colWidths=[65*mm, 65*mm, 65*mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("INNERGRID", (0,0), (-1,-1), 0, colors.white),
            ("BOX", (0,0), (-1,-1), 0, colors.white),
        ]))
        return [table]

    def _kpi_card(self, number: str, label: str):
        # Table pour créer une "carte" légère
        box = Table([
            [Paragraph(number, self.styles["KpiNumber"])],
            [Paragraph(label, self.styles["KpiLabel"])],
        ], colWidths=[60*mm])
        box.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), CARD_BG),
            ("BOX",       (0,0), (-1,-1), 0.75, BORDER),
            ("LINEBEFORE",(0,0), (-1,-1), 0.75, BORDER),
            ("LINEAFTER", (0,0), (-1,-1), 0.75, BORDER),
            ("TOPPADDING",(0,0), (-1,-1), 6),
            ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ]))
        return box

    def _build_article_cards(self, articles: List[Dict[str, Any]]) -> List[Any]:
        flows: List[Any] = []
        for a in articles[:12]:  # limiter pour la lisibilité
            title = self._escape(a.get("title") or "Sans titre")
            src = a.get("source") or a.get("site") or ""
            url = a.get("url") or ""
            t = a.get("date") or a.get("scraped_at") or ""
            summary = a.get("ai_summary") or a.get("summary") or a.get("gpt_analysis") or ""

            head = f"<b>{title}</b>"
            meta = " • ".join([x for x in [src, self._dt_fr(t)] if x])
            body = self._sanitize_inline_html(summary)

            card = Table([
                [Paragraph(head, self.styles["CardHeader"])],
                [Paragraph(meta, self.styles["Muted"])],
                [Spacer(1, 1*mm)],
                [Paragraph(body, self.styles["Body"])],
                [Paragraph(self._link(url), self.styles["Muted"]) if url else ""],
            ], colWidths=[440])
            card.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1), colors.white),
                ("BOX",      (0,0),(-1,-1), 0.75, BORDER),
                ("LINEABOVE",(0,0),(-1,0),  2, BRAND_PRIMARY_LITE),
                ("LEFTPADDING",(0,0),(-1,-1), 8),
                ("RIGHTPADDING",(0,0),(-1,-1), 8),
                ("TOPPADDING",(0,0),(-1,-1), 6),
                ("BOTTOMPADDING",(0,0),(-1,-1), 8),
            ]))
            flows.extend([card, Spacer(1, 4*mm)])
        return flows

    def _build_transcription_cards(self, trans: List[Dict[str, Any]]) -> List[Any]:
        flows: List[Any] = []
        for t in trans[:8]:
            name = t.get("stream_name") or t.get("section") or "Journal"
            when = self._dt_fr(t.get("captured_at") or t.get("timestamp") or "")
            dur = int(t.get("duration_seconds") or 0)
            mins = f"{dur//60} min" if dur else ""
            head = f"<b>{self._escape(name)}</b>"
            meta = " • ".join([x for x in [when, mins] if x])
            summ = t.get("ai_summary") or t.get("gpt_analysis") or t.get("transcription_text", "")[:400]
            body = self._sanitize_inline_html(summ)

            card = Table([
                [Paragraph(head, self.styles["CardHeader"])],
                [Paragraph(meta, self.styles["Muted"])],
                [Spacer(1, 1*mm)],
                [Paragraph(body, self.styles["Body"])],
            ], colWidths=[440])
            card.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,-1), colors.white),
                ("BOX",      (0,0),(-1,-1), 0.75, BORDER),
                ("LINEABOVE",(0,0),(-1,0),  2, BRAND_ACCENT),
                ("LEFTPADDING",(0,0),(-1,-1), 8),
                ("RIGHTPADDING",(0,0),(-1,-1), 8),
                ("TOPPADDING",(0,0),(-1,-1), 6),
                ("BOTTOMPADDING",(0,0),(-1,-1), 8),
            ]))
            flows.extend([card, Spacer(1, 4*mm)])
        return flows

    # ---------- HTML → PDF (minimal mais propre) ----------
    def _add_html_to_story(self, story: List[Any], html: str):
        # Remplacements basiques de balises pour Paragraph
        lines = [l.strip() for l in html.split("\n") if l.strip()]
        for line in lines:
            if re.search(r"</?h2>", line, flags=re.I):
                text = re.sub(r"</?h2>", "", line, flags=re.I)
                story.append(Paragraph(self._sanitize_inline_html(text), self.styles["SubHeading"]))
            elif re.search(r"</?h3>", line, flags=re.I):
                text = re.sub(r"</?h3>", "", line, flags=re.I)
                story.append(Paragraph(f"<b>{self._sanitize_inline_html(text)}</b>", self.styles["Body"]))
            else:
                story.append(Paragraph(self._sanitize_inline_html(line), self.styles["Body"]))
        story.append(Spacer(1, 2*mm))

    # ---------- Helpers ----------
    def _sanitize_inline_html(self, text: str) -> str:
        if not text:
            return ""
        # keep <b>, <i>, <br/> ; convert <strong>/<em>; strip others
        t = text
        t = re.sub(r"<\s*strong\s*>", "<b>", t, flags=re.I)
        t = re.sub(r"<\s*/\s*strong\s*>", "</b>", t, flags=re.I)
        t = re.sub(r"<\s*em\s*>", "<i>", t, flags=re.I)
        t = re.sub(r"<\s*/\s*em\s*>", "</i>", t, flags=re.I)
        t = re.sub(r"<\s*br\s*/?\s*>", "<br/>", t, flags=re.I)

        # liens → "Texte (URL)"
        link_pat = re.compile(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', flags=re.I)
        def _repl(m):
            url = m.group(1).strip()
            label = self._escape(m.group(2))
            return f"<b>{label}</b> ({self._escape(url)})"
        t = link_pat.sub(_repl, t)

        # supprimer le reste des balises
        t = re.sub(r"<[^>]+>", "", t)
        # espaces
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _escape(self, s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _date_fr(self, date_str: str) -> str:
        try:
            d = datetime.fromisoformat(date_str.replace("Z","+00:00")) if "T" in date_str else datetime.strptime(date_str, "%Y-%m-%d")
            mois = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
            return f"{d.day} {mois[d.month-1]} {d.year}"
        except Exception:
            return date_str

    def _dt_fr(self, dt_str: str) -> str:
        if not dt_str:
            return ""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z","+00:00"))
            return f"{self._date_fr(dt.strftime('%Y-%m-%d'))} à {dt.strftime('%H:%M')}"
        except Exception:
            return dt_str


# Instance + helper
pdf_digest_service = PDFDigestService()

def create_digest_pdf(digest_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
    return pdf_digest_service.create_pdf_digest(digest_data, output_path)
