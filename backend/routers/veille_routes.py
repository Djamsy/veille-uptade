"""
Routes API Veille — Briefing, Trending, Coverage, Watchlist

Prefix: /api/veille
"""

from fastapi import APIRouter, Query, HTTPException, Body
from typing import Optional
from backend.db import get_db
from backend.services.briefing_service import (
    generate_morning_briefing,
    detect_trending,
    analyze_coverage,
    get_watchlist,
    add_watchlist_keyword,
    remove_watchlist_keyword,
    send_telegram_briefing,
)

router = APIRouter()


# ── Briefing matinal ──────────────────────────────────────
@router.get("/briefing")
def briefing(hours: int = Query(24, ge=1, le=168)):
    """Briefing intelligence complet des dernières N heures.

    Inclut : top affaires, nouvelles affaires, radio, trending,
    couverture, watchlist hits, stats.
    """
    db = get_db()
    try:
        return generate_morning_briefing(db, hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur briefing: {e}")


@router.post("/briefing/telegram")
def send_briefing_telegram(hours: int = Query(24, ge=1, le=168)):
    """Envoie le briefing sur Telegram manuellement."""
    db = get_db()
    try:
        success = send_telegram_briefing(db, hours=hours)
        return {"success": success, "message": "Briefing envoyé" if success else "Telegram non configuré"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur envoi Telegram: {e}")


# ── Trending ──────────────────────────────────────────────
@router.get("/trending")
def trending(hours: int = Query(12, ge=1, le=72)):
    """Affaires en accélération (plus d'activité récente).

    Retourne les affaires triées par trend_score = velocity × sources × gravity.
    """
    db = get_db()
    try:
        return detect_trending(db, hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur trending: {e}")


# ── Couverture sources ────────────────────────────────────
@router.get("/coverage")
def coverage(days: int = Query(1, ge=1, le=30)):
    """Analyse de couverture médiatique : sources × thèmes × affaires.

    Identifie les trous de couverture (affaires graves couvertes par 1 seule source).
    """
    db = get_db()
    try:
        return analyze_coverage(db, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur coverage: {e}")


# ── Watchlist ─────────────────────────────────────────────
@router.get("/watchlist")
def watchlist_get():
    """Liste les mots-clés surveillés (watchlist active)."""
    db = get_db()
    try:
        items = get_watchlist(db)
        return {"success": True, "watchlist": items, "total": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur watchlist: {e}")


@router.post("/watchlist")
def watchlist_add(
    keyword: str = Body(..., embed=True),
    category: str = Body("general", embed=True),
    notify_telegram: bool = Body(True, embed=True),
    min_gravity: float = Body(0.0, embed=True),
):
    """Ajoute un mot-clé à la watchlist.

    Paramètres :
    - keyword : le mot-clé à surveiller
    - category : catégorie libre (ex: "politique", "environnement", "personnalité")
    - notify_telegram : envoyer une alerte Telegram si trouvé
    - min_gravity : gravité minimale pour déclencher (0.0 = tout)
    """
    db = get_db()
    try:
        result = add_watchlist_keyword(
            db, keyword, category=category,
            notify_telegram=notify_telegram, min_gravity=min_gravity,
        )
        if not result.get("success"):
            raise HTTPException(status_code=409, detail=result.get("error", "Erreur"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur ajout watchlist: {e}")


@router.delete("/watchlist")
def watchlist_remove(keyword: str = Query(...)):
    """Retire un mot-clé de la watchlist."""
    db = get_db()
    try:
        result = remove_watchlist_keyword(db, keyword)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Non trouvé"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suppression watchlist: {e}")


# ── Résumé rapide (endpoint léger pour le widget frontend) ──
@router.get("/quick-summary")
def quick_summary():
    """Résumé rapide pour widget dashboard (low-cost, pas de trending)."""
    db = get_db()
    from datetime import datetime, timedelta

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    cutoff = now - timedelta(hours=6)
    cutoff_iso = cutoff.isoformat()

    try:
        affairs_col = db["affairs"]
        articles_col = db["articles_guadeloupe"]
        radio_col = db["radio_transcriptions"]

        active_count = affairs_col.count_documents({"status": "active"})
        hot_count = affairs_col.count_documents({
            "status": "active", "gravity_score": {"$gte": 0.75}
        })

        articles_today = articles_col.count_documents({"date": today})
        radio_today = radio_col.count_documents({"date": today})

        # Dernière affaire créée
        latest = affairs_col.find_one(
            {"status": "active"},
            {"title": 1, "gravity_score": 1, "created_at": 1},
            sort=[("created_at", -1)],
        )

        return {
            "success": True,
            "summary": {
                "active_affairs": active_count,
                "hot_affairs": hot_count,
                "articles_today": articles_today,
                "radio_today": radio_today,
                "latest_affair": {
                    "title": latest.get("title", "") if latest else "",
                    "gravity": latest.get("gravity_score", 0) if latest else 0,
                } if latest else None,
                "timestamp": now.isoformat(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur résumé: {e}")
