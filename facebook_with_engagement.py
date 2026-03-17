#!/usr/bin/env python3
"""
Facebook scraper avec engagement forcé
"""

import os
from apify_client import ApifyClient
from dotenv import load_dotenv
import uuid
from datetime import datetime
from pymongo import MongoClient
import certifi

load_dotenv()

class FacebookEngagementScraper:
    def __init__(self):
        token = os.getenv('APIFY_API_TOKEN')
        self.client = ApifyClient(token)
        
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        if mongo_url.startswith('mongodb+srv'):
            self.mongo_client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            self.mongo_client = MongoClient(mongo_url)
        
        self.db = self.mongo_client['veille_media']
        self.collection = self.db['social_media_posts']

    def scrape_with_engagement(self):
        """Scraper Facebook avec engagement forcé"""
        facebook_pages = [
            "https://www.facebook.com/RCIGUADELOUPE971",
            "https://www.facebook.com/FranceAntillesGuadeloupe"
        ]
        
        # Configuration optimisée pour l'engagement
        run_input = {
            "startUrls": [{"url": url} for url in facebook_pages],
            "resultsLimit": 20,  # Limite mise à jour
            "scrapeComments": True,   # Activer les commentaires
            "scrapeReactions": True,  # Activer les réactions
            "onlyPublic": True,
            "maxCommentsPerPost": 10  # Limiter pour éviter les timeouts
        }
        
        try:
            print("Scraping Facebook avec engagement...")
            run = self.client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
            
            posts_with_engagement = []
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                text = str(item.get('text', ''))
                
                # Debug : afficher les données brutes d'engagement
                print(f"\nPost brut:")
                print(f"Text: {text[:60]}...")
                print(f"Raw engagement data: {item.get('engagement', 'MISSING')}")
                print(f"Likes: {item.get('likesCount', 'MISSING')}")
                print(f"Comments: {item.get('commentsCount', 'MISSING')}")
                print(f"Shares: {item.get('sharesCount', 'MISSING')}")
                print(f"Reactions: {item.get('reactionsCount', 'MISSING')}")
                
                # Essayer différents champs pour l'engagement
                engagement = {
                    'likes': (item.get('likesCount') or 
                             item.get('likes') or 
                             item.get('engagement', {}).get('likes', 0)),
                    'comments': (item.get('commentsCount') or 
                                item.get('comments') or 
                                item.get('engagement', {}).get('comments', 0)),
                    'shares': (item.get('sharesCount') or 
                              item.get('shares') or 
                              item.get('engagement', {}).get('shares', 0)),
                    'reactions': (item.get('reactionsCount') or 
                                 item.get('reactions') or 
                                 item.get('engagement', {}).get('reactions', 0))
                }
                
                # Classification améliorée
                keywords = self._improved_classification(text)
                
                post = {
                    'id': f'fb_eng_{uuid.uuid4().hex[:8]}',
                    'platform': 'facebook_engagement',
                    'content': text[:500],
                    'author': item.get('authorName', ''),
                    'engagement': engagement,
                    'keyword_searched': keywords,
                    'raw_data': {
                        'url': item.get('postUrl', ''),
                        'time': item.get('time', ''),
                        'all_fields': list(item.keys())  # Debug
                    },
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'scraped_at': datetime.now().isoformat(),
                    'facebook_engagement': True
                }
                
                posts_with_engagement.append(post)
            
            return posts_with_engagement
            
        except Exception as e:
            print(f"Erreur engagement scraping: {e}")
            return []
    
    def _improved_classification(self, text):
        """Classification améliorée des posts"""
        if not text:
            return 'facebook_empty'
        
        text_lower = text.lower()
        
        # Recherche plus large pour Guy Losbar
        guy_terms = ['guy losbar', 'losbar', 'président conseil', 'président départemental']
        if any(term in text_lower for term in guy_terms):
            return 'Guy Losbar'
            
        # CD971 et dérivés
        cd971_terms = ['cd971', 'conseil départemental', 'département guadeloupe', 'collectivité']
        if any(term in text_lower for term in cd971_terms):
            return 'CD971'
            
        # Sujets départementaux
        if any(term in text_lower for term in ['budget', 'investissement', 'subvention']):
            return 'Budget départemental'
        elif any(term in text_lower for term in ['route', 'infrastructure', 'travaux']):
            return 'Infrastructure départementale'  
        elif any(term in text_lower for term in ['collège', 'éducation', 'jeunes']):
            return 'Education départementale'
            
        # Actualités locales importantes
        if any(term in text_lower for term in ['cyclone', 'météo', 'alerte']):
            return 'Météo/Sécurité'
        elif 'guadeloupe' in text_lower:
            return 'Actualités Guadeloupe'
        else:
            return 'Media local'

    def test_engagement_scraping(self):
        """Test du scraping avec engagement"""
        posts = self.scrape_with_engagement()
        
        if posts:
            print(f"\nPosts avec engagement: {len(posts)}")
            
            # Analyser l'engagement
            for post in posts:
                keyword = post['keyword_searched'] 
                engagement = post['engagement']
                total_engagement = sum(engagement.values())
                
                if total_engagement > 0:
                    print(f"✅ [{keyword}] {total_engagement} total engagement")
                else:
                    print(f"⚠️ [{keyword}] Pas d'engagement détecté")
            
            # Sauvegarder
            saved = 0
            for post in posts:
                try:
                    self.collection.update_one(
                        {'id': post['id']},
                        {'$set': post},
                        upsert=True
                    )
                    saved += 1
                except Exception as e:
                    print(f"Erreur sauvegarde: {e}")
            
            print(f"💾 {saved} posts sauvegardés")
            
        return len(posts)

if __name__ == "__main__":
    scraper = FacebookEngagementScraper()
    count = scraper.test_engagement_scraping()
    print(f"\nTest terminé: {count} posts traités")
