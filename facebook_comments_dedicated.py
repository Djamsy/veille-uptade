#!/usr/bin/env python3
"""
Extracteur de commentaires Facebook avec l'actor dédié
"""

import os
from apify_client import ApifyClient
from dotenv import load_dotenv
import uuid
from datetime import datetime
from pymongo import MongoClient
import certifi

load_dotenv()

class FacebookCommentsDedicated:
    def __init__(self):
        token = os.getenv('APIFY_API_TOKEN')
        self.client = ApifyClient(token)
        
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        if mongo_url.startswith('mongodb+srv'):
            self.mongo_client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            self.mongo_client = MongoClient(mongo_url)
        
        self.db = self.mongo_client['veille_media']
        self.posts_collection = self.db['social_media_posts'] 
        self.comments_collection = self.db['facebook_comments']

    def get_facebook_post_urls(self):
        """Récupérer les URLs des posts Facebook avec engagement"""
        posts = list(self.posts_collection.find({
            'facebook_engagement': True,
            'post_url': {'$exists': True, '$ne': ''}
        }).sort('engagement.likes', -1).limit(5))
        
        urls = []
        for post in posts:
            url = post.get('post_url', '')
            if url and 'facebook.com' in url:
                urls.append(url)
                print(f"Post trouvé: {url}")
                print(f"  Contenu: {post.get('content', '')[:60]}...")
                print(f"  Engagement: {sum(post.get('engagement', {}).values())}")
        
        return urls

    def extract_comments_from_url(self, post_url):
        """Extraire commentaires d'une URL spécifique"""
        input_config = {
            "startUrls": [{"url": post_url}],
            "resultsLimit": 50,
            "includeNestedComments": False,
            "viewOption": "RANKED_UNFILTERED"
        }
        
        try:
            print(f"\nExtraction commentaires: {post_url}")
            run = self.client.actor("us5srxAYnsrkgUv2v").call(input_config)
            
            comments_extracted = 0
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                # Debug structure
                print(f"Champs disponibles: {list(item.keys())}")
                
                comment_text = item.get('text', '') or item.get('comment', '') or item.get('content', '')
                author = item.get('author', '') or item.get('user', '') or item.get('name', '')
                likes = item.get('likes', 0) or item.get('reactions', 0)
                
                if comment_text and author:
                    print(f"Comment trouvé: @{author}")
                    print(f"  Texte: {comment_text[:80]}...")
                    print(f"  Likes: {likes}")
                    
                    # Sauvegarder
                    comment_doc = {
                        'id': f'fb_comment_ded_{uuid.uuid4().hex[:8]}',
                        'post_url': post_url,
                        'comment_text': comment_text,
                        'author_name': author,
                        'likes': likes,
                        'raw_data': item,  # Conserver toutes les données
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'scraped_at': datetime.now().isoformat(),
                        'source': 'apify_dedicated',
                        'processed': False
                    }
                    
                    try:
                        self.comments_collection.update_one(
                            {'id': comment_doc['id']},
                            {'$set': comment_doc},
                            upsert=True
                        )
                        comments_extracted += 1
                    except Exception as e:
                        print(f"Erreur sauvegarde: {e}")
                
                if comments_extracted >= 10:  # Limiter affichage
                    break
            
            return comments_extracted
            
        except Exception as e:
            print(f"Erreur extraction: {e}")
            return 0

    def extract_all_comments(self):
        """Extraire commentaires de tous les posts Facebook"""
        post_urls = self.get_facebook_post_urls()
        
        if not post_urls:
            print("Aucune URL de post Facebook trouvée")
            return 0
        
        total_comments = 0
        
        for url in post_urls[:3]:  # Limiter à 3 posts pour le test
            comments_count = self.extract_comments_from_url(url)
            total_comments += comments_count
            print(f"Commentaires extraits: {comments_count}")
        
        return total_comments

    def show_extracted_comments(self):
        """Afficher les commentaires extraits"""
        comments = list(self.comments_collection.find({
            'source': 'apify_dedicated'
        }).limit(5))
        
        if comments:
            print(f"\nCommentaires extraits avec l'actor dédié:")
            for i, comment in enumerate(comments):
                author = comment.get('author_name', 'unknown')
                text = comment.get('comment_text', '')[:60]
                likes = comment.get('likes', 0)
                
                print(f"{i+1}. @{author} ({likes} likes)")
                print(f"   {text}...")
        
        return len(comments)

if __name__ == "__main__":
    extractor = FacebookCommentsDedicated()
    
    # Extraire commentaires avec l'actor dédié
    total = extractor.extract_all_comments()
    
    if total > 0:
        # Afficher résultats
        extractor.show_extracted_comments()
    
    print(f"\nTotal commentaires extraits: {total}")
