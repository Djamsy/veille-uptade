# backend/radio_cards_routes.py
from fastapi import APIRouter, Query, HTTPException, Body, Request
from datetime import datetime
from typing import Any, Dict, Optional

from starlette.responses import StreamingResponse
from gridfs import GridFSBucket
from bson import ObjectId

import logging
import traceback
import shutil

try:
    from backend.radio_service import radio_service, TZ, TIMEZONE_NAME  # type: ignore
except Exception:
    from radio_service import radio_service, TZ, TIMEZONE_NAME  # fallback

router = APIRouter(prefix="/api/radio", tags=["radio"])

# ----------------------
# Helpers
# ----------------------

def _grab_str(val: Any) -> str:
    """
    Returns a clean string out of various possible structures (str or dicts with 'summary'/'text'...).
    """
    if isinstance(val, str):
        s = val.strip()
        if s:
            return s
        return ""
    if isinstance(val, dict):
        for k in ("summary", "short", "full", "text", "content", "value"):
            v = val.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""

def _choose_best(*vals: Any) -> str:
    """Pick the first non-empty string among values/dicts."""
    for v in vals:
        s = _grab_str(v)
        if s:
            return s
    return ""

def _extract_gpt_and_transcription(doc: Dict[str, Any]) -> Dict[str, str]:
    """
    Be robust to different field names:
    - GPT summary preferred: ai_summary, ai_summary_html, gpt_summary, gpt_analysis, gpt, summary_gpt, summary
    - Transcription fields: transcription_text, transcript, text, content
    """
    gpt_summary = _choose_best(
        doc.get("ai_summary"),
        doc.get("ai_summary_html"),
        doc.get("gpt_summary"),
        doc.get("gpt_analysis"),
        doc.get("gpt"),
        doc.get("summary_gpt"),
        doc.get("summary"),
    )
    raw_transcription = _choose_best(
        doc.get("transcription_text"),
        doc.get("transcript"),
        doc.get("text"),
        doc.get("content"),
    )
    return {"gpt_summary": gpt_summary, "raw_transcription": raw_transcription}

def _mins(sec: Any) -> int:
  try:
      return int(round((sec or 0) / 60))
  except Exception:
      return 0


