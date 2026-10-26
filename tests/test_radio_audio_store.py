"""Test du nettoyage des rushs audio radio (backend/services/radio_audio_store.py).

Nécessite mongomock. Usage : python tests/test_radio_audio_store.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mongomock  # noqa: E402

import backend.services.radio_audio_store as store  # noqa: E402

MB = 1048576


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


def make_db():
    db = mongomock.MongoClient()["veille_media"]
    now = datetime.utcnow()
    files = [  # (id, âge en jours, taille Mo)
        ("vieux", 30, 10), ("j3", 3, 40), ("j2", 2, 40), ("j1", 1, 40), ("auj", 0, 40),
    ]
    for fid, age, size in files:
        db["radio_audio.files"].insert_one({"_id": fid, "length": size * MB, "uploadDate": now - timedelta(days=age)})
        db["radio_audio.chunks"].insert_many([{"files_id": fid, "n": i} for i in range(3)])
    db["radio_audio.chunks"].insert_many([{"files_id": "orphelin", "n": i} for i in range(2)])
    return db


def main():
    unlinked = []
    store._unlink_transcriptions = lambda ids: unlinked.extend(ids) or len(ids)

    print("Rétention + plafond (cluster de secours)")
    db = make_db()
    dry = store.cleanup_db(db, "fallback", max_bytes=100 * MB, days=21, dry_run=True)
    check(dry["deleted_old"] == 1 and dry["deleted_over_cap"] == 2, "simulation : 1 trop vieux + 2 hors plafond")
    check(db["radio_audio.files"].count_documents({}) == 5, "la simulation ne supprime rien")

    s = store.cleanup_db(db, "fallback", max_bytes=100 * MB, days=21)
    left = sorted(d["_id"] for d in db["radio_audio.files"].find())
    check(left == ["auj", "j1"], "garde les plus récents sous le plafond (80 Mo <= 100 Mo)")
    check(s["deleted_old"] == 1 and s["deleted_over_cap"] == 2, "1 supprimé pour l'âge, 2 pour le plafond")
    check(set(db["radio_audio.chunks"].distinct("files_id")) == {"auj", "j1"}, "chunks supprimés avec leurs fichiers, orphelins compris")
    check(s["freed_mb"] == 90.0 and s["remaining_mb"] == 80.0, "90 Mo libérés, 80 Mo restants")
    check(sorted(unlinked) == ["j2", "j3", "vieux"], "les transcriptions perdent le lien vers l'audio supprimé")

    print("Principal : rétention seule")
    db = make_db()
    s = store.cleanup_db(db, "primary", max_bytes=None, days=21)
    check(db["radio_audio.files"].count_documents({}) == 4 and s["deleted_over_cap"] == 0,
          "seul l'audio de plus de 21 jours est supprimé, pas de plafond")

    print("\n✅ TOUS LES TESTS PASSENT")


if __name__ == "__main__":
    main()
