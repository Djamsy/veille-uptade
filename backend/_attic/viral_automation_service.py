# backend/viral_automation_service.py
"""
Service d'automatisation complète de l'analyse virale
- Analyse automatique de TOUS les nouveaux articles scrapés
- Analyse automatique de TOUTES les nouvelles transcriptions radio
- Système d'alertes automatiques basé sur les seuils
- Monitoring temps réel des tendances virales
- Intégration avec Telegram pour alertes
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

class ViralAutomationService:
    """Service d'automatisation de l'analyse virale"""
    
    def __init__(self, db, viral_detection_service, viral_predictor_service, 
                 media_noise_service, sentiment_analysis_service, telegram_alerts=None):
        self.db = db
        self.viral_detection_service = viral_detection_service
        self.viral_predictor_service = viral_predictor_service
        self.media_noise_service = media_noise_service
        self.sentiment_analysis_service = sentiment_analysis_service
        self.telegram_alerts = telegram_alerts
        
        # Seuils d'alerte
        self.alert_thresholds = {
            'critical': 0.8,    # Alerte critique
            'high': 0.6,        # Alerte élevée
            'medium': 0.4       # Surveillance renforcée
        }
        
        # Cache des contenus déjà analysés (éviter les doublons)
        self.analyzed_cache = set()
    
    async def process_new_articles(self):
        """Analyse automatique des nouveaux articles"""
        try:
            # Récupérer les articles des dernières 24h non encore analysés pour la viralité
            yesterday = datetime.utcnow() - timedelta(days=1)
            
            new_articles = list(
                self.db.articles_guadeloupe.find({
                    "scraped_at": {"$gte": yesterday},
                    "viral_analysis": {"$exists": False}  # Pas encore analysé
                }).limit(50)  # Traiter par batches
            )
            
            logger.info(f"🔍 Analyse virale de {len(new_articles)} nouveaux articles")
            
            for article in new_articles:
                await self._analyze_single_content(article, content_type="article")
                
            return len(new_articles)
            
        except Exception as e:
            logger.error(f"Erreur analyse automatique articles: {e}")
            return 0
    
    async def process_new_transcriptions(self):
        """Analyse automatique des nouvelles transcriptions radio"""
        try:
            # Récupérer les transcriptions des dernières 24h non analysées
            yesterday = datetime.utcnow() - timedelta(days=1)
            
            new_transcriptions = list(
                self.db.radio_transcriptions.find({
                    "captured_at": {"$gte": yesterday},
                    "viral_analysis": {"$exists": False}
                }).limit(50)
            )
            
            logger.info(f"📻 Analyse virale de {len(new_transcriptions)} nouvelles transcriptions")
            
            for transcription in new_transcriptions:
                await self._analyze_single_content(transcription, content_type="transcription")
                
            return len(new_transcriptions)
            
        except Exception as e:
            logger.error(f"Erreur analyse automatique transcriptions: {e}")
            return 0
    
    async def _analyze_single_content(self, content_doc: Dict[str, Any], content_type: str):
        """Analyse virale d'un contenu unique"""
        try:
            # Extraire le texte selon le type
            if content_type == "article":
                text = f"{content_doc.get('title', '')} {content_doc.get('content', '')}"
                content_id = str(content_doc.get('_id'))
                collection = self.db.articles_guadeloupe
            else:  # transcription
                text = content_doc.get('transcription_text', '') or content_doc.get('content', '')
                content_id = str(content_doc.get('_id'))
                collection = self.db.radio_transcriptions
            
            if not text or len(text.strip()) < 20:
                return
            
            # Éviter les doublons
            cache_key = f"{content_type}:{content_id}"
            if cache_key in self.analyzed_cache:
                return
            
            # Analyse virale complète
            analysis_result = await self._perform_viral_analysis(text, content_doc)
            
            # Sauvegarder les résultats dans le document
            update_data = {
                "viral_analysis": analysis_result,
                "viral_score": analysis_result.get("global_viral_score", 0),
                "viral_level": analysis_result.get("viral_level", "faible"),
                "analyzed_at": datetime.utcnow()
            }
            
            collection.update_one(
                {"_id": content_doc["_id"]},
                {"$set": update_data}
            )
            
            # Vérifier les seuils d'alerte
            await self._check_viral_alerts(analysis_result, content_doc, content_type)
            
            # Ajouter au cache
            self.analyzed_cache.add(cache_key)
            
            # Nettoyer le cache si trop gros
            if len(self.analyzed_cache) > 1000:
                self.analyzed_cache.clear()
            
            logger.debug(f"✅ Analysé {content_type} {content_id}: score {analysis_result.get('global_viral_score', 0):.3f}")
            
        except Exception as e:
            logger.error(f"Erreur analyse {content_type}: {e}")
    
    async def _perform_viral_analysis(self, text: str, content_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Effectue l'analyse virale complète"""
        results = {}
        
        # 1. Détection virale de base
        if self.viral_detection_service:
            try:
                viral_score = self.viral_detection_service.calculate_viral_score({"content": text})
                results["viral_detection"] = {
                    "score": viral_score,
                    "level": "high" if viral_score > 0.7 else "medium" if viral_score > 0.4 else "low"
                }
            except Exception as e:
                logger.warning(f"Erreur viral detection: {e}")
        
        # 2. Analyse de sentiment
        if self.sentiment_analysis_service:
            try:
                sentiment = self.sentiment_analysis_service(text)
                results["sentiment"] = sentiment
            except Exception as e:
                logger.warning(f"Erreur sentiment analysis: {e}")
        
        # 3. Bruit médiatique
        if self.media_noise_service:
            try:
                noise_score = self.media_noise_service.calculate_noise_level(text)
                results["media_noise"] = {
                    "score": noise_score,
                    "level": "high" if noise_score > 0.7 else "medium" if noise_score > 0.4 else "low"
                }
            except Exception as e:
                logger.warning(f"Erreur media noise: {e}")
        
        # 4. Prédiction d'escalade
        if self.viral_predictor_service:
            try:
                prediction = self.viral_predictor_service.predict_escalation({
                    "content": text,
                    "source": content_doc.get("source", ""),
                    "title": content_doc.get("title", "")
                })
                results["escalation_prediction"] = prediction
            except Exception as e:
                logger.warning(f"Erreur escalation prediction: {e}")
        
        # 5. Score global
        global_score = self._calculate_global_score(results)
        results["global_viral_score"] = global_score
        results["viral_level"] = self._get_viral_level(global_score)
        results["analyzed_at"] = datetime.utcnow().isoformat()
        
        return results
    
    def _calculate_global_score(self, results: Dict[str, Any]) -> float:
        """Calcule le score viral global"""
        weights = {"viral_detection": 0.4, "sentiment": 0.3, "media_noise": 0.3}
        global_score = 0
        
        if "viral_detection" in results and "score" in results["viral_detection"]:
            global_score += results["viral_detection"]["score"] * weights["viral_detection"]
        
        if "sentiment" in results and results["sentiment"].get("compound", 0) != 0:
            sentiment_intensity = abs(results["sentiment"]["compound"])
            global_score += sentiment_intensity * weights["sentiment"]
        
        if "media_noise" in results and "score" in results["media_noise"]:
            global_score += results["media_noise"]["score"] * weights["media_noise"]
        
        return min(global_score, 1.0)
    
    def _get_viral_level(self, score: float) -> str:
        """Détermine le niveau viral"""
        if score > 0.8:
            return "très_élevé"
        elif score > 0.6:
            return "élevé"
        elif score > 0.4:
            return "moyen"
        else:
            return "faible"
    
    async def _check_viral_alerts(self, analysis: Dict[str, Any], content_doc: Dict[str, Any], content_type: str):
        """Vérifie les seuils d'alerte et envoie des notifications"""
        try:
            viral_score = analysis.get("global_viral_score", 0)
            
            if viral_score >= self.alert_thresholds['critical']:
                await self._send_critical_alert(analysis, content_doc, content_type)
            elif viral_score >= self.alert_thresholds['high']:
                await self._send_high_alert(analysis, content_doc, content_type)
            elif viral_score >= self.alert_thresholds['medium']:
                await self._send_medium_alert(analysis, content_doc, content_type)
                
        except Exception as e:
            logger.error(f"Erreur envoi alertes: {e}")
    
    async def _send_critical_alert(self, analysis: Dict[str, Any], content_doc: Dict[str, Any], content_type: str):
        """Alerte critique - Risque viral très élevé"""
        score = analysis.get("global_viral_score", 0)
        title = content_doc.get("title", "")[:100]
        source = content_doc.get("source", "Inconnu")
        
        message = f"""🚨 ALERTE VIRALE CRITIQUE 🚨

📊 Score viral: {score:.1%} (CRITIQUE)
📝 {content_type.title()}: {title}
📰 Source: {source}
⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}

🎯 ACTIONS REQUISES:
• Cellule de crise immédiate
• Surveillance renforcée
• Préparation réponse officielle

#AlerteVirale #Critique #CD971"""
        
        if self.telegram_alerts:
            self.telegram_alerts.send_alert_sync(message)
        
        # Log en base pour traçabilité
        self._log_viral_alert("CRITICAL", analysis, content_doc, content_type)
    
    async def _send_high_alert(self, analysis: Dict[str, Any], content_doc: Dict[str, Any], content_type: str):
        """Alerte élevée - Surveillance renforcée"""
        score = analysis.get("global_viral_score", 0)
        title = content_doc.get("title", "")[:100]
        source = content_doc.get("source", "Inconnu")
        
        message = f"""⚠️ ALERTE VIRALE ÉLEVÉE

📊 Score viral: {score:.1%} (ÉLEVÉ)
📝 {content_type.title()}: {title}
📰 Source: {source}
⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}

📈 SURVEILLANCE RENFORCÉE
• Monitoring actif requis
• Préparation éléments de réponse

#AlerteVirale #Élevé #Surveillance"""
        
        if self.telegram_alerts:
            self.telegram_alerts.send_alert_sync(message)
        
        self._log_viral_alert("HIGH", analysis, content_doc, content_type)
    
    async def _send_medium_alert(self, analysis: Dict[str, Any], content_doc: Dict[str, Any], content_type: str):
        """Alerte modérée - Information"""
        score = analysis.get("global_viral_score", 0)
        title = content_doc.get("title", "")[:100]
        
        message = f"""📊 Potentiel viral détecté: {score:.1%}
📝 {title}
📍 Surveillance normale maintenue"""
        
        if self.telegram_alerts:
            self.telegram_alerts.send_alert_sync(message)
        
        self._log_viral_alert("MEDIUM", analysis, content_doc, content_type)
    
    def _log_viral_alert(self, level: str, analysis: Dict[str, Any], content_doc: Dict[str, Any], content_type: str):
        """Log des alertes virales en base"""
        try:
            alert_doc = {
                "alert_level": level,
                "content_type": content_type,
                "content_id": str(content_doc.get("_id")),
                "viral_score": analysis.get("global_viral_score", 0),
                "viral_analysis": analysis,
                "content_title": content_doc.get("title", ""),
                "content_source": content_doc.get("source", ""),
                "created_at": datetime.utcnow(),
                "status": "new"
            }
            
            self.db.viral_alerts.insert_one(alert_doc)
            
        except Exception as e:
            logger.error(f"Erreur log alerte: {e}")
    
    async def get_trending_content(self, hours: int = 24, limit: int = 20) -> List[Dict[str, Any]]:
        """Récupère le contenu viral trending"""
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            # Articles viraux récents
            viral_articles = list(
                self.db.articles_guadeloupe.find({
                    "analyzed_at": {"$gte": since},
                    "viral_score": {"$gte": 0.4}
                }).sort("viral_score", -1).limit(limit)
            )
            
            # Transcriptions virales récentes
            viral_transcriptions = list(
                self.db.radio_transcriptions.find({
                    "analyzed_at": {"$gte": since},
                    "viral_score": {"$gte": 0.4}
                }).sort("viral_score", -1).limit(limit)
            )
            
            # Combiner et trier
            all_content = []
            
            for article in viral_articles:
                all_content.append({
                    "type": "article",
                    "id": str(article["_id"]),
                    "title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "viral_score": article.get("viral_score", 0),
                    "viral_level": article.get("viral_level", ""),
                    "analyzed_at": article.get("analyzed_at"),
                    "url": article.get("url", "")
                })
            
            for trans in viral_transcriptions:
                all_content.append({
                    "type": "transcription",
                    "id": str(trans["_id"]),
                    "title": f"Radio {trans.get('stream_name', '')}",
                    "source": trans.get("stream_name", "Radio"),
                    "viral_score": trans.get("viral_score", 0),
                    "viral_level": trans.get("viral_level", ""),
                    "analyzed_at": trans.get("analyzed_at"),
                    "content_preview": trans.get("transcription_text", "")[:200] + "..."
                })
            
            # Trier par score viral
            all_content.sort(key=lambda x: x["viral_score"], reverse=True)
            
            return all_content[:limit]
            
        except Exception as e:
            logger.error(f"Erreur trending content: {e}")
            return []
    
    async def get_viral_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Statistiques virales des derniers jours"""
        try:
            since = datetime.utcnow() - timedelta(days=days)
            
            # Stats articles
            article_stats = self.db.articles_guadeloupe.aggregate([
                {"$match": {"analyzed_at": {"$gte": since}}},
                {"$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "avg_viral_score": {"$avg": "$viral_score"},
                    "max_viral_score": {"$max": "$viral_score"},
                    "high_viral": {"$sum": {"$cond": [{"$gte": ["$viral_score", 0.6]}, 1, 0]}},
                    "medium_viral": {"$sum": {"$cond": [{"$and": [{"$gte": ["$viral_score", 0.4]}, {"$lt": ["$viral_score", 0.6]}]}, 1, 0]}}
                }}
            ])
            
            article_data = list(article_stats)
            article_stats_result = article_data[0] if article_data else {}
            
            # Stats alertes
            alert_counts = self.db.viral_alerts.aggregate([
                {"$match": {"created_at": {"$gte": since}}},
                {"$group": {
                    "_id": "$alert_level",
                    "count": {"$sum": 1}
                }}
            ])
            
            alerts_by_level = {item["_id"]: item["count"] for item in alert_counts}
            
            return {
                "period_days": days,
                "articles": {
                    "total_analyzed": article_stats_result.get("total", 0),
                    "avg_viral_score": round(article_stats_result.get("avg_viral_score", 0), 3),
                    "max_viral_score": round(article_stats_result.get("max_viral_score", 0), 3),
                    "high_viral_count": article_stats_result.get("high_viral", 0),
                    "medium_viral_count": article_stats_result.get("medium_viral", 0)
                },
                "alerts": {
                    "critical": alerts_by_level.get("CRITICAL", 0),
                    "high": alerts_by_level.get("HIGH", 0),
                    "medium": alerts_by_level.get("MEDIUM", 0)
                },
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur stats virales: {e}")
            return {}


# ===========================
# INTÉGRATION DANS LE SCHEDULER
# ===========================

# Ajout des jobs automatiques dans scheduler_service.py

async def job_viral_analysis():
    """Job automatique d'analyse virale (toutes les 15 minutes)"""
    global viral_automation_service
    
    if not viral_automation_service:
        logger.warning("Service d'automatisation viral non disponible")
        return
    
    try:
        logger.info("🦠 Analyse virale automatique démarrée")
        
        # Analyser nouveaux articles
        articles_processed = await viral_automation_service.process_new_articles()
        
        # Analyser nouvelles transcriptions
        transcriptions_processed = await viral_automation_service.process_new_transcriptions()
        
        logger.info(f"✅ Analyse virale terminée: {articles_processed} articles, {transcriptions_processed} transcriptions")
        
        # Log du job
        _log_job("viral_analysis", True, f"articles={articles_processed}, transcriptions={transcriptions_processed}")
        
    except Exception as e:
        logger.error(f"Erreur job viral analysis: {e}")
        _log_job("viral_analysis", False, str(e))

# À ajouter dans _ensure_scheduler():
# _scheduler.add_job(job_viral_analysis, CronTrigger(minute="*/15", timezone=TZ), 
#                    id="viral_analysis", replace_existing=True)


# ===========================
# INITIALISATION DU SERVICE
# ===========================

viral_automation_service = None

def initialize_viral_automation(db, viral_detection_service, viral_predictor_service, 
                               media_noise_service, sentiment_analysis_service, telegram_alerts=None):
    """Initialise le service d'automatisation virale"""
    global viral_automation_service
    
    try:
        viral_automation_service = ViralAutomationService(
            db=db,
            viral_detection_service=viral_detection_service,
            viral_predictor_service=viral_predictor_service,
            media_noise_service=media_noise_service,
            sentiment_analysis_service=sentiment_analysis_service,
            telegram_alerts=telegram_alerts
        )
        
        logger.info("🤖 Service d'automatisation virale initialisé")
        return viral_automation_service
        
    except Exception as e:
        logger.error(f"Erreur initialisation automatisation virale: {e}")
        return None
