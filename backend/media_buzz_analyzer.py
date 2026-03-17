# backend/smart_media_buzz_service.py
"""
Service de bruit médiatique intelligent avec recherche en cascade
1. Recherche Google pour détecter le buzz général
2. Si buzz détecté → recherche RS ciblée via Apify
3. Extraction des commentaires pour analyse sentiment local
"""

import os
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SmartMediaBuzzService:
    def __init__(self):
        # MongoDB
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        try:
            if mongo_url.startswith("mongodb+srv"):
                self.client = MongoClient(mongo_url, tlsCAFile=certifi.where())
            else:
                self.client = MongoClient(mongo_url)
            
            self.db = self.client.veille_media
            self.articles_collection = self.db.scraped_articles
            self.transcriptions_collection = self.db.transcriptions
            self.social_collection = self.db.social_media_posts
            self.buzz_cache = self.db.buzz_analysis_cache  # Cache des recherches
            
            logger.info("Smart Media Buzz Service initialisé")
        except Exception as e:
            logger.error(f"Erreur MongoDB Smart Buzz: {e}")
            self.db = None
        
        # Configuration Google Search
        self.google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        self.google_cse_id = os.environ.get("GOOGLE_CSE_ID", "")
        
        # Configuration Apify
        self.apify_token = os.environ.get("APIFY_API_TOKEN", "")
        
        # Seuils de déclenchement
        self.google_buzz_threshold = 5  # Minimum 5 résultats Google pour déclencher RS
        self.cache_duration_hours = 6   # Cache pendant 6h
        
    def analyze_affair_buzz_smart(self, affair_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyse intelligente du bruit médiatique en cascade :
        1. Vérifier cache
        2. Recherche Google News avec titre d'affaire
        3. Si buzz → recherche RS + commentaires
        4. Calcul score composite
        """
        # Prioriser le titre d'affaire sur l'entité
        affair_title = affair_data.get('affaire_titre', '')
        primary_entity = affair_data.get('primary_entity', '')
        affair_id = affair_data.get('affair_id', '')
        
        # Construire la requête optimale
        search_query = affair_title if affair_title else primary_entity
        if not search_query:
            return {"buzz_level": "minimal", "buzz_score": 0, "error": "Pas de titre ou entité"}
        
        logger.info(f"Analyse smart pour affaire: '{search_query}'")
        
        # 1. Vérifier le cache (basé sur le titre ou l'entité)
        cache_key = f"{search_query}_{datetime.now().strftime('%Y-%m-%d')}"
        cached_result = self._get_cached_analysis(cache_key)
        if cached_result:
            logger.info(f"Cache hit pour '{search_query}'")
            return cached_result
        
        # 2. Phase 1: Recherche Google News avec titre optimisé
        google_buzz = self._analyze_google_news_buzz(search_query, primary_entity)
        logger.info(f"Google buzz pour '{search_query}': {google_buzz['result_count']} résultats")
        
        # 3. Phase 2: Si buzz Google suffisant → recherche RS ciblée
        social_buzz = {"social_posts": [], "comments": [], "social_score": 0}
        if google_buzz['result_count'] >= self.google_buzz_threshold:
            logger.info(f"Seuil atteint ({google_buzz['result_count']} >= {self.google_buzz_threshold}), déclenchement recherche RS")
            # Utiliser le titre pour la recherche RS aussi
            social_buzz = self._search_social_media_targeted(search_query, primary_entity)
        else:
            logger.info(f"Seuil non atteint, recherche RS skippée")
        
        # 4. Données locales (basées sur l'entité pour la compatibilité)
        local_data = self._get_local_media_data(primary_entity)
        
        # 5. Calcul du score composite intelligent
        buzz_analysis = self._calculate_smart_buzz_score(
            google_buzz, social_buzz, local_data, search_query
        )
        
        # 6. Mise en cache
        self._cache_analysis(cache_key, buzz_analysis)
        
        return buzz_analysis
    
    def _analyze_google_news_buzz(self, search_query: str, entity: str = "") -> Dict[str, Any]:
        """Phase 1: Analyser le buzz sur Google News avec titre d'affaire"""
        if not self.google_api_key or not self.google_cse_id:
            logger.warning("Clés Google Search manquantes, simulation du buzz")
            return {
                "result_count": 3,
                "recent_articles": [],
                "trending_score": 2.5,
                "source": "simulated"
            }
        
        try:
            # Requête optimisée avec titre d'affaire + géolocalisation
            google_query = f'"{search_query}" Guadeloupe'
            
            # Si le titre est trop court, ajouter l'entité pour plus de précision
            if len(search_query) < 20 and entity:
                google_query = f'"{search_query}" "{entity}" Guadeloupe'
            
            params = {
                "key": self.google_api_key,
                "cx": self.google_cse_id,
                "q": google_query,
                "dateRestrict": "d7",  # 7 derniers jours
                "num": 10,
                "sort": "date",
                "siteSearch": "site:franceantilles.fr OR site:rci.fm OR site:la1ere.francetvinfo.fr"  # Sources locales prioritaires
            }
            
            logger.info(f"Recherche Google: '{google_query}'")
            
            response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("items", [])
            result_count = len(items)
            
            # Analyser la qualité et récence des résultats
            trending_score = self._calculate_google_trending_score(items, search_query)
            
            logger.info(f"Google: {result_count} résultats pour '{search_query}'")
            
            return {
                "result_count": result_count,
                "recent_articles": items[:5],
                "trending_score": trending_score,
                "search_query": google_query,
                "source": "google_search_api"
            }
            
        except Exception as e:
            logger.error(f"Erreur Google Search pour '{entity}': {e}")
            return {
                "result_count": 0,
                "recent_articles": [],
                "trending_score": 0,
                "error": str(e)
            }
    
    def _search_social_media_targeted(self, search_query: str, entity: str = "") -> Dict[str, Any]:
        """Phase 2: Recherche ciblée RS via Apify avec titre d'affaire"""
        if not self.apify_token:
            logger.warning("Token Apify manquant, recherche RS locale")
            return self._search_social_media_local(search_query)
        
        try:
            # Construire les termes de recherche optimaux
            search_terms = [search_query]
            if entity and entity not in search_query:
                search_terms.append(f"{entity} {search_query}")
            
            # Recherche Facebook avec commentaires
            facebook_data = self._apify_facebook_search_with_comments(search_terms)
            
            # Recherche Instagram 
            instagram_data = self._apify_instagram_search(search_terms)
            
            # Recherche Twitter
            twitter_data = self._apify_twitter_search(search_terms)
            
            # Combiner les résultats
            social_posts = facebook_data + instagram_data + twitter_data
            
            # Extraire tous les commentaires
            all_comments = []
            for post in social_posts:
                comments = post.get('comments', [])
                all_comments.extend(comments)
            
            # Calculer score social
            social_score = self._calculate_social_score(social_posts, all_comments)
            
            # Sauvegarder en DB
            self._save_social_data(social_posts, search_query)
            
            return {
                "social_posts": social_posts,
                "comments": all_comments,
                "social_score": social_score,
                "platforms": ["facebook", "instagram", "twitter"],
                "search_terms": search_terms,
                "source": "apify"
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche RS Apify pour '{entity}': {e}")
            return self._search_social_media_local(entity)
    
    def _apify_facebook_search_with_comments(self, entity: str) -> List[Dict[str, Any]]:
        """Recherche Facebook avec commentaires via Apify"""
        try:
            input_data = {
                "searchTerms": [f'"{entity}" Guadeloupe'],
                "maxPostsPerPage": 10,
                "includeComments": True,  # IMPORTANT: inclure les commentaires
                "maxCommentsPerPost": 20,
                "onlyInLanguage": "fr",
                "location": "Guadeloupe, France"
            }
            
            result = self._run_apify_actor("apify/facebook-posts-scraper", input_data)
            
            posts = []
            if result and result.get("items"):
                for item in result["items"]:
                    post = {
                        "id": f"facebook_{item.get('postId', hash(item.get('text', '')))}",
                        "platform": "facebook",
                        "content": item.get("text", ""),
                        "author": item.get("authorName", ""),
                        "created_at": item.get("createdAt", datetime.now().isoformat()),
                        "url": item.get("url", ""),
                        "engagement": {
                            "likes": item.get("likesCount", 0),
                            "shares": item.get("sharesCount", 0),
                            "comments_count": item.get("commentsCount", 0)
                        },
                        "comments": item.get("comments", [])[:20],  # Max 20 commentaires
                        "location": item.get("location", ""),
                        "source_method": "apify_facebook"
                    }
                    posts.append(post)
            
            return posts
            
        except Exception as e:
            logger.error(f"Erreur Facebook Apify: {e}")
            return []
    
    def _apify_instagram_search(self, entity: str) -> List[Dict[str, Any]]:
        """Recherche Instagram via Apify"""
        try:
            # Utiliser les hashtags Guadeloupe + recherche par mots-clés
            hashtags = ["#guadeloupe", "#gwada"]
            
            posts = []
            for hashtag in hashtags:
                input_data = {
                    "hashtags": [hashtag],
                    "searchTerms": [entity],
                    "resultsPerPage": 5,
                    "resultsType": "posts"
                }
                
                result = self._run_apify_actor("apify/instagram-hashtag-scraper", input_data)
                
                if result and result.get("items"):
                    for item in result["items"]:
                        post = {
                            "id": f"instagram_{item.get('id', hash(item.get('caption', '')))}",
                            "platform": "instagram",
                            "content": item.get("caption", ""),
                            "author": item.get("ownerUsername", ""),
                            "created_at": item.get("timestamp", datetime.now().isoformat()),
                            "url": item.get("url", ""),
                            "engagement": {
                                "likes": item.get("likesCount", 0),
                                "comments_count": item.get("commentsCount", 0)
                            },
                            "hashtag_searched": hashtag,
                            "source_method": "apify_instagram"
                        }
                        posts.append(post)
                
                time.sleep(1)  # Rate limiting
            
            return posts
            
        except Exception as e:
            logger.error(f"Erreur Instagram Apify: {e}")
            return []
    
    def _apify_twitter_search(self, entity: str) -> List[Dict[str, Any]]:
        """Recherche Twitter via Apify"""
        try:
            search_query = f'"{entity}" (Guadeloupe OR Gwada OR 971)'
            
            input_data = {
                "searchTerms": [search_query],
                "maxTweetsPerQuery": 15,
                "language": "fr",
                "onlyVerified": False
            }
            
            result = self._run_apify_actor("apify/twitter-scraper", input_data)
            
            posts = []
            if result and result.get("items"):
                for item in result["items"]:
                    post = {
                        "id": f"twitter_{item.get('id', hash(item.get('text', '')))}",
                        "platform": "twitter",
                        "content": item.get("text", ""),
                        "author": item.get("author", {}).get("userName", ""),
                        "created_at": item.get("createdAt", datetime.now().isoformat()),
                        "url": item.get("url", ""),
                        "engagement": {
                            "likes": item.get("likeCount", 0),
                            "retweets": item.get("retweetCount", 0),
                            "replies": item.get("replyCount", 0)
                        },
                        "source_method": "apify_twitter"
                    }
                    posts.append(post)
            
            return posts
            
        except Exception as e:
            logger.error(f"Erreur Twitter Apify: {e}")
            return []
    
    def _run_apify_actor(self, actor_id: str, input_data: Dict) -> Optional[Dict]:
        """Exécute un acteur Apify (simplifié)"""
        try:
            url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
            headers = {"Authorization": f"Bearer {self.apify_token}"}
            
            response = requests.post(url, json=input_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            run_data = response.json()["data"]
            run_id = run_data["id"]
            
            # Attendre la fin (simplifié)
            for _ in range(30):  # Max 5 minutes
                status_url = f"https://api.apify.com/v2/actor-runs/{run_id}"
                status_response = requests.get(status_url, headers=headers, timeout=10)
                status = status_response.json()["data"]["status"]
                
                if status == "SUCCEEDED":
                    dataset_id = status_response.json()["data"]["defaultDatasetId"]
                    dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
                    data_response = requests.get(dataset_url, headers=headers, timeout=30)
                    return {"items": data_response.json()}
                elif status in ["FAILED", "ABORTED"]:
                    return None
                
                time.sleep(10)
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur Apify actor {actor_id}: {e}")
            return None
    
    def _search_social_media_local(self, entity: str) -> Dict[str, Any]:
        """Fallback: recherche dans les données locales existantes"""
        if not self.db:
            return {"social_posts": [], "comments": [], "social_score": 0}
        
        try:
            # Rechercher dans les posts existants
            posts = list(self.social_collection.find({
                "$text": {"$search": entity}
            }).limit(20))
            
            social_score = len(posts) * 2  # Score basique
            
            return {
                "social_posts": posts,
                "comments": [],
                "social_score": social_score,
                "source": "local_db"
            }
            
        except Exception as e:
            logger.error(f"Erreur recherche locale: {e}")
            return {"social_posts": [], "comments": [], "social_score": 0}
    
    def _get_local_media_data(self, entity: str) -> Dict[str, Any]:
        """Récupère les données locales (articles + transcriptions)"""
        if not self.db:
            return {"articles": [], "transcriptions": []}
        
        try:
            # Articles
            articles = list(self.articles_collection.find({
                "$or": [
                    {"title": {"$regex": entity, "$options": "i"}},
                    {"content": {"$regex": entity, "$options": "i"}}
                ]
            }).limit(10))
            
            # Transcriptions
            transcriptions = list(self.transcriptions_collection.find({
                "$or": [
                    {"gpt_analysis": {"$regex": entity, "$options": "i"}},
                    {"ai_summary": {"$regex": entity, "$options": "i"}}
                ]
            }).limit(10))
            
            return {
                "articles": articles,
                "transcriptions": transcriptions
            }
            
        except Exception as e:
            logger.error(f"Erreur données locales: {e}")
            return {"articles": [], "transcriptions": []}
    
    def _calculate_smart_buzz_score(self, google_buzz: Dict, social_buzz: Dict, local_data: Dict, entity: str) -> Dict[str, Any]:
        """Calcule le score de bruit intelligent"""
        
        # Composantes du score
        google_score = min(google_buzz.get('result_count', 0) * 5, 30)  # Max 30 points
        social_score = min(social_buzz.get('social_score', 0), 40)      # Max 40 points  
        local_score = min((len(local_data.get('articles', [])) + len(local_data.get('transcriptions', []))) * 3, 30)  # Max 30 points
        
        # Score composite
        total_score = google_score + social_score + local_score
        
        # Niveau de buzz
        if total_score >= 80:
            buzz_level = "viral"
        elif total_score >= 60:
            buzz_level = "élevé"
        elif total_score >= 40:
            buzz_level = "modéré"
        elif total_score >= 20:
            buzz_level = "faible"
        else:
            buzz_level = "minimal"
        
        # Analyse des commentaires pour le sentiment
        comments_analysis = self._analyze_comments_sentiment(social_buzz.get('comments', []))
        
        return {
            "entity": entity,
            "buzz_score": total_score,
            "buzz_level": buzz_level,
            "components": {
                "google_score": google_score,
                "social_score": social_score, 
                "local_score": local_score
            },
            "details": {
                "google_results": google_buzz.get('result_count', 0),
                "social_posts": len(social_buzz.get('social_posts', [])),
                "comments": len(social_buzz.get('comments', [])),
                "local_articles": len(local_data.get('articles', [])),
                "local_transcriptions": len(local_data.get('transcriptions', []))
            },
            "comments_sentiment": comments_analysis,
            "interpretation": self._generate_smart_interpretation(total_score, buzz_level, social_buzz, comments_analysis),
            "calculated_at": datetime.now().isoformat(),
            "search_strategy": "smart_cascade"
        }
    
    def _analyze_comments_sentiment(self, comments: List[Dict]) -> Dict[str, Any]:
        """Analyse le sentiment des commentaires"""
        if not comments:
            return {"dominant": "neutral", "distribution": {}, "sample_comments": []}
        
        # Analyse basique par mots-clés
        positive_words = ["bien", "bravo", "excellent", "parfait", "réussi", "bon"]
        negative_words = ["scandale", "honte", "grave", "catastrophe", "nul", "inadmissible"]
        
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        
        for comment in comments:
            text = comment.get('text', '').lower()
            
            pos_count = sum(1 for word in positive_words if word in text)
            neg_count = sum(1 for word in negative_words if word in text)
            
            if pos_count > neg_count:
                sentiment_counts["positive"] += 1
            elif neg_count > pos_count:
                sentiment_counts["negative"] += 1
            else:
                sentiment_counts["neutral"] += 1
        
        total = len(comments)
        dominant = max(sentiment_counts, key=sentiment_counts.get)
        
        return {
            "dominant": dominant,
            "distribution": {k: round(v/total*100, 1) for k, v in sentiment_counts.items()},
            "sample_comments": comments[:5],  # Échantillon pour analyse
            "total_analyzed": total
        }
    
    def _generate_smart_interpretation(self, score: float, level: str, social_buzz: Dict, comments_sentiment: Dict) -> str:
        """Génère une interprétation intelligente"""
        base_interpretations = {
            "viral": "Buzz viral exceptionnel détecté",
            "élevé": "Forte couverture médiatique avec activité RS significative", 
            "modéré": "Couverture médiatique notable avec présence RS",
            "faible": "Couverture médiatique limitée, faible écho RS",
            "minimal": "Impact médiatique minimal"
        }
        
        base = base_interpretations.get(level, "Impact indéterminé")
        
        # Enrichir avec info RS
        social_posts_count = len(social_buzz.get('social_posts', []))
        comments_count = len(social_buzz.get('comments', []))
        
        if social_posts_count > 20:
            base += f" avec forte activité RS ({social_posts_count} posts"
        elif social_posts_count > 5:
            base += f" avec activité RS notable ({social_posts_count} posts"
        elif social_posts_count > 0:
            base += f" avec présence RS limitée ({social_posts_count} posts"
        
        # Ajouter info commentaires
        if comments_count > 50:
            base += f", {comments_count} commentaires)"
        elif comments_count > 10:
            base += f", {comments_count} commentaires)"
        elif comments_count > 0:
            base += f", {comments_count} commentaires)"
        else:
            base += ")"
        
        # Sentiment des commentaires
        dominant_sentiment = comments_sentiment.get('dominant', 'neutral')
        if dominant_sentiment != 'neutral' and comments_count > 0:
            base += f" - Réactions du public: {dominant_sentiment}"
        
        return base
    
    def _calculate_social_score(self, posts: List[Dict], comments: List[Dict]) -> float:
        """Calcule le score social basé sur posts + commentaires"""
        if not posts:
            return 0
        
        score = 0
        
        # Score basé sur les posts
        for post in posts:
            engagement = post.get('engagement', {})
            likes = engagement.get('likes', 0)
            shares = engagement.get('shares', 0) or engagement.get('retweets', 0)
            comments_count = engagement.get('comments_count', 0)
            
            post_score = (likes * 1) + (shares * 2) + (comments_count * 1.5)
            score += min(post_score, 100)  # Cap par post
        
        # Bonus pour les commentaires
        score += len(comments) * 0.5
        
        return min(score, 1000)  # Cap global
    
    def _calculate_google_trending_score(self, items: List[Dict]) -> float:
        """Calcule le score de tendance Google"""
        if not items:
            return 0
        
        score = len(items) * 2
        
        # Bonus pour sources fiables
        reliable_sources = ["francetvinfo", "franceantilles", "rci.fm", "guadeloupe.fr"]
        for item in items:
            link = item.get('link', '').lower()
            if any(source in link for source in reliable_sources):
                score += 3
        
        return min(score, 20)
    
    def _get_cached_analysis(self, entity: str) -> Optional[Dict]:
        """Récupère l'analyse en cache si récente"""
        if not self.db:
            return None
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=self.cache_duration_hours)
            cached = self.buzz_cache.find_one({
                "entity": entity,
                "calculated_at": {"$gte": cutoff_time.isoformat()}
            })
            
            if cached:
                cached.pop('_id', None)
                return cached
                
        except Exception:
            pass
        
        return None
    
    def _cache_analysis(self, entity: str, analysis: Dict):
        """Met en cache l'analyse"""
        if not self.db:
            return
        
        try:
            self.buzz_cache.update_one(
                {"entity": entity},
                {"$set": analysis},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Erreur cache: {e}")
    
    def _save_social_data(self, posts: List[Dict], entity: str):
        """Sauvegarde les données sociales"""
        if not self.db or not posts:
            return
        
        try:
            for post in posts:
                post['search_entity'] = entity
                post['scraped_at'] = datetime.now().isoformat()
                
                self.social_collection.update_one(
                    {"id": post["id"]},
                    {"$set": post},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Erreur sauvegarde social: {e}")

# Instance globale
smart_media_buzz = SmartMediaBuzzService()