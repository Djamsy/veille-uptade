#!/usr/bin/env python3
"""
Script de rattrapage : réconcilie les données existantes en base.
À exécuter UNE FOIS après le déploiement du service de réconciliation.

Usage :
    # Mode simulation (rien ne change en base)
    python -m backend.reconcile_existing_data --dry-run

    # Mode live (écrit en base)
    python -m backend.reconcile_existing_data

    # Personnaliser la fenêtre temporelle
    python -m backend.reconcile_existing_data --days 7

    # Réconcilier aussi les affaires
    python -m backend.reconcile_existing_data --days 7 --affairs
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("reconcile_existing")


def main():
    parser = argparse.ArgumentParser(description="Réconciliation des données existantes")
    parser.add_argument("--days", type=int, default=3, help="Fenêtre en jours (défaut: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation")
    parser.add_argument("--affairs", action="store_true", help="Réconcilier aussi les affaires")
    parser.add_argument("--verbose", action="store_true", help="Logs détaillés")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("RÉCONCILIATION DES DONNÉES EXISTANTES")
    logger.info(f"Mode: {'SIMULATION' if args.dry_run else 'LIVE'}")
    logger.info(f"Fenêtre: {args.days} jours")
    logger.info(f"Affaires: {'OUI' if args.affairs else 'NON'}")
    logger.info("=" * 60)

    # Initialiser le service
    from backend.entity_reconciliation_service import EntityReconciliationService
    service = EntityReconciliationService()

    if service.db is None:
        logger.error("❌ Impossible de se connecter à MongoDB")
        sys.exit(1)

    # 1. Construire l'index des articles
    logger.info("\n📚 Construction de l'index des articles...")
    index_count = service.build_article_index(force=True)
    logger.info(f"   → {index_count} articles indexés")

    if index_count == 0:
        logger.warning("⚠️ Aucun article dans la fenêtre — rien à réconcilier")
        sys.exit(0)

    # 2. Réconcilier les transcriptions
    logger.info(f"\n📻 Réconciliation des transcriptions ({args.days} derniers jours)...")
    trans_stats = service.reconcile_recent_transcriptions(
        days=args.days, dry_run=args.dry_run
    )

    logger.info("\n📊 RÉSULTATS TRANSCRIPTIONS :")
    logger.info(f"   Total vérifiées   : {trans_stats.get('total', 0)}")
    logger.info(f"   Réconciliées      : {trans_stats.get('reconciled', 0)}")
    logger.info(f"   Sans match        : {trans_stats.get('no_match', 0)}")
    logger.info(f"   Ignorées          : {trans_stats.get('skipped', 0)}")
    logger.info(f"   Erreurs           : {trans_stats.get('errors', 0)}")

    # Détails des réconciliations
    if trans_stats.get("details"):
        logger.info("\n   📋 Détails des réconciliations :")
        for d in trans_stats["details"][:20]:
            logger.info(
                f"      • Transcription {d['id'][:8]}... → "
                f"Article: '{d['matched_article'][:50]}' "
                f"(score={d['score']:.2f}, entités={d['entities']})"
            )

    # 3. Réconcilier les affaires si demandé
    if args.affairs:
        logger.info(f"\n📁 Réconciliation des affaires ({args.days} derniers jours)...")
        affairs_stats = service.reconcile_recent_affairs(
            days=args.days, dry_run=args.dry_run
        )
        logger.info("\n📊 RÉSULTATS AFFAIRES :")
        logger.info(f"   Total vérifiées   : {affairs_stats.get('total', 0)}")
        logger.info(f"   Réconciliées      : {affairs_stats.get('reconciled', 0)}")
        logger.info(f"   Inchangées        : {affairs_stats.get('unchanged', 0)}")
        logger.info(f"   Erreurs           : {affairs_stats.get('errors', 0)}")

    logger.info("\n" + "=" * 60)
    if args.dry_run:
        logger.info("✅ SIMULATION TERMINÉE — aucune modification en base")
        logger.info("   Pour appliquer les changements, relancer SANS --dry-run")
    else:
        logger.info("✅ RÉCONCILIATION TERMINÉE — données mises à jour en base")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
