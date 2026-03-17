#!/usr/bin/env python3
"""
Service Apify avec gestion des IDs uniques
"""

import os
import uuid
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
        self.client = ApifyClient(token)
        print("✅ Client Apify initialisé")
        
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
        """Scraper Instagram avec IDs uniques"""
        print("🔍 Scraping Instagram...")
        
        run_input = {
            "searchType": "hashtag",
            "hashtags": ["guadeloupe", "cd971"],
            "resultsLimit": 10
        }
        
        try:
            run = self.client.actor("shu8hvrXbJbY3Eb9W").call(run_input=run_input)
            print(f"✅ Run terminé: {run.get('status')}")
            
            posts = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                
                # Générer ID unique pour éviter les conflits
                unique_id = f"instagram_apify_{uuid.uuid4().hex[:12]}"
                
                post = {
                    'id': unique_id,  # ID unique requis
                    'platform': 'instagram_apify',
                    'content': (item.get('caption') or '')[:500],  # Limiter la taille
                    'author': item.get('ownerUsername', ''),
                    'engagement': {
                        'likes': item.get('likesCount', 0),
                        'comments': item.get('commentsCount', 0)
                    },
                    'url': item.get('url', ''),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'scraped_at': datetime.now().isoformat(),
                    'keyword_searched': 'guadeloupe_hashtag',
                    'apify_source': True,
                    'hashtags': item.get('hashtags', [])[:5]  # Max 5 hashtags
                }
                posts.append(post)
            
            print(f"📱 Instagram: {len(posts)} posts récupérés")
            return posts
            
        except Exception as e:
            print(f"❌ Erreur Instagram: {e}")
            return []
    
    def save_posts_safely(self, posts):
        """Sauvegarder avec gestion des doublons"""
        if not posts:
            return 0
            
        saved_count = 0
        for post in posts:
            try:
                # Utiliser upsert pour éviter les doublons
                self.collection.update_one(
                    {'id': post['id']},
                    {'$set': post},
                    upsert=True
                )
                saved_count += 1
            except Exception as e:
                print(f"⚠️ Erreur sauvegarde post {post['id']}: {e}")
                
        return saved_count
    
    def scrape_and_save(self):
        """Scraper et sauvegarder avec statistiques"""
        posts = self.scrape_instagram_guadeloupe()
        
        if posts:
            saved = self.save_posts_safely(posts)
            print(f"💾 Sauvegardés: {saved}/{len(posts)} posts")
            
            # Afficher échantillon
            for i, post in enumerate(posts[:2]):
                content = post['content'][:60] if post['content'] else 'Pas de caption'
                likes = post['engagement']['likes']
                print(f"  {i+1}. @{post['author']}: {content}... ({likes} likes)")
        
        # Stats finales
        total_apify = self.collection.count_documents({'apify_source': True})
        total_guadeloupe = self.collection.count_documents({
            'keyword_searched': {'$regex': 'guadeloupe', '$options': 'i'}
        })
        
        return {
            'posts_scraped': len(posts),
            'posts_saved': saved if posts else 0,
            'total_apify_posts': total_apify,
            'total_guadeloupe_posts': total_guadeloupe
        }

if __name__ == "__main__":
    service = SimpleApifyService()
    results = service.scrape_and_save()
    
    print(f"\n🎯 RÉSULTATS FINAUX:")
    print(f"   Scraped: {results['posts_scraped']}")
    print(f"   Saved: {results['posts_saved']}")  
    print(f"   Total Apify: {results['total_apify_posts']}")
    print(f"   Total Guadeloupe: {results['total_guadeloupe_posts']}")
