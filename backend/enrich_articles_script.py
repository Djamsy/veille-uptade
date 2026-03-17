# backend/enrich_existing_articles.py
"""
Script pour enrichir automatiquement les articles existants avec :
- themes : détection automatique depuis le titre/contenu
- elected : détection des personnalités mentionnées
- _tags : tags automatiques pour l'indexation

Usage:
    python enrich_existing_articles.py [--dry-run] [--limit 100] [--batch-size 50]
"""

import os
import re
import logging
from datetime import datetime
from typing import Dict, List, Any, Set
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
import argparse

# Configuration
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "veille_media")
ARTICLES_COLLECTION = os.environ.get("ARTICLES_COLLECTION", "articles_guadeloupe")

# Thèmes et patterns de détection (adaptés de analytics_routes.py)
THEMES_REGEX = [
    ("eau", r"\b(eau|robinet|coupure|siaeag|saur|cistern)\b"),
    ("sargasses", r"\b(sargasse|algues?\s*brunes?)\b"),
    ("cyclone", r"\b(ouragan|cyclone|temp(ê|e)te|vigilance)\b"),
    ("chlordecone", r"\b(chlord[ée]cone|pesticide|pollution|bananes?)\b"),
    ("social", r"\b(gr[èe]ve|blocage|manifestation|syndicat)\b"),
    ("justice", r"\b(tribunal|cour d'appel|procureur|condamn[ée]e?)\b"),
    ("transport", r"\b(bus|transport|circulation|embouteillage|route)\b"),
    ("education", r"\b(école|collège|lycée|université|éducation|enseignant|prof)\b"),
    ("sante", r"\b(santé|hôpital|chu|médecin|vaccin|covid|épidémie)\b"),
    ("economie", r"\b(économie|emploi|chômage|entreprise|commerce|tourisme)\b"),
    ("culture", r"\b(culture|festival|concert|musique|carnaval|créole)\b"),
    ("sport", r"\b(sport|football|basketball|athlétisme|natation|compétition)\b"),
    ("environnement", r"\b(environnement|pollution|déchets|recyclage|nature|biodiversité)\b"),
]

# Liste complète des élus de Guadeloupe (conseillers régionaux, départementaux et maires)
ELECTED_LIST = [
    # Conseil régional
    "Ary Chalus", "Jean Bardail", "Eddy Chateaubon", "Camille Elisabeth", "Valérie Estelle Samuel",
    "Jean-Marie Hubert", "Magaly Marcin", "Sylvie Dagonia", "Camille Pelage", "Corinne Petro",
    "Jean-Marie Pilli", "Sonia Taillepierre", "Hilaire Brudey", "Patrick Dollin", "Marie-Luce Penchard",
    "David Montout", "Gersiane Bondot-Galas", "Josette Borel-Lincertin", "Bernard Guillaume", "Chantal Lerus",
    "Philippe Dezac", "Marcelle Pierrot", "Betty Véronique Armougom", "Sylvie Chammougom Anno", "Jim Lapin",
    "Géraldine Naigre", "Aurélie Bitufwila", "Loïc Martol", "Sheila Moréna

def normalize_text(text: str) -> str:
    """Normalise le texte pour la recherche"""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.lower().strip())

def detect_themes(title: str, content: str = "") -> List[str]:
    """Détecte les thèmes dans le titre et contenu"""
    text = f"{title} {content}".lower()
    detected_themes = []
    
    for theme_id, pattern in THEMES_REGEX:
        if re.search(pattern, text, re.IGNORECASE):
            detected_themes.append(theme_id)
    
    return detected_themes

def detect_elected(title: str, content: str = "") -> List[str]:
    """Détecte les personnalités mentionnées"""
    text = f"{title} {content}".lower()
    detected_elected = []
    
    for person in ELECTED_LIST:
        # Recherche par nom complet et variations
        person_variations = [
            person.lower(),
            person.split()[-1].lower(),  # Nom de famille seulement
        ]
        
        for variation in person_variations:
            if len(variation) > 3 and re.search(rf"\b{re.escape(variation)}\b", text):
                detected_elected.append(person)
                break  # Éviter les doublons
    
    return list(set(detected_elected))  # Déduplique

def generate_tags(article: Dict[str, Any], themes: List[str], elected: List[str]) -> List[str]:
    """Génère les tags automatiques pour un article"""
    tags = set()
    
    # Tags de source
    if article.get("source"):
        source_name = normalize_text(str(article["source"]))
        tags.add(f"source:{source_name}")
    
    # Tags de site
    if article.get("site"):
        site_name = normalize_text(str(article["site"]))
        tags.add(f"site:{site_name}")
    
    # Tags de thèmes
    for theme in themes:
        tags.add(f"theme:{theme}")
    
    # Tags d'élus
    for person in elected:
        person_normalized = normalize_text(person.replace(" ", "-"))
        tags.add(f"elu:{person_normalized}")
    
    # Tag de date si disponible
    for date_field in ["published", "created_at", "captured_at", "scraped_at", "date"]:
        if article.get(date_field):
            try:
                if isinstance(article[date_field], str):
                    date_obj = datetime.fromisoformat(article[date_field].replace('Z', '+00:00'))
                else:
                    date_obj = article[date_field]
                date_str = date_obj.strftime("%Y-%m")
                tags.add(f"date:{date_str}")
                break
            except:
                continue
    
    return sorted(list(tags))

