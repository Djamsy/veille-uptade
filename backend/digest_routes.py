# backend/digest_routes.py
import os
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from zoneinfo import ZoneInfo

logger = logging.getLogger("backend.digest_routes")

# ===== DB helper =====
try:
    from backend.db import get_db  # ton helper existant
except Exception:
    from pymongo import MongoClient
    def get_db():
        client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        return client.get_default_database()

# ===== TZ locale (Guadeloupe par défaut) =====
TIMEZONE = os.environ.get("TIMEZONE", "America/Guadeloupe")
GP_TZ = ZoneInfo(TIMEZONE)

router = APIRouter(prefix="/api/digest", tags=["digest"])

def _iso_local(d: datetime) -> str:
    return d.astimezone(GP_TZ).strftime("%Y-%m-%d")

def _day_bounds_local(date_str: str):
    start_local = datetime.fromisoformat(f"{date_str}T00:00:00").replace(tzinfo=GP_TZ)
    end_local = start_local + timedelta(days=1)
    # on stocke en ISO (avec TZ) pour filtrages éventuels
    return start_local.isoformat(), end_local.isoformat()

def _fetch_articles(db, date_str: str) -> List[Dict[str, Any]]:
    """
    Adapte le nom de collection selon ton schéma:
    - si tu utilises 'articles_guadeloupe', on la prend
    - sinon fallback 'articles'
    """
    start_iso, end_iso = _day_bounds_local(date_str)
    coll_name = "articles_guadeloupe" if "articles_guadeloupe" in db.list_collection_names() else "articles"
    coll = db.get_collection(coll_name)
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
        {
            "_id": 0,
            "title": 1, "url": 1, "source": 1, "site": 1,
            "summary": 1, "ai_summary": 1, "gpt_analysis": 1,
            "scraped_at": 1, "published_at": 1, "date": 1,
        },
    ).sort([("published_at", -1), ("scraped_at", -1)]).limit(60)
    return list(cur)

def _fetch_transcriptions(db, date_str: str) -> List[Dict[str, Any]]:
    coll = db.get_collection("radio_transcriptions")
    if not coll:
        return []
    cur = coll.find(
        {"date": date_str},
        {"_id": 0, "stream_name": 1, "section": 1, "ai_summary": 1,
         "gpt_analysis": 1, "captured_at": 1, "duration_seconds": 1,
         "transcription_text": 1}
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
            source = a.get("source") or a.get("site", "")
            summ = (a.get("ai_summary") or a.get("summary") or "").strip()
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
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    coll.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)

def _load_digest(db, date_str: str) -> Optional[Dict[str, Any]]:
    coll = db.get_collection("daily_digests")
    if not coll:
        return None
    return coll.find_one({"id": f"digest_{date_str}"}, {"_id": 0})

# --------- PDF helpers ---------
def _payload_for_pdf(date_str: str, created_at_iso: str, arts: List[Dict[str, Any]], trs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "date": date_str,
        "created_at": created_at_iso,
        "articles_count": len(arts),
        "transcriptions_count": len(trs),
        "digest_html": _build_html(date_str, arts, trs),
        "articles": arts,
        "transcriptions": trs,
    }

def _make_simple_pdf_bytes(html: str) -> bytes:
    # Fallback très simple (ton ancien rendu)
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        text = re.sub(r"<[^>]+>", "", html)

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from io import BytesIO

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
    return buf.getvalue()

# ===================== ROUTES =====================

@router.get("")
@router.get("/")
def get_today_or_query(date: Optional[str] = None):
    """
    GET /api/digest
    GET /api/digest?date=YYYY-MM-DD
    -> renvoie (et upsert si besoin) le digest complet
    """
    db = get_db()
    date_str = date or _iso_local(datetime.now(GP_TZ))

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

@router.post("/create-now")
def create_now(with_pdf: bool = Query(False, description="Générer aussi un PDF 'brandé'")):
    """
    Construit le digest du jour et l'enregistre.
    Optionnel: génère le PDF stylé via pdf_digest_service (fallback simple si indispo).
    """
    db = get_db()
    date_str = _iso_local(datetime.now(GP_TZ))

    arts = _fetch_articles(db, date_str)
    trs = _fetch_transcriptions(db, date_str)
    html = _build_html(date_str, arts, trs)

    _save_digest(db, date_str, html, len(arts), len(trs))

    out = {
        "success": True,
        "id": f"digest_{date_str}",
        "date": date_str,
        "digest_html": html,
        "articles_count": len(arts),
        "transcriptions_count": len(trs),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    if with_pdf:
        try:
            try:
                from backend.pdf_digest_service import create_digest_pdf  # brandé
            except Exception:
                from pdf_digest_service import create_digest_pdf  # fallback import

            pdf_path = create_digest_pdf(
                _payload_for_pdf(date_str, out["created_at"], arts, trs)
            )
            out["pdf_path"] = pdf_path
            out["pdf_download"] = f"/api/digest/{date_str}/pdf"  # route ci-dessous
        except Exception as e:
            logger.error("Génération PDF échouée: %s", e)
            out["pdf_error"] = str(e)

    return out

@router.get("/pdf/today")
def pdf_today():
    """PDF du jour (brandé si possible, sinon simple)."""
    return get_pdf(_iso_local(datetime.now(GP_TZ)))

@router.get("/{date_str}/pdf")
def get_pdf(date_str: str):
    """
    Génère un PDF brandé via pdf_digest_service si dispo,
    sinon fallback PDF texte simple (ton implémentation initiale).
    """
    db = get_db()
    doc = _load_digest(db, date_str)
    if doc:
        html = doc.get("digest_html", "")
        ac = doc.get("articles_count", 0)
        tc = doc.get("transcriptions_count", 0)
        created_at = doc.get("updated_at") or datetime.utcnow().isoformat() + "Z"
        # on rechargera les listes pour les cartes si possibles
        arts = _fetch_articles(db, date_str) if ac else []
        trs = _fetch_transcriptions(db, date_str) if tc else []
    else:
        arts = _fetch_articles(db, date_str)
        trs = _fetch_transcriptions(db, date_str)
        html = _build_html(date_str, arts, trs)
        created_at = datetime.utcnow().isoformat() + "Z"
        _save_digest(db, date_str, html, len(arts), len(trs))

    # 1) tentative PDF brandé
    try:
        try:
            from backend.pdf_digest_service import create_digest_pdf
        except Exception:
            from pdf_digest_service import create_digest_pdf
        pdf_path = create_digest_pdf(
            _payload_for_pdf(date_str, created_at, arts, trs)
        )
        # sert le fichier (inline)
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=f"digest_{date_str}.pdf",
        )
    except Exception as e:
        logger.warning("pdf_digest_service indisponible, fallback simple: %s", e)

    # 2) fallback simple (texte)
    try:
        pdf_bytes = _make_simple_pdf_bytes(html)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="digest_{date_str}.pdf"'},
        )
    except Exception as e:
        logger.error("Erreur génération PDF fallback: %s", e)
        raise HTTPException(status_code=500, detail="Erreur génération PDF")
