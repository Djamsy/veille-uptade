#!/usr/bin/env python3
"""
Script de séparation d'affaires fusionnées à tort.
===================================================

Usage :
  python -m backend.scripts.split_merged_affairs

Ce script cherche l'affaire fusionnée "meurtre Guadeloupe + humanitaire RDC"
et sépare les articles RDC dans une nouvelle affaire distincte.

Il peut aussi servir de modèle pour séparer d'autres fusions incorrectes.
"""

import os
import sys
import re
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient

# ── Connexion MongoDB ──
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "veille_guadeloupe")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
affairs = db["affairs"]
articles = db["articles"]
timeline = db["affair_timeline"]


# ── Marqueurs géographiques ──
RDC_MARKERS = {
    "rdc", "congo", "république démocratique du congo",
    "kinshasa", "goma", "nord-kivu", "humanitaire",
    "humanitaire française", "ong",
}

GUADELOUPE_MARKERS = {
    "guadeloupe", "abymes", "les abymes", "pointe-à-pitre",
    "basse-terre", "baie-mahault", "971",
}


def find_problematic_affair():
    """Cherche l'affaire fusionnée contenant à la fois des refs Guadeloupe et RDC."""
    # Chercher les affaires actives contenant "meurtre" ou "tuée" dans le titre
    candidates = list(affairs.find({
        "status": {"$in": ["active", "stale"]},
        "$or": [
            {"title": {"$regex": "meurtre|tuée|tuee|balles|sécurité", "$options": "i"}},
            {"description": {"$regex": "meurtre|tuée|tuee|humanitaire|rdc|congo", "$options": "i"}},
        ]
    }))

    print(f"🔍 {len(candidates)} affaires candidates trouvées")

    for aff in candidates:
        title = aff.get("title", "")
        desc = aff.get("description", "")
        full_text = f"{title} {desc}".lower()

        # Vérifier si l'affaire mélange Guadeloupe et RDC/Congo
        has_local = any(m in full_text for m in GUADELOUPE_MARKERS)
        has_rdc = any(m in full_text for m in RDC_MARKERS)

        if has_local or has_rdc:
            print(f"\n📋 Affaire: {title[:80]}")
            print(f"   ID: {aff['_id']}")
            print(f"   Gravité: {aff.get('gravity_score', 0):.0%}")
            print(f"   Items: {aff.get('item_count', 0)}")
            print(f"   Articles: {len(aff.get('articles', []))}")
            print(f"   Local: {has_local}, RDC: {has_rdc}")

            # Lister les articles liés
            article_ids = aff.get("articles", [])
            if article_ids:
                for aid in article_ids:
                    try:
                        art = articles.find_one({"_id": ObjectId(aid) if isinstance(aid, str) else aid})
                        if art:
                            art_title = art.get("title", "?")[:60]
                            art_text = f"{art_title} {art.get('ai_summary', '')}".lower()
                            is_rdc = any(m in art_text for m in RDC_MARKERS)
                            is_local = any(m in art_text for m in GUADELOUPE_MARKERS)
                            tag = "🌍 RDC" if is_rdc else ("📍 GPE" if is_local else "❓")
                            print(f"      {tag} {art_title}")
                    except Exception as e:
                        print(f"      ⚠️ Erreur article {aid}: {e}")

    return candidates