def enrich_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit un article avec themes, elected et _tags"""
    title = article.get("title", "")
    content = article.get("content", "") or article.get("text", "")
    
    # Détection automatique
    themes = detect_themes(title, content)
    elected = detect_elected(title, content)
    tags = generate_tags(article, themes, elected)
    
    # Préparation des updates
    updates = {}
    
    # Ajouter themes seulement si pas déjà présent ou vide
    if not article.get("themes") and themes:
        updates["themes"] = themes
    
    # Ajouter elected seulement si pas déjà présent ou vide
    if not article.get("elected") and elected:
        updates["elected"] = elected
    
    # Toujours mettre à jour _tags
    updates["_tags"] = tags
    
    # Métadonnées d'enrichissement
    updates["enriched_at"] = datetime.utcnow()
    updates["enrichment_version"] = "1.0"
    
    return updates

def main():
    parser = argparse.ArgumentParser(description="Enrichit les articles existants")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans modifications")
    parser.add_argument("--limit", type=int, help="Limite le nombre d'articles à traiter")
    parser.add_argument("--batch-size", type=int, default=100, help="Taille des lots de traitement")
    parser.add_argument("--force", action="store_true", help="Force la mise à jour même si déjà enrichi")
    
    args = parser.parse_args()
    
    # Configuration logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    try:
        # Connexion MongoDB
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        collection = db[ARTICLES_COLLECTION]
        
        logger.info(f"🔗 Connecté à {MONGO_URL}")
        logger.info(f"📁 Collection: {ARTICLES_COLLECTION}")
        
        # Construction du filtre
        query_filter = {}
        if not args.force:
            # Ne traiter que les articles non encore enrichis
            query_filter = {
                "$or": [
                    {"enriched_at": {"$exists": False}},
                    {"_tags": {"$exists": False}},
                    {"themes": {"$exists": False}},
                    {"elected": {"$exists": False}}
                ]
            }
        
        # Comptage total
        total_count = collection.count_documents(query_filter)
        logger.info(f"📊 Articles à traiter: {total_count}")
        
        if args.limit:
            total_count = min(total_count, args.limit)
            logger.info(f"📊 Limité à: {total_count}")
        
        if total_count == 0:
            logger.info("✅ Aucun article à enrichir")
            return
        
        # Traitement par lots
        processed = 0
        batch_operations = []
        
        cursor = collection.find(query_filter)
        if args.limit:
            cursor = cursor.limit(args.limit)
        
        for article in cursor:
            try:
                # Enrichissement de l'article
                updates = enrich_article(article)
                
                if updates and not args.dry_run:
                    operation = UpdateOne(
                        {"_id": article["_id"]},
                        {"$set": updates}
                    )
                    batch_operations.append(operation)
                
                processed += 1
                
                # Affichage du progrès
                if processed % 50 == 0:
                    logger.info(f"⏳ Traité: {processed}/{total_count}")
                
                # Exécution par lots
                if len(batch_operations) >= args.batch_size:
                    if not args.dry_run:
                        result = collection.bulk_write(batch_operations, ordered=False)
                        logger.info(f"💾 Lot sauvé: {result.modified_count} mises à jour")
                    batch_operations = []
                
            except Exception as e:
                logger.error(f"❌ Erreur sur article {article.get('_id')}: {e}")
                continue
        
        # Dernier lot
        if batch_operations and not args.dry_run:
            result = collection.bulk_write(batch_operations, ordered=False)
            logger.info(f"💾 Dernier lot: {result.modified_count} mises à jour")
        
        # Statistiques finales
        logger.info(f"🎉 Enrichissement terminé!")
        logger.info(f"📊 Articles traités: {processed}")
        
        if args.dry_run:
            logger.info("🔍 Mode dry-run - aucune modification effectuée")
        else:
            # Vérification post-traitement
            enriched_count = collection.count_documents({"enriched_at": {"$exists": True}})
            logger.info(f"✅ Articles enrichis en base: {enriched_count}")
            
            # Statistiques des thèmes détectés
            themes_stats = list(collection.aggregate([
                {"$unwind": "$themes"},
                {"$group": {"_id": "$themes", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]))
            
            if themes_stats:
                logger.info("📈 Top thèmes détectés:")
                for stat in themes_stats:
                    logger.info(f"   • {stat['_id']}: {stat['count']} articles")
            
            # Statistiques des élus détectés
            elected_stats = list(collection.aggregate([
                {"$unwind": "$elected"},
                {"$group": {"_id": "$elected", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]))
            
            if elected_stats:
                logger.info("👥 Top personnalités détectées:")
                for stat in elected_stats:
                    logger.info(f"   • {stat['_id']}: {stat['count']} mentions")
    
    except PyMongoError as e:
        logger.error(f"❌ Erreur MongoDB: {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ Erreur générale: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())