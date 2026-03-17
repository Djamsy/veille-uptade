# backend/critical_topics_monitor.py
"""
Système de surveillance des sujets critiques en Guadeloupe
Surveille YouTube, TikTok, Facebook et Twitter pour détecter les polémiques émergentes
Version sécurisée avec tokens en variables d'environnement
"""

import os
import requests
import time
import json
import hashlib
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
import feedparser
from dataclasses import dataclass


logger = logging.getLogger(__name__)

@dataclass
class CriticalTopic:
    name: str
    keywords: List[str]
    severity_level: int  # 1-5, 5 = très critique
    platforms: List[str]  # ["youtube", "tiktok", "facebook", "twitter"]
    alert_threshold: int  # Nombre de mentions pour déclencher une alerte

class CriticalTopicsMonitor:
    def __init__(self):
        # Configuration API depuis variables d'environnement
        self.youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
        self.facebook_token = os.environ.get("FACEBOOK_ACCESS_TOKEN")
        self.twitter_bearer = os.environ.get("TWITTER_BEARER_TOKEN") 
        self.apify_token = os.environ.get("APIFY_API_TOKEN")
        
        # Vérification des tokens requis
        self._validate_api_tokens()
        
        # MongoDB connection
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.critical_alerts = self.db.critical_alerts
        self.social_monitoring = self.db.social_monitoring
        
        # Configuration des sujets critiques
        self.critical_topics = self._define_critical_topics()
        
        # Comptes à surveiller (détracteurs connus)
        self.monitored_accounts = self._load_monitored_accounts()

    def _validate_api_tokens(self):
        """Valide la présence des tokens API essentiels"""
        missing_tokens = []
        
        if not self.youtube_api_key:
            missing_tokens.append("YOUTUBE_API_KEY")
        if not self.facebook_token:
            missing_tokens.append("FACEBOOK_ACCESS_TOKEN")  
        if not self.twitter_bearer:
            missing_tokens.append("TWITTER_BEARER_TOKEN")
        if not self.apify_token:
            missing_tokens.append("APIFY_API_TOKEN")
        
        if missing_tokens:
            logger.warning(f"⚠️ Tokens manquants: {', '.join(missing_tokens)}")
            logger.warning("Certaines plateformes ne seront pas surveillées")
        else:
            logger.info("✅ Tous les tokens API sont configurés")

    def _load_monitored_accounts(self) -> Dict[str, List[Dict]]:
        """Charge la liste des comptes à surveiller depuis env ou config par défaut"""
        
        # Possibilité de configurer via variables d'environnement
        youtube_channels = os.environ.get("CRITICAL_YOUTUBE_CHANNELS", "").split(",")
        tiktok_accounts = os.environ.get("CRITICAL_TIKTOK_ACCOUNTS", "").split(",")
        facebook_pages = os.environ.get("CRITICAL_FACEBOOK_PAGES", "").split(",")
        twitter_accounts = os.environ.get("CRITICAL_TWITTER_ACCOUNTS", "").split(",")
        
        # Configuration par défaut si pas d'env
        return {
            "youtube_channels": [
                {"name": f"Channel {i}", "channel_id": channel.strip(), "risk_level": 4}
                for i, channel in enumerate(youtube_channels) if channel.strip()
            ] if youtube_channels[0] else [
                {"name": "Opposition Politique GP", "channel_id": "UC_EXAMPLE", "risk_level": 5},
            ],
            
            "tiktok_accounts": [
                {"username": account.strip(), "risk_level": 4}
                for account in tiktok_accounts if account.strip()
            ] if tiktok_accounts[0] else [
                {"username": "@critique_gwada", "risk_level": 5},
            ],
            
            "facebook_pages": [
                {"name": f"Page {i}", "page_id": page.strip(), "risk_level": 4}
                for i, page in enumerate(facebook_pages) if page.strip()
            ] if facebook_pages[0] else [
                {"name": "Page Opposition", "page_id": "123456789", "risk_level": 4},
            ],
            
            "twitter_accounts": [
                {"username": account.strip(), "risk_level": 4}
                for account in twitter_accounts if account.strip()
            ] if twitter_accounts[0] else [
                {"username": "opposition_gp", "risk_level": 5},
            ]
        }

    def _define_critical_topics(self) -> List[CriticalTopic]:
        """Définit les sujets critiques à surveiller"""
        return [
            CriticalTopic(
                name="Gestion de l'eau",
                keywords=["SMGEAG", "coupure eau", "tour d'eau", "eau potable", "pénurie eau"],
                severity_level=5,
                platforms=["youtube", "tiktok", "facebook", "twitter"],
                alert_threshold=10
            ),
            CriticalTopic(
                name="Corruption élus",
                keywords=["Guy Losbar", "corruption", "détournement", "procès élu", "justice"],
                severity_level=5,
                platforms=["youtube", "tiktok", "facebook", "twitter"],
                alert_threshold=5
            ),
            CriticalTopic(
                name="Sargasses",
                keywords=["sargasses", "algues", "pollution marine", "odeur", "santé sargasses"],
                severity_level=4,
                platforms=["youtube", "tiktok", "facebook", "twitter"],
                alert_threshold=15
            ),
            CriticalTopic(
                name="Chômage jeunes",
                keywords=["chômage", "jeunes sans emploi", "formation", "insertion"],
                severity_level=4,
                platforms=["youtube", "tiktok", "twitter"],
                alert_threshold=20
            ),
            CriticalTopic(
                name="Coût de la vie",
                keywords=["cherté", "prix", "pouvoir d'achat", "essence", "courses"],
                severity_level=3,
                platforms=["youtube", "facebook", "twitter"],
                alert_threshold=25
            ),
            CriticalTopic(
                name="Indépendance/autonomie",
                keywords=["indépendance", "autonomie", "statut", "souveraineté"],
                severity_level=4,
                platforms=["youtube", "tiktok", "twitter"],
                alert_threshold=8
            ),
            CriticalTopic(
                name="Chlordécane",
                keywords=["chlordécane", "pesticide", "cancer", "empoisonnement", "banane"],
                severity_level=5,
                platforms=["youtube", "facebook", "twitter"],
                alert_threshold=12
            ),
            CriticalTopic(
                name="Système de santé",
                keywords=["CHU", "CHUG", "hôpital", "médecins", "soins", "santé publique"],
                severity_level=4,
                platforms=["youtube", "facebook", "twitter"],
                alert_threshold=15
            )
        ]

    def monitor_youtube_channels(self) -> List[Dict[str, Any]]:
        """Surveille les nouvelles vidéos sur les chaînes YouTube critiques"""
        if not self.youtube_api_key:
            logger.warning("⚠️ YOUTUBE_API_KEY manquant, surveillance YouTube désactivée")
            return []
            
        alerts = []
        
        for channel in self.monitored_accounts["youtube_channels"]:
            try:
                # RSS feed de la chaîne
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
                feed = feedparser.parse(rss_url)
                
                # Analyser les dernières vidéos (dernières 24h)
                recent_threshold = datetime.now() - timedelta(hours=24)
                
                for entry in feed.entries[:5]:  # Dernières 5 vidéos
                    video_date = datetime.fromisoformat(entry.published.replace('Z', '+00:00'))
                    
                    if video_date > recent_threshold:
                        # Analyser le titre pour sujets critiques
                        critical_matches = self._analyze_content_for_critical_topics(
                            entry.title + " " + entry.summary
                        )
                        
                        if critical_matches:
                            alert = {
                                "platform": "youtube",
                                "account": channel["name"],
                                "risk_level": channel["risk_level"],
                                "video_url": entry.link,
                                "title": entry.title,
                                "critical_topics": critical_matches,
                                "published_at": video_date,
                                "detected_at": datetime.now(),
                                "comments_scraped": False
                            }
                            alerts.append(alert)
                            
                            # Programmer le scraping des commentaires
                            self._schedule_comment_scraping(entry.link, "youtube")
                
            except Exception as e:
                logger.error(f"Erreur surveillance YouTube {channel['name']}: {e}")
        
        return alerts

    def monitor_tiktok_accounts(self) -> List[Dict[str, Any]]:
        """Surveille les comptes TikTok via Apify"""
        if not self.apify_token:
            logger.warning("⚠️ APIFY_API_TOKEN manquant, surveillance TikTok désactivée")
            return []
            
        alerts = []
        
        for account in self.monitored_accounts["tiktok_accounts"]:
            try:
                # Utiliser Apify TikTok Profile Scraper
                apify_url = f"https://api.apify.com/v2/acts/clockworks~tiktok-profile-scraper/run-sync-get-dataset-items"
                
                payload = {
                    "profiles": [account["username"]],
                    "resultsLimit": 10
                }
                
                headers = {
                    "Authorization": f"Bearer {self.apify_token}",
                    "Content-Type": "application/json"
                }
                
                response = requests.post(apify_url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    videos = response.json()
                    
                    # Analyser les dernières vidéos
                    recent_threshold = datetime.now() - timedelta(hours=24)
                    
                    for video in videos:
                        video_date = datetime.fromisoformat(video.get("createTime", ""))
                        
                        if video_date > recent_threshold:
                            critical_matches = self._analyze_content_for_critical_topics(
                                video.get("text", "") + " " + video.get("hashtags", "")
                            )
                            
                            if critical_matches:
                                alert = {
                                    "platform": "tiktok",
                                    "account": account["username"],
                                    "risk_level": account["risk_level"],
                                    "video_url": video.get("webVideoUrl"),
                                    "text": video.get("text"),
                                    "critical_topics": critical_matches,
                                    "published_at": video_date,
                                    "detected_at": datetime.now(),
                                    "comments_scraped": False
                                }
                                alerts.append(alert)
                                
                                # Programmer le scraping des commentaires TikTok
                                self._schedule_comment_scraping(video.get("webVideoUrl"), "tiktok")
                
            except Exception as e:
                logger.error(f"Erreur surveillance TikTok {account['username']}: {e}")
        
        return alerts

    def monitor_twitter_keywords(self) -> List[Dict[str, Any]]:
        """Surveille Twitter pour les mots-clés critiques"""
        if not self.twitter_bearer:
            logger.warning("⚠️ TWITTER_BEARER_TOKEN manquant, surveillance Twitter désactivée")
            return []
            
        alerts = []
        
        headers = {
            "Authorization": f"Bearer {self.twitter_bearer}",
            "Content-Type": "application/json"
        }
        
        # Construire query avec tous les mots-clés critiques
        all_keywords = []
        for topic in self.critical_topics:
            if "twitter" in topic.platforms:
                all_keywords.extend(topic.keywords)
        
        # Rechercher tweets récents (dernières 2h)
        query = " OR ".join([f'"{kw}"' for kw in all_keywords[:10]])  # Limite API
        query += " lang:fr -is:retweet"
        
        try:
            url = "https://api.twitter.com/2/tweets/search/recent"
            params = {
                "query": query,
                "max_results": 50,
                "tweet.fields": "created_at,author_id,public_metrics"
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                tweets = response.json().get("data", [])
                
                for tweet in tweets:
                    critical_matches = self._analyze_content_for_critical_topics(tweet["text"])
                    
                    if critical_matches:
                        # Analyser l'engagement
                        metrics = tweet.get("public_metrics", {})
                        engagement_score = (
                            metrics.get("retweet_count", 0) * 2 +
                            metrics.get("like_count", 0) +
                            metrics.get("reply_count", 0) * 3
                        )
                        
                        if engagement_score > 10:  # Seuil d'alerte
                            alert = {
                                "platform": "twitter",
                                "tweet_id": tweet["id"],
                                "text": tweet["text"],
                                "critical_topics": critical_matches,
                                "engagement_score": engagement_score,
                                "metrics": metrics,
                                "created_at": tweet["created_at"],
                                "detected_at": datetime.now()
                            }
                            alerts.append(alert)
            
        except Exception as e:
            logger.error(f"Erreur surveillance Twitter: {e}")
        
        return alerts

    def monitor_facebook_pages(self) -> List[Dict[str, Any]]:
        """Surveille les pages Facebook pour les sujets critiques"""
        if not self.facebook_token:
            logger.warning("⚠️ FACEBOOK_ACCESS_TOKEN manquant, surveillance Facebook désactivée")
            return []
            
        alerts = []
        
        for page in self.monitored_accounts["facebook_pages"]:
            try:
                # Facebook Graph API
                url = f"https://graph.facebook.com/v18.0/{page['page_id']}/posts"
                params = {
                    "access_token": self.facebook_token,
                    "fields": "message,created_time,reactions.summary(true),comments.summary(true)",
                    "limit": 10
                }
                
                response = requests.get(url, params=params)
                
                if response.status_code == 200:
                    posts = response.json().get("data", [])
                    
                    recent_threshold = datetime.now() - timedelta(hours=24)
                    
                    for post in posts:
                        post_date = datetime.fromisoformat(post["created_time"].replace('Z', '+00:00'))
                        
                        if post_date > recent_threshold:
                            message = post.get("message", "")
                            critical_matches = self._analyze_content_for_critical_topics(message)
                            
                            if critical_matches:
                                reactions = post.get("reactions", {}).get("summary", {}).get("total_count", 0)
                                comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                                
                                engagement_score = reactions + (comments * 2)
                                
                                if engagement_score > 20:  # Seuil Facebook
                                    alert = {
                                        "platform": "facebook",
                                        "page": page["name"],
                                        "post_id": post["id"],
                                        "message": message,
                                        "critical_topics": critical_matches,
                                        "engagement_score": engagement_score,
                                        "reactions": reactions,
                                        "comments_count": comments,
                                        "created_at": post_date,
                                        "detected_at": datetime.now()
                                    }
                                    alerts.append(alert)
                
            except Exception as e:
                logger.error(f"Erreur surveillance Facebook {page['name']}: {e}")
        
        return alerts

    def _analyze_content_for_critical_topics(self, content: str) -> List[Dict[str, Any]]:
        """Analyse le contenu pour détecter les sujets critiques"""
        content_lower = content.lower()
        critical_matches = []
        
        for topic in self.critical_topics:
            matches = []
            for keyword in topic.keywords:
                if keyword.lower() in content_lower:
                    matches.append(keyword)
            
            if matches:
                critical_matches.append({
                    "topic": topic.name,
                    "severity": topic.severity_level,
                    "matched_keywords": matches,
                    "alert_threshold": topic.alert_threshold
                })
        
        return critical_matches

    def _schedule_comment_scraping(self, url: str, platform: str):
        """Programme le scraping des commentaires pour une URL"""
        try:
            # Enregistrer la tâche de scraping différé
            scraping_task = {
                "url": url,
                "platform": platform,
                "scheduled_at": datetime.now(),
                "execute_at": datetime.now() + timedelta(hours=3),  # 3h plus tard
                "status": "pending"
            }
            
            self.social_monitoring.insert_one(scraping_task)
            logger.info(f"Scraping programmé pour {platform}: {url}")
            
        except Exception as e:
            logger.error(f"Erreur programmation scraping: {e}")

    def scrape_comments_with_apify(self, url: str, platform: str) -> List[Dict[str, Any]]:
        """Scrape les commentaires via Apify"""
        if not self.apify_token:
            logger.warning("APIFY_API_TOKEN manquant pour scraping commentaires")
            return []
            
        try:
            if platform == "youtube":
                apify_actor = "bernardo~youtube-scraper"
                payload = {"startUrls": [url], "maxComments": 100}
            
            elif platform == "tiktok":
                apify_actor = "clockworks~tiktok-scraper"
                payload = {"startUrls": [url], "maxComments": 50}
            
            apify_url = f"https://api.apify.com/v2/acts/{apify_actor}/run-sync-get-dataset-items"
            
            headers = {
                "Authorization": f"Bearer {self.apify_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(apify_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            
        except Exception as e:
            logger.error(f"Erreur scraping commentaires {platform}: {e}")
        
        return []

    def analyze_comments_sentiment(self, comments: List[Dict], topic_context: List[Dict]) -> Dict[str, Any]:
        """Analyse le sentiment des commentaires sur les sujets critiques"""
        
        negative_indicators = ["scandale", "honte", "démission", "corruption", "mensonge", 
                              "incompétent", "voyou", "voleur", "ça suffit", "dehors"]
        
        positive_indicators = ["bravo", "enfin", "soutien", "courage", "bien fait", "justice"]
        
        sentiment_analysis = {
            "total_comments": len(comments),
            "negative_sentiment": 0,
            "positive_sentiment": 0,
            "neutral_sentiment": 0,
            "crisis_indicators": [],
            "trending_phrases": []
        }
        
        for comment in comments:
            text = comment.get("text", "").lower()
            
            neg_score = sum(1 for indicator in negative_indicators if indicator in text)
            pos_score = sum(1 for indicator in positive_indicators if indicator in text)
            
            if neg_score > pos_score:
                sentiment_analysis["negative_sentiment"] += 1
            elif pos_score > neg_score:
                sentiment_analysis["positive_sentiment"] += 1
            else:
                sentiment_analysis["neutral_sentiment"] += 1
            
            # Détecter indicateurs de crise
            if neg_score >= 2:
                sentiment_analysis["crisis_indicators"].append({
                    "comment": text[:100],
                    "negative_score": neg_score
                })
        
        # Calculer ratio critique
        if sentiment_analysis["total_comments"] > 10:
            negative_ratio = sentiment_analysis["negative_sentiment"] / sentiment_analysis["total_comments"]
            sentiment_analysis["crisis_level"] = "HIGH" if negative_ratio > 0.7 else "MEDIUM" if negative_ratio > 0.5 else "LOW"
        else:
            sentiment_analysis["crisis_level"] = "INSUFFICIENT_DATA"
        
        return sentiment_analysis

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """Lance un cycle complet de surveillance"""
        logger.info("🚀 Démarrage surveillance sujets critiques")
        
        all_alerts = []
        
        # Surveillance YouTube
        youtube_alerts = self.monitor_youtube_channels()
        all_alerts.extend(youtube_alerts)
        logger.info(f"📺 YouTube: {len(youtube_alerts)} alertes")
        
        # Surveillance TikTok
        tiktok_alerts = self.monitor_tiktok_accounts()
        all_alerts.extend(tiktok_alerts)
        logger.info(f"🎵 TikTok: {len(tiktok_alerts)} alertes")
        
        # Surveillance Twitter
        twitter_alerts = self.monitor_twitter_keywords()
        all_alerts.extend(twitter_alerts)
        logger.info(f"🐦 Twitter: {len(twitter_alerts)} alertes")
        
        # Surveillance Facebook
        facebook_alerts = self.monitor_facebook_pages()
        all_alerts.extend(facebook_alerts)
        logger.info(f"👥 Facebook: {len(facebook_alerts)} alertes")
        
        # Sauvegarder toutes les alertes
        if all_alerts:
            self.critical_alerts.insert_many(all_alerts)
            logger.info(f"💾 {len(all_alerts)} alertes sauvegardées en base")
        
        # Traiter les tâches de scraping en attente
        processed_tasks = self._process_pending_scraping_tasks()
        
        result = {
            "timestamp": datetime.now(),
            "total_alerts": len(all_alerts),
            "youtube_alerts": len(youtube_alerts),
            "tiktok_alerts": len(tiktok_alerts),
            "twitter_alerts": len(twitter_alerts),
            "facebook_alerts": len(facebook_alerts),
            "processed_scraping_tasks": processed_tasks,
            "critical_topics_detected": list(set([
                topic["topic"] for alert in all_alerts 
                for topic in alert.get("critical_topics", [])
            ]))
        }
        
        logger.info(f"✅ Surveillance terminée: {result}")
        return result

    def _process_pending_scraping_tasks(self) -> int:
        """Traite les tâches de scraping de commentaires en attente"""
        current_time = datetime.now()
        
        pending_tasks = list(self.social_monitoring.find({
            "status": "pending",
            "execute_at": {"$lte": current_time}
        }))
        
        processed_count = 0
        
        for task in pending_tasks:
            try:
                # Scraper les commentaires
                comments = self.scrape_comments_with_apify(task["url"], task["platform"])
                
                # Analyser le sentiment
                if comments:
                    # Récupérer le contexte critique de l'alert originale
                    original_alert = self.critical_alerts.find_one({"video_url": task["url"]})
                    topic_context = original_alert.get("critical_topics", []) if original_alert else []
                    
                    sentiment_analysis = self.analyze_comments_sentiment(comments, topic_context)
                    
                    # Mettre à jour l'alert avec l'analyse
                    self.critical_alerts.update_one(
                        {"video_url": task["url"]},
                        {"$set": {
                            "comments_analysis": sentiment_analysis,
                            "comments_scraped": True,
                            "crisis_level": sentiment_analysis.get("crisis_level", "UNKNOWN")
                        }}
                    )
                    
                    # Déclencher une alerte si niveau de crise élevé
                    if sentiment_analysis.get("crisis_level") == "HIGH":
                        self._trigger_high_crisis_alert(task["url"], sentiment_analysis)
                    
                    processed_count += 1
                
                # Marquer la tâche comme terminée
                self.social_monitoring.update_one(
                    {"_id": task["_id"]},
                    {"$set": {"status": "completed", "completed_at": current_time}}
                )
                
            except Exception as e:
                logger.error(f"Erreur traitement tâche scraping: {e}")
                self.social_monitoring.update_one(
                    {"_id": task["_id"]},
                    {"$set": {"status": "error", "error": str(e)}}
                )
        
        return processed_count

    def _trigger_high_crisis_alert(self, url: str, sentiment_analysis: Dict):
        """Déclenche une alerte de crise de niveau élevé"""
        crisis_alert = {
            "type": "HIGH_CRISIS",
            "url": url,
            "detected_at": datetime.now(),
            "sentiment_analysis": sentiment_analysis,
            "requires_immediate_attention": True,
            "status": "ACTIVE"
        }
        
        self.critical_alerts.insert_one(crisis_alert)
        
        # Ici vous pouvez ajouter des notifications (email, Telegram, etc.)
        logger.critical(f"🚨 ALERTE CRISE ÉLEVÉE détectée: {url}")

    def get_active_alerts(self, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Récupère les alertes actives des dernières heures"""
        threshold = datetime.now() - timedelta(hours=hours_back)
        
        return list(self.critical_alerts.find({
            "detected_at": {"$gte": threshold}
        }).sort("detected_at", -1))

    def get_crisis_dashboard(self) -> Dict[str, Any]:
        """Génère un dashboard des crises en cours"""
        
        # Alertes des dernières 24h
        recent_alerts = self.get_active_alerts(24)
        
        # Statistiques par plateforme
        platform_stats = {}
        for alert in recent_alerts:
            platform = alert["platform"]
            platform_stats[platform] = platform_stats.get(platform, 0) + 1
        
        # Topics les plus critiques
        topic_frequency = {}
        for alert in recent_alerts:
            for topic in alert.get("critical_topics", []):
                topic_name = topic["topic"]
                topic_frequency[topic_name] = topic_frequency.get(topic_name, 0) + 1
        
        # Alertes de crise élevée
        high_crisis_alerts = [alert for alert in recent_alerts if alert.get("type") == "HIGH_CRISIS"]
        
        return {
            "timestamp": datetime.now(),
            "total_alerts_24h": len(recent_alerts),
            "high_crisis_alerts": len(high_crisis_alerts),
            "platform_breakdown": platform_stats,
            "most_critical_topics": sorted(topic_frequency.items(), key=lambda x: x[1], reverse=True),
            "requires_attention": len(high_crisis_alerts) > 0,
            "latest_alerts": recent_alerts[:10]
        }


# Instance globale
critical_monitor = CriticalTopicsMonitor()

# Export explicite pour l'import
__all__ = ['critical_monitor', 'CriticalTopicsMonitor']

if __name__ == "__main__":
    # Test du système
    result = critical_monitor.run_monitoring_cycle()
    print(json.dumps(result, indent=2, default=str))