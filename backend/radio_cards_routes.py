# backend/radio_cards_routes.py
"""
Routes pour les cartes radio avec gestion robuste des erreurs et URLs de fallback
- Résolution intelligente des clés de flux
- URLs de secours automatiques
- Gestion d'erreur granulaire
- Validation des données avant capture
"""

from fastapi import APIRouter, Query, HTTPException, Body, Request
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple
import requests
import logging
import traceback
import shutil
import inspect
import re

from starlette.responses import StreamingResponse
from gridfs import GridFSBucket
from bson import ObjectId

try:
    from backend.radio_service import radio_service, TZ, TIMEZONE_NAME
except Exception:
    from radio_service import radio_service, TZ, TIMEZONE_NAME

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/radio", tags=["radio"])

# =========================
# Configuration URLs de fallback
# =========================
FALLBACK_URLS = {
    "rci": "https://rci.streamakaci.com/rci971.mp3",
    "guadeloupe_premiere": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
    "test": "https://www.soundjay.com/misc/sounds/bell-ringing-05.wav"  # URL de test courte
}

PRIORITY_STREAMS = [
    "rci_replay",
    "gp_radio_0700", 
    "guadeloupe_premiere_7h",
    "rci_7h"
]

# =========================
# Helpers
# =========================
def _grab_str(val: Any) -> str:
    """Retourne une chaîne propre depuis divers formats."""
    if isinstance(val, str):
        s = val.strip()
        return s if s else ""
    if isinstance(val, dict):
        for k in ("summary", "short", "full", "text", "content", "value"):
            v = val.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""

def _choose_best(*vals: Any) -> str:
    """Prend la première chaîne non vide parmi des valeurs/dicts."""
    for v in vals:
        s = _grab_str(v)
        if s:
            return s
    return ""

def _build_summary_from_ai_topics(ai_topics: list) -> str:
    """Construit un résumé lisible à partir des ai_topics (split_radio_transcription)."""
    if not ai_topics or not isinstance(ai_topics, list):
        return ""
    parts = []
    for topic in ai_topics:
        if not isinstance(topic, dict):
            continue
        title = topic.get("title", "").strip()
        summary = topic.get("summary", "").strip()
        if title and summary:
            parts.append(f"**{title}** — {summary}")
        elif title:
            parts.append(f"**{title}**")
        elif summary:
            parts.append(summary)
    return "\n\n".join(parts) if parts else ""


def _extract_gpt_and_transcription(doc: Dict[str, Any]) -> Dict[str, str]:
    """Extraction robuste des champs de transcription.
    Supporte aussi bien les anciens champs (ai_summary, gpt_summary)
    que le nouveau format ai_topics (tableau de sujets extraits par l'IA)."""
    gpt_summary = _choose_best(
        doc.get("ai_summary"),
        doc.get("ai_summary_html"),
        doc.get("gpt_summary"),
        doc.get("gpt_analysis"),
        doc.get("gpt"),
        doc.get("summary_gpt"),
        doc.get("summary"),
    )
    # Si pas de résumé classique, essayer de construire depuis ai_topics
    if not gpt_summary:
        ai_topics = doc.get("ai_topics")
        if ai_topics:
            gpt_summary = _build_summary_from_ai_topics(ai_topics)

    raw_transcription = _choose_best(
        doc.get("transcription"),
        doc.get("transcription_text"),
        doc.get("transcript"),
        doc.get("text"),
        doc.get("content"),
    )
    return {"gpt_summary": gpt_summary, "raw_transcription": raw_transcription}

def _mins(sec: Any) -> int:
    """Conversion sécurisée secondes vers minutes."""
    try:
        return int(round((sec or 0) / 60))
    except Exception:
        return 0

