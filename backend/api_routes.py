# backend/api_routes.py
from fastapi import APIRouter, Query
from backend.db import get_db
from datetime import datetime, timedelta

router = APIRouter()  # PAS de prefix ici; le prefix /api est ajouté dans server.py

def serialize_doc(doc):
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if "scraped_at" in doc and isinstance(doc["scraped_at"], datetime):
        doc["scraped_at"] = doc["scraped_at"].isoformat()
    if "published_at" in doc and isinstance(doc["published_at"], datetime):
        doc["published_at"] = doc["published_at"].isoformat()
    if "captured_at" in doc and isinstance(doc["captured_at"], datetime):
        doc["captured_at"] = doc["captured_at"].isoformat()
    return doc

@router.get("/dashboard-stats")
def dashboard_stats():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        articles_count = db["articles_guadeloupe"].count_documents({"date": today})
        sources_count = len(db["articles_guadeloupe"].distinct("source", {"date": today}))
        trans_count = db["radio_transcriptions"].count_documents({"date": today})
    except Exception:
        articles_count, sources_count, trans_count = 0, 0, 0

    return {
        "success": True,
        "data": {
            "total": articles_count,           # alias attendu par le front
            "total_articles": articles_count,  # compat
            "total_sources": sources_count,
            "total_transcriptions": trans_count,
        },
    }

@router.get("/articles/sources")
def articles_sources():
    db = get_db()
    sources = db["articles_guadeloupe"].distinct("source")
    return {"success": True, "sources": sources}

@router.get("/articles")
def articles():
    db = get_db()
    arts = list(db["articles_guadeloupe"].find().sort("scraped_at", -1))
    return {"success": True, "articles": [serialize_doc(a) for a in arts]}

@router.get("/articles/filtered")
def filtered_articles(limit: int = 50, offset: int = 0, sort_by: str = "date_desc"):
    db = get_db()
    sort_order = -1 if sort_by == "date_desc" else 1
    arts = (
        db["articles_guadeloupe"]
        .find()
        .sort("scraped_at", sort_order)
        .skip(offset)
        .limit(limit)
    )
    return {"success": True, "articles": [serialize_doc(a) for a in arts]}

@router.get("/search")
def search(q: str = Query("")):
    db = get_db()
    results = list(
        db["articles_guadeloupe"].find({"title": {"$regex": q, "$options": "i"}}).limit(50)
    )
    return {"success": True, "query": q, "results": [serialize_doc(r) for r in results]}

@router.get("/search/suggestions")
def suggestions(q: str = Query("")):
    db = get_db()
    sugg = db["articles_guadeloupe"].distinct("title", {"title": {"$regex": q, "$options": "i"}})
    return {"success": True, "query": q, "suggestions": sugg}

@router.get("/comments")
def comments():
    db = get_db()
    coms = list(db["comments"].find().sort("created_at", -1))
    return {"success": True, "comments": [serialize_doc(c) for c in coms]}

@router.get("/digest")
def digest():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    articles = list(
        db["articles_guadeloupe"]
        .find({"date": today}, {"_id": 0})
        .sort("scraped_at", -1)
    )

    transcriptions = list(
        db["radio_transcriptions"]
        .find({"date": today}, {"_id": 0})
        .sort("captured_at", -1)
    )

    return {
        "success": True,
        "date": today,
        "counts": {"articles": len(articles), "transcriptions": len(transcriptions)},
        "articles": [serialize_doc(a) for a in articles],
        "transcriptions": [serialize_doc(t) for t in transcriptions],
    }

@router.get("/scheduler/status")
def scheduler_status():
    return {"success": True, "scheduler": "ok"}

# Déclenchement manuel du scraper (non bloquant)
@router.post("/articles/scrape-now")
def scrape_now():
    try:
        from backend.scraper_service import guadeloupe_scraper
    except Exception:
        return {"success": False, "message": "Scraper non disponible"}

    import threading
    threading.Thread(target=guadeloupe_scraper.run, daemon=True).start()
    return {"success": True, "message": "Scraping lancé en arrière-plan"}