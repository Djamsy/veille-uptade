"""
Service d'alertes Telegram automatiques pour la veille média Guadeloupe
Surveille les mentions "Guy Losbar" et les tâches en cours
Envoie des notifications instantanées avec formatage riche
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from telegram import Bot
from telegram.constants import ParseMode
from pymongo import MongoClient
import re
import json
import threading
import time

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramAlertsService:
    def __init__(self):
        # Configuration Telegram
        self.telegram_token = None  # À configurer via l'API
        self.bot = None
        self.default_chat_id = None  # Chat ID de l'utilisateur principal
        
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            
            # Collections
            self.articles_collection = self.db.articles_guadeloupe
            self.social_collection = self.db.social_media_posts
            self.transcriptions_collection = self.db.radio_transcriptions
            self.alerts_collection = self.db.telegram_alerts
            self.alerts_config_collection = self.db.alerts_config
            
            logger.info("✅ Connexion MongoDB réussie pour alertes Telegram")
        except Exception as e:
            logger.error(f"❌ Erreur MongoDB: {e}")
        
        # Configuration étendue des mots-clés surveillés
        self.monitored_keywords = [
            # GÉNÉRIQUES INSTITUTIONNELS
            "Conseil Départemental Guadeloupe", "Département Guadeloupe", "CD971", "cd971",
            "Institution Guadeloupe", "Collectivité territoriale Guadeloupe",
            "Président Conseil Départemental", "Assemblée départementale Guadeloupe",
            "Élus départementaux Guadeloupe", "Session plénière Conseil Départemental",
            
            # PERSONNALITÉS POLITIQUES
            "Guy Losbar", "Losbar", "guy losbar", "Jean-Philippe COURTOIS", "COURTOIS",
            "jean-philippe courtois", "Majorité départementale Guadeloupe",
            
            # GOUVERNANCE ET DÉCISIONS
            "Évolution institutionnelle Guadeloupe", "Congrès des élus Guadeloupe",
            "Schéma départemental", "Décision du Conseil Départemental",
            "Budget départemental Guadeloupe",
            
            # DOMAINES D'ACTION SOCIALE
            "Action sociale Guadeloupe", "Aide sociale à l'enfance Guadeloupe",
            "BRSA Guadeloupe", "PMI Guadeloupe", "Personnes âgées Guadeloupe",
            "Insertion professionnelle Guadeloupe",
            
            # INFRASTRUCTURES ET SERVICES
            "Routes départementales Guadeloupe", "Collèges Guadeloupe",
            "Culture départementale Guadeloupe", "Sport départemental Guadeloupe",
            "Environnement Conseil Départemental", "Tourisme et patrimoine Guadeloupe",
            "Aménagement du territoire Guadeloupe",
            
            # PUBLICS CIBLES
            "Jeunesse Guadeloupe", "Séniors Guadeloupe", "Publics fragiles Guadeloupe",
            "Personnes en situation de handicap Guadeloupe",
            "Familles monoparentales Guadeloupe",
            
            # DISPOSITIFS SPÉCIFIQUES
            "Dispositif stArt Guadeloupe", "Koudmen Jeunes", "Village Départemental",
            "Maison Départementale des Solidarités", "Plan santé solidarité Guadeloupe",
            "Dispositif d'insertion BRSA", "Plan de résilience économique Guadeloupe",
            
            # STRUCTURES DÉPARTEMENTALES
            "Maison Départementale des Personnes Handicapées", "MDPH Guadeloupe",
            "Archives départementales Guadeloupe", "Médiathèques départementales",
            "EHPAD départementaux", "Services sociaux départementaux",
            
            # ÉVÉNEMENTS ET COMMUNICATION
            "Grand Forum Citoyen Guadeloupe", "Conférence de presse Conseil Départemental",
            "Communiqué Conseil Départemental", "Evénement institutionnel Guadeloupe",
            "Conseil de surveillance CHU Guadeloupe", "Visite de terrain Guy Losbar",
            "Conseil départemental en action"
        ]
        
        # Dernière vérification pour éviter les doublons
        self.last_check_time = datetime.now() - timedelta(minutes=30)
        
        # Thread de surveillance actif
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Statut des tâches surveillées
        self.monitored_tasks = {
            'transcription_radio': {'status': 'unknown', 'last_update': None},
            'scraping_articles': {'status': 'unknown', 'last_update': None},
            'scraping_social': {'status': 'unknown', 'last_update': None},
            'gpt_analysis': {'status': 'unknown', 'last_update': None}
        }

    def configure_telegram(self, token: str, chat_id: int):
        """Configurer le bot Telegram avec token et chat ID"""
        try:
            self.telegram_token = token
            self.default_chat_id = chat_id
            self.bot = Bot(token=token)
            
            # Sauvegarder la configuration
            self.alerts_config_collection.update_one(
                {'type': 'telegram_config'},
                {
                    '$set': {
                        'token': token,
                        'default_chat_id': chat_id,
                        'configured_at': datetime.now().isoformat(),
                        'status': 'active'
                    }
                },
                upsert=True
            )
            
            logger.info(f"✅ Bot Telegram configuré pour chat_id: {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur configuration Telegram: {e}")
            return False

    def load_config(self):
        """Charger la configuration depuis MongoDB"""
        try:
            config = self.alerts_config_collection.find_one({'type': 'telegram_config'})
            if config and config.get('status') == 'active':
                self.telegram_token = config.get('token')
                self.default_chat_id = config.get('default_chat_id')
                self.bot = Bot(token=self.telegram_token)
                logger.info(f"✅ Configuration Telegram chargée")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Erreur chargement configuration: {e}")
            return False

    def escape_markdown_v2(self, text: str) -> str:
        """Échapper les caractères spéciaux pour MarkdownV2"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            escaped_char = '\\' + char
            text = text.replace(char, escaped_char)
        return text

    async def send_alert(self, message: str, chat_id: int = None, parse_mode: str = "MarkdownV2"):
        """Envoyer une alerte Telegram"""
        if not self.bot:
            if not self.load_config():
                logger.error("❌ Bot Telegram non configuré")
                return False
        
        try:
            target_chat_id = chat_id or self.default_chat_id
            if not target_chat_id:
                logger.error("❌ Aucun chat_id configuré")
                return False
            
            # Échapper le message si nécessaire
            if parse_mode == "MarkdownV2":
                message = self.escape_markdown_v2(message)
            
            # Envoyer le message
            await self.bot.send_message(
                chat_id=target_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            
            # Logger l'alerte
            self.alerts_collection.insert_one({
                'chat_id': target_chat_id,
                'message': message,
                'sent_at': datetime.now().isoformat(),
                'status': 'sent'
            })
            
            logger.info(f"✅ Alerte Telegram envoyée à {target_chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi alerte Telegram: {e}")
            self.alerts_collection.insert_one({
                'chat_id': target_chat_id,
                'message': message,
                'sent_at': datetime.now().isoformat(),
                'status': 'failed',
                'error': str(e)
            })
            return False

    def send_alert_sync(self, message: str, chat_id: int = None):
        """Version synchrone pour envoyer une alerte"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si on est déjà dans une boucle async, créer une nouvelle boucle
                asyncio.run_coroutine_threadsafe(
                    self.send_alert(message, chat_id), loop
                ).result(timeout=10)
            else:
                asyncio.run(self.send_alert(message, chat_id))
            return True
        except Exception as e:
            logger.error(f"❌ Erreur envoi alerte sync: {e}")
            return False

    def check_guy_losbar_mentions(self) -> List[Dict]:
        """Vérifier les nouvelles mentions de Guy Losbar"""
        try:
            # Vérifier depuis la dernière fois
            since_time = self.last_check_time.isoformat()
            
            new_mentions = []
            
            # 1. Vérifier dans les articles
            articles_with_mentions = list(self.articles_collection.find({
                'scraped_at': {'$gte': since_time},
                '$or': [
                    {'title': {'$regex': r'guy losbar|losbar', '$options': 'i'}},
                    {'content': {'$regex': r'guy losbar|losbar', '$options': 'i'}}
                ]
            }))
            
            for article in articles_with_mentions:
                new_mentions.append({
                    'type': 'article',
                    'source': article.get('source', ''),
                    'title': article.get('title', ''),
                    'url': article.get('url', ''),
                    'found_at': article.get('scraped_at', ''),
                    'platform': 'presse'
                })
            
            # 2. Vérifier dans les réseaux sociaux
            social_with_mentions = list(self.social_collection.find({
                'scraped_at': {'$gte': since_time},
                'content': {'$regex': r'guy losbar|losbar', '$options': 'i'}
            }))
            
            for post in social_with_mentions:
                content = post.get('content', '')
                truncated_content = content[:200] + '...' if len(content) > 200 else content
                
                new_mentions.append({
                    'type': 'social_post',
                    'platform': post.get('platform', 'social'),
                    'author': post.get('author', ''),
                    'content': truncated_content,
                    'url': post.get('url', ''),
                    'found_at': post.get('scraped_at', ''),
                    'engagement': post.get('engagement', {}).get('total', 0)
                })
            
            # 3. Vérifier dans les transcriptions radio
            transcriptions_with_mentions = list(self.transcriptions_collection.find({
                'captured_at': {'$gte': since_time},
                '$or': [
                    {'transcription': {'$regex': r'guy losbar|losbar', '$options': 'i'}},
                    {'gpt_analysis': {'$regex': r'guy losbar|losbar', '$options': 'i'}}
                ]
            }))
            
            for transcription in transcriptions_with_mentions:
                gpt_content = transcription.get('gpt_analysis', '')
                truncated_gpt = gpt_content[:200] + '...' if len(gpt_content) > 200 else gpt_content
                
                new_mentions.append({
                    'type': 'radio_transcription',
                    'section': transcription.get('section', ''),
                    'content': truncated_gpt,
                    'found_at': transcription.get('captured_at', ''),
                    'platform': 'radio'
                })
            
            logger.info(f"🔍 Vérification Guy Losbar: {len(new_mentions)} nouvelles mentions trouvées")
            return new_mentions
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification mentions Guy Losbar: {e}")
            return []

    def check_task_status_changes(self) -> List[Dict]:
        """Vérifier les changements de statut des tâches"""
        try:
            status_changes = []
            
            # 1. Statut transcription radio
            try:
                latest_transcription = self.transcriptions_collection.find_one(
                    {}, sort=[('captured_at', -1)]
                )
                if latest_transcription:
                    current_status = latest_transcription.get('status', 'unknown')
                    last_known = self.monitored_tasks['transcription_radio']['status']
                    
                    if current_status != last_known:
                        status_changes.append({
                            'task': 'transcription_radio',
                            'old_status': last_known,
                            'new_status': current_status,
                            'section': latest_transcription.get('section', ''),
                            'timestamp': latest_transcription.get('captured_at', '')
                        })
                        self.monitored_tasks['transcription_radio']['status'] = current_status
                        self.monitored_tasks['transcription_radio']['last_update'] = datetime.now()
            except Exception as e:
                logger.warning(f"Erreur vérification statut transcription: {e}")
            
            # 2. Vérifier scraping articles (basé sur la dernière activité)
            try:
                recent_articles = self.articles_collection.count_documents({
                    'scraped_at': {'$gte': (datetime.now() - timedelta(hours=2)).isoformat()}
                })
                
                current_scraping_status = 'active' if recent_articles > 0 else 'inactive'
                last_known_scraping = self.monitored_tasks['scraping_articles']['status']
                
                if current_scraping_status != last_known_scraping:
                    status_changes.append({
                        'task': 'scraping_articles',
                        'old_status': last_known_scraping,
                        'new_status': current_scraping_status,
                        'articles_count': recent_articles,
                        'timestamp': datetime.now().isoformat()
                    })
                    self.monitored_tasks['scraping_articles']['status'] = current_scraping_status
                    self.monitored_tasks['scraping_articles']['last_update'] = datetime.now()
            except Exception as e:
                logger.warning(f"Erreur vérification scraping articles: {e}")
            
            # 3. Vérifier scraping réseaux sociaux
            try:
                recent_social = self.social_collection.count_documents({
                    'scraped_at': {'$gte': (datetime.now() - timedelta(hours=2)).isoformat()}
                })
                
                current_social_status = 'active' if recent_social > 0 else 'inactive'
                last_known_social = self.monitored_tasks['scraping_social']['status']
                
                if current_social_status != last_known_social:
                    status_changes.append({
                        'task': 'scraping_social',
                        'old_status': last_known_social,
                        'new_status': current_social_status,
                        'posts_count': recent_social,
                        'timestamp': datetime.now().isoformat()
                    })
                    self.monitored_tasks['scraping_social']['status'] = current_social_status
                    self.monitored_tasks['scraping_social']['last_update'] = datetime.now()
            except Exception as e:
                logger.warning(f"Erreur vérification scraping social: {e}")
            
            logger.info(f"📊 Vérification tâches: {len(status_changes)} changements de statut détectés")
            return status_changes
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification changements tâches: {e}")
            return []

    def format_guy_losbar_alert(self, mentions: List[Dict]) -> str:
        """Formater une alerte pour les mentions de Guy Losbar"""
        if not mentions:
            return ""
        
        alert_parts = ["🚨 *ALERTE Guy Losbar*", ""]
        
        for mention in mentions:
            if mention['type'] == 'article':
                source = mention['source']
                title = mention['title']
                url = mention['url']
                
                alert_parts.append(f"📰 *Article* - {source}")
                title_display = title[:100] + "..." if len(title) > 100 else title
                alert_parts.append(f"📝 {title_display}")
                if url:
                    alert_parts.append(f"🔗 [Lire l'article]({url})")
                
            elif mention['type'] == 'social_post':
                platform = mention['platform']
                author = mention['author']
                content = mention['content']
                engagement = mention['engagement']
                
                emoji = "🐦" if platform == 'twitter' else "📱"
                alert_parts.append(f"{emoji} *{platform.title()}* - @{author}")
                alert_parts.append(f"💬 {content}")
                if engagement > 0:
                    alert_parts.append(f"📊 {engagement} interactions")
                
            elif mention['type'] == 'radio_transcription':
                section = mention['section']
                content = mention['content']
                
                alert_parts.append(f"📻 *Radio* - {section}")
                alert_parts.append(f"🎙️ {content}")
            
            alert_parts.append("")  # Ligne vide entre mentions
        
        current_time = datetime.now().strftime('%d/%m/%Y à %H:%M')
        alert_parts.append(f"⏰ Détecté le {current_time}")
        
        return "\n".join(alert_parts)

    def format_task_status_alert(self, changes: List[Dict]) -> str:
        """Formater une alerte pour les changements de statut des tâches"""
        if not changes:
            return ""
        
        alert_parts = ["⚙️ *STATUT DES TÂCHES*", ""]
        
        status_emojis = {
            'active': '✅',
            'inactive': '⏸️',
            'error': '❌',
            'completed': '✅',
            'in_progress': '🔄',
            'unknown': '❓'
        }
        
        task_names = {
            'transcription_radio': 'Transcription Radio',
            'scraping_articles': 'Scraping Articles',
            'scraping_social': 'Scraping Réseaux Sociaux',
            'gpt_analysis': 'Analyse GPT'
        }
        
        for change in changes:
            task_name = task_names.get(change['task'], change['task'])
            old_emoji = status_emojis.get(change['old_status'], '❓')
            new_emoji = status_emojis.get(change['new_status'], '❓')
            new_status = change['new_status']
            
            alert_parts.append(f"🔄 *{task_name}*")
            alert_parts.append(f"   {old_emoji} → {new_emoji} {new_status}")
            
            # Informations spécifiques par tâche
            if change['task'] == 'scraping_articles' and 'articles_count' in change:
                articles_count = change['articles_count']
                alert_parts.append(f"   📊 {articles_count} articles récents")
            elif change['task'] == 'scraping_social' and 'posts_count' in change:
                posts_count = change['posts_count']
                alert_parts.append(f"   📊 {posts_count} posts récents")
            elif change['task'] == 'transcription_radio' and 'section' in change:
                section = change['section']
                alert_parts.append(f"   📻 Section: {section}")
            
            alert_parts.append("")
        
        current_time = datetime.now().strftime('%d/%m/%Y à %H:%M')
        alert_parts.append(f"⏰ Mis à jour le {current_time}")
        
        return "\n".join(alert_parts)

    def start_monitoring(self):
        """Démarrer la surveillance automatique"""
        if self.monitoring_active:
            logger.info("⚠️ Surveillance déjà active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        logger.info("🚀 Surveillance automatique démarrée")

    def stop_monitoring(self):
        """Arrêter la surveillance automatique"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("⏹️ Surveillance automatique arrêtée")

    def _monitoring_loop(self):
        """Boucle principale de surveillance"""
        while self.monitoring_active:
            try:
                # Vérifier les mentions Guy Losbar
                guy_losbar_mentions = self.check_guy_losbar_mentions()
                if guy_losbar_mentions:
                    alert_message = self.format_guy_losbar_alert(guy_losbar_mentions)
                    if alert_message:
                        self.send_alert_sync(alert_message)
                
                # Vérifier les changements de statut des tâches
                task_changes = self.check_task_status_changes()
                if task_changes:
                    task_alert = self.format_task_status_alert(task_changes)
                    if task_alert:
                        self.send_alert_sync(task_alert)
                
                # Mettre à jour la dernière vérification
                self.last_check_time = datetime.now()
                
                # Attendre 2 minutes avant la prochaine vérification (plus fréquent pour le radio)
                time.sleep(120)  # 2 minutes au lieu de 5
                
            except Exception as e:
                logger.error(f"❌ Erreur dans la boucle de surveillance: {e}")
                time.sleep(60)  # Attendre 1 minute en cas d'erreur

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Obtenir le statut de la surveillance"""
        return {
            'monitoring_active': self.monitoring_active,
            'bot_configured': self.bot is not None,
            'default_chat_id': self.default_chat_id,
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'monitored_tasks': self.monitored_tasks,
            'monitored_keywords': self.monitored_keywords
        }

    def send_test_alert(self, chat_id: int = None) -> bool:
        """Envoyer une alerte de test"""
        current_time = datetime.now().strftime('%d/%m/%Y à %H:%M')
        
        test_message = f"""🧪 *TEST ALERTE TELEGRAM*

✅ Bot Telegram configuré
✅ Surveillance active
✅ Mots-clés: Guy Losbar, CD971
✅ Tâches surveillées: 4

⏰ Test envoyé le {current_time}

🎯 Vous recevrez des alertes pour:
• Nouvelles mentions Guy Losbar
• Changements statut des tâches"""
        
        return self.send_alert_sync(test_message, chat_id)

# Instance globale
telegram_alerts = TelegramAlertsService()

if __name__ == "__main__":
    # Test du service
    print("=== Test du service d'alertes Telegram ===")
    
    # Charger la configuration si disponible
    if telegram_alerts.load_config():
        print("✅ Configuration chargée")
        
        # Test d'alerte
        success = telegram_alerts.send_test_alert()
        print(f"Test alerte: {'✅ Envoyée' if success else '❌ Échec'}")
        
        # Démarrer la surveillance
        telegram_alerts.start_monitoring()
        print("🚀 Surveillance démarrée")
        
    else:
        print("⚠️ Configuration Telegram requise")
        print("Utilisez l'endpoint /api/telegram/configure pour configurer le bot")