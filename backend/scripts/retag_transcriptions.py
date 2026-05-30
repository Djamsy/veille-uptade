#!/usr/bin/env python3
# backend/scripts/retag_transcriptions.py
"""
Script de correction ponctuel pour retagger les transcriptions radio
Utilise la configuration MongoDB existante du projet
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# Charger l'environnement
load_dotenv()

# Ajouter le chemin backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend._attic.ai_service import ai_service

# Configuration logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TranscriptionRetagger:
    def __init__(self):
        """Utilise la même config MongoDB que le projet"""
        
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        
        try:
            if "mongodb+srv://" in MONGO_URL or "atlas" in MONGO_URL.lower():
                self.client = MongoClient(
                    MONGO_URL,
                    tlsCAFile=certifi.where(),
                    serverSelectionTimeoutMS=20000,
                    retryWrites=True,
                )
            else:
                self.client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=20000)

            self.client.admin.command("ping")

            # Résolution DB (même logique que scraper)
            try:
                dbname = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
                if "mongodb+srv://" in MONGO_URL and ("?" in dbname or not dbname):
                    dbname = os.environ.get("MONGO_DB_NAME", "veille_media")
            except:
                dbname = os.environ.get("MONGO_DB_NAME", "veille_media")

            self.db = self.client[dbname]
            self.transcripts_coll = self.db["radio_transcriptions"]
            
            print(f"Connecté à {self.transcripts_coll.full_name}")

        except Exception as e:
            print(f"Erreur connexion MongoDB: {e}")
            sys.exit(1)

    def get_stats(self):
        """Statistiques rapides"""
        total = self.transcripts_coll.count_documents({})
        with_keywords = self.transcripts_coll.count_documents({"ai_keywords": {"$exists": True, "$ne": []}})
        
        suspects = ["Nicolas Sarkozy", "Emmanuel Macron", "Marine Le Pen"]
        suspect_count = self.transcripts_coll.count_documents({"ai_keywords": {"$in": suspects}})
        
        return {
            "total": total,
            "with_keywords": with_keywords, 
            "suspect_count": suspect_count
        }

    def retag_transcription(self, transcription):
        """Retag une transcription"""
        text_content = " ".join([
            transcription.get("transcription_text", ""),
            transcription.get("ai_summary", ""),
            transcription.get("gpt_analysis", "")
        ]).strip()
        
        if len(text_content) < 50:
            return {"status": "skipped"}
        
        old_keywords = transcription.get("ai_keywords", [])
        
        # Validation avec le nouveau ai_service
        try:
            result = ai_service.classify_transcription_advanced(text_content)
            entities = result.get("entities_detected", {})
            
            new_keywords = []
            new_keywords.extend(entities.get("elus", []))
            new_keywords.extend(entities.get("services", []))
            new_keywords.extend(entities.get("mots_critiques", []))
            new_keywords = list(set([k for k in new_keywords if k and k != "Aucune"]))
            
            return {
                "status": "success",
                "old": old_keywords,
                "new": new_keywords,
                "removed": list(set(old_keywords) - set(new_keywords)),
                "added": list(set(new_keywords) - set(old_keywords))
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def run_retag(self, limit=100, days=7, dry_run=True):
        """Exécution du retag"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = {
            "captured_at": {"$gte": cutoff},
            "ai_keywords": {"$exists": True, "$ne": []}
        }
        
        transcriptions = list(self.transcripts_coll.find(query).limit(limit))
        
        if not transcriptions:
            print("Aucune transcription à traiter")
            return
        
        print(f"Traitement de {len(transcriptions)} transcriptions (dry_run={dry_run})")
        
        stats = {"processed": 0, "success": 0, "skipped": 0, "errors": 0}
        removed_keywords = {}
        
        for i, trans in enumerate(transcriptions, 1):
            result = self.retag_transcription(trans)
            stats["processed"] += 1
            
            if result["status"] == "success":
                stats["success"] += 1
                removed = result.get("removed", [])
                
                # Compter les suppressions
                for keyword in removed:
                    removed_keywords[keyword] = removed_keywords.get(keyword, 0) + 1
                
                if removed:
                    print(f"[{i}] {trans.get('stream_name', 'Unknown')} - Supprimés: {removed}")
                
                # Sauvegarder si pas dry_run
                if not dry_run:
                    self.transcripts_coll.update_one(
                        {"_id": trans["_id"]},
                        {"$set": {"ai_keywords": result["new"]}}
                    )
                    
            elif result["status"] == "skipped":
                stats["skipped"] += 1
            else:
                stats["errors"] += 1
        
        print(f"\nRésultats: {stats}")
        
        if removed_keywords:
            print(f"Mots-clés les plus supprimés:")
            for keyword, count in sorted(removed_keywords.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {keyword}: {count} fois")

def main():
    print("Script de retag des transcriptions radio")
    print("=" * 40)
    
    retagger = TranscriptionRetagger()
    
    # Afficher stats
    stats = retagger.get_stats()
    print(f"Total transcriptions: {stats['total']}")
    print(f"Avec mots-clés: {stats['with_keywords']}")  
    print(f"Avec mots suspects: {stats['suspect_count']}")
    
    print("\nOptions:")
    print("1. Test (10 transcriptions, dry run)")
    print("2. Retag récent (100 transcriptions, 7 jours)")
    print("3. Retag étendu (500 transcriptions, 30 jours)")
    
    choice = input("\nChoix (1-3): ").strip()
    
    if choice == "1":
        retagger.run_retag(limit=10, days=7, dry_run=True)
    elif choice == "2":
        confirm = input("Confirmer retag récent (oui/non): ")
        dry_run = confirm.lower() not in ['oui', 'o', 'yes', 'y']
        retagger.run_retag(limit=100, days=7, dry_run=dry_run)
    elif choice == "3":
        confirm = input("Confirmer retag étendu (oui/non): ")
        dry_run = confirm.lower() not in ['oui', 'o', 'yes', 'y']
        retagger.run_retag(limit=500, days=30, dry_run=dry_run)
    else:
        print("Choix invalide")

if __name__ == "__main__":
    main()
