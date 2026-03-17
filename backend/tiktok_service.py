# backend/tiktok_service.py
"""
Service TikTok complet pour la veille départementale Guadeloupe
- Actor Apify pour posts et commentaires TikTok
- Comptes médias guadeloupéens (RCI, Guadeloupe la 1ère, etc.)
- Analyse d'engagement et sentiment vidéo
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

class TikTokService:
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
            self.comments_collection = self.db.tiktok_comments
            logger.info("✅ Connexion MongoDB TikTok réussie")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration Apify
        self.apify_client = ApifyClient(os.getenv('APIFY_API_TOKEN'))
        self.tiktok_actor_id = 'naqsZgh7DhGajnD5z'  # Actor TikTok Apify
        
        # Comptes TikTok guadeloupéens (avec user_id récupérés)
        self.guadeloupe_accounts = [
            {
                'username': 'rciguadeloupeoff',
                'display_name': 'RCI Guadeloupe',
                'user_id': '7243882077824533531',
                'sec_user_id': 'MS4wLjABAAAAasMJ0eq3y7qbOg81DDRaRqPagZ2W4BMrX5PEpFpn6kcOLnBl2CorYmOSPRwLdrQE',
                'followers': 19786
            },
            {
                'username': 'guadeloupela1ere',
                'display_name': 'Guadeloupe la 1ère',
                'user_id': '7083169886869111813', 
                'sec_user_id': 'MS4wLjABAAAACV-TMSp5nsDGoY6V9sxvW9mcAXt8lbOoTdH-LmeZIS0mHdhyJ9ztam36zFrk_iiz',
                'followers': 13071
            },
            {
                'username': 'lapausesansfiltre',
                'display_name': 'La Pause Sans Filtre',
                'user_id': '',  # À récupérer
                'sec_user_id': '',
                'followers': 0
            }
        ]
        
        # Hashtags locaux TikTok
        self.local_hashtags = [
            '#guadeloupe',
            '#gwada', 
            '#antilles',
            '#rci971',
            '#guylosbar',
            '#cd971'
        ]
        
        self.rate_limit_delay = 4
        self.max_posts_per_account = 10

    def scrape_tiktok_posts(self, accounts: List[Dict] = None) -> List[Dict[str, Any]]:
        """Scraper principal TikTok - posts des comptes locaux"""
        
        if accounts is None:
            accounts = [acc for acc in self.guadeloupe_accounts if acc['user_id']]  # Seulement ceux avec user_id
            
        all_posts = []
        
        logger.info(f"🎵 Scraping TikTok - {len(accounts)} comptes")
        
        for account in accounts:
            logger.info(f"🔄 Scraping @{account['username']}...")
            
            posts = self._scrape_account_posts(account)
            all_posts.extend(posts)
            
            # Pause entre comptes
            time.sleep(self.rate_limit_delay)
        
        # Enrichissement des posts
        enriched_posts = []
        for post in all_posts:
            enriched = self._enrich_post(post)
            enriched_posts.append(enriched)
        
        # Trier par engagement (TikTok privilégie les vues)
        enriched_posts.sort(key=lambda x: x.get('engagement', {}).get('views', 0), reverse=True)
        
        logger.info(f"📊 Total posts TikTok: {len(enriched_posts)}")
        return enriched_posts

    def _scrape_account_posts(self, account: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scraper les posts d'un compte TikTok"""
        posts = []
        
        run_input = {
            'userPosts_userId': account['user_id'],
            'userPosts_secUserId': account['sec_user_id'],
            'userPosts_count': self.max_posts_per_account,
            'userPosts_maxCursor': '0'
        }
        
        try:
            run = self.apify_client.actor(self.tiktok_actor_id).call(run_input=run_input)
            
            for item in self.apify_client.dataset(run['defaultDatasetId']).iterate_items():
                
                # Vérifier si c'est dans aweme_list
                if 'aweme_list' in item and isinstance(item['aweme_list'], list):
                    for aweme in item['aweme_list']:
                        post_data = self._extract_post_data(aweme, account)
                        if post_data:
                            posts.append(post_data)
                
                # Ou directement un post
                elif 'desc' in item or 'statistics' in item:
                    post_data = self._extract_post_data(item, account)
                    if post_data:
                        posts.append(post_data)
                        
        except Exception as e:
            logger.error(f"❌ Erreur scraping @{account['username']}: {e}")
        
        logger.info(f"  ✅ @{account['username']}: {len(posts)} posts récupérés")
        return posts

    def _extract_post_data(self, aweme: Dict[str, Any], account: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extraire les données d'un post TikTok depuis l'objet aweme"""
        
        try:
            # Statistiques d'engagement
            stats = aweme.get('statistics', {})
            
            # URL du post
            share_url = ''
            if 'share_url' in aweme:
                share_url = aweme['share_url']
            elif 'aweme_id' in aweme:
                share_url = f"https://www.tiktok.com/@{account['username']}/video/{aweme['aweme_id']}"
            
            # Informations vidéo
            video_info = aweme.get('video', {})
            video_url = ''
            if isinstance(video_info, dict) and 'play_addr' in video_info:
                play_addr = video_info['play_addr']
                if isinstance(play_addr, dict) and 'url_list' in play_addr:
                    video_urls = play_addr['url_list']
                    if video_urls:
                        video_url = video_urls[0]
            
            # Données du post
            post_data = {
                'id': f'tiktok_{uuid.uuid4().hex[:10]}',
                'platform': 'tiktok',
                'source_method': 'apify_tiktok',
                'account': account['username'],
                'account_display_name': account['display_name'],
                'author': account['username'],
                'aweme_id': aweme.get('aweme_id', ''),
                'content': aweme.get('desc', ''),
                'url': share_url,
                'video_url': video_url,
                'created_at': aweme.get('create_time', datetime.now().timestamp()),
                'engagement': {
                    'views': stats.get('play_count', 0),
                    'likes': stats.get('digg_count', 0),
                    'comments': stats.get('comment_count', 0), 
                    'shares': stats.get('share_count', 0),
                    'total': stats.get('digg_count', 0) + stats.get('comment_count', 0) + stats.get('share_count', 0)
                },
                'hashtags': self._extract_hashtags(aweme.get('desc', '')),
                'mentions': self._extract_mentions(aweme.get('desc', '')),
                'duration': video_info.get('duration', 0) if isinstance(video_info, dict) else 0,
                'scraped_at': datetime.now().isoformat(),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'demo_data': False
            }
            
            return post_data
            
        except Exception as e:
            logger.error(f"❌ Erreur extraction post TikTok: {e}")
            return None

    def scrape_tiktok_comments(self, aweme_ids: List[str], max_comments: int = 20) -> List[Dict[str, Any]]:
        """Scraper les commentaires de posts TikTok spécifiques"""
        
        if not aweme_ids:
            logger.warning("Aucun aweme_id fourni pour les commentaires")
            return []
        
        logger.info(f"💬 Scraping commentaires TikTok - {len(aweme_ids)} posts")
        
        comments = []
        
        for aweme_id in aweme_ids[:3]:  # Limiter en mode gratuit
            run_input = {
                'listComments_awemeId': aweme_id,
                'listComments_count': max_comments,
                'listComments_cursor': 0
            }
            
            try:
                run = self.apify_client.actor(self.tiktok_actor_id).call(run_input=run_input)
                
                for item in self.apify_client.dataset(run['defaultDatasetId']).iterate_items():
                    
                    # Vérifier structure commentaires TikTok
                    if 'comments' in item and isinstance(item['comments'], list):
                        for comment in item['comments']:
                            comment_data = {
                                'id': f'tiktok_comment_{uuid.uuid4().hex[:8]}',
                                'platform': 'tiktok',
                                'aweme_id': aweme_id,
                                'comment_id': comment.get('cid', ''),
                                'text': comment.get('text', ''),
                                'author': comment.get('user', {}).get('nickname', '') if isinstance(comment.get('user'), dict) else '',
                                'author_username': comment.get('user', {}).get('unique_id', '') if isinstance(comment.get('user'), dict) else '',
                                'likes': comment.get('digg_count', 0),
                                'replies_count': comment.get('reply_comment_total', 0),
                                'created_at': comment.get('create_time', ''),
                                'sentiment': self._analyze_sentiment(comment.get('text', '')),
                                'scraped_at': datetime.now().isoformat(),
                                'processed': True
                            }
                            
                            comments.append(comment_data)
                            
            except Exception as e:
                logger.error(f"❌ Erreur scraping commentaires TikTok {aweme_id}: {e}")
                
            time.sleep(2)  # Pause entre posts
        
        logger.info(f"💬 Commentaires TikTok extraits: {len(comments)}")
        return comments

    def get_top_posts_for_comments(self, min_views: int = 1000) -> List[str]:
        """Récupérer les aweme_id des posts avec le plus de vues pour extraction commentaires"""
        
        try:
            # Chercher posts TikTok récents avec fort engagement
            top_posts = list(self.collection.find({
                'platform': 'tiktok',
                'engagement.views': {'$gte': min_views},
                'aweme_id': {'$exists': True, '$ne': ''}
            }).sort('engagement.views', -1).limit(5))
            
            aweme_ids = [post['aweme_id'] for post in top_posts if post.get('aweme_id')]
            
            logger.info(f"📈 Posts TikTok sélectionnés pour commentaires: {len(aweme_ids)}")
            return aweme_ids
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération top posts TikTok: {e}")
            return []

    def _enrich_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichir post avec analyse locale"""
        content = post.get('content', '').lower()
        
        # Score de pertinence (TikTok privilégie les vues)
        views = post.get('engagement', {}).get('views', 0)
        total_engagement = post.get('engagement', {}).get('total', 0)
        relevance_score = views + (total_engagement * 10)
        
        # Boost selon contenu local
        if any(term in content for term in ['guy losbar', 'losbar']):
            relevance_score += 500
            post['political_figure'] = 'Guy Losbar'
        elif any(term in content for term in ['cd971', 'conseil départemental']):
            relevance_score += 300
            post['political_figure'] = 'CD971'
        
        if any(term in content for term in ['guadeloupe', 'gwada', 'antilles']):
            relevance_score += 100
        
        # Analyse sentiment
        post['sentiment'] = self._analyze_sentiment(content)
        post['relevance_score'] = relevance_score
        
        # Classification thématique
        post['topic_category'] = self._classify_topic(content)
        
        # Analyse de la durée vidéo
        post['duration_category'] = self._classify_duration(post.get('duration', 0))
        
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
        
        positive_words = ['super', 'génial', 'excellent', 'magnifique', 'bravo', '😍', '🔥', '👏', '❤️']
        negative_words = ['nul', 'mauvais', 'scandale', 'honte', 'catastrophe', '😡', '😢', '👎']
        
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
        
        if any(term in text for term in ['météo', 'cyclone', 'ouragan', 'alerte']):
            return 'Météo/Alerte'
        elif any(term in text for term in ['actualité', 'news', 'info']):
            return 'Actualités'
        elif any(term in text for term in ['culture', 'carnaval', 'musique', 'danse']):
            return 'Culture'
        elif any(term in text for term in ['sport', 'football', 'basket']):
            return 'Sport'
        elif any(term in text for term in ['politique', 'élection', 'maire']):
            return 'Politique'
        elif any(term in text for term in ['humor', 'drôle', 'blague', 'rire']):
            return 'Humour'
        else:
            return 'Vie quotidienne'

    def _classify_duration(self, duration: int) -> str:
        """Classifier selon la durée de la vidéo"""
        if duration <= 15:
            return 'Très court (<15s)'
        elif duration <= 30:
            return 'Court (15-30s)'
        elif duration <= 60:
            return 'Moyen (30-60s)'
        else:
            return 'Long (>60s)'

    def save_posts_to_db(self, posts: List[Dict[str, Any]]) -> int:
        """Sauvegarder posts TikTok en MongoDB"""
        if not posts:
            return 0
        
        saved_count = 0
        
        for post in posts:
            try:
                # Éviter les doublons par aweme_id
                existing = self.collection.find_one({
                    'aweme_id': post.get('aweme_id')
                })
                
                if not existing:
                    self.collection.insert_one(post)
                    saved_count += 1
                else:
                    # Mettre à jour l'engagement si plus récent
                    current_views = post.get('engagement', {}).get('views', 0)
                    existing_views = existing.get('engagement', {}).get('views', 0)
                    
                    if current_views > existing_views:
                        self.collection.update_one(
                            {'_id': existing['_id']},
                            {'$set': {'engagement': post.get('engagement')}}
                        )
                        
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde post TikTok: {e}")
        
        logger.info(f"💾 Posts TikTok sauvegardés: {saved_count}/{len(posts)}")
        return saved_count

    def save_comments_to_db(self, comments: List[Dict[str, Any]]) -> int:
        """Sauvegarder commentaires TikTok en MongoDB"""
        if not comments:
            return 0
        
        saved_count = 0
        
        for comment in comments:
            try:
                # Éviter les doublons par comment_id
                existing = self.comments_collection.find_one({
                    'comment_id': comment.get('comment_id')
                })
                
                if not existing:
                    self.comments_collection.insert_one(comment)
                    saved_count += 1
                        
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde commentaire TikTok: {e}")
        
        logger.info(f"💬 Commentaires TikTok sauvegardés: {saved_count}/{len(comments)}")
        return saved_count

    def get_tiktok_stats(self) -> Dict[str, Any]:
        """Statistiques TikTok"""
        try:
            total_posts = self.collection.count_documents({'platform': 'tiktok'})
            total_comments = self.comments_collection.count_documents({})
            
            # Stats par compte
            accounts_stats = list(self.collection.aggregate([
                {'$match': {'platform': 'tiktok'}},
                {'$group': {
                    '_id': '$account',
                    'posts_count': {'$sum': 1},
                    'total_views': {'$sum': '$engagement.views'},
                    'total_likes': {'$sum': '$engagement.likes'},
                    'avg_engagement': {'$avg': '$engagement.total'}
                }},
                {'$sort': {'total_views': -1}}
            ]))
            
            # Top posts par vues
            top_posts = list(self.collection.find(
                {'platform': 'tiktok'},
                {'content': 1, 'account': 1, 'engagement.views': 1, 'url': 1}
            ).sort('engagement.views', -1).limit(5))
            
            # Stats par durée
            duration_stats = list(self.collection.aggregate([
                {'$match': {'platform': 'tiktok'}},
                {'$group': {
                    '_id': '$duration_category',
                    'count': {'$sum': 1},
                    'avg_views': {'$avg': '$engagement.views'}
                }}
            ]))
            
            return {
                'total_posts': total_posts,
                'total_comments': total_comments,
                'accounts_stats': accounts_stats,
                'top_posts': top_posts,
                'duration_stats': duration_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur stats TikTok: {e}")
            return {'error': str(e)}

# Instance globale
tiktok_service = TikTokService()

def run_tiktok_scraping() -> Dict[str, Any]:
    """Fonction principale de scraping TikTok"""
    try:
        # 1. Scraper les posts
        posts = tiktok_service.scrape_tiktok_posts()
        posts_saved = tiktok_service.save_posts_to_db(posts)
        
        # 2. Scraper les commentaires des top posts
        top_aweme_ids = tiktok_service.get_top_posts_for_comments()
        comments = tiktok_service.scrape_tiktok_comments(top_aweme_ids)
        comments_saved = tiktok_service.save_comments_to_db(comments)
        
        return {
            'success': True,
            'posts_found': len(posts),
            'posts_saved': posts_saved,
            'comments_found': len(comments),
            'comments_saved': comments_saved,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur scraping TikTok: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

if __name__ == "__main__":
    # Test du service
    print("🎵 Test service TikTok...")
    result = run_tiktok_scraping()
    print(f"Résultat: {result}")
