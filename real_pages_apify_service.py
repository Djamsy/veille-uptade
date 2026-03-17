#!/usr/bin/env python3
"""
Service Apify avec les vraies pages médias Guadeloupe
"""

import os
import uuid
from datetime import datetime
from apify_client import ApifyClient
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

load_dotenv()

class RealPagesApifyService:
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
        
        # Vraies pages médias Guadeloupe confirmées
        self.target_pages = [
            "https://www.instagram.com/rciguadeloupe/",
            "https://www.instagram.com/guadeloupela1ere/", 
            "https://www.instagram.com/franceantilles_guadeloupe/",
            "https://www.instagram.com/la_pause_sans_filtre21/"
        ]
        
        # Mapping page -> source pour l'analyse
        self.page_sources = {
            'rciguadeloupe': 'RCI Guadeloupe',
            'guadeloupela1ere': 'Guadeloupe La 1ère',
            'franceantilles_guadeloupe': 'France-Antilles Guadeloupe',
            'la_pause_sans_filtre21': 'La Pause Sans Filtre'
        }
    
    def scrape_media_pages(self):
        """Scraper les pages médias réelles"""
        print(f"Scraping {len(self.target_pages)} pages médias confirmées...")
        
        run_input = {
            "directUrls": self.target_pages,
            "resultsType": "posts",
            "resultsLimit": 30,  # 30 posts par page
            "addParentData": True
        }
        
        try:
            run = self.client.actor("shu8hvrXbJbY3Eb9W").call(run_input=run_input)
            print(f"Status: {run.get('status')}")
            
            posts = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                username = item.get('ownerUsername', '')
                content = item.get('caption', '')
                
                # Identifier la source médiatique
                media_source = self.page_sources.get(username, username)
                
                # Extraire mots-clés départementaux
                keywords = self._extract_department_keywords(content)
                
                post = {
                    'id': f'media_{uuid.uuid4().hex[:12]}',
                    'platform': 'instagram_media',
                    'content': content[:500] if content else '',
                    'author': username,
                    'media_source': media_source,
                    'engagement': {
                        'likes': item.get('likesCount', 0),
                        'comments': item.get('commentsCount', 0),
                        'views': item.get('videoViewCount', 0)
                    },
                    'url': item.get('url', ''),
                    'post_timestamp': item.get('timestamp', ''),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'scraped_at': datetime.now().isoformat(),
                    'keyword_searched': keywords,
                    'is_media_content': True,
                    'location': 'Guadeloupe'
                }
                posts.append(post)
            
            print(f"Posts médias récupérés: {len(posts)}")
            return posts
            
        except Exception as e:
            print(f"Erreur scraping pages médias: {e}")
            return []
    
    def _extract_department_keywords(self, content):
        """Extraire mots-clés liés au département"""
        if not content:
            return 'actualités_media'
        
        content_lower = content.lower()
        
        department_keywords = {
            'Guy Losbar': ['guy losbar', 'losbar', 'président conseil'],
            'CD971': ['cd971', 'conseil départemental', 'département'],
            'Budget départemental': ['budget', 'finances', 'investissement'],
            'Infrastructure': ['route', 'travaux', 'aménagement'],
            'Social': ['aide sociale', 'solidarité', 'famille'],
            'Education': ['collège', 'jeunesse', 'éducation']
        }
        
        for keyword, terms in department_keywords.items():
            if any(term in content_lower for term in terms):
                return keyword
                
        return 'actualités_guadeloupe'
    
    def scrape_and_analyze(self):
        """Scraper et analyser le contenu médiatique"""
        posts = self.scrape_media_pages()
        
        if posts:
            # Analyser par source
            by_source = {}
            department_content = 0
            
            for post in posts:
                source = post['media_source']
                by_source[source] = by_source.get(source, 0) + 1
                
                if post['keyword_searched'] in ['Guy Losbar', 'CD971']:
                    department_content += 1
            
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
            
            print(f"Sauvegardés: {saved}/{len(posts)} posts")
            print(f"Contenu départemental: {department_content} posts")
            
            print("\nPar source médiatique:")
            for source, count in by_source.items():
                print(f"  - {source}: {count} posts")
            
            # Échantillon posts départementaux
            dept_posts = [p for p in posts if p['keyword_searched'] in ['Guy Losbar', 'CD971']]
            if dept_posts:
                print("\nContenu départemental trouvé:")
                for i, post in enumerate(dept_posts[:3]):
                    content = post['content'][:80] if post['content'] else 'Pas de caption'
                    print(f"  {i+1}. [{post['media_source']}] {content}...")
        
        # Stats finales
        total_media = self.collection.count_documents({'is_media_content': True})
        guy_media = self.collection.count_documents({
            'is_media_content': True,
            'keyword_searched': 'Guy Losbar'
        })
        
        return {
            'posts_scraped': len(posts),
            'posts_saved': saved if posts else 0,
            'department_content': department_content if posts else 0,
            'total_media_posts': total_media,
            'guy_losbar_media': guy_media
        }

if __name__ == "__main__":
    service = RealPagesApifyService()
    results = service.scrape_and_analyze()
    
    print(f"\nRÉSULTATS PAGES MÉDIAS RÉELLES:")
    for key, value in results.items():
        print(f"   {key}: {value}")