def _validate_url(url: str, timeout: int = 5) -> bool:
    """Valide qu'une URL est accessible."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code < 400
    except Exception as e:
        logger.debug(f"URL validation failed for {url}: {e}")
        return False

def _get_working_url(stream_config: Dict[str, Any]) -> str:
    """Retourne une URL fonctionnelle pour un stream."""
    original_url = stream_config.get("url", "")
    
    # Test de l'URL originale
    if _validate_url(original_url):
        return original_url
    
    # URLs de fallback selon le type de stream
    stream_key = stream_config.get("name", "").lower()
    
    if "rci" in stream_key:
        fallback = FALLBACK_URLS["rci"]
        if _validate_url(fallback):
            logger.info(f"Using RCI fallback URL for {stream_key}")
            return fallback
    
    if "guadeloupe" in stream_key or "gp" in stream_key:
        fallback = FALLBACK_URLS["guadeloupe_premiere"]
        if _validate_url(fallback):
            logger.info(f"Using GP fallback URL for {stream_key}")
            return fallback
    
    # Derniere chance avec URL de test
    test_url = FALLBACK_URLS["test"]
    if _validate_url(test_url):
        logger.warning(f"Using test URL for {stream_key} - all real URLs failed")
        return test_url
    
    # Retourner l'URL originale même si elle ne marche pas
    logger.error(f"No working URL found for {stream_key}, using original")
    return original_url

def _resolve_stream_key(provided: str, streams: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """
    Résolution robuste des clés de flux avec scoring intelligent.
    Retourne (key, reason) où reason explique le choix.
    """
    if not provided:
        # Pas de section fournie - utiliser le stream prioritaire
        for priority_key in PRIORITY_STREAMS:
            if priority_key in streams:
                return priority_key, f"default_priority:{priority_key}"
        return None, "no_streams_available"
    
    provided_clean = provided.strip()
    
    # 1. Clé exacte
    if provided_clean in streams:
        return provided_clean, "exact_match"
    
    # 2. Recherche par correspondance partielle
    provided_lower = provided_clean.lower()
    
    # Correspondances exactes sur section/name
    exact_candidates = []
    partial_candidates = []
    
    for key, config in streams.items():
        section = str(config.get("section", "")).lower()
        name = str(config.get("name", "")).lower()
        priority = int(config.get("priority", 9999))
        enabled = config.get("enabled", True)
        
        # Ignorer les streams désactivés
        if not enabled:
            continue
        
        # Score de correspondance
        score = 0
        
        # Correspondance exacte sur section
        if provided_lower == section:
            score += 100
        elif provided_lower in section:
            score += 50
        
        # Correspondance exacte sur nom
        if provided_lower in name:
            score += 30
        
        # Correspondances partielles
        words = re.findall(r'\w+', provided_lower)
        for word in words:
            if word in section:
                score += 10
            if word in name:
                score += 5
        
        if score >= 100:
            exact_candidates.append((key, score, priority))
        elif score >= 10:
            partial_candidates.append((key, score, priority))
    
    # Trier par score puis par priorité
    if exact_candidates:
        exact_candidates.sort(key=lambda x: (-x[1], x[2]))
        return exact_candidates[0][0], f"exact_section_match:score={exact_candidates[0][1]}"
    
    if partial_candidates:
        partial_candidates.sort(key=lambda x: (-x[1], x[2]))
        return partial_candidates[0][0], f"partial_match:score={partial_candidates[0][1]}"
    
    # 3. Fallback intelligent selon le type
    if any(word in provided_lower for word in ["rci", "radio"]):
        for priority_key in ["rci_replay", "rci_7h", "rci_0620"]:
            if priority_key in streams:
                return priority_key, f"rci_fallback:{priority_key}"
    
    if any(word in provided_lower for word in ["gp", "guadeloupe", "premiere"]):
        for priority_key in ["gp_radio_0700", "guadeloupe_premiere_7h"]:
            if priority_key in streams:
                return priority_key, f"gp_fallback:{priority_key}"
    
    # 4. Fallback par priorité générale
    for priority_key in PRIORITY_STREAMS:
        if priority_key in streams:
            return priority_key, f"general_fallback:{priority_key}"
    
    return None, "no_suitable_stream_found"

def _card(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Uniformise une carte à partir d'un document de transcription."""
    try:
        build_card = getattr(radio_service, "build_card", None)
        if callable(build_card):
            return build_card(doc, TIMEZONE_NAME)
    except Exception:
        pass

    # Construction manuelle de la carte
    title = doc.get("name") or doc.get("stream_name") or doc.get("section") or "Transcription"
    dur_min = _mins(doc.get("duration_minutes", 0) * 60 or doc.get("duration_seconds", 0))
    start = doc.get("time") or doc.get("start_time_local") or ""

    fields = _extract_gpt_and_transcription(doc)
    gpt_summary = fields["gpt_summary"]
    raw_transcription = fields["raw_transcription"]

    preferred_full = gpt_summary if gpt_summary else raw_transcription

    is_truncated = False
    summary_short = preferred_full
    if len(preferred_full) > 400:
        summary_short = preferred_full[:400] + "…"
        is_truncated = True

    return {
        "id": doc.get("id") or str(doc.get("_id", "")),
        "title": title,
        "subtitle": f"{doc.get('date', '')} • {start} • {dur_min} min".strip(" •"),
        "summary": summary_short,
        "fullSummary": gpt_summary,
        "fullText": preferred_full,
        "isTruncated": is_truncated,
        "summarySource": "gpt" if gpt_summary else "transcription",
        "audioUrl": (f"/api/radio/audio/{doc['audio_file_id']}" if doc.get("audio_file_id") else None),
        "type": doc.get("type", "radio"),
        "source": doc.get("section"),
        "capturedAt": doc.get("captured_at"),
        "timezone": doc.get("timezone") or TIMEZONE_NAME,
        "meta": {
            "transcriptionMethod": doc.get("transcription_method"),
            "analysisMethod": doc.get("analysis_method"),
        },
    }

