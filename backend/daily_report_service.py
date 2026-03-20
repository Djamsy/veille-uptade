# backend/daily_report_service.py
"""
Service de génération du bilan quotidien en PDF.
Génère un rapport PDF professionnel résumant la veille de la veille,
puis l'envoie par Telegram.

Planifié à 7h du matin (heure Guadeloupe) via le scheduler.
"""

import os
import io
import json
import logging
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger("veille.daily_report")

# ============================================================
# CONFIGURATION
# ============================================================
REPORT_RETENTION_DAYS = 30  # Garder les rapports 30 jours en base


def generate_daily_pdf(db) -> Optional[bytes]:
    """
    Génère le bilan PDF de la veille.
    Retourne les bytes du PDF ou None si erreur.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm, cm
        from reportlab.lib.colors import HexColor, white, black
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, HRFlowable
        )
    except ImportError:
        logger.error("reportlab non installé — pip install reportlab")
        return None

    now = datetime.now()
    yesterday = now - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    date_label = yesterday.strftime("%d/%m/%Y")

    # ── Collecter les données de la veille ──────────────────
    articles_col = db["articles_guadeloupe"]
    affairs_col = db.get_collection("affairs")
    transcriptions_col = db["radio_transcriptions"]
    social_col = db.get_collection("social_posts")

    # Articles du jour
    cutoff_start = yesterday.replace(hour=0, minute=0, second=0)
    cutoff_end = yesterday.replace(hour=23, minute=59, second=59)
    cutoff_start_str = cutoff_start.isoformat()
    cutoff_end_str = cutoff_end.isoformat()

    articles = list(articles_col.find({
        "$or": [
            {"scraped_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
            {"scraped_at": {"$gte": cutoff_start_str, "$lte": cutoff_end_str}},
            {"date": yesterday_str},
        ]
    }).sort("gravity_score", -1).limit(50))

    # Affaires actives
    active_affairs = list(affairs_col.find({"status": "active"}).sort("priority", -1).limit(20))

    # Transcriptions radio du jour
    radio_topics = list(transcriptions_col.find({
        "$or": [
            {"captured_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
            {"captured_at": {"$gte": cutoff_start_str, "$lte": cutoff_end_str}},
        ]
    }).limit(30))

    # Posts sociaux du jour
    social_posts = []
    if social_col:
        social_posts = list(social_col.find({
            "$or": [
                {"scraped_at": {"$gte": cutoff_start, "$lte": cutoff_end}},
                {"scraped_at": {"$gte": cutoff_start_str, "$lte": cutoff_end_str}},
            ]
        }).sort("engagement_total", -1).limit(20))

    # Stats globales
    total_articles = len(articles)
    total_radio = len(radio_topics)
    total_social = len(social_posts)
    total_affairs = len(active_affairs)

    # Top thèmes
    from collections import Counter
    themes = Counter(a.get("theme", "general") for a in articles)
    top_themes = themes.most_common(5)

    # Top sources
    sources = Counter(a.get("source", "?") for a in articles)
    top_sources = sources.most_common(5)

    # Articles haute gravité
    high_gravity = [a for a in articles if (a.get("gravity_score") or 0) >= 0.6]

    # ── Construire le PDF ───────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
    )

    # Couleurs Guadeloupe
    GREEN = HexColor("#16a34a")
    RED = HexColor("#dc2626")
    YELLOW = HexColor("#facc15")
    BLUE = HexColor("#2563eb")
    DARK = HexColor("#0f172a")
    GRAY = HexColor("#64748b")
    LIGHT_BG = HexColor("#f1f5f9")

    # Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Title'],
        fontSize=22, textColor=GREEN, spaceAfter=6,
        fontName='Helvetica-Bold',
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle', parent=styles['Normal'],
        fontSize=11, textColor=GRAY, alignment=TA_CENTER,
        spaceAfter=20,
    )
    section_style = ParagraphStyle(
        'SectionTitle', parent=styles['Heading2'],
        fontSize=14, textColor=DARK, spaceBefore=16, spaceAfter=8,
        fontName='Helvetica-Bold', borderWidth=0,
        leftIndent=0,
    )
    body_style = ParagraphStyle(
        'ReportBody', parent=styles['Normal'],
        fontSize=9, textColor=DARK, leading=13,
    )
    small_style = ParagraphStyle(
        'SmallText', parent=styles['Normal'],
        fontSize=8, textColor=GRAY, leading=11,
    )
    kpi_num_style = ParagraphStyle(
        'KpiNum', parent=styles['Normal'],
        fontSize=24, fontName='Helvetica-Bold',
        textColor=GREEN, alignment=TA_CENTER,
    )
    kpi_label_style = ParagraphStyle(
        'KpiLabel', parent=styles['Normal'],
        fontSize=8, textColor=GRAY, alignment=TA_CENTER,
    )

    story = []

    # ── En-tête ──
    story.append(Paragraph("VEILLE MÉDIA GUADELOUPE", title_style))
    story.append(Paragraph(f"Bilan du {date_label}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=GREEN, spaceAfter=15))

    # ── KPIs ──
    kpi_data = [
        [
            Paragraph(str(total_articles), kpi_num_style),
            Paragraph(str(total_radio), kpi_num_style),
            Paragraph(str(total_social), kpi_num_style),
            Paragraph(str(total_affairs), kpi_num_style),
            Paragraph(str(len(high_gravity)), kpi_num_style),
        ],
        [
            Paragraph("Articles", kpi_label_style),
            Paragraph("Sujets radio", kpi_label_style),
            Paragraph("Posts sociaux", kpi_label_style),
            Paragraph("Affaires actives", kpi_label_style),
            Paragraph("Alertes", kpi_label_style),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[3.2 * cm] * 5)
    kpi_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 15))

    # ── Affaires prioritaires ──
    if active_affairs:
        story.append(Paragraph("AFFAIRES PRIORITAIRES", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY, spaceAfter=8))

        for i, aff in enumerate(active_affairs[:8]):
            gravity = aff.get("gravity_score", 0)
            gravity_pct = int(gravity * 100)
            bmg = int((aff.get("bmg", 0)) * 100)
            items = aff.get("item_count", 0)
            sentiment = aff.get("sentiment", "neutre")
            title = (aff.get("title") or "Sans titre")[:80]
            desc = (aff.get("description") or "")[:120]

            # Couleur gravité
            if gravity >= 0.7:
                grav_color = RED
                grav_label = "CRITIQUE"
            elif gravity >= 0.5:
                grav_color = HexColor("#f97316")
                grav_label = "ÉLEVÉE"
            else:
                grav_color = GREEN
                grav_label = "MODÉRÉE"

            affair_text = (
                f'<b>{i+1}. {title}</b><br/>'
                f'<font color="#64748b" size="8">{desc}</font><br/>'
                f'<font color="{grav_color.hexval()}" size="8"><b>Gravité {gravity_pct}% ({grav_label})</b></font> '
                f'<font color="#64748b" size="8">| BMG {bmg} | {items} items | {sentiment}</font>'
            )
            story.append(Paragraph(affair_text, body_style))
            story.append(Spacer(1, 6))

    # ── Articles haute gravité ──
    if high_gravity:
        story.append(Spacer(1, 8))
        story.append(Paragraph("ARTICLES À HAUTE GRAVITÉ", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RED, spaceAfter=8))

        for art in high_gravity[:10]:
            grav = int((art.get("gravity_score") or 0) * 100)
            source = art.get("source", "?")
            theme = art.get("theme", "")
            title = (art.get("title") or "Sans titre")[:90]

            art_text = (
                f'<font color="#dc2626" size="8"><b>{grav}%</b></font> '
                f'<b>{title}</b><br/>'
                f'<font color="#64748b" size="8">{source} | {theme}</font>'
            )
            story.append(Paragraph(art_text, body_style))
            story.append(Spacer(1, 4))

    # ── Thèmes du jour ──
    if top_themes:
        story.append(Spacer(1, 8))
        story.append(Paragraph("THÈMES DU JOUR", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BLUE, spaceAfter=8))

        theme_labels = {
            "securite_justice": "Sécurité / Justice",
            "politique": "Politique",
            "economie_emploi": "Économie / Emploi",
            "sante_social": "Santé / Social",
            "education": "Éducation",
            "culture_patrimoine": "Culture / Patrimoine",
            "eau_env": "Eau / Environnement",
            "energie_transports": "Énergie / Transports",
            "sport": "Sport",
            "general": "Général",
        }

        theme_data = [["Thème", "Articles", "%"]]
        for theme, count in top_themes:
            pct = int(count / max(total_articles, 1) * 100)
            label = theme_labels.get(theme, theme)
            theme_data.append([label, str(count), f"{pct}%"])

        theme_table = Table(theme_data, colWidths=[8 * cm, 3 * cm, 3 * cm])
        theme_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, LIGHT_BG]),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(theme_table)

    # ── Sources du jour ──
    if top_sources:
        story.append(Spacer(1, 8))
        story.append(Paragraph("SOURCES", section_style))
        source_text = " | ".join(f"<b>{s}</b> ({c})" for s, c in top_sources)
        story.append(Paragraph(source_text, body_style))

    # ── Radio du jour ──
    if radio_topics:
        story.append(Spacer(1, 12))
        story.append(Paragraph("SUJETS RADIO", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#f59e0b"), spaceAfter=8))

        for radio in radio_topics[:8]:
            topics = radio.get("ai_topics") or []
            radio_name = radio.get("radio", "?")
            for topic in topics[:2]:
                t_title = topic.get("title", "")[:70]
                t_summary = topic.get("summary", "")[:100]
                t_gravity = int(topic.get("gravity", 0) * 100)
                radio_text = (
                    f'<font color="#f59e0b" size="8"><b>{t_gravity}%</b></font> '
                    f'<b>{t_title}</b> '
                    f'<font color="#64748b" size="8">({radio_name})</font><br/>'
                    f'<font color="#64748b" size="8">{t_summary}</font>'
                )
                story.append(Paragraph(radio_text, body_style))
                story.append(Spacer(1, 3))

    # ── Footer ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=6))
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'],
        fontSize=7, textColor=GRAY, alignment=TA_CENTER,
    )
    story.append(Paragraph(
        f"Veille Média Guadeloupe — Rapport généré le {now.strftime('%d/%m/%Y à %H:%M')} — "
        f"Données du {date_label}",
        footer_style,
    ))

    # Build
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(f"📄 Bilan PDF généré: {len(pdf_bytes)} bytes, "
                f"{total_articles} articles, {total_affairs} affaires")

    return pdf_bytes


def send_pdf_telegram(pdf_bytes: bytes, date_label: str) -> bool:
    """Envoie le PDF par Telegram en tant que document."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram non configuré — PDF non envoyé")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        boundary = "----VeillePDFBoundary"
        filename = f"bilan_veille_{date_label.replace('/', '-')}.pdf"
        caption = f"📊 Bilan Veille Média Guadeloupe — {date_label}"

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{chat_id}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8")

        body += pdf_bytes
        body += f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                logger.info("📨 Bilan PDF envoyé par Telegram")
                return True
            logger.warning(f"Telegram sendDocument erreur: {result}")
            return False

    except Exception as e:
        logger.error(f"Erreur envoi PDF Telegram: {e}")
        return False


