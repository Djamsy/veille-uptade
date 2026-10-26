#!/usr/bin/env python3
"""Outil de supervision du cluster MongoDB de secours.

Lit MONGO_URL et MONGO_URL_FALLBACK dans l'environnement (ou backend/.env).

Usage (depuis la racine du repo) :
    python backend/scripts/mongo_failover.py check           # ping des deux clusters
    python backend/scripts/mongo_failover.py status          # ce qui attend sur le secours
    python backend/scripts/mongo_failover.py resync --dry-run
    python backend/scripts/mongo_failover.py resync          # secours -> principal
    python backend/scripts/mongo_failover.py prepare         # index + miroir principal -> secours
    python backend/scripts/mongo_failover.py audio-cleanup --dry-run   # nettoyage audio radio

La resync n'écrase jamais un document du principal : elle insère ce qui manque.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
os.environ["MONGO_FAILOVER_MONITOR"] = "0"     # pas de thread de surveillance ici
os.environ.setdefault("MONGO_FAILOVER_TELEGRAM", "0")

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / "backend" / ".env")
except ImportError:
    pass

from backend.db import get_failover_router  # noqa: E402
from backend.db_failover import FALLBACK, PRIMARY  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["check", "status", "resync", "prepare", "audio-cleanup"])
    parser.add_argument("--dry-run", action="store_true", help="resync : compter sans rien écrire")
    args = parser.parse_args()

    if args.command == "audio-cleanup":  # fonctionne aussi sans cluster de secours
        from backend.services.radio_audio_store import cleanup_all
        print(json.dumps(cleanup_all(dry_run=args.dry_run), indent=2, ensure_ascii=False, default=str))
        return 0

    router = get_failover_router()
    if router is None:
        print("❌ MONGO_URL_FALLBACK n'est pas défini (ou identique à MONGO_URL).")
        return 2

    if args.command == "check":
        for target in (PRIMARY, FALLBACK):
            ok = router.ping(target)
            print(f"{'✅' if ok else '❌'} {target:8} {'' if ok else router.last_error}")
        return 0

    if not router.ping(FALLBACK):
        print(f"❌ Secours injoignable : {router.last_error}")
        return 1

    if args.command == "status":
        db = router.raw_db(FALLBACK)
        mirrored = set(router.mirror_collections)
        print(f"Base : {router.db_name}   collections miroir : {', '.join(sorted(mirrored))}")
        for coll in sorted(c for c in db.list_collection_names() if not c.startswith("system.")):
            n = db[coll].estimated_document_count()
            if coll.startswith("radio_audio."):
                tag = "audio radio (reste sur le secours)"
            else:
                tag = "miroir" if coll in mirrored else ("à resynchroniser" if n else "vide")
            print(f"  {coll:32} {n:>7}  {tag}")
        return 0

    if not router.ping(PRIMARY):
        print(f"❌ Principal injoignable : {router.last_error}")
        return 1

    if args.command == "prepare":
        router.sync_indexes()
        print(json.dumps(router.mirror(), indent=2, ensure_ascii=False))
        return 0

    stats = router.resync(dry_run=args.dry_run)
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
    return 0 if not stats["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
