# backend/transcription_routes.py
import os
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.radio_service import radio_service

logger = logging.getLogger("backend.transcription_routes")
logger.setLevel(logging.INFO)
logger.info("🔌 transcription_routes loaded")

# ====== CONFIG & MODE ======
TRANSCRIPTION_MODE = os.getenv("TRANSCRIPTION_MODE", "simulate").strip().lower()
SIMULATE = TRANSCRIPTION_MODE != "real"
REAL_CAPTURE_AVAILABLE = True  # on part du principe que radio_service est importé

# Import GPT analyzer
try:
    from backend.gpt_analysis_service import analyze_transcription_with_gpt
    GPT_OK = True
except Exception as e:
    logger.warning("gpt_analysis_service indisponible: %s", e)
    GPT_OK = False

logger.info(
    "🎛️ Transcription config — TRANSCRIPTION_MODE=%s | simulate=%s | real_available=%s | gpt=%s",
    TRANSCRIPTION_MODE, SIMULATE, REAL_CAPTURE_AVAILABLE, GPT_OK
)

# IMPORTANT : on met le prefix ici pour éviter les 404, et on inclut ce router SANS prefix côté server.py
router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])

# ====== ÉTAT LÉGER POUR LE MODE SIMULÉ ======
STATUS: Dict[str, Any] = {
    "sections": {
        "rci": "idle",
        "la1ere": "idle",
        "autres": "idle",
    },
    "global_status": {
        "any_in_progress": False,
        "total_sections": 3,
        "active_sections": 0,
        "last_update": datetime.utcnow().isoformat()
    }
}
TRANSCRIPTIONS: Dict[str, list] = {
    "rci": [],
    "la1ere": [],
    "autres": []
}

def _set_section_status(section: str, new_status: str):
    section = section.lower()
    if section not in STATUS["sections"]:
        STATUS["sections"][section] = "idle"
        TRANSCRIPTIONS.setdefault(section, [])
        STATUS["global_status"]["total_sections"] = len(STATUS["sections"])
    STATUS["sections"][section] = new_status
    STATUS["global_status"]["any_in_progress"] = any(
        s == "in_progress" for s in STATUS["sections"].values()
    )
    STATUS["global_status"]["active_sections"] = sum(
        1 for s in STATUS["sections"].values() if s == "in_progress"
    )
    STATUS["global_status"]["last_update"] = datetime.utcnow().isoformat()
    logger.info("[transcriptions] Section=%s -> %s | any_in_progress=%s",
                section, new_status, STATUS["global_status"]["any_in_progress"])


