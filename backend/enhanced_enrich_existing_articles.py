#!/usr/bin/env python3
"""
Script d'enrichissement amélioré avec IA locale (Ollama) + fallback GPT
Version optimisée utilisant le nouveau ai_service.py
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import time

# Imports MongoDB
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import certifi

# Import du nouveau service IA
try:
    from ai_service import ai_service
    AI_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Service IA non disponible: {e}")
    AI_AVAILABLE = False

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedArticleEnricher:
    def __init__(self):
        """Initialise l'enrichisseur avec IA locale"""
        
        # Configuration MongoDB
        self.mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.db_name = os.environ.get('DB_NAME', 'veille_media')
        self.collection_name = os.environ.get('ARTICLES_COLLECTION', 'articles_guadeloupe')
        
        # Connexion MongoDB
        self.client = None
        self.db = None
        self.collection = None
        self._connect_mongodb()
        
        # Vérification du service IA
        if AI_AVAILABLE:
            health = ai_service.health_check()
            logger.info(f"🤖 Service IA: {health['status']} (Ollama: {health['ollama_available']})")
        else:
            logger.warning("🚨 Service IA non disponible - mode dégradé")
        
        # Statistiques
        self.stats = {
            'processed': 0,
            'enriched': 0,
            'errors': 0,
            'ai_analyses': 0,
            'fallback_used': 0,
            'start_time': time.time()
        }
    
    def _connect_mongodb(self):
        """Connexion à MongoDB avec gestion d'erreurs"""
        try:
            if "mongodb+srv://" in self.mongo_url or "atlas" in self.mongo_url.lower():
                self.client = MongoClient(
                    self.mongo_url,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000,
                    maxPoolSize=20,
                    retryWrites=True,
                    retryReads=True,
                )
            else:
                self.client = MongoClient(
                    self.mongo_url,
                    serverSelectionTimeoutMS=20000,
                    connectTimeoutMS=20000,
                    socketTimeoutMS=20000
                )
            
            # Test de connexion
            self.client.admin.command("ping")
            logger.info("✅ Connexion MongoDB établie")
            
            # Base et collection
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            
            # Compter les articles
            total_articles = self.collection.count_documents({})
            articles_sans_ai = self.collection.count_documents({
                "$or": [
                    {"sentiment": {"$exists": False}},
                    {"theme_principal": {"$exists": False}},
                    {"ai_analysis_timestamp": {"$exists": False}}
                ]
            })
            
            logger.info(f"📊 Articles total: {total_articles:,}")
            logger.info(f"🔍 Articles à enrichir: {articles_sans_ai:,}")
            
        except ServerSelectionTimeoutError as e:
            logger.error(f"❌ Impossible de se connecter à MongoDB: {e}")
            self._print_connection_help()
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
            sys.exit(1)
    
    def _print_connection_help(self):
        """Aide en cas d'échec de connexion"""
        print("\n❌ Vérifiez:")
        print("  • Que MongoDB est accessible")
        print("  • Que l'URL de connexion est correcte")
        print("  • Que les variables d'environnement sont bien définies")
        print(f"  • URL actuelle: {self.mongo_url}")
    
    def get_articles_to_enrich(self, limit: int = None, days: int = None, force: bool = False) -> List[Dict]:
        """Récupère les articles à enrichir"""
        
        # Critères de base
        if force:
            # Mode force : tous les articles
            query = {}
        else:
            # Mode normal : articles sans enrichissement IA
            query = {
                "$or": [
                    {"sentiment": {"$exists": False}},
                    {"theme_principal": {"$exists": False}},
                    {"ai_analysis_timestamp": {"$exists": False}}
                ]
            }
        
        # Filtre temporel
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            query["published_date"] = {"$gte": cutoff_date}
        
        # Tri par date (plus récents en premier)
        cursor = self.collection.find(query).sort("published_date", -1)
        
        if limit:
            cursor = cursor.limit(limit)
        
        return list(cursor)
    
    def improve_content_extraction(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Améliore l'extraction de contenu si nécessaire"""
        
        # Si le contenu est vide ou très court, essayer d'extraire plus
        content = article.get("content", "") or article.get("text", "")
        title = article.get("title", "")
        
        # Si on n'a que le titre, c'est insuffisant pour l'IA
        if not content and title:
            article["content"] = title
            article["content_source"] = "title_only"
            logger.warning(f"📰 Article {article.get('_id')} n'a que le titre")
        
        elif len(content) < 100 and article.get("url"):
            # Contenu trop court, pourrait nécessiter un re-scraping
            article["content_source"] = "insufficient"
            logger.warning(f"📰 Contenu insuffisant pour {article.get('_id')}")
        
        else:
            article["content_source"] = "adequate"
        
        return article
    
    def enrich_single_article(self, article: Dict[str, Any], use_ai: bool = True) -> tuple[Dict[str, Any], bool]:
        """Enrichit un seul article avec la nouvelle IA"""
        
        try:
            # Améliorer le contenu si nécessaire
            article = self.improve_content_extraction(article)
            
            # Préparer les champs d'enrichissement
            enriched = article.copy()
            modified = False
            
            if use_ai and AI_AVAILABLE:
                # Utiliser le nouveau service IA
                try:
                    enriched = ai_service.enrich_article(article)
                    self.stats['ai_analyses'] += 1
                    modified = True
                    
                    # Vérifier si fallback GPT a été utilisé
                    if enriched.get('ai_fallback_used'):
                        self.stats['fallback_used'] += 1
                    
                    logger.debug(f"🤖 IA: {enriched.get('sentiment')} | {enriched.get('theme_principal')}")
                    
                except Exception as e:
                    logger.error(f"❌ Erreur IA pour {article.get('_id')}: {e}")
                    self.stats['errors'] += 1
                    # Continuer sans enrichissement IA
            
            # Enrichissement basique si IA non disponible
            if not modified:
                enriched.update({
                    'enrichment_timestamp': datetime.now().isoformat(),
                    'enrichment_method': 'basic_fallback',
                    'sentiment': 'unknown',
                    'theme_principal': 'general'
                })
                modified = True
            
            return enriched, modified
            
        except Exception as e:
            logger.error(f"❌ Erreur enrichissement {article.get('_id')}: {e}")
            self.stats['errors'] += 1
            return article, False
    
    def enrich_articles_batch(self, articles: List[Dict], dry_run: bool = False, batch_size: int = 50) -> int:
        """Enrichit les articles par lots"""
        
        total_enriched = 0
        
        # Traitement par lots
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            batch_enriched = []
            
            logger.info(f"📦 Traitement du lot {i//batch_size + 1} ({len(batch)} articles)")
            
            # Enrichir chaque article du lot
            for j, article in enumerate(batch):
                try:
                    enriched, modified = self.enrich_single_article(article)
                    
                    if modified:
                        batch_enriched.append(enriched)
                        total_enriched += 1
                    
                    self.stats['processed'] += 1
                    
                    # Progression
                    if (self.stats['processed']) % 25 == 0:
                        progress = (self.stats['processed'] / len(articles)) * 100
                        logger.info(f"⏳ Progression: {self.stats['processed']}/{len(articles)} ({progress:.1f}%)")
                
                except Exception as e:
                    logger.error(f"❌ Erreur article {j}: {e}")
                    self.stats['errors'] += 1
                    continue
            
            # Sauvegarde du lot
            if batch_enriched and not dry_run:
                try:
                    # Mise à jour en base par lot
                    bulk_operations = []
                    for enriched_article in batch_enriched:
                        article_id = enriched_article['_id']
                        update_data = {k: v for k, v in enriched_article.items() if k != '_id'}
                        
                        bulk_operations.append({
                            'updateOne': {
                                'filter': {'_id': article_id},
                                'update': {'$set': update_data}
                            }
                        })
                    
                    if bulk_operations:
                        result = self.collection.bulk_write(bulk_operations, ordered=False)
                        logger.info(f"💾 Lot sauvegardé: {result.modified_count} articles mis à jour")
                
                except Exception as e:
                    logger.error(f"❌ Erreur sauvegarde lot: {e}")
                    self.stats['errors'] += 1
            
            # Pause entre lots pour éviter la surcharge
            time.sleep(0.5)
        
        return total_enriched
    
    def print_final_stats(self, enriched_count: int, dry_run: bool = False):
        """Affiche les statistiques finales"""
        
        elapsed_time = time.time() - self.stats['start_time']
        
        print("\n" + "="*60)
        print("🎉 ENRICHISSEMENT TERMINÉ")
        print("="*60)
        print(f"📊 Articles traités: {self.stats['processed']:,}")
        print(f"✨ Articles enrichis: {enriched_count:,}")
        print(f"🤖 Analyses IA: {self.stats['ai_analyses']:,}")
        print(f"🔄 Fallbacks GPT: {self.stats['fallback_used']:,}")
        print(f"❌ Erreurs: {self.stats['errors']:,}")
        print(f"⏱️ Temps écoulé: {elapsed_time:.1f}s")
        
        if self.stats['processed'] > 0:
            success_rate = ((self.stats['processed'] - self.stats['errors']) / self.stats['processed']) * 100
            print(f"📈 Taux de succès: {success_rate:.1f}%")
        
        if AI_AVAILABLE:
            health = ai_service.health_check()
            print(f"🤖 État IA final: {health['status']}")
        
        if dry_run:
            print("\n🔍 Mode dry-run - aucune modification effectuée")
            print("   Relancez sans --dry-run pour appliquer les changements")
        
        print("="*60)
    
    def run_enrichment(self, args):
        """Lance l'enrichissement avec les paramètres donnés"""
        
        print("="*60)
        print("🏷️  ENRICHISSEMENT AUTOMATIQUE DES ARTICLES")
        print("="*60)
        print(f"📊 Base de données: {self.db_name}")
        print(f"📁 Collection: {self.collection_name}")
        print(f"🌐 MongoDB: {self.mongo_url[:50]}...")
        if AI_AVAILABLE:
            health = ai_service.health_check()
            print(f"🤖 IA locale: {health['status']} ({health['model']})")
        print(f"🔍 Mode: {'DRY-RUN (aucune modification)' if args.dry_run else 'ENRICHISSEMENT RÉEL'}")
        print("="*60)
        
        # Récupérer les articles à traiter
        logger.info("🔍 Recherche des articles à enrichir...")
        articles = self.get_articles_to_enrich(
            limit=args.limit,
            days=args.days,
            force=args.force
        )
        
        if not articles:
            logger.info("✅ Aucun article à enrichir trouvé")
            return
        
        logger.info(f"📋 {len(articles)} articles à traiter")
        
        if args.limit and len(articles) > args.limit:
            articles = articles[:args.limit]
            logger.info(f"🔒 Limité à: {args.limit}")
        
        # Démarrer l'enrichissement
        print("\n🔄 Démarrage du traitement...")
        enriched_count = self.enrich_articles_batch(
            articles=articles,
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )
        
        # Statistiques finales
        self.print_final_stats(enriched_count, args.dry_run)


def main():
    """Point d'entrée principal"""
    
    parser = argparse.ArgumentParser(description="Enrichissement automatique avec IA locale")
    parser.add_argument("--limit", type=int, help="Nombre max d'articles à traiter")
    parser.add_argument("--days", type=int, help="Traiter seulement les X derniers jours")
    parser.add_argument("--force", action="store_true", help="Forcer le re-traitement des articles déjà enrichis")
    parser.add_argument("--dry-run", action="store_true", help="Mode test - aucune modification en base")
    parser.add_argument("--batch-size", type=int, default=50, help="Taille des lots (défaut: 50)")
    
    args = parser.parse_args()
    
    # Vérifications
    if not AI_AVAILABLE:
        print("⚠️ Service IA non disponible - fonctionnement en mode dégradé")
        response = input("Continuer ? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Lancer l'enrichissement
    try:
        enricher = EnhancedArticleEnricher()
        enricher.run_enrichment(args)
    except KeyboardInterrupt:
        print("\n\n⚠️ Interruption utilisateur")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
