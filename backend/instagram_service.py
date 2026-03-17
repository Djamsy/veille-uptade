# backend/instagram_service.py
"""
Service Instagram complet pour la veille départementale Guadeloupe
- Actor Apify pour posts et commentaires Instagram
- Comptes médias guadeloupéens (RCI, France-Antilles, etc.)
- Analyse d'engagement et sentiment
- Sauvegarde MongoDB avec métriques détaillées
"""

import os
import re
import time
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from pymongo.errors import ConfigurationError
from apify_client import ApifyClient
from dotenv import load_dotenv
import certifi

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

class InstagramService:
    def __init__(self):
        # Configuration MongoDB
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            if MONGO_URL.startswith("mongodb+srv"):
                self.mongo_client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
            else:
                self.mongo_client = MongoClient(MONGO_URL)
            self.db = self.mongo_client.veille_media
            self.collection = self.db.social_media_posts
            self.comments_collection = self.db.instagram_comments
            logger.info("✅ Connexion MongoDB Instagram réussie")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration Apify
        self.apify_client = ApifyClient(os.getenv('APIFY_API_TOKEN'))
        self.posts_actor_id = 'shu8hvrXbJbY3Eb9W'  # Actor profils Instagram
        self.comments_actor_id = 'SbK00X0JYCPblD2wp'  # Actor commentaires Instagram
        
        # Comptes Instagram guadeloupéens
        self.guadeloupe_accounts = [
            'https://www.instagram.com/rciguadeloupe/',
            'https://www.instagram.com/franceantilles_guadeloupe/', 
            'https://www.instagram.com/guadeloupela1ere/',
            'https://www.instagram.com/la_pause_sans_filtre21/',
            'https://www.instagram.com/metooguadeloupe/'
        ]
        
        # Hashtags locaux à surveiller
        self.local_hashtags = [
            '#guadeloupe',
            '#gwada', 
            '#cd971',
            '#guylosbar',
            '#conseildepar mental',
            '#basseterre'
        ]
        
        self.rate_limit_delay = 3
        self.max_posts_per_account = 12  # Limité en mode gratuit

    def scrape_instagram_posts(self, accounts: List[str] = None) -> List[Dict[str, Any]]:
        """Scraper principal Instagram - posts des comptes locaux"""
        
        if accounts is None:
            accounts = self.guadeloupe_accounts
            
        all_posts = []
        
        logger.info(f"📸 Scraping Instagram - {len(accounts)} comptes")
        
        for account_url in accounts:
            account_name = account_url.split('/')[-2]
            logger.info(f"🔄 Scraping @{account_name}...")
            
            posts = self._scrape_account_posts(account_url, account_name)
            all_posts.extend(posts)
            
            # Pause entre comptes
            time.sleep(self.rate_limit_delay)
        
        # Enrichissement des posts
        enriched_posts = []
        for post in all_posts:
            enriched = self._enrich_post(post)
            enriched_posts.append(enriched)
        
        # Trier par engagement
        enriched_posts.sort(key=lambda x: x.get('engagement', {}).get('total', 0), reverse=True)
        
        logger.info(f"📊 Total posts Instagram: {len(enriched_posts)}")
        return enriched_posts

    def _scrape_account_posts(self, account_url: str, account_name: str) -> List[Dict[str, Any]]:
        """Scraper les posts d'un compte Instagram"""
        posts = []
        
        run_input = {
            'directUrls': [account_url],
            'resultsType': 'posts',
            'resultsLimit': self.max_posts_per_account,
            'searchType': 'hashtag',
            'searchLimit': 1,
            'addParentData': False
        }
        
        try:
            run = self.apify_client.actor(self.posts_actor_id).call(run_input=run_input)
            
            for item in self.apify_client.dataset(run['defaultDatasetId']).iterate_items():
                
                # Ignorer données démo
                if item.get('demo'):
                    continue
                
                # Extraire données du post
                post_data = {
                    'id': f'instagram_{uuid.uuid4().hex[:10]}',
                    'platform': 'instagram',
                    'source_method': 'apify_instagram',
                    'account': account_name,
                    'account_url': account_url,
                    'content': item.get('caption', ''),
                    'author': account_name,
                    'post_type': item.get('type', 'post'),  # post, reel, video
                    'url': item.get('url', ''),
                    'image_url': item.get('displayUrl', ''),
                    'video_url': item.get('videoUrl', ''),
                    'created_at': item.get('timestamp', datetime.now().isoformat()),
                    'engagement': {
                        'likes': item.get('likesCount', 0),
                        'comments': item.get('commentsCount', 0), 
                        'total': item.get('likesCount', 0) + item.get('commentsCount', 0)
                    },
                    'hashtags': self._extract_hashtags(item.get('caption', '')),
                    'mentions': self._extract_mentions(item.get('caption', '')),
                    'scraped_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'demo_data': False
                }
                
                posts.append(post_data)
                
        except Exception as e:
            logger.error(f"❌ Erreur scraping @{account_name}: {e}")
        
        logger.info(f"  ✅ @{account_name}: {len(posts)} posts récupérés")
        return posts

    def scrape_instagram_comments(self, post_urls: List[str], max_comments: int = 20) -> List[Dict[str, Any]]:
        """Scraper les commentaires de posts Instagram spécifiques"""
        
        if not post_urls:
            logger.warning("Aucune URL de post fournie pour les commentaires")
            return []
        
        logger.info(f"💬 Scraping commentaires - {len(post_urls)} posts")
        
        run_input = {
            'directUrls': post_urls[:5],  # Limiter en mode gratuit
            'resultsLimit': max_comments
        }
        
        comments = []
        
        try:
            run = self.apify_client.actor(self.comments_actor_id).call(run_input=run_input)
            
            for item in self.apify_client.dataset(run['defaultDatasetId']).iterate_items():
                
                # Vérifier si c'est un vrai commentaire
                if 'text' in item and 'ownerUsername' in item:
                    
                    comment_data = {
                        'id': f'ig_comment_{uuid.uuid4().hex[:8]}',
                        'platform': 'instagram',
                        'post_url': item.get('postUrl', ''),
                        'comment_url': item.get('commentUrl', ''),
                        'text': item.get('text', ''),
                        'author': item.get('ownerUsername', ''),
                        'author_profile_pic': item.get('ownerProfilePicUrl', ''),
                        'likes': item.get('likesCount', 0),
                        'replies_count': item.get('repliesCount', 0),
                        'timestamp': item.get('timestamp', ''),
                        'replies': item.get('replies', []),
                        'sentiment': self._analyze_sentiment(item.get('text', '')),
                        'scraped_at': datetime.now().isoformat(),
                        'processed': True
                    }
                    
                    comments.append(comment_data)
                
        except Exception as e:
            logger.error(f"❌ Erreur scraping commentaires: {e}")
        
        logger.info(f"💬 Commentaires extraits: {len(comments)}")
        return comments

    def get_top_posts_for_comments(self, min_engagement: int = 50) -> List[str]:
        """Récupérer les URLs des posts avec le plus d'engagement pour extraction commentaires"""
        
        try:
            # Chercher posts Instagram récents avec fort engagement
            top_posts = list(self.collection.find({
                'platform': 'instagram',
                'engagement.total': {'$gte': min_engagement},
                'url': {'$exists': True, '$ne': ''}
            }).sort('engagement.total', -1).limit(10))
            
            post_urls = [post['url'] for post in top_posts if post.get('url')]
            
            logger.info(f"📈 Posts sélectionnés pour commentaires: {len(post_urls)}")
            return post_urls
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération top posts: {e}")
            return []

    def _enrich_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichir post avec analyse locale"""
        content = post.get('content', '').lower()
        
        # Score de pertinence départementale
        relevance_score = post.get('engagement', {}).get('total', 0)
        
        # Boost selon contenu local
        if any(term in content for term in ['guy losbar', 'losbar']):
            relevance_score += 100
            post['political_figure'] = 'Guy Losbar'
        elif any(term in content for term in ['cd971', 'conseil départemental']):
            relevance_score += 75
            post['political_figure'] = 'CD971'
        
        if any(term in content for term in ['guadeloupe', 'gwada']):
            relevance_score += 30
        
        # Analyse sentiment
        post['sentiment'] = self._analyze_sentiment(content)
        post['relevance_score'] = relevance_score
        
        # Classification thématique
        post['topic_category'] = self._classify_topic(content)
        
        # Détection du type de contenu
        post['content_type'] = self._detect_content_type(post)
        
        return post

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extraire hashtags du texte"""
        if not text:
            return []
        return re.findall(r'#\w+', text.lower())

    def _extract_mentions(self, text: str) -> List[str]:
        """Extraire mentions du texte"""
        if not text:
            return []
        return re.findall(r'@\w+', text.lower())

    def _analyze_sentiment(self, text: str) -> str:
        """Analyse de sentiment basique"""
        if not text:
            return 'neutral'
            
        text = text.lower()
        
        positive_words = ['bravo', 'merci', 'super', 'excellent', 'magnifique', '❤️', '👏', '😍']
        negative_words = ['scandale', 'honte', 'inadmissible', 'catastrophe', 'triste', '😡', '😢']
        
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        return 'neutral'

    def _classify_topic(self, text: str) -> str:
        """Classification thématique"""
        if not text:
            return 'Général'
            
        text = text.lower()
        
        if any(term in text for term in ['météo', 'cyclone', 'ouragan', 'vigilance']):
            return 'Météo/Alerte'
        elif any(term in text for term in ['route', 'circulation', 'embouteillage']):
            return 'Transport'
        elif any(term in text for term in ['santé', 'hôpital', 'chu']):
            return 'Santé'
        elif any(term in text for term in ['école', 'éducation', 'collège', 'lycée']):
            return 'Éducation'
        elif any(term in text for term in ['culture', 'carnaval', 'festival', 'musique']):
            return 'Culture'
        elif any(term in text for term in ['sport', 'football', 'basket']):
            return 'Sport'
        elif any(term in text for term in ['économie', 'emploi', 'entreprise']):
            return 'Économie'
        else:
            return 'Actualité générale'

    def _detect_content_type(self, post: Dict[str, Any]) -> str:
        """Détecter le type de contenu"""
        if post.get('video_url'):
            return 'video'
        elif post.get('post_type') == 'reel':
            return 'reel'
        elif post.get('image_url'):
            return 'image'
        else:
            return 'text'

    def save_posts_to_db(self, posts: List[Dict[str, Any]]) -> int:
        """Sauvegarder posts Instagram en MongoDB"""
        if not posts:
            return 0
        
        saved_count = 0
        
        for post in posts:
            try:
                # Éviter les doublons
                existing = self.collection.find_one({
                    'url': post.get('url')
                })
                
                if not existing:
                    self.collection.insert_one(post)
                    saved_count += 1
                else:
                    # Mettre à jour l'engagement si plus récent
                    if post.get('engagement', {}).get('total', 0) > existing.get('engagement', {}).get('total', 0):
                        self.collection.update_one(
                            {'_id': existing['_id']},
                            {'$set': {'engagement': post.get('engagement')}}
                        )
                        
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde post Instagram: {e}")
        
        logger.info(f"💾 Posts Instagram sauvegardés: {saved_count}/{len(posts)}")
        return saved_count

    def save_comments_to_db(self, comments: List[Dict[str, Any]]) -> int:
        """Sauvegarder commentaires Instagram en MongoDB"""
        if not comments:
            return 0
        
        saved_count = 0
        
        for comment in comments:
            try:
                # Éviter les doublons
                existing = self.comments_collection.find_one({
                    'comment_url': comment.get('comment_url')
                })
                
                if not existing:
                    self.comments_collection.insert_one(comment)
                    saved_count += 1
                        
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde commentaire Instagram: {e}")
        
        logger.info(f"💬 Commentaires Instagram sauvegardés: {saved_count}/{len(comments)}")
        return saved_count

    def get_instagram_stats(self) -> Dict[str, Any]:
        """Statistiques Instagram"""
        try:
            total_posts = self.collection.count_documents({'platform': 'instagram'})
            total_comments = self.comments_collection.count_documents({})
            
            # Stats par compte
            accounts_stats = list(self.collection.aggregate([
                {'$match': {'platform': 'instagram'}},
                {'$group': {
                    '_id': '$account',
                    'posts_count': {'$sum': 1},
                    'total_engagement': {'$sum': '$engagement.total'},
                    'avg_engagement': {'$avg': '$engagement.total'}
                }},
                {'$sort': {'total_engagement': -1}}
            ]))
            
            # Top posts par engagement
            top_posts = list(self.collection.find(
                {'platform': 'instagram'},
                {'content': 1, 'account': 1, 'engagement.total': 1, 'url': 1}
            ).sort('engagement.total', -1).limit(5))
            
            # Stats par sentiment
            sentiment_stats = list(self.collection.aggregate([
                {'$match': {'platform': 'instagram'}},
                {'$group': {
                    '_id': '$sentiment',
                    'count': {'$sum': 1}
                }}
            ]))
            
            return {
                'total_posts': total_posts,
                'total_comments': total_comments,
                'accounts_stats': accounts_stats,
                'top_posts': top_posts,
                'sentiment_stats': sentiment_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur stats Instagram: {e}")
            return {'error': str(e)}

# Instance globale
instagram_service = InstagramService()

def run_instagram_scraping() -> Dict[str, Any]:
    """Fonction principale de scraping Instagram"""
    try:
        # 1. Scraper les posts
        posts = instagram_service.scrape_instagram_posts()
        posts_saved = instagram_service.save_posts_to_db(posts)
        
        # 2. Scraper les commentaires des top posts
        top_post_urls = instagram_service.get_top_posts_for_comments()
        comments = instagram_service.scrape_instagram_comments(top_post_urls)
        comments_saved = instagram_service.save_comments_to_db(comments)
        
        return {
            'success': True,
            'posts_found': len(posts),
            'posts_saved': posts_saved,
            'comments_found': len(comments),
            'comments_saved': comments_saved,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur scraping Instagram: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

if __name__ == "__main__":
    # Test du service
    print("📸 Test service Instagram...")
    result = run_instagram_scraping()
    print(f"Résultat: {result}")