def generate_and_send_daily_report(db) -> Dict[str, Any]:
    """Génère le bilan PDF et l'envoie par Telegram. Sauvegarde aussi en base."""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    date_label = yesterday.strftime("%d/%m/%Y")

    pdf_bytes = generate_daily_pdf(db)
    if not pdf_bytes:
        return {"success": False, "error": "Génération PDF échouée"}

    # Sauvegarder en base (pour téléchargement depuis le frontend)
    reports_col = db.get_collection("daily_reports")
    import bson
    report_doc = {
        "date": yesterday.strftime("%Y-%m-%d"),
        "generated_at": now,
        "pdf_size": len(pdf_bytes),
        "pdf_data": bson.Binary(pdf_bytes),
    }
    # Upsert — un seul rapport par jour
    reports_col.update_one(
        {"date": yesterday.strftime("%Y-%m-%d")},
        {"$set": report_doc},
        upsert=True,
    )

    # Nettoyage vieux rapports
    cutoff = now - timedelta(days=REPORT_RETENTION_DAYS)
    reports_col.delete_many({"generated_at": {"$lt": cutoff}})

    # Envoyer par Telegram
    telegram_ok = send_pdf_telegram(pdf_bytes, date_label)

    return {
        "success": True,
        "date": date_label,
        "pdf_size_kb": round(len(pdf_bytes) / 1024, 1),
        "telegram_sent": telegram_ok,
    }
