# backend/social_amplification_tracker.py
"""
Service de tracking d'amplification sociale en temps réel
Suit la propagation virale et les patterns d'engagement sur tous les canaux
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict, deque
import threading
import time

from pymongo import MongoClient
import requests
from dataclasses import dataclass
import hashlib

logger = logging.getLogger("social_amplification_tracker")

@dataclass
class AmplificationEvent:
    """Événement d'amplification détecté"""
    timestamp: datetime
    content_hash: str
    platform: str
    engagement_spike: float
    propagation_velocity: float
    influence_score: float
    geographic_reach: int
    sentiment_shift: float

@dataclass
class InfluencerProfile:
    """Profil d'influenceur local"""
    name: str
    platform: str
    followers: int
    engagement_rate: float
    local_influence: float
    topics: List[str]
    last_activity: datetime

class SocialAmplificationTracker:
    """Tracker d'amplification sociale haute performance"""
    
    def __init__(self):
        # MongoDB
        self.mongo_client = self._get_mongo_client()
        self.db = self._get_database()
        
        # Cache en mémoire pour la performance
        self.amplification_events: deque = deque(maxlen=1000)
        self.active_trends: Dict[str, Dict] = {}
        self.influencer_profiles: Dict[str, InfluencerProfile] = {}
        
        # Métriques de tracking
        self.tracking_window = timedelta(hours=2)  # Fenêtre glissante
        self.velocity_threshold = 5.0  # Posts/minute
        self.engagement_multiplier_threshold = 3.0
        
        # Plateformes surveillées
        self.monitored_platforms = {
            'facebook': {'weight': 0.4, 'viral_threshold': 100},
            'twitter': {'weight': 0.3, 'viral_threshold': 50},
            'instagram': {'weight': 0.2, 'viral_threshold': 200},
            'tiktok': {'weight': 0.1, 'viral_threshold': 1000},
            'whatsapp': {'weight': 0.5, 'viral_threshold': 10},  # Poids élevé pour WhatsApp local
            'youtube': {'weight': 0.3, 'viral_threshold': 500},
            'radio_comments': {'weight': 0.6, 'viral_threshold': 20}  # Commentaires radio
        }
        
        # Zones géographiques Guadeloupe
        self.geographic_zones = {
            'pointe_a_pitre': {'population': 120000, 'influence': 0.3},
            'basse_terre': {'population': 80000, 'influence': 0.25},
            'le_gosier': {'population': 28000, 'influence': 0.15},
            'sainte_anne': {'population': 24000, 'influence': 0.1},
            'baie_mahault': {'population': 32000, 'influence': 0.12},
            'marie_galante': {'population': 12000, 'influence': 0.08}
        }
        
        # État de monitoring temps réel
        self.tracking_active = False
        self.tracking_thread = None
        
        logger.info("🚀 Social Amplification Tracker initialisé")
    
    def _get_mongo_client(self) -> Optional[MongoClient]:
        """Connexion MongoDB"""
        mongo_url = os.environ.get("MONGO_URL", "").strip()
        if not mongo_url:
            return None
        try:
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
            client.admin.command("ping")
            return client
        except Exception as e:
            logger.error(f"Erreur MongoDB amplification: {e}")
            return None
    
    def _get_database(self):
        if not self.mongo_client:
            return None
        return self.mongo_client[os.environ.get("MONGO_DB_NAME", "veille_media")]
    
    def detect_amplification_patterns(self, content_hash: Optional[str] = None, hours_back: int = 4) -> Dict[str, Any]:
        """Détecte les patterns d'amplification en cours"""
        if not self.db:
            return {'patterns': [], 'amplification_score': 0}
        
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)
        
        detected_patterns = []
        
        try:
            # 1. Analyser la vélocité de propagation
            velocity_patterns = self._detect_velocity_patterns(start_time, end_time, content_hash)
            detected_patterns.extend(velocity_patterns)
            
            # 2. Détecter les cascades d'engagement
            engagement_cascades = self._detect_engagement_cascades(start_time, end_time, content_hash)
            detected_patterns.extend(engagement_cascades)
            
            # 3. Identifier les amplificateurs influents
            influencer_amplification = self._detect_influencer_amplification(start_time, end_time, content_hash)
            detected_patterns.extend(influencer_amplification)
            
            # 4. Analyser la propagation géographique
            geographic_spread = self._analyze_geographic_propagation(start_time, end_time, content_hash)
            
            # 5. Calculer le score d'amplification global
            amplification_score = self._calculate_amplification_score(
                detected_patterns, geographic_spread
            )
            
            return {
                'detection_timestamp': end_time.isoformat(),
                'analysis_period_hours': hours_back,
                'detected_patterns': detected_patterns,
                'geographic_spread': geographic_spread,
                'amplification_score': amplification_score,
                'risk_level': self._assess_amplification_risk(amplification_score),
                'trending_content': self._identify_trending_content(detected_patterns),
                'prediction': self._predict_amplification_trajectory(detected_patterns)
            }
            
        except Exception as e:
            logger.error(f"Erreur détection patterns: {e}")
            return {'patterns': [], 'amplification_score': 0, 'error': str(e)}
    
    def _detect_velocity_patterns(self, start_time: datetime, end_time: datetime, content_hash: Optional[str]) -> List[Dict]:
        """Détecte les patterns de vélocité de propagation"""
        patterns = []
        
        try:
            # Analyser par tranches de 30 minutes
            time_slices = []
            current = start_time
            while current < end_time:
                slice_end = min(current + timedelta(minutes=30), end_time)
                time_slices.append((current, slice_end))
                current = slice_end
            
            # Compter les posts par tranche pour chaque plateforme
            for platform in self.monitored_platforms.keys():
                platform_velocities = []
                
                for slice_start, slice_end in time_slices:
                    query = {
                        'platform': platform,
                        'scraped_at': {
                            '$gte': slice_start.isoformat(),
                            '$lt': slice_end.isoformat()
                        }
                    }
                    
                    if content_hash:
                        # Recherche par hash de contenu similaire
                        query['content_hash'] = content_hash
                    
                    count = self.db.social_media_posts.count_documents(query)
                    velocity = count / 30  # Posts par minute
                    platform_velocities.append(velocity)
                
                # Détecter les spikes de vélocité
                if len(platform_velocities) >= 2:
                    max_velocity = max(platform_velocities)
                    avg_velocity = sum(platform_velocities) / len(platform_velocities)
                    
                    if max_velocity > self.velocity_threshold and max_velocity > avg_velocity * 3:
                        patterns.append({
                            'type': 'velocity_spike',
                            'platform': platform,
                            'peak_velocity': round(max_velocity, 2),
                            'average_velocity': round(avg_velocity, 2),
                            'spike_ratio': round(max_velocity / (avg_velocity or 1), 2),
                            'urgency': 'high' if max_velocity > 10 else 'medium',
                            'pattern_strength': min(max_velocity / 20, 1.0)
                        })
        
        except Exception as e:
            logger.error(f"Erreur velocity patterns: {e}")
        
        return patterns
    
    def _detect_engagement_cascades(self, start_time: datetime, end_time: datetime, content_hash: Optional[str]) -> List[Dict]:
        """Détecte les cascades d'engagement (likes → partages → commentaires)"""
        patterns = []
        
        try:
            # Rechercher les posts avec engagement élevé
            query = {
                'scraped_at': {'$gte': start_time.isoformat(), '$lt': end_time.isoformat()},
                'engagement.total': {'$gt': 10}  # Seuil minimal
            }
            
            if content_hash:
                query['content_hash'] = content_hash
            
            high_engagement_posts = list(self.db.social_media_posts.find(query).sort('engagement.total', -1).limit(50))
            
            for post in high_engagement_posts:
                engagement = post.get('engagement', {})
                total_engagement = engagement.get('total', 0)
                likes = engagement.get('likes', 0)
                shares = engagement.get('shares', 0)
                comments = engagement.get('comments', 0)
                
                # Calculer les ratios de cascade
                like_share_ratio = shares / (likes or 1)
                share_comment_ratio = comments / (shares or 1)
                
                # Détecter les patterns de cascade virale
                if like_share_ratio > 0.1 and share_comment_ratio > 0.5:  # Ratios élevés
                    cascade_strength = (like_share_ratio + share_comment_ratio) / 2
                    
                    patterns.append({
                        'type': 'engagement_cascade',
                        'platform': post.get('platform', 'unknown'),
                        'post_id': str(post.get('_id', '')),
                        'total_engagement': total_engagement,
                        'cascade_metrics': {
                            'likes': likes,
                            'shares': shares,
                            'comments': comments,
                            'like_share_ratio': round(like_share_ratio, 3),
                            'share_comment_ratio': round(share_comment_ratio, 3)
                        },
                        'cascade_strength': round(cascade_strength, 3),
                        'viral_potential': 'high' if cascade_strength > 0.3 else 'medium',
                        'pattern_strength': min(cascade_strength * 2, 1.0)
                    })
        
        except Exception as e:
            logger.error(f"Erreur engagement cascades: {e}")
        
        return patterns
    
    def _detect_influencer_amplification(self, start_time: datetime, end_time: datetime, content_hash: Optional[str]) -> List[Dict]:
        """Détecte l'amplification par des influenceurs locaux"""
        patterns = []
        
        try:
            # Identifier les comptes avec forte influence locale
            # (ici on simule, mais vous pourriez avoir une DB d'influenceurs)
            local_influencers = [
                {'name': 'RCI Guadeloupe', 'followers': 45000, 'platform': 'facebook'},
                {'name': 'La1ere Guadeloupe', 'followers': 67000, 'platform': 'facebook'},
                {'name': 'Eric Damaseau', 'followers': 12000, 'platform': 'youtube'},
                {'name': 'Info Guadeloupe', 'followers': 23000, 'platform': 'instagram'}
            ]
            
            for influencer in local_influencers:
                # Rechercher les posts de cet influenceur dans la période
                query = {
                    'author': {'$regex': influencer['name'], '$options': 'i'},
                    'platform': influencer['platform'],
                    'scraped_at': {'$gte': start_time.isoformat(), '$lt': end_time.isoformat()}
                }
                
                if content_hash:
                    query['content_hash'] = content_hash
                
                influencer_posts = list(self.db.social_media_posts.find(query))
                
                for post in influencer_posts:
                    engagement = post.get('engagement', {}).get('total', 0)
                    expected_engagement = influencer['followers'] * 0.02  # 2% engagement moyen
                    
                    if engagement > expected_engagement * 1.5:  # 50% au-dessus de la normale
                        amplification_factor = engagement / expected_engagement
                        
                        patterns.append({
                            'type': 'influencer_amplification',
                            'influencer_name': influencer['name'],
                            'platform': influencer['platform'],
                            'follower_count': influencer['followers'],
                            'post_engagement': engagement,
                            'expected_engagement': round(expected_engagement),
                            'amplification_factor': round(amplification_factor, 2),
                            'influence_level': 'high' if amplification_factor > 3 else 'medium',
                            'pattern_strength': min(amplification_factor / 5, 1.0)
                        })
        
        except Exception as e:
            logger.error(f"Erreur influencer amplification: {e}")
        
        return patterns
    
    def _analyze_geographic_propagation(self, start_time: datetime, end_time: datetime, content_hash: Optional[str]) -> Dict[str, Any]:
        """Analyse la propagation géographique"""
        try:
            # Analyser les mentions de zones géographiques
            geographic_mentions = defaultdict(int)
            
            query = {
                'scraped_at': {'$gte': start_time.isoformat(), '$lt': end_time.isoformat()}
            }
            if content_hash:
                query['content_hash'] = content_hash
            
            posts = list(self.db.social_media_posts.find(query, {'content': 1, 'location': 1}))
            
            for post in posts:
                content = post.get('content', '').lower()
                location = post.get('location', '').lower()
                
                # Détecter les zones mentionnées
                for zone, zone_data in self.geographic_zones.items():
                    zone_keywords = [zone.replace('_', ' '), zone.replace('_', '-')]
                    
                    if any(keyword in content or keyword in location for keyword in zone_keywords):
                        geographic_mentions[zone] += 1
            
            # Calculer la portée géographique
            total_zones = len(self.geographic_zones)
            zones_touched = len(geographic_mentions)
            geographic_reach = zones_touched / total_zones if total_zones > 0 else 0
            
            # Calculer le score d'influence par zone
            influence_distribution = {}
            total_population = sum(data['population'] for data in self.geographic_zones.values())
            
            for zone, mentions in geographic_mentions.items():
                zone_data = self.geographic_zones.get(zone, {})
                population_ratio = zone_data.get('population', 0) / total_population
                influence_score = mentions * population_ratio * zone_data.get('influence', 0)
                influence_distribution[zone] = {
                    'mentions': mentions,
                    'population_ratio': round(population_ratio, 3),
                    'influence_score': round(influence_score, 3)
                }
            
            return {
                'zones_touched': zones_touched,
                'total_zones': total_zones,
                'geographic_reach': round(geographic_reach, 3),
                'zone_mentions': dict(geographic_mentions),
                'influence_distribution': influence_distribution,
                'dominant_zone': max(geographic_mentions.items(), key=lambda x: x[1])[0] if geographic_mentions else None
            }
            
        except Exception as e:
            logger.error(f"Erreur propagation géographique: {e}")
            return {'zones_touched': 0, 'geographic_reach': 0, 'zone_mentions': {}}
    
    def _calculate_amplification_score(self, patterns: List[Dict], geographic_spread: Dict) -> Dict[str, Any]:
        """Calcule le score d'amplification global"""
        try:
            # Composantes du score
            velocity_score = 0
            engagement_score = 0
            influencer_score = 0
            geographic_score = geographic_spread.get('geographic_reach', 0)
            
            # Analyser les patterns
            for pattern in patterns:
                strength = pattern.get('pattern_strength', 0)
                
                if pattern['type'] == 'velocity_spike':
                    velocity_score = max(velocity_score, strength)
                elif pattern['type'] == 'engagement_cascade':
                    engagement_score = max(engagement_score, strength)
                elif pattern['type'] == 'influencer_amplification':
                    influencer_score = max(influencer_score, strength)
            
            # Score composite pondéré
            weights = {
                'velocity': 0.3,
                'engagement': 0.25,
                'influencer': 0.25,
                'geographic': 0.2
            }
            
            composite_score = (
                velocity_score * weights['velocity'] +
                engagement_score * weights['engagement'] +
                influencer_score * weights['influencer'] +
                geographic_score * weights['geographic']
            )
            
            # Niveau d'amplification
            if composite_score >= 0.8:
                amplification_level = 'viral'
            elif composite_score >= 0.6:
                amplification_level = 'high'
            elif composite_score >= 0.4:
                amplification_level = 'medium'
            elif composite_score >= 0.2:
                amplification_level = 'low'
            else:
                amplification_level = 'minimal'
            
            return {
                'composite_score': round(composite_score, 3),
                'amplification_level': amplification_level,
                'components': {
                    'velocity': round(velocity_score, 3),
                    'engagement': round(engagement_score, 3),
                    'influencer': round(influencer_score, 3),
                    'geographic': round(geographic_score, 3)
                },
                'pattern_count': len(patterns),
                'interpretation': self._interpret_amplification_level(amplification_level, composite_score)
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul score amplification: {e}")
            return {'composite_score': 0, 'amplification_level': 'minimal'}
    
    def _assess_amplification_risk(self, amplification_score: Dict) -> Dict[str, Any]:
        """Évalue le risque d'amplification"""
        level = amplification_score.get('amplification_level', 'minimal')
        score = amplification_score.get('composite_score', 0)
        
        risk_mapping = {
            'viral': {'risk_level': 'critical', 'response_time': 'immediate'},
            'high': {'risk_level': 'high', 'response_time': '1-2 hours'},
            'medium': {'risk_level': 'medium', 'response_time': '4-6 hours'},
            'low': {'risk_level': 'low', 'response_time': '12-24 hours'},
            'minimal': {'risk_level': 'minimal', 'response_time': 'routine'}
        }
        
        risk_info = risk_mapping.get(level, risk_mapping['minimal'])
        
        # Facteurs de risque additionnels
        risk_factors = []
        if score > 0.7:
            risk_factors.append('high_amplification_potential')
        if amplification_score.get('components', {}).get('influencer', 0) > 0.5:
            risk_factors.append('influencer_involvement')
        if amplification_score.get('components', {}).get('geographic', 0) > 0.5:
            risk_factors.append('wide_geographic_spread')
        
        return {
            **risk_info,
            'risk_factors': risk_factors,
            'monitoring_priority': 'high' if level in ['viral', 'high'] else 'normal',
            'alert_recommended': level in ['viral', 'high'],
            'estimated_peak_time': self._estimate_peak_time(level, score)
        }
    
    def _identify_trending_content(self, patterns: List[Dict]) -> List[Dict]:
        """Identifie le contenu en tendance"""
        trending = []
        
        # Grouper par contenu/sujet
        content_scores = defaultdict(float)
        content_details = defaultdict(dict)
        
        for pattern in patterns:
            # Utiliser l'ID du post ou le hash comme identificateur
            content_id = pattern.get('post_id', pattern.get('content_hash', 'unknown'))
            strength = pattern.get('pattern_strength', 0)
            
            content_scores[content_id] += strength
            content_details[content_id].update({
                'platform': pattern.get('platform'),
                'type': pattern.get('type'),
                'latest_strength': strength
            })
        
        # Trier par score décroissant
        sorted_content = sorted(content_scores.items(), key=lambda x: x[1], reverse=True)
        
        for content_id, total_score in sorted_content[:5]:  # Top 5
            details = content_details[content_id]
            trending.append({
                'content_id': content_id,
                'trending_score': round(total_score, 3),
                'platform': details.get('platform', 'unknown'),
                'trend_type': details.get('type', 'unknown'),
                'trending_level': 'high' if total_score > 1.5 else 'medium' if total_score > 0.8 else 'emerging'
            })
        
        return trending
    
    def _predict_amplification_trajectory(self, patterns: List[Dict]) -> Dict[str, Any]:
        """Prédit la trajectoire d'amplification"""
        try:
            if not patterns:
                return {'trajectory': 'stable', 'confidence': 0}
            
            # Analyser les tendances des patterns
            velocity_patterns = [p for p in patterns if p['type'] == 'velocity_spike']
            engagement_patterns = [p for p in patterns if p['type'] == 'engagement_cascade']
            influencer_patterns = [p for p in patterns if p['type'] == 'influencer_amplification']
            
            # Facteurs de prédiction
            acceleration_factor = 0
            if velocity_patterns:
                max_velocity = max(p.get('spike_ratio', 0) for p in velocity_patterns)
                acceleration_factor = min(max_velocity / 10, 1.0)
            
            engagement_momentum = 0
            if engagement_patterns:
                max_cascade = max(p.get('cascade_strength', 0) for p in engagement_patterns)
                engagement_momentum = max_cascade
            
            influencer_boost = 0
            if influencer_patterns:
                max_amplification = max(p.get('amplification_factor', 0) for p in influencer_patterns)
                influencer_boost = min(max_amplification / 5, 1.0)
            
            # Score de trajectoire composite
            trajectory_score = (
                acceleration_factor * 0.4 +
                engagement_momentum * 0.35 +
                influencer_boost * 0.25
            )
            
            # Prédiction
            if trajectory_score > 0.7:
                trajectory = 'explosive_growth'
                peak_time = 'dans 1-3 heures'
                confidence = 0.8
            elif trajectory_score > 0.5:
                trajectory = 'rapid_growth'
                peak_time = 'dans 3-6 heures'
                confidence = 0.7
            elif trajectory_score > 0.3:
                trajectory = 'steady_growth'
                peak_time = 'dans 6-12 heures'
                confidence = 0.6
            elif trajectory_score > 0.15:
                trajectory = 'slow_growth'
                peak_time = 'dans 12-24 heures'
                confidence = 0.5
            else:
                trajectory = 'stable'
                peak_time = 'croissance limitée'
                confidence = 0.4
            
            return {
                'trajectory': trajectory,
                'trajectory_score': round(trajectory_score, 3),
                'predicted_peak_time': peak_time,
                'confidence': confidence,
                'contributing_factors': {
                    'velocity_acceleration': round(acceleration_factor, 3),
                    'engagement_momentum': round(engagement_momentum, 3),
                    'influencer_boost': round(influencer_boost, 3)
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur prédiction trajectoire: {e}")
            return {'trajectory': 'unknown', 'confidence': 0}
    
    def _interpret_amplification_level(self, level: str, score: float) -> str:
        """Interprète le niveau d'amplification"""
        interpretations = {
            'viral': 'Amplification virale critique - Action immédiate requise',
            'high': 'Amplification élevée - Surveillance renforcée recommandée',
            'medium': 'Amplification modérée - Suivi attentif nécessaire',
            'low': 'Amplification faible - Monitoring de routine',
            'minimal': 'Amplification minimale - Situation normale'
        }
        return interpretations.get(level, 'Niveau d\'amplification indéterminé')
    
    def _estimate_peak_time(self, level: str, score: float) -> str:
        """Estime le temps de pic d'amplification"""
        estimates = {
            'viral': '30 minutes - 2 heures',
            'high': '1-4 heures',
            'medium': '2-8 heures',
            'low': '4-12 heures',
            'minimal': '12+ heures'
        }
        return estimates.get(level, 'Indéterminé')
    
    def start_real_time_tracking(self, interval_minutes: int = 10):
        """Démarre le tracking temps réel"""
        if self.tracking_active:
            logger.warning("Tracking déjà actif")
            return
            
        self.tracking_active = True
        self.tracking_thread = threading.Thread(
            target=self._tracking_loop,
            args=(interval_minutes,),
            daemon=True
        )
        self.tracking_thread.start()
        logger.info(f"🎯 Tracking amplification démarré (intervalle: {interval_minutes}min)")
    
    def stop_real_time_tracking(self):
        """Arrête le tracking temps réel"""
        self.tracking_active = False
        if self.tracking_thread:
            self.tracking_thread.join(timeout=30)
        logger.info("⏹️ Tracking amplification arrêté")
    
    def _tracking_loop(self, interval_minutes: int):
        """Boucle de tracking temps réel"""
        while self.tracking_active:
            try:
                # Analyse d'amplification complète
                analysis = self.detect_amplification_patterns(hours_back=3)
                
                # Stocker l'événement si significatif
                risk = analysis.get('risk_level', {})
                if risk.get('alert_recommended', False):
                    self._store_amplification_event(analysis)
                    
                logger.info(f"Tracking amplification: {analysis.get('amplification_score', {}).get('amplification_level', 'unknown')}")
                
            except Exception as e:
                logger.error(f"Erreur tracking loop: {e}")
            
            time.sleep(interval_minutes * 60)
    
    def _store_amplification_event(self, analysis: Dict):
        """Stocke un événement d'amplification"""
        try:
            if not self.db:
                return
                
            event = {
                'timestamp': analysis['detection_timestamp'],
                'amplification_score': analysis['amplification_score']['composite_score'],
                'amplification_level': analysis['amplification_score']['amplification_level'],
                'patterns_detected': len(analysis['detected_patterns']),
                'geographic_reach': analysis['geographic_spread']['geographic_reach'],
                'risk_assessment': analysis.get('risk_level', {}),
                'trending_content': analysis.get('trending_content', []),
                'prediction': analysis.get('prediction', {}),
                'stored_at': datetime.now().isoformat()
            }
            
            self.db.amplification_events.insert_one(event)
            
            # Garder en mémoire
            amp_event = AmplificationEvent(
                timestamp=datetime.fromisoformat(analysis['detection_timestamp'].replace('Z', '+00:00')),
                content_hash=analysis.get('content_hash', 'auto_detected'),
                platform='multi_platform',
                engagement_spike=analysis['amplification_score']['components']['engagement'],
                propagation_velocity=analysis['amplification_score']['components']['velocity'],
                influence_score=analysis['amplification_score']['components']['influencer'],
                geographic_reach=int(analysis['geographic_spread']['zones_touched']),
                sentiment_shift=0.0  # À intégrer avec le service sentiment
            )
            
            self.amplification_events.append(amp_event)
            
        except Exception as e:
            logger.error(f"Erreur stockage événement amplification: {e}")
    
    def get_tracking_status(self) -> Dict[str, Any]:
        """Status du tracker"""
        return {
            'tracking_active': self.tracking_active,
            'cached_events': len(self.amplification_events),
            'active_trends': len(self.active_trends),
            'monitored_platforms': list(self.monitored_platforms.keys()),
            'database_connected': self.db is not None,
            'last_analysis': self.amplification_events[-1].timestamp.isoformat() if self.amplification_events else None,
            'service_status': 'operational' if self.db else 'degraded'
        }

# Instance globale
social_amplification = SocialAmplificationTracker()