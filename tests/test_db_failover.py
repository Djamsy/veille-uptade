"""Test fonctionnel de la bascule MongoDB principal -> secours (backend/db_failover.py).

Deux « clusters » mongomock en mémoire, que l'on peut rendre injoignables à la
demande : toute opération lève alors ServerSelectionTimeoutError, comme Atlas
quand il refuse la connexion. Nécessite : pip install mongomock

Usage : python tests/test_db_failover.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MONGO_FAILOVER_TELEGRAM"] = "0"

import mongomock  # noqa: E402
from pymongo.errors import ServerSelectionTimeoutError  # noqa: E402

from backend.db_failover import (  # noqa: E402
    FALLBACK, PRIMARY, FailoverDatabase, FailoverRouter,
)


# ── Faux cluster débranchable ────────────────────────────────────────────────

class _Admin:
    def __init__(self, state):
        self._s = state

    def command(self, *a, **k):
        if self._s["down"]:
            raise ServerSelectionTimeoutError("SSL handshake failed (simulé)")
        return {"ok": 1}


class _FlakyCursor:
    def __init__(self, cursor, state):
        self._c, self._s = cursor, state

    def __getattr__(self, name):
        attr = getattr(self._c, name)

        def call(*a, **k):
            res = attr(*a, **k)
            return self if res is self._c else res
        return call if callable(attr) else attr

    def __iter__(self):
        return self

    def __next__(self):
        if self._s["down"]:
            raise ServerSelectionTimeoutError("SSL handshake failed (simulé)")
        return next(self._c)


class _Flaky:
    """Enveloppe une Database/Collection mongomock et échoue quand le cluster est down."""

    def __init__(self, target, state):
        object.__setattr__(self, "_t", target)
        object.__setattr__(self, "_s", state)

    def __getitem__(self, name):
        return _Flaky(self._t[name], self._s)

    def __getattr__(self, name):
        attr = getattr(self._t, name)
        if isinstance(attr, (mongomock.Database, mongomock.Collection)):
            return _Flaky(attr, self._s)
        if not callable(attr):
            return attr

        def call(*a, **k):
            if name == "find":  # paresseux, comme pymongo : l'erreur arrive à l'itération
                return _FlakyCursor(attr(*a, **k), self._s)
            if self._s["down"]:
                raise ServerSelectionTimeoutError("SSL handshake failed (simulé)")
            res = attr(*a, **k)
            if isinstance(res, (mongomock.Database, mongomock.Collection)):
                return _Flaky(res, self._s)
            return res
        return call


class FakeCluster:
    def __init__(self):
        self.state = {"down": False}
        self._client = mongomock.MongoClient()
        self.admin = _Admin(self.state)

    def __getitem__(self, name):
        return _Flaky(self._client[name], self.state)

    def raw(self, name="veille_media"):
        return self._client[name]


def make():
    p, f = FakeCluster(), FakeCluster()
    r = FailoverRouter(p, f, "veille_media")
    r.mirror_collections = ["users"]
    return p, f, r, FailoverDatabase(r)


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


# ── Scénarios ────────────────────────────────────────────────────────────────

def test_normal_mode():
    print("Mode normal")
    p, f, r, db = make()
    db.articles_guadeloupe.insert_one({"title": "a", "n": 2})
    db["articles_guadeloupe"].insert_one({"title": "b", "n": 1})
    check(p.raw().articles_guadeloupe.count_documents({}) == 2, "les écritures vont au principal")
    check(f.raw().articles_guadeloupe.count_documents({}) == 0, "rien sur le secours")
    titles = [d["title"] for d in db.articles_guadeloupe.find({}).sort("n", 1).limit(5)]
    check(titles == ["b", "a"], "find().sort().limit() fonctionne via le proxy")
    check(db.name == "veille_media", "db.name est exposé")
    check(not r.is_degraded(), "pas de mode dégradé")


def test_failover_resync():
    print("Panne, bascule, retour et resync")
    p, f, r, db = make()
    p.raw().articles_guadeloupe.create_index("article_id", unique=True, sparse=True)
    p.raw().articles_guadeloupe.insert_one({"_id": "old1", "article_id": "A1", "title": "historique"})
    p.raw().users.insert_one({"_id": "u1", "email": "admin@x"})
    p.raw().affairs.insert_one({"_id": "aff1", "title": "affaire existante", "score": 10})

    r.sync_indexes()
    r.mirror()
    check(f.raw().users.find_one({"_id": "u1"}) is not None, "les utilisateurs sont recopiés sur le secours")

    lazy = db.articles_guadeloupe.find({}).sort("title", 1)   # curseur créé AVANT la panne
    p.state["down"] = True

    db.articles_guadeloupe.insert_one({"_id": "new1", "article_id": "A2", "title": "pendant la panne"})
    check(r.active == FALLBACK and r.is_degraded(), "une écriture en échec déclenche la bascule")
    check(f.raw().articles_guadeloupe.find_one({"_id": "new1"}) is not None, "l'écriture est rejouée sur le secours")

    docs = list(lazy)
    check([d["_id"] for d in docs] == ["new1"], "un curseur ouvert avant la panne est rejoué sur le secours")

    check(db.users.find_one({"email": "admin@x"}) is not None, "connexion possible pendant la panne (miroir users)")

    # Même article que l'historique du principal (même article_id) -> doublon à la resync
    db.articles_guadeloupe.insert_one({"_id": "dup1", "article_id": "A1", "title": "re-scrapé"})
    # Nouvel utilisateur pendant la panne (collection miroir)
    db.users.insert_one({"_id": "u2", "email": "nouveau@x"})
    # Upsert partiel d'un document qui n'existe que sur le principal -> conflit
    db.affairs.update_one({"_id": "aff1"}, {"$set": {"score": 99}}, upsert=True)
    # Rush audio stocké directement sur le secours (GridFS, hors proxy)
    f.raw()["radio_audio.files"].insert_one({"_id": "audio1", "length": 10})

    p.state["down"] = False
    r.switch_to_primary()
    s = r.last_resync
    check(r.active == PRIMARY, "retour au principal")
    check(s["copied"] == 2 and s["duplicates"] == 1 and s["conflicts"] == 1 and s["errors"] == 0,
          "bilan resync : 2 copiés (article + utilisateur), 1 doublon, 1 conflit, 0 erreur")
    check(p.raw().articles_guadeloupe.find_one({"_id": "new1"}) is not None, "l'article de la panne est dans le principal")
    check(p.raw().articles_guadeloupe.find_one({"_id": "dup1"}) is None, "le doublon n'est pas inséré")
    check(p.raw().users.find_one({"_id": "u2"}) is not None, "le nouvel utilisateur est dans le principal")
    check(p.raw().affairs.find_one({"_id": "aff1"})["title"] == "affaire existante",
          "le principal n'est jamais écrasé par un document partiel")
    check(f.raw().articles_guadeloupe.count_documents({}) == 0, "le secours est vidé de ce qui a été recopié")
    check(f.raw().affairs.find_one({"_id": "aff1"}) is not None, "le conflit reste sur le secours pour examen")
    check(f.raw().users.count_documents({}) == 2, "le miroir users reste en place sur le secours")
    check(p.raw()["radio_audio.files"].count_documents({}) == 0
          and f.raw()["radio_audio.files"].count_documents({}) == 1,
          "l'audio radio reste sur le secours, jamais recopié vers le principal")

    again = r.resync()
    check(again["copied"] == 0 and again["errors"] == 0, "relancer la resync ne recopie rien (idempotent)")


def test_both_down():
    print("Principal ET secours injoignables")
    p, f, r, db = make()
    p.state["down"] = f.state["down"] = True
    try:
        db.articles_guadeloupe.insert_one({"x": 1})
        raise AssertionError("aurait dû lever")
    except ServerSelectionTimeoutError:
        pass
    check(r.active == PRIMARY, "pas de bascule vers un secours mort, l'erreur remonte")


def test_monitor():
    print("Surveillance automatique")
    p, f, r, db = make()
    r.check_interval = 0.05
    r.mirror_every = 10_000
    r.start_monitor()
    time.sleep(0.3)
    p.state["down"] = True
    deadline = time.time() + 3
    while r.active != FALLBACK and time.time() < deadline:
        time.sleep(0.02)
    check(r.active == FALLBACK, "2 pings ratés -> bascule sans aucune requête applicative")
    db.radio_transcriptions.insert_one({"_id": "t1", "text": "flash info"})
    p.state["down"] = False
    deadline = time.time() + 3
    while r.active != PRIMARY and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.1)
    r.stop_monitor()
    check(r.active == PRIMARY, "2 pings réussis -> retour au principal")
    check(p.raw().radio_transcriptions.find_one({"_id": "t1"}) is not None, "resync automatique au retour")


def test_skip_when_degraded():
    print("Analyses en pause en mode dégradé")
    import asyncio
    import backend.db as dbmod
    from backend.services.scheduler_service import _skip_when_degraded

    calls = []

    @_skip_when_degraded
    async def job():
        calls.append(1)
        return {"ok": True}

    orig = dbmod.is_degraded
    try:
        dbmod.is_degraded = lambda: True
        res = asyncio.run(job())
        check(res == {"skipped": "degraded_mode"} and not calls, "la tâche est ignorée en mode dégradé")
        dbmod.is_degraded = lambda: False
        res = asyncio.run(job())
        check(res == {"ok": True} and calls == [1], "la tâche tourne normalement sinon")
    finally:
        dbmod.is_degraded = orig


if __name__ == "__main__":
    test_normal_mode()
    test_failover_resync()
    test_both_down()
    test_monitor()
    test_skip_when_degraded()
    print("\n✅ TOUS LES TESTS PASSENT")
