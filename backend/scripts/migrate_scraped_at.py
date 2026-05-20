#!/usr/bin/env python3
"""
Migration : convertit scraped_at string → ISODate dans articles_guadeloupe.

Problème : ~5700 articles ont scraped_at stocké comme chaîne ("2024-03-15T10:00:00")
au lieu d'un vrai type Date MongoDB. Conséquence : le pipeline d'affaires ne peut
pas les trier chronologiquement → ils restent bloqués dans le backlog.

Usage :
    python3 backend/scripts/migrate_scraped_at.py [--dry-run]

Options :
    --dry-run   Compte et affiche les docs concernés sans les modifier.
    --batch N   Taille des batches (défaut : 500).
"""

import argparse
import os
import sys
import time
from datetime import datetime

try:
    from pymongo import MongoClient, UpdateOne
    from pymongo.errors import BulkWriteError
except ImportError:
    print("❌ pymongo non installé : pip install pymongo")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────
MONGO_URL = os.environ.get(
    "MONGO_URL",
    "mongodb+srv://djamalloiseau:djamalloiseau@cluster0.kae7vjm.mongodb.net/"
    "veille_media?retryWrites=true&w=majority",
)
DB_NAME   = os.environ.get("MONGO_DB_NAME", "veille_media")
COL_NAME  = "articles_guadeloupe"


def connect():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=15000)
    client.admin.command("ping")   # lève une exception si pas de connexion
    return client[DB_NAME][COL_NAME]


def audit(col):
    """Retourne le nombre de docs avec scraped_at en string."""
    n_string = col.count_documents({"scraped_at": {"$type": "string"}})
    n_date   = col.count_documents({"scraped_at": {"$type": "date"}})
    n_absent = col.count_documents({"scraped_at": {"$exists": False}})
    total    = col.count_documents({})
    return {
        "total": total,
        "string": n_string,
        "date": n_date,
        "absent": n_absent,
    }


def run_migration(col, batch_size: int = 500, dry_run: bool = False):
    stats = audit(col)
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Audit avant migration :")
    print(f"  Total articles        : {stats['total']:,}")
    print(f"  scraped_at string     : {stats['string']:,}  ← à migrer")
    print(f"  scraped_at date       : {stats['date']:,}  ✅ déjà OK")
    print(f"  scraped_at absent     : {stats['absent']:,}")

    if stats["string"] == 0:
        print("\n✅ Rien à migrer — tous les scraped_at sont déjà des dates.")
        return

    if dry_run:
        print(f"\n[DRY-RUN] {stats['string']:,} documents seraient convertis.")
        # Montre quelques exemples
        samples = list(
            col.find({"scraped_at": {"$type": "string"}}, {"scraped_at": 1, "title": 1}).limit(5)
        )
        print("Exemples :")
        for s in samples:
            print(f"  scraped_at={s['scraped_at']!r}  title={s.get('title', '?')[:60]}")
        return

    # ── Migration par batch ($toDate via pipeline d'agrégation) ─────────────
    print(f"\n🔄 Migration en cours (batch={batch_size}) …")
    t0 = time.time()
    converted = 0
    errors    = 0

    cursor = col.find(
        {"scraped_at": {"$type": "string"}},
        {"_id": 1, "scraped_at": 1},
        batch_size=batch_size,
    )

    batch = []
    for doc in cursor:
        raw = doc.get("scraped_at", "")
        # Tente de parser — formats attendus : ISO8601 ou "YYYY-MM-DD HH:MM:SS"
        dt = None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except (ValueError, TypeError):
                continue

        if dt is None:
            # Fallback : laisser MongoDB convertir via $toDate
            batch.append(UpdateOne(
                {"_id": doc["_id"]},
                [{"$set": {"scraped_at": {"$toDate": "$scraped_at"}}}],
            ))
        else:
            batch.append(UpdateOne(
                {"_id": doc["_id"]},
                {"$set": {"scraped_at": dt}},
            ))

        if len(batch) >= batch_size:
            try:
                result = col.bulk_write(batch, ordered=False)
                converted += result.modified_count
            except BulkWriteError as e:
                errors += e.details.get("nInserted", 0)
                converted += e.details.get("nModified", 0)
            batch = []
            elapsed = time.time() - t0
            print(f"  … {converted:,} convertis ({elapsed:.1f}s)", end="\r", flush=True)

    # Dernier batch
    if batch:
        try:
            result = col.bulk_write(batch, ordered=False)
            converted += result.modified_count
        except BulkWriteError as e:
            errors += e.details.get("nInserted", 0)
            converted += e.details.get("nModified", 0)

    elapsed = time.time() - t0
    print(f"\n✅ Migration terminée en {elapsed:.1f}s")
    print(f"   Convertis : {converted:,}")
    if errors:
        print(f"   Erreurs   : {errors:,}  (docs laissés en string)")

    # Audit après
    print("\nAudit après migration :")
    stats_after = audit(col)
    print(f"  scraped_at string     : {stats_after['string']:,}")
    print(f"  scraped_at date       : {stats_after['date']:,}  ✅")


def main():
    parser = argparse.ArgumentParser(description="Migrate scraped_at string→date")
    parser.add_argument("--dry-run", action="store_true", help="Compte sans modifier")
    parser.add_argument("--batch",   type=int, default=500, help="Taille batch")
    args = parser.parse_args()

    print("🔌 Connexion MongoDB …")
    try:
        col = connect()
        print("✅ Connecté")
    except Exception as e:
        print(f"❌ Connexion échouée : {e}")
        sys.exit(1)

    run_migration(col, batch_size=args.batch, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
