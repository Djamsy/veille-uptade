# backend/routers/publication_validation_routes.py
"""
Routes « publications pour validation ».

  Admin (JWT admin) — /api/publications/...
    GET    /status                     diagnostic configuration (chiffrement, feuille, Buffer)
    GET    /pending?status=            liste déchiffrée (sans jetons)
    GET    /pending/{id}               détail + journal d'audit
    POST   /pending                    soumission (JSON ou multipart avec fichiers `media`) → lien (une seule fois)
    PUT    /pending/{id}               modification (texte, titre, options, médias) tant que non décidée
    POST   /pending/{id}/token         nouveau lien (l'ancien est invalidé) ; {notify:true} le renvoie aux validateurs
    DELETE /pending/{id}/token         révoque le lien
    POST   /pending/{id}/cancel        annule la demande
    POST   /pending/{id}/publish       publie une demande validée sur Buffer (action manuelle admin)
    DELETE /pending/{id}               suppression définitive
    POST   /sync-sheet                 import immédiat depuis la feuille

  Public par jeton (aucune authentification, limité en débit, non mis en cache)
    GET    /validate/{token}           aperçu pour le validateur
    POST   /validate/{token}           {decision: approve|reject, validator_name, comment?, edited_text?}
"""

import time
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, Body

from backend.routers.auth_routes import require_admin
from backend.services import publication_validation_service as svc

logger = logging.getLogger("veille.publications.routes")
router = APIRouter(prefix="/api/publications", tags=["publications-validation"])


# ── Limitation de débit (mémoire locale, suffisant pour un lien personnel) ──
_RATE: Dict[str, deque] = defaultdict(deque)
_RATE_LIMITS = {"read": (60, 60), "write": (10, 60), "miss": (10, 300)}  # (n, fenêtre s)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")) or "?"


def _rate_check(kind: str, ip: str) -> None:
    n, window = _RATE_LIMITS[kind]
    now = time.time()
    q = _RATE[f"{kind}:{ip}"]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "Trop de requêtes, réessayez dans quelques instants")
    q.append(now)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"


def _translate(e: Exception) -> HTTPException:
    if isinstance(e, svc.TokenInvalid):
        return HTTPException(404, str(e))
    if isinstance(e, svc.TokenExpired):
        return HTTPException(410, str(e))
    if isinstance(e, svc.AlreadyDecided):
        return HTTPException(409, str(e))
    if isinstance(e, svc.NotFound):
        return HTTPException(404, str(e))
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    logger.error("publications : %s", e, exc_info=True)
    return HTTPException(500, "Erreur interne")




# ── Hébergement d'un fichier reçu (image compressée / vidéo) sur Cloudinary ──
async def _host_upload(media_file) -> Optional[str]:
    """Reçoit un UploadFile (image ou vidéo), le dépose sur Cloudinary et renvoie son URL directe.
    None si le fichier est vide. Lève HTTPException 502 si Cloudinary échoue."""
    import os
    import tempfile
    from backend.services.campaign_service import upload_to_cloudinary

    if media_file is None or not hasattr(media_file, "read"):
        return None
    content = await media_file.read()
    if not content:
        return None
    ctype = (getattr(media_file, "content_type", "") or "").lower()
    fname = str(getattr(media_file, "filename", "") or "").lower()
    is_video = ctype.startswith("video") or fname.endswith((".mp4", ".mov", ".m4v", ".webm"))
    if not is_video and not (ctype.startswith("image") or fname.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))):
        raise HTTPException(400, f"Fichier non pris en charge : {fname or ctype or 'inconnu'} (image ou vidéo attendue)")
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (200 Mo max)")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4" if is_video else ".jpg") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        if not is_video:
            try:  # même traitement que /api/publish : max 1920 px, JPEG qualité 80
                from PIL import Image
                img = Image.open(tmp_path)
                if max(img.size) > 1920:
                    img.thumbnail((1920, 1920), Image.LANCZOS)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(tmp_path, "JPEG", quality=80, optimize=True)
            except Exception as e:
                logger.debug("compression image ignorée : %s", e)
        hosted = upload_to_cloudinary(f"file://{tmp_path}", "video" if is_video else "image")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    if not hosted:
        raise HTTPException(502, "Hébergement du média échoué (vérifier CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET)")
    return hosted


