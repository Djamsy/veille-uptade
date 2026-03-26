"""
Service de Briefing Matinal — Veille Média Guadeloupe

Génère un résumé intelligence pour le matin :
- Top affaires des dernières 24h
- Nouvelles affaires créées pendant la nuit
- Résumé des captures radio
- Tendances émergentes (affaires en accélération)
- Couverture par source (qui couvre quoi)
- Watchlist : alertes sur mots-clés surveillés

Endpoints :
  GET /api/veille/briefing         — Briefing complet
  GET /api/veille/trending         — Affaires en accélération
  GET /api/veille/coverage         — Matrice de couverture sources
  GET /api/veille/watchlist        — Alertes watchlist
  POST /api/veille/watchlist       — Ajouter un mot-clé
  DELETE /api/veille/watchlist     — Supprimer un mot-clé
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import Counter, defaultdict

from pymongo import DESCENDING

logger = logging.getLogger("veille.briefing")


# ================================================================
# BRIEFING MATINAL
# ================================================================

def generate_morning_briefing(db, hours: int = 24) -> Dict[str, Any]:
    """Génère le briefing intelligence des dernières `hours` heures.

    Retourne un dict structuré avec :
    - top_affairs : affaires les plus graves actives
    - new_affairs : créées dans la fenêtre
    - escalations : affaires dont la gravité a monté
    - radio_highlights : résumés radio récents
    - trending : affaires en accélération
    - coverage : matrice sources ↔ affaires
    - watchlist_hits : alertes sur mots-clés surveillés
    - stats : compteurs généraux
    """
    now = datetime.now()
    cutoff = now - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    today_str = now.strftime("%Y-%m-%d")

    affairs_col = db["affairs"]
    articles_col = db["articles_guadeloupe"]
    radio_col = db["radio_transcriptions"]
    timeline_col = db["affair_timeline"]

    # ── 1. Affaires actives triées par gravité ──
    active_affairs = list(
        affairs_col.find(
            {"status": {"$in": ["active", "stale"]}},
            {"title": 1, "gravity_score": 1, "theme": 1, "status": 1,
             "item_count": 1, "sources": 1, "elected": 1, "institutions": 1,
             "created_at": 1, "last_activity": 1, "bmg": 1, "commune": 1,
             "source_types": 1, "sentiment": 1, "priority": 1},
        ).sort("gravity_score", DESCENDING).limit(50)
    )

    # ── 2. Nouvelles affaires (créées dans la fenêtre) ──
    new_affairs = []
    for a in active_affairs:
        created = a.get("created_at")
        if created:
            try:
                if isinstance(created, str):
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                else:
                    created_dt = created.replace(tzinfo=None) if created.tzinfo else created
                if created_dt >= cutoff:
                    new_affairs.append(a)
            except Exception:
                pass

    # ── 3. Articles récents (pour stats + couverture) ──
    recent_articles = list(
        articles_col.find(
            {"$or": [
                {"scraped_at": {"$gte": cutoff}},
                {"scraped_at": {"$gte": cutoff_iso}},
                {"date": today_str},
            ]},
            {"title": 1, "source": 1, "theme": 1, "gravity_score": 1,
             "scraped_at": 1, "ai_summary": 1, "sentiment": 1, "commune": 1},
        ).sort("scraped_at", DESCENDING).limit(200)
    )

    # ── 4. Captures radio récentes ──
    radio_recent = list(
        radio_col.find(
            {"$or": [
                {"captured_at": {"$gte": cutoff}},
                {"captured_at": {"$gte": cutoff_iso}},
                {"date": today_str},
            ]},
            {"stream_name": 1, "section": 1, "topic_title": 1, "ai_summary": 1,
             "gpt_analysis": 1, "topic_summary": 1, "captured_at": 1,
             "gravity": 1, "duration_seconds": 1},
        ).sort("captured_at", DESCENDING).limit(30)
    )

    radio_highlights = []
    for r in radio_recent:
        summary = (r.get("ai_summary") or r.get("gpt_analysis")
                   or r.get("topic_summary") or "")
        if summary:
            radio_highlights.append({
                "stream": r.get("stream_name") or r.get("section", "Radio"),
                "summary": summary[:300],
                "topic": r.get("topic_title", ""),
                "gravity": r.get("gravity", 0),
                "captured_at": _iso(r.get("captured_at")),
            })

    # ── 5. Trending (affaires en accélération) ──
    trending = _detect_trending(affairs_col, timeline_col, cutoff)

    # ── 6. Couverture sources ──
    coverage = _build_coverage_matrix(active_affairs[:20], recent_articles)

    # ── 7. Watchlist ──
    watchlist_hits = _check_watchlist(db, recent_articles, radio_recent)

    # ── 8. Stats globales ──
    source_counts = Counter(a.get("source", "?") for a in recent_articles)
    theme_counts = Counter(a.get("theme", "autre") for a in recent_articles if a.get("theme"))
    sentiment_counts = Counter(a.get("sentiment", "neutre") for a in recent_articles if a.get("sentiment"))

    stats = {
        "period_hours": hours,
        "total_active_affairs": len(active_affairs),
        "new_affairs_count": len(new_affairs),
        "articles_count": len(recent_articles),
        "radio_captures_count": len(radio_recent),
        "sources_active": dict(source_counts),
        "themes_distribution": dict(theme_counts),
        "sentiment_distribution": dict(sentiment_counts),
        "generated_at": now.isoformat(),
    }

    # ── Sérialisation ──
    def _serialize(doc):
        d = dict(doc)
        if "_id" in d:
            d["_id"] = str(d["_id"])
        for k in ("created_at", "last_activity", "scraped_at", "captured_at", "updated_at"):
            if k in d and d[k] is not None:
                d[k] = _iso(d[k])
        return d

    return {
        "success": True,
        "briefing": {
            "generated_at": now.isoformat(),
            "period_hours": hours,
            "top_affairs": [_serialize(a) for a in active_affairs[:10]],
            "new_affairs": [_serialize(a) for a in new_affairs[:10]],
            "radio_highlights": radio_highlights[:10],
            "trending": trending,
            "coverage": coverage,
            "watchlist_hits": watchlist_hits,
            "stats": stats,
        },
    }


# ================================================================
# TRENDING — Détection des affaires en accélération
# ================================================================

def detect_trending(db, hours: int = 12) -> Dict[str, Any]:
    """Endpoint dédié trending."""
    affairs_col = db["affairs"]
    timeline_col = db["affair_timeline"]
    cutoff = datetime.now() - timedelta(hours=hours)
    trending = _detect_trending(affairs_col, timeline_col, cutoff)
    return {"success": True, "trending": trending, "period_hours": hours}


def _detect_trending(affairs_col, timeline_col, cutoff) -> List[Dict[str, Any]]:
    """Détecte les affaires qui accélèrent (plus d'activité récente que d'habitude).

    Métriques :
    - velocity : nombre d'événements timeline dans la fenêtre
    - source_spread : nombre de sources différentes
    - is_new : créée dans les dernières 6h
    """
    cutoff_iso = cutoff.isoformat()

    # Cherche les événements timeline récents
    recent_events = list(
        timeline_col.find(
            {"$or": [
                {"timestamp": {"$gte": cutoff}},
                {"timestamp": {"$gte": cutoff_iso}},
            ]},
            {"affair_id": 1, "event_type": 1, "timestamp": 1},
        ).limit(500)
    )

    # Compte les événements par affaire
    affair_velocity = Counter()
    affair_events = defaultdict(list)
    for evt in recent_events:
        aid = str(evt.get("affair_id", ""))
        if aid:
            affair_velocity[aid] += 1
            affair_events[aid].append(evt.get("event_type", ""))

    if not affair_velocity:
        return []

    # Top affaires par vélocité
    top_ids = [aid for aid, _ in affair_velocity.most_common(15)]

    from bson import ObjectId
    oids = []
    for aid in top_ids:
        try:
            oids.append(ObjectId(aid))
        except Exception:
            pass

    if not oids:
        return []

    affairs = {
        str(a["_id"]): a
        for a in affairs_col.find(
            {"_id": {"$in": oids}, "status": {"$in": ["active", "stale"]}},
            {"title": 1, "gravity_score": 1, "theme": 1, "sources": 1,
             "item_count": 1, "created_at": 1, "commune": 1, "priority": 1},
        )
    }

    trending = []
    now = datetime.now()
    for aid in top_ids:
        if aid not in affairs:
            continue
        a = affairs[aid]
        velocity = affair_velocity[aid]
        sources = a.get("sources", [])

        # Détermine si c'est nouveau (< 6h)
        is_new = False
        created = a.get("created_at")
        if created:
            try:
                if isinstance(created, str):
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
                else:
                    created_dt = created.replace(tzinfo=None) if created.tzinfo else created
                is_new = (now - created_dt).total_seconds() < 6 * 3600
            except Exception:
                pass

        # Score trending = velocity * source_spread * gravity_boost
        gravity = a.get("gravity_score", 0.5)
        source_spread = len(set(sources))
        trend_score = velocity * max(1, source_spread) * (0.5 + gravity)

        trending.append({
            "_id": aid,
            "title": a.get("title", ""),
            "gravity_score": gravity,
            "theme": a.get("theme", ""),
            "commune": a.get("commune", ""),
            "velocity": velocity,
            "source_spread": source_spread,
            "trend_score": round(trend_score, 2),
            "is_new": is_new,
            "event_types": dict(Counter(affair_events[aid])),
            "priority": a.get("priority", "minor"),
        })

    trending.sort(key=lambda x: x["trend_score"], reverse=True)
    return trending[:10]


# ================================================================
# COUVERTURE SOURCES
# ================================================================

def analyze_coverage(db, days: int = 1) -> Dict[str, Any]:
    """Analyse la couverture médiatique : quelles sources couvrent quoi."""
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    articles_col = db["articles_guadeloupe"]
    affairs_col = db["affairs"]

    recent = list(
        articles_col.find(
            {"$or": [
                {"scraped_at": {"$gte": cutoff}},
                {"scraped_at": {"$gte": cutoff_iso}},
                {"date": today},
            ]},
            {"source": 1, "theme": 1, "title": 1, "gravity_score": 1},
        ).limit(500)
    )

    active = list(
        affairs_col.find(
            {"status": "active"},
            {"title": 1, "sources": 1, "theme": 1, "gravity_score": 1, "item_count": 1},
        ).sort("gravity_score", DESCENDING).limit(20)
    )

    coverage = _build_coverage_matrix(active, recent)

    return {"success": True, "coverage": coverage, "period_days": days}


def _build_coverage_matrix(active_affairs, recent_articles) -> Dict[str, Any]:
    """Construit la matrice sources × thèmes + détecte les trous de couverture."""

    # Sources actives
    all_sources = set()
    for a in recent_articles:
        s = a.get("source")
        if s:
            all_sources.add(s)

    # Matrice source × thème
    source_themes = defaultdict(lambda: Counter())
    for a in recent_articles:
        s = a.get("source", "?")
        t = a.get("theme", "autre")
        source_themes[s][t] += 1

    # Affaires couvertes par source
    affair_sources = {}
    for aff in active_affairs:
        aid = str(aff.get("_id", ""))
        title = aff.get("title", "")
        sources = aff.get("sources", [])
        affair_sources[title[:80]] = {
            "sources": sources,
            "source_count": len(set(sources)),
            "gravity": aff.get("gravity_score", 0),
        }

    # Trous de couverture : affaires graves couvertes par 1 seule source
    gaps = []
    for aff in active_affairs:
        sources = set(aff.get("sources", []))
        gravity = aff.get("gravity_score", 0)
        if len(sources) <= 1 and gravity >= 0.5:
            missing = all_sources - sources
            gaps.append({
                "affair_title": aff.get("title", "")[:80],
                "gravity": gravity,
                "covered_by": list(sources),
                "missing_from": list(missing)[:5],
            })

    return {
        "sources_active": sorted(list(all_sources)),
        "source_theme_matrix": {s: dict(c) for s, c in source_themes.items()},
        "affair_coverage": affair_sources,
        "coverage_gaps": gaps[:10],
        "total_sources": len(all_sources),
        "total_articles": len(recent_articles),
    }


# ================================================================
# WATCHLIST — Surveillance par mots-clés
# ================================================================

def get_watchlist(db) -> List[Dict[str, Any]]:
    """Retourne la watchlist active."""
    col = db["watchlist"]
    items = list(col.find({"active": True}).sort("created_at", DESCENDING))
    for item in items:
        item["_id"] = str(item["_id"])
        if "created_at" in item:
            item["created_at"] = _iso(item["created_at"])
    return items


def add_watchlist_keyword(
    db, keyword: str, category: str = "general",
    notify_telegram: bool = True, min_gravity: float = 0.0
) -> Dict[str, Any]:
    """Ajoute un mot-clé à la watchlist."""
    col = db["watchlist"]

    # Vérifie doublon
    existing = col.find_one({"keyword": keyword.lower().strip(), "active": True})
    if existing:
        return {"success": False, "error": "Mot-clé déjà dans la watchlist"}

    doc = {
        "keyword": keyword.lower().strip(),
        "keyword_display": keyword.strip(),
        "category": category,
        "notify_telegram": notify_telegram,
        "min_gravity": min_gravity,
        "active": True,
        "hit_count": 0,
        "last_hit": None,
        "created_at": datetime.now(),
    }
    result = col.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    doc["created_at"] = doc["created_at"].isoformat()
    return {"success": True, "item": doc}


def remove_watchlist_keyword(db, keyword: str) -> Dict[str, Any]:
    """Désactive un mot-clé de la watchlist."""
    col = db["watchlist"]
    result = col.update_one(
        {"keyword": keyword.lower().strip(), "active": True},
        {"$set": {"active": False, "deactivated_at": datetime.now()}},
    )
    if result.modified_count > 0:
        return {"success": True, "message": f"'{keyword}' retiré de la watchlist"}
    return {"success": False, "error": "Mot-clé non trouvé"}


def _check_watchlist(db, recent_articles, recent_radio) -> List[Dict[str, Any]]:
    """Vérifie si des articles/radio récents matchent la watchlist."""
    col = db.get_collection("watchlist")
    try:
        watchlist = list(col.find({"active": True}))
    except Exception:
        return []

    if not watchlist:
        return []

    hits = []
    for item in watchlist:
        kw = item.get("keyword", "").lower()
        min_gravity = item.get("min_gravity", 0.0)
        if not kw:
            continue

        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        matched_articles = []
        matched_radio = []

        for art in recent_articles:
            title = art.get("title", "")
            summary = art.get("ai_summary", "")
            gravity = art.get("gravity_score", 0)
            if gravity < min_gravity:
                continue
            if pattern.search(title) or pattern.search(summary):
                matched_articles.append({
                    "title": title[:100],
                    "source": art.get("source", ""),
                    "gravity": gravity,
                })

        for r in recent_radio:
            summary = (r.get("ai_summary") or r.get("gpt_analysis")
                       or r.get("topic_summary") or "")
            topic = r.get("topic_title", "")
            if pattern.search(summary) or pattern.search(topic):
                matched_radio.append({
                    "stream": r.get("stream_name") or r.get("section", "Radio"),
                    "topic": topic[:100],
                })

        if matched_articles or matched_radio:
            hit = {
                "keyword": item.get("keyword_display", kw),
                "category": item.get("category", "general"),
                "articles_matched": len(matched_articles),
                "radio_matched": len(matched_radio),
                "top_articles": matched_articles[:5],
                "top_radio": matched_radio[:3],
                "notify_telegram": item.get("notify_telegram", True),
            }
            hits.append(hit)

            # Update hit count
            try:
                col.update_one(
                    {"_id": item["_id"]},
                    {"$inc": {"hit_count": len(matched_articles) + len(matched_radio)},
                     "$set": {"last_hit": datetime.now()}},
                )
            except Exception:
                pass

    return hits


# ================================================================
# TELEGRAM BRIEFING
# ================================================================

def send_telegram_briefing(db, hours: int = 24) -> bool:
    """Envoie le briefing matinal sur Telegram."""
    try:
        from backend.telegram_service import send_message, is_configured
        if not is_configured():
            return False
    except ImportError:
        try:
            from telegram_service import send_message, is_configured
            if not is_configured():
                return False
        except ImportError:
            return False

    briefing_data = generate_morning_briefing(db, hours)
    b = briefing_data.get("briefing", {})
    stats = b.get("stats", {})

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── Construction du message ──
    lines = [
        f"☀️ <b>BRIEFING MATINAL — {now}</b>",
        "",
        f"📊 <b>Vue d'ensemble ({stats.get('period_hours', 24)}h)</b>",
        f"  📰 {stats.get('articles_count', 0)} articles",
        f"  📻 {stats.get('radio_captures_count', 0)} captures radio",
        f"  🆕 {stats.get('new_affairs_count', 0)} nouvelles affaires",
        f"  📋 {stats.get('total_active_affairs', 0)} affaires actives",
    ]

    # Top affaires
    top = b.get("top_affairs", [])
    if top:
        lines.append("")
        lines.append("🔥 <b>Top Affaires</b>")
        for i, a in enumerate(top[:5], 1):
            g = a.get("gravity_score", 0)
            emoji = "🔴" if g >= 0.75 else "🟠" if g >= 0.55 else "🟡" if g >= 0.40 else "🟢"
            lines.append(f"  {i}. {emoji} {a.get('title', '?')[:70]} ({g:.0%})")

    # Trending
    trending = b.get("trending", [])
    if trending:
        lines.append("")
        lines.append("📈 <b>Tendances</b>")
        for t in trending[:3]:
            vel = t.get("velocity", 0)
            lines.append(f"  ⚡ {t.get('title', '')[:60]} (×{vel} activités)")

    # Radio
    radio = b.get("radio_highlights", [])
    if radio:
        lines.append("")
        lines.append("🎙️ <b>Radio</b>")
        for r in radio[:3]:
            lines.append(f"  📻 {r.get('stream', '')} — {r.get('summary', '')[:80]}")

    # Watchlist
    wl_hits = b.get("watchlist_hits", [])
    if wl_hits:
        lines.append("")
        lines.append("🔔 <b>Alertes Watchlist</b>")
        for w in wl_hits[:5]:
            count = w.get("articles_matched", 0) + w.get("radio_matched", 0)
            lines.append(f"  🏷 <b>{w.get('keyword', '')}</b> — {count} mentions")

    # Couverture gaps
    gaps = b.get("coverage", {}).get("coverage_gaps", [])
    if gaps:
        lines.append("")
        lines.append("⚠️ <b>Trous de couverture</b>")
        for g in gaps[:3]:
            lines.append(
                f"  📌 {g.get('affair_title', '')[:50]} "
                f"({g.get('gravity', 0):.0%}) — manque: {', '.join(g.get('missing_from', [])[:3])}"
            )

    text = "\n".join(lines)
    return send_message(text)


def send_watchlist_alerts_telegram(db, hits: List[Dict[str, Any]]) -> int:
    """Envoie les alertes watchlist individuellement sur Telegram."""
    try:
        from backend.telegram_service import send_message, is_configured
        if not is_configured():
            return 0
    except ImportError:
        try:
            from telegram_service import send_message, is_configured
            if not is_configured():
                return 0
        except ImportError:
            return 0

    sent = 0
    for hit in hits:
        if not hit.get("notify_telegram", True):
            continue
        kw = hit.get("keyword", "")
        articles = hit.get("top_articles", [])
        radio = hit.get("top_radio", [])

        lines = [f"🔔 <b>ALERTE WATCHLIST — {kw}</b>"]
        if articles:
            lines.append(f"\n📰 {len(articles)} article(s) :")
            for a in articles[:3]:
                lines.append(f"  • {a.get('title', '')[:70]} ({a.get('source', '')})")
        if radio:
            lines.append(f"\n📻 {len(radio)} capture(s) radio :")
            for r in radio[:2]:
                lines.append(f"  • {r.get('stream', '')} — {r.get('topic', '')[:60]}")

        if send_message("\n".join(lines)):
            sent += 1
    return sent


# ================================================================
# HELPERS
# ================================================================

def _iso(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)
