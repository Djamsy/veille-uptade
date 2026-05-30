# backend/api_routes.py
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.db import get_db, ensure_api_indexes, get_cached_stats

router = APIRouter()  # le prefix /api est ajouté dans server.py

# ── Initialisation lazy des index au premier appel ──
_init_done = False

def _init():
    global _init_done
    if not _init_done:
        ensure_api_indexes()
        _init_done = True


# ------- Helpers -------
def _iso(dt: Any) -> Any:
    return dt.isoformat() if isinstance(dt, datetime) else dt


# Projection minimale pour les listes d'articles (exclut le contenu lourd)
_ARTICLE_LIST_PROJECTION = {
    "_id": 1, "title": 1, "source": 1, "url": 1, "date": 1,
    "scraped_at": 1, "published_at": 1, "ai_summary": 1,
    "theme": 1, "gravity_score": 1, "commune": 1, "image_url": 1,
}


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for k in ("scraped_at", "published_at", "captured_at", "created_at", "updated_at"):
        if k in out and out[k] is not None:
            out[k] = _iso(out[k])
    return out


# ------- Endpoints -------
@router.get("/dashboard-stats")
def dashboard_stats():
    _init()
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        articles_today = db["articles_guadeloupe"].count_documents({"date": today})
        sources_today = len(
            db["articles_guadeloupe"].distinct("source", {"date": today})
        )
        trans_today = db["radio_transcriptions"].count_documents({"date": today})

        # estimated_document_count() utilise les métadonnées de la collection
        # au lieu de scanner toute la collection — O(1) vs O(n)
        total_articles = get_cached_stats(
            "total_articles",
            lambda: db["articles_guadeloupe"].estimated_document_count(),
            ttl=120,
        )
        total_transcriptions = get_cached_stats(
            "total_transcriptions",
            lambda: db["radio_transcriptions"].estimated_document_count(),
            ttl=120,
        )
    except Exception:
        articles_today = sources_today = trans_today = 0
        total_articles = total_transcriptions = 0

    data = {
        "total": total_articles,
        "total_articles": total_articles,
        "total_sources": sources_today,
        "total_transcriptions": total_transcriptions,
    }

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
    _init()
    db = get_db()
    try:
        # Cache la liste des sources (change rarement)
        sources = get_cached_stats(
            "article_sources",
            lambda: db["articles_guadeloupe"].distinct("source"),
            ttl=300,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "sources": sources}


@router.get("/articles")
def articles(limit: int = Query(100, ge=1, le=1000)):
    _init()
    db = get_db()
    try:
        arts = list(
            db["articles_guadeloupe"]
            .find({}, _ARTICLE_LIST_PROJECTION)
            .sort("scraped_at", -1)
            .limit(limit)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "articles": [serialize_doc(a) for a in arts]}


