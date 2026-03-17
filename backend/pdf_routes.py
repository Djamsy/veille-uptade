# backend/pdf_routes.py
import os
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from pymongo import MongoClient
import certifi

# --- PDF service (import robuste) ---
try:
    from backend.pdf_digest_service import create_digest_pdf  # type: ignore
except Exception:
    from pdf_digest_service import create_digest_pdf  # fallback

router = APIRouter(prefix="/api/digest/pdf", tags=["digest-pdf"])

# --- Mongo (petite connexion locale, pour éviter l'import circulaire de server.py) ---
MONGO_URL = os.environ.get("MONGO_URL", "").strip() or "mongodb://localhost:27017"

def _get_db():
    try:
        client = (
            MongoClient(MONGO_URL, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=20000)
            if MONGO_URL.startswith("mongodb+srv")
            else MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)
        )
        client.admin.command("ping")
        # si la DB n'est pas dans l'URL, get_default_database() peut être None → fallback
        return client.get_default_database() or client["veille_media"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB indisponible: {e}")

def _cleanup(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

def _fetch_digest_record(date_str: str) -> dict:
    db = _get_db()
    rec = db["daily_digests"].find_one({"date": date_str}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail=f"Aucun digest pour {date_str}")
    # petit garde-fou si le HTML est manquant
    if not rec.get("digest_html"):
        raise HTTPException(status_code=404, detail=f"Digest {date_str} trouvé mais sans contenu HTML")
    return rec

@router.get("/today")
def pdf_today(inline: bool = Query(False, description="Afficher dans le navigateur (inline)")):
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return _pdf_for_date(date_str, inline)

@router.get("/{date_str}")
def pdf_by_date(
    date_str: str, 
    inline: bool = Query(False, description="Afficher dans le navigateur (inline)")
):
    # accepte YYYY-MM-DD
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Format de date attendu: YYYY-MM-DD")
    return _pdf_for_date(date_str, inline)

def _pdf_for_date(date_str: str, inline: bool):
    rec = _fetch_digest_record(date_str)
    # Le service PDF attend un dict proche de celui stocké
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{date_str}.pdf")
    tmp.close()
    out_path = tmp.name

    try:
        pdf_path = create_digest_pdf(rec, output_path=out_path)
    except Exception as e:
        _cleanup(out_path)
        raise HTTPException(status_code=500, detail=f"Erreur génération PDF: {e}")

    filename = f"digest_guadeloupe_{date_str}.pdf"
    disposition = "inline" if inline else "attachment"

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        background=BackgroundTask(_cleanup, pdf_path),
    )
