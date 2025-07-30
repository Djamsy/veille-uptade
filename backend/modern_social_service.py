"""
Service moderne de réseaux sociaux pour la Guadeloupe - 2025
Remplace snscrape/Playwright par des solutions fiables et gratuites:
- Twitter API v2 (Bearer Token)
- Nitter comme fallback
- RSS feeds officiels
- Sources locales Guadeloupe
"""
import requests
import feedparser
import logging
import os
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModernSocialMediaService:
    def __init__(self):
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.social_collection = self.db.social_media_posts
            logger.info("✅ Connexion MongoDB réussie pour réseaux sociaux modernes")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration Twitter API v2
        self.twitter_bearer_token = "AAAAAAAAAAAAAAAAAAAAAFJR3QEAAAAAnkX1t%2FDFat7Ew%2BhH2QcTOtKrXOY%3D7b9DPe3oIMTcRDnM51YVO3XswfI6ckZLlbg7UCU9S1Xl6OeHD7"
        self.twitter_headers = {
            'Authorization': f'Bearer {self.twitter_bearer_token}',
            'Content-Type': 'application/json'
        }
        
        # Mots-clés spécifiques Guadeloupe
        self.keywords_guadeloupe = [
            "Guy Losbar", "Conseil Départemental Guadeloupe", "CD971",
            "Département Guadeloupe", "Losbar", "Basse-Terre politique",
            "Collectivité Guadeloupe", "Budget départemental"
        ]
        
        # URLs Nitter (fallback gratuit)
        self.nitter_instances = [
            "https://nitter.net",
            "https://nitter.it",
            "https://nitter.fdn.fr",
            "https://nitter.1d4.us"
        ]
        
        # RSS Feeds officiels Guadeloupe
        self.official_rss_feeds = {
            'conseil_departemental': 'https://www.cg971.fr/rss.xml',
            'prefecture': 'https://www.guadeloupe.gouv.fr/layout/rss',
            'region': 'https://www.regionguadeloupe.fr/rss.xml',
            'actualites_guadeloupe': 'https://www.guadeloupe.fr/rss.xml'
        }
        
        self.rate_limit_delay = 1  # Plus rapide avec API officielle
        self.max_posts_per_source = 25

    def search_twitter_api_v2(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Utiliser l'API Twitter v2 pour rechercher des tweets"""
        try:
            # Construction de la requête pour la Guadeloupe
            if query.lower() in ['guy losbar', 'losbar']:
                search_query = f'"Guy Losbar" OR "Losbar" OR "président conseil départemental" lang:fr'
            elif query.lower() in ['conseil départemental', 'cd971']:
                search_query = f'"Conseil Départemental" OR "CD971" OR "département guadeloupe" lang:fr'
            else:
                search_query = f'{query} (guadeloupe OR gwada OR 971 OR antilles) lang:fr -is:retweet'
            
            # Endpoint Twitter API v2
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                'query': search_query,
                'max_results': min(max_results, 100),  # API limit
                'tweet.fields': 'created_at,author_id,public_metrics,lang,context_annotations',
                'user.fields': 'username,name,public_metrics,verified',
                'expansions': 'author_id'
            }
            
            logger.info(f"🔍 Recherche Twitter API v2: {search_query}")
            
            response = requests.get(url, headers=self.twitter_headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                tweets = data.get('data', [])
                users = {user['id']: user for user in data.get('includes', {}).get('users', [])}
                
                posts = []
                for tweet in tweets:
                    user = users.get(tweet['author_id'], {})
                    
                    # Filtrer pour la pertinence Guadeloupe
                    content = tweet.get('text', '').lower()
                    is_relevant = any(keyword.lower() in content for keyword in [
                        'guy losbar', 'losbar', 'conseil départemental', 'cd971', 
                        'guadeloupe', 'gwada', 'département'
                    ])
                    
                    if not is_relevant:
                        continue
                    
                    metrics = tweet.get('public_metrics', {})
                    total_engagement = (
                        metrics.get('like_count', 0) + 
                        metrics.get('retweet_count', 0) + 
                        metrics.get('reply_count', 0)
                    )
                    
                    post_data = {
                        'id': f'twitter_api_{tweet["id"]}',
                        'platform': 'twitter',
                        'source_method': 'twitter_api_v2',
                        'keyword_searched': query,
                        'content': tweet.get('text', ''),
                        'author': user.get('username', 'unknown'),
                        'author_name': user.get('name', ''),
                        'author_followers': user.get('public_metrics', {}).get('followers_count', 0),
                        'author_verified': user.get('verified', False),
                        'created_at': tweet.get('created_at', datetime.now().isoformat()),
                        'engagement': {
                            'likes': metrics.get('like_count', 0),
                            'retweets': metrics.get('retweet_count', 0),
                            'replies': metrics.get('reply_count', 0),
                            'quotes': metrics.get('quote_count', 0),
                            'total': total_engagement
                        },
                        'url': f"https://twitter.com/{user.get('username', 'twitter')}/status/{tweet['id']}",
                        'scraped_at': datetime.now().isoformat(),
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'language': tweet.get('lang', 'fr'),
                        'demo_data': False,
                        'relevance_score': total_engagement + (100 if 'guy losbar' in content else 50)
                    }
                    
                    # Détecter les figures politiques mentionnées
                    if any(name in content for name in ['guy losbar', 'losbar']):
                        post_data['political_figure'] = 'Guy Losbar'
                    elif 'ary chalus' in content:
                        post_data['political_figure'] = 'Ary Chalus'
                    
                    posts.append(post_data)
                
                # Trier par pertinence
                posts.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                
                logger.info(f"✅ Twitter API v2 {query}: {len(posts)} posts récupérés")
                return posts
                
            elif response.status_code == 429:
                logger.warning("⚠️ Limite Twitter API atteinte, utilisation de Nitter comme fallback")
                return self.search_nitter_fallback(query, max_results)
            else:
                logger.error(f"❌ Erreur Twitter API: {response.status_code} - {response.text}")
                return self.search_nitter_fallback(query, max_results)
                
        except Exception as e:
            logger.error(f"❌ Erreur Twitter API v2: {e}")
            return self.search_nitter_fallback(query, max_results)

    def search_nitter_fallback(self, query: str, max_results: int = 30) -> List[Dict[str, Any]]:
        """Utiliser Nitter comme fallback gratuit"""
        posts = []
        
        for nitter_instance in self.nitter_instances:
            try:
                # Construction URL Nitter
                search_query = query.replace(' ', '%20')
                url = f"{nitter_instance}/search?f=tweets&q={search_query}%20guadeloupe"
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    tweets = soup.find_all('div', class_='timeline-item')
                    
                    for tweet in tweets[:max_results]:
                        try:
                            # Extraire les données du tweet
                            content_elem = tweet.find('div', class_='tweet-content')
                            if not content_elem:
                                continue
                                
                            content = content_elem.get_text(strip=True)
                            
                            # Filtrer pour pertinence Guadeloupe
                            if not any(keyword.lower() in content.lower() for keyword in self.keywords_guadeloupe):
                                continue
                            
                            # Extraire métadonnées
                            username_elem = tweet.find('a', class_='username')
                            username = username_elem.get_text(strip=True) if username_elem else 'unknown'
                            
                            date_elem = tweet.find('span', class_='tweet-date')
                            tweet_date = date_elem.get('title') if date_elem else datetime.now().isoformat()
                            
                            # Stats d'engagement (approximatives depuis Nitter)
                            stats_elems = tweet.find_all('span', class_='tweet-stat')
                            likes = retweets = replies = 0
                            
                            for stat in stats_elems:
                                text = stat.get_text(strip=True)
                                if '❤' in text:
                                    likes = int(re.findall(r'\d+', text)[0]) if re.findall(r'\d+', text) else 0
                                elif '🔁' in text:
                                    retweets = int(re.findall(r'\d+', text)[0]) if re.findall(r'\d+', text) else 0
                                elif '💬' in text:
                                    replies = int(re.findall(r'\d+', text)[0]) if re.findall(r'\d+', text) else 0
                            
                            post_data = {
                                'id': f'nitter_{hash(content + username)}',
                                'platform': 'twitter',
                                'source_method': 'nitter_fallback',
                                'keyword_searched': query,
                                'content': content,
                                'author': username.replace('@', ''),
                                'author_name': username,
                                'author_followers': 0,  # Non disponible via Nitter
                                'author_verified': False,
                                'created_at': tweet_date,
                                'engagement': {
                                    'likes': likes,
                                    'retweets': retweets,
                                    'replies': replies,
                                    'quotes': 0,
                                    'total': likes + retweets + replies
                                },
                                'url': f"{nitter_instance}{username}/status/{hash(content)}",
                                'scraped_at': datetime.now().isoformat(),
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'language': 'fr',
                                'demo_data': False,
                                'relevance_score': (likes + retweets + replies) + (50 if 'guy losbar' in content.lower() else 25)
                            }
                            
                            posts.append(post_data)
                            
                        except Exception as e:
                            logger.warning(f"Erreur extraction tweet Nitter: {e}")
                            continue
                    
                    if posts:
                        logger.info(f"✅ Nitter {nitter_instance}: {len(posts)} posts récupérés")
                        break  # Succès avec cette instance
                    
            except Exception as e:
                logger.warning(f"Erreur instance Nitter {nitter_instance}: {e}")
                continue
        
        posts.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return posts[:max_results]

    def scrape_official_rss_feeds(self) -> List[Dict[str, Any]]:
        """Récupérer les flux RSS officiels de Guadeloupe"""
        posts = []
        
        for source_name, rss_url in self.official_rss_feeds.items():
            try:
                logger.info(f"📡 Récupération RSS {source_name}: {rss_url}")
                
                feed = feedparser.parse(rss_url)
                
                if feed.entries:
                    for entry in feed.entries[:self.max_posts_per_source]:
                        # Filtrer pour les sujets pertinents
                        title = entry.get('title', '')
                        summary = entry.get('summary', '')
                        content = f"{title} {summary}".lower()
                        
                        # Vérifier la pertinence pour les mots-clés Guadeloupe
                        is_relevant = any(keyword.lower() in content for keyword in self.keywords_guadeloupe + [
                            'budget', 'conseil', 'départemental', 'politique', 'élection', 'développement'
                        ])
                        
                        if not is_relevant:
                            continue
                        
                        # Date de publication
                        pub_date = entry.get('published_parsed')
                        if pub_date:
                            pub_datetime = datetime(*pub_date[:6])
                        else:
                            pub_datetime = datetime.now()
                        
                        post_data = {
                            'id': f'rss_{source_name}_{hash(title)}',
                            'platform': 'rss_official',
                            'source_method': 'rss_feed',
                            'source_name': source_name,
                            'keyword_searched': 'official_feed',
                            'content': f"{title}\n\n{summary}",
                            'title': title,
                            'summary': summary,
                            'author': source_name.replace('_', ' ').title(),
                            'author_name': f"Source officielle {source_name}",
                            'author_followers': 10000,  # Estimation pour sources officielles
                            'author_verified': True,
                            'created_at': pub_datetime.isoformat(),
                            'engagement': {
                                'likes': 0,
                                'retweets': 0, 
                                'replies': 0,
                                'shares': 0,
                                'total': 0
                            },
                            'url': entry.get('link', rss_url),
                            'scraped_at': datetime.now().isoformat(),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'language': 'fr',
                            'demo_data': False,
                            'relevance_score': 75,  # Score élevé pour sources officielles
                            'official_source': True
                        }
                        
                        posts.append(post_data)
                
                logger.info(f"✅ RSS {source_name}: {len([p for p in posts if p['source_name'] == source_name])} articles récupérés")
                
            except Exception as e:
                logger.warning(f"Erreur RSS {source_name}: {e}")
                continue
        
        return posts

    def scrape_all_modern_sources(self, keywords: List[str] = None) -> Dict[str, Any]:
        """Scraper toutes les sources modernes pour récupérer du contenu pertinent"""
        if not keywords:
            keywords = self.keywords_guadeloupe[:3]  # Limiter pour éviter les quotas
        
        results = {
            'twitter_api': [],
            'twitter_nitter': [],
            'rss_official': [],
            'total_posts': 0,
            'keywords_searched': keywords,
            'scraped_at': datetime.now().isoformat(),
            'demo_mode': False,
            'methods_used': [],
            'success_rate': {},
            'note': 'Sources modernes fiables - Twitter API v2 + Nitter + RSS officiels'
        }
        
        logger.info(f"🚀 Scraping moderne pour {len(keywords)} mots-clés")
        
        # 1. Twitter API v2 (priorité)
        twitter_api_posts = []
        api_success_count = 0
        
        for keyword in keywords:
            try:
                posts = self.search_twitter_api_v2(keyword, self.max_posts_per_source)
                twitter_api_posts.extend(posts)
                if posts:
                    api_success_count += 1
                logger.info(f"Twitter API {keyword}: {len(posts)} posts")
                time.sleep(self.rate_limit_delay)
                
            except Exception as e:
                logger.warning(f"Erreur Twitter API pour {keyword}: {e}")
        
        results['twitter_api'] = twitter_api_posts
        results['methods_used'].append('twitter_api_v2')
        results['success_rate']['twitter_api'] = f"{api_success_count}/{len(keywords)}"
        
        # 2. RSS Feeds officiels (toujours fiables)
        try:
            rss_posts = self.scrape_official_rss_feeds()
            results['rss_official'] = rss_posts
            results['methods_used'].append('rss_feeds')
            results['success_rate']['rss_feeds'] = "100%" if rss_posts else "0%"
            logger.info(f"RSS officiels: {len(rss_posts)} articles")
            
        except Exception as e:
            logger.warning(f"Erreur RSS feeds: {e}")
        
        # 3. Nitter comme fallback si API limitée
        if len(twitter_api_posts) < 10:  # Seuil minimum
            logger.info("🔄 Utilisation Nitter comme complément")
            nitter_posts = []
            nitter_success_count = 0
            
            for keyword in keywords[:2]:  # Limiter Nitter pour éviter IP ban
                try:
                    posts = self.search_nitter_fallback(keyword, 15)
                    nitter_posts.extend(posts)
                    if posts:
                        nitter_success_count += 1
                    logger.info(f"Nitter {keyword}: {len(posts)} posts")
                    time.sleep(2)  # Plus d'attente pour Nitter
                    
                except Exception as e:
                    logger.warning(f"Erreur Nitter pour {keyword}: {e}")
            
            results['twitter_nitter'] = nitter_posts
            results['methods_used'].append('nitter_fallback')
            results['success_rate']['nitter'] = f"{nitter_success_count}/{min(len(keywords), 2)}"
        
        # Calculer totaux
        results['total_posts'] = len(results['twitter_api']) + len(results['twitter_nitter']) + len(results['rss_official'])
        
        # Message de résultat
        if results['total_posts'] > 0:
            results['note'] = f"✅ {results['total_posts']} posts récupérés via méthodes modernes fiables"
        else:
            results['note'] = "⚠️ Aucun post récupéré - vérifier connectivité ou quotas API"
        
        logger.info(f"✅ Scraping moderne terminé: {results['total_posts']} posts total")
        logger.info(f"📊 Méthodes utilisées: {', '.join(results['methods_used'])}")
        
        return results

    def save_posts_to_db(self, posts: List[Dict[str, Any]]) -> int:
        """Sauvegarder les posts en base de données"""
        try:
            if not posts:
                return 0
            
            saved_count = 0
            for post in posts:
                try:
                    # Upsert pour éviter les doublons
                    self.social_collection.update_one(
                        {'id': post['id']},
                        {'$set': post},
                        upsert=True
                    )
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Erreur sauvegarde post: {e}")
            
            logger.info(f"💾 {saved_count} posts sauvegardés en base")
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde base: {e}")
            return 0

    def get_recent_posts(self, days: int = 1, platform: str = None) -> List[Dict[str, Any]]:
        """Récupérer les posts récents de la base"""
        try:
            since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            query = {'date': {'$gte': since_date}}
            if platform:
                query['platform'] = platform
            
            posts = list(self.social_collection.find(
                query, 
                {'_id': 0}
            ).sort('scraped_at', -1).limit(100))
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération posts: {e}")
            return []

    def get_posts_stats(self) -> Dict[str, Any]:
        """Obtenir les statistiques des posts avec méthodes modernes"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Compter par plateforme et méthode
            twitter_api_count = self.social_collection.count_documents({
                'platform': 'twitter', 
                'source_method': 'twitter_api_v2',
                'date': today
            })
            
            twitter_nitter_count = self.social_collection.count_documents({
                'platform': 'twitter',
                'source_method': 'nitter_fallback', 
                'date': today
            })
            
            rss_count = self.social_collection.count_documents({
                'platform': 'rss_official',
                'date': today
            })
            
            # Top mots-clés
            pipeline = [
                {'$match': {'date': today}},
                {'$group': {'_id': '$keyword_searched', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 5}
            ]
            top_keywords = list(self.social_collection.aggregate(pipeline))
            
            # Statistiques par méthode
            methods_stats = {
                'twitter_api_v2': twitter_api_count,
                'nitter_fallback': twitter_nitter_count,
                'rss_feeds': rss_count
            }
            
            total_today = twitter_api_count + twitter_nitter_count + rss_count
            
            return {
                'total_today': total_today,
                'by_platform': {
                    'twitter': twitter_api_count + twitter_nitter_count,
                    'rss_official': rss_count,
                    'facebook': 0,  # Deprecated
                    'instagram': 0  # Deprecated
                },
                'by_method': methods_stats,
                'top_keywords': [
                    {'keyword': item['_id'], 'count': item['count']}
                    for item in top_keywords
                ],
                'demo_mode': False,
                'methods_available': ['twitter_api_v2', 'nitter_fallback', 'rss_feeds'],
                'last_updated': datetime.now().isoformat(),
                'service_version': 'modern_2025'
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur stats: {e}")
            return {}

    def clean_demo_data_from_db(self):
        """Nettoyer les anciennes données de démonstration"""
        try:
            result = self.social_collection.delete_many({'demo_data': True})
            logger.info(f"🧹 {result.deleted_count} posts de démonstration supprimés")
            return result.deleted_count
        except Exception as e:
            logger.error(f"❌ Erreur nettoyage données démo: {e}")
            return 0

# Instance globale
modern_social_scraper = ModernSocialMediaService()

if __name__ == "__main__":
    # Test du service moderne
    print("=== Test du service réseaux sociaux moderne ===")
    
    # Test avec les mots-clés Guadeloupe
    test_keywords = ["Guy Losbar", "CD971"]
    results = modern_social_scraper.scrape_all_modern_sources(test_keywords)
    
    print(f"Résultats: {results['total_posts']} posts")
    print(f"Twitter API: {len(results['twitter_api'])} posts")
    print(f"Twitter Nitter: {len(results['twitter_nitter'])} posts") 
    print(f"RSS Officiel: {len(results['rss_official'])} posts")
    print(f"Méthodes utilisées: {', '.join(results['methods_used'])}")
    
    # Sauvegarder en base
    all_posts = results['twitter_api'] + results['twitter_nitter'] + results['rss_official']
    saved = modern_social_scraper.save_posts_to_db(all_posts)
    print(f"Sauvegardés: {saved} posts")