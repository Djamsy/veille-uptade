#!/usr/bin/env python3
"""
Extracteur de tous les commentaires Facebook - sans filtrage
"""

import os
from apify_client import ApifyClient
from dotenv import load_dotenv
import uuid
from datetime import datetime
from pymongo import MongoClient
import certifi

load_dotenv()

class FacebookAllCommentsExtractor:
    def __init__(self):
        token = os.getenv('APIFY_API_TOKEN')
        self.client = ApifyClient(token)
        
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        if mongo_url.startswith('mongodb+srv'):
            self.mongo_client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            self.mongo_client = MongoClient(mongo_url)
        
        self.db = self.mongo_client['veille_media']
        self.comments_collection = self.db['facebook_comments']

    def extract_all_comments(self):
        """Extraire tous les commentaires sans filtrage"""
        facebook_pages = [
            "https://www.facebook.com/RCIGUADELOUPE971",
            "https://www.facebook.com/FranceAntillesGuadeloupe"
        ]
        
        run_input = {
            "startUrls": [{"url": url} for url in facebook_pages],
            "resultsLimit": 25,  # Plus de posts
            "scrapeComments": True,
            "maxCommentsPerPost": 100,  # Maximum de commentaires
            "scrapeReactions": True,
            "onlyPublic": True
        }
        
        try:
            print("Extraction complète des commentaires...")
            run = self.client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
            
            total_comments = 0
            posts_processed = 0
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                posts_processed += 1
                post_text = str(item.get('text', ''))
                post_url = item.get('postUrl', '')
                
                comments = item.get('comments', [])
                
                if comments:
                    print(f"\nPost {posts_processed}: {len(comments)} commentaires")
                    print(f"Contenu: {post_text[:80]}...")
                    
                    for comment in comments:
                        comment_text = comment.get('text', '')
                        comment_author = comment.get('authorName', '')
                        comment_likes = comment.get('likesCount', 0)
                        comment_time = comment.get('timestamp', '')
                        
                        # Sauvegarder chaque commentaire brut
                        comment_doc = {
                            'id': f'fb_comment_{uuid.uuid4().hex[:10]}',
                            'post_url': post_url,
                            'post_text': post_text[:200],
                            'comment_text': comment_text,
                            'author_name': comment_author,
                            'likes': comment_likes,
                            'timestamp': comment_time,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'scraped_at': datetime.now().isoformat(),
                            'source': 'facebook_apify',
                            'processed': False  # Flag pour le traitement ultérieur
                        }
                        
                        try:
                            self.comments_collection.update_one(
                                {'id': comment_doc['id']},
                                {'$set': comment_doc},
                                upsert=True
                            )
                            total_comments += 1
                        except Exception as e:
                            print(f"Erreur sauvegarde: {e}")
                
                else:
                    print(f"Post {posts_processed}: aucun commentaire")
            
            print(f"\nExtraction terminée:")
            print(f"Posts traités: {posts_processed}")
            print(f"Commentaires sauvegardés: {total_comments}")
            
            return total_comments
            
        except Exception as e:
            print(f"Erreur extraction: {e}")
            return 0
    
    def show_sample_comments(self, limit=5):
        """Afficher un échantillon des commentaires extraits"""
        comments = list(self.comments_collection.find().limit(limit))
        
        if comments:
            print(f"\nÉchantillon de {len(comments)} commentaires:")
            for i, comment in enumerate(comments):
                author = comment.get('author_name', 'unknown')
                text = comment.get('comment_text', '')[:100]
                likes = comment.get('likes', 0)
                post = comment.get('post_text', '')[:60]
                
                print(f"\n{i+1}. @{author} ({likes} likes)")
                print(f"   Post: {post}...")
                print(f"   Comment: {text}...")
        
        return len(comments)
    
    def get_stats(self):
        """Statistiques des commentaires extraits"""
        total = self.comments_collection.count_documents({})
        today = self.comments_collection.count_documents({
            'date': datetime.now().strftime('%Y-%m-%d')
        })
        
        return {
            'total_comments': total,
            'today_comments': today
        }

if __name__ == "__main__":
    extractor = FacebookAllCommentsExtractor()
    
    # Extraire tous les commentaires
    extracted = extractor.extract_all_comments()
    
    if extracted > 0:
        # Afficher échantillon
        extractor.show_sample_comments(3)
        
        # Stats
        stats = extractor.get_stats()
        print(f"\nSTATISTIQUES:")
        print(f"Total commentaires en base: {stats['total_comments']}")
        print(f"Commentaires d'aujourd'hui: {stats['today_comments']}")
    
    print(f"\nCommentaires extraits cette session: {extracted}")
