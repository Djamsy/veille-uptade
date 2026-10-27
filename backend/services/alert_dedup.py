# backend/services/alert_dedup.py
"""Anti-doublon des alertes (Telegram, e-mail) : une même annonce n'est envoyée qu'une fois.

Le titre est normalisé par regex avant comparaison :
    « Guadeloupe. Feux dans la nuit ! »  ->  « feux dans la nuit »
    « FEUX DANS LA NUIT »                ->  « feux dans la nuit »
(accents, casse, ponctuation, espaces et préfixe de lieu « Guadeloupe. » neutralisés)

Les empreintes sont stockées en base (collection sent_alerts, _id unique,
expiration après ALERT_DEDUP_DAYS jours, 3 par défaut) : l'anti-doublon
résiste aux redémarrages, aux déploiements et à plusieurs instances
simultanées. Si la base est injoignable, repli sur une mémoire locale.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone

logger = logging.getLogger("alert_dedup")

COLLECTION = "sent_alerts"

# Préfixe de lieu en tête de titre : « Guadeloupe. », « Martinique : », « Basse-Terre - »…
_PLACE_PREFIX = re.compile(
    r"^(guadeloupe|martinique|guyane|caraibes?|antilles|outre[- ]mer|saint[- ]martin|"
    r"saint[- ]barthelemy|marie[- ]galante|basse[- ]terre|pointe[- ]a[- ]pitre)\s*[.:\-–—|]\s*"
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MIN_SIGNIFICANT = 20  # titre normalisé trop court (« Faits divers ») : on ajoute l'URL à la clé

_local_lock = threading.Lock()
_local: "OrderedDict[str, float]" = OrderedDict()
_index_ready = False


def normalize(text: str) -> str:
    """Forme canonique d'un titre pour la comparaison."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("’", "'").strip()
    t = _PLACE_PREFIX.sub("", t)
    t = _NON_ALNUM.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _key(channel: str, text: str, extra: str = "") -> str:
    norm = normalize(text)
    if len(norm) < _MIN_SIGNIFICANT and extra:
        norm = f"{norm}|{extra}"
    return hashlib.sha1(f"{channel}::{norm}".encode("utf-8")).hexdigest()


def _ttl_days() -> int:
    try:
        return max(1, int(os.environ.get("ALERT_DEDUP_DAYS", "3")))
    except ValueError:
        return 3


def _collection():
    global _index_ready
    from backend.db import get_db
    col = get_db()[COLLECTION]
    if not _index_ready:
        try:
            col.create_index("created_at", name="idx_sent_alerts_ttl",
                             expireAfterSeconds=_ttl_days() * 86400)
        except Exception as e:
            logger.debug("Index TTL sent_alerts : %s", e)
        _index_ready = True
    return col


def _claim_local(key: str) -> bool:
    with _local_lock:
        if key in _local:
            return False
        _local[key] = datetime.now(timezone.utc).timestamp()
        while len(_local) > 5000:
            _local.popitem(last=False)
        return True


def claim(channel: str, text: str, extra: str = "") -> bool:
    """True si l'annonce n'a pas encore été envoyée sur ce canal (et la réserve).

    channel : « telegram_article », « email_article », « telegram_radio »…
    text    : le titre (ou l'identifiant) de l'annonce
    extra   : complément de clé pour les titres trop courts (URL…)
    """
    if not normalize(text):
        return True
    key = _key(channel, text, extra)
    try:
        import pymongo
        from pymongo.errors import DuplicateKeyError
        try:
            with pymongo.timeout(3):  # ne jamais bloquer une alerte sur une base lente
                _collection().insert_one({
                    "_id": key, "channel": channel, "text": str(text)[:200],
                    "created_at": datetime.now(timezone.utc),
                })
            _claim_local(key)
            return True
        except DuplicateKeyError:
            logger.info("🔇 Annonce déjà envoyée (%s) : %s", channel, str(text)[:80])
            return False
    except Exception as e:
        # Base injoignable : on ne bloque pas les alertes, mémoire locale seulement
        logger.debug("Anti-doublon en base indisponible (%s) — mémoire locale", e)
        ok = _claim_local(key)
        if not ok:
            logger.info("🔇 Annonce déjà envoyée (%s, mémoire) : %s", channel, str(text)[:80])
        return ok