# ====== MODE SIMULÉ ======
def _simulate_capture_then_process(section: str, duration: int):
    """
    Simule une capture (quelques secondes), génère un faux texte,
    appelle GPT (si dispo) puis push le résultat.
    """
    try:
        logger.info("🎙️ Simulation capture section '%s'…", section)
        time.sleep(min(2, max(1, duration // 120)))  # petite attente

        logger.info("🔊 Simulation ASR (transcription)…")
        fake_text = (
            "Journal RCI Guadeloupe — principaux points : "
            "travaux routiers, événements culturels, annonces institutionnelles."
        )
        time.sleep(2)

        if GPT_OK:
            logger.info("📤 Envoi de la transcription à GPT pour synthèse…")
            analysis = analyze_transcription_with_gpt(fake_text, stream_name=section)
        else:
            analysis = {
                "original_text": fake_text,
                "summary": "Résumé local (fallback).",
                "status": "fallback",
                "processed_at": datetime.utcnow().isoformat(),
            }

        TRANSCRIPTIONS[section].insert(0, {
            "id": f"{section}_{int(time.time())}",
            "section": section,
            "stream_name": section,
            "transcription_text": fake_text,
            "ai_summary": analysis.get("summary"),
            "gpt_analysis": analysis.get("gpt_analysis"),
            "status": "completed",
            "captured_at": datetime.utcnow().isoformat(),
            "analysis_method": analysis.get("analysis_method", "unknown"),
        })

    except Exception as e:
        logger.exception("Erreur simulation capture: %s", e)
    finally:
        _set_section_status(section, "completed")


# ====== MODE RÉEL ======
def _real_capture_then_process(section: str, duration: int):
    """
    Utilise radio_service pour capturer un flux audio, faire l’ASR, puis GPT.
    """
    try:
        logger.info("🎧 Capture réelle section '%s' (%ss)…", section, duration)

        # 1) Capture
        audio_path = radio_service.capture_stream(section, duration)
        if not audio_path:
            raise RuntimeError("capture_stream a renvoyé vide")

        # 2) Transcription
        logger.info("📝 ASR réelle en cours…")
        stream_key = radio_service.resolve_stream_key(section)
        tr = radio_service.transcribe_audio_file(audio_path, stream_key)
        text = tr["text"] if tr and tr.get("text") else ""
        text = text.strip() or "Transcription vide/inaudible."

        # 3) Analyse GPT
        if GPT_OK:
            logger.info("📤 Envoi de la transcription à GPT pour synthèse…")
            analysis = analyze_transcription_with_gpt(text, stream_name=section)
        else:
            analysis = {
                "original_text": text,
                "summary": "Résumé local (fallback).",
                "status": "fallback",
                "processed_at": datetime.utcnow().isoformat(),
            }

        # 4) Stockage léger (NOTE: la vraie sauvegarde durable est gérée par radio_service.capture_and_transcribe_stream)
        TRANSCRIPTIONS.setdefault(section, [])
        TRANSCRIPTIONS[section].insert(0, {
            "id": f"{section}_{int(time.time())}",
            "section": section,
            "stream_name": section,
            "transcription_text": text,
            "ai_summary": analysis.get("summary"),
            "gpt_analysis": analysis.get("gpt_analysis"),
            "status": "completed",
            "captured_at": datetime.utcnow().isoformat(),
            "analysis_method": analysis.get("analysis_method", "unknown"),
        })

    except Exception as e:
        logger.exception("Erreur capture réelle: %s", e)
    finally:
        _set_section_status(section, "completed")


# ====== ROUTES ======

@router.get("/sections")
def get_sections():
    """
    Transcriptions du jour groupées par section (clé: '7H RCI', '7H Guadeloupe Première', 'Autres')
    -> délégué au radio_service pour matcher le front.
    """
    sections = radio_service.get_todays_transcriptions_by_section()
    return {"success": True, "sections": sections}


@router.get("/status")
def get_status():
    """
    Statut détaillé des captures (radio_service sait présenter step + progress pour chaque flux).
    """
    status = radio_service.get_transcription_status()
    return {"success": True, "status": status}


@router.get("")
def get_today_flat():
    """
    Transcriptions du jour (liste plate).
    """
    items = radio_service.get_todays_transcriptions()
    return {"success": True, "transcriptions": items}


@router.get("/by-date/{date_str}")
def get_by_date(date_str: str):
    """
    Transcriptions pour une date (YYYY-MM-DD).
    """
    items = radio_service.get_transcriptions_by_date(date_str)
    return {"success": True, "transcriptions": items}


@router.post("/capture-now")
def capture_now(
    section: str = Query(..., description="ex: rci, rci_7h, guadeloupe_premiere_7h"),
    duration: Optional[int] = Query(None, ge=30, le=1800, description="Durée override en secondes (ex: 300)")
):
    """
    Lance une capture (simulate ou réelle selon TRANSCRIPTION_MODE).
    - section accepte les alias (rci → rci_7h)
    - duration (sec) permet un test court (ex: 300)
    """
    sec = (section or "").lower().strip()

    # Vérifier que la section est connue du service (via alias)
    stream_key = radio_service.resolve_stream_key(sec)
    if stream_key not in radio_service.radio_streams:
        raise HTTPException(status_code=400, detail=f"Section inconnue: {section} (résolue: {stream_key})")

    # Protection re-entrance (vue simplifiée côté sim), côté réel le service gère déjà son statut
    if STATUS["sections"].get(sec) == "in_progress":
        raise HTTPException(status_code=409, detail=f"Section '{sec}' déjà en cours")

    _set_section_status(sec, "in_progress")

    # Lancer en background pour ne pas bloquer la requête
    def worker_sim():
        _simulate_capture_then_process(sec, duration or 180)

    def worker_real():
        try:
            # on délègue au pipeline complet du service pour capture + transcription + analyse + sauvegarde DB
            radio_service.capture_and_transcribe_stream(
                stream_key=stream_key,
                duration_override_secs=duration
            )
        except Exception as e:
            logger.exception("Erreur pipeline capture '%s': %s", sec, e)
        finally:
            # IMPORTANT : libérer le drapeau local, sinon les captures suivantes restent bloquées en 'in_progress'
            _set_section_status(sec, "completed")

    if SIMULATE:
        threading.Thread(target=worker_sim, daemon=True).start()
        mode = "simulate"
        estimated = duration or 180
    else:
        threading.Thread(target=worker_real, daemon=True).start()
        mode = "real"
        estimated = duration or (radio_service.radio_streams[stream_key]["duration_minutes"] * 60)

    # Retour immédiat
    return {
        "success": True,
        "message": f"Capture '{sec}' lancée en mode {mode} pour ~{estimated}s",
        "simulate": SIMULATE,
        "real_available": REAL_CAPTURE_AVAILABLE,
        "estimated_seconds": estimated
    }