@router.get("/articles/filtered")
def filtered_articles(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("date_desc"),
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    source: Optional[str] = None,
    search_text: Optional[str] = None,
):
    """
    sort_by: date_desc|date_asc|source_asc|source_desc|title_asc|title_desc
    """
    _init()
    db = get_db()

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

    # ── Recherche texte optimisée ──
    # Utilise $text (index inversé) quand disponible, fallback sur $regex
    use_text_search = False
    if search_text:
        try:
            # Tente une recherche $text (beaucoup plus rapide avec l'index)
            text_q = {**q, "$text": {"$search": search_text}}
            # Teste que le text index existe en faisant un count rapide
            db["articles_guadeloupe"].find(text_q).limit(1).next()
            q = text_q
            use_text_search = True
        except StopIteration:
            # Aucun résultat mais l'index existe
            q = text_q
            use_text_search = True
        except Exception:
            # Pas de text index ou erreur → fallback regex
            q["$or"] = [
                {"title": {"$regex": search_text, "$options": "i"}},
                {"summary": {"$regex": search_text, "$options": "i"}},
                {"ai_summary": {"$regex": search_text, "$options": "i"}},
            ]

    # Tri
    sort_field = "scraped_at"
    sort_dir = -1
    if sort_by in ("date_asc", "date_desc"):
        sort_field = "scraped_at"
        sort_dir = 1 if sort_by.endswith("_asc") else -1
    elif sort_by in ("source_asc", "source_desc", "title_asc", "title_desc"):
        sort_field = "source" if sort_by.startswith("source") else "title"
        sort_dir = 1 if sort_by.endswith("_asc") else -1

    # Si on utilise $text, on peut trier par pertinence
    sort_spec = [(sort_field, sort_dir)]
    projection = _ARTICLE_LIST_PROJECTION.copy()
    if use_text_search and sort_by == "date_desc":
        # Ajoute le score de pertinence
        projection["_text_score"] = {"$meta": "textScore"}

    try:
        total = db["articles_guadeloupe"].count_documents(q)
        cursor = (
            db["articles_guadeloupe"]
            .find(q, projection)
            .sort(sort_spec)
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
    _init()
    db = get_db()

    # ── Articles : $text si disponible, sinon $regex ──
    try:
        try:
            # $text search (rapide, utilise l'index inversé)
            text_filter = {"$text": {"$search": q}}
            articles_list: List[Dict[str, Any]] = list(
                db["articles_guadeloupe"]
                .find(text_filter, {**_ARTICLE_LIST_PROJECTION, "_text_score": {"$meta": "textScore"}})
                .sort([("score", {"$meta": "textScore"})])
                .limit(50)
            )
        except Exception:
            # Fallback regex
            articles_list = list(
                db["articles_guadeloupe"]
                .find({"title": {"$regex": q, "$options": "i"}}, _ARTICLE_LIST_PROJECTION)
                .sort("scraped_at", -1)
                .limit(50)
            )
    except Exception:
        articles_list = []

    # ── Réseaux sociaux ──
    try:
        try:
            social_posts: List[Dict[str, Any]] = list(
                db["social_media_posts"]
                .find({"$text": {"$search": q}})
                .sort([("score", {"$meta": "textScore"})])
                .limit(50)
            )
        except Exception:
            social_posts = list(
                db["social_media_posts"]
                .find({"content": {"$regex": q, "$options": "i"}})
                .sort("scraped_at", -1)
                .limit(50)
            )
    except Exception:
        social_posts = []

    payload = {
        "success": True,
        "query": q,
        "searched_in": ["articles"] + (["social"] if social_posts else []),
        "articles": [serialize_doc(a) for a in articles_list],
        "social_posts": [serialize_doc(p) for p in social_posts],
        "total_results": len(articles_list) + len(social_posts),
    }
    return payload


@router.get("/search/suggestions")
def suggestions(q: str = Query(""), limit: int = Query(15, ge=1, le=50)):
    _init()
    db = get_db()
    try:
        # Projection minimale : titre uniquement
        cursor = (
            db["articles_guadeloupe"]
            .find({"title": {"$regex": q, "$options": "i"}}, {"title": 1, "scraped_at": 1})
            .sort("scraped_at", -1)
            .limit(200)
        )
        seen, out = set(), []
        for d in cursor:
            t = d.get("title")
            if t and t not in seen:
                seen.add(t)
                out.append(t)
                if len(out) >= limit:
                    break
        sugg = out
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return {"success": True, "query": q, "suggestions": sugg}


@router.get("/comments")
def comments(limit: int = Query(100, ge=1, le=500)):
    _init()
    db = get_db()
    try:
        coms = list(db["comments"].find().sort("created_at", -1).limit(limit))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "comments": [serialize_doc(c) for c in coms]}


@router.get("/digest")
def digest():
    _init()
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        articles_list = list(
            db["articles_guadeloupe"]
            .find({"date": today}, _ARTICLE_LIST_PROJECTION)
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
        "counts": {"articles": len(articles_list), "transcriptions": len(transcriptions)},
        "articles": [serialize_doc(a) for a in articles_list],
        "transcriptions": [serialize_doc(t) for t in transcriptions],
    }
