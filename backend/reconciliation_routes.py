# backend/reconciliation_routes.py
"""
Routes API pour le service de réconciliation entités/affaires.
Permet de :
- Lancer la réconciliation batch (transcriptions + affaires)
- Réconcilier une transcription individuelle
- Voir l'état du service et les stats
- Voir le log des réconciliations récentes
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Body

logger = logging.getLogger("reconciliation_routes")
router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

# Le service sera injecté par server.py
_service = None


def set_service(service):
    """Appelé par server.py pour injecter le service."""
    global _service
    _service = service


def _get_service():
    if _service is None:
        raise HTTPException(503, "Service de réconciliation non disponible")
    return _service


# ============================================================
# ROUTES
# ============================================================

@router.get("/health")
async def reconciliation_health():
    """État du service de réconciliation."""
    svc = _get_service()
    return svc.health_check()


@router.post("/transcriptions/batch")
async def reconcile_transcriptions_batch(
    days: int = Query(default=3, ge=1, le=14, description="Nombre de jours à réconcilier"),
    dry_run: bool = Query(default=False, description="Mode simulation (pas d'écriture en base)"),
):
    """
    Lance la réconciliation batch des transcriptions récentes.
    Compare chaque transcription avec les articles des N derniers jours.
    """
    svc = _get_service()
    try:
        stats = svc.reconcile_recent_transcriptions(days=days, dry_run=dry_run)
        return {
            "success": True,
            "mode": "dry_run" if dry_run else "live",
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Erreur batch transcriptions: {e}")
        raise HTTPException(500, f"Erreur réconciliation: {str(e)}")


@router.post("/affairs/batch")
async def reconcile_affairs_batch(
    days: int = Query(default=7, ge=1, le=30, description="Nombre de jours"),
    dry_run: bool = Query(default=False, description="Mode simulation"),
):
    """
    Lance la réconciliation batch des affaires récentes.
    Consolide les entités depuis les articles liés.
    """
    svc = _get_service()
    try:
        stats = svc.reconcile_recent_affairs(days=days, dry_run=dry_run)
        return {
            "success": True,
            "mode": "dry_run" if dry_run else "live",
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Erreur batch affaires: {e}")
        raise HTTPException(500, f"Erreur réconciliation affaires: {str(e)}")


@router.post("/transcription/single")
async def reconcile_single_transcription(
    transcription_id: str = Body(..., embed=True),
):
    """
    Réconcilie une transcription individuelle par son ID.
    """
    svc = _get_service()
    try:
        # Charger la transcription
        from bson import ObjectId
        trans = svc.transcriptions_col.find_one({"_id": ObjectId(transcription_id)})
        if not trans:
            raise HTTPException(404, "Transcription non trouvée")

        result = svc.reconcile_transcription(dict(trans))
        recon = result.get("_reconciliation", {})

        if recon.get("status") == "reconciled":
            # Sauvegarder
            svc.transcriptions_col.update_one(
                {"_id": trans["_id"]},
                {"$set": {
                    "elected": result.get("elected", []),
                    "institutions": result.get("institutions", []),
                    "entities": result.get("entities", []),
                    "theme": result.get("theme"),
                    "affair_id": result.get("affair_id"),
                    "is_affair": result.get("is_affair"),
                    "affair_type": result.get("affair_type"),
                    "gravity_score": result.get("gravity_score"),
                    "importance_score": result.get("importance_score"),
                    "linked_articles": result.get("linked_articles", []),
                    "_reconciliation": recon,
                }}
            )

        return {
            "success": True,
            "reconciliation": recon,
            "entities": result.get("elected", []),
            "institutions": result.get("institutions", []),
            "affair_id": result.get("affair_id"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur réconciliation single: {e}")
        raise HTTPException(500, str(e))


@router.get("/index/status")
async def article_index_status():
    """
    État de l'index des articles (taille, âge, contenu).
    """
    svc = _get_service()
    svc.build_article_index()

    # Résumé des entités dans l'index
    all_entities = set()
    themes_count = {}
    affairs_count = 0

    for art in svc._article_index:
        all_entities.update(art.get("entities", set()))
        theme = art.get("theme", "general")
        themes_count[theme] = themes_count.get(theme, 0) + 1
        if art.get("is_affair"):
            affairs_count += 1

    return {
        "index_size": len(svc._article_index),
        "index_age_minutes": (
            round((datetime.utcnow() - svc._index_built_at).total_seconds() / 60, 1)
            if svc._index_built_at else None
        ),
        "unique_entities": len(all_entities),
        "entities_list": sorted(all_entities)[:50],
        "themes_distribution": themes_count,
        "affairs_in_index": affairs_count,
    }


@router.get("/log/recent")
async def recent_reconciliations(
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Récupère les dernières réconciliations effectuées.
    """
    svc = _get_service()
    try:
        logs = list(
            svc.reconciliation_log
            .find()
            .sort("timestamp", -1)
            .limit(limit)
        )
        for log in logs:
            log["_id"] = str(log["_id"])
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/index/rebuild")
async def rebuild_article_index():
    """
    Force la reconstruction de l'index des articles.
    """
    svc = _get_service()
    count = svc.build_article_index(force=True)
    return {
        "success": True,
        "articles_indexed": count,
        "built_at": datetime.utcnow().isoformat(),
    }
