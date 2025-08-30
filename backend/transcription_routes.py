# backend/transcription_routes.py
from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query, Body

# Import radio service + TZ helpers (compatible avec exécution depuis backend/ ou racine)
try:
    from backend.radio_service import radio_service, TZ, TIMEZONE_NAME  # type: ignore
except Exception:  # pragma: no cover
    from radio_service import radio_service, TZ, TIMEZONE_NAME  # type: ignore

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])

# -----------------
# Helpers
# -----------------

def _sections_payload() -> Dict[str, Any]:
    """Expose les créneaux déclarés dans radio_service.streams, format simple."""
    sections: Dict[str, Any] = {}
    for key, cfg in (radio_service.streams or {}).items():
        sch = cfg.get("schedule", {})
        sections[key] = {
            "key": key,
            "name": cfg.get("name"),
            "section": cfg.get("section"),
            "type": cfg.get("type", "radio"),
            "url": cfg.get("url"),
            "duration_minutes": cfg.get("duration_minutes"),
            "schedule": {
                "days": sch.get("days"),
                "hour": sch.get("hour"),
                "minute": sch.get("minute"),
                "timezone": TIMEZONE_NAME,
            },
            "priority": cfg.get("priority", 0),
        }
    return sections


def _status_payload() -> Dict[str, Any]:
    st = getattr(radio_service, "status", {}) or {}
    any_in_progress = any(v.get("in_progress") for v in st.values())
    return {
        "sections": st,
        "global_status": {
            "any_in_progress": any_in_progress,
            "total_sections": len(st),
            "active_sections": sum(1 for v in st.values() if v.get("in_progress")),
            "now_local": datetime.now(TZ).isoformat(),
            "timezone": TIMEZONE_NAME,
        },
    }


def _mins(sec: Any) -> int:
    try:
        return int(round((sec or 0) / 60))
    except Exception:
        return 0


def _card(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format 'card' compatible avec le front (fallback si radio_cards_routes n'est pas monté)."""
    title = doc.get("stream_name") or doc.get("section") or "Transcription"
    dur_min = _mins(doc.get("duration_seconds"))
    start = doc.get("start_time_local") or ""
    summary = (doc.get("ai_summary")
               or doc.get("gpt_analysis")
               or doc.get("transcription_text", "")).strip()
    if len(summary) > 400:
        summary = summary[:400] + "…"

    return {
        "id": doc.get("id"),
        "title": title,
        "subtitle": f"{doc.get('date','')} • {start} • {dur_min} min".strip(" •"),
        "summary": summary,
        "audioUrl": doc.get("audio_url"),   # None si non sauvegardé
        "type": doc.get("type", "radio"),   # radio | tv
        "source": doc.get("section"),
        "capturedAt": doc.get("captured_at"),
        "timezone": doc.get("timezone") or TIMEZONE_NAME,
        "meta": {
            "transcriptionMethod": doc.get("transcription_method"),
            "analysisMethod": doc.get("analysis_method"),
        },
    }

# -----------------
# Endpoints racine (compat front)
# -----------------

@router.get("")
@router.get("/")
def overview():
    """Racine attendue par le front : sections + statut actuel."""
    return {"success": True, "sections": _sections_payload(), "status": _status_payload()}

@router.get("/sections")
def transcriptions_sections():
    return {"success": True, "sections": _sections_payload()}

@router.get("/status")
def transcriptions_status():
    return {"success": True, "status": _status_payload()}

# -----------------
# Listing simple
# -----------------

@router.get("/today")
def transcriptions_today():
    """Liste plate des transcriptions du jour."""
    items = radio_service.get_todays_transcriptions()
    return {"success": True, "transcriptions": items}

@router.get("/by-date/{date_str}")
def transcriptions_by_date(date_str: str):
    items = radio_service.get_transcriptions_by_date(date_str)
    return {"success": True, "transcriptions": items}

# -----------------
# Cards (fallback intégré)
# -----------------

@router.get("/cards/today")
def transcriptions_cards_today(limit: int = Query(20, ge=1, le=100)):
    """Retourne des 'cards' construites côté backend pour le jour courant."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    items = radio_service.get_transcriptions_by_date(today)[:limit]
    cards = [_card(d) for d in items]
    return {"success": True, "date": today, "count": len(cards), "cards": cards}

@router.get("/cards")
def transcriptions_cards(
    date: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")
    docs = radio_service.get_transcriptions_by_date(date)
    total = len(docs)
    page = docs[offset : offset + limit]
    cards = [_card(d) for d in page]
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

# -----------------
# Actions
# -----------------

@router.post("/capture-now")
def capture_now(
    payload: Dict[str, Any] = Body(default={}),
    section: Optional[str] = Query(None, description="Clé de stream (ex: rci_0620)"),
    duration: Optional[int] = Query(None, ge=30, le=3600, description="Durée override en secondes"),
):
    """Lance une capture immédiate via le pipeline du service."""
    # section peut venir du body (compat front) ou de la query
    key = (payload.get("section") or payload.get("key") or section or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Paramètre 'section' requis")

    if key not in radio_service.streams:
        raise HTTPException(status_code=400, detail=f"Section inconnue: {key}")

    try:
        res = radio_service.capture_and_transcribe_stream(key, duration_override_secs=duration)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur capture: {e}")

    return {"success": bool(res.get("success")), "result": res}

@router.post("/run-due")
def run_due_now():
    """
    Déclenche la vérification des créneaux 'due now' et exécute les captures correspondantes.
    Utile pour tester le scheduler manuellement via l'UI.
    """
    try:
        result = radio_service.capture_due_streams()
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur run-due: {e}")