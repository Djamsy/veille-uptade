# backend/services/radio_audio_store.py
"""Stockage des rushs audio radio (GridFS « radio_audio ») + nettoyage automatique.

Où sont stockés les nouveaux fichiers audio
-------------------------------------------
- Sur le cluster de SECOURS si MONGO_URL_FALLBACK est défini (défaut), pour
  soulager le cluster principal. Forcer le principal : RADIO_AUDIO_STORE=primary.
- Sinon sur le cluster principal.
L'audio n'est jamais resynchronisé vers le principal (voir db_failover.resync).
La lecture cherche d'abord dans le stockage audio, puis dans le principal
(anciens fichiers enregistrés avant ce changement).

Nettoyage (tâche planifiée toutes les heures)
---------------------------------------------
Sur chaque cluster joignable :
1. supprime l'audio plus vieux que RADIO_AUDIO_RETENTION_DAYS (défaut 21 j) ;
2. sur le cluster de secours (512 Mo), supprime en plus les plus anciens
   tant que l'audio dépasse RADIO_AUDIO_MAX_MB (défaut 250 Mo) ;
3. supprime les chunks orphelins (radio_audio.chunks sans fichier) ;
4. retire le lien audio des transcriptions dont l'audio a été supprimé.
Le texte des transcriptions n'est jamais supprimé.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("radio_audio_store")

BUCKET = "radio_audio"
FILES = f"{BUCKET}.files"
CHUNKS = f"{BUCKET}.chunks"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def retention_days() -> int:
    return max(1, _int_env("RADIO_AUDIO_RETENTION_DAYS", 21))


def max_mb_fallback() -> int:
    return max(10, _int_env("RADIO_AUDIO_MAX_MB", 250))


def _fallback_db():
    """Database brute du cluster de secours, ou None s'il n'est pas configuré."""
    from backend.db import get_failover_router
    from backend.db_failover import FALLBACK
    router = get_failover_router()
    return router.raw_db(FALLBACK) if router is not None else None


def store_target() -> str:
    """'fallback' ou 'primary' : où sont écrits les nouveaux fichiers audio."""
    if (os.environ.get("RADIO_AUDIO_STORE") or "").strip().lower() == "primary":
        return "primary"
    return "fallback" if _fallback_db() is not None else "primary"


def get_audio_db():
    """Database brute (vraie pymongo Database, exigée par GridFS) pour écrire l'audio."""
    from backend.db import get_primary_db
    if store_target() == "fallback":
        return _fallback_db()
    return get_primary_db()


def read_dbs() -> List[Any]:
    """Bases où chercher un fichier audio, dans l'ordre (stockage audio, puis principal)."""
    from backend.db import get_primary_db
    dbs = [get_audio_db()]
    primary = get_primary_db()
    if store_target() != "primary":
        dbs.append(primary)
    return dbs


# ── Nettoyage ────────────────────────────────────────────────────────────────

def _delete_files(db, file_ids: List[Any]) -> int:
    """Supprime des fichiers GridFS (métadonnées + chunks). Renvoie les octets libérés."""
    if not file_ids:
        return 0
    freed = sum(d.get("length", 0) for d in db[FILES].find({"_id": {"$in": file_ids}}, {"length": 1}))
    db[CHUNKS].delete_many({"files_id": {"$in": file_ids}})
    db[FILES].delete_many({"_id": {"$in": file_ids}})
    return freed


def _unlink_transcriptions(file_ids: List[Any]) -> int:
    """Retire audio_file_id des transcriptions dont l'audio a disparu (lecteur cassé sinon)."""
    if not file_ids:
        return 0
    try:
        from backend.db import get_db
        res = get_db()["radio_transcriptions"].update_many(
            {"audio_file_id": {"$in": [str(i) for i in file_ids]}},
            {"$set": {"audio_file_id": None, "audio_purged_at": datetime.utcnow()}},
        )
        return res.modified_count
    except Exception as e:
        logger.warning("Nettoyage audio : liens transcriptions non mis à jour : %s", e)
        return 0


def cleanup_db(db, label: str, max_bytes: Optional[int], days: Optional[int] = None,
               dry_run: bool = False) -> Dict[str, Any]:
    days = days or retention_days()
    cutoff = datetime.utcnow() - timedelta(days=days)
    stats: Dict[str, Any] = {"store": label, "retention_days": days, "deleted_old": 0,
                             "deleted_over_cap": 0, "orphan_chunks": 0, "freed_mb": 0.0,
                             "remaining_mb": 0.0, "dry_run": dry_run}
    freed = 0
    deleted_ids: List[Any] = []

    # 1. Âge
    old_ids = [d["_id"] for d in db[FILES].find({"uploadDate": {"$lt": cutoff}}, {"_id": 1})]
    stats["deleted_old"] = len(old_ids)
    if old_ids and not dry_run:
        freed += _delete_files(db, old_ids)
        deleted_ids += old_ids

    # 2. Plafond de taille (plus anciens d'abord)
    if max_bytes is not None:
        files = list(db[FILES].find({}, {"_id": 1, "length": 1, "uploadDate": 1}).sort("uploadDate", 1))
        if dry_run:
            files = [f for f in files if f["_id"] not in set(old_ids)]
        total = sum(f.get("length", 0) for f in files)
        over: List[Any] = []
        for f in files:
            if total <= max_bytes:
                break
            over.append(f["_id"])
            total -= f.get("length", 0)
        stats["deleted_over_cap"] = len(over)
        if over and not dry_run:
            freed += _delete_files(db, over)
            deleted_ids += over

    # 3. Chunks orphelins
    file_ids = set(db[FILES].distinct("_id"))
    orphan_ids = [fid for fid in db[CHUNKS].distinct("files_id") if fid not in file_ids]
    stats["orphan_chunks_files"] = len(orphan_ids)
    if orphan_ids and not dry_run:
        stats["orphan_chunks"] = db[CHUNKS].delete_many({"files_id": {"$in": orphan_ids}}).deleted_count

    # 4. Liens des transcriptions
    if not dry_run:
        stats["transcriptions_unlinked"] = _unlink_transcriptions(deleted_ids)

    stats["freed_mb"] = round(freed / 1048576, 1)
    remaining = sum(d.get("length", 0) for d in db[FILES].find({}, {"length": 1}))
    stats["remaining_mb"] = round(remaining / 1048576, 1)
    return stats


def cleanup_all(dry_run: bool = False) -> List[Dict[str, Any]]:
    """Nettoie l'audio sur le principal et, s'il existe, sur le secours."""
    from backend.db import get_primary_db
    results = []
    targets = [("primary", get_primary_db(), None)]
    fb = _fallback_db()
    if fb is not None:
        targets.append(("fallback", fb, max_mb_fallback() * 1048576))
    for label, db, cap in targets:
        try:
            import pymongo
            with pymongo.timeout(5):
                db.client.admin.command("ping")
        except Exception as e:
            results.append({"store": label, "error": f"injoignable : {type(e).__name__}"})
            continue
        try:
            s = cleanup_db(db, label, cap, dry_run=dry_run)
            results.append(s)
            if s["deleted_old"] or s["deleted_over_cap"] or s.get("orphan_chunks"):
                logger.info("🧹 Audio radio (%s) : %s anciens + %s hors plafond supprimés, "
                            "%s chunks orphelins, %s Mo libérés, %s Mo restants",
                            label, s["deleted_old"], s["deleted_over_cap"], s.get("orphan_chunks", 0),
                            s["freed_mb"], s["remaining_mb"])
        except Exception as e:
            results.append({"store": label, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            logger.warning("🧹 Audio radio (%s) : nettoyage impossible : %s", label, str(e)[:200])
    return results
