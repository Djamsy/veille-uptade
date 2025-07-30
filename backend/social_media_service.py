"""
Service de récupération de contenus sur les réseaux sociaux
Utilise snscrape pour X/Twitter et Playwright pour Facebook/Instagram (posts publics)
Sans API, respecte les limites légales
"""
import asyncio
import os
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
import json
from pymongo import MongoClient

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SocialMediaScraper:
    def __init__(self):
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.social_collection = self.db.social_media_posts
            logger.info("✅ Connexion MongoDB réussie pour réseaux sociaux")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration par défaut
        self.keywords_guadeloupe = [
            "Guadeloupe", "Pointe-à-Pitre", "Basse-Terre", "Marie-Galante",
            "Antilles", "Gwada", "971", "Archipel guadeloupéen",
            "Saint-François", "Le Gosier", "Sainte-Anne", "Deshaies"
        ]
        
        self.max_posts_per_keyword = 20
        self.rate_limit_delay = 2  # secondes entre les requêtes

    def install_dependencies(self):
        """Installer les dépendances nécessaires"""
        try:
            import subprocess
            import sys
            
            # Installer snscrape
            subprocess.check_call([sys.executable, "-m", "pip", "install", "snscrape"])
            logger.info("✅ snscrape installé")
            
            # Installer playwright pour Facebook/Instagram
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            logger.info("✅ Playwright installé")
            
        except Exception as e:
            logger.error(f"❌ Erreur installation: {e}")

    def scrape_twitter_keyword(self, keyword: str, max_posts: int = 20) -> List[Dict[str, Any]]:
        """Scraper X/Twitter pour un mot-clé avec snscrape"""
        try:
            import snscrape.modules.twitter as sntwitter
            
            posts = []
            search_query = f'{keyword} lang:fr OR lang:ht'  # Français ou créole haïtien
            
            logger.info(f"🔍 Recherche Twitter: {search_query}")
            
            # Limiter aux tweets des 7 derniers jours
            since_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            search_query += f' since:{since_date}'
            
            for i, tweet in enumerate(sntwitter.TwitterSearchScraper(search_query).get_items()):
                if i >= max_posts:
                    break
                
                # Filtrer les tweets avec engagement minimum
                if tweet.replyCount + tweet.retweetCount + tweet.likeCount < 1:
                    continue
                
                post_data = {
                    'id': f'twitter_{tweet.id}',
                    'platform': 'twitter',
                    'keyword_searched': keyword,
                    'content': tweet.rawContent,
                    'author': tweet.user.username,
                    'author_followers': tweet.user.followersCount,
                    'created_at': tweet.date.isoformat(),
                    'engagement': {
                        'likes': tweet.likeCount,
                        'retweets': tweet.retweetCount,
                        'replies': tweet.replyCount,
                        'total': tweet.likeCount + tweet.retweetCount + tweet.replyCount
                    },
                    'url': tweet.url,
                    'scraped_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'is_reply': tweet.inReplyToTweetId is not None,
                    'language': tweet.lang or 'fr'
                }
                
                posts.append(post_data)
                
                # Respecter les limites
                time.sleep(self.rate_limit_delay)
            
            logger.info(f"✅ Twitter {keyword}: {len(posts)} posts récupérés")
            return posts
            
        except ImportError:
            logger.error("❌ snscrape non installé. Lancez install_dependencies()")
            return []
        except Exception as e:
            logger.error(f"❌ Erreur scraping Twitter {keyword}: {e}")
            return []

    async def scrape_facebook_keyword(self, keyword: str, max_posts: int = 15) -> List[Dict[str, Any]]:
        """Scraper Facebook pour posts publics avec Playwright"""
        try:
            from playwright.async_api import async_playwright
            
            posts = []
            
            async with async_playwright() as p:
                # Lancer navigateur en mode headless
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()
                
                # Aller sur Facebook (sans connexion)
                search_url = f"https://www.facebook.com/public?query={keyword}"
                
                try:
                    await page.goto(search_url, wait_until='networkidle')
                    await page.wait_for_timeout(3000)  # Attendre le chargement
                    
                    # Récupérer les posts publics visibles
                    posts_elements = await page.query_selector_all('[data-pagelet^="FeedUnit"]')
                    
                    for i, element in enumerate(posts_elements[:max_posts]):
                        try:
                            # Extraire le texte du post
                            text_elem = await element.query_selector('[data-ad-preview="message"]')
                            if not text_elem:
                                text_elem = await element.query_selector('[data-testid="post_message"]')
                            
                            content = await text_elem.inner_text() if text_elem else ""
                            
                            if not content or len(content.strip()) < 10:
                                continue
                            
                            # Extraire l'auteur si possible
                            author_elem = await element.query_selector('strong a')
                            author = await author_elem.inner_text() if author_elem else "Utilisateur Facebook"
                            
                            # Extraire la date approximative
                            time_elem = await element.query_selector('abbr')
                            time_str = await time_elem.get_attribute('title') if time_elem else ""
                            
                            post_data = {
                                'id': f'facebook_{hash(content + author)}',
                                'platform': 'facebook',
                                'keyword_searched': keyword,
                                'content': content.strip(),
                                'author': author,
                                'author_followers': 0,  # Non accessible sans API
                                'created_at': time_str or datetime.now().isoformat(),
                                'engagement': {
                                    'likes': 0,  # Non accessible facilement
                                    'comments': 0,
                                    'shares': 0,
                                    'total': 0
                                },
                                'url': search_url,  # URL de recherche
                                'scraped_at': datetime.now().isoformat(),
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'is_reply': False,
                                'language': 'fr'
                            }
                            
                            posts.append(post_data)
                            
                        except Exception as e:
                            logger.warning(f"Erreur extraction post Facebook: {e}")
                            continue
                    
                except Exception as e:
                    logger.warning(f"Erreur navigation Facebook: {e}")
                
                await browser.close()
            
            logger.info(f"✅ Facebook {keyword}: {len(posts)} posts récupérés")
            return posts
            
        except ImportError:
            logger.error("❌ Playwright non installé. Lancez install_dependencies()")
            return []
        except Exception as e:
            logger.error(f"❌ Erreur scraping Facebook {keyword}: {e}")
            return []

    def scrape_instagram_basic(self, keyword: str, max_posts: int = 10) -> List[Dict[str, Any]]:
        """Scraper Instagram basique (hashtags publics)"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            posts = []
            
            # Recherche via hashtag Instagram (méthode limitée)
            hashtag = keyword.replace(' ', '').lower()
            url = f"https://www.instagram.com/explore/tags/{hashtag}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                # Cette méthode est très limitée car Instagram bloque le scraping
                # On peut seulement obtenir des informations basiques
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Rechercher des scripts JSON avec des données
                scripts = soup.find_all('script', type='application/ld+json')
                
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if 'name' in data:
                            post_data = {
                                'id': f'instagram_{hash(hashtag)}',
                                'platform': 'instagram',
                                'keyword_searched': keyword,
                                'content': f"Hashtag #{hashtag} sur Instagram",
                                'author': 'Instagram',
                                'author_followers': 0,
                                'created_at': datetime.now().isoformat(),
                                'engagement': {'likes': 0, 'comments': 0, 'total': 0},
                                'url': url,
                                'scraped_at': datetime.now().isoformat(),
                                'date': datetime.now().strftime('%Y-%m-%d'),
                                'is_reply': False,
                                'language': 'fr'
                            }
                            posts.append(post_data)
                            break
                    except:
                        continue
            
            logger.info(f"✅ Instagram {keyword}: {len(posts)} posts récupérés (limité)")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Erreur scraping Instagram {keyword}: {e}")
            return []

    def scrape_all_keywords(self, keywords: List[str] = None) -> Dict[str, List[Dict]]:
        """Scraper tous les réseaux pour tous les mots-clés"""
        if not keywords:
            keywords = self.keywords_guadeloupe[:3]  # Limiter pour éviter la surcharge
        
        results = {
            'twitter': [],
            'facebook': [],
            'instagram': [],
            'total_posts': 0,
            'keywords_searched': keywords,
            'scraped_at': datetime.now().isoformat()
        }
        
        logger.info(f"🚀 Début scraping pour {len(keywords)} mots-clés")
        
        for keyword in keywords:
            logger.info(f"🔍 Scraping pour: {keyword}")
            
            # Twitter/X
            twitter_posts = self.scrape_twitter_keyword(keyword, self.max_posts_per_keyword)
            results['twitter'].extend(twitter_posts)
            
            # Pause entre les plateformes
            time.sleep(self.rate_limit_delay)
            
            # Facebook (méthode async)
            try:
                facebook_posts = asyncio.run(self.scrape_facebook_keyword(keyword, self.max_posts_per_keyword))
                results['facebook'].extend(facebook_posts)
            except Exception as e:
                logger.warning(f"Facebook scraping failed for {keyword}: {e}")
            
            # Instagram (basique)
            instagram_posts = self.scrape_instagram_basic(keyword, 5)
            results['instagram'].extend(instagram_posts)
            
            # Pause entre les mots-clés
            time.sleep(self.rate_limit_delay * 2)
        
        # Calculer totaux
        results['total_posts'] = len(results['twitter']) + len(results['facebook']) + len(results['instagram'])
        
        logger.info(f"✅ Scraping terminé: {results['total_posts']} posts au total")
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
        """Obtenir les statistiques des posts"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Compter par plateforme
            twitter_count = self.social_collection.count_documents({'platform': 'twitter', 'date': today})
            facebook_count = self.social_collection.count_documents({'platform': 'facebook', 'date': today})
            instagram_count = self.social_collection.count_documents({'platform': 'instagram', 'date': today})
            
            # Top mots-clés
            pipeline = [
                {'$match': {'date': today}},
                {'$group': {'_id': '$keyword_searched', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 5}
            ]
            top_keywords = list(self.social_collection.aggregate(pipeline))
            
            return {
                'total_today': twitter_count + facebook_count + instagram_count,
                'by_platform': {
                    'twitter': twitter_count,
                    'facebook': facebook_count,
                    'instagram': instagram_count
                },
                'top_keywords': [
                    {'keyword': item['_id'], 'count': item['count']}
                    for item in top_keywords
                ],
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur stats: {e}")
            return {}

# Instance globale
social_scraper = SocialMediaScraper()

if __name__ == "__main__":
    # Test du scraper
    print("=== Test du scraper réseaux sociaux ===")
    
    # Installer les dépendances si nécessaire
    social_scraper.install_dependencies()
    
    # Test avec un mot-clé
    test_keywords = ["Guadeloupe"]
    results = social_scraper.scrape_all_keywords(test_keywords)
    
    print(f"Résultats: {results['total_posts']} posts")
    print(f"Twitter: {len(results['twitter'])} posts")
    print(f"Facebook: {len(results['facebook'])} posts")
    print(f"Instagram: {len(results['instagram'])} posts")
    
    # Sauvegarder en base
    all_posts = results['twitter'] + results['facebook'] + results['instagram']
    saved = social_scraper.save_posts_to_db(all_posts)
    print(f"Sauvegardés: {saved} posts")