def _form_list(form, key: str) -> list:
    """Valeurs multiples d'un champ de formulaire (ex. plusieurs fichiers `media`)."""
    try:
        return [v for v in form.getlist(key)]
    except Exception:
        v = form.get(key)
        return [v] if v is not None else []


# ════════════════════════════════════════════════════════
#  ADMIN
# ════════════════════════════════════════════════════════

@router.get("/status")
def pub_status(admin: dict = Depends(require_admin)):
    try:
        rep = svc.status_report()
        rep["counts"] = svc.counts()
        return rep
    except Exception as e:
        raise _translate(e)


@router.get("/pending")
def list_pending(status: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500),
                 admin: dict = Depends(require_admin)):
    if status and status not in svc.ALL_STATUSES:
        raise HTTPException(400, f"status doit être parmi {svc.ALL_STATUSES}")
    try:
        return {"publications": svc.list_publications(status, limit), "counts": svc.counts()}
    except Exception as e:
        raise _translate(e)


@router.post("/pending")
async def create_pending(request: Request, admin: dict = Depends(require_admin)):
    """Soumet une publication à validation. Deux formes :
      - JSON : {title, text, media_urls[], networks[], requester, notes, ttl_hours, notify…}
      - multipart/form-data : mêmes champs + fichiers `media` (plusieurs possibles, images ou vidéos),
        hébergés sur Cloudinary avant chiffrement de la demande.
    Le lien renvoyé n'est affiché qu'une fois."""
    try:
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            payload: Dict[str, Any] = {k: form.get(k, "") for k in
                                       ("title", "text", "requester", "requester_email", "notes", "scheduled_for",
                                        "campaign_id", "campaign_name")}
            payload["networks"] = str(form.get("networks", "") or "")
            media_urls = [u.strip() for u in str(form.get("media_urls", "") or "").replace("\n", ",").split(",") if u.strip()]
            for f in _form_list(form, "media"):
                hosted = await _host_upload(f)
                if hosted:
                    media_urls.append(hosted)
            payload["media_urls"] = media_urls
            ttl = form.get("ttl_hours") or None
            notify = str(form.get("notify", "1")).lower() not in ("0", "false", "no", "off")
        else:
            payload = await request.json()
            ttl = payload.pop("ttl_hours", None)
            notify = bool(payload.pop("notify", True))
        res = svc.create_pending(payload, source="manual", actor=admin.get("email", ""),
                                 ttl_hours=int(ttl) if ttl else None, notify=notify)
        return {"ok": True, **res, "media_count": len(payload.get("media_urls") or [])}
    except HTTPException:
        raise
    except Exception as e:
        raise _translate(e)


@router.put("/pending/{pub_id}")
async def update_pending(pub_id: str, request: Request, admin: dict = Depends(require_admin)):
    """Modifie une publication en attente (texte, titre, options, médias).
    JSON : {title, text, networks, …, remove_media: [url], media_urls_add: [url]}
    multipart : mêmes champs + fichiers `media` à ajouter + `remove_media` (répétable ou séparé par des virgules)."""
    try:
        add: List[str] = []
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            changes = {k: form.get(k) for k in svc.EDITABLE_FIELDS if k in form}
            remove = [u.strip() for v in _form_list(form, "remove_media") for u in str(v).split(",") if u.strip()]
            add += [u.strip() for u in str(form.get("media_urls_add", "") or "").replace("\n", ",").split(",") if u.strip()]
            for f in _form_list(form, "media"):
                hosted = await _host_upload(f)
                if hosted:
                    add.append(hosted)
        else:
            body = await request.json()
            changes = {k: body.get(k) for k in svc.EDITABLE_FIELDS if k in body}
            remove = list(body.get("remove_media") or [])
            add += list(body.get("media_urls_add") or [])
        res = svc.update_publication(pub_id, changes, actor=admin.get("email", ""), add_media=add, remove_media=remove)
        return {"ok": True, **res}
    except HTTPException:
        raise
    except Exception as e:
        raise _translate(e)