def split_affair(affair_id: str, dry_run: bool = True):
    """
    Sépare une affaire en deux :
    - Les articles Guadeloupe restent dans l'affaire existante
    - Les articles RDC/hors-Guadeloupe sont déplacés dans une nouvelle affaire

    Args:
        affair_id: ID MongoDB de l'affaire à séparer
        dry_run: Si True, affiche ce qui serait fait sans modifier la DB
    """
    aff = affairs.find_one({"_id": ObjectId(affair_id)})
    if not aff:
        print(f"❌ Affaire {affair_id} introuvable")
        return

    print(f"\n{'='*60}")
    print(f"🔧 Séparation de: {aff.get('title', '?')[:80]}")
    print(f"{'='*60}")

    article_ids = aff.get("articles", [])
    local_articles = []
    foreign_articles = []

    for aid in article_ids:
        try:
            art = articles.find_one({"_id": ObjectId(aid) if isinstance(aid, str) else aid})
            if not art:
                continue

            art_title = art.get("title", "")
            art_summary = art.get("ai_summary", "") or ""
            art_text = f"{art_title} {art_summary}".lower()

            is_rdc = any(m in art_text for m in RDC_MARKERS)
            is_local = any(m in art_text for m in GUADELOUPE_MARKERS)

            if is_rdc and not is_local:
                foreign_articles.append(art)
                print(f"   🌍 → SÉPARER: {art_title[:60]}")
            else:
                local_articles.append(art)
                print(f"   📍 → GARDER:  {art_title[:60]}")
        except Exception as e:
            print(f"   ⚠️ Erreur: {e}")

    if not foreign_articles:
        print("\n⚠️ Aucun article étranger trouvé — rien à séparer")
        return

    if not local_articles:
        print("\n⚠️ Aucun article local trouvé — l'affaire entière est hors-Guadeloupe")
        print("   → Archivage recommandé plutôt que séparation")
        return

    print(f"\n📊 Résultat:")
    print(f"   Articles locaux (restent): {len(local_articles)}")
    print(f"   Articles étrangers (nouvelle affaire): {len(foreign_articles)}")

    if dry_run:
        print("\n🔒 DRY RUN — Aucune modification effectuée")
        print("   Relancez avec dry_run=False pour appliquer")
        return

    # ── Créer la nouvelle affaire pour les articles étrangers ──
    foreign_title = foreign_articles[0].get("title", "Affaire séparée")
    foreign_sources = list(set(a.get("source", "") for a in foreign_articles if a.get("source")))
    foreign_elected = []
    foreign_institutions = []
    for a in foreign_articles:
        foreign_elected.extend(a.get("elected", []) or [])
        foreign_institutions.extend(a.get("institutions", []) or [])
    foreign_elected = list(set(foreign_elected))
    foreign_institutions = list(set(foreign_institutions))

    max_gravity = max((a.get("gravity_score", 0) for a in foreign_articles), default=0)

    new_affair = {
        "title": foreign_title,
        "description": foreign_articles[0].get("ai_summary", ""),
        "status": "active",
        "gravity_score": max_gravity,
        "bmg": 0,
        "theme": foreign_articles[0].get("theme", "sécurité"),
        "elected": foreign_elected,
        "institutions": foreign_institutions,
        "sources": foreign_sources,
        "articles": [str(a["_id"]) for a in foreign_articles],
        "radio_transcriptions": [],
        "social_posts": [],
        "item_count": len(foreign_articles),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "_split_from": str(aff["_id"]),
        "_split_reason": "geographic_mismatch_correction",
    }

    result = affairs.insert_one(new_affair)
    new_id = result.inserted_id
    print(f"\n✅ Nouvelle affaire créée: {new_id}")
    print(f"   Titre: {foreign_title[:80]}")

    # ── Mettre à jour l'affaire originale (retirer les articles étrangers) ──
    foreign_ids = [str(a["_id"]) for a in foreign_articles]
    local_ids = [str(a["_id"]) for a in local_articles]
    local_sources = list(set(a.get("source", "") for a in local_articles if a.get("source")))
    local_elected = []
    local_institutions = []
    for a in local_articles:
        local_elected.extend(a.get("elected", []) or [])
        local_institutions.extend(a.get("institutions", []) or [])
    local_elected = list(set(local_elected))
    local_institutions = list(set(local_institutions))
    local_max_gravity = max((a.get("gravity_score", 0) for a in local_articles), default=aff.get("gravity_score", 0))

    affairs.update_one(
        {"_id": aff["_id"]},
        {"$set": {
            "articles": local_ids,
            "sources": local_sources,
            "elected": local_elected,
            "institutions": local_institutions,
            "item_count": len(local_articles),
            "gravity_score": local_max_gravity,
            "updated_at": datetime.utcnow(),
        }}
    )
    print(f"✅ Affaire originale mise à jour ({len(local_articles)} articles restants)")

    # ── Timeline entries ──
    timeline.insert_one({
        "affair_id": str(aff["_id"]),
        "event": "split",
        "detail": f"Articles hors-Guadeloupe séparés → nouvelle affaire {new_id}",
        "articles_removed": foreign_ids,
        "new_affair_id": str(new_id),
        "timestamp": datetime.utcnow(),
    })

    timeline.insert_one({
        "affair_id": str(new_id),
        "event": "created_from_split",
        "detail": f"Créée par séparation géographique depuis {aff['_id']}",
        "original_affair_id": str(aff["_id"]),
        "timestamp": datetime.utcnow(),
    })

    print(f"\n✅ Séparation terminée !")
    print(f"   Affaire locale: {aff['_id']} ({len(local_articles)} articles)")
    print(f"   Affaire étrangère: {new_id} ({len(foreign_articles)} articles)")


if __name__ == "__main__":
    print("🔍 Recherche des affaires mal fusionnées...\n")
    candidates = find_problematic_affair()

    if candidates:
        print("\n" + "="*60)
        print("Pour séparer une affaire, lancez dans un shell Python :")
        print("  from backend.scripts.split_merged_affairs import split_affair")
        print("  split_affair('AFFAIR_ID', dry_run=False)")
        print("="*60)
