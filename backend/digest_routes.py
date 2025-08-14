# backend/digest_routes.py
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter
logger = logging.getLogger("backend.digest_routes")

# DB helper
try:
    from backend.db import get_db  # ton helper existant
except Exception:
    # fallback minimal pour ne pas crasher pendant l’intégration
    from pymongo import MongoClient
    import os
    def get_db():
        client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        return client.get_default_database()

router = APIRouter(prefix="/api/digest", tags=["digest"])

def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def _day_bounds(date_str: str):
    start = datetime.fromisoformat(f"{date_str}T00:00:00")
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()

def _fetch_articles(db, date_str: str) -> List[Dict[str, Any]]:
    start_iso, end_iso = _day_bounds(date_str)
    coll = db.get_collection("articles_guadeloupe")
    if not coll:
        return []
    q = {
        "$or": [
            {"date": date_str},
            {"scraped_at": {"$gte": start_iso, "$lt": end_iso}},
            {"published_at": {"$gte": start_iso, "$lt": end_iso}},
        ]
    }
    cur = coll.find(
        q,
        {"_id": 0, "title": 1, "url": 1, "source": 1, "summary": 1, "scraped_at": 1, "published_at": 1},
    ).sort([("published_at", -1), ("scraped_at", -1)]).limit(60)
    return list(cur)

def _fetch_transcriptions(db, date_str: str) -> List[Dict[str, Any]]:
    coll = db.get_collection("radio_transcriptions")
    if not coll:
        return []
    cur = coll.find(
        {"date": date_str},
        {"_id": 0, "stream_name": 1, "section": 1, "ai_summary": 1, "gpt_analysis": 1, "captured_at": 1},
    ).sort("captured_at", -1)
    return list(cur)

def _build_html(date_str: str, arts: List[Dict[str, Any]], trs: List[Dict[str, Any]]) -> str:
    parts = [f"<h1>Digest — {date_str}</h1>"]

    parts.append("<h2>📻 Radio — Synthèses</h2>")
    if trs:
        for t in trs[:10]:
            title = t.get("section") or t.get("stream_name") or "Transcription"
            summ = (t.get("ai_summary") or t.get("gpt_analysis") or "").strip()
            if not summ:
                continue
            parts.append(f"<h3>{title}</h3>")
            parts.append(f"<p>{summ}</p>")
    else:
        parts.append("<p><em>Aucune transcription pour cette date.</em></p>")

    parts.append("<h2>📰 Articles — Sélection</h2>")
    if arts:
        parts.append("<ul>")
        for a in arts[:20]:
            title = a.get("title", "Sans titre")
            url = a.get("url", "#")
            source = a.get("source", "")
            summ = (a.get("summary") or "").strip()
            parts.append("<li>")
            parts.append(f"<strong>{source}</strong> — <a href='{url}' target='_blank' rel='noopener'>{title}</a>")
            if summ:
                parts.append(f"<div style='color:#667085;margin-top:4px'>{summ}</div>")
            parts.append("</li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>Aucun article pour cette date.</em></p>")

    return "\n".join(parts)

def _save_digest(db, date_str: str, html: str, ac: int, tc: int):
    coll = db.get_collection("daily_digests")
    if not coll:
        return
    doc = {
        "id": f"digest_{date_str}",
        "date": date_str,
        "digest_html": html,
        "articles_count": ac,
        "transcriptions_count": tc,
        "updated_at": datetime.utcnow().isoformat(),
    }
    coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)

def _load_digest(db, date_str: str) -> Optional[Dict[str, Any]]:
    coll = db.get_collection("daily_digests")
    if not coll:
        return None
    return coll.find_one({"id": f"digest_{date_str}"}, {"_id": 0})

@router.get("")
@router.get("/")
def get_today_or_query(date: Optional[str] = None):
    """
    GET /api/digest            -> digest du jour
    GET /api/digest?date=YYYY-MM-DD
    Renvoie toujours un objet complet (jamais de texte “démo”).
    """
    db = get_db()
    date_str = date or _iso(datetime.utcnow())

    doc = _load_digest(db, date_str)
    if doc:
        return {"success": True, **doc}

    arts = _fetch_articles(db, date_str)
    trs = _fetch_transcriptions(db, date_str)
    html = _build_html(date_str, arts, trs)
    _save_digest(db, date_str, html, len(arts), len(trs))

    return {
        "success": True,
        "id": f"digest_{date_str}",
        "date": date_str,
        "digest_html": html,
        "articles_count": len(arts),
        "transcriptions_count": len(trs),
    }

@router.get("/{date_str}")
def get_by_date(date_str: str):
    db = get_db()
    doc = _load_digest(db, date_str)
    if doc:
        return {"success": True, **doc}
    arts = _fetch_articles(db, date_str)
    trs = _fetch_transcriptions(db, date_str)
    html = _build_html(date_str, arts, trs)
    _save_digest(db, date_str, html, len(arts), len(trs))
    return {
        "success": True,
        "id": f"digest_{date_str}",
        "date": date_str,
        "digest_html": html,
        "articles_count": len(arts),
        "transcriptions_count": len(trs),
    }

@router.get("/{date_str}/pdf")
def get_pdf(date_str: str):
    # Fabrique un PDF simple depuis le HTML enregistré (ou reconstruit si absent)
    db = get_db()
    doc = _load_digest(db, date_str)
    if doc:
        html = doc.get("digest_html", "")
    else:
        arts = _fetch_articles(db, date_str)
        trs = _fetch_transcriptions(db, date_str)
        html = _build_html(date_str, arts, trs)

    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        import re
        text = re.sub(r"<[^>]+>", "", html)

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from io import BytesIO
    from fastapi.responses import Response

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 2*cm
    for line in text.splitlines():
        if not line.strip():
            y -= 0.4*cm
            continue
        c.drawString(2*cm, y, line[:110])
        y -= 0.6*cm
        if y < 2*cm:
            c.showPage()
            y = h - 2*cm
    c.showPage()
    c.save()

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="digest_{date_str}.pdf"'},
    )