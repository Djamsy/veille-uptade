# backend/apify_social_service.py
"""
Service d'intégration Apify pour scraping réseaux sociaux
Version économique - Budget $10/mois
Optimisé pour la veille Guadeloupe avec ciblage géographique précis
"""

import os
import logging
import requests
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
import certifi

logger = logging.getLogger(__name__)

class ApifySocialService:
    def __init__(self):
        # Configuration Apify
        self.apify_token = os.environ.get("APIFY_API_TOKEN", "")
        self.apify_base_url = "https://api.apify.com/v2"
        
        if not self.apify_token:
            logger.warning("APIFY_API_TOKEN non configuré - mode démo activé")
        
        # MongoDB
        self._init_mongo()
        
        # Mots-clés Guadeloupe optimisés pour économiser les requêtes
        self.keywords_guadeloupe = [
            "Guadeloupe OR Gwada OR 971",  # Requête combinée pour économiser
            "Guy Losbar OR CD971",        # Requête combinée
            "Conseil Départemental Guadeloupe"
        ]
        
        # Configuration économique des scrapers
        self.scrapers_config = {
            "facebook": {
                "actor_id": "encouraged_printer/facebook-posts-scraper-task",
                "max_posts": 30,  # Limité pour économiser
                "cost_per_1000": 0.25,
                "enabled": True
            },
            "instagram": {
                "actor_id": "encouraged_printer/instagram-scraper-task", 
                "max_posts": 20,  # Instagram moins prioritaire
                "cost_per_1000": 0.30,
                "enabled": True
            },
            "twitter": {
                "actor_id": "encouraged_printer/tweet-scraper-v2---x-twitter-scraper-task",
                "max_posts": 40,  # Twitter important pour l'info
                "cost_per_1000": 0.20,
                "enabled": True
            }
        }
        
        # Budget quotidien en opérations (~$0.30/jour = $10/mois)
        self.daily_operation_budget = 1200
        self.operation_counter = 0
        
    def _init_mongo(self):
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        try:
            if mongo_url.startswith("mongodb+srv"):
                self.client = MongoClient(mongo_url, tlsCAFile=certifi.where())
            else:
                self.client = MongoClient(mongo_url)
            
            self.db = self.client.veille_media
            self.social_collection = self.db.social_media_posts
            self.apify_runs_collection = self.db.apify_runs  # Track des exécutions
            
            logger.info("MongoDB connecté pour Apify service")
        except Exception as e:
            logger.error(f"Erreur MongoDB Apify: {e}")
            self.db = None

    def run_daily_scraping(self) -> Dict[str, Any]:
        """Lance le scraping quotidien avec budget optimisé"""
        if not self.apify_token:
            return {"error": "Token Apify manquant", "demo_mode": True}
        
        # Vérifier le budget quotidien
        today = datetime.now().strftime("%Y-%m-%d")
        if self._check_daily_budget_exceeded(today):
            return {
                "status": "budget_exceeded",
                "message": "Budget quotidien atteint",
                "operations_used": self.operation_counter
            }
        
        results = {
            "date": today,
            "scraped_data": {},
            "operations_used": 0,
            "estimated_cost": 0.0,
            "errors": []
        }
        
        try:
            # Facebook - Priorité 1
            if self.scrapers_config["facebook"]["enabled"]:
                fb_data = self._scrape_facebook_posts()
                results["scraped_data"]["facebook"] = fb_data
                results["operations_used"] += len(fb_data)
            
            # Twitter - Priorité 2  
            if self.scrapers_config["twitter"]["enabled"]:
                twitter_data = self._scrape_twitter_posts()
                results["scraped_data"]["twitter"] = twitter_data
                results["operations_used"] += len(twitter_data)
            
            # Instagram - Si budget restant
            remaining_budget = self.daily_operation_budget - results["operations_used"]
            if remaining_budget > 20 and self.scrapers_config["instagram"]["enabled"]:
                insta_data = self._scrape_instagram_posts()
                results["scraped_data"]["instagram"] = insta_data
                results["operations_used"] += len(insta_data)
            
            # Calcul coût estimé
            results["estimated_cost"] = self._calculate_cost(results["operations_used"])
            
            # Sauvegarder en DB
            self._save_to_database(results["scraped_data"])
            
            # Enregistrer l'exécution
            self._log_apify_run(results)
            
            logger.info(f"Scraping Apify terminé: {results['operations_used']} opérations, ${results['estimated_cost']:.3f}")
            
        except Exception as e:
            logger.error(f"Erreur scraping Apify: {e}")
            results["errors"].append(str(e))
        
        return results

    def _scrape_facebook_posts(self) -> List[Dict[str, Any]]:
        """Scraper Facebook avec recherche géographique"""
        posts = []
        
        for keyword in self.keywords_guadeloupe[:2]:  # Limiter à 2 requêtes
            try:
                input_data = {
                    "searchTerms": [keyword],
                    "location": "Guadeloupe, France",  # Ciblage géographique
                    "maxPostsPerPage": self.scrapers_config["facebook"]["max_posts"],
                    "maxPagesPerQuery": 1,  # Une seule page pour économiser
                    "includeComments": False,  # Pas de commentaires pour économiser
                    "onlyInLanguage": "fr"
                }
                
                run_result = self._run_apify_actor(
                    self.scrapers_config["facebook"]["actor_id"],
                    input_data
                )
                
                if run_result and run_result.get("items"):
                    for item in run_result["items"]:
                        post = self._format_facebook_post(item, keyword)
                        if post:
                            posts.append(post)
                
                time.sleep(2)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Erreur Facebook scraping pour '{keyword}': {e}")
        
        return posts

    def _scrape_twitter_posts(self) -> List[Dict[str, Any]]:
        """Scraper Twitter avec recherche géographique"""
        posts = []
        
        for keyword in self.keywords_guadeloupe:
            try:
                # Requête Twitter avec géolocalisation
                search_query = f"{keyword} (near:\"Guadeloupe\" OR place:\"Guadeloupe\")"
                
                input_data = {
                    "searchTerms": [search_query],
                    "maxTweetsPerQuery": self.scrapers_config["twitter"]["max_posts"],
                    "language": "fr",
                    "onlyVerified": False,
                    "includeReplies": False  # Économiser les opérations
                }
                
                run_result = self._run_apify_actor(
                    self.scrapers_config["twitter"]["actor_id"],
                    input_data
                )
                
                if run_result and run_result.get("items"):
                    for item in run_result["items"]:
                        post = self._format_twitter_post(item, keyword)
                        if post:
                            posts.append(post)
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Erreur Twitter scraping pour '{keyword}': {e}")
        
        return posts

    def _scrape_instagram_posts(self) -> List[Dict[str, Any]]:
        """Scraper Instagram avec hashtags locaux"""
        posts = []
        
        # Hashtags Guadeloupe populaires
        hashtags = ["#guadeloupe", "#gwada", "#cd971"]
        
        for hashtag in hashtags[:2]:  # Limiter à 2 hashtags
            try:
                input_data = {
                    "hashtags": [hashtag],
                    "resultsPerPage": self.scrapers_config["instagram"]["max_posts"],
                    "resultsType": "posts"
                }
                
                run_result = self._run_apify_actor(
                    self.scrapers_config["instagram"]["actor_id"],
                    input_data
                )
                
                if run_result and run_result.get("items"):
                    for item in run_result["items"]:
                        post = self._format_instagram_post(item, hashtag)
                        if post:
                            posts.append(post)
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Erreur Instagram scraping pour '{hashtag}': {e}")
        
        return posts

    def _run_apify_actor(self, actor_id: str, input_data: Dict) -> Optional[Dict]:
        """Exécute un acteur Apify et récupère les résultats"""
        if not self.apify_token:
            logger.warning("APIFY_API_TOKEN non configuré — impossible de lancer l'actor")
            return None

        try:
            # Lancer l'acteur
            start_url = f"{self.apify_base_url}/acts/{actor_id}/runs"
            headers = {"Authorization": f"Bearer {self.apify_token}"}

            response = requests.post(start_url, json=input_data, headers=headers)

            # ── Gestion spécifique des erreurs d'authentification ──
            if response.status_code == 401:
                logger.error(
                    f"🔐 Apify 401 — Token invalide ou expiré.\n"
                    f"   Token: {self.apify_token[:12]}...\n"
                    f"   → Régénérez sur https://console.apify.com/account#/integrations\n"
                    f"   → Mettez à jour APIFY_API_TOKEN dans les variables d'env.\n"
                    f"   Réponse: {response.text[:300]}"
                )
                return None
            if response.status_code == 402:
                logger.error(f"💰 Apify 402 — Crédits épuisés. Rechargez sur https://console.apify.com/billing")
                return None
            if response.status_code == 429:
                logger.error(f"⏳ Apify 429 — Rate limit, réessayez plus tard")
                return None

            response.raise_for_status()

            run_info = response.json()["data"]
            run_id = run_info["id"]

            # Attendre la fin (max 5 minutes)
            max_wait = 300  # 5 minutes
            waited = 0

            while waited < max_wait:
                status_url = f"{self.apify_base_url}/actor-runs/{run_id}"
                status_response = requests.get(status_url, headers=headers)

                if status_response.status_code == 401:
                    logger.error("🔐 Apify 401 pendant polling — token expiré en cours de run")
                    return None

                status_data = status_response.json()["data"]

                if status_data["status"] == "SUCCEEDED":
                    # Récupérer les résultats
                    dataset_id = status_data["defaultDatasetId"]
                    dataset_url = f"{self.apify_base_url}/datasets/{dataset_id}/items"

                    data_response = requests.get(dataset_url, headers=headers)
                    return {"items": data_response.json()}

                elif status_data["status"] in ["FAILED", "ABORTED"]:
                    logger.error(f"Apify run failed: {status_data.get('statusMessage')}")
                    return None

                time.sleep(10)
                waited += 10

            logger.warning(f"Apify run timeout après {max_wait}s")
            return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"Erreur HTTP Apify actor {actor_id}: {e} — {e.response.text[:300] if e.response else ''}")
            return None
        except Exception as e:
            logger.error(f"Erreur exécution Apify actor {actor_id}: {e}")
            return None

    def _format_facebook_post(self, item: Dict, keyword: str) -> Optional[Dict[str, Any]]:
        """Formate un post Facebook au format standard"""
        try:
            return {
                "id": f"facebook_{item.get('postId', hash(item.get('text', '')))}",
                "platform": "facebook",
                "content": item.get("text", ""),
                "author": item.get("authorName", ""),
                "created_at": item.get("createdAt", datetime.now().isoformat()),
                "url": item.get("url", ""),
                "engagement": {
                    "likes": item.get("likesCount", 0),
                    "shares": item.get("sharesCount", 0),
                    "comments": item.get("commentsCount", 0),
                    "total": (item.get("likesCount", 0) + 
                             item.get("sharesCount", 0) + 
                             item.get("commentsCount", 0))
                },
                "keyword_searched": keyword,
                "scraped_at": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_method": "apify_facebook",
                "demo_data": False
            }
        except Exception as e:
            logger.error(f"Erreur formatage post Facebook: {e}")
            return None

    def _format_twitter_post(self, item: Dict, keyword: str) -> Optional[Dict[str, Any]]:
        """Formate un tweet au format standard"""
        try:
            return {
                "id": f"twitter_{item.get('id', hash(item.get('text', '')))}",
                "platform": "twitter",
                "content": item.get("text", ""),
                "author": item.get("author", {}).get("userName", ""),
                "created_at": item.get("createdAt", datetime.now().isoformat()),
                "url": item.get("url", ""),
                "engagement": {
                    "likes": item.get("likeCount", 0),
                    "retweets": item.get("retweetCount", 0),
                    "replies": item.get("replyCount", 0),
                    "total": (item.get("likeCount", 0) + 
                             item.get("retweetCount", 0) + 
                             item.get("replyCount", 0))
                },
                "keyword_searched": keyword,
                "scraped_at": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_method": "apify_twitter",
                "demo_data": False
            }
        except Exception as e:
            logger.error(f"Erreur formatage tweet: {e}")
            return None

    def _format_instagram_post(self, item: Dict, hashtag: str) -> Optional[Dict[str, Any]]:
        """Formate un post Instagram au format standard"""
        try:
            return {
                "id": f"instagram_{item.get('id', hash(item.get('caption', '')))}",
                "platform": "instagram",
                "content": item.get("caption", ""),
                "author": item.get("ownerUsername", ""),
                "created_at": item.get("timestamp", datetime.now().isoformat()),
                "url": item.get("url", ""),
                "engagement": {
                    "likes": item.get("likesCount", 0),
                    "comments": item.get("commentsCount", 0),
                    "total": (item.get("likesCount", 0) + item.get("commentsCount", 0))
                },
                "keyword_searched": hashtag,
                "scraped_at": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "source_method": "apify_instagram",
                "demo_data": False
            }
        except Exception as e:
            logger.error(f"Erreur formatage post Instagram: {e}")
            return None

    def _save_to_database(self, scraped_data: Dict[str, List[Dict]]):
        """Sauvegarde les données en base avec déduplication"""
        if self.db is None:
            return
        
        saved_count = 0
        for platform, posts in scraped_data.items():
            for post in posts:
                try:
                    # Upsert pour éviter les doublons
                    self.social_collection.update_one(
                        {"id": post["id"]},
                        {"$set": post},
                        upsert=True
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Erreur sauvegarde post {post.get('id')}: {e}")
        
        logger.info(f"Sauvegardé {saved_count} posts Apify en DB")

    def _check_daily_budget_exceeded(self, date: str) -> bool:
        """Vérifie si le budget quotidien est dépassé"""
        if self.db is None:
            return False
        
        try:
            today_runs = self.apify_runs_collection.find({"date": date})
            total_operations = sum(run.get("operations_used", 0) for run in today_runs)
            return total_operations >= self.daily_operation_budget
        except Exception:
            return False

    def _calculate_cost(self, operations: int) -> float:
        """Calcule le coût estimé en dollars"""
        # Moyenne pondérée des coûts par plateforme
        avg_cost_per_1000 = 0.25  # $0.25 pour 1000 opérations en moyenne
        return (operations / 1000) * avg_cost_per_1000

    def _log_apify_run(self, results: Dict):
        """Enregistre l'exécution pour le suivi des coûts"""
        if self.db is None:
            return
        
        try:
            log_entry = {
                "date": results["date"],
                "operations_used": results["operations_used"],
                "estimated_cost": results["estimated_cost"],
                "platforms_scraped": list(results["scraped_data"].keys()),
                "total_posts": sum(len(posts) for posts in results["scraped_data"].values()),
                "timestamp": datetime.now().isoformat(),
                "errors": results.get("errors", [])
            }
            
            self.apify_runs_collection.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Erreur log Apify run: {e}")

    def get_monthly_stats(self) -> Dict[str, Any]:
        """Statistiques mensuelles d'utilisation et coûts"""
        if self.db is None:
            return {}
        
        try:
            # Derniers 30 jours
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            pipeline = [
                {"$match": {"date": {"$gte": start_date}}},
                {"$group": {
                    "_id": None,
                    "total_operations": {"$sum": "$operations_used"},
                    "total_cost": {"$sum": "$estimated_cost"},
                    "total_posts": {"$sum": "$total_posts"},
                    "run_count": {"$sum": 1}
                }}
            ]
            
            result = list(self.apify_runs_collection.aggregate(pipeline))
            
            if result:
                stats = result[0]
                return {
                    "period": "30 derniers jours",
                    "total_operations": stats.get("total_operations", 0),
                    "estimated_cost": round(stats.get("total_cost", 0), 2),
                    "total_posts_collected": stats.get("total_posts", 0),
                    "scraping_runs": stats.get("run_count", 0),
                    "avg_cost_per_day": round(stats.get("total_cost", 0) / 30, 3),
                    "budget_utilization": f"{stats.get('total_cost', 0) * 100 / 10:.1f}%"  # Sur budget $10/mois
                }
            
        except Exception as e:
            logger.error(f"Erreur stats mensuelles: {e}")
        
        return {"error": "Impossible de calculer les stats"}

# Instance globale
apify_social_service = ApifySocialService()