def _card(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Uniformise une carte à partir d'un document de transcription.
    Si le service expose build_card(), on l'utilise pour éviter la duplication.
    """
    try:
        build_card = getattr(radio_service, "build_card", None)
    except Exception:
        build_card = None

    if callable(build_card):
        return build_card(doc, TIMEZONE_NAME)

    # Fallback local (si build_card n'existe pas)
    title = doc.get("stream_name") or doc.get("section") or "Transcription"
    dur_min = _mins(doc.get("duration_seconds"))
    start = doc.get("start_time_local") or ""

    # Build both short (preview) and full versions
    fields = _extract_gpt_and_transcription(doc)
    gpt_summary = fields["gpt_summary"]
    raw_transcription = fields["raw_transcription"]

    # Prefer GPT summary both in preview and in expanded view; fallback to raw transcription
    preferred_full = gpt_summary if gpt_summary else raw_transcription

    is_truncated = False
    summary_short = preferred_full
    if len(preferred_full) > 400:
        summary_short = preferred_full[:400] + "…"
        is_truncated = True

    return {
        "id": doc.get("id"),
        "title": title,
        "subtitle": f"{doc.get('date','')} • {start} • {dur_min} min".strip(" •"),
        "summary": summary_short,                 # preview (may be truncated)
        "fullSummary": gpt_summary,               # full GPT summary (untruncated, may be empty)
        "fullText": preferred_full,               # expanded content (GPT if available, else transcription)
        "isTruncated": is_truncated,
        "summarySource": "gpt" if gpt_summary else "transcription",
        "audioUrl": (f"/api/radio/audio/{doc['audio_file_id']}" if doc.get("audio_file_id") else None),
        "type": doc.get("type", "radio"),   # radio | tv
        "source": doc.get("section"),
        "capturedAt": doc.get("captured_at"),
        "timezone": doc.get("timezone") or TIMEZONE_NAME,
        "meta": {
            "transcriptionMethod": doc.get("transcription_method"),
            "analysisMethod": doc.get("analysis_method"),
        },
    }


def _snapshots_col():
    db = getattr(radio_service, "db", None)
    return db["radio_cards_snapshots"] if db is not None else None


# ----------------------
# Endpoints cartes (live)
# ----------------------

@router.get("/cards/today")
def radio_cards_today(limit: int = Query(20, ge=1, le=100)):
    col = radio_service.transcriptions_collection
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        docs = list(
            col.find({"date": today}, {"_id": 0}).sort("captured_at", -1).limit(limit)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    cards = [_card(d) for d in docs]
    return {"success": True, "date": today, "count": len(cards), "cards": cards}


@router.get("/cards")
def radio_cards(
    date: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    col = radio_service.transcriptions_collection
    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        cur = (
            col.find({"date": date}, {"_id": 0})
            .sort("captured_at", -1)
            .skip(offset)
            .limit(limit)
        )
        docs = list(cur)
        total = col.count_documents({"date": date})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    cards = [_card(d) for d in docs]
    return {
        "success": True,
        "date": date,
        "cards": cards,
        "pagination": {
            "total": total,
            "offset": offset,
            "returned": len(cards),
            "hasMore": offset + len(cards) < total,
        },
    }


@router.get("/cards/{transcription_id}")
def radio_card_by_id(transcription_id: str):
    col = radio_service.transcriptions_collection
    try:
        doc = col.find_one({"id": transcription_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    return {"success": True, "card": _card(doc), "raw": doc}


# ----------------------
# Endpoints SNAPSHOT (persistés en DB)
# ----------------------

@router.get("/cards/snapshot")
def radio_cards_snapshot(date: Optional[str] = None):
    """Retourne un snapshot mongo s'il existe, sinon reconstruit live."""
    col = radio_service.transcriptions_collection
    snaps = _snapshots_col()
    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")

    # 1) Lire le snapshot s'il existe
    if snaps is not None:
        snap = snaps.find_one({"date": date}, {"_id": 0})
        if snap:
            return {"success": True, "date": date, "source": "snapshot", "cards": snap.get("cards", [])}

    # 2) Fallback live
    try:
        docs = list(col.find({"date": date}, {"_id": 0}).sort("captured_at", -1))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    cards = [_card(d) for d in docs]
    return {"success": True, "date": date, "source": "live", "cards": cards}


@router.post("/cards/refresh-snapshot")
def refresh_snapshot(date: Optional[str] = Body(default=None)):
    """Reconstruit le snapshot pour une date (par défaut aujourd'hui)."""
    col = radio_service.transcriptions_collection
    snaps = _snapshots_col()
    if snaps is None:
        raise HTTPException(status_code=503, detail="Snapshots DB non disponible")

    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")

    try:
        docs = list(col.find({"date": date}, {"_id": 0}).sort("captured_at", -1))
        cards = [_card(d) for d in docs]
        snaps.update_one(
            {"date": date},
            {"$set": {"date": date, "cards": cards, "refreshed_at": datetime.utcnow().isoformat() + "Z"}},
            upsert=True,
        )
        return {"success": True, "date": date, "count": len(cards), "cards": cards}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

# ----------------------
# Endpoint CAPTURE IMMEDIATE (déclenche une courte capture)
# ----------------------
@router.post("/capture")
async def capture_radio_now(
    section: str = Query("RCI", description="Clé de flux OU fragment (ex: 'rci_0620', 'RCI', '6h20', 'GP')"),
    duration: int = Query(20, ge=5, le=600, description="Durée en secondes (5–600)")
):
    """Lance une capture courte puis persiste transcription + audio GridFS.
    'section' peut être une clé exacte de radio_service.streams ou un fragment recherché dans name/section.
    """
    logger = logging.getLogger(__name__)

    # Sanity checks clairs pour éviter les 500 silencieux
    if not hasattr(radio_service, "capture_and_transcribe_stream"):
        raise HTTPException(status_code=500, detail="radio_service.capture_and_transcribe_stream introuvable")
    if shutil.which("ffmpeg") is None:
        raise HTTPException(status_code=500, detail="ffmpeg introuvable dans le PATH (installez-le ou ajoutez-le au PATH)")

    # 1) Résoudre une clé de flux valide à partir de 'section'
    provided = (section or "").strip()
    streams = getattr(radio_service, "streams", {}) or {}
    key = None

    # Cas 1: clé exacte
    if provided in streams:
        key = provided
    else:
        low = provided.lower()
        candidates = []
        for k, cfg in streams.items():
            sec = str(cfg.get("section", "")).lower()
            nm  = str(cfg.get("name", "")).lower()
            if low and (low in sec or low in nm):
                candidates.append((k, int(cfg.get("priority", 9999))))
        if candidates:
            candidates.sort(key=lambda x: x[1])  # plus faible priority = plus prioritaire
            key = candidates[0][0]
        else:
            # Fallback par défaut si "RCI" ou vide
            key = "rci_7h" if ("rci" in low or not low) else "guadeloupe_premiere_7h"

    if key not in streams:
        raise HTTPException(status_code=400, detail=f"Flux introuvable pour '{section}'. Clés dispo: {', '.join(streams.keys())}")

    try:
        # 2) Appel avec la bonne signature (clé + duration_override_secs)
        result = radio_service.capture_and_transcribe_stream(key=key, duration_override_secs=duration)
        import inspect
        doc = await result if inspect.isawaitable(result) else result

        if not doc or not isinstance(doc, dict):
            raise HTTPException(status_code=500, detail="Aucun document retourné par la capture")

        # Normaliser le retour éventuel {success, transcription}
        record = doc.get("transcription") if ("success" in doc and "transcription" in doc) else doc
        if not record:
            raise HTTPException(status_code=500, detail="Transcription manquante dans la réponse")

        return {"success": True, "card": _card(record), "raw": record, "used_key": key}

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Capture failed: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Capture failed: {e.__class__.__name__}: {e}")

# ----------------------
# Endpoint AUDIO (GridFS streaming + Range)
# ----------------------
@router.get("/audio/{file_id}")
def stream_audio(file_id: str, request: Request):
    """Stream un fichier audio stocké dans GridFS avec support Range (206)."""
    db = getattr(radio_service, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="DB non initialisée")

    try:
        bucket = GridFSBucket(db, bucket_name="radio_audio")
        grid_out = bucket.open_download_stream(ObjectId(file_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Audio introuvable")

    file_size = grid_out.length
    content_type = (grid_out.metadata or {}).get("contentType") or "audio/mp4"

    range_header = request.headers.get("range")
    if not range_header:
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=86400",
        }

        def body_iter():
            try:
                while True:
                    chunk = grid_out.read(1024 * 256)
                    if not chunk:
                        break
                    yield chunk
            finally:
                grid_out.close()

        return StreamingResponse(body_iter(), headers=headers, media_type=content_type)

    # Parse Range header: bytes=start-end
    try:
        _, byte_range = range_header.split("=")
        start_str, end_str = (byte_range.split("-") + [""])[:2]
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=416, detail="Range invalide")

    # Position du curseur et réponse partielle
    grid_out.seek(start)
    chunk_len = end - start + 1

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_len),
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=86400",
    }

    def range_iter():
        remaining = chunk_len
        try:
            while remaining > 0:
                buf = grid_out.read(min(1024 * 256, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf
        finally:
            grid_out.close()

    return StreamingResponse(range_iter(), headers=headers, status_code=206, media_type=content_type)
