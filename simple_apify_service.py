#!/usr/bin/env python3
"""
Service Apify simplifié avec le client officiel
"""

import os
from datetime import datetime
from apify_client import ApifyClient
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

load_dotenv()

class SimpleApifyService:
    def __init__(self):
        # Client Apify
        token = os.getenv('APIFY_API_TOKEN')
        if not token:
            print("❌ Token Apify manquant dans .env")
            return
            
        self.client = ApifyClient(token)
        print(f"✅ Client Apify initialisé (token: {token[:10]}...)")
        
        # MongoDB
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        if mongo_url.startswith('mongodb+srv'):
            self.mongo_client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            self.mongo_client = MongoClient(mongo_url)
        
        self.db = self.mongo_client['veille_media']
        self.collection = self.db['social_media_posts']
        print("✅ MongoDB connecté")
    
    def scrape_instagram_guadeloupe(self):
        """Scraper Instagram pour la Guadeloupe"""
        print("🔍 Scraping Instagram...")
        
        # Configuration pour la Guadeloupe
        run_input = {
            "searchType": "hashtag",
            "hashtags": ["guadeloupe", "cd971", "guylosbar"],
            "resultsLimit": 20,  # Limite réduite pour les tests
            "addParentData": False,
        }
        
        try:
            # Utiliser l'actor ID Instagram
            print("⏳ Lancement de l'actor Instagram...")
            run = self.client.actor("shu8hvrXbJbY3Eb9W").call(run_input=run_input)
            print(f"✅ Run terminé: {run.get('status')}")
            
            posts = []
            dataset_id = run["defaultDatasetId"]
            print(f"📊 Récupération des données du dataset {dataset_id}...")
            
            for item in self.client.dataset(dataset_id).iterate_items():
                posts.append({
                    'platform': 'instagram_apify',
                    'content': item.get('caption', '')[:200],  # Limiter la taille
                    'author': item.get('ownerUsername', ''),
                    'engagement': {
                        'likes': item.get('likesCount', 0),
                        'comments': item.get('commentsCount', 0)
                    },
                    'url': item.get('url', ''),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'scraped_at': datetime.now().isoformat(),
                    'keyword_searched': 'guadeloupe_hashtag',
                    'apify_source': True
                })
            
            print(f"📱 Instagram: {len(posts)} posts récupérés")
            return posts
            
        except Exception as e:
            print(f"❌ Erreur Instagram Apify: {e}")
            return []
    
    def scrape_department_content(self):
        """Scraper pour le contenu départemental"""
        print("🚀 Démarrage scraping départemental...")
        all_posts = []
        
        # Instagram
        instagram_posts = self.scrape_instagram_guadeloupe()
        all_posts.extend(instagram_posts)
        
        # Sauvegarder
        if all_posts:
            result = self.collection.insert_many(all_posts)
            print(f"💾 Sauvegardé: {len(result.inserted_ids)} posts")
        else:
            print("⚠️ Aucun post à sauvegarder")
        
        # Stats
        guy_count = self.collection.count_documents({'keyword_searched': {'$regex': 'guy', '$options': 'i'}})
        cd971_count = self.collection.count_documents({'keyword_searched': {'$regex': 'cd971', '$options': 'i'}})
        apify_count = self.collection.count_documents({'apify_source': True})
        
        return {
            'total_scraped': len(all_posts),
            'instagram_posts': len(instagram_posts),
            'total_guy_losbar': guy_count,
            'total_cd971': cd971_count,
            'total_apify_posts': apify_count
        }

# Instance globale
simple_apify = SimpleApifyService()

if __name__ == "__main__":
    if hasattr(simple_apify, 'client'):
        results = simple_apify.scrape_department_content()
        print(f"🎯 Résultats finaux: {results}")
    else:
        print("❌ Service non initialisé - vérifiez votre token Apify")
