#!/usr/bin/env python3
"""
Service Facebook complet pour la veille départementale
Gère le scraping des posts et commentaires via Apify
"""

import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from apify_client import ApifyClient
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

class FacebookService:
    def __init__(self):
        # Configuration Apify
        self.apify_token = os.getenv('APIFY_API_TOKEN')
        if not self.apify_token:
            raise ValueError("APIFY_API_TOKEN manquant dans .env")
        
        self.client = ApifyClient(self.apify_token)
        
        # Actors Apify
        self.posts_actor_id = "apify/facebook-posts-scraper"
        self.comments_actor_id = "us5srxAYnsrkgUv2v"
        
        # Configuration MongoDB
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        if mongo_url.startswith('mongodb+srv'):
            self.mongo_client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            self.mongo_client = MongoClient(mongo_url)
        
        self.db = self.mongo_client['veille_media']
        self.posts_collection = self.db['social_media_posts']
        self.comments_collection = self.db['facebook_comments']
        
        # Pages Facebook des médias guadeloupéens
        self.guadeloupe_pages = [
            "https://www.facebook.com/RCIGUADELOUPE971",
            "https://www.facebook.com/FranceAntillesGuadeloupe"
        ]
        
        logger.info("Service Facebook initialisé")

    def scrape_posts(self, pages: List[str] = None, limit: int = 25) -> Dict[str, Any]:
        """Scraper les posts Facebook des pages médias"""
        pages = pages or self.guadeloupe_pages
        
        run_input = {
            "startUrls": [{"url": url} for url in pages],
            "resultsLimit": limit,
            "scrapeComments": False,  # Posts seulement
            "scrapeReactions": True,
            "onlyPublic": True
        }
        
        try:
            logger.info(f"Scraping {len(pages)} pages Facebook...")
            run = self.client.actor(self.posts_actor_id).call(run_input=run_input)
            
            posts_scraped = []
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                post = self._process_post_item(item)
                if post:
                    posts_scraped.append(post)
            
            # Sauvegarder les posts
            saved_count = self._save_posts(posts_scraped)
            
            return {
                'success': True,
                'posts_scraped': len(posts_scraped),
                'posts_saved': saved_count,
                'pages_processed': len(pages),
                'run_id': run.get('id', ''),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur scraping posts Facebook: {e}")
            return {
                'success': False,
                'error': str(e),
                'posts_scraped': 0,
                'posts_saved': 0
            }

    def scrape_comments(self, post_url: str, limit: int = 100) -> Dict[str, Any]:
        """Scraper les commentaires d'un post Facebook spécifique"""
        run_input = {
            "startUrls": [{"url": post_url}],
            "resultsLimit": limit,
            "includeNestedComments": True,
            "viewOption": "RANKED_UNFILTERED"
        }
        
        try:
            logger.info(f"Scraping commentaires: {post_url[:60]}...")
            run = self.client.actor(self.comments_actor_id).call(run_input=run_input)
            
            comments_scraped = []
            
            for item in self.client.dataset(run['defaultDatasetId']).iterate_items():
                comment = self._process_comment_item(item, post_url)
                if comment:
                    comments_scraped.append(comment)
            
            # Sauvegarder les commentaires
            saved_count = self._save_comments(comments_scraped)
            
            # Analyser les sentiments
            sentiment_analysis = self._analyze_sentiment_stats(comments_scraped)
            
            return {
                'success': True,
                'comments_scraped': len(comments_scraped),
                'comments_saved': saved_count,
                'post_url': post_url,
                'sentiment_analysis': sentiment_analysis,
                'run_id': run.get('id', ''),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur scraping commentaires: {e}")
            return {
                'success': False,
                'error': str(e),
                'comments_scraped': 0,
                'comments_saved': 0
            }

    def scrape_high_engagement_posts_comments(self, min_engagement: int = 50) -> Dict[str, Any]:
        """Scraper les commentaires des posts avec fort engagement"""
        # Récupérer les posts avec engagement élevé
        high_engagement_posts = list(self.posts_collection.find({
            'platform': {'$regex': 'facebook'},
            'engagement': {'$exists': True}
        }).sort('engagement.likes', -1).limit(5))
        
        total_comments = 0
        results = []
        
        for post in high_engagement_posts:
            engagement = post.get('engagement', {})
            total_eng = sum(engagement.values())
            
            if total_eng >= min_engagement:
                # Construire l'URL du post si possible
                post_url = post.get('post_url') or post.get('url')
                if not post_url:
                    # Essayer de construire l'URL basique
                    author = post.get('author', '')
                    if author:
                        post_url = f"https://www.facebook.com/{author}/posts/"
                
                if post_url:
                    comment_result = self.scrape_comments(post_url, limit=50)
                    total_comments += comment_result['comments_scraped']
                    results.append(comment_result)
        
        return {
            'success': True,
            'posts_processed': len(results),
            'total_comments_scraped': total_comments,
            'results': results,
            'timestamp': datetime.now().isoformat()
        }

    def _process_post_item(self, item: Dict) -> Optional[Dict]:
        """Traiter un item de post Facebook"""
        text = item.get('text', '')
        if not text or len(text) < 10:
            return None
        
        # Calculer l'engagement
        engagement = {
            'likes': self._safe_int(item.get('likesCount', 0)),
            'comments': self._safe_int(item.get('commentsCount', 0)),
            'shares': self._safe_int(item.get('sharesCount', 0)),
            'reactions': self._safe_int(item.get('reactionsCount', 0))
        }
        
        total_engagement = sum(engagement.values())
        
        return {
            'id': f'fb_post_{uuid.uuid4().hex[:10]}',
            'platform': 'facebook_apify',
            'content': text,
            'author': item.get('authorName', ''),
            'engagement': engagement,
            'total_engagement': total_engagement,
            'post_url': item.get('postUrl', ''),
            'post_date': item.get('time', ''),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'scraped_at': datetime.now().isoformat(),
            'keyword_searched': self._extract_keywords(text),
            'facebook_apify': True,
            'location': 'Guadeloupe'
        }

    def _process_comment_item(self, item: Dict, post_url: str) -> Optional[Dict]:
        """Traiter un item de commentaire Facebook"""
        text = item.get('text', '')
        author = item.get('profileName', '')
        
        if not text or not author:
            return None
        
        return {
            'id': f'fb_comment_{uuid.uuid4().hex[:10]}',
            'text': text,
            'author': author,
            'likes': self._safe_int(item.get('likesCount', 0)),
            'date': item.get('date', ''),
            'post_url': post_url,
            'comment_url': item.get('commentUrl', ''),
            'sentiment': self._analyze_sentiment(text),
            'language': self._detect_language(text),
            'topic': self._extract_topic(text),
            'engagement_score': self._calculate_engagement_score(item, text),
            'scraped_at': datetime.now().isoformat(),
            'processed': True
        }

    def _analyze_sentiment(self, text: str) -> str:
        """Analyser le sentiment d'un texte"""
        text_lower = text.lower()
        
        positive_words = ['bien', 'bon', 'bravo', 'merci', 'excellent', 'parfait', 'génial', 'soutien']
        negative_words = ['pas', 'non', 'mauvais', 'honte', 'scandale', 'horrible', 'dégoûtant', 'nul']
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        else:
            return 'neutral'

    def _detect_language(self, text: str) -> str:
        """Détecter la langue (français ou créole)"""
        creole_words = ['ka', 'sa', 'nou', 'yo', 'ki', 'mwen', 'sé', 'pa', 'pou']
        creole_count = sum(1 for word in creole_words if word in text.lower())
        
        return 'creole' if creole_count >= 2 else 'french'

    def _extract_topic(self, text: str) -> str:
        """Extraire le sujet principal du texte"""
        text_lower = text.lower()
        
        if any(term in text_lower for term in ['guy losbar', 'losbar', 'président']):
            return 'Guy Losbar'
        elif any(term in text_lower for term in ['cd971', 'conseil départemental', 'département']):
            return 'CD971'
        elif 'sarkozy' in text_lower:
            return 'Sarkozy'
        elif any(term in text_lower for term in ['cyclone', 'météo', 'pluie', 'vigilance']):
            return 'Météo'
        else:
            return 'Actualités locales'

    def _extract_keywords(self, text: str) -> str:
        """Extraire les mots-clés d'un post"""
        text_lower = text.lower()
        
        if any(term in text_lower for term in ['guy losbar', 'losbar']):
            return 'Guy Losbar'
        elif any(term in text_lower for term in ['cd971', 'conseil départemental']):
            return 'CD971'
        elif 'sarkozy' in text_lower:
            return 'Sarkozy'
        else:
            return 'actualités_locales'

    def _calculate_engagement_score(self, item: Dict, text: str) -> int:
        """Calculer un score d'engagement composite"""
        likes = self._safe_int(item.get('likesCount', 0))
        text_length = len(text)
        
        return likes * 2 + text_length // 10

    def _safe_int(self, value) -> int:
        """Conversion sécurisée en entier"""
        try:
            return int(value) if value is not None else 0
        except (ValueError, TypeError):
            return 0

    def _save_posts(self, posts: List[Dict]) -> int:
        """Sauvegarder les posts en base"""
        saved_count = 0
        for post in posts:
            try:
                self.posts_collection.update_one(
                    {'id': post['id']},
                    {'$set': post},
                    upsert=True
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Erreur sauvegarde post: {e}")
        
        return saved_count

    def _save_comments(self, comments: List[Dict]) -> int:
        """Sauvegarder les commentaires en base"""
        saved_count = 0
        for comment in comments:
            try:
                self.comments_collection.update_one(
                    {'id': comment['id']},
                    {'$set': comment},
                    upsert=True
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Erreur sauvegarde commentaire: {e}")
        
        return saved_count

    def _analyze_sentiment_stats(self, comments: List[Dict]) -> Dict[str, Any]:
        """Analyser les statistiques de sentiment"""
        if not comments:
            return {}
        
        sentiments = [c['sentiment'] for c in comments if 'sentiment' in c]
        
        stats = {
            'total_comments': len(comments),
            'positive': sentiments.count('positive'),
            'negative': sentiments.count('negative'),
            'neutral': sentiments.count('neutral')
        }
        
        # Calculer les pourcentages
        if stats['total_comments'] > 0:
            stats['positive_pct'] = round((stats['positive'] / stats['total_comments']) * 100, 1)
            stats['negative_pct'] = round((stats['negative'] / stats['total_comments']) * 100, 1)
            stats['neutral_pct'] = round((stats['neutral'] / stats['total_comments']) * 100, 1)
        
        return stats

    def get_facebook_stats(self) -> Dict[str, Any]:
        """Récupérer les statistiques Facebook"""
        try:
            total_posts = self.posts_collection.count_documents({'platform': {'$regex': 'facebook'}})
            total_comments = self.comments_collection.count_documents({})
            
            # Top posts par engagement
            top_posts = list(self.posts_collection.find({
                'platform': {'$regex': 'facebook'},
                'total_engagement': {'$exists': True}
            }).sort('total_engagement', -1).limit(5))
            
            # Stats par sentiment
            sentiment_stats = {}
            for sentiment in ['positive', 'negative', 'neutral']:
                sentiment_stats[sentiment] = self.comments_collection.count_documents({
                    'sentiment': sentiment
                })
            
            return {
                'total_posts': total_posts,
                'total_comments': total_comments,
                'top_posts': [
                    {
                        'content': post.get('content', '')[:80] + '...',
                        'engagement': post.get('total_engagement', 0),
                        'author': post.get('author', ''),
                        'date': post.get('date', '')
                    }
                    for post in top_posts
                ],
                'sentiment_breakdown': sentiment_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération stats: {e}")
            return {'error': str(e)}

# Instance globale
facebook_service = FacebookService()

if __name__ == "__main__":
    # Test du service
    print("=== Test Service Facebook ===")
    
    # Test scraping posts
    result = facebook_service.scrape_posts(limit=10)
    print(f"Posts: {result}")
    
    # Test stats
    stats = facebook_service.get_facebook_stats()
    print(f"Stats: {stats}")
