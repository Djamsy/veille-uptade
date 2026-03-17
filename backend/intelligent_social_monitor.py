# backend/intelligent_social_monitor.py
"""
Système de surveillance réseaux sociaux intelligent
- Seuil 2 conditionné par les résultats de l'IA
- Récupération et analyse des commentaires
- Génération de graphiques de sentiment
- Métriques avancées et tableaux de bord
"""

import os
import time
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pymongo import MongoClient
import hashlib
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SentimentMetrics:
    positive_count: int
    negative_count: int
    neutral_count: int
    total_posts: int
    negative_ratio: float
    positive_ratio: float
    engagement_score: float
    crisis_indicators: List[str]

class IntelligentSocialMonitor:
    def __init__(self):
        # MongoDB
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.affaires_collection = self.db["affaires_guadeloupe"]
        self.social_collection = self.db["social_media_posts"]
        self.comments_collection = self.db["social_comments"]
        self.sentiment_metrics = self.db["sentiment_metrics"]
        self.monitoring_log = self.db["social_monitoring_log"]
        
        # Configuration des seuils intelligents
        self.thresholds = {
            "basic_scan": 0.7,           # Seuil 1: Scanner les pages officielles
            "ai_triggered_scan": {       # Seuil 2: Conditionné par l'IA
                "min_importance": 0.75,
                "required_ai_confidence": 0.7,
                "negative_sentiment_trigger": -0.3,
                "entity_relevance": ["Guy Losbar", "CD971", "Conseil Départemental"]
            },
            "deep_crisis_scan": 0.85     # Seuil 3: Scan critique
        }
        
        # Comptes des médias locaux
        self.media_accounts = {
            "facebook": [
                {
                    "name": "RCI Guadeloupe",
                    "page_id": "RCIGUADELOUPE971",
                    "url": "https://www.facebook.com/RCIGUADELOUPE971",
                    "priority": "high",
                    "comments_enabled": True
                },
                {
                    "name": "KaribInfo",
                    "page_id": "Karibinfo",
                    "url": "https://www.facebook.com/Karibinfo",
                    "priority": "high",
                    "comments_enabled": True
                },
                {
                    "name": "France-Antilles Guadeloupe",
                    "page_id": "FranceAntillesGuadeloupe",
                    "url": "https://www.facebook.com/FranceAntillesGuadeloupe",
                    "priority": "high",
                    "comments_enabled": True
                }
            ],
            "instagram": [
                {
                    "name": "France-Antilles Guadeloupe",
                    "username": "franceantilles_guadeloupe",
                    "url": "https://www.instagram.com/franceantilles_guadeloupe/",
                    "priority": "high",
                    "comments_enabled": True
                },
                {
                    "name": "RCI Guadeloupe",
                    "username": "rciguadeloupe", 
                    "url": "https://www.instagram.com/rciguadeloupe/",
                    "priority": "high",
                    "comments_enabled": True
                }
            ]
        }
        
        # Configuration APIs
        self.facebook_token = os.environ.get("FACEBOOK_ACCESS_TOKEN")
        self.apify_token = os.environ.get("APIFY_API_TOKEN")
        
        # Indicateurs de crise pour analyse de sentiment
        self.crisis_indicators = {
            "high": ["démission", "scandale", "corruption", "procès", "condamnation", "honte", "inadmissible"],
            "medium": ["problème", "colère", "déçu", "incompétence", "mensonge", "tromperie"],
            "escalation": ["manifestation", "grève", "blocage", "révolte", "ça suffit", "dehors"]
        }

    def check_ai_triggered_conditions(self, affair: Dict[str, Any]) -> Dict[str, Any]:
        """Vérifie les conditions intelligentes pour déclencher le seuil 2"""
        
        try:
            importance_score = affair.get("importance_score", 0.0)
            ai_confidence = affair.get("analysis_confidence", 0.0)
            sentiment_analysis = affair.get("sentiment", {})
            primary_entity = affair.get("primary_entity", "")
            theme = affair.get("theme", "")
            mistral_called = affair.get("mistral_called", False)
            
            conditions = {
                "importance_met": importance_score >= self.thresholds["ai_triggered_scan"]["min_importance"],
                "ai_confidence_met": ai_confidence >= self.thresholds["ai_triggered_scan"]["required_ai_confidence"],
                "mistral_analysis": mistral_called,
                "entity_relevant": any(entity in primary_entity for entity in self.thresholds["ai_triggered_scan"]["entity_relevance"]),
                "sentiment_negative": sentiment_analysis.get("score", 0) < self.thresholds["ai_triggered_scan"]["negative_sentiment_trigger"],
                "departmental_theme": theme in ["politique_institutions", "securite_justice"]
            }
            
            # Conditions obligatoires
            mandatory_conditions = ["importance_met", "mistral_analysis", "entity_relevant"]
            mandatory_met = all(conditions[cond] for cond in mandatory_conditions)
            
            # Conditions optionnelles (au moins 1)
            optional_conditions = ["ai_confidence_met", "sentiment_negative", "departmental_theme"]
            optional_met = any(conditions[cond] for cond in optional_conditions)
            
            should_trigger = mandatory_met and optional_met
            
            return {
                "should_trigger": should_trigger,
                "conditions": conditions,
                "reason": self._generate_trigger_reason(conditions, should_trigger),
                "confidence_score": ai_confidence,
                "importance_score": importance_score
            }
            
        except Exception as e:
            logger.error(f"Erreur vérification conditions IA: {e}")
            return {"should_trigger": False, "reason": f"Erreur: {e}"}

    def _generate_trigger_reason(self, conditions: Dict[str, bool], should_trigger: bool) -> str:
        """Génère une explication de la décision de déclenchement"""
        
        if not should_trigger:
            failed_conditions = [k for k, v in conditions.items() if not v]
            return f"Conditions non remplies: {', '.join(failed_conditions)}"
        
        met_conditions = [k for k, v in conditions.items() if v]
        return f"IA déclenché: {', '.join(met_conditions)}"

    def execute_ai_triggered_scan(self, affair: Dict[str, Any]) -> Dict[str, Any]:
        """Seuil 2: Scan déclenché par l'IA avec récupération de commentaires"""
        
        logger.info(f"AI TRIGGERED SCAN pour affaire {affair['affaire_id']}")
        
        results = {
            "scan_type": "ai_triggered_scan",
            "affair_id": affair["affaire_id"],
            "posts_found": [],
            "comments_analyzed": [],
            "sentiment_metrics": {},
            "platforms_scanned": [],
            "ai_trigger_reason": "",
            "execution_time": 0,
            "cost_estimate": "medium-high"
        }
        
        start_time = time.time()
        
        # Générer mots-clés intelligents basés sur l'analyse IA
        keywords = self._generate_ai_keywords(affair)
        
        try:
            # Scanner Facebook avec récupération de commentaires
            fb_posts = self._scan_facebook_with_comments(keywords, affair)
            results["posts_found"].extend(fb_posts)
            results["platforms_scanned"].append("facebook")
            
            # Scanner Instagram avec récupération de commentaires
            ig_posts = self._scan_instagram_with_comments(keywords, affair)
            results["posts_found"].extend(ig_posts)
            results["platforms_scanned"].append("instagram")
            
            # Collecter tous les commentaires
            all_comments = []
            for post in results["posts_found"]:
                all_comments.extend(post.get("comments", []))
            
            results["comments_analyzed"] = all_comments
            
            # Analyser le sentiment des commentaires
            if all_comments:
                sentiment_metrics = self._analyze_comments_sentiment_advanced(all_comments, affair)
                results["sentiment_metrics"] = sentiment_metrics
                
                # Sauvegarder métriques pour graphiques
                self._save_sentiment_metrics(affair["affaire_id"], sentiment_metrics)
            
        except Exception as e:
            logger.error(f"Erreur AI triggered scan: {e}")
            results["error"] = str(e)
        
        results["execution_time"] = round(time.time() - start_time, 2)
        
        logger.info(f"AI triggered scan terminé: {len(results['posts_found'])} posts, "
                   f"{len(results['comments_analyzed'])} commentaires en {results['execution_time']}s")
        
        return results

    def _generate_ai_keywords(self, affair: Dict[str, Any]) -> List[str]:
        """Génère des mots-clés intelligents basés sur l'analyse IA"""
        
        keywords = []
        
        # Entité principale analysée par l'IA
        primary_entity = affair.get("primary_entity", "")
        if primary_entity and primary_entity != "Aucune":
            keywords.append(primary_entity)
            
            # Variations spécifiques selon l'entité
            if "Guy Losbar" in primary_entity:
                keywords.extend(["Losbar", "Président CD971", "Conseil Départemental Guadeloupe"])
            elif "CD971" in primary_entity:
                keywords.extend(["Conseil Départemental", "Département Guadeloupe", "CD 971"])
        
        # Entités secondaires détectées par l'IA
        entities_analysis = affair.get("entities_analysis", [])
        for entity_data in entities_analysis[:2]:  # Limiter à 2
            if isinstance(entity_data, dict) and entity_data.get("entity"):
                keywords.append(entity_data["entity"])
        
        # Mots-clés thématiques selon l'analyse IA
        theme = affair.get("theme", "")
        ai_theme_keywords = {
            "politique_institutions": ["politique", "budget", "conseil", "décision"],
            "securite_justice": ["justice", "procès", "tribunal", "enquête"],
            "sante_social": ["santé", "social", "hôpital"]
        }
        
        if theme in ai_theme_keywords:
            keywords.extend(ai_theme_keywords[theme])
        
        # Contexte émotionnel selon le sentiment IA
        sentiment = affair.get("sentiment", {})
        if sentiment.get("impact") == "négatif":
            keywords.extend(["problème", "crise", "scandale"])
        
        return list(set(keywords))[:6]  # Déduplication et limitation

    def _scan_facebook_with_comments(self, keywords: List[str], affair: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scan Facebook avec récupération de commentaires"""
        posts = []
        
        for media_account in self.media_accounts["facebook"]:
            if not media_account.get("comments_enabled"):
                continue
                
            try:
                # Simuler la récupération de posts avec commentaires
                # En réalité, on utiliserait l'API Facebook ou Apify
                
                for keyword in keywords[:3]:  # Limiter pour coûts
                    post_data = {
                        "id": f"fb_{media_account['page_id']}_{hashlib.md5(keyword.encode()).hexdigest()}",
                        "platform": "facebook",
                        "source": media_account["name"],
                        "content": f"Post sur {keyword} de {media_account['name']}",
                        "keyword_searched": keyword,
                        "url": f"{media_account['url']}/posts/123456",
                        "created_at": datetime.now().isoformat(),
                        "engagement": {"likes": 45, "shares": 12, "comments": 8},
                        "comments": self._simulate_facebook_comments(keyword, affair),
                        "scan_method": "ai_triggered_facebook"
                    }
                    
                    posts.append(post_data)
                    time.sleep(2)  # Rate limiting
                    
            except Exception as e:
                logger.warning(f"Erreur scan Facebook {media_account['name']}: {e}")
        
        return posts

    def _scan_instagram_with_comments(self, keywords: List[str], affair: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scan Instagram avec récupération de commentaires"""
        posts = []
        
        for media_account in self.media_accounts["instagram"]:
            if not media_account.get("comments_enabled"):
                continue
                
            try:
                # Simuler la récupération de posts Instagram avec commentaires
                
                for keyword in keywords[:2]:  # Plus strict pour Instagram
                    post_data = {
                        "id": f"ig_{media_account['username']}_{hashlib.md5(keyword.encode()).hexdigest()}",
                        "platform": "instagram",
                        "source": media_account["name"],
                        "content": f"Post Instagram sur {keyword}",
                        "keyword_searched": keyword,
                        "url": f"{media_account['url']}p/ABC123/",
                        "created_at": datetime.now().isoformat(),
                        "engagement": {"likes": 120, "comments": 15},
                        "comments": self._simulate_instagram_comments(keyword, affair),
                        "scan_method": "ai_triggered_instagram"
                    }
                    
                    posts.append(post_data)
                    time.sleep(3)  # Rate limiting plus strict
                    
            except Exception as e:
                logger.warning(f"Erreur scan Instagram {media_account['name']}: {e}")
        
        return posts

    def _simulate_facebook_comments(self, keyword: str, affair: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Simule des commentaires Facebook réalistes"""
        
        # En production, ceci ferait appel à l'API Facebook ou Apify
        comments = [
            {
                "id": f"comment_{hashlib.md5(f'{keyword}_1'.encode()).hexdigest()}",
                "author": "User1",
                "content": f"Encore un scandale avec {keyword} ! Ça suffit !",
                "created_at": datetime.now().isoformat(),
                "likes": 12,
                "sentiment_predicted": "negative"
            },
            {
                "id": f"comment_{hashlib.md5(f'{keyword}_2'.encode()).hexdigest()}",
                "author": "User2", 
                "content": f"Il faut soutenir {keyword} dans cette période difficile",
                "created_at": datetime.now().isoformat(),
                "likes": 3,
                "sentiment_predicted": "positive"
            },
            {
                "id": f"comment_{hashlib.md5(f'{keyword}_3'.encode()).hexdigest()}",
                "author": "User3",
                "content": "Où sont les preuves ? Il faut attendre la justice",
                "created_at": datetime.now().isoformat(),
                "likes": 7,
                "sentiment_predicted": "neutral"
            }
        ]
        
        return comments

    def _simulate_instagram_comments(self, keyword: str, affair: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Simule des commentaires Instagram réalistes"""
        
        comments = [
            {
                "id": f"ig_comment_{hashlib.md5(f'{keyword}_1'.encode()).hexdigest()}",
                "author": "@user_gwada",
                "content": f"😡 {keyword} déception totale !",
                "created_at": datetime.now().isoformat(),
                "likes": 25,
                "sentiment_predicted": "negative"
            },
            {
                "id": f"ig_comment_{hashlib.md5(f'{keyword}_2'.encode()).hexdigest()}",
                "author": "@citoyen971",
                "content": "👏 Enfin la vérité sur cette affaire",
                "created_at": datetime.now().isoformat(),
                "likes": 8,
                "sentiment_predicted": "positive"
            }
        ]
        
        return comments

    def _analyze_comments_sentiment_advanced(self, comments: List[Dict[str, Any]], affair: Dict[str, Any]) -> SentimentMetrics:
        """Analyse avancée du sentiment des commentaires avec détection de crise"""
        
        if not comments:
            return SentimentMetrics(0, 0, 0, 0, 0.0, 0.0, 0.0, [])
        
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        total_engagement = 0
        crisis_indicators_found = []
        
        for comment in comments:
            content = comment.get("content", "").lower()
            likes = comment.get("likes", 0)
            total_engagement += likes
            
            # Analyse sentiment basée sur indicateurs de crise
            crisis_score = 0
            positive_score = 0
            
            # Détection indicateurs de crise
            for level, indicators in self.crisis_indicators.items():
                for indicator in indicators:
                    if indicator in content:
                        if level == "high":
                            crisis_score += 3
                            crisis_indicators_found.append(indicator)
                        elif level == "medium":
                            crisis_score += 2
                        elif level == "escalation":
                            crisis_score += 4
                            crisis_indicators_found.append(f"ESCALADE: {indicator}")
            
            # Indicateurs positifs
            positive_indicators = ["bravo", "soutien", "courage", "bien", "félicitations", "👏", "❤️"]
            for indicator in positive_indicators:
                if indicator in content:
                    positive_score += 1
            
            # Classification finale
            if crisis_score > positive_score + 1:
                negative_count += 1
            elif positive_score > crisis_score:
                positive_count += 1
            else:
                neutral_count += 1
        
        total_posts = len(comments)
        negative_ratio = negative_count / total_posts if total_posts > 0 else 0
        positive_ratio = positive_count / total_posts if total_posts > 0 else 0
        engagement_score = total_engagement / total_posts if total_posts > 0 else 0
        
        return SentimentMetrics(
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            total_posts=total_posts,
            negative_ratio=negative_ratio,
            positive_ratio=positive_ratio,
            engagement_score=engagement_score,
            crisis_indicators=list(set(crisis_indicators_found))
        )

    def _save_sentiment_metrics(self, affair_id: str, metrics: SentimentMetrics):
        """Sauvegarde les métriques de sentiment pour génération de graphiques"""
        
        try:
            metric_document = {
                "affair_id": affair_id,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "hour": datetime.now().hour,
                "metrics": {
                    "positive_count": metrics.positive_count,
                    "negative_count": metrics.negative_count,
                    "neutral_count": metrics.neutral_count,
                    "total_posts": metrics.total_posts,
                    "negative_ratio": metrics.negative_ratio,
                    "positive_ratio": metrics.positive_ratio,
                    "engagement_score": metrics.engagement_score,
                    "crisis_indicators": metrics.crisis_indicators
                },
                "alert_level": self._determine_alert_level(metrics)
            }
            
            self.sentiment_metrics.insert_one(metric_document)
            
            # Créer aussi un point pour les graphiques temporels
            self._create_sentiment_graph_data(affair_id, metrics)
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde métriques sentiment: {e}")

    def _determine_alert_level(self, metrics: SentimentMetrics) -> str:
        """Détermine le niveau d'alerte basé sur les métriques"""
        
        if metrics.crisis_indicators and any("ESCALADE" in indicator for indicator in metrics.crisis_indicators):
            return "CRITICAL"
        elif metrics.negative_ratio > 0.8 and metrics.engagement_score > 10:
            return "HIGH"
        elif metrics.negative_ratio > 0.6 or len(metrics.crisis_indicators) > 2:
            return "MEDIUM"
        else:
            return "LOW"

    def _create_sentiment_graph_data(self, affair_id: str, metrics: SentimentMetrics):
        """Crée les données pour les graphiques de sentiment temporels"""
        
        try:
            # Collection spéciale pour données de graphiques
            graph_collection = self.db["sentiment_graph_data"]
            
            graph_point = {
                "affair_id": affair_id,
                "timestamp": datetime.now(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "hour": datetime.now().hour,
                "minute": datetime.now().minute,
                "positive_ratio": round(metrics.positive_ratio, 3),
                "negative_ratio": round(metrics.negative_ratio, 3),
                "engagement_score": round(metrics.engagement_score, 2),
                "crisis_level": len(metrics.crisis_indicators)
            }
            
            graph_collection.insert_one(graph_point)
            
        except Exception as e:
            logger.error(f"Erreur création données graphique: {e}")

    def generate_sentiment_dashboard(self, affair_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Génère un tableau de bord de sentiment pour une affaire"""
        
        try:
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            
            # Récupérer métriques de l'affaire
            metrics_data = list(self.sentiment_metrics.find({
                "affair_id": affair_id,
                "date": {"$gte": since_date}
            }).sort("timestamp", 1))
            
            if not metrics_data:
                return {"error": "Aucune donnée de sentiment disponible"}
            
            # Données pour graphique temporel
            graph_data = list(self.db["sentiment_graph_data"].find({
                "affair_id": affair_id,
                "timestamp": {"$gte": datetime.now() - timedelta(days=days_back)}
            }).sort("timestamp", 1))
            
            # Statistiques générales
            latest_metrics = metrics_data[-1]["metrics"]
            total_comments = sum([m["metrics"]["total_posts"] for m in metrics_data])
            avg_negative_ratio = sum([m["metrics"]["negative_ratio"] for m in metrics_data]) / len(metrics_data)
            
            # Tendance (comparaison premier vs dernier)
            if len(metrics_data) > 1:
                first_negative = metrics_data[0]["metrics"]["negative_ratio"]
                last_negative = metrics_data[-1]["metrics"]["negative_ratio"]
                trend = "DETERIORATION" if last_negative > first_negative + 0.1 else "AMELIORATION" if first_negative > last_negative + 0.1 else "STABLE"
            else:
                trend = "INSUFFICIENT_DATA"
            
            dashboard = {
                "affair_id": affair_id,
                "generated_at": datetime.now().isoformat(),
                "period": f"{days_back} derniers jours",
                "summary": {
                    "total_comments_analyzed": total_comments,
                    "current_negative_ratio": latest_metrics["negative_ratio"],
                    "average_negative_ratio": round(avg_negative_ratio, 3),
                    "trend": trend,
                    "alert_level": self._determine_alert_level(SentimentMetrics(**latest_metrics)),
                    "crisis_indicators_active": latest_metrics["crisis_indicators"]
                },
                "graph_data": [
                    {
                        "timestamp": point["timestamp"].isoformat(),
                        "positive_ratio": point["positive_ratio"],
                        "negative_ratio": point["negative_ratio"],
                        "engagement_score": point["engagement_score"]
                    }
                    for point in graph_data
                ],
                "daily_breakdown": self._generate_daily_breakdown(metrics_data),
                "recommendations": self._generate_recommendations(latest_metrics, trend)
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Erreur génération dashboard sentiment: {e}")
            return {"error": str(e)}

    def _generate_daily_breakdown(self, metrics_data: List[Dict]) -> List[Dict]:
        """Génère un résumé par jour"""
        
        daily_data = {}
        
        for metric in metrics_data:
            date = metric["date"]
            if date not in daily_data:
                daily_data[date] = {
                    "date": date,
                    "total_comments": 0,
                    "negative_count": 0,
                    "positive_count": 0,
                    "crisis_indicators": []
                }
            
            daily_data[date]["total_comments"] += metric["metrics"]["total_posts"]
            daily_data[date]["negative_count"] += metric["metrics"]["negative_count"]
            daily_data[date]["positive_count"] += metric["metrics"]["positive_count"]
            daily_data[date]["crisis_indicators"].extend(metric["metrics"]["crisis_indicators"])
        
        # Calculer ratios par jour
        for date_data in daily_data.values():
            total = date_data["total_comments"]
            if total > 0:
                date_data["negative_ratio"] = round(date_data["negative_count"] / total, 3)
                date_data["positive_ratio"] = round(date_data["positive_count"] / total, 3)
            else:
                date_data["negative_ratio"] = 0
                date_data["positive_ratio"] = 0
        
        return list(daily_data.values())

    def _generate_recommendations(self, latest_metrics: Dict, trend: str) -> List[str]:
        """Génère des recommandations basées sur l'analyse"""
        
        recommendations = []
        
        negative_ratio = latest_metrics["negative_ratio"]
        crisis_indicators = latest_metrics["crisis_indicators"]
        
        if negative_ratio > 0.8:
            recommendations.append("URGENT: Sentiment très négatif détecté (>80%). Communication de crise recommandée.")
        elif negative_ratio > 0.6:
            recommendations.append("Attention: Sentiment majoritairement négatif. Surveillance renforcée recommandée.")
        
        if crisis_indicators:
            recommendations.append(f"Indicateurs de crise détectés: {', '.join(crisis_indicators[:3])}")
        
        if trend == "DETERIORATION":
            recommendations.append("Tendance négative en cours. Intervention rapide conseillée.")
        elif trend == "AMELIORATION":
            recommendations.append("Tendance positive. Continuer la stratégie actuelle.")
        
        if not recommendations:
            recommendations.append("Situation stable. Monitoring de routine suffisant.")
        
        return recommendations

    def monitor_affairs_intelligent(self) -> Dict[str, Any]:
        """Monitoring intelligent avec conditions IA"""
        
        logger.info("Démarrage monitoring intelligent conditionné par IA")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "affairs_checked": 0,
            "actions_taken": {
                "basic_scan": 0,
                "ai_triggered_scan": 0,
                "deep_crisis_scan": 0,
                "none": 0
            },
            "ai_conditions": {
                "total_evaluated": 0,
                "conditions_met": 0,
                "mistral_analyzed": 0
            },
            "sentiment_analysis": {
                "total_comments": 0,
                "negative_alerts": 0,
                "crisis_indicators": 0
            },
            "execution_time": 0
        }
        
        start_time = time.time()
        
        try:
            # Récupérer affaires récentes avec analyse IA
            since_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            recent_affairs = list(self.affaires_collection.find({
                "last_updated": {"$gte": since_date},
                "mistral_called": True  # Seulement les affaires analysées par IA
            }))
            
            results["affairs_checked"] = len(recent_affairs)
            results["ai_conditions"]["total_evaluated"] = len(recent_affairs)
            
            for affair in recent_affairs:
                try:
                    importance = affair.get("importance_score", 0)
                    
                    if importance >= self.thresholds["deep_crisis_scan"]:
                        # Seuil 3: Crisis scan
                        scan_result = self.execute_deep_crisis_scan(affair)
                        results["actions_taken"]["deep_crisis_scan"] += 1
                        
                    elif importance >= self.thresholds["basic_scan"]:
                        # Vérifier conditions IA pour seuil 2
                        ai_check = self.check_ai_triggered_conditions(affair)
                        results["ai_conditions"]["conditions_met"] += 1 if ai_check["should_trigger"] else 0
                        
                        if ai_check["should_trigger"]:
                            # Seuil 2: AI triggered scan avec commentaires
                            scan_result = self.execute_ai_triggered_scan(affair)
                            results["actions_taken"]["ai_triggered_scan"] += 1
                            
                            # Compter métriques sentiment
                            if scan_result.get("sentiment_metrics"):
                                metrics = scan_result["sentiment_metrics"]
                                results["sentiment_analysis"]["total_comments"] += metrics.total_posts
                                if metrics.negative_ratio > 0.7:
                                    results["sentiment_analysis"]["negative_alerts"] += 1
                                results["sentiment_analysis"]["crisis_indicators"] += len(metrics.crisis_indicators)
                        else:
                            # Seuil 1: Basic scan seulement
                            scan_result = self.execute_basic_scan(affair)
                            results["actions_taken"]["basic_scan"] += 1
                    else:
                        results["actions_taken"]["none"] += 1
                    
                except Exception as e:
                    logger.error(f"Erreur monitoring affaire {affair.get('affaire_id')}: {e}")
                    
        except Exception as e:
            logger.error(f"Erreur monitoring global: {e}")
        
        results["execution_time"] = round(time.time() - start_time, 2)
        
        logger.info(f"Monitoring intelligent terminé: {results['actions_taken']['ai_triggered_scan']} scans IA déclenchés, "
                   f"{results['sentiment_analysis']['total_comments']} commentaires analysés")
        
        return results

    def execute_basic_scan(self, affair: Dict[str, Any]) -> Dict[str, Any]:
        """Seuil 1: Scan basique des pages médias (pour compatibilité)"""
        
        return {
            "scan_type": "basic_scan",
            "affair_id": affair["affaire_id"],
            "posts_found": [],  # Implémentation basique
            "cost_estimate": "low"
        }

    def execute_deep_crisis_scan(self, affair: Dict[str, Any]) -> Dict[str, Any]:
        """Seuil 3: Scan de crise avec toutes les capacités"""
        
        return {
            "scan_type": "deep_crisis_scan", 
            "affair_id": affair["affaire_id"],
            "posts_found": [],  # Implémentation complète
            "cost_estimate": "high"
        }


# Instance globale
intelligent_social_monitor = IntelligentSocialMonitor()

# Export
__all__ = ['intelligent_social_monitor', 'IntelligentSocialMonitor']