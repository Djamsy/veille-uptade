# backend/routers/publication_validation_routes.py
"""
Routes « publications pour validation ».

  Admin (JWT admin) — /api/publications/...
    GET    /status                     diagnostic configuration (chiffrement, feuille, Buffer)
    GET    /pending?status=            liste déchiffrée (sans jetons)
    GET    /pending/{id}               détail + journal d'audit
    POST   /pending                    création manuelle → renvoie le lien (une seule fois)
    POST   /pending/{id}/token         nouveau lien (l'ancien est invalidé)
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
from typing import Any, Dict, Optional

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
def create_pending(payload: Dict[str, Any] = Body(...), admin: dict = Depends(require_admin)):
    """Création manuelle. Le lien renvoyé n'est affiché qu'une fois."""
    try:
        ttl = payload.pop("ttl_hours", None)
        notify = bool(payload.pop("notify", True))
        res = svc.create_pending(payload, source="manual", actor=admin.get("email", ""),
                                 ttl_hours=int(ttl) if ttl else None, notify=notify)
        return {"ok": True, **res}
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
                                                   ttl_hours=int(ttl) if ttl else None)}
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
    """Publie sur Buffer. Accepte en option un multipart/form-data avec un champ `media`
    (image ou vidéo) : utile quand la feuille ne donne qu'un lien WeTransfer / Purevision."""
    extra: list = []
    try:
        if request.headers.get("content-type", "").startswith("multipart/"):
            form = await request.form()
            media_file = form.get("media")
            if media_file is not None and hasattr(media_file, "read"):
                import tempfile, os
                from backend.services.campaign_service import upload_to_cloudinary
                content = await media_file.read()
                if content:
                    ctype = getattr(media_file, "content_type", "") or ""
                    is_video = "video" in ctype or str(getattr(media_file, "filename", "")).lower().endswith((".mp4", ".mov", ".m4v", ".webm"))
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4" if is_video else ".jpg") as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    try:
                        hosted = upload_to_cloudinary(f"file://{tmp_path}", "video" if is_video else "image")
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                    if not hosted:
                        raise HTTPException(502, "Upload Cloudinary échoué (vérifier CLOUDINARY_*)")
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