def _snapshots_col():
    """Accès sécurisé à la collection snapshots."""
    try:
        db = getattr(radio_service, "db", None)
        return db["radio_cards_snapshots"] if db is not None else None
    except Exception:
        return None

def _safe_db_operation(operation_name: str, operation_func):
    """Wrapper sécurisé pour les opérations DB."""
    try:
        return operation_func()
    except Exception as e:
        logger.error(f"DB operation '{operation_name}' failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database error in {operation_name}")

# =========================
# Endpoints cartes (live)
# =========================
@router.get("/cards/today")
def radio_cards_today(limit: int = Query(20, ge=1, le=100)):
    """Cartes radio du jour avec gestion d'erreur robuste."""
    if not hasattr(radio_service, 'transcriptions_collection'):
        raise HTTPException(status_code=503, detail="Service radio non initialisé")
    
    if radio_service.transcriptions_collection is None:
        raise HTTPException(status_code=503, detail="Collection transcriptions non disponible")
    
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    
    def _get_cards():
        col = radio_service.transcriptions_collection
        docs = list(
            col.find({"date": today}, {"_id": 0})
            .sort("captured_at", -1)
            .limit(limit)
        )
        return [_card(d) for d in docs]
    
    cards = _safe_db_operation("cards_today", _get_cards)
    return {"success": True, "date": today, "count": len(cards), "cards": cards}

