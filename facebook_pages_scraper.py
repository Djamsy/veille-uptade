#!/usr/bin/env python3
"""
Scraper Facebook avec les vraies pages médias Guadeloupe
"""

import os
from apify_client import ApifyClient
from dotenv import load_dotenv
import uuid
from datetime import datetime
from pymongo import MongoClient
import certifi

load_dotenv()

class FacebookPagesScraper:
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
        
        # Vraies pages Facebook médias Guadeloupe
        self.facebook_pages = [
            "https://www.facebook.com/RCIGUADELOUPE971",
            "https://www.facebook.com/FranceAntillesGuadeloupe"
        ]

    def scrape_facebook_pages(self):
        """Scraper les pages Facebook des médias locaux"""
        print(f"Scraping {len(self.facebook_pages)} pages Facebook...")
        
        # Configuration pour Facebook pages scraper
        run_input = {
            "startUrls": [{"url": url} for url in self.facebook_pages],
            "maxPosts": 30,  # 30 posts par page
            "onlyPublic": True,
            "scrapeComments": False,  # Éviter les commentaires pour économiser
            "scrapeReactions": True   # Récupérer les réactions
        }
        
        try:
            print("Lancement Facebook Pages Scraper...")
            run = self.client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
            
            print(f"Status: {run.get('status')}")
            
            posts = []
            count = 0
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                count += 1
                
                text = str(item.get('text', ''))
                author = item.get('authorName', '')
                
                print(f"\nPost {count}:")
                print(f"  Auteur: {author}")
                print(f"  Texte: {text[:100]}...")
                print(f"  Likes: {item.get('likesCount', 0)}")
                print(f"  Commentaires: {item.get('commentsCount', 0)}")
                print(f"  Partages: {item.get('sharesCount', 0)}")
                
                # Extraire mots-clés départementaux
                keywords = self._extract_department_keywords(text)
                
                post = {
                    'id': f'fb_page_{uuid.uuid4().hex[:10]}',
                    'platform': 'facebook_media',
                    'content': text[:500] if text else '',
                    'author': author,
                    'page_source': self._identify_page_source(author, item.get('postUrl', '')),
                    'engagement': {
                        'likes': item.get('likesCount', 0),
                        'comments': item.get('commentsCount', 0),
                        'shares': item.get('sharesCount', 0),
                        'reactions': item.get('reactionsCount', 0)
                    },
                    'post_url': item.get('postUrl', ''),
                    'post_date': item.get('time', ''),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'scraped_at': datetime.now().isoformat(),
                    'keyword_searched': keywords,
                    'facebook_media': True,
                    'location': 'Guadeloupe'
                }
                
                posts.append(post)
                
                if count >= 10:  # Limiter l'affichage
                    print(f"... et {len(list(self.client.dataset(run['defaultDatasetId']).iterate_items())) - 10} autres posts")
                    break
            
            print(f"\nTotal Facebook posts récupérés: {len(posts)}")
            return posts
            
        except Exception as e:
            print(f"Erreur Facebook scraping: {e}")
            return []
    
    def _identify_page_source(self, author, url):
        """Identifier la source médiatique"""
        author_lower = author.lower()
        url_lower = url.lower()
        
        if 'rci' in author_lower or 'rci' in url_lower:
            return 'RCI Guadeloupe'
        elif 'france' in author_lower and 'antilles' in author_lower:
            return 'France-Antilles Guadeloupe'
        else:
            return author or 'Media Guadeloupe'
    
    def _extract_department_keywords(self, text):
        """Extraire mots-clés départementaux"""
        if not text:
            return 'actualites_media'
        
        text_lower = text.lower()
        
        # Mots-clés spécifiques au département
        if any(term in text_lower for term in ['guy losbar', 'losbar']):
            return 'Guy Losbar'
        elif any(term in text_lower for term in ['cd971', 'conseil départemental', 'département']):
            return 'CD971'
        elif any(term in text_lower for term in ['budget', 'investissement', 'finances']):
            return 'Budget départemental'
        elif any(term in text_lower for term in ['route', 'infrastructure', 'travaux']):
            return 'Infrastructure'
        elif any(term in text_lower for term in ['collège', 'éducation', 'jeunesse']):
            return 'Education'
        elif 'guadeloupe' in text_lower:
            return 'Actualités Guadeloupe'
        else:
            return 'media_local'
    
    def scrape_and_save(self):
        """Scraper Facebook et sauvegarder"""
        posts = self.scrape_facebook_pages()
        
        if posts:
            # Analyser le contenu départemental
            dept_posts = [p for p in posts if p['keyword_searched'] in ['Guy Losbar', 'CD971', 'Budget départemental']]
            
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
            
            print(f"\nSauvegarde: {saved}/{len(posts)} posts")
            print(f"Contenu départemental: {len(dept_posts)} posts")
            
            # Afficher contenu départemental trouvé
            if dept_posts:
                print("\nContenu départemental détecté:")
                for i, post in enumerate(dept_posts[:3]):
                    source = post['page_source']
                    keyword = post['keyword_searched']
                    content = post['content'][:80]
                    likes = post['engagement']['likes']
                    print(f"  {i+1}. [{source}] {keyword}: {content}... ({likes} likes)")
        
        # Stats finales
        total_fb = self.collection.count_documents({'facebook_media': True})
        guy_fb = self.collection.count_documents({
            'facebook_media': True,
            'keyword_searched': 'Guy Losbar'
        })
        
        return {
            'posts_scraped': len(posts),
            'posts_saved': saved if posts else 0,
            'department_content': len(dept_posts) if posts else 0,
            'total_facebook_posts': total_fb,
            'guy_losbar_facebook': guy_fb
        }

if __name__ == "__main__":
    scraper = FacebookPagesScraper()
    results = scraper.scrape_and_save()
    
    print(f"\nRESULTATS FACEBOOK SCRAPING:")
    for key, value in results.items():
        print(f"   {key}: {value}")
