# backend/db_failover.py
"""Bascule automatique MongoDB : cluster principal -> cluster de secours.

Activé uniquement si MONGO_URL_FALLBACK est défini. Sinon backend/db.py renvoie
une Database pymongo classique et ce module n'est jamais utilisé.

Principe
--------
- get_db() renvoie un proxy (FailoverDatabase) qui choisit la base active à
  CHAQUE opération. Les services qui gardent `self.db` en cache basculent donc
  sans redémarrage.
- Une opération qui échoue avec ServerSelectionTimeoutError sur le principal
  (la requête n'a jamais atteint le serveur, rejouer est sans risque) déclenche
  la bascule immédiate et est rejouée sur le secours.
- Un thread de surveillance ping le principal toutes les 15 s :
    * 2 échecs consécutifs  -> bascule vers le secours
    * 2 succès consécutifs  -> retour au principal + resynchronisation
- Resynchronisation (secours -> principal) : on INSÈRE ce qui manque, on
  n'écrase jamais un document du principal. Les documents recopiés sont
  retirés du secours, qui ne garde ainsi que ce qui reste à traiter.
- Miroir (principal -> secours) des petites collections de référence
  (utilisateurs, config…) pour que la connexion et les alertes marchent
  pendant une panne. Rafraîchi au démarrage puis toutes les 6 h.
- Les index du principal sont recopiés sur le secours (TTL compris).

Limites connues (documentées volontairement)
--------------------------------------------
- Le secours ne contient que l'activité de la panne + les collections miroir :
  l'historique n'est pas consultable pendant une panne.
- Une mise à jour, pendant la panne, d'un document qui n'existe que sur le
  principal est sans effet (le document n'est pas sur le secours).
- Si un document du secours a le même _id qu'un document du principal (hors
  collections miroir), il n'est pas recopié : il reste sur le secours et est
  compté comme « conflit » pour examen manuel.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.cursor import Cursor
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

logger = logging.getLogger("db_failover")

PRIMARY = "primary"
FALLBACK = "fallback"

DEFAULT_MIRROR = "users,alerts_config,watchlist,campaigns,push_subscriptions"


def _env_list(name: str, default: str) -> List[str]:
    return [c.strip() for c in os.getenv(name, default).split(",") if c.strip()]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class FailoverRouter:
    """Choisit la base active et gère la bascule / le retour / la resync."""

    def __init__(self, primary_client: MongoClient, fallback_client: MongoClient, db_name: str):
        self._clients = {PRIMARY: primary_client, FALLBACK: fallback_client}
        self.db_name = db_name
        self.active = PRIMARY
        self.switched_at: Optional[float] = None
        self.last_resync: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self._lock = threading.RLock()
        self._monitor: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._both_down_logged_at = 0.0
        self.check_interval = _env_float("MONGO_FAILOVER_CHECK_S", 15.0)
        self.ping_timeout = _env_float("MONGO_FAILOVER_PING_TIMEOUT_S", 5.0)
        self.mirror_every = _env_float("MONGO_FALLBACK_MIRROR_EVERY_S", 6 * 3600)
        self.mirror_collections = _env_list("MONGO_FALLBACK_MIRROR", DEFAULT_MIRROR)
        self.telegram_enabled = os.getenv("MONGO_FAILOVER_TELEGRAM", "1").strip().lower() not in ("0", "false", "no", "off")

    # ── Accès bruts ──────────────────────────────────────────────────────────
    def raw_db(self, target: str) -> Database:
        return self._clients[target][self.db_name]

    def active_db(self) -> Database:
        return self.raw_db(self.active)

    def is_degraded(self) -> bool:
        return self.active == FALLBACK

    def ping(self, target: str, timeout_s: Optional[float] = None) -> bool:
        try:
            with pymongo.timeout(timeout_s or self.ping_timeout):
                self._clients[target].admin.command("ping")
            return True
        except Exception as e:
            self.last_error = f"{target}: {type(e).__name__}: {str(e)[:200]}"
            return False

    # ── Exécution avec bascule ───────────────────────────────────────────────
    def run(self, fn: Callable[[Database], Any]) -> Any:
        target = self.active
        try:
            return fn(self.raw_db(target))
        except ServerSelectionTimeoutError:
            fallback_db = self.failover_from(target)
            if fallback_db is None:
                raise
            return fn(fallback_db)

    def failover_from(self, failed_target: str) -> Optional[Database]:
        """Le principal vient d'échouer : bascule si possible, renvoie la base de secours."""
        if failed_target != PRIMARY:
            return None
        self.switch_to_fallback("échec d'une opération sur le principal")
        return self.raw_db(FALLBACK) if self.active == FALLBACK else None

    def switch_to_fallback(self, reason: str) -> bool:
        with self._lock:
            if self.active == FALLBACK:
                return True
            if not self.ping(FALLBACK):
                if time.time() - self._both_down_logged_at > 300:  # pas plus d'un log / 5 min
                    logger.error("❌ Principal KO et secours injoignable — pas de bascule (%s)", self.last_error)
                    self._both_down_logged_at = time.time()
                return False
            self.active = FALLBACK
            self.switched_at = time.time()
        logger.error("🔀 MongoDB : bascule vers le cluster de SECOURS (%s)", reason)
        self._notify(
            "🔀 <b>MongoDB : bascule sur le cluster de secours</b>\n"
            f"Raison : {reason}\n"
            "Mode dégradé : collecte maintenue, analyses (affaires, rapports) en pause."
        )
        return True

    def switch_to_primary(self) -> None:
        with self._lock:
            if self.active == PRIMARY:
                return
            self.active = PRIMARY
            down_for = int(time.time() - (self.switched_at or time.time()))
            self.switched_at = None
        logger.warning("✅ MongoDB : retour sur le cluster PRINCIPAL (panne ~%ss) — resynchronisation", down_for)
        stats = self.resync()
        self._notify(
            "✅ <b>MongoDB : retour sur le cluster principal</b>\n"
            f"Panne : ~{down_for // 60} min\n"
            f"Resync : {stats.get('copied', 0)} copiés, {stats.get('duplicates', 0)} doublons, "
            f"{stats.get('conflicts', 0)} conflits, {stats.get('errors', 0)} erreurs"
        )

    # ── Surveillance ─────────────────────────────────────────────────────────
    def start_monitor(self) -> None:
        with self._lock:
            if self._monitor is not None and self._monitor.is_alive():
                return
            self._monitor = threading.Thread(target=self._monitor_loop, name="mongo-failover", daemon=True)
            self._monitor.start()

    def stop_monitor(self) -> None:
        self._stop.set()

    def _monitor_loop(self) -> None:
        fails = oks = 0
        last_mirror = 0.0
        first = True
        while not self._stop.is_set():
            if not first:
                self._stop.wait(self.check_interval)
                if self._stop.is_set():
                    return
            primary_ok = self.ping(PRIMARY)
            try:
                if self.active == PRIMARY:
                    fails = 0 if primary_ok else fails + 1
                    oks = 0
                    # Au démarrage, un seul échec suffit (personne n'a encore écrit nulle part)
                    if fails >= (1 if first else 2):
                        self.switch_to_fallback("le principal ne répond plus au ping")
                        fails = 0
                    elif primary_ok and time.time() - last_mirror >= self.mirror_every and self.ping(FALLBACK):
                        self.sync_indexes()
                        self.mirror()
                        last_mirror = time.time()
                else:
                    oks = oks + 1 if primary_ok else 0
                    fails = 0
                    if oks >= 2:
                        self.switch_to_primary()
                        oks = 0
            except Exception as e:  # la surveillance ne doit jamais mourir
                logger.exception("Surveillance failover : %s", e)
            first = False

    # ── Index & miroir (principal -> secours) ────────────────────────────────
    def sync_indexes(self) -> int:
        """Recopie sur le secours les index du principal (TTL, uniques, texte…)."""
        src, dst = self.raw_db(PRIMARY), self.raw_db(FALLBACK)
        created = 0
        for coll in src.list_collection_names():
            if coll.startswith("system."):
                continue
            for idx in src[coll].list_indexes():
                spec = dict(idx)
                name = spec.pop("name")
                if name == "_id_":
                    continue
                key = spec.pop("key")
                for k in ("v", "ns", "background"):
                    spec.pop(k, None)
                if "weights" in spec:  # index texte : la clé réelle est dans weights
                    keys = [(f, pymongo.TEXT) for f in spec["weights"]]
                else:
                    keys = list(key.items())
                try:
                    dst[coll].create_index(keys, name=name, **spec)
                    created += 1
                except Exception as e:
                    logger.debug("Index %s.%s non recopié : %s", coll, name, e)
        logger.info("🗂️ Index recopiés sur le secours : %s", created)
        return created

    def mirror(self) -> Dict[str, int]:
        """Copie les collections de référence du principal vers le secours (upsert par _id)."""
        src, dst = self.raw_db(PRIMARY), self.raw_db(FALLBACK)
        out: Dict[str, int] = {}
        for coll in self.mirror_collections:
            ops, n = [], 0
            for doc in src[coll].find({}):
                ops.append(pymongo.ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                if len(ops) >= 500:
                    dst[coll].bulk_write(ops, ordered=False)
                    n += len(ops)
                    ops = []
            if ops:
                dst[coll].bulk_write(ops, ordered=False)
                n += len(ops)
            out[coll] = n
        logger.info("🪞 Miroir principal -> secours : %s", out)
        return out

    # ── Resynchronisation (secours -> principal) ─────────────────────────────
    def resync(self, dry_run: bool = False) -> Dict[str, Any]:
        """Recopie dans le principal ce qui a été écrit sur le secours pendant la panne.

        - _id absent du principal  -> insertion, puis suppression du secours
        - doublon sur un index unique (ex. même article) -> déjà présent, retiré du secours
        - _id déjà présent : collection miroir -> normal, ignoré ; sinon -> conflit,
          laissé sur le secours pour examen manuel
        """
        src, dst = self.raw_db(FALLBACK), self.raw_db(PRIMARY)
        mirrored = set(self.mirror_collections)
        stats: Dict[str, Any] = {"copied": 0, "duplicates": 0, "conflicts": 0, "errors": 0,
                                 "dry_run": dry_run, "collections": {}}
        try:
            names = [c for c in src.list_collection_names() if not c.startswith("system.")]
        except Exception as e:
            logger.error("Resync impossible (secours injoignable) : %s", e)
            stats["errors"] += 1
            return stats

        for coll in names:
            c = {"copied": 0, "duplicates": 0, "conflicts": 0, "errors": 0}
            for doc in src[coll].find({}):
                _id = doc["_id"]
                try:
                    if dst[coll].find_one({"_id": _id}, {"_id": 1}) is not None:
                        if coll not in mirrored:
                            c["conflicts"] += 1
                        continue
                    if dry_run:
                        c["copied"] += 1
                        continue
                    try:
                        dst[coll].insert_one(doc)
                        c["copied"] += 1
                    except DuplicateKeyError:
                        c["duplicates"] += 1
                    if coll not in mirrored:
                        src[coll].delete_one({"_id": _id})
                except Exception as e:
                    c["errors"] += 1
                    logger.warning("Resync %s/%s : %s", coll, _id, e)
            if any(c.values()):
                stats["collections"][coll] = c
            for k in ("copied", "duplicates", "conflicts", "errors"):
                stats[k] += c[k]

        self.last_resync = {**stats, "at": time.time()}
        logger.warning("🔁 Resync secours -> principal : %s", {k: stats[k] for k in ("copied", "duplicates", "conflicts", "errors")})
        if stats["conflicts"]:
            logger.warning("⚠️ %s document(s) en conflit laissés sur le secours : lancer "
                           "backend/scripts/mongo_failover.py status pour le détail", stats["conflicts"])
        return stats

    # ── Divers ───────────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "fallback_configured": True,
            "active": self.active,
            "degraded": self.is_degraded(),
            "switched_at": self.switched_at,
            "last_error": self.last_error,
            "last_resync": self.last_resync,
            "mirror_collections": self.mirror_collections,
        }

    def _notify(self, text: str) -> None:
        if not self.telegram_enabled:
            return

        def _send():
            try:
                from backend.services.telegram_service import send_message
                send_message(text)
            except Exception as e:
                logger.debug("Alerte Telegram failover non envoyée : %s", e)

        threading.Thread(target=_send, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
#  Proxies : mêmes appels que pymongo, base résolue à chaque opération
# ═════════════════════════════════════════════════════════════════════════════

def _no_bool(self):
    # Même comportement que pymongo (évite les « if db: » silencieusement faux)
    raise NotImplementedError(
        f"{type(self).__name__} objects do not implement truth value testing or bool(). "
        "Please compare with None instead: obj is not None"
    )


class FailoverDatabase:
    def __init__(self, router: FailoverRouter):
        object.__setattr__(self, "_router", router)

    __bool__ = _no_bool

    @property
    def name(self) -> str:
        return self._router.db_name

    def get_collection(self, name: str, **kwargs) -> "FailoverCollection":
        return FailoverCollection(self._router, name, kwargs)

    def __getitem__(self, name: str) -> "FailoverCollection":
        return FailoverCollection(self._router, name, {})

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(Database, name, None)
        if attr is None:
            return FailoverCollection(self._router, name, {})
        if isinstance(attr, property):
            return getattr(self._router.active_db(), name)

        def call(*args, **kwargs):
            return self._router.run(lambda db: getattr(db, name)(*args, **kwargs))
        return call

    def __eq__(self, other):
        return isinstance(other, FailoverDatabase) and other._router is self._router

    def __hash__(self):
        return hash((id(self._router), "db"))

    def __repr__(self):
        return f"FailoverDatabase({self.name!r}, active={self._router.active})"


class FailoverCollection:
    def __init__(self, router: FailoverRouter, name: str, kwargs: Dict[str, Any]):
        object.__setattr__(self, "_router", router)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_kwargs", kwargs)

    __bool__ = _no_bool

    def _on(self, db: Database) -> Collection:
        return db.get_collection(self._name, **self._kwargs)

    @property
    def name(self) -> str:
        return self._name  # comme pymongo : "parent.enfant" pour une sous-collection

    @property
    def full_name(self) -> str:
        return f"{self._router.db_name}.{self._name}"

    def find(self, *args, **kwargs) -> "FailoverCursor":
        return FailoverCursor(self._router, lambda db: self._on(db).find(*args, **kwargs))

    def __getitem__(self, sub: str) -> "FailoverCollection":
        return FailoverCollection(self._router, f"{self._name}.{sub}", self._kwargs)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(Collection, name, None)
        if attr is None:
            return FailoverCollection(self._router, f"{self._name}.{name}", self._kwargs)
        if isinstance(attr, property):
            return getattr(self._on(self._router.active_db()), name)

        def call(*args, **kwargs):
            return self._router.run(lambda db: getattr(self._on(db), name)(*args, **kwargs))
        return call

    def __eq__(self, other):
        return (isinstance(other, FailoverCollection) and other._router is self._router
                and other._name == self._name)

    def __hash__(self):
        return hash((id(self._router), self._name))

    def __repr__(self):
        return f"FailoverCollection({self.full_name!r}, active={self._router.active})"


class FailoverCursor:
    """Curseur find() paresseux : si le principal tombe avant le 1er document,
    la requête (avec ses sort/limit/skip…) est rejouée sur le secours."""

    def __init__(self, router: FailoverRouter, build: Callable[[Database], Cursor]):
        self._router = router
        self._build_base = build
        self._calls: List[tuple] = []
        self._target = router.active
        self._cursor = build(router.raw_db(self._target))
        self._started = False

    def _rebuild(self, db: Database) -> Cursor:
        cur = self._build_base(db)
        for name, args, kwargs in self._calls:
            cur = getattr(cur, name)(*args, **kwargs)
        return cur

    def __getattr__(self, name: str):
        attr = getattr(self._cursor, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            result = attr(*args, **kwargs)
            if result is self._cursor:  # méthode chaînable (sort, limit, skip…)
                if not self._started:
                    self._calls.append((name, args, kwargs))
                return self
            return result
        return call

    def __iter__(self):
        return self

    def __next__(self):
        if self._started:
            return next(self._cursor)
        try:
            doc = next(self._cursor)
        except ServerSelectionTimeoutError:
            fallback_db = self._router.failover_from(self._target)
            if fallback_db is None:
                raise
            self._target = FALLBACK
            self._cursor = self._rebuild(fallback_db)
            doc = next(self._cursor)
        self._started = True
        return doc

    next = __next__

    def __getitem__(self, index):
        return self._cursor[index]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._cursor.close()
