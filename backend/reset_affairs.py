#!/usr/bin/env python3
"""
RESET SÛR DE LA COLLECTION `affairs`
====================================

Ce script permet de repartir de zéro avec la nouvelle logique de fusion
basée sur le contenu des articles (reference_text).

Étapes :
  1. Backup JSON de la collection `affairs` → backend/backups/affairs_<timestamp>.json
  2. Backup JSON de la collection `timeline_events` (si présente)
  3. Vide les collections `affairs` et `timeline_events`
  4. Réinitialise les flags `_affair_processed`, `_affair_id`, `_affair_ignored`,
     `_match_attempts` sur les articles, transcriptions radio et posts sociaux
     → le prochain cycle du pipeline recréera toutes les affaires avec la
       nouvelle logique content-based.

USAGE :
  python reset_affairs.py              # mode dry-run (n'écrit rien)
  python reset_affairs.py --confirm    # exécute réellement le reset
  python reset_affairs.py --confirm --skip-backup   # skip backup (déconseillé)

Le script REFUSE de s'exécuter sans --confirm par sécurité.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from pymongo import MongoClient
except ImportError:
    print("❌ pymongo n'est pas installé. `pip install pymongo`")
    sys.exit(1)

# Charger .env si dispo
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "veille_media")

BACKUP_DIR = Path(__file__).parent / "backups"


def _ser(obj):
    """JSON serializer pour ObjectId, datetime, etc."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def backup_collection(db, collection_name: str, timestamp: str) -> Path:
    """Dump une collection entière en JSON dans backups/."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    col = db[collection_name]
    docs = list(col.find({}))
    out = BACKUP_DIR / f"{collection_name}_{timestamp}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2, default=_ser)
    print(f"   💾 Backup {collection_name}: {len(docs)} documents → {out}")
    return out


def reset_affairs(confirm: bool, skip_backup: bool) -> int:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    try:
        client.admin.command("ismaster")
    except Exception as e:
        print(f"❌ Connexion MongoDB échouée : {e}")
        return 2
    db = client[DB_NAME]

    n_affairs = db["affairs"].count_documents({})
    n_timeline = db["timeline_events"].count_documents({}) if "timeline_events" in db.list_collection_names() else 0
    n_articles_processed = db["articles_guadeloupe"].count_documents({"_affair_processed": True})
    n_trans_processed = 0
    if "radio_transcriptions" in db.list_collection_names():
        n_trans_processed = db["radio_transcriptions"].count_documents({"_affair_processed": True})
    n_posts_processed = 0
    if "social_media_posts" in db.list_collection_names():
        n_posts_processed = db["social_media_posts"].count_documents({"_affair_processed": True})

    print("=" * 60)
    print("🔧 RESET AFFAIRS — DIAGNOSTIC")
    print("=" * 60)
    print(f"DB                    : {DB_NAME}")
    print(f"URL                   : {MONGO_URL.split('@')[-1]}")
    print(f"Affaires actuelles    : {n_affairs}")
    print(f"Timeline events       : {n_timeline}")
    print(f"Articles processés    : {n_articles_processed}")
    print(f"Transcriptions proc.  : {n_trans_processed}")
    print(f"Posts sociaux proc.   : {n_posts_processed}")
    print("=" * 60)

    if not confirm:
        print("⚠️  Mode DRY-RUN — aucune modification.")
        print("   Relance avec --confirm pour exécuter réellement le reset.")
        return 0

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if not skip_backup:
        print("\n📦 BACKUP en cours…")
        try:
            backup_collection(db, "affairs", ts)
            if n_timeline:
                backup_collection(db, "timeline_events", ts)
        except Exception as e:
            print(f"❌ Backup échoué : {e}")
            print("   Abandon — aucune suppression effectuée.")
            return 3
    else:
        print("⚠️  BACKUP SKIPPED (option --skip-backup)")

    print("\n🗑️  Suppression des collections…")
    del_affairs = db["affairs"].delete_many({}).deleted_count
    print(f"   ✓ affairs                 : {del_affairs} supprimées")

    if n_timeline:
        del_tl = db["timeline_events"].delete_many({}).deleted_count
        print(f"   ✓ timeline_events         : {del_tl} supprimés")

    print("\n♻️  Réinitialisation des flags de traitement…")
    flag_unset = {
        "_affair_processed": "",
        "_affair_id": "",
        "_affair_ignored": "",
        "_affair_ignore_reason": "",
        "_ignore_reason": "",
        "_match_attempts": "",
        "_match_last_attempt": "",
    }

    art_res = db["articles_guadeloupe"].update_many(
        {"_affair_processed": {"$exists": True}},
        {"$unset": flag_unset},
    )
    print(f"   ✓ articles_guadeloupe     : {art_res.modified_count} réinitialisés")

    if "radio_transcriptions" in db.list_collection_names():
        tr_res = db["radio_transcriptions"].update_many(
            {"_affair_processed": {"$exists": True}},
            {"$unset": flag_unset},
        )
        print(f"   ✓ radio_transcriptions    : {tr_res.modified_count} réinitialisés")

    if "social_media_posts" in db.list_collection_names():
        sp_res = db["social_media_posts"].update_many(
            {"_affair_processed": {"$exists": True}},
            {"$unset": flag_unset},
        )
        print(f"   ✓ social_media_posts      : {sp_res.modified_count} réinitialisés")

    if "topic_clusters" in db.list_collection_names():
        tc_res = db["topic_clusters"].delete_many({})
        print(f"   ✓ topic_clusters          : {tc_res.deleted_count} supprimés")

    print("\n✅ Reset terminé. Le prochain cycle du pipeline va recréer")
    print("   les affaires à partir des articles existants, avec la nouvelle")
    print("   logique de fusion basée sur le contenu (reference_text).")
    print()
    print("🔁 Pour déclencher le cycle immédiatement :")
    print("   - Via l'API : POST /api/affairs/cycle")
    print("   - Ou attendre le scheduler automatique")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Reset sûr de la collection affairs (avec backup).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Exécute réellement le reset (sinon dry-run).",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="N'effectue pas le backup (DÉCONSEILLÉ).",
    )
    args = parser.parse_args()

    try:
        rc = reset_affairs(confirm=args.confirm, skip_backup=args.skip_backup)
    except KeyboardInterrupt:
        print("\n⚠️  Interrompu par l'utilisateur.")
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
