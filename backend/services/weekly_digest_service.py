# backend/services/weekly_digest_service.py
"""
Bilan hebdomadaire des réseaux sociaux — digest texte envoyé sur Telegram.

Le bilan PNG complet est généré côté navigateur (canvas) ; il ne peut pas
être produit par un job backend. Ce service envoie à la place un digest
texte structuré (KPI de la semaine, post le plus vu, sentiment, reco IA),
réutilisant `get_decision_insights` et `telegram_service`.

Planifié le lundi matin via le scheduler ; déclenchable manuellement via
l'endpoint admin POST /api/social-stats/weekly-digest.
"""

import logging
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger("veille.weekly_digest")


def _fmt(n) -> str:
    """Format compact d'un nombre (1234 → 1.2k)."""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "0"
    if abs(n) >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(int(round(n)))


def build_weekly_digest_text(days: int = 7, db=None) -> str:
    """Construit le texte HTML du bilan hebdomadaire."""
    from backend.services.campaign_service import get_decision_insights

    data = get_decision_insights(days=days, db=db)
    totals = data.get("totals") or {}
    top = data.get("top_post") or {}
    what = data.get("what_works") or {}
    sentiment = data.get("sentiment") or {}
    recos = data.get("recommendations") or []

    date_label = datetime.now().strftime("%d/%m/%Y")
    lines = [
        f"📊 <b>Bilan réseaux sociaux — {days} derniers jours</b>",
        f"<i>{date_label}</i>",
        "",
        "<b>Vue d'ensemble</b>",
        f"  • {_fmt(totals.get('posts'))} publications",
        f"  • {_fmt(totals.get('views'))} vues · {_fmt(totals.get('likes'))} likes · {_fmt(totals.get('comments'))} commentaires",
        f"  • {_fmt(totals.get('engagement'))} interactions au total",
    ]

    if top.get("title"):
        plat = (top.get("platform") or "").capitalize()
        st = top.get("stats") or {}
        lines += [
            "",
            "🏆 <b>Post le plus vu</b>",
            f"  {top['title'][:120]}",
            f"  {plat} — {_fmt(st.get('views'))} vues · {_fmt(st.get('likes'))} likes · {_fmt(st.get('comments'))} comm.",
        ]

    # « Ce qui marche » (issu de la dernière analyse IA)
    bits = []
    if what.get("best_format"):
        bits.append(f"format <b>{what['best_format']}</b>")
    if what.get("best_platform"):
        bits.append(f"plateforme <b>{what['best_platform']}</b>")
    if what.get("best_day"):
        bits.append(f"jour <b>{what['best_day']}</b>")
    if what.get("best_time"):
        bits.append(f"créneau <b>{what['best_time']}</b>")
    if bits:
        lines += ["", "✅ <b>Ce qui marche</b>", "  " + " · ".join(bits)]

    # Sentiment global des commentaires
    glob = sentiment.get("global") if isinstance(sentiment, dict) else None
    if glob:
        emoji = "🟢" if "posit" in glob.lower() else "🔴" if ("nég" in glob.lower() or "neg" in glob.lower()) else "🟡"
        lines += ["", f"{emoji} <b>Sentiment</b> : {glob}"]

    if recos:
        lines += ["", "💡 <b>Recommandations</b>"]
        lines += [f"  {i}. {r}" for i, r in enumerate(recos[:3], 1)]

    return "\n".join(lines)


def send_weekly_digest(days: int = 7, db=None) -> Dict[str, Any]:
    """Génère et envoie le bilan hebdomadaire sur Telegram."""
    try:
        from backend.services.telegram_service import send_message, is_configured
    except ImportError:
        return {"ok": False, "error": "telegram_service indisponible"}

    if not is_configured():
        logger.warning("Telegram non configuré — bilan hebdo non envoyé")
        return {"ok": False, "error": "Telegram non configuré (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"}

    text = build_weekly_digest_text(days=days, db=db)
    ok = send_message(text)
    logger.info(f"📬 Bilan hebdo Telegram : {'envoyé' if ok else 'échec'}")
    return {"ok": bool(ok), "days": days, "sent": bool(ok)}
