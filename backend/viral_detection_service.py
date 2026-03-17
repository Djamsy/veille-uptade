# backend/viral_detection_service.py
"""
Service de détection virale en temps réel - Version 2025 boostée
Combine vélocité, cross-platform tracking, sentiment momentum et patterns locaux
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter
import json
import threading
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError
import certifi
import redis

# Imports de vos services existants
try:
    from backend.media_noise_service import media_noise_service
    from backend.gpt_sentiment_service import gpt_sentiment_analyzer
    from backend.population_reaction_service import PopulationReactionPredictor
    from backend.telegram_alerts_service import telegram_alerts
    from backend.tags_index import infer_tags_and_theme
except ImportError as e:
    logging.warning(f"Import service: {e}")

logger = logging.getLogger("viral_detection_service")

class ViralDetectionService:
    """Service de détection virale multicritères avec alertes temps réel"""
    
    def __init__(self):
        # MongoDB
        self.mongo_client = self._get_mongo_client()
        self.db = self._get_database()
        
        # Redis pour le cache temps réel (optionnel)
        try:
            self.redis_client = redis.Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=int(os.environ.get('REDIS_PORT', 6379)),
                decode_responses=True
            )
            self.redis_available = True
        except Exception:
            self.redis_client = None
            self.redis_available = False
            
        # Seuils de détection virale
        self.viral_thresholds = {
            'velocity_spike': 5.0,      # Articles/heure vs moyenne
            'cross_platform_ratio': 0.3, # % de platforms touchées
            'sentiment_momentum': 0.4,   # Accélération du sentiment
            'engagement_multiplier': 3.0, # Engagement vs normal
            'elected_mention_spike': 2.0, # Mentions élus vs normal
            'geographic_spread': 0.4     # % zones géographiques
        }
        
        # État de monitoring temps réel
        self.monitoring_active = False
        self.monitoring_thread = None
        self.last_viral_check = datetime.now()
        
        # Cache des patterns viraux détectés
        self.active_viral_patterns = {}
        self.viral_history = []
        
        logger.info("✅ Service de détection virale initialisé")
    
    def _get_mongo_client(self) -> Optional[MongoClient]:
        """Connexion MongoDB optimisée"""
        mongo_url = os.environ.get("MONGO_URL", "").strip()
        if not mongo_url:
            return None
            
        try:
            client = MongoClient(
                mongo_url,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=10000,
                maxPoolSize=50
            )
            client.admin.command("ping")
            return client
        except Exception as e:
            logger.error(f"Erreur MongoDB viral service: {e}")
            return None
    
    def _get_database(self):
        """Base de données"""
        if not self.mongo_client:
            return None
        db_name = os.environ.get("MONGO_DB_NAME", "veille_media")
        return self.mongo_client[db_name]
    
    def calculate_velocity_score(self, content_type: str = "all", window_minutes: int = 60) -> Dict[str, float]:
        """Calcule la vélocité de publication (articles/heure vs moyenne)"""
        if not self.db:
            return {'current': 0, 'baseline': 0, 'spike_factor': 0}
            
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)
        baseline_start = now - timedelta(days=7)  # Moyenne sur 7 jours
        
        try:
            # Contenu actuel dans la fenêtre
            current_query = {
                "$or": [
                    {"scraped_at": {"$gte": window_start.isoformat(), "$lte": now.isoformat()}},
                    {"captured_at": {"$gte": window_start, "$lte": now}}
                ]
            }
            
            current_articles = self.db.articles_guadeloupe.count_documents(current_query)
            current_transcriptions = self.db.radio_transcriptions.count_documents(current_query)
            current_social = self.db.social_media_posts.count_documents(current_query)
            
            current_total = current_articles + current_transcriptions + current_social
            current_rate = (current_total / window_minutes) * 60  # Par heure
            
            # Baseline (moyenne hebdomadaire)
            baseline_query = {
                "$or": [
                    {"scraped_at": {"$gte": baseline_start.isoformat(), "$lt": window_start.isoformat()}},
                    {"captured_at": {"$gte": baseline_start, "$lt": window_start}}
                ]
            }
            
            baseline_articles = self.db.articles_guadeloupe.count_documents(baseline_query)
            baseline_transcriptions = self.db.radio_transcriptions.count_documents(baseline_query)
            baseline_social = self.db.social_media_posts.count_documents(baseline_query)
            
            baseline_total = baseline_articles + baseline_transcriptions + baseline_social
            baseline_hours = (window_start - baseline_start).total_seconds() / 3600
            baseline_rate = baseline_total / baseline_hours if baseline_hours > 0 else 1
            
            spike_factor = current_rate / baseline_rate if baseline_rate > 0 else current_rate
            
            return {
                'current_rate': round(current_rate, 2),
                'baseline_rate': round(baseline_rate, 2),
                'spike_factor': round(spike_factor, 2),
                'window_minutes': window_minutes,
                'is_spike': spike_factor >= self.viral_thresholds['velocity_spike']
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul vélocité: {e}")
            return {'current': 0, 'baseline': 0, 'spike_factor': 0, 'error': str(e)}
    
    def detect_cross_platform_amplification(self, text_query: str, hours_back: int = 6) -> Dict[str, Any]:
        """Détecte si un sujet se propage sur plusieurs plateformes"""
        if not self.db:
            return {'platforms': [], 'amplification_score': 0}
            
        since = datetime.now() - timedelta(hours=hours_back)
        platforms_data = {}
        
        try:
            # Recherche dans les articles
            articles_regex = {"$regex": text_query, "$options": "i"}
            articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {"$gte": since.isoformat()},
                "$or": [
                    {"title": articles_regex},
                    {"content": articles_regex}
                ]
            }, {"source": 1, "title": 1, "scraped_at": 1}))
            
            if articles:
                platforms_data['press'] = {
                    'count': len(articles),
                    'sources': list(set(a.get('source', 'inconnu') for a in articles)),
                    'latest': max(a.get('scraped_at', '') for a in articles)
                }
            
            # Recherche dans les transcriptions radio
            radio_transcriptions = list(self.db.radio_transcriptions.find({
                "captured_at": {"$gte": since},
                "transcription": articles_regex
            }, {"radio_name": 1, "captured_at": 1}))
            
            if radio_transcriptions:
                platforms_data['radio'] = {
                    'count': len(radio_transcriptions),
                    'sources': list(set(t.get('radio_name', 'inconnu') for t in radio_transcriptions)),
                    'latest': max(t.get('captured_at', datetime.min) for t in radio_transcriptions)
                }
            
            # Recherche dans les réseaux sociaux
            social_posts = list(self.db.social_media_posts.find({
                "scraped_at": {"$gte": since.isoformat()},
                "content": articles_regex
            }, {"platform": 1, "author": 1, "engagement": 1, "scraped_at": 1}))
            
            if social_posts:
                platforms_data['social'] = {
                    'count': len(social_posts),
                    'platforms': list(set(p.get('platform', 'inconnu') for p in social_posts)),
                    'total_engagement': sum(p.get('engagement', {}).get('total', 0) for p in social_posts),
                    'latest': max(p.get('scraped_at', '') for p in social_posts)
                }
            
            # Calcul du score d'amplification
            num_platforms = len(platforms_data)
            total_content = sum(data.get('count', 0) for data in platforms_data.values())
            
            # Bonus pour diversité des sources
            all_sources = []
            for platform_data in platforms_data.values():
                all_sources.extend(platform_data.get('sources', []) + platform_data.get('platforms', []))
            unique_sources = len(set(all_sources))
            
            amplification_score = (num_platforms / 3) * 0.4 + (unique_sources / 10) * 0.3 + (total_content / 20) * 0.3
            
            return {
                'platforms_detected': list(platforms_data.keys()),
                'platforms_data': platforms_data,
                'amplification_score': round(min(amplification_score, 1.0), 3),
                'unique_sources': unique_sources,
                'total_content_items': total_content,
                'is_cross_platform': num_platforms >= 2,
                'query': text_query,
                'analysis_period_hours': hours_back
            }
            
        except Exception as e:
            logger.error(f"Erreur détection cross-platform: {e}")
            return {'platforms': [], 'amplification_score': 0, 'error': str(e)}
    
    def calculate_sentiment_momentum(self, text_query: str, hours_back: int = 12) -> Dict[str, Any]:
        """Calcule l'évolution du sentiment dans le temps"""
        if not self.db:
            return {'momentum': 0, 'direction': 'stable'}
            
        now = datetime.now()
        time_periods = []
        
        # Découper en tranches de 2h pour voir l'évolution
        for i in range(0, hours_back, 2):
            period_start = now - timedelta(hours=i+2)
            period_end = now - timedelta(hours=i)
            time_periods.append((period_start, period_end))
        
        sentiment_evolution = []
        
        try:
            for period_start, period_end in time_periods:
                # Récupérer le contenu de cette période
                query_regex = {"$regex": text_query, "$options": "i"}
                
                articles = list(self.db.articles_guadeloupe.find({
                    "scraped_at": {
                        "$gte": period_start.isoformat(),
                        "$lt": period_end.isoformat()
                    },
                    "$or": [{"title": query_regex}, {"content": query_regex}]
                }, {"title": 1, "content": 1, "sentiment": 1}))
                
                if not articles:
                    continue
                
                # Analyser le sentiment de cette période
                period_sentiments = []
                for article in articles:
                    # Utiliser le sentiment déjà calculé ou le calculer
                    existing_sentiment = article.get('sentiment', {})
                    if existing_sentiment and 'score' in existing_sentiment:
                        period_sentiments.append(existing_sentiment['score'])
                    else:
                        # Analyser avec GPT si disponible
                        text_to_analyze = article.get('title', '') + ' ' + article.get('content', '')[:200]
                        if hasattr(gpt_sentiment_analyzer, 'analyze_sentiment'):
                            sentiment_result = gpt_sentiment_analyzer.analyze_sentiment(text_to_analyze)
                            if 'score' in sentiment_result:
                                period_sentiments.append(sentiment_result['score'])
                
                if period_sentiments:
                    avg_sentiment = sum(period_sentiments) / len(period_sentiments)
                    sentiment_evolution.append({
                        'period_start': period_start,
                        'period_end': period_end,
                        'avg_sentiment': avg_sentiment,
                        'content_count': len(articles)
                    })
            
            if len(sentiment_evolution) < 2:
                return {'momentum': 0, 'direction': 'insufficient_data', 'data_points': len(sentiment_evolution)}
            
            # Calculer la tendance
            recent_avg = sum(p['avg_sentiment'] for p in sentiment_evolution[:2]) / 2  # 2 périodes récentes
            older_avg = sum(p['avg_sentiment'] for p in sentiment_evolution[-2:]) / 2   # 2 périodes anciennes
            
            momentum = recent_avg - older_avg
            
            # Déterminer la direction
            if abs(momentum) < 0.1:
                direction = 'stable'
            elif momentum > 0:
                direction = 'amélioration' if momentum > 0.3 else 'légère_amélioration'
            else:
                direction = 'dégradation' if momentum < -0.3 else 'légère_dégradation'
            
            return {
                'momentum': round(momentum, 3),
                'direction': direction,
                'is_significant': abs(momentum) >= self.viral_thresholds['sentiment_momentum'],
                'recent_sentiment': round(recent_avg, 3),
                'baseline_sentiment': round(older_avg, 3),
                'evolution_data': sentiment_evolution,
                'analysis_periods': len(sentiment_evolution)
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul sentiment momentum: {e}")
            return {'momentum': 0, 'direction': 'error', 'error': str(e)}
    
    def detect_elected_mention_spike(self, hours_back: int = 8) -> Dict[str, Any]:
        """Détecte les pics de mentions d'élus"""
        if not self.db:
            return {'spikes': [], 'total_spike_score': 0}
            
        now = datetime.now()
        spike_window = now - timedelta(hours=hours_back)
        baseline_window = now - timedelta(days=7)
        
        try:
            # Mentions récentes
            recent_articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {"$gte": spike_window.isoformat()},
                "elected": {"$exists": True, "$ne": []}
            }, {"elected": 1, "title": 1, "source": 1}))
            
            # Compter les mentions récentes
            recent_mentions = Counter()
            for article in recent_articles:
                for elu in article.get('elected', []):
                    recent_mentions[elu] += 1
            
            # Baseline (moyenne hebdomadaire)
            baseline_articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {
                    "$gte": baseline_window.isoformat(),
                    "$lt": spike_window.isoformat()
                },
                "elected": {"$exists": True, "$ne": []}
            }, {"elected": 1}))
            
            baseline_mentions = Counter()
            for article in baseline_articles:
                for elu in article.get('elected', []):
                    baseline_mentions[elu] += 1
            
            # Normaliser par la durée
            baseline_hours = (spike_window - baseline_window).total_seconds() / 3600
            baseline_rate = {elu: count / baseline_hours * hours_back 
                           for elu, count in baseline_mentions.items()}
            
            # Détecter les spikes
            detected_spikes = []
            for elu, recent_count in recent_mentions.items():
                baseline_count = baseline_rate.get(elu, 0.1)  # Éviter division par 0
                spike_ratio = recent_count / baseline_count
                
                if spike_ratio >= self.viral_thresholds['elected_mention_spike']:
                    # Récupérer des exemples d'articles
                    example_articles = [
                        {
                            'title': article['title'],
                            'source': article.get('source', 'inconnu')
                        }
                        for article in recent_articles 
                        if elu in article.get('elected', [])
                    ][:3]
                    
                    detected_spikes.append({
                        'elected_name': elu,
                        'recent_mentions': recent_count,
                        'baseline_expected': round(baseline_count, 1),
                        'spike_ratio': round(spike_ratio, 2),
                        'example_articles': example_articles,
                        'urgency_level': 'high' if spike_ratio > 5 else 'medium'
                    })
            
            # Trier par ratio de spike
            detected_spikes.sort(key=lambda x: x['spike_ratio'], reverse=True)
            
            total_spike_score = sum(spike['spike_ratio'] for spike in detected_spikes)
            
            return {
                'detected_spikes': detected_spikes,
                'total_spike_score': round(total_spike_score, 2),
                'analysis_period_hours': hours_back,
                'has_significant_spikes': len(detected_spikes) > 0,
                'top_spiking_elected': detected_spikes[0]['elected_name'] if detected_spikes else None
            }
            
        except Exception as e:
            logger.error(f"Erreur détection spike élus: {e}")
            return {'spikes': [], 'total_spike_score': 0, 'error': str(e)}
    
    def comprehensive_viral_analysis(self, text_query: Optional[str] = None, auto_detect: bool = True) -> Dict[str, Any]:
        """Analyse virale complète multicritères"""
        analysis_start = datetime.now()
        
        # 1. Vélocité globale
        velocity = self.calculate_velocity_score(window_minutes=90)
        
        # 2. Si pas de requête spécifique, détecter automatiquement les sujets chauds
        if not text_query and auto_detect:
            text_query = self._detect_trending_topics()
        
        results = {
            'analysis_timestamp': analysis_start.isoformat(),
            'query': text_query,
            'velocity_analysis': velocity,
            'viral_indicators': {}
        }
        
        # 3. Analyses spécifiques si on a un sujet
        if text_query:
            # Cross-platform
            cross_platform = self.detect_cross_platform_amplification(text_query, hours_back=8)
            results['cross_platform_analysis'] = cross_platform
            
            # Sentiment momentum
            sentiment_momentum = self.calculate_sentiment_momentum(text_query, hours_back=16)
            results['sentiment_momentum'] = sentiment_momentum
            
            # Score viral composite
            viral_score = self._calculate_composite_viral_score(
                velocity, cross_platform, sentiment_momentum
            )
            results['viral_score'] = viral_score
        
        # 4. Spike des élus (indépendant du sujet)
        elected_spikes = self.detect_elected_mention_spike(hours_back=12)
        results['elected_spikes'] = elected_spikes
        
        # 5. Évaluation du risque viral
        risk_assessment = self._assess_viral_risk(results)
        results['risk_assessment'] = risk_assessment
        
        # 6. Recommandations
        recommendations = self._generate_viral_recommendations(results)
        results['recommendations'] = recommendations
        
        analysis_duration = (datetime.now() - analysis_start).total_seconds()
        results['analysis_duration_seconds'] = round(analysis_duration, 2)
        
        # 7. Stocker dans l'historique si significatif
        if risk_assessment.get('risk_level') in ['medium', 'high']:
            self._store_viral_event(results)
        
        return results
    
    def _detect_trending_topics(self) -> Optional[str]:
        """Détecte automatiquement les sujets tendance"""
        if not self.db:
            return None
            
        # Analyser les dernières 4 heures
        since = datetime.now() - timedelta(hours=4)
        
        try:
            # Récupérer les articles récents avec thèmes
            recent_articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {"$gte": since.isoformat()},
                "theme": {"$exists": True, "$ne": None}
            }, {"theme": 1, "title": 1, "elected": 1}))
            
            if not recent_articles:
                return None
            
            # Compter les thèmes
            theme_counts = Counter()
            elected_counts = Counter()
            
            for article in recent_articles:
                theme = article.get('theme')
                if theme:
                    theme_counts[theme] += 1
                
                for elu in article.get('elected', []):
                    elected_counts[elu] += 1
            
            # Le sujet le plus fréquent
            if theme_counts:
                top_theme = theme_counts.most_common(1)[0][0]
                return top_theme
            elif elected_counts:
                top_elected = elected_counts.most_common(1)[0][0]
                return top_elected
                
        except Exception as e:
            logger.error(f"Erreur détection trending: {e}")
            
        return None
    
    def _calculate_composite_viral_score(self, velocity: Dict, cross_platform: Dict, sentiment: Dict) -> Dict[str, Any]:
        """Calcule un score viral composite"""
        # Composantes du score (0-1)
        velocity_component = min(velocity.get('spike_factor', 0) / 10, 1.0)
        platform_component = cross_platform.get('amplification_score', 0)
        sentiment_component = min(abs(sentiment.get('momentum', 0)) / 0.8, 1.0)
        
        # Poids
        weights = {'velocity': 0.4, 'platform': 0.35, 'sentiment': 0.25}
        
        composite_score = (
            velocity_component * weights['velocity'] +
            platform_component * weights['platform'] +
            sentiment_component * weights['sentiment']
        )
        
        # Niveau viral
        if composite_score >= 0.7:
            viral_level = 'very_high'
        elif composite_score >= 0.5:
            viral_level = 'high'
        elif composite_score >= 0.3:
            viral_level = 'medium'
        else:
            viral_level = 'low'
        
        return {
            'composite_score': round(composite_score, 3),
            'viral_level': viral_level,
            'components': {
                'velocity': round(velocity_component, 3),
                'cross_platform': round(platform_component, 3),
                'sentiment_momentum': round(sentiment_component, 3)
            },
            'interpretation': self._interpret_viral_score(composite_score)
        }
    
    def _assess_viral_risk(self, analysis: Dict) -> Dict[str, Any]:
        """Évalue le risque viral global"""
        risk_factors = []
        risk_score = 0
        
        # Vélocité
        velocity = analysis.get('velocity_analysis', {})
        if velocity.get('is_spike', False):
            risk_factors.append('publication_spike')
            risk_score += 0.3
        
        # Cross-platform
        cross_platform = analysis.get('cross_platform_analysis', {})
        if cross_platform.get('is_cross_platform', False):
            risk_factors.append('multi_platform_spread')
            risk_score += 0.25
        
        # Sentiment
        sentiment = analysis.get('sentiment_momentum', {})
        if sentiment.get('is_significant', False):
            risk_factors.append('sentiment_shift')
            risk_score += 0.2
        
        # Élus
        elected_spikes = analysis.get('elected_spikes', {})
        if elected_spikes.get('has_significant_spikes', False):
            risk_factors.append('elected_attention_spike')
            risk_score += 0.25
        
        # Score viral composite
        viral_score = analysis.get('viral_score', {})
        if viral_score.get('viral_level') in ['high', 'very_high']:
            risk_factors.append('high_viral_potential')
            risk_score += 0.3
        
        # Niveau de risque
        if risk_score >= 0.7:
            risk_level = 'high'
        elif risk_score >= 0.4:
            risk_level = 'medium'
        elif risk_score >= 0.2:
            risk_level = 'low'
        else:
            risk_level = 'minimal'
        
        return {
            'risk_level': risk_level,
            'risk_score': round(min(risk_score, 1.0), 3),
            'risk_factors': risk_factors,
            'alert_recommended': risk_level in ['medium', 'high'],
            'monitoring_priority': 'high' if risk_level == 'high' else 'normal'
        }
    
    def _generate_viral_recommendations(self, analysis: Dict) -> List[str]:
        """Génère des recommandations basées sur l'analyse"""
        recommendations = []
        risk = analysis.get('risk_assessment', {})
        
        if risk.get('risk_level') == 'high':
            recommendations.append("🚨 Alerte virale détectée - Monitoring renforcé recommandé")
            recommendations.append("📢 Préparer une stratégie de communication proactive")
            
        if 'publication_spike' in risk.get('risk_factors', []):
            recommendations.append("📈 Pic de publication détecté - Analyser les sources")
            
        if 'multi_platform_spread' in risk.get('risk_factors', []):
            recommendations.append("🌐 Propagation multi-plateformes - Surveiller l'amplification")
            
        if 'sentiment_shift' in risk.get('risk_factors', []):
            recommendations.append("😟 Évolution du sentiment - Identifier les causes")
            
        if 'elected_attention_spike' in risk.get('risk_factors', []):
            recommendations.append("🏛️ Attention accrue sur les élus - Contact préventif recommandé")
            
        # Recommendations générales
        if len(recommendations) == 0:
            recommendations.append("✅ Situation stable - Maintenir la surveillance normale")
            
        return recommendations
    
    def _interpret_viral_score(self, score: float) -> str:
        """Interprète le score viral"""
        if score >= 0.8:
            return "Potentiel viral très élevé - Diffusion imminente probable"
        elif score >= 0.6:
            return "Potentiel viral élevé - Surveillance renforcée recommandée"
        elif score >= 0.4:
            return "Potentiel viral modéré - Situation à suivre"
        elif score >= 0.2:
            return "Potentiel viral faible - Activité normale"
        else:
            return "Aucun indicateur viral significatif"
    
    def _store_viral_event(self, analysis: Dict):
        """Stocke un événement viral dans l'historique"""
        if not self.db:
            return
            
        try:
            viral_event = {
                'timestamp': analysis['analysis_timestamp'],
                'query': analysis.get('query'),
                'risk_level': analysis['risk_assessment']['risk_level'],
                'viral_score': analysis.get('viral_score', {}).get('composite_score', 0),
                'risk_factors': analysis['risk_assessment']['risk_factors'],
                'analysis_summary': {
                    'velocity_spike': analysis['velocity_analysis'].get('is_spike', False),
                    'cross_platform': analysis.get('cross_platform_analysis', {}).get('is_cross_platform', False),
                    'elected_spikes': len(analysis.get('elected_spikes', {}).get('detected_spikes', [])),
                    'sentiment_direction': analysis.get('sentiment_momentum', {}).get('direction', 'stable')
                },
                'stored_at': datetime.now().isoformat()
            }
            
            # Stocker en base
            self.db.viral_events_history.insert_one(viral_event)
            
            # Garder aussi en mémoire (limité à 50)
            self.viral_history.append(viral_event)
            if len(self.viral_history) > 50:
                self.viral_history.pop(0)
                
        except Exception as e:
            logger.error(f"Erreur stockage événement viral: {e}")
    
    def start_real_time_monitoring(self, interval_minutes: int = 15):
        """Démarre le monitoring temps réel"""
        if self.monitoring_active:
            logger.warning("Monitoring déjà actif")
            return
            
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, 
            args=(interval_minutes,), 
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info(f"🚀 Monitoring viral démarré (intervalle: {interval_minutes}min)")
    
    def stop_real_time_monitoring(self):
        """Arrête le monitoring temps réel"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=30)
        logger.info("⏹️ Monitoring viral arrêté")
    
    def _monitoring_loop(self, interval_minutes: int):
        """Boucle de monitoring temps réel"""
        while self.monitoring_active:
            try:
                # Analyse virale complète
                analysis = self.comprehensive_viral_analysis(auto_detect=True)
                
                # Si risque élevé, envoyer une alerte
                risk = analysis.get('risk_assessment', {})
                if risk.get('alert_recommended', False):
                    self._send_viral_alert(analysis)
                
                # Mise à jour du cache
                self.last_viral_check = datetime.now()
                
                # Stocker dans Redis si disponible
                if self.redis_available:
                    try:
                        self.redis_client.setex(
                            'latest_viral_analysis',
                            3600,  # 1 heure
                            json.dumps(analysis, default=str)
                        )
                    except Exception:
                        pass
                
                logger.info(f"Analyse virale: {risk.get('risk_level', 'unknown')} (score: {analysis.get('viral_score', {}).get('composite_score', 0)})")
                
            except Exception as e:
                logger.error(f"Erreur monitoring loop: {e}")
            
            # Attendre avant la prochaine vérification
            time.sleep(interval_minutes * 60)
    
    def _send_viral_alert(self, analysis: Dict):
        """Envoie une alerte virale via Telegram"""
        try:
            risk = analysis.get('risk_assessment', {})
            viral_score = analysis.get('viral_score', {})
            query = analysis.get('query', 'Sujet détecté')
            
            alert_message = f"""🚨 ALERTE VIRALE DÉTECTÉE