@router.get("/cards")
def radio_cards(
    date: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Cartes radio avec pagination robuste."""
    if not hasattr(radio_service, 'transcriptions_collection'):
        raise HTTPException(status_code=503, detail="Service radio non initialisé")
    
    if radio_service.transcriptions_collection is None:
        raise HTTPException(status_code=503, detail="Collection transcriptions non disponible")
    
    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")
    
    def _get_paginated_cards():
        col = radio_service.transcriptions_collection
        cur = (
            col.find({"date": date}, {"_id": 0})
            .sort("captured_at", -1)
            .skip(offset)
            .limit(limit)
        )
        docs = list(cur)
        total = col.count_documents({"date": date})
        return docs, total
    
    docs, total = _safe_db_operation("cards_paginated", _get_paginated_cards)
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
    """Récupération d'une carte par ID avec validation."""
    if not hasattr(radio_service, 'transcriptions_collection'):
        raise HTTPException(status_code=503, detail="Service radio non initialisé")
    
    if radio_service.transcriptions_collection is None:
        raise HTTPException(status_code=503, detail="Collection transcriptions non disponible")
    
    def _get_card():
        col = radio_service.transcriptions_collection
        # Recherche par plusieurs champs possibles
        query = {
            "$or": [
                {"id": transcription_id},
                {"_id": transcription_id},
                {"stream_key": transcription_id}
            ]
        }
        doc = col.find_one(query, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Transcription {transcription_id} not found")
        return doc
    
    doc = _safe_db_operation("card_by_id", _get_card)
    return {"success": True, "card": _card(doc), "raw": doc}

@router.get("/cards/snapshot")
def radio_cards_snapshot(date: Optional[str] = None):
    """Snapshot avec fallback live intelligent."""
    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")

    # Essayer le snapshot d'abord
    snaps = _snapshots_col()
    if snaps is not None:
        try:
            snap = snaps.find_one({"date": date}, {"_id": 0})
            if snap and snap.get("cards"):
                return {"success": True, "date": date, "source": "snapshot", "cards": snap["cards"]}
        except Exception as e:
            logger.warning(f"Snapshot read failed: {e}")

    # Fallback live
    if not hasattr(radio_service, 'transcriptions_collection'):
        return {"success": True, "date": date, "source": "empty", "cards": []}
    
    if radio_service.transcriptions_collection is None:
        return {"success": True, "date": date, "source": "empty", "cards": []}
    
    def _get_live_cards():
        col = radio_service.transcriptions_collection
        docs = list(col.find({"date": date}, {"_id": 0}).sort("captured_at", -1))
        return [_card(d) for d in docs]
    
    cards = _safe_db_operation("snapshot_live_fallback", _get_live_cards)
    return {"success": True, "date": date, "source": "live", "cards": cards}

@router.post("/cards/refresh-snapshot")
def refresh_snapshot(date: Optional[str] = Body(default=None)):
    """Reconstruction robuste du snapshot."""
    snaps = _snapshots_col()
    if snaps is None:
        raise HTTPException(status_code=503, detail="Snapshots DB non disponible")

    if not date:
        date = datetime.now(TZ).strftime("%Y-%m-%d")

    def _refresh_snapshot():
        col = radio_service.transcriptions_collection
        docs = list(col.find({"date": date}, {"_id": 0}).sort("captured_at", -1))
        cards = [_card(d) for d in docs]
        
        snaps.update_one(
            {"date": date},
            {"$set": {
                "date": date, 
                "cards": cards, 
                "refreshed_at": datetime.utcnow().isoformat() + "Z",
                "card_count": len(cards)
            }},
            upsert=True,
        )
        return cards
    
    cards = _safe_db_operation("refresh_snapshot", _refresh_snapshot)
    return {"success": True, "date": date, "count": len(cards), "cards": cards}

# =========================
# Capture robuste
# =========================
@router.post("/capture")
async def capture_radio_now(
    section: str = Query("", description="Clé de flux OU fragment (ex: 'rci_0620', 'RCI', '6h20', 'GP')"),
    duration: int = Query(20, ge=5, le=600, description="Durée en secondes (5–600)")
):
    """Capture radio avec résolution intelligente et URLs de fallback."""
    
    # Vérifications préliminaires
    if not hasattr(radio_service, "capture_and_transcribe_stream"):
        raise HTTPException(status_code=500, detail="Service de capture non disponible")
    
    if shutil.which("ffmpeg") is None:
        raise HTTPException(status_code=500, detail="FFmpeg non installé")

    # Résolution de la clé de flux
    streams = getattr(radio_service, "streams", {}) or {}
    if not streams:
        raise HTTPException(status_code=503, detail="Aucun flux configuré")
    
    key, resolution_reason = _resolve_stream_key(section, streams)
    if not key:
        available_keys = list(streams.keys())
        raise HTTPException(
            status_code=400, 
            detail=f"Flux introuvable pour '{section}'. Disponibles: {available_keys}"
        )
    
    logger.info(f"Stream resolution: '{section}' -> '{key}' (reason: {resolution_reason})")
    
    # Vérification et correction de l'URL
    stream_config = streams[key].copy()
    working_url = _get_working_url(stream_config)
    
    # Si l'URL a changé, mettre à jour temporairement
    if working_url != stream_config.get("url"):
        logger.info(f"Using fallback URL for {key}: {working_url}")
        # Créer une copie temporaire avec l'URL corrigée
        temp_streams = radio_service.streams.copy()
        temp_streams[key] = stream_config.copy()
        temp_streams[key]["url"] = working_url
        
        # Remplacer temporairement
        original_streams = radio_service.streams
        radio_service.streams = temp_streams
        
        try:
            # Capture avec URL corrigée
            result = radio_service.capture_and_transcribe_stream(key=key, duration_override_secs=duration)
            
            # Attendre si c'est une coroutine
            if inspect.isawaitable(result):
                result = await result
            
        finally:
            # Restaurer la configuration originale
            radio_service.streams = original_streams
    else:
        # Capture normale
        result = radio_service.capture_and_transcribe_stream(key=key, duration_override_secs=duration)
        if inspect.isawaitable(result):
            result = await result

    # Validation du résultat
    if not result or not isinstance(result, dict):
        raise HTTPException(status_code=500, detail="Capture failed - no result")

    if not result.get("success", False):
        error_msg = result.get("error", "Unknown capture error")
        # Log détaillé pour debug
        logger.error(f"Capture failed for {key}: {error_msg}")
        
        # Retourner une erreur avec plus de contexte
        raise HTTPException(
            status_code=422, 
            detail=f"Capture failed for stream '{key}': {error_msg}"
        )

    # Extraire la transcription
    doc = result.get("transcription", result)
    if not doc:
        raise HTTPException(status_code=500, detail="No transcription data in result")

    # Construire la réponse
    try:
        card = _card(doc)
        return {
            "success": True, 
            "card": card, 
            "raw": doc, 
            "used_key": key,
            "resolution_reason": resolution_reason,
            "url_used": working_url
        }
    except Exception as e:
        logger.error(f"Card generation failed: {e}")
        return {
            "success": True, 
            "card": {"error": "Card generation failed", "raw": str(e)}, 
            "raw": doc, 
            "used_key": key
        }

# =========================
# Streaming audio robuste
# =========================
@router.get("/audio/{file_id}")
def stream_audio(file_id: str, request: Request):
    """Stream audio avec gestion d'erreur complète."""
    db = getattr(radio_service, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Base de données non initialisée")

    try:
        # Validation de l'ObjectId
        if not file_id or len(file_id) != 24:
            raise HTTPException(status_code=400, detail="ID audio invalide")
        
        bucket = GridFSBucket(db, bucket_name="radio_audio")
        grid_out = bucket.open_download_stream(ObjectId(file_id))
        
    except Exception as e:
        logger.error(f"Audio file access failed for {file_id}: {e}")
        raise HTTPException(status_code=404, detail="Fichier audio introuvable")

    file_size = grid_out.length
    content_type = (grid_out.metadata or {}).get("contentType") or "audio/wav"

    # Gestion Range requests
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
            except Exception as e:
                logger.error(f"Stream error: {e}")
            finally:
                try:
                    grid_out.close()
                except:
                    pass

        return StreamingResponse(body_iter(), headers=headers, media_type=content_type)

    # Parse Range header
    try:
        _, byte_range = range_header.split("=")
        start_str, end_str = (byte_range.split("-") + [""])[:2]
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        
        if start > end or start >= file_size:
            raise ValueError("Range invalide")
            
    except Exception:
        raise HTTPException(status_code=416, detail="Range header invalide")

    # Position et streaming partiel
    try:
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
            except Exception as e:
                logger.error(f"Range stream error: {e}")
            finally:
                try:
                    grid_out.close()
                except:
                    pass

        return StreamingResponse(range_iter(), headers=headers, status_code=206, media_type=content_type)
        
    except Exception as e:
        logger.error(f"Range streaming failed: {e}")
        raise HTTPException(status_code=500, detail="Erreur streaming audio")

# =========================
# Endpoints de diagnostic
# =========================
@router.get("/debug/streams")
def debug_streams():
    """Debug: liste des streams avec validation des URLs."""
    streams = getattr(radio_service, "streams", {})
    if not streams:
        return {"success": False, "error": "No streams configured"}
    
    debug_info = []
    for key, config in streams.items():
        url = config.get("url", "")
        working_url = _get_working_url(config)
        url_changed = url != working_url
        
        debug_info.append({
            "key": key,
            "name": config.get("name", ""),
            "original_url": url,
            "working_url": working_url,
            "url_changed": url_changed,
            "enabled": config.get("enabled", True),
            "priority": config.get("priority", 9999)
        })
    
    return {"success": True, "streams": debug_info}

@router.post("/debug/test-capture")
def debug_test_capture(stream_key: str = Body(...)):
    """Debug: test de capture pour un stream spécifique."""
    streams = getattr(radio_service, "streams", {})
    if stream_key not in streams:
        return {"success": False, "error": f"Stream {stream_key} not found"}

    config = streams[stream_key]
    working_url = _get_working_url(config)

    return {
        "success": True,
        "stream_key": stream_key,
        "original_url": config.get("url"),
        "working_url": working_url,
        "url_valid": _validate_url(working_url, timeout=10),
        "config": config
    }


# =========================
# Health-check flux radio
# =========================

def _check_stream_health(key: str, config: Dict[str, Any], timeout: int = 8) -> Dict[str, Any]:
    """Vérifie la santé d'un flux radio individuel.
    Teste : accessibilité HTTP + entêtes audio + latence."""
    url = config.get("url", "")
    enabled = config.get("enabled", True)
    result = {
        "key": key,
        "name": config.get("name", ""),
        "section": config.get("section", ""),
        "type": config.get("type", "radio"),
        "url": url,
        "enabled": enabled,
        "status": "unknown",
        "latency_ms": None,
        "content_type": None,
        "error": None,
        "checked_at": datetime.now(TZ).isoformat(),
    }
    if not enabled:
        result["status"] = "disabled"
        return result
    if not url:
        result["status"] = "error"
        result["error"] = "URL vide"
        return result

    import time as _time
    try:
        t0 = _time.monotonic()
        resp = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
        latency = round((_time.monotonic() - t0) * 1000)
        result["latency_ms"] = latency
        result["content_type"] = resp.headers.get("Content-Type", "")
        result["http_status"] = resp.status_code

        if resp.status_code >= 400:
            result["status"] = "error"
            result["error"] = f"HTTP {resp.status_code}"
        else:
            ct = (resp.headers.get("Content-Type") or "").lower()
            is_audio = any(t in ct for t in ["audio", "mpeg", "mp3", "ogg", "mpegurl", "octet-stream"])
            if is_audio:
                # Tenter de lire quelques octets pour vérifier que le flux envoie des données
                chunk = resp.raw.read(4096)
                if chunk and len(chunk) > 0:
                    result["status"] = "ok"
                    result["bytes_received"] = len(chunk)
                else:
                    result["status"] = "warning"
                    result["error"] = "Flux accessible mais aucune donnée reçue"
            else:
                result["status"] = "warning"
                result["error"] = f"Content-Type inattendu: {ct}"
        resp.close()
    except requests.exceptions.Timeout:
        result["status"] = "error"
        result["error"] = f"Timeout après {timeout}s"
    except requests.exceptions.ConnectionError as e:
        result["status"] = "error"
        result["error"] = f"Connexion refusée: {str(e)[:120]}"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


@router.get("/health-check")
def radio_health_check():
    """Vérifie l'accessibilité de TOUS les flux radio configurés.
    Retourne le statut de chaque flux + un résumé global."""
    streams = getattr(radio_service, "streams", {})
    if not streams:
        return {"success": False, "error": "Aucun flux configuré"}

    results = []
    for key, config in streams.items():
        results.append(_check_stream_health(key, config))

    ok = sum(1 for r in results if r["status"] == "ok")
    warning = sum(1 for r in results if r["status"] == "warning")
    error = sum(1 for r in results if r["status"] == "error")
    disabled = sum(1 for r in results if r["status"] == "disabled")

    return {
        "success": True,
        "summary": {
            "total": len(results),
            "ok": ok,
            "warning": warning,
            "error": error,
            "disabled": disabled,
            "health_score": round(ok / max(1, ok + warning + error) * 100),
        },
        "streams": results,
        "checked_at": datetime.now(TZ).isoformat(),
    }


@router.post("/health-check/{stream_key}")
def radio_health_check_single(stream_key: str):
    """Vérifie un flux radio spécifique."""
    streams = getattr(radio_service, "streams", {})
    if stream_key not in streams:
        raise HTTPException(status_code=404, detail=f"Flux '{stream_key}' introuvable")
    return {
        "success": True,
        "stream": _check_stream_health(stream_key, streams[stream_key]),
    }


# Variable pour stocker le dernier health-check auto
_last_auto_health: Dict[str, Any] = {}

def run_auto_health_check() -> Dict[str, Any]:
    """Exécute le health-check automatique (appelé par le scheduler).
    Stocke les résultats pour consultation ultérieure et log les erreurs."""
    global _last_auto_health
    streams = getattr(radio_service, "streams", {})
    if not streams:
        return {"error": "no_streams"}

    results = []
    for key, config in streams.items():
        results.append(_check_stream_health(key, config))

    ok = sum(1 for r in results if r["status"] == "ok")
    error_streams = [r for r in results if r["status"] == "error"]

    _last_auto_health = {
        "streams": results,
        "checked_at": datetime.now(TZ).isoformat(),
        "ok": ok,
        "errors": len(error_streams),
    }

    # Log les flux en erreur
    if error_streams:
        names = ", ".join(f"{r['name']} ({r['error']})" for r in error_streams)
        logger.warning(f"⚠️ Radio health-check: {len(error_streams)} flux en erreur — {names}")
    else:
        logger.info(f"✅ Radio health-check: {ok} flux OK")

    return _last_auto_health


@router.get("/health-check/last")
def radio_health_check_last():
    """Retourne le dernier résultat du health-check automatique."""
    if not _last_auto_health:
        return {"success": True, "message": "Aucun health-check automatique exécuté", "streams": []}
    return {"success": True, **_last_auto_health}