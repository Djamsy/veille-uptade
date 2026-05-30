#!/usr/bin/env python3
"""
Test MongoDB avec correction pour Atlas
"""

import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

def test_mongodb_atlas():
    """Test de connexion MongoDB Atlas corrigé"""
    try:
        from pymongo import MongoClient
        import certifi
        
        # Récupérer l'URL depuis .env et nettoyer
        mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
        mongo_url = mongo_url.strip('"\'')  # Enlever les guillemets
        
        print(f"🔗 MongoDB URL: {mongo_url[:60]}...")
        
        # Connexion Atlas avec certificats
        if mongo_url.startswith("mongodb+srv"):
            client = MongoClient(mongo_url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
        else:
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
        
        # Spécifier explicitement la base de données
        db_name = os.getenv('MONGO_DB_NAME', 'veille_media')
        print(f"📁 Base de données: {db_name}")
        
        db = client[db_name]  # Utiliser explicitement le nom de la DB
        
        # Test de connexion
        db.command('ping')
        print("✅ Connexion MongoDB Atlas OK")
        
        # Lister les collections
        collections = db.list_collection_names()
        print(f"📚 Collections trouvées: {len(collections)}")
        
        if collections:
            for col in collections[:5]:  # Afficher les 5 premières
                count = db[col].count_documents({})
                print(f"   - {col}: {count} documents")
        
        # Vérifier/créer collection social_media_posts
        if 'social_media_posts' in collections:
            count = db.social_media_posts.count_documents({})
            print(f"\n📱 Collection social_media_posts: {count} posts")
            
            if count > 0:
                # Échantillon des posts
                sample = list(db.social_media_posts.find().limit(3))
                print("📝 Échantillon posts:")
                for i, post in enumerate(sample):
                    platform = post.get('platform', '?')
                    content = str(post.get('content', post.get('text', '')))[:50]
                    date = post.get('date', post.get('scraped_at', '?'))
                    print(f"   {i+1}. [{platform}] {date} | {content}...")
            else:
                print("📭 Aucun post en base pour l'instant")
        else:
            print("📱 Collection social_media_posts n'existe pas encore")
            print("   → Elle sera créée au premier scraping")
            
        return True
        
    except Exception as e:
        print(f"❌ Erreur MongoDB: {e}")
        return False

def test_env_variables():
    """Vérifier les variables d'environnement importantes"""
    print("\n🔧 Variables d'environnement:")
    print("=" * 30)
    
    important_vars = [
        'MONGO_URL',
        'MONGO_DB_NAME', 
        'TWITTER_BEARER_TOKEN',
        'GOOGLE_API_KEY',
        'APIFY_API_TOKEN'
    ]
    
    for var in important_vars:
        value = os.getenv(var, 'NON_DEFINI')
        if value == 'NON_DEFINI':
            print(f"❌ {var}: non défini")
        else:
            # Masquer les tokens sensibles
            if 'TOKEN' in var or 'KEY' in var:
                display_value = f"{value[:10]}...{value[-5:]}" if len(value) > 15 else "***"
            else:
                display_value = value[:50] + "..." if len(value) > 50 else value
            print(f"✅ {var}: {display_value}")

if __name__ == "__main__":
    print("🚀 TEST MONGODB ATLAS + VARIABLES ENV")
    print("=" * 50)
    
    # Test 1: Variables d'environnement
    test_env_variables()
    
    # Test 2: Connexion MongoDB
    print("\n" + "=" * 50)
    if test_mongodb_atlas():
        print("✅ MongoDB Atlas opérationnel")
        print("🎯 Prêt pour le scraping des réseaux sociaux")
    else:
        print("❌ Problème de connexion MongoDB")
        print("💡 Vérifiez:")
        print("   - L'URL dans le .env")
        print("   - Les droits d'accès sur Atlas")
        print("   - La connexion internet")
