# backend/api_routes.py
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Any, Dict, List

from backend.db import get_db  # suppose un backend/db.py qui expose get_db()

router = APIRouter()  # le prefix /api est ajouté dans server.py

def _iso(dt: Any) -> Any:
    return dt.isoformat() if isinstance(dt, datetime) else dt

def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for k in ("scraped_at", "published_at", "captured_at", "created_at"):
        if k in out:
            out[k] = _iso(out[k])
    return out

@router.get("/dashboard-stats")
def dashboard_stats():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        articles_today = db["articles_guadeloupe"].count_documents({"date": today})
        sources_today = len(db["articles_guadeloupe"].distinct("source", {"date": today}))
        trans_today = db["radio_transcriptions"].count_documents({"date": today})
        total_articles = db["articles_guadeloupe"].count_documents({})
        total_transcriptions = db["radio_transcriptions"].count_documents({})
    except Exception:
        articles_today = sources_today = trans_today = 0
        total_articles = total_transcriptions = 0

    data = {
        "total": total_articles,
        "total_articles": total_articles,
        "total_sources": sources_today,
        "total_transcriptions": total_transcriptions,
    }

    # Alias plats pour compat front
    return {
        "success": True,
        "data": data,
        "articles_today": articles_today,
        "total_articles": total_articles,
        "active_sources": sources_today,
        "transcriptions_today": trans_today,
    }

@router.get("/articles/sources")
def articles_sources():
    db = get_db()
    try:
        sources = db["articles_guadeloupe"].distinct("source")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "sources": sources}

@router.get("/articles")
def articles(limit: int = 100):
    db = get_db()
    try:
        arts = list(db["articles_guadeloupe"].find().sort("scraped_at", -1).limit(limit))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "articles": [serialize_doc(a) for a in arts]}

@router.get("/articles/filtered")
def filtered_articles(
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "date_desc",
    date_start: str | None = None,
    date_end: str | None = None,
    source: str | None = None,
    search_text: str | None = None,
):
    db = get_db()

    # Filtre de base
    q: Dict[str, Any] = {}
    if date_start or date_end:
        q["date"] = {}
        if date_start:
            q["date"]["$gte"] = date_start
        if date_end:
            q["date"]["$lte"] = date_end
        if not q["date"]:
            del q["date"]
    if source and source != "all":
        q["source"] = source
    if search_text:
        q["$or"] = [
            {"title": {"$regex": search_text, "$options": "i"}},
            {"summary": {"$regex": search_text, "$options": "i"}},
            {"ai_summary": {"$regex": search_text, "$options": "i"}},
        ]

    sort_field = "scraped_at"
    sort_dir = -1
    if sort_by in ("date_asc",):
        sort_dir = 1
    elif sort_by in ("source_asc", "source_desc", "title_asc", "title_desc"):
        sort_field = "source" if sort_by.startswith("source") else "title"
        sort_dir = 1 if sort_by.endswith("_asc") else -1

    try:
        total = db["articles_guadeloupe"].count_documents(q)
        cursor = (
            db["articles_guadeloupe"]
            .find(q)
            .sort(sort_field, sort_dir)
            .skip(offset)
            .limit(limit)
        )
        arts = list(cursor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    returned = len(arts)
    has_more = (offset + returned) < total
    pagination = {
        "total": total,
        "offset": offset,
        "returned": returned,
        "hasMore": has_more,
    }

    return {
        "success": True,
        "articles": [serialize_doc(a) for a in arts],
        "pagination": pagination,
    }

@router.get("/search")
def search(q: str = Query("")):
    db = get_db()

    # Articles
    try:
        articles: List[Dict[str, Any]] = list(
            db["articles_guadeloupe"]
            .find({"title": {"$regex": q, "$options": "i"}})
            .sort("scraped_at", -1)
            .limit(50)
        )
    except Exception:
        articles = []

    # Réseaux sociaux (si collection présente)
    try:
        social_posts: List[Dict[str, Any]] = list(
            db["social_posts"]
            .find({"text": {"$regex": q, "$options": "i"}})
            .sort("created_at", -1)
            .limit(50)
        )
    except Exception:
        social_posts = []

    payload = {
        "success": True,
        "query": q,
        "searched_in": ["articles"] + (["social"] if social_posts else []),
        "articles": [serialize_doc(a) for a in articles],
        "social_posts": [serialize_doc(p) for p in social_posts],
        "total_results": len(articles) + len(social_posts),
    }
    return payload

@router.get("/search/suggestions")
def suggestions(q: str = Query("")):
    db = get_db()
    try:
        sugg = db["articles_guadeloupe"].distinct(
            "title", {"title": {"$regex": q, "$options": "i"}}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "query": q, "suggestions": sugg}

@router.get("/comments")
def comments():
    db = get_db()
    try:
        coms = list(db["comments"].find().sort("created_at", -1))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "comments": [serialize_doc(c) for c in coms]}

@router.get("/digest")
def digest():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        articles = list(
            db["articles_guadeloupe"]
            .find({"date": today})
            .sort("scraped_at", -1)
        )
        transcriptions = list(
            db["radio_transcriptions"]
            .find({"date": today})
            .sort("captured_at", -1)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return {
        "success": True,
        "date": today,
        "counts": {
            "articles": len(articles),
            "transcriptions": len(transcriptions),
        },
        "articles": [serialize_doc(a) for a in articles],
        "transcriptions": [serialize_doc(t) for t in transcriptions],
    }

@router.get("/scheduler/status")
def scheduler_status():
    return {"success": True, "scheduler": "ok"}

@router.post("/articles/scrape-now")
def scrape_now():
    # lancement non bloquant si service dispo
    try:
        from backend.scraper_service import guadeloupe_scraper  # type: ignore
    except Exception:
        return {"success": False, "message": "Scraper non disponible"}

    import threading
    threading.Thread(target=guadeloupe_scraper.run, daemon=True).start()
    return {"success": True, "message": "Scraping lancé en arrière-plan"}
