#!/usr/bin/env python3
"""
Script de retag des transcriptions radio avec validation des entités
Corrige les entités hallucinées par Mistral dans les transcriptions existantes
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pymongo import MongoClient
import certifi

# Ajouter le chemin backend pour importer ai_service
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ai_service import ai_service

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TranscriptionRetagger:
    def __init__(self):
        """Initialize retagger avec connexion MongoDB"""
        
        # Configuration MongoDB
        self.mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.db_name = os.environ.get("DB_NAME", "veille_media")
        self.transcripts_collection_name = os.environ.get("TRANSCRIPTS_COLLECTION", "radio_transcriptions")
        
        # Connexion MongoDB
        try:
            if "mongodb+srv://" in self.mongo_url or "atlas" in self.mongo_url.lower():
                self.client = MongoClient(
                    self.mongo_url,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=20000
                )
            else:
                self.client = MongoClient(self.mongo_url, serverSelectionTimeoutMS=20000)
            
            # Test connexion
            self.client.admin.command("ping")
            
            self.db = self.client[self.db_name]
            self.transcripts_coll = self.db[self.transcripts_collection_name]
            
            logger.info(f"✅ Connecté à MongoDB: {self.db_name}.{self.transcripts_collection_name}")
            
        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB: {e}")
            raise

    def get_transcriptions_stats(self) -> Dict[str, Any]:
        """Statistiques des transcriptions à retaguer"""
        try:
            total_transcriptions = self.transcripts_coll.count_documents({})
            
            # Transcriptions avec ai_keywords
            with_keywords = self.transcripts_coll.count_documents({
                "ai_keywords": {"$exists": True, "$ne": []}
            })
            
            # Transcriptions des 30 derniers jours
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            recent_transcriptions = self.transcripts_coll.count_documents({
                "captured_at": {"$gte": thirty_days_ago}
            })
            
            # Échantillon de transcriptions avec keywords suspects
            suspect_keywords_sample = list(self.transcripts_coll.find({
                "ai_keywords": {"$in": ["Nicolas Sarkozy", "Emmanuel Macron", "Marine Le Pen"]}
            }).limit(5))
            
            return {
                "total_transcriptions": total_transcriptions,
                "with_keywords": with_keywords,
                "recent_transcriptions": recent_transcriptions,
                "suspect_samples": len(suspect_keywords_sample),
                "sample_titles": [t.get("stream_name", "Unknown") for t in suspect_keywords_sample]
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération stats: {e}")
            return {}

    def retag_transcription(self, transcription: Dict[str, Any]) -> Dict[str, Any]:
        """Retag une transcription avec la validation d'entités"""
        try:
            # Récupérer le texte complet
            text_content = (
                transcription.get("transcription_text", "") + " " +
                transcription.get("ai_summary", "") + " " +
                transcription.get("gpt_analysis", "")
            ).strip()
            
            if not text_content or len(text_content) < 50:
                logger.warning(f"Transcription {transcription.get('_id')} : contenu insuffisant")
                return {"status": "skipped", "reason": "content_too_short"}
            
            # Anciens mots-clés (pour comparaison)
            old_keywords = transcription.get("ai_keywords", [])
            
            # Utiliser le nouveau ai_service avec validation
            if hasattr(ai_service, 'classify_transcription_advanced'):
                result = ai_service.classify_transcription_advanced(text_content)
                
                # Extraire les nouvelles entités validées
                entities_detected = result.get("entities_detected", {})
                validated_elus = entities_detected.get("elus", [])
                
                # Créer les nouveaux mots-clés validés
                new_keywords = []
                
                # Ajouter les élus validés
                new_keywords.extend(validated_elus)
                
                # Ajouter les services et mots critiques (déjà validés par détection)
                new_keywords.extend(entities_detected.get("services", []))
                new_keywords.extend(entities_detected.get("mots_critiques", []))
                
                # Nettoyer et dédupliquer
                new_keywords = list(set([k for k in new_keywords if k and k != "Aucune"]))
                
                return {
                    "status": "success",
                    "old_keywords": old_keywords,
                    "new_keywords": new_keywords,
                    "changes": {
                        "removed": list(set(old_keywords) - set(new_keywords)),
                        "added": list(set(new_keywords) - set(old_keywords)),
                        "kept": list(set(old_keywords) & set(new_keywords))
                    },
                    "method": result.get("method", "ai_service_validated")
                }
            else:
                # Fallback : validation manuelle des keywords existants
                validated_keywords = ai_service._validate_detected_entities(text_content, old_keywords)
                
                return {
                    "status": "fallback",
                    "old_keywords": old_keywords,
                    "new_keywords": validated_keywords,
                    "changes": {
                        "removed": list(set(old_keywords) - set(validated_keywords)),
                        "added": [],
                        "kept": validated_keywords
                    },
                    "method": "manual_validation"
                }
                
        except Exception as e:
            logger.error(f"Erreur retag transcription {transcription.get('_id')}: {e}")
            return {"status": "error", "error": str(e)}

    def bulk_retag(self, limit: int = 100, days_back: int = 30, dry_run: bool = True) -> Dict[str, Any]:
        """Retag en masse des transcriptions"""
        
        # Filtre temporel
        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        
        # Query pour les transcriptions à retaguer
        query = {
            "captured_at": {"$gte": cutoff_date},
            "ai_keywords": {"$exists": True, "$ne": []}
        }
        
        logger.info(f"🔄 Début retag - Limite: {limit}, Jours: {days_back}, Dry run: {dry_run}")
        
        # Récupérer les transcriptions
        transcriptions = list(self.transcripts_coll.find(query).limit(limit))
        
        if not transcriptions:
            logger.warning("Aucune transcription trouvée pour le retag")
            return {"total_processed": 0, "message": "Aucune transcription à traiter"}
        
        logger.info(f"📊 {len(transcriptions)} transcriptions à traiter")
        
        results = {
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "changes_summary": {
                "total_keywords_removed": 0,
                "total_keywords_added": 0,
                "most_removed_keywords": {},
                "most_added_keywords": {}
            },
            "sample_changes": []
        }
        
        for i, transcription in enumerate(transcriptions, 1):
            transcription_id = str(transcription.get("_id"))
            stream_name = transcription.get("stream_name", "Unknown")
            
            logger.info(f"[{i}/{len(transcriptions)}] Traitement: {stream_name} ({transcription_id[:8]}...)")
            
            # Retag
            retag_result = self.retag_transcription(transcription)
            results["total_processed"] += 1
            
            if retag_result["status"] == "success" or retag_result["status"] == "fallback":
                results["success_count"] += 1
                
                changes = retag_result.get("changes", {})
                removed = changes.get("removed", [])
                added = changes.get("added", [])
                
                # Statistiques des changements
                results["changes_summary"]["total_keywords_removed"] += len(removed)
                results["changes_summary"]["total_keywords_added"] += len(added)
                
                # Compter les mots-clés les plus supprimés/ajoutés
                for keyword in removed:
                    results["changes_summary"]["most_removed_keywords"][keyword] = \
                        results["changes_summary"]["most_removed_keywords"].get(keyword, 0) + 1
                
                for keyword in added:
                    results["changes_summary"]["most_added_keywords"][keyword] = \
                        results["changes_summary"]["most_added_keywords"].get(keyword, 0) + 1
                
                # Échantillon de changements significatifs
                if (len(removed) > 0 or len(added) > 0) and len(results["sample_changes"]) < 10:
                    results["sample_changes"].append({
                        "stream_name": stream_name,
                        "old_keywords": retag_result["old_keywords"],
                        "new_keywords": retag_result["new_keywords"],
                        "removed": removed,
                        "added": added
                    })
                
                # Mise à jour en base (si pas dry run)
                if not dry_run:
                    try:
                        self.transcripts_coll.update_one(
                            {"_id": transcription["_id"]},
                            {
                                "$set": {
                                    "ai_keywords": retag_result["new_keywords"],
                                    "retag_date": datetime.now().isoformat(),
                                    "retag_method": retag_result["method"]
                                }
                            }
                        )
                        logger.info(f"  ✅ Mise à jour sauvée : {len(removed)} supprimés, {len(added)} ajoutés")
                    except Exception as e:
                        logger.error(f"  ❌ Erreur sauvegarde: {e}")
                        results["error_count"] += 1
                        results["success_count"] -= 1
                else:
                    logger.info(f"  🔍 Dry run : {len(removed)} à supprimer, {len(added)} à ajouter")
                    
            elif retag_result["status"] == "skipped":
                results["skipped_count"] += 1
                logger.info(f"  ⏭️ Ignoré: {retag_result.get('reason', 'unknown')}")
                
            else:  # error
                results["error_count"] += 1
                logger.error(f"  ❌ Erreur: {retag_result.get('error', 'unknown')}")
        
        # Trier les mots-clés les plus affectés
        results["changes_summary"]["most_removed_keywords"] = dict(
            sorted(results["changes_summary"]["most_removed_keywords"].items(), 
                   key=lambda x: x[1], reverse=True)[:10]
        )
        results["changes_summary"]["most_added_keywords"] = dict(
            sorted(results["changes_summary"]["most_added_keywords"].items(), 
                   key=lambda x: x[1], reverse=True)[:10]
        )
        
        return results

    def retag_specific_keywords(self, suspect_keywords: List[str], dry_run: bool = True) -> Dict[str, Any]:
        """Retag spécifiquement les transcriptions contenant des mots-clés suspects"""
        
        logger.info(f"🎯 Retag ciblé pour mots-clés suspects: {suspect_keywords}")
        
        # Query pour transcriptions avec mots-clés suspects
        query = {"ai_keywords": {"$in": suspect_keywords}}
        
        transcriptions = list(self.transcripts_coll.find(query))
        
        if not transcriptions:
            return {"message": f"Aucune transcription trouvée avec les mots-clés: {suspect_keywords}"}
        
        logger.info(f"🔍 {len(transcriptions)} transcriptions trouvées avec mots-clés suspects")
        
        results = {"processed": 0, "cleaned": 0, "unchanged": 0, "details": []}
        
        for transcription in transcriptions:
            retag_result = self.retag_transcription(transcription)
            results["processed"] += 1
            
            if retag_result["status"] in ["success", "fallback"]:
                changes = retag_result.get("changes", {})
                removed = changes.get("removed", [])
                
                # Vérifier si des mots-clés suspects ont été supprimés
                suspect_removed = [k for k in removed if k in suspect_keywords]
                
                if suspect_removed:
                    results["cleaned"] += 1
                    results["details"].append({
                        "stream_name": transcription.get("stream_name", "Unknown"),
                        "suspect_removed": suspect_removed,
                        "all_removed": removed
                    })
                    
                    # Mise à jour si pas dry run
                    if not dry_run:
                        self.transcripts_coll.update_one(
                            {"_id": transcription["_id"]},
                            {"$set": {"ai_keywords": retag_result["new_keywords"]}}
                        )
                else:
                    results["unchanged"] += 1
        
        return results

