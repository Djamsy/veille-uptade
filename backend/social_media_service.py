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
import feedparser
from urllib.parse import quote_plus

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SocialMediaScraper:
    def __init__(self):
        self.noapi_mode = os.environ.get('SOCIAL_NOAPI_MODE', 'true').lower() == 'true'

        self.nitter_instances = [
            "https://nitter.net",
            "https://nitter.fdn.fr",
            "https://nitter.privacy.com.de",
            "https://nitter.poast.org",
            "https://nitter.cz",
        ]

        # Flux Youtube publics (ajoute tes chaînes)
        self.youtube_feeds = [
            # "https://www.youtube.com/feeds/videos.xml?channel_id=UCxxxxxxxxxxxx",
        ]

        # Flux RSS locaux (presse / institutions)
        self.rss_sources = [
            "https://la1ere.francetvinfo.fr/guadeloupe/rss",
            "https://www.franceantilles.fr/rss",
        ]
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.social_collection = self.db.social_media_posts
            self.ensure_indexes()
            logger.info("✅ Connexion MongoDB réussie pour réseaux sociaux")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration par défaut - Focus Conseil Départemental et Guy Losbar
        self.keywords_guadeloupe = [
            "Conseil Départemental Guadeloupe", "CD971", "Département Guadeloupe",
            "Guy Losbar", "Losbar", "Président conseil départemental",
            "Collectivité Guadeloupe", "Basse-Terre politique", "CD Guadeloupe"
        ]
        
        # Mots-clés secondaires pour contexte
        self.keywords_context = [
            "Guadeloupe politique", "Assemblée départementale", "Budget départemental",
            "Routes Guadeloupe", "Collèges Guadeloupe", "Social Guadeloupe",
            "Aide sociale 971", "Transport scolaire Guadeloupe"
        ]
        
        self.max_posts_per_keyword = 20
        self.rate_limit_delay = 2  # secondes entre les requêtes

    def ensure_indexes(self):
        """Créer des index Mongo utiles (id unique, dates, texte)."""
        try:
            self.social_collection.create_index([("id", 1)], unique=True)
            self.social_collection.create_index([("date", 1)])
            self.social_collection.create_index([("platform", 1)])
            self.social_collection.create_index([("scraped_at", -1)])
            self.social_collection.create_index([("keyword_searched", 1)])
            # Index texte pour recherche plein-texte basique (si supporté)
            try:
                self.social_collection.create_index(
                    [("content", "text"), ("author", "text")],
                    name="content_text_idx"
                )
            except Exception as ie:
                logger.warning(f"Index texte non créé (peut ne pas être supporté) : {ie}")
        except Exception as e:
            logger.warning(f"Création d'index échouée: {e}")

    def search_posts(self, query: str, limit: int = 40) -> Dict[str, Any]:
        """Recherche simple dans les posts enregistrés (content, author, keyword_searched)."""
        q = (query or "").strip()
        if not q:
            return {"query": q, "total_results": 0, "posts": []}
        try:
            rx = re.compile(re.escape(q), re.IGNORECASE)
            mongo_filter = {
                "$or": [
                    {"content": rx},
                    {"author": rx},
                    {"keyword_searched": rx},
                ]
            }
            docs = list(
                self.social_collection.find(mongo_filter, {"_id": 0})
                .sort("scraped_at", -1)
                .limit(int(limit) if limit else 40)
            )
            return {"query": q, "total_results": len(docs), "posts": docs}
        except Exception as e:
            logger.error(f"❌ Erreur recherche posts '{q}': {e}")
            return {"query": q, "total_results": 0, "posts": [], "error": str(e)}

    def start_scrape(self, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """Démarrer un scraping immédiat et sauvegarder les posts en base."""
        results = self.scrape_all_keywords(keywords)
        posts = (
            results.get("twitter", [])
            + results.get("facebook", [])
            + results.get("instagram", [])
            + results.get("news", [])
            + results.get("youtube", [])
        )
        saved = self.save_posts_to_db(posts)
        results["saved"] = saved
        return results

    def install_dependencies(self):
        """Installer les dépendances nécessaires (désactivé en production)"""
        logger.warning("⚠️ Installation automatique des dépendances désactivée en production")
        logger.info("Les dépendances doivent être installées via requirements.txt")
        return
        
        # Code d'installation commenté pour éviter les problèmes en production
        # try:
        #     import subprocess
        #     import sys
        #     
        #     # Installer snscrape
        #     subprocess.check_call([sys.executable, "-m", "pip", "install", "snscrape"])
        #     logger.info("✅ snscrape installé")
        #     
        #     # Installer playwright pour Facebook/Instagram (désactivé)
        #     # subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        #     # subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        #     # logger.info("✅ Playwright installé")
        #     
        # except Exception as e:
        #     logger.error(f"❌ Erreur installation: {e}")

    def scrape_twitter_keyword(self, keyword: str, max_posts: int = 20) -> List[Dict[str, Any]]:
        """Scraper X/Twitter pour un mot-clé avec snscrape - Version améliorée"""
        try:
            import snscrape.modules.twitter as sntwitter
            
            posts = []
            
            # Construire une query plus spécifique pour la Guadeloupe
            if keyword.lower() in ['guy losbar', 'losbar']:
                search_query = f'"Guy Losbar" OR "Losbar" OR "président conseil départemental" lang:fr'
            elif keyword.lower() in ['conseil départemental', 'cd971']:
                search_query = f'"Conseil Départemental" OR "CD971" OR "département guadeloupe" lang:fr'
            else:
                search_query = f'{keyword} (guadeloupe OR gwada OR 971 OR antilles) lang:fr'
            
            logger.info(f"🔍 Recherche Twitter: {search_query}")
            
            # Limiter aux tweets des 30 derniers jours pour plus de résultats
            since_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            search_query += f' since:{since_date}'
            
            tweet_count = 0
            for tweet in sntwitter.TwitterSearchScraper(search_query).get_items():
                if tweet_count >= max_posts:
                    break
                
                # Filtrer les tweets avec un minimum d'engagement ou de contenu
                if len(tweet.rawContent) < 20:  # Tweets trop courts
                    continue
                
                # Prioriser les tweets avec engagement
                total_engagement = tweet.replyCount + tweet.retweetCount + tweet.likeCount
                
                # Détecter les entités pertinentes dans le contenu
                content_lower = tweet.rawContent.lower()
                is_relevant = any(entity in content_lower for entity in [
                    'guy losbar', 'losbar', 'conseil départemental', 'cd971',
                    'département guadeloupe', 'guadeloupe', 'gwada'
                ])
                
                if not is_relevant:
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
                        'total': total_engagement
                    },
                    'url': tweet.url,
                    'scraped_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'is_reply': tweet.inReplyToTweetId is not None,
                    'language': tweet.lang or 'fr',
                    'demo_data': False,  # Explicitement marquer comme vraies données
                    'relevance_score': total_engagement + (50 if 'guy losbar' in content_lower else 0)
                }
                
                # Détecter l'entité politique mentionnée
                if any(name in content_lower for name in ['guy losbar', 'losbar']):
                    post_data['political_figure'] = 'Guy Losbar'
                elif 'ary chalus' in content_lower:
                    post_data['political_figure'] = 'Ary Chalus'
                
                posts.append(post_data)
                tweet_count += 1
                
                # Respecter les limites
                time.sleep(self.rate_limit_delay / 2)  # Réduire le délai
            
            # Trier par pertinence et engagement
            posts.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            
            logger.info(f"✅ Twitter {keyword}: {len(posts)} posts récupérés (réels)")
            return posts
            
        except ImportError:
            logger.error("❌ snscrape non installé. Lancez: pip install snscrape")
            return []
        except Exception as e:
            logger.error(f"❌ Erreur scraping Twitter {keyword}: {e}")
            return []

    async def scrape_facebook_keyword(self, keyword: str, max_posts: int = 15) -> List[Dict[str, Any]]:
        """Scraper Facebook pour posts publics avec Playwright (désactivé en production)"""
        try:
            # Playwright désactivé en production pour réduire les dépendances
            logger.warning("⚠️ Facebook scraping désactivé en production - utilisez les flux RSS officiels")
            return []
            
            # Code commenté pour éviter les erreurs de dépendances
            # from playwright.async_api import async_playwright
            # 
            # posts = []
            # 
            # async with async_playwright() as p:
            #     # Lancer navigateur en mode headless
            #     browser = await p.chromium.launch(headless=True)
            #     context = await browser.new_context(
            #         user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            #     )
            #     page = await context.new_page()
            #     
            #     # Aller sur Facebook (sans connexion)
            #     search_url = f"https://www.facebook.com/public?query={keyword}"
            #     
            #     try:
            #         await page.goto(search_url, wait_until='networkidle')
            #         await page.wait_for_timeout(3000)  # Attendre le chargement
            #         
            #         # Récupérer les posts publics visibles
            #         posts_elements = await page.query_selector_all('[data-pagelet^="FeedUnit"]')
            #         
            #         for i, element in enumerate(posts_elements[:max_posts]):
            #             try:
            #                 # Extraire le texte du post
            #                 text_elem = await element.query_selector('[data-ad-preview="message"]')
            #                 if not text_elem:
            #                     text_elem = await element.query_selector('[data-testid="post_message"]')
            #                 
            #                 content = await text_elem.inner_text() if text_elem else ""
            #                 
            #                 if not content or len(content.strip()) < 10:
            #                     continue
            #                 
            #                 # Extraire l'auteur si possible
            #                 author_elem = await element.query_selector('strong a')
            #                 author = await author_elem.inner_text() if author_elem else "Utilisateur Facebook"
            #                 
            #                 # Extraire la date approximative
            #                 time_elem = await element.query_selector('abbr')
            #                 time_str = await time_elem.get_attribute('title') if time_elem else ""
            #                 
            #                 post_data = {
            #                     'id': f'facebook_{hash(content + author)}',
            #                     'platform': 'facebook',
            #                     'keyword_searched': keyword,
            #                     'content': content.strip(),
            #                     'author': author,
            #                     'author_followers': 0,  # Non accessible sans API
            #                     'created_at': time_str or datetime.now().isoformat(),
            #                     'engagement': {
            #                         'likes': 0,  # Non accessible facilement
            #                         'comments': 0,
            #                         'shares': 0,
            #                         'total': 0
            #                     },
            #                     'url': search_url,  # URL de recherche
            #                     'scraped_at': datetime.now().isoformat(),
            #                     'date': datetime.now().strftime('%Y-%m-%d'),
            #                     'is_reply': False,
            #                     'language': 'fr'
            #                 }
            #                 
            #                 posts.append(post_data)
            #                 
            #             except Exception as e:
            #                 logger.warning(f"Erreur extraction post Facebook: {e}")
            #                 continue
            #         
            #     except Exception as e:
            #         logger.warning(f"Erreur navigation Facebook: {e}")
            #     
            #     await browser.close()
            # 
            # logger.info(f"✅ Facebook {keyword}: {len(posts)} posts récupérés")
            # return posts
            
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
        """Scraper les réseaux sociaux pour récupérer de vrais commentaires - SANS données de démonstration"""
        if not keywords:
            keywords = self.keywords_guadeloupe[:3]

        results = {
            'twitter': [],
            'facebook': [],
            'instagram': [],
            'news': [],
            'youtube': [],
            'total_posts': 0,
            'keywords_searched': keywords,
            'scraped_at': datetime.now().isoformat(),
            'demo_mode': False,
            'note': 'Scraping réel avec fallbacks sans API (Nitter/Flux RSS/YouTube)'
        }

        logger.info(f"🚀 Scraping pour {len(keywords)} mots-clés (noapi_mode={self.noapi_mode})")

        for keyword in keywords:
            try:
                twitter_posts = self.scrape_twitter_keyword(keyword, self.max_posts_per_keyword)
                results['twitter'].extend(twitter_posts)
                logger.info(f"Twitter {keyword}: {len(twitter_posts)} posts")

                # Fallback Nitter si bloqué ou noapi_mode activé
                if self.noapi_mode or len(twitter_posts) == 0:
                    n_posts = self._try_nitter_search(keyword, max_items=20)
                    if n_posts:
                        logger.info(f"Nitter fallback {keyword}: +{len(n_posts)} posts")
                        results['twitter'].extend(n_posts)

                # News (Google News RSS) + sources locales
                news_from_google = self.google_news_rss(keyword, limit=15)
                results['news'].extend(news_from_google)
                for rss in self.rss_sources:
                    results['news'].extend(self.fetch_rss_feed(rss, platform_tag="news", keyword=keyword, limit=10))

                # Facebook/Instagram (limités)
                try:
                    facebook_posts = asyncio.run(self.scrape_facebook_keyword(keyword, 10))
                    results['facebook'].extend(facebook_posts)
                except Exception as fb_error:
                    logger.warning(f"Facebook scraping échoué pour {keyword}: {fb_error}")

                try:
                    instagram_posts = self.scrape_instagram_basic(keyword, 5)
                    results['instagram'].extend(instagram_posts)
                except Exception as ig_error:
                    logger.warning(f"Instagram scraping échoué pour {keyword}: {ig_error}")

                time.sleep(self.rate_limit_delay)

            except Exception as e:
                logger.error(f"Erreur scraping pour {keyword}: {e}")
                continue

        # YouTube (global)
        try:
            results['youtube'] = self.scrape_youtube_basic()
        except Exception as yerr:
            logger.warning(f"YouTube feeds erreur: {yerr}")
            results['youtube'] = []

        results['total_posts'] = sum(len(results[k]) for k in ['twitter','facebook','instagram','news','youtube'])

        if results['total_posts'] == 0:
            results['note'] = 'Aucun post trouvé — X/Twitter peut bloquer; RSS/Nitter/YouTube ajoutés en fallback.'
            logger.warning("⚠️ Aucun post récupéré. Vérifier les miroirs Nitter et les flux RSS.")

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

    def clean_demo_data_from_db(self):
        """Nettoyer les anciennes données de démonstration de la base"""
        try:
            # Supprimer tous les posts marqués comme demo_data
            result = self.social_collection.delete_many({'demo_data': True})
            logger.info(f"🧹 {result.deleted_count} posts de démonstration supprimés")
            return result.deleted_count
        except Exception as e:
            logger.error(f"❌ Erreur nettoyage données démo: {e}")
            return 0

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
    def _normalize_post(self, *, pid, platform, keyword, content, author, url, created_at=None, extra=None):
        data = {
            "id": pid,
            "platform": platform,
            "keyword_searched": keyword,
            "content": (content or "").strip(),
            "author": author or "",
            "author_followers": 0,
            "created_at": created_at or datetime.now().isoformat(),
            "engagement": {"likes": 0, "retweets": 0, "replies": 0, "comments": 0, "shares": 0, "total": 0},
            "url": url,
            "scraped_at": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "is_reply": False,
            "language": "fr",
            "demo_data": False,
        }
        if extra:
            data.update(extra)
        return data

    def fetch_rss_feed(self, url, platform_tag="news", keyword=None, limit=20):
        items = []
        feed = feedparser.parse(url)
        if getattr(feed, "entries", None):
            for e in feed.entries[:limit]:
                link = getattr(e, "link", "")
                title = getattr(e, "title", "")
                summary = getattr(e, "summary", "")
                published = getattr(e, "published", datetime.now().isoformat())
                pid = f"{platform_tag}_{abs(hash((link or title) + (keyword or platform_tag)))}"
                content = f"{title}\n{summary}".strip()
                items.append(self._normalize_post(
                    pid=pid, platform=platform_tag, keyword=keyword or platform_tag,
                    content=content, author="", url=link or url, created_at=published
                ))
        return items

    def google_news_rss(self, keyword, limit=20):
        q = quote_plus(keyword)
        url = f"https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"
        return self.fetch_rss_feed(url, platform_tag="news", keyword=keyword, limit=limit)

    def _try_nitter_search(self, keyword, max_items=20):
        posts = []
        query = f'{keyword} (guadeloupe OR gwada OR 971 OR antilles)'
        q = quote_plus(query)
        for base in self.nitter_instances:
            url = f"{base}/search/rss?f=tweets&amp;q={q}"
            feed = feedparser.parse(url)
            entries = getattr(feed, "entries", None)
            if not entries:
                continue
            for entry in entries[:max_items]:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "")
                author = getattr(entry, "author", "nitter")
                published = getattr(entry, "published", datetime.now().isoformat())
                content = f"{title}\n{summary}".strip()
                pid = f"nitter_{abs(hash(link or content))}"
                posts.append(self._normalize_post(
                    pid=pid, platform="twitter", keyword=keyword,
                    content=content, author=author, url=link or url, created_at=published,
                    extra={"source": base}
                ))
            if posts:
                break
        return posts

    def scrape_youtube_basic(self, limit_per_feed=8):
        all_items = []
        for feed_url in self.youtube_feeds:
            all_items.extend(self.fetch_rss_feed(feed_url, platform_tag="youtube", keyword="youtube", limit=limit_per_feed))
        return all_items