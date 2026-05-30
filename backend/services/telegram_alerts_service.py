"""
Service d'alertes Telegram automatiques pour la veille média Guadeloupe
Surveille les mentions "Guy Losbar" et les tâches en cours
Envoie des notifications instantanées avec formatage riche
"""
import os
import asyncio
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
try:
    from telegram import Bot
    from telegram.constants import ParseMode
except Exception:  # make telegram optional; we can still send via HTTP
    Bot = None
    class ParseMode:
        HTML = "HTML"
        MARKDOWN_V2 = "MarkdownV2"
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
        # Configuration Telegram (env d'abord, Mongo sinon)
        self.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.bot = None
        if self.telegram_token and self.default_chat_id and Bot is not None:
            try:
                self.bot = Bot(token=self.telegram_token)
                logger.info("✅ Bot Telegram initialisé depuis les variables d'environnement")
            except Exception as e:
                logger.warning(f"⚠️ Impossible d'initialiser Bot (env): {e}")
        
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
            # Si pas de token en env, tenter un chargement Mongo (fallback)
            if not self.telegram_token or not self.default_chat_id:
                try:
                    cfg = self.db.alerts_config.find_one({"type": "telegram_config", "status": "active"})
                    if cfg:
                        self.telegram_token = self.telegram_token or cfg.get("token")
                        self.default_chat_id = self.default_chat_id or cfg.get("default_chat_id")
                        if self.telegram_token and self.default_chat_id and Bot is not None:
                            self.bot = Bot(token=self.telegram_token)
                            logger.info("✅ Configuration Telegram chargée depuis MongoDB")
                except Exception as e:
                    logger.warning(f"⚠️ Fallback Mongo pour Telegram échoué: {e}")
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

        # ── Cache anti-doublons : IDs déjà notifiés ──
        # Empêche de re-notifier les mêmes articles/posts/transcriptions
        self._notified_ids: set = set()
        self._notified_ids_max = 2000  # Taille max du cache

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
        """Configurer le bot Telegram avec token et chat ID (persistance Mongo + mémoire)."""
        try:
            self.telegram_token = token
            self.default_chat_id = str(chat_id)
            if Bot is not None:
                try:
                    self.bot = Bot(token=token)
                except Exception as e:
                    logger.warning(f"⚠️ Bot non initialisé (lib manquante ou erreur): {e}")
            # Sauvegarde Mongo
            self.alerts_config_collection.update_one(
                {"type": "telegram_config"},
                {"$set": {
                    "token": token,
                    "default_chat_id": self.default_chat_id,
                    "configured_at": datetime.now().isoformat(),
                    "status": "active"
                }},
                upsert=True
            )
            logger.info(f"✅ Bot Telegram configuré pour chat_id: {self.default_chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur configuration Telegram: {e}")
            return False

    def load_config(self):
        """Charger la configuration depuis ENV puis MongoDB."""
        # ENV prioritaire
        if self.telegram_token and self.default_chat_id:
            if Bot is not None and self.bot is None:
                try:
                    self.bot = Bot(token=self.telegram_token)
                except Exception as e:
                    logger.warning(f"⚠️ Init Bot depuis ENV échouée: {e}")
            return True
        # Mongo fallback
        try:
            config = self.alerts_config_collection.find_one({"type": "telegram_config", "status": "active"})
            if config:
                self.telegram_token = config.get("token")
                self.default_chat_id = str(config.get("default_chat_id"))
                if Bot is not None:
                    try:
                        self.bot = Bot(token=self.telegram_token)
                    except Exception as e:
                        logger.warning(f"⚠️ Init Bot depuis Mongo échouée: {e}")
                logger.info("✅ Configuration Telegram chargée")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Erreur chargement configuration: {e}")
            return False
    def _send_via_http(self, message: str, chat_id: Optional[str] = None) -> bool:
        token = self.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat = str(chat_id or self.default_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
        if not token or not chat:
            logger.warning("[telegram] Missing token/chat for HTTP send")
            return False
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat, "text": message[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
            r = requests.post(url, json=payload, timeout=10)
            ok = r.ok and r.json().get("ok") is True
            if not ok:
                logger.error("[telegram] HTTP send failed: %s", r.text)
            return ok
        except Exception as e:
            logger.exception("[telegram] HTTP send exception: %s", e)
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
            # tente ENV/Mongo
            if not self.load_config():
                logger.error("❌ Bot Telegram non configuré (fallback HTTP possible)")
                # fallback HTTP direct
                return self._send_via_http(message, chat_id)

        try:
            target_chat_id = chat_id or self.default_chat_id
            if not target_chat_id:
                logger.error("❌ Aucun chat_id configuré")
                return False

            # Utilise HTML par défaut (moins pénible que MarkdownV2)
            if parse_mode == "MarkdownV2":
                parse_mode = ParseMode.HTML
            
            # Envoi via SDK si disponible
            if self.bot is not None:
                await self.bot.send_message(chat_id=target_chat_id, text=message, parse_mode=parse_mode)
                sent_via_sdk = True
            else:
                sent_via_sdk = False

            # Si pas de SDK ou échec SDK, tente HTTP
            if not sent_via_sdk:
                http_ok = self._send_via_http(message, target_chat_id)
                if not http_ok:
                    return False

            # Log to Mongo
            self.alerts_collection.insert_one({
                'chat_id': str(target_chat_id),
                'message': message,
                'sent_at': datetime.now().isoformat(),
                'status': 'sent'
            })
            logger.info(f"✅ Alerte Telegram envoyée à {target_chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur envoi alerte Telegram: {e}")
            self.alerts_collection.insert_one({
                'chat_id': str(chat_id or self.default_chat_id or ''),
                'message': message,
                'sent_at': datetime.now().isoformat(),
                'status': 'failed',
                'error': str(e)
            })
            # Dernier recours HTTP (au cas où)
            try:
                return self._send_via_http(message, chat_id)
            except Exception:
                return False

    def send_alert_sync(self, message: str, chat_id: int = None):
        """Version synchrone pour envoyer une alerte"""
        try:
            # Toujours exécuter dans une nouvelle boucle pour éviter les conflits
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.send_alert(message, chat_id))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"❌ Erreur envoi alerte sync: {e}")
            # Fallback HTTP ultime
            return self._send_via_http(message, chat_id)

    def check_guy_losbar_mentions(self) -> List[Dict]:
        """Vérifier les nouvelles mentions des mots-clés surveillés (Guy Losbar et sujets départementaux)"""
        try:
            # Vérifier depuis la dernière fois
            since_time = self.last_check_time.isoformat()
            
            new_mentions = []
            
            # Créer un pattern regex optimisé pour tous les mots-clés
            keywords_pattern = "|".join([
                re.escape(keyword.lower()) for keyword in self.monitored_keywords
            ])
            
            # 1. Vérifier dans les articles
            articles_with_mentions = list(self.articles_collection.find({
                'scraped_at': {'$gte': since_time},
                '$or': [
                    {'title': {'$regex': keywords_pattern, '$options': 'i'}},
                    {'content': {'$regex': keywords_pattern, '$options': 'i'}}
                ]
            }))
            
            for article in articles_with_mentions:
                # ── Anti-doublon : ignorer si déjà notifié ──
                art_id = str(article.get('_id', ''))
                if art_id in self._notified_ids:
                    continue

                # Identifier quels mots-clés ont été trouvés
                title = article.get('title', '').lower()
                content = article.get('content', '').lower()
                full_text = f"{title} {content}"

                found_keywords = [keyword for keyword in self.monitored_keywords
                                if keyword.lower() in full_text]

                new_mentions.append({
                    'type': 'article',
                    '_id': art_id,
                    'source': article.get('source', ''),
                    'title': article.get('title', ''),
                    'url': article.get('url', ''),
                    'found_at': article.get('scraped_at', ''),
                    'platform': 'presse',
                    'keywords_found': found_keywords,
                    'priority': 'high' if any(k.lower() in ['guy losbar', 'losbar'] for k in found_keywords) else 'medium'
                })
            
            # 2. Vérifier dans les réseaux sociaux
            social_with_mentions = list(self.social_collection.find({
                'scraped_at': {'$gte': since_time},
                'content': {'$regex': keywords_pattern, '$options': 'i'}
            }))
            
            for post in social_with_mentions:
                # ── Anti-doublon ──
                post_id = str(post.get('_id', ''))
                if post_id in self._notified_ids:
                    continue

                content = post.get('content', '').lower()
                found_keywords = [keyword for keyword in self.monitored_keywords
                                if keyword.lower() in content]

                truncated_content = post.get('content', '')
                if len(truncated_content) > 200:
                    truncated_content = truncated_content[:200] + '...'

                new_mentions.append({
                    'type': 'social_post',
                    '_id': post_id,
                    'platform': post.get('platform', 'social'),
                    'author': post.get('author', ''),
                    'content': truncated_content,
                    'url': post.get('url', ''),
                    'found_at': post.get('scraped_at', ''),
                    'engagement': post.get('engagement', {}).get('total', 0),
                    'keywords_found': found_keywords,
                    'priority': 'high' if any(k.lower() in ['guy losbar', 'losbar'] for k in found_keywords) else 'medium'
                })
            
            # 3. Vérifier dans les transcriptions radio
            transcriptions_with_mentions = list(self.transcriptions_collection.find({
                'captured_at': {'$gte': since_time},
                '$or': [
                    {'transcription_text': {'$regex': keywords_pattern, '$options': 'i'}},
                    {'gpt_analysis': {'$regex': keywords_pattern, '$options': 'i'}},
                    {'ai_summary': {'$regex': keywords_pattern, '$options': 'i'}}
                ]
            }))
            
            for transcription in transcriptions_with_mentions:
                # ── Anti-doublon ──
                trans_id = str(transcription.get('_id', ''))
                if trans_id in self._notified_ids:
                    continue

                transcription_text = transcription.get('transcription_text', '')
                gpt_content = transcription.get('gpt_analysis', '') or transcription.get('ai_summary', '')
                full_content = f"{transcription_text} {gpt_content}".lower()

                found_keywords = [keyword for keyword in self.monitored_keywords
                                if keyword.lower() in full_content]

                display_content = gpt_content if gpt_content else transcription_text
                if len(display_content) > 200:
                    display_content = display_content[:200] + '...'

                new_mentions.append({
                    'type': 'radio_transcription',
                    '_id': trans_id,
                    'section': transcription.get('section', ''),
                    'stream_name': transcription.get('stream_name', ''),
                    'content': display_content,
                    'found_at': transcription.get('captured_at', ''),
                    'platform': 'radio',
                    'keywords_found': found_keywords,
                    'priority': 'high' if any(k.lower() in ['guy losbar', 'losbar'] for k in found_keywords) else 'medium'
                })
            
            # Trier par priorité (high d'abord) puis par date
            new_mentions.sort(key=lambda x: (x['priority'] != 'high', x['found_at']), reverse=True)
            
            logger.info(f"🔍 Vérification mots-clés étendus: {len(new_mentions)} nouvelles mentions trouvées")
            if new_mentions:
                high_priority = len([m for m in new_mentions if m['priority'] == 'high'])
                logger.info(f"   📈 Dont {high_priority} mentions haute priorité (Guy Losbar/Losbar)")
            
            return new_mentions
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification mentions étendues: {e}")
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
        """Formater une alerte pour les mentions des mots-clés surveillés"""
        if not mentions:
            return ""
        
        # Séparer par priorité
        high_priority_mentions = [m for m in mentions if m.get('priority') == 'high']
        medium_priority_mentions = [m for m in mentions if m.get('priority') == 'medium']
        
        alert_parts = []
        
        # Titre dynamique selon la priorité
        if high_priority_mentions:
            alert_parts.extend(["🚨 <b>ALERTE PRIORITAIRE Guy Losbar</b>", ""])
            mentions_to_show = high_priority_mentions[:3]  # Limiter pour Telegram
        else:
            alert_parts.extend(["📢 <b>ALERTE Conseil Départemental</b>", ""])
            mentions_to_show = medium_priority_mentions[:3]
        
        for mention in mentions_to_show:
            keywords_found = mention.get('keywords_found', [])
            keywords_display = ", ".join(keywords_found[:3])  # Limiter l'affichage
            if len(keywords_found) > 3:
                keywords_display += f" (+{len(keywords_found)-3} autres)"
            
            if mention['type'] == 'article':
                source = mention['source']
                title = mention['title']
                url = mention['url']
                
                alert_parts.append(f"📰 *Article* - {source}")
                title_display = title[:100] + "..." if len(title) > 100 else title
                alert_parts.append(f"📝 {title_display}")
                alert_parts.append(f"🔍 Mots-clés: {keywords_display}")
                if url:
                    alert_parts.append(f"🔗 [Lire l'article]({url})")
                
            elif mention['type'] == 'social_post':
                platform = mention['platform']
                author = mention['author']
                content = mention['content']
                engagement = mention.get('engagement', 0)
                
                emoji = "🐦" if platform == 'twitter' else "📱"
                alert_parts.append(f"{emoji} *{platform.title()}* - @{author}")
                alert_parts.append(f"💬 {content}")
                alert_parts.append(f"🔍 Mots-clés: {keywords_display}")
                if engagement > 0:
                    alert_parts.append(f"📊 {engagement} interactions")
                
            elif mention['type'] == 'radio_transcription':
                section = mention['section']
                stream_name = mention.get('stream_name', section)
                content = mention['content']
                
                alert_parts.append(f"📻 *Radio* - {stream_name}")
                alert_parts.append(f"🎙️ {content}")
                alert_parts.append(f"🔍 Mots-clés: {keywords_display}")
            
            alert_parts.append("")  # Ligne vide entre mentions
        
        # Résumé si plus de mentions
        total_mentions = len(mentions)
        if total_mentions > len(mentions_to_show):
            remaining = total_mentions - len(mentions_to_show)
            alert_parts.append(f"📋 +{remaining} autres mentions non affichées")
            alert_parts.append("")
        
        # Priorité et timing
        priority_info = f"🎯 Priorité haute: {len(high_priority_mentions)}" if high_priority_mentions else ""
        if medium_priority_mentions and high_priority_mentions:
            priority_info += f" | Normale: {len(medium_priority_mentions)}"
        elif medium_priority_mentions:
            priority_info = f"📝 Mentions normales: {len(medium_priority_mentions)}"
        
        if priority_info:
            alert_parts.append(priority_info)
        
        current_time = datetime.now().strftime('%d/%m/%Y à %H:%M')
        alert_parts.append(f"⏰ Détecté le {current_time}")
        
        return "\n".join(alert_parts)

    def format_task_status_alert(self, changes: List[Dict]) -> str:
        """Formater une alerte pour les changements de statut des tâches"""
        if not changes:
            return ""
        
        alert_parts = ["⚙️ <b>STATUT DES TÂCHES</b>", ""]
        
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
            
            alert_parts.append(f"🔄 <b>{task_name}</b>")
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
        """Boucle principale de surveillance (thread daemon)"""
        logger.info("🔔 Boucle de monitoring Telegram démarrée")
        while self.monitoring_active:
            try:
                # Vérifier les mentions Guy Losbar
                guy_losbar_mentions = self.check_guy_losbar_mentions()
                if guy_losbar_mentions:
                    alert_message = self.format_guy_losbar_alert(guy_losbar_mentions)
                    if alert_message:
                        # Utiliser HTTP directement depuis le thread (pas de conflit asyncio)
                        sent_ok = self._send_via_http(alert_message)
                        if sent_ok:
                            # Marquer les IDs comme notifiés pour éviter les doublons
                            for mention in guy_losbar_mentions:
                                mid = mention.get('_id', '')
                                if mid:
                                    self._notified_ids.add(mid)
                            # Purger le cache si trop gros
                            if len(self._notified_ids) > self._notified_ids_max:
                                # Garder seulement les 1000 plus récents
                                overflow = len(self._notified_ids) - (self._notified_ids_max // 2)
                                for _ in range(overflow):
                                    self._notified_ids.pop()

                # Vérifier les changements de statut des tâches
                task_changes = self.check_task_status_changes()
                if task_changes:
                    task_alert = self.format_task_status_alert(task_changes)
                    if task_alert:
                        self._send_via_http(task_alert)

                # Mettre à jour la dernière vérification
                self.last_check_time = datetime.now()

                # Attendre 2 minutes avant la prochaine vérification
                time.sleep(120)

            except Exception as e:
                logger.error(f"❌ Erreur dans la boucle de surveillance: {e}")
                time.sleep(60)

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
        print("Configurez TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans l'env ou utilisez /api/telegram/configure")