def main():
    """Fonction principale avec menu interactif"""
    
    print("🔄 Script de retag des transcriptions radio")
    print("=" * 50)
    
    try:
        retagger = TranscriptionRetagger()
        
        # Afficher les stats
        stats = retagger.get_transcriptions_stats()
        print(f"📊 Statistiques:")
        print(f"   Total transcriptions: {stats.get('total_transcriptions', 0)}")
        print(f"   Avec mots-clés: {stats.get('with_keywords', 0)}")
        print(f"   Récentes (30j): {stats.get('recent_transcriptions', 0)}")
        print(f"   Échantillons suspects: {stats.get('suspect_samples', 0)}")
        
        if stats.get("sample_titles"):
            print(f"   Exemples suspects: {', '.join(stats['sample_titles'][:3])}")
        
        print("\n" + "=" * 50)
        print("Options disponibles:")
        print("1. Test dry run (10 transcriptions)")
        print("2. Retag récent (100 transcriptions, 7 jours)")
        print("3. Retag étendu (500 transcriptions, 30 jours)")
        print("4. Nettoyage ciblé (mots-clés suspects)")
        print("5. Retag complet (ATTENTION: toutes les transcriptions)")
        
        choice = input("\nVotre choix (1-5): ").strip()
        
        if choice == "1":
            print("\n🧪 Test dry run...")
            results = retagger.bulk_retag(limit=10, days_back=7, dry_run=True)
            
        elif choice == "2":
            confirm = input("Confirmer retag récent (100 transcriptions) ? (oui/non): ")
            if confirm.lower() in ['oui', 'o', 'yes', 'y']:
                results = retagger.bulk_retag(limit=100, days_back=7, dry_run=False)
            else:
                results = retagger.bulk_retag(limit=100, days_back=7, dry_run=True)
                
        elif choice == "3":
            confirm = input("Confirmer retag étendu (500 transcriptions) ? (oui/non): ")
            if confirm.lower() in ['oui', 'o', 'yes', 'y']:
                results = retagger.bulk_retag(limit=500, days_back=30, dry_run=False)
            else:
                results = retagger.bulk_retag(limit=500, days_back=30, dry_run=True)
                
        elif choice == "4":
            suspects = ["Nicolas Sarkozy", "Emmanuel Macron", "Marine Le Pen", "Donald Trump"]
            confirm = input(f"Nettoyer les mots-clés suspects {suspects} ? (oui/non): ")
            dry_run = confirm.lower() not in ['oui', 'o', 'yes', 'y']
            results = retagger.retag_specific_keywords(suspects, dry_run=dry_run)
            
        elif choice == "5":
            confirm = input("⚠️  ATTENTION: Retag COMPLET. Êtes-vous sûr ? (tapez 'CONFIRMER'): ")
            if confirm == "CONFIRMER":
                results = retagger.bulk_retag(limit=10000, days_back=365, dry_run=False)
            else:
                print("Annulé.")
                return
        else:
            print("Choix invalide.")
            return
        
        # Afficher les résultats
        print("\n" + "=" * 50)
        print("📈 RÉSULTATS:")
        
        if "total_processed" in results:
            print(f"   Transcriptions traitées: {results['total_processed']}")
            print(f"   Succès: {results['success_count']}")
            print(f"   Erreurs: {results['error_count']}")
            print(f"   Ignorées: {results['skipped_count']}")
            
            changes = results.get("changes_summary", {})
            print(f"   Mots-clés supprimés: {changes.get('total_keywords_removed', 0)}")
            print(f"   Mots-clés ajoutés: {changes.get('total_keywords_added', 0)}")
            
            # Top des suppressions
            most_removed = changes.get("most_removed_keywords", {})
            if most_removed:
                print(f"   Plus supprimés: {dict(list(most_removed.items())[:5])}")
            
            # Échantillon de changements
            samples = results.get("sample_changes", [])
            if samples:
                print(f"\n📋 Échantillon de changements:")
                for sample in samples[:3]:
                    print(f"   {sample['stream_name']}:")
                    if sample['removed']:
                        print(f"     - Supprimés: {sample['removed']}")
                    if sample['added']:
                        print(f"     + Ajoutés: {sample['added']}")
        else:
            print(f"   Résultat: {results}")
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Arrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")

if __name__ == "__main__":
    main()