@router.get("/pending/{pub_id}")
def get_pending(pub_id: str, admin: dict = Depends(require_admin)):
    try:
        return svc.get_publication(pub_id)
    except Exception as e:
        raise _translate(e)


@router.post("/pending/{pub_id}/token")
def regenerate_token(pub_id: str, payload: Dict[str, Any] = Body(default={}), admin: dict = Depends(require_admin)):
    try:
        ttl = payload.get("ttl_hours")
        return {"ok": True, **svc.regenerate_token(pub_id, actor=admin.get("email", ""),
                                                   ttl_hours=int(ttl) if ttl else None,
                                                   notify=bool(payload.get("notify", False)))}
    except Exception as e:
        raise _translate(e)


@router.delete("/pending/{pub_id}/token")
def revoke_token(pub_id: str, admin: dict = Depends(require_admin)):
    try:
        svc.revoke_token(pub_id, actor=admin.get("email", ""))
        return {"ok": True}
    except Exception as e:
        raise _translate(e)


@router.post("/pending/{pub_id}/cancel")
def cancel(pub_id: str, admin: dict = Depends(require_admin)):
    try:
        svc.cancel_publication(pub_id, actor=admin.get("email", ""))
        return {"ok": True}
    except Exception as e:
        raise _translate(e)


@router.post("/pending/{pub_id}/publish")
async def publish(pub_id: str, request: Request, admin: dict = Depends(require_admin)):
    """Publie sur Buffer. Accepte en option un multipart/form-data avec un ou plusieurs champs `media`
    (image ou vidéo) : utile quand la feuille ne donne qu'un lien WeTransfer / Purevision."""
    extra: list = []
    try:
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            for f in _form_list(form, "media"):
                hosted = await _host_upload(f)
                if hosted:
                    extra.append(hosted)
        return {"ok": True, **svc.publish_now(pub_id, actor=admin.get("email", ""), extra_media_urls=extra)}
    except HTTPException:
        raise
    except Exception as e:
        raise _translate(e)


@router.delete("/pending/{pub_id}")
def delete(pub_id: str, admin: dict = Depends(require_admin)):
    try:
        svc.delete_publication(pub_id)
        return {"ok": True}
    except Exception as e:
        raise _translate(e)


@router.post("/sync-sheet")
def sync_sheet(payload: Dict[str, Any] = Body(default={}), admin: dict = Depends(require_admin)):
    try:
        return svc.sync_from_sheet(notify=bool(payload.get("notify", True)))
    except Exception as e:
        raise _translate(e)


# ════════════════════════════════════════════════════════
#  VALIDATEUR (lien à jeton)
# ════════════════════════════════════════════════════════

@router.get("/validate/{token}")
def validate_preview(token: str, request: Request, response: Response):
    ip = _client_ip(request)
    _rate_check("read", ip)
    _no_store(response)
    try:
        return svc.get_by_token(token, ip=ip)
    except (svc.TokenInvalid, svc.TokenExpired) as e:
        _rate_check("miss", ip)  # freine l'énumération de jetons
        raise _translate(e)
    except Exception as e:
        raise _translate(e)


@router.post("/validate/{token}")
def validate_decide(token: str, request: Request, response: Response, payload: Dict[str, Any] = Body(...)):
    ip = _client_ip(request)
    _rate_check("write", ip)
    _no_store(response)
    try:
        return svc.decide(
            token,
            decision=str(payload.get("decision", "")),
            validator=str(payload.get("validator_name", "")),
            comment=str(payload.get("comment", "") or ""),
            edited_text=payload.get("edited_text"),
            ip=ip,
        )
    except (svc.TokenInvalid, svc.TokenExpired) as e:
        _rate_check("miss", ip)
        raise _translate(e)
    except Exception as e:
        raise _translate(e)
