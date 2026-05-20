"""
Service de notifications Telegram pour Veille Média Guadeloupe.

Configuration requise (variables d'environnement) :
  TELEGRAM_BOT_TOKEN  — token du bot créé via @BotFather
  TELEGRAM_CHAT_ID    — ID du chat/groupe où envoyer les notifs

Pour obtenir le chat_id :
  1. Envoie un message au bot
  2. Appelle https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Récupère le chat.id dans la réponse
"""

import os
import logging
import urllib.request
import urllib.parse
import json
import hashlib
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from collections import OrderedDict

logger = logging.getLogger("veille.telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Cache anti-doublons ──────────────────────────────────
# Garde en mémoire les hashes des notifications envoyées récemment.
# Taille max : 500 entrées (les plus anciennes sont éjectées).
_SENT_CACHE_MAX = 500
_sent_cache: OrderedDict = OrderedDict()  # hash → timestamp
_sent_lock = threading.Lock()


def _make_alert_hash(alert_type: str, identifier: str) -> str:
    """Crée un hash unique pour une notification (type + identifiant)."""
    raw = f"{alert_type}::{identifier}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _is_already_sent(alert_type: str, identifier: str) -> bool:
    """Vérifie si cette notification a déjà été envoyée récemment."""
    h = _make_alert_hash(alert_type, identifier)
    with _sent_lock:
        return h in _sent_cache


def _mark_as_sent(alert_type: str, identifier: str):
    """Marque une notification comme envoyée."""
    h = _make_alert_hash(alert_type, identifier)
    with _sent_lock:
        _sent_cache[h] = datetime.utcnow()
        # Éjecter les plus anciennes si le cache dépasse la taille max
        while len(_sent_cache) > _SENT_CACHE_MAX:
            _sent_cache.popitem(last=False)


def is_configured() -> bool:
    """Vérifie si Telegram est configuré."""
    return bool(BOT_TOKEN and CHAT_ID)


def send_message(text: str, parse_mode: str = "HTML", disable_preview: bool = True) -> bool:
    """Envoie un message Telegram. Retourne True si succès."""
    if not is_configured():
        logger.debug("Telegram non configuré — notification ignorée")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return True
            logger.warning(f"Telegram API erreur: {result}")
            return False
    except Exception as e:
        logger.warning(f"Telegram envoi échoué: {e}")
        return False


# ── Templates de notification ──────────────────────────────

def _gravity_emoji(gravity: float) -> str:
    if gravity >= 0.80:
        return "🔴"
    elif gravity >= 0.60:
        return "🟠"
    elif gravity >= 0.45:
        return "🟡"
    return "🟢"


def _priority_label(gravity: float) -> str:
    if gravity >= 0.75:
        return "CRITIQUE"
    elif gravity >= 0.55:
        return "IMPORTANT"
    elif gravity >= 0.40:
        return "À SUIVRE"
    return "MINEUR"


def notify_new_affair(affair: Dict[str, Any], source_type: str = "article") -> bool:
    """Notifie la création d'une nouvelle affaire."""
    # ── Anti-doublon : vérifier si déjà envoyé ──
    affair_id = str(affair.get("_id", affair.get("title", "")))
    if _is_already_sent("new_affair", affair_id):
        logger.debug(f"🔇 Notification doublon ignorée: new_affair {affair_id[:20]}")
        return False

    title = affair.get("title", "Sans titre")[:150]
    description = affair.get("description", "")[:200]
    gravity = affair.get("gravity_score", 0)
    theme = affair.get("theme", "")
    elected = affair.get("elected", []) or []
    institutions = affair.get("institutions", []) or []
    sources = affair.get("sources", []) or []

    emoji = _gravity_emoji(gravity)
    priority = _priority_label(gravity)

    # Icône source
    source_icon = {"article": "📰", "transcription": "📻", "social": "📱"}.get(source_type, "📄")

    entities_str = ", ".join((elected + institutions)[:5]) or "—"
    source_str = ", ".join(sources[:2]) or "—"

    text = (
        f"{emoji} <b>NOUVELLE AFFAIRE — {priority}</b>\n\n"
        f"<b>{title}</b>\n"
    )
    if description:
        text += f"{description}\n"
    text += (
        f"\n"
        f"{source_icon} Source : {source_str}\n"
        f"📊 Gravité : {gravity:.0%}\n"
        f"🏷 Thème : {theme}\n"
        f"👤 Entités : {entities_str}\n"
    )

    result = send_message(text)
    if result:
        _mark_as_sent("new_affair", affair_id)
    return result


def notify_affair_escalation(affair: Dict[str, Any], old_gravity: float, new_gravity: float) -> bool:
    """Notifie quand une affaire monte en gravité."""
    if new_gravity - old_gravity < 0.10:
        return False  # Pas assez significatif

    title = affair.get("title", "Sans titre")[:150]
    emoji = _gravity_emoji(new_gravity)
    item_count = affair.get("item_count", 0)

    text = (
        f"{emoji} <b>ESCALADE</b>\n\n"
        f"<b>{title}</b>\n"
        f"📊 Gravité : {old_gravity:.0%} → {new_gravity:.0%}\n"
        f"📎 {item_count} sources\n"
    )

    return send_message(text)


def notify_daily_summary(
    affairs_created: int,
    affairs_total: int,
    articles_enriched: int,
    top_affairs: list,
) -> bool:
    """Résumé quotidien de la veille."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    text = (
        f"📋 <b>RÉSUMÉ VEILLE — {now}</b>\n\n"
        f"🆕 {affairs_created} nouvelles affaires\n"
        f"📊 {affairs_total} affaires actives\n"
        f"📰 {articles_enriched} articles enrichis\n"
    )

    if top_affairs:
        text += "\n<b>Top affaires :</b>\n"
        for i, aff in enumerate(top_affairs[:5], 1):
            g = aff.get("gravity_score", 0)
            emoji = _gravity_emoji(g)
            text += f"{i}. {emoji} {aff.get('title', '?')[:80]} ({g:.0%})\n"

    return send_message(text)


def notify_pipeline_result(
    articles_scraped: int = 0,
    articles_enriched: int = 0,
    affairs_created: int = 0,
    affairs_merged: int = 0,
    affairs_ignored: int = 0,
    radio_created: int = 0,
) -> bool:
    """Résumé envoyé après chaque exécution du pipeline (toutes les 5 min)."""
    if not is_configured():
        return False

    # Ne rien envoyer si rien ne s'est passé
    total_activity = articles_scraped + articles_enriched + affairs_created + affairs_merged + radio_created
    if total_activity == 0:
        return False

    now = datetime.now().strftime("%H:%M")

    lines = [f"⚡ <b>Pipeline {now}</b>"]

    if articles_scraped > 0:
        lines.append(f"📰 {articles_scraped} articles scrapés")
    if articles_enriched > 0:
        lines.append(f"🧠 {articles_enriched} enrichis")
    if affairs_created > 0:
        lines.append(f"🆕 {affairs_created} affaires créées")
    if affairs_merged > 0:
        lines.append(f"🔗 {affairs_merged} fusionnées")
    if radio_created > 0:
        lines.append(f"📻 {radio_created} affaires radio")
    if affairs_ignored > 0:
        lines.append(f"🌍 {affairs_ignored} hors Guadeloupe ignorées")

    return send_message("\n".join(lines))


# ── Notification nouvel article département ──────────────

def notify_new_article(article: Dict[str, Any]) -> bool:
    """Notifie un nouvel article pertinent (département, affaires, institutions)."""
    if not is_configured():
        return False

    # ── Anti-doublon ──
    article_id = str(article.get("_id", article.get("url", article.get("title", ""))))
    if _is_already_sent("new_article", article_id):
        logger.debug(f"🔇 Notification doublon ignorée: new_article {article_id[:30]}")
        return False

    title = article.get("title", "Sans titre")[:150]
    source = article.get("source", "?")
    theme = article.get("theme", "")
    gravity = article.get("gravity_score", 0)
    sentiment = article.get("sentiment", "")
    elected = article.get("elected", []) or []
    institutions = article.get("institutions", []) or []
    url = article.get("url", "")
    summary = article.get("ai_summary", "")

    emoji = _gravity_emoji(gravity)
    entities = ", ".join((elected + institutions)[:4]) or "—"
    sentiment_emoji = {"positif": "🟢", "négatif": "🔴", "neutre": "⚪", "mitigé": "🟡"}.get(sentiment, "⚪")

    text = (
        f"📰 <b>NOUVEL ARTICLE</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"📡 {source}\n"
        f"{emoji} Gravité : {gravity:.0%}\n"
        f"{sentiment_emoji} Sentiment : {sentiment or '—'}\n"
        f"🏷 {theme}\n"
        f"👤 {entities}\n"
    )

    if summary:
        text += f"\n📝 <i>{summary[:200]}</i>\n"

    if url:
        text += f"\n🔗 <a href=\"{url}\">Lire l'article</a>"

    result = send_message(text)
    if result:
        _mark_as_sent("new_article", article_id)
    return result


# ── Notification résumé radio ────────────────────────────

def notify_radio_summary(transcription: Dict[str, Any]) -> bool:
    """Notifie un résumé de transcription radio."""
    if not is_configured():
        return False

    # ── Anti-doublon ──
    radio_id = str(transcription.get("_id", transcription.get("captured_at", "")))
    if _is_already_sent("radio", radio_id):
        logger.debug(f"🔇 Notification doublon ignorée: radio {radio_id[:20]}")
        return False

    stream_name = transcription.get("stream_name", "") or transcription.get("section", "Radio")
    summary = (transcription.get("ai_summary", "") or transcription.get("gpt_analysis", "")
               or transcription.get("topic_summary", ""))
    # Fallback : texte brut tronqué si pas de résumé IA
    if not summary:
        raw = transcription.get("text", "") or transcription.get("transcription", "")
        if raw and len(raw) > 30:
            summary = raw[:400] + ("..." if len(raw) > 400 else "")
    topic = transcription.get("topic_title", "")
    gravity = transcription.get("gravity", 0) or 0
    captured_at = transcription.get("captured_at", "")

    if not summary:
        return False  # Rien à envoyer

    emoji = _gravity_emoji(gravity) if gravity else "📻"

    text = f"🎙️ <b>RADIO — {stream_name}</b>\n\n"

    if topic:
        text += f"📌 <b>{topic[:100]}</b>\n\n"

    text += f"{summary[:500]}\n"

    if gravity:
        text += f"\n{emoji} Gravité : {gravity:.0%}"

    if captured_at:
        try:
            from datetime import datetime as dt
            t = dt.fromisoformat(captured_at.replace("Z", "+00:00"))
            text += f"\n⏰ {t.strftime('%H:%M')}"
        except Exception:
            pass

    result = send_message(text)
    if result:
        _mark_as_sent("radio", radio_id)
    return result


# ── Endpoint de test ──────────────────────────────────────

def test_connection() -> Dict[str, Any]:
    """Teste la connexion Telegram."""
    if not is_configured():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID non configuré"}

    success = send_message("✅ <b>Veille Média Guadeloupe</b> — Connexion Telegram OK !")
    return {"ok": success, "bot_token_set": bool(BOT_TOKEN), "chat_id_set": bool(CHAT_ID)}


# ── Notifications Fusion / Déliage ──────────────────────────

def notify_affair_merged(
    keep_affair: Dict[str, Any],
    absorbed_affair: Dict[str, Any],
    merge_type: str = "auto",
    reason: str = "",
    by: str = "",
) -> bool:
    """Notifie quand une affaire en absorbe une autre (fusion).

    merge_type: "auto" (système), "manual" (admin), "ia" (dédup IA), "stale" (stale→active)
    """
    if not is_configured():
        return False

    # ── Anti-doublon ──
    merge_id = f"{keep_affair.get('_id', '')}_{absorbed_affair.get('_id', '')}"
    if _is_already_sent("merged", merge_id):
        logger.debug(f"🔇 Notification doublon ignorée: merged {merge_id[:30]}")
        return False

    keep_title = keep_affair.get("title", "Sans titre")[:120]
    absorbed_title = absorbed_affair.get("title", "Sans titre")[:120]
    keep_gravity = keep_affair.get("gravity_score", 0)
    absorbed_gravity = absorbed_affair.get("gravity_score", 0)
    keep_items = keep_affair.get("item_count", 0)
    absorbed_items = absorbed_affair.get("item_count", 0)

    emoji = _gravity_emoji(max(keep_gravity, absorbed_gravity))

    type_labels = {
        "auto": "🤖 Auto",
        "manual": "👤 Manuelle",
        "ia": "🧠 Dédup IA",
        "stale": "🔄 Stale→Active",
        "inter": "🔀 Inter-affaires",
    }
    type_label = type_labels.get(merge_type, merge_type)

    text = (
        f"🔗 <b>FUSION — {type_label}</b>\n\n"
        f"{emoji} <b>{keep_title}</b>\n"
        f"    ← absorbe ←\n"
        f"📄 <i>{absorbed_title}</i>\n\n"
        f"📊 Gravité : {keep_gravity:.0%} (absorbée: {absorbed_gravity:.0%})\n"
        f"📎 Items : {keep_items} + {absorbed_items}\n"
    )

    if reason:
        text += f"💬 Raison : {reason}\n"
    if by:
        text += f"👤 Par : {by}\n"

    result = send_message(text)
    if result:
        _mark_as_sent("merged", merge_id)
    return result


def notify_affair_unlinked(
    affair: Dict[str, Any],
    article_title: str = "",
    article_source: str = "",
    unlink_type: str = "manual",
    reason: str = "",
    by: str = "",
) -> bool:
    """Notifie quand un article est délié d'une affaire.

    unlink_type: "manual" (admin), "auto" (vérification GPT), "cleanup" (nettoyage)
    """
    if not is_configured():
        return False

    affair_title = affair.get("title", "Sans titre")[:120]
    gravity = affair.get("gravity_score", 0)
    remaining_items = affair.get("item_count", 0)

    type_labels = {
        "manual": "👤 Manuelle",
        "auto": "🤖 Vérification IA",
        "cleanup": "🧹 Nettoyage",
    }
    type_label = type_labels.get(unlink_type, unlink_type)

    text = (
        f"✂️ <b>DÉLIAGE — {type_label}</b>\n\n"
        f"📄 <i>{article_title or 'Article inconnu'}</i>"
    )
    if article_source:
        text += f" ({article_source})"
    text += (
        f"\n    délié de →\n"
        f"📋 <b>{affair_title}</b>\n\n"
        f"📊 Gravité affaire : {gravity:.0%}\n"
        f"📎 Items restants : {remaining_items}\n"
    )

    if reason:
        text += f"💬 Raison : {reason}\n"
    if by:
        text += f"👤 Par : {by}\n"

    return send_message(text)


# ── Notification résumé fusions (anti boule de neige) ──────

def notify_propagation_spike(affair: Dict[str, Any]) -> bool:
    """Alerte quand une affaire entre en phase de viralisation (spike propagation détecté).

    Spike = velocity_j7 > 3× velocity_j30 et velocity_j7 > 1 article/j.
    Anti-doublon : une seule alerte par affaire par fenêtre de 6h.
    """
    if not is_configured():
        return False

    affair_id = str(affair.get("_id", ""))
    # Anti-doublon : une alerte par affaire toutes les 6h
    cache_key = f"spike_6h_{affair_id}"
    if _is_already_sent("spike", cache_key):
        return False

    title    = affair.get("title", "Sans titre")[:120]
    gravity  = affair.get("gravity_score", 0)
    prop     = affair.get("propagation") or {}
    velocity = prop.get("velocity") or {}
    vecteurs = prop.get("vecteurs") or {}
    score    = prop.get("score", 0)
    v_j7     = velocity.get("j7", 0)
    v_j30    = velocity.get("j30", 0)
    nb_src   = prop.get("nb_sources", 0)

    vecteurs_str = " · ".join(
        f"{k} ({v})" for k, v in vecteurs.items() if v > 0
    ) or "presse"

    text = (
        f"🔥 <b>VIRALISATION DÉTECTÉE</b>\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"📈 Vélocité : <b>{v_j7:.1f} art/j</b> (vs {v_j30:.1f} j30)\n"
        f"📡 Vecteurs : {vecteurs_str}\n"
        f"🗞️ Sources : {nb_src} distinctes\n"
        f"📊 Score propagation : {score:.0%}\n"
        f"⚡ Gravité : {gravity:.0%}\n\n"
        f"Cette affaire s'emballe — à surveiller en priorité."
    )

    sent = send_message(text)
    if sent:
        _mark_as_sent("spike", cache_key)
    return sent


def notify_snowball_alert(
    affair: Dict[str, Any],
    merge_count_recent: int,
    threshold: int = 5,
) -> bool:
    """Alerte quand une affaire accumule trop de fusions récentes (effet boule de neige).
    Permet de détecter les affaires qui absorbent tout."""
    if not is_configured():
        return False

    title = affair.get("title", "Sans titre")[:120]
    gravity = affair.get("gravity_score", 0)
    item_count = affair.get("item_count", 0)

    text = (
        f"⚠️ <b>ALERTE BOULE DE NEIGE</b>\n\n"
        f"📋 <b>{title}</b>\n\n"
        f"🔗 {merge_count_recent} fusions récentes (seuil: {threshold})\n"
        f"📎 {item_count} items au total\n"
        f"📊 Gravité : {gravity:.0%}\n\n"
        f"⚠️ Cette affaire absorbe beaucoup de contenu.\n"
        f"Vérifiez qu'il ne s'agit pas d'un thème trop large."
    )

    return send_message(text)