📊 **Sujet:** {query}
🎯 **Niveau de risque:** {risk.get('risk_level', 'unknown').upper()}
📈 **Score viral:** {viral_score.get('composite_score', 0):.2f}/1.0

🔥 **Facteurs détectés:**
{chr(10).join(f"• {factor}" for factor in risk.get('risk_factors', []))}

📋 **Recommandations:**
{chr(10).join(f"• {rec}" for rec in analysis.get('recommendations', [])[:3])}

⏰ **Détecté le:** {datetime.now().strftime('%d/%m/%Y à %H:%M')}
🔍 **Monitoring:** En cours"""

            # Envoyer via le service Telegram
            if hasattr(telegram_alerts, 'send_alert_sync'):
                success = telegram_alerts.send_alert_sync(alert_message)
                if success:
                    logger.info("✅ Alerte virale envoyée via Telegram")
                else:
                    logger.warning("⚠️ Échec envoi alerte Telegram")
            
        except Exception as e:
            logger.error(f"Erreur envoi alerte virale: {e}")
    
    def get_viral_status(self) -> Dict[str, Any]:
        """Retourne le statut actuel du service viral"""
        # Analyse rapide
        quick_analysis = self.comprehensive_viral_analysis()
        
        return {
            'monitoring_active': self.monitoring_active,
            'last_check': self.last_viral_check.isoformat() if self.last_viral_check else None,
            'current_risk_level': quick_analysis.get('risk_assessment', {}).get('risk_level', 'unknown'),
            'viral_score': quick_analysis.get('viral_score', {}).get('composite_score', 0),
            'active_patterns': len(self.active_viral_patterns),
            'history_entries': len(self.viral_history),
            'redis_available': self.redis_available,
            'database_connected': self.db is not None,
            'service_status': 'operational' if self.db else 'degraded'
        }

# Instance globale
viral_detector = ViralDetectionService()