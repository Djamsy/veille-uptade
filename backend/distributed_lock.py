"""
Lock distribué Mongo-based — empêche deux replicas de lancer le même job
simultanément (race condition multi-replica que `asyncio.Lock` ne protège pas).

Usage :

    from backend.distributed_lock import distributed_lock

    with distributed_lock("affair_cycle", ttl_seconds=600) as acquired:
        if not acquired:
            logger.info("Cycle déjà en cours sur une autre instance, skip")
            return
        ... travail ...

Si le détenteur crash sans release, le lock expire automatiquement après
`ttl_seconds`. Le TTL doit être > durée max attendue du job pour éviter
qu'un travail long ne libère sa propre clé.

Pour usage hors `with` :
    if try_acquire("name", 300):
        try:
            ...
        finally:
            release("name")
"""
from __future__ import annotations

import os
import logging
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

try:
    from backend.db import get_db  # type: ignore
except ImportError:
    from db import get_db  # type: ignore

logger = logging.getLogger("distributed_lock")

# Identifiant unique de ce process — apparaît dans les logs pour diag.
_HOLDER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _locks_col():
    db = get_db()
    return db["_distributed_locks"]


def try_acquire(name: str, ttl_seconds: int) -> bool:
    """Tente d'acquérir le lock `name` avec un TTL.

    Retourne True si on l'a obtenu, False sinon. Idempotent : si le même
    holder appelle deux fois, le second renouvelle l'expiration.
    """
    col = _locks_col()
    now = _now_utc()
    new_expires = now + timedelta(seconds=ttl_seconds)

    # 1) Tente l'upsert : insert si le doc n'existe pas OU si il a expiré.
    try:
        result = col.update_one(
            {
                "_id": name,
                "$or": [
                    {"expires_at": {"$lt": now}},
                    {"holder": _HOLDER_ID},  # renouveler son propre lock
                ],
            },
            {
                "$set": {
                    "holder": _HOLDER_ID,
                    "acquired_at": now,
                    "expires_at": new_expires,
                }
            },
            upsert=True,
        )
        return result.matched_count > 0 or result.upserted_id is not None
    except DuplicateKeyError:
        # Le doc existe avec un holder différent et un TTL encore valide.
        return False
    except Exception as e:
        # Erreur Mongo (réseau, etc.) — log et considère qu'on n'a pas le lock.
        # Évite qu'une erreur transitoire bypasse la protection.
        logger.warning(f"⚠️ distributed_lock '{name}': erreur acquire — {e}")
        return False


def release(name: str) -> bool:
    """Libère le lock `name` SEULEMENT si c'est nous qui le détenions.
    Retourne True si on a effectivement supprimé, False sinon.
    """
    col = _locks_col()
    try:
        result = col.delete_one({"_id": name, "holder": _HOLDER_ID})
        return result.deleted_count > 0
    except Exception as e:
        logger.warning(f"⚠️ distributed_lock '{name}': erreur release — {e}")
        return False


@contextmanager
def distributed_lock(name: str, ttl_seconds: int = 600):
    """Context manager : yield True si lock acquis, False sinon.

    L'appelant doit vérifier la valeur :

        with distributed_lock("cycle", 600) as ok:
            if not ok:
                return  # un autre worker bosse, on skip
            ... travail ...

    Le lock est libéré à la sortie du `with`, même en cas d'exception,
    SAUF si on n'a pas réussi à l'acquérir (rien à libérer).
    """
    acquired = try_acquire(name, ttl_seconds)
    try:
        yield acquired
    finally:
        if acquired:
            release(name)
