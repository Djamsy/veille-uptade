# backend/twitter_service.py
"""
Service Twitter avec Apify pour la veille départementale Guadeloupe
- Actor Twitter Apify (avec gestion mode gratuit limité)
- Fallback API Twitter v2 Bearer Token
- Analyse des mentions politiques locales
- Sauvegarde MongoDB avec métriques d'engagement
"""

import os
import re
import time
import json
import uuid
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from pymongo.errors import ConfigurationError
from apify_client import ApifyClient
import certifi

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TwitterService:
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
            logger.info("✅ Connexion MongoDB Twitter réussie")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration Apify
        self.apify_client = ApifyClient(os.getenv('APIFY_API_TOKEN'))
        self.twitter_actor_id = '61RPP7dywgiy0JPD0'  # Actor Twitter Apify
        
        # Configuration Twitter API v2 (fallback)
        self.bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
        self.twitter_headers = {
            'Authorization': f'Bearer {self.bearer_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; GuadeloupeVeille/1.0)'
        }
        
        # Mots-clés spécifiques Guadeloupe
        self.keywords_guadeloupe = [
            "Guy Losbar",
            "Conseil Départemental Guadeloupe", 
            "CD971",
            "Département Guadeloupe",
            "Basse-Terre politique",
            "Collectivité Guadeloupe"
        ]
        
        # Comptes Twitter locaux à surveiller
        self.local_accounts = [
            "GuyLosbar971",
            "CD971", 
            "StimpflingEric",
            "guadeloupe_fr",
            "prefecture971"
        ]
        
        self.rate_limit_delay = 2
        self.max_tweets_per_query = 20

    def scrape_twitter_posts(self, keywords: List[str] = None, accounts: List[str] = None) -> List[Dict[str, Any]]:
        """Scraper principal Twitter - essaie Apify puis fallback API"""
        
        if keywords is None:
            keywords = self.keywords_guadeloupe
        if accounts is None:
            accounts = self.local_accounts
            
        all_tweets = []
        
        # 1. Essayer Apify d'abord
        logger.info("🐦 Tentative scraping Twitter via Apify...")
        apify_tweets = self._scrape_with_apify(keywords, accounts)
        
        if apify_tweets and len(apify_tweets) > 3:  # Si on a plus que des données demo
            logger.info(f"✅ Apify: {len(apify_tweets)} tweets récupérés")
            all_tweets.extend(apify_tweets)
        else:
            logger.warning("⚠️ Apify limité, fallback API Twitter...")
            # 2. Fallback API Twitter v2
            api_tweets = self._scrape_with_api(keywords)
            all_tweets.extend(api_tweets)
        
        # 3. Enrichissement et analyse
        enriched_tweets = []
        for tweet in all_tweets:
            enriched = self._enrich_tweet(tweet)
            enriched_tweets.append(enriched)
        
        # 4. Trier par pertinence
        enriched_tweets.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        logger.info(f"📊 Total tweets traités: {len(enriched_tweets)}")
        return enriched_tweets

    def _scrape_with_apify(self, keywords: List[str], accounts: List[str]) -> List[Dict[str, Any]]:
        """Scraping avec l'actor Apify Twitter"""
        tweets = []
        
        # Configuration pour recherches + comptes
        run_input = {
            'searchTerms': [f"{kw} (guadeloupe OR gwada OR 971)" for kw in keywords[:3]],  # Limiter en mode gratuit
            'twitterHandles': accounts[:3],  # Limiter pour éviter les timeouts
            'maxItems': 30,  # Limité en mode gratuit
            'sort': 'Latest',
            'tweetLanguage': 'fr'
        }
        
        try:
            logger.info(f"🔄 Apify scraping: {len(run_input['searchTerms'])} recherches + {len(run_input['twitterHandles'])} comptes")
            
            run = self.apify_client.actor(self.twitter_actor_id).call(run_input=run_input)
            
            for item in self.apify_client.dataset(run['defaultDatasetId']).iterate_items():
                # Vérifier si c'est des vraies données ou du demo
                if item.get('demo'):
                    continue
                    
                # Extraire les données Apify
                tweet_data = {
                    'id': f'apify_twitter_{uuid.uuid4().hex[:10]}',
                    'platform': 'twitter_apify',
                    'source_method': 'apify_actor',
                    'content': item.get('text', ''),
                    'author': item.get('author', {}).get('userName', '') if isinstance(item.get('author'), dict) else str(item.get('author', '')),
                    'author_name': item.get('author', {}).get('name', '') if isinstance(item.get('author'), dict) else '',
                    'author_followers': item.get('author', {}).get('followers', 0) if isinstance(item.get('author'), dict) else 0,
                    'created_at': item.get('createdAt', datetime.now().isoformat()),
                    'engagement': {
                        'likes': item.get('likes', 0),
                        'retweets': item.get('retweets', 0),
                        'replies': item.get('replies', 0),
                        'total': item.get('likes', 0) + item.get('retweets', 0) + item.get('replies', 0)
                    },
                    'url': item.get('url', ''),
                    'tweet_id': item.get('id', ''),
                    'scraped_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'demo_data': False
                }
                
                tweets.append(tweet_data)
                
        except Exception as e:
            logger.error(f"❌ Erreur Apify Twitter: {e}")
            
        return tweets

    def _scrape_with_api(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """Fallback avec API Twitter v2"""
        tweets = []
        
        url = "https://api.twitter.com/2/tweets/search/recent"
        
        for keyword in keywords[:3]:  # Limiter pour éviter les limites
            # Construction requête pour Guadeloupe
            search_query = f"{keyword} (guadeloupe OR gwada OR 971) -is:retweet lang:fr"
            
            params = {
                'query': search_query,
                'max_results': 20,
                'tweet.fields': 'created_at,public_metrics,author_id,lang',
                'user.fields': 'username,name,public_metrics,verified',
                'expansions': 'author_id'
            }
            
            try:
                response = requests.get(url, headers=self.twitter_headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'data' not in data:
                        continue
                    
                    # Créer mapping utilisateurs
                    users_map = {}
                    if 'includes' in data and 'users' in data['includes']:
                        for user in data['includes']['users']:
                            users_map[user['id']] = user
                    
                    for tweet in data['data']:
                        user = users_map.get(tweet['author_id'], {})
                        metrics = tweet.get('public_metrics', {})
                        
                        tweet_data = {
                            'id': f'api_twitter_{tweet["id"]}',
                            'platform': 'twitter_api',
                            'source_method': 'twitter_api_v2',
                            'keyword_searched': keyword,
                            'content': tweet.get('text', ''),
                            'author': user.get('username', 'unknown'),
                            'author_name': user.get('name', ''),
                            'author_id': tweet['author_id'],
                            'author_followers': user.get('public_metrics', {}).get('followers_count', 0),
                            'author_verified': user.get('verified', False),
                            'created_at': tweet.get('created_at', datetime.now().isoformat()),
                            'engagement': {
                                'likes': metrics.get('like_count', 0),
                                'retweets': metrics.get('retweet_count', 0),
                                'replies': metrics.get('reply_count', 0),
                                'quotes': metrics.get('quote_count', 0),
                                'total': sum(metrics.values()) if metrics else 0
                            },
                            'url': f"https://twitter.com/{user.get('username', 'twitter')}/status/{tweet['id']}",
                            'tweet_id': tweet['id'],
                            'language': tweet.get('lang', 'fr'),
                            'scraped_at': datetime.now().isoformat(),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'demo_data': False
                        }
                        
                        tweets.append(tweet_data)
                        
                elif response.status_code == 429:
                    logger.warning(f"⚠️ Limite API atteinte pour: {keyword}")
                    break
                else:
                    logger.error(f"❌ API erreur {response.status_code} pour: {keyword}")
                    
            except Exception as e:
                logger.error(f"❌ Erreur API pour {keyword}: {e}")
            
            time.sleep(self.rate_limit_delay)
        
        return tweets

    def _enrich_tweet(self, tweet: Dict[str, Any]) -> Dict[str, Any]:
        """Enrichir tweet avec analyse locale"""
        content = tweet.get('content', '').lower()
        
        # Score de pertinence départementale
        relevance_score = tweet.get('engagement', {}).get('total', 0)
        
        # Boost selon mentions politiques
        if any(term in content for term in ['guy losbar', 'losbar']):
            relevance_score += 200
            tweet['political_figure'] = 'Guy Losbar'
        elif any(term in content for term in ['cd971', 'conseil départemental']):
            relevance_score += 150
            tweet['political_figure'] = 'CD971'
        elif any(term in content for term in ['ary chalus', 'chalus']):
            relevance_score += 100
            tweet['political_figure'] = 'Ary Chalus'
        
        # Boost engagement local
        if any(term in content for term in ['guadeloupe', 'gwada', '971']):
            relevance_score += 50
        
        # Analyse sentiment basique
        tweet['sentiment'] = self._analyze_sentiment(content)
        tweet['relevance_score'] = relevance_score
        
        # Classification thématique
        tweet['topic_category'] = self._classify_topic(content)
        
        return tweet

    def _analyze_sentiment(self, text: str) -> str:
        """Analyse de sentiment simple"""
        text = text.lower()
        
        positive_words = ['bravo', 'félicitations', 'excellent', 'merci', 'soutien', 'bien']
        negative_words = ['scandale', 'honte', 'démission', 'inadmissible', 'catastrophe']
        
        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        return 'neutral'

    def _classify_topic(self, text: str) -> str:
        """Classification thématique"""
        text = text.lower()
        
        if any(term in text for term in ['budget', 'finances', 'économie']):
            return 'Budget/Économie'
        elif any(term in text for term in ['route', 'transport', 'infrastructure']):
            return 'Infrastructure'
        elif any(term in text for term in ['santé', 'hôpital', 'médical']):
            return 'Santé'
        elif any(term in text for term in ['éducation', 'école', 'collège']):
            return 'Éducation'
        elif any(term in text for term in ['environnement', 'écologie', 'climat']):
            return 'Environnement'
        else:
            return 'Politique générale'

    def save_tweets_to_db(self, tweets: List[Dict[str, Any]]) -> int:
        """Sauvegarder tweets en MongoDB"""
        if not tweets:
            return 0
        
        saved_count = 0
        
        for tweet in tweets:
            try:
                # Éviter les doublons
                existing = self.collection.find_one({
                    '$or': [
                        {'tweet_id': tweet.get('tweet_id')},
                        {'url': tweet.get('url')}
                    ]
                })
                
                if not existing:
                    self.collection.insert_one(tweet)
                    saved_count += 1
                else:
                    # Mettre à jour l'engagement si plus récent
                    if tweet.get('engagement', {}).get('total', 0) > existing.get('engagement', {}).get('total', 0):
                        self.collection.update_one(
                            {'_id': existing['_id']},
                            {'$set': {'engagement': tweet.get('engagement')}}
                        )
                        
            except Exception as e:
                logger.error(f"❌ Erreur sauvegarde tweet: {e}")
        
        logger.info(f"💾 Tweets sauvegardés: {saved_count}/{len(tweets)}")
        return saved_count

    def get_twitter_stats(self) -> Dict[str, Any]:
        """Statistiques Twitter"""
        try:
            total_tweets = self.collection.count_documents({'platform': {'$regex': 'twitter'}})
            
            # Stats par source
            apify_count = self.collection.count_documents({'platform': 'twitter_apify'})
            api_count = self.collection.count_documents({'platform': 'twitter_api'})
            
            # Top tweets par engagement
            top_tweets = list(self.collection.find(
                {'platform': {'$regex': 'twitter'}},
                {'content': 1, 'author': 1, 'engagement.total': 1}
            ).sort('engagement.total', -1).limit(5))
            
            # Stats politiques
            guy_losbar_mentions = self.collection.count_documents({
                'platform': {'$regex': 'twitter'},
                'political_figure': 'Guy Losbar'
            })
            
            return {
                'total_tweets': total_tweets,
                'sources': {
                    'apify': apify_count,
                    'api': api_count
                },
                'guy_losbar_mentions': guy_losbar_mentions,
                'top_tweets': top_tweets,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur stats Twitter: {e}")
            return {'error': str(e)}

# Instance globale
twitter_service = TwitterService()

def run_twitter_scraping(keywords: List[str] = None) -> Dict[str, Any]:
    """Fonction principale de scraping Twitter"""
    try:
        tweets = twitter_service.scrape_twitter_posts(keywords)
        saved = twitter_service.save_tweets_to_db(tweets)
        
        return {
            'success': True,
            'tweets_found': len(tweets),
            'tweets_saved': saved,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur scraping Twitter: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

if __name__ == "__main__":
    # Test du service
    print("🐦 Test service Twitter...")
    result = run_twitter_scraping()
    print(f"Résultat: {result}")
