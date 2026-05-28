#!/usr/bin/env python3
"""
Script pour vider complètement la base MongoDB locale
Usage: python3 clear_mongodb.py
"""

import os
from pymongo import MongoClient

def clear_local_mongodb():
    """Vide toutes les collections de la base MongoDB locale"""
    
    # Connexion à MongoDB local
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
    
    print("🔗 Connexion à MongoDB local...")
    print(f"   URL: {MONGO_URL}")
    
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        
        # Extraire le nom de la base
        db_name = MONGO_URL.rsplit("/", 1)[-1].split("?")[0] or "veille_media"
        db = client[db_name]
        
        # Ping pour vérifier la connexion
        client.admin.command('ping')
        print(f"✅ Connecté à la base: {db_name}")
        
        # Lister toutes les collections
        collections = db.list_collection_names()
        print(f"\n📋 Collections trouvées: {len(collections)}")
        for coll in collections:
            print(f"   - {coll}")
        
        # Demander confirmation
        print(f"\n⚠️  ATTENTION: Vous allez SUPPRIMER toutes les données de '{db_name}'")
        response = input("   Tapez 'OUI' pour confirmer: ")
        
        if response.strip().upper() != "OUI":
            print("❌ Opération annulée")
            return
        
        # Supprimer toutes les collections
        print("\n🗑️  Suppression en cours...")
        deleted_count = {}
        
        for collection_name in collections:
            collection = db[collection_name]
            count_before = collection.count_documents({})
            result = collection.delete_many({})
            deleted_count[collection_name] = result.deleted_count
            print(f"   ✅ {collection_name}: {result.deleted_count} documents supprimés")
        
        print("\n✅ Base de données vidée avec succès!")
        print(f"   Total supprimé: {sum(deleted_count.values())} documents")
        
        client.close()
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return

if __name__ == "__main__":
    clear_local_mongodb()
