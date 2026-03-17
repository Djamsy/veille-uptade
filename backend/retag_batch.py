#!/usr/bin/env python3
"""
Script de re-tagging des articles par lots de 500
Version optimisée pour traitement de gros volumes
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Ajouter le chemin backend
sys.path.append(os.path.dirname(__file__))

from scraper_service import guadeloupe_scraper

class BatchRetagService:
    def __init__(self, batch_size: int = 500):
        self.batch_size = batch_size
        self.scraper = guadeloupe_scraper
        self.stats = {
            "total_found": 0,
            "total_processed": 0,
            "total_updated": 0,
            "total_errors": 0,
            "batches_completed": 0,
            "start_time": None,
            "end_time": None
        }

    def get_articles_to_retag(self, start_date: str = None, end_date: str = None, 
                            exclude_methods: List[str] = None) -> List[Dict]:
        """Récupère les articles à re-tagger avec pagination"""
        
        # Construire query MongoDB
        query = {}
        
        # Filtre par date
        if start_date:
            query["date"] = {"$gte": start_date}
            if end_date:
                query["date"]["$lte"] = end_date
        
        # Exclure les articles déjà traités avec la nouvelle méthode
        if exclude_methods is None:
            exclude_methods = ["mistral_optimized", "mistral_smart_entities"]
        
        if exclude_methods:
            query["analysis_method"] = {"$nin": exclude_methods}
        
        # Compter total
        total_count = self.scraper.articles_collection.count_documents(query)
        print(f"Total articles à traiter: {total_count}")
        
        return query, total_count

    def process_batch(self, articles: List[Dict], batch_num: int) -> Dict[str, int]:
        """Traite un lot d'articles"""
        
        batch_stats = {
            "processed": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0
        }
        
        print(f"\n--- BATCH {batch_num} : {len(articles)} articles ---")
        
        for i, article in enumerate(articles, 1):
            try:
                # Log progression
                if i % 50 == 0:
                    print(f"  Progress: {i}/{len(articles)} ({i/len(articles)*100:.1f}%)")
                
                # Re-analyser avec nouvelle logique
                original_entity = article.get("primary_entity", "N/A")
                original_theme = article.get("theme", "N/A")
                original_importance = article.get("importance_score", 0)
                
                # Log style scraping pour chaque article
                title = article.get("title", "")
                url = article.get("url", "")
                
                # ÉTAPE CRITIQUE : Ré-extraire le contenu depuis l'URL
                existing_content = article.get("content", "")
                if not existing_content or len(existing_content) < 100:
                    print(f"  📥 EXTRACTION CONTENU depuis: {url}")
                    content = self.scraper.extract_content_from_url(url)
                    article["content"] = content
                    content_length = len(content)
                    print(f"  📄 CONTENU EXTRAIT: {content_length} chars")
                else:
                    content_length = len(existing_content)
                    print(f"  📄 CONTENU EXISTANT: {content_length} chars")
                
                print(f"  🔍 ANALYSE ARTICLE: '{title[:60]}...'")
                
                enriched = self.scraper.enrich_article_with_mistral_force(article)
                
                # Log du résultat avec format identique au scraping
                method_status = "MISTRAL" if enriched.get("mistral_called") else "FALLBACK"
                sentiment_display = enriched.get("sentiment", {}).get("sentiment", "neutre")
                new_entity = enriched.get("primary_entity", "Aucune")
                new_theme = enriched.get("theme", "general")
                new_importance = enriched.get("importance_score", 0)
                
                print(f"  ✅ IA ({method_status}): {sentiment_display} | {new_theme} | Imp: {new_importance:.2f}")
                
                # Vérifier si changements significatifs
                has_changes = (
                    new_entity != original_entity or
                    new_theme != original_theme or
                    abs(new_importance - original_importance) > 0.1
                )
                
                if has_changes:
                    # Log des changements détaillés
                    changes = []
                    if new_entity != original_entity:
                        changes.append(f"Entité: '{original_entity}' → '{new_entity}'")
                    if new_theme != original_theme:
                        changes.append(f"Thème: '{original_theme}' → '{new_theme}'")
                    if abs(new_importance - original_importance) > 0.1:
                        changes.append(f"Importance: {original_importance:.2f} → {new_importance:.2f}")
                    
                    print(f"  🔄 CHANGEMENTS: {' | '.join(changes)}")
                    
                    # Créer une nouvelle affaire si nécessaire
                    affair_status = ""
                    if new_importance >= 0.7 and enriched.get("affaire_id"):
                        affair_status = " | Nouvelle affaire"
                        print(f"  🆕 AFFAIRE CRÉÉE: {enriched.get('affaire_id')}")
                    elif enriched.get("affaire_id"):
                        affair_status = " | Affaire mise à jour"
                        print(f"  📊 AFFAIRE MAJ: {enriched.get('affaire_id')}")
                    
                    # Mettre à jour en base
                    update_result = self.scraper.articles_collection.update_one(
                        {"id": article["id"]},
                        {"$set": {
                            "content": article.get("content", ""),  # Sauvegarder le contenu extrait
                            "primary_entity": enriched["primary_entity"],
                            "importance_score": enriched["importance_score"],
                            "theme": enriched["theme"],
                            "sentiment": enriched.get("sentiment", {}),
                            "entities_analysis": enriched.get("entities_analysis", []),
                            "analysis_method": enriched["analysis_method"],
                            "analysis_confidence": enriched.get("analysis_confidence", 0.5),
                            "retagged_at": datetime.now().isoformat(),
                            "content_extracted_at": datetime.now().isoformat(),
                            "retag_changes": {
                                "old_entity": original_entity,
                                "old_theme": original_theme,
                                "old_importance": original_importance
                            }
                        }}
                    )
                    
                    if update_result.modified_count > 0:
                        batch_stats["updated"] += 1
                        
                        # Log changements significatifs
                        if enriched.get("primary_entity") != original_entity:
                            print(f"    Entité: '{original_entity}' → '{enriched.get('primary_entity')}'")
                        
                else:
                    batch_stats["skipped"] += 1
                    print(f"  ⏭️  AUCUN CHANGEMENT: Entité='{new_entity}', Thème='{new_theme}', Imp={new_importance:.2f}")
                
                batch_stats["processed"] += 1
                
                # Ligne de séparation pour lisibilité
                print(f"  " + "-" * 80)
                
            except Exception as e:
                batch_stats["errors"] += 1
                print(f"  ERREUR article {article.get('id', 'unknown')}: {e}")
        
        print(f"Batch {batch_num} terminé: {batch_stats['updated']} mis à jour, {batch_stats['errors']} erreurs")
        return batch_stats

    def retag_articles(self, start_date: str = None, end_date: str = None, 
                      max_batches: int = None) -> Dict[str, Any]:
        """Lance le re-tagging par lots"""
        
        self.stats["start_time"] = datetime.now()
        print(f"DÉMARRAGE RE-TAGGING par lots de {self.batch_size}")
        print(f"Période: {start_date or 'début'} → {end_date or 'fin'}")
        print(f"Heure début: {self.stats['start_time']}")
        
        # Récupérer la query et le total
        query, total_count = self.get_articles_to_retag(start_date, end_date)
        self.stats["total_found"] = total_count
        
        if total_count == 0:
            print("Aucun article à traiter")
            return self.stats
        
        # Traitement par lots
        skip = 0
        batch_num = 1
        
        while skip < total_count:
            if max_batches and batch_num > max_batches:
                print(f"\nLimite de {max_batches} batches atteinte")
                break
            
            # Récupérer le lot actuel
            articles = list(self.scraper.articles_collection.find(query)
                          .skip(skip)
                          .limit(self.batch_size))
            
            if not articles:
                break
            
            # Traiter le lot
            batch_stats = self.process_batch(articles, batch_num)
            
            # Mettre à jour statistiques globales
            self.stats["total_processed"] += batch_stats["processed"]
            self.stats["total_updated"] += batch_stats["updated"]
            self.stats["total_errors"] += batch_stats["errors"]
            self.stats["batches_completed"] += 1
            
            # Pause entre lots pour éviter surcharge
            time.sleep(2)
            
            skip += self.batch_size
            batch_num += 1
        
        self.stats["end_time"] = datetime.now()
        
        # Rapport final
        self._print_final_report()
        
        return self.stats

    def _print_final_report(self):
        """Affiche le rapport final"""
        duration = self.stats["end_time"] - self.stats["start_time"]
        
        print(f"\n" + "="*60)
        print("RAPPORT FINAL RE-TAGGING")
        print("="*60)
        print(f"Articles trouvés:      {self.stats['total_found']:,}")
        print(f"Articles traités:      {self.stats['total_processed']:,}")
        print(f"Articles mis à jour:   {self.stats['total_updated']:,}")
        print(f"Erreurs:              {self.stats['total_errors']:,}")
        print(f"Batches complétés:    {self.stats['batches_completed']}")
        print(f"Durée totale:         {duration}")
        print(f"Articles/seconde:     {self.stats['total_processed']/duration.total_seconds():.1f}")
        
        if self.stats['total_processed'] > 0:
            success_rate = (self.stats['total_updated'] / self.stats['total_processed']) * 100
            print(f"Taux de mise à jour:  {success_rate:.1f}%")

    def retag_today(self):
        """Re-tague les articles d'aujourd'hui"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.retag_articles(start_date=today, end_date=today)

    def retag_last_n_days(self, days: int = 7):
        """Re-tague les N derniers jours"""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.retag_articles(start_date=start_date, end_date=end_date)

    def retag_with_old_smgeag_bias(self):
        """Re-tague spécifiquement les articles avec biais SMGEAG"""
        
        print("Recherche articles avec biais SMGEAG...")
        
        # Query spécifique pour articles avec SMGEAG comme entité principale
        query = {
            "primary_entity": {"$regex": "SMGEAG", "$options": "i"},
            "analysis_method": {"$nin": ["mistral_optimized"]}
        }
        
        articles = list(self.scraper.articles_collection.find(query))
        print(f"Trouvé {len(articles)} articles avec potentiel biais SMGEAG")
        
        if articles:
            return self.process_batch(articles, 1)
        
        return {"processed": 0, "updated": 0, "errors": 0, "skipped": 0}


def main():
    """Fonction principale avec options"""
    
    retagger = BatchRetagService(batch_size=500)
    
    print("Options de re-tagging:")
    print("1. Aujourd'hui seulement")
    print("2. 7 derniers jours")
    print("3. Période personnalisée")
    print("4. Articles avec biais SMGEAG")
    print("5. Tous les articles (ATTENTION: peut être long)")
    
    choice = input("\nChoisissez une option (1-5): ").strip()
    
    if choice == "1":
        retagger.retag_today()
    
    elif choice == "2":
        retagger.retag_last_n_days(7)
    
    elif choice == "3":
        start = input("Date début (YYYY-MM-DD): ").strip()
        end = input("Date fin (YYYY-MM-DD, optionnel): ").strip() or None
        max_batches = input("Limite batches (optionnel): ").strip()
        max_batches = int(max_batches) if max_batches else None
        
        retagger.retag_articles(start_date=start, end_date=end, max_batches=max_batches)
    
    elif choice == "4":
        retagger.retag_with_old_smgeag_bias()
    
    elif choice == "5":
        confirm = input("Êtes-vous sûr de vouloir re-tagger TOUS les articles? (oui/non): ")
        if confirm.lower() == "oui":
            max_batches = input("Limite batches pour sécurité (recommandé): ").strip()
            max_batches = int(max_batches) if max_batches else 20  # Sécurité
            retagger.retag_articles(max_batches=max_batches)
    
    else:
        print("Option invalide")


if __name__ == "__main__":
    main()