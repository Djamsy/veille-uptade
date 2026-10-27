# backend/services/email_service.py
"""Alertes e-mail via Brevo (API transactionnelle v3).

Configuration (variables d'environnement)
-----------------------------------------
    BREVO_API_KEY         clé API Brevo (Paramètres > SMTP & API > Clés API)
    BREVO_SENDER_EMAIL    expéditeur — DOIT être vérifié dans Brevo (Expéditeurs)
    BREVO_SENDER_NAME     nom affiché (défaut « Veille Média 971 »)
    EMAIL_ALERT_TO        destinataires, séparés par des virgules
    EMAIL_ARTICLE_ALERTS  all (défaut) | relevant | off
                            all      : tous les nouveaux articles
                            relevant : gravité >= EMAIL_MIN_GRAVITY (défaut 0.4)
    EMAIL_DAILY_LIMIT     plafond d'e-mails/jour, destinataires compris (défaut 250 ;
                          le plan gratuit Brevo autorise 300/jour)

Un seul e-mail par cycle de scraping (toutes les 5 min au plus), qui regroupe
les nouveaux articles : on reste sous le quota gratuit de Brevo.
L'envoi se fait dans un thread : il ne ralentit jamais le scraping.
"""
from __future__ import annotations

import html
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("email_service")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"

_quota_lock = threading.Lock()
_quota = {"day": None, "sent": 0}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def recipients() -> List[str]:
    return [e.strip() for e in _env("EMAIL_ALERT_TO").split(",") if "@" in e]


def is_configured() -> bool:
    return bool(_env("BREVO_API_KEY") and _env("BREVO_SENDER_EMAIL") and recipients())


def article_alerts_mode() -> str:
    mode = _env("EMAIL_ARTICLE_ALERTS", "all").lower()
    return mode if mode in ("all", "relevant", "off") else "all"


def status() -> Dict[str, Any]:
    """État de la configuration (sans jamais exposer la clé)."""
    return {
        "configured": is_configured(),
        "api_key_set": bool(_env("BREVO_API_KEY")),
        "sender": _env("BREVO_SENDER_EMAIL") or None,
        "recipients": recipients(),
        "mode": article_alerts_mode(),
        "daily_limit": _daily_limit(),
        "sent_today": _quota["sent"] if _quota["day"] == _today() else 0,
    }


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _daily_limit() -> int:
    try:
        return int(_env("EMAIL_DAILY_LIMIT", "250"))
    except ValueError:
        return 250


def _reserve_quota(n: int) -> bool:
    """Réserve n envois sur le quota du jour (UTC). False si le plafond serait dépassé."""
    with _quota_lock:
        if _quota["day"] != _today():
            _quota["day"], _quota["sent"] = _today(), 0
        if _quota["sent"] + n > _daily_limit():
            return False
        _quota["sent"] += n
        return True


def send_email(subject: str, html_content: str, text_content: Optional[str] = None,
               to: Optional[List[str]] = None) -> Dict[str, Any]:
    """Envoi synchrone via Brevo. Renvoie {"ok": bool, ...} (jamais d'exception)."""
    to = to or recipients()
    api_key, sender = _env("BREVO_API_KEY"), _env("BREVO_SENDER_EMAIL")
    if not (api_key and sender and to):
        return {"ok": False, "error": "Brevo non configuré (BREVO_API_KEY, BREVO_SENDER_EMAIL, EMAIL_ALERT_TO)"}
    if not _reserve_quota(len(to)):
        logger.warning("📧 Plafond quotidien d'e-mails atteint (%s) — envoi ignoré", _daily_limit())
        return {"ok": False, "error": "plafond quotidien atteint"}

    payload: Dict[str, Any] = {
        "sender": {"name": _env("BREVO_SENDER_NAME", "Veille Média 971"), "email": sender},
        "to": [{"email": e} for e in to],
        "subject": subject[:200],
        "htmlContent": html_content,
    }
    if text_content:
        payload["textContent"] = text_content
    try:
        r = requests.post(BREVO_URL, json=payload, timeout=15, headers={
            "api-key": api_key, "accept": "application/json", "content-type": "application/json",
        })
        if r.status_code in (200, 201, 202):
            return {"ok": True, "message_id": (r.json() or {}).get("messageId")}
        # Message d'erreur Brevo (ex. expéditeur non vérifié, clé invalide) — sans la clé
        detail = r.text[:300]
        logger.warning("📧 Brevo HTTP %s : %s", r.status_code, detail)
        return {"ok": False, "status": r.status_code, "error": detail}
    except Exception as e:
        logger.warning("📧 Brevo injoignable : %s", e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def send_email_async(subject: str, html_content: str, text_content: Optional[str] = None) -> None:
    threading.Thread(target=send_email, args=(subject, html_content, text_content),
                     name="brevo-send", daemon=True).start()


def send_startup_email() -> Dict[str, Any]:
    """E-mail « service démarré » envoyé à chaque démarrage (donc à chaque déploiement).

    Sert de test de bout en bout de Brevo : le résultat est écrit dans les logs.
    Désactivable avec EMAIL_STARTUP_NOTIFY=0.
    """
    if _env("EMAIL_STARTUP_NOTIFY", "1").lower() in ("0", "false", "no", "off"):
        return {"ok": False, "skipped": "EMAIL_STARTUP_NOTIFY=0"}
    if not is_configured():
        logger.info("📧 Brevo non configuré — pas d'e-mail de démarrage "
                    "(BREVO_API_KEY, BREVO_SENDER_EMAIL, EMAIL_ALERT_TO)")
        return {"ok": False, "skipped": "non configuré"}
    try:
        from backend.db import get_failover_status
        db_state = get_failover_status()
        cluster = "secours (mode dégradé)" if db_state.get("degraded") else "principal"
    except Exception:
        cluster = "inconnu"
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    mode = article_alerts_mode()
    html_content = (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto">'
        '<h2 style="font-size:18px;color:#111827">✅ Veille Média 971 a démarré</h2>'
        f'<p style="font-size:14px;color:#374151">Démarrage le {html.escape(now)}.</p>'
        '<ul style="font-size:14px;color:#374151">'
        f'<li>Base de données : cluster {html.escape(cluster)}</li>'
        f'<li>Alertes articles par e-mail : {html.escape(mode)}</li>'
        f'<li>Destinataires : {html.escape(", ".join(recipients()))}</li>'
        '</ul>'
        '<p style="font-size:11px;color:#9ca3af">Cet e-mail confirme que les alertes Brevo fonctionnent. '
        'Pour ne plus le recevoir à chaque déploiement : EMAIL_STARTUP_NOTIFY=0.</p></div>'
    )
    result = send_email("✅ Veille Média 971 a démarré", html_content,
                        f"Veille Média 971 a démarré le {now}. Cluster : {cluster}. Alertes : {mode}.")
    if result.get("ok"):
        logger.info("📧 E-mail de démarrage envoyé via Brevo à %s", ", ".join(recipients()))
    else:
        logger.error("📧 E-mail de démarrage NON envoyé — Brevo : %s", result.get("error"))
    return result


# ── Alertes articles ─────────────────────────────────────────────────────────

def _relevant(article: Dict[str, Any]) -> bool:
    try:
        min_g = float(_env("EMAIL_MIN_GRAVITY", "0.4"))
    except ValueError:
        min_g = 0.4
    try:
        return float(article.get("gravity_score") or 0) >= min_g
    except (TypeError, ValueError):
        return False


def build_articles_email(articles: List[Dict[str, Any]]) -> Dict[str, str]:
    """Sujet + HTML + texte d'un e-mail regroupant de nouveaux articles."""
    esc = lambda v: html.escape(str(v or ""))  # noqa: E731
    sources = sorted({str(a.get("source") or "?") for a in articles})
    n = len(articles)
    subject = (f"📰 {articles[0].get('title', 'Nouvel article')}" if n == 1
               else f"📰 {n} nouveaux articles — {', '.join(sources)}")

    rows, lines = [], []
    for a in articles:
        url = a.get("url") or ""
        try:
            gravity = f"{float(a.get('gravity_score') or 0):.0%}"
        except (TypeError, ValueError):
            gravity = "—"
        chapo = str(a.get("ai_summary") or a.get("content") or "")[:300]
        badge = (' <span style="font-size:11px;color:#6b7280;border:1px solid #d1d5db;'
                 'border-radius:3px;padding:0 4px">Réservé abonnés</span>') if a.get("content_restricted") else ""
        title_html = (f'<a href="{esc(url)}" style="color:#0f766e;text-decoration:none">{esc(a.get("title"))}</a>'
                      if url else esc(a.get("title")))
        rows.append(
            '<tr><td style="padding:14px 0;border-bottom:1px solid #e5e7eb">'
            f'<div style="font-size:12px;color:#6b7280">{esc(a.get("source"))} · {esc(a.get("theme") or "—")} '
            f'· gravité {gravity}{badge}</div>'
            f'<div style="font-size:16px;font-weight:600;margin:4px 0">{title_html}</div>'
            + (f'<div style="font-size:13px;color:#374151">{esc(chapo)}</div>' if chapo else "")
            + (f'<div style="font-size:12px;margin-top:4px"><a href="{esc(url)}" style="color:#0f766e">{esc(url)}</a></div>' if url else "")
            + "</td></tr>"
        )
        lines.append(f"- [{a.get('source')}] {a.get('title')}\n  {url}")

    html_content = (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto">'
        f'<h2 style="font-size:18px;color:#111827">Veille Média 971 — {n} nouvel{"s" if n > 1 else ""} article{"s" if n > 1 else ""}</h2>'
        f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        '<p style="font-size:11px;color:#9ca3af;margin-top:16px">Alerte automatique — Veille Média Guadeloupe</p>'
        "</div>"
    )
    return {"subject": subject, "html": html_content, "text": "\n".join(lines)}


def notify_new_articles(articles: List[Dict[str, Any]]) -> bool:
    """Un e-mail regroupant les nouveaux articles d'un cycle de scraping (non bloquant)."""
    if not articles or not is_configured():
        return False
    mode = article_alerts_mode()
    if mode == "off":
        return False
    selected = articles if mode == "all" else [a for a in articles if _relevant(a)]
    # Anti-doublon : une annonce déjà envoyée par e-mail (titre normalisé) n'est pas renvoyée
    from backend.services.alert_dedup import claim
    selected = [a for a in selected if claim("email_article", a.get("title", ""), str(a.get("url", "")))]
    if not selected:
        return False
    mail = build_articles_email(selected)
    send_email_async(mail["subject"], mail["html"], mail["text"])
    logger.info("📧 E-mail d'alerte en cours d'envoi (%s article(s))", len(selected))
    return True
