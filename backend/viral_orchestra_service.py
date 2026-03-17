# backend/viral_orchestra_service.py
"""
Service Maître d'Orchestration Virale - Le chef d'orchestre de tous les services
Combine détection virale, amplification sociale, prédiction d'escalade et alertes
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import threading
import time

from pymongo import MongoClient
import certifi

# Imports des services boostés
try:
    from backend.viral_detection_service import viral_detector
    from backend.social_amplification_tracker import social_amplification
    from backend.viral_escalation_predictor import escalation_predictor
    from backend.media_noise_service import media_noise_service
    from backend.gpt_sentiment_service import gpt_sentiment_analyzer
    from backend.telegram_alerts_service import telegram_alerts
    from backend.population_reaction_service import PopulationReactionPredictor
except ImportError as e:
    logging.warning(f"Import service orchestration: {e}")

logger = logging.getLogger("viral_orchestra_service")

@dataclass
class ViralThreatLevel:
    """Niveau de menace virale consolidé"""
    level: str  # minimal, low, medium, high, critical
    score: float  # 0.0 - 1.0
    components: Dict[str, float]
    risk_factors: List[str]
    estimated_peak: datetime
    recommended_actions: List[str]
    confidence: float

@dataclass
class ViralEvent:
    """Événement viral détecté et analysé"""
    event_id: str
    detection_time: datetime
    threat_level: ViralThreatLevel
    content_hash: Optional[str]
    affected_platforms: List[str]
    geographic_spread: Dict[str, Any]
    sentiment_analysis: Dict[str, Any]
    prediction: Dict[str, Any]
    response_status: str

class ViralOrchestraService:
    """Service maître d'orchestration virale - Le système nerveux central"""
    
    def __init__(self):
        # MongoDB pour persistence
        self.mongo_client = self._get_mongo_client()
        self.db = self._get_database()
        
        # État du système
        self.orchestra_active = False
        self.orchestra_thread = None
        self.last_full_analysis = None
        
        # Cache des événements actifs
        self.active_viral_events: Dict[str, ViralEvent] = {}
        self.event_history = []
        
        # Configuration des seuils consolidés
        self.threat_thresholds = {
            'minimal': {'score': 0.0, 'response_time': 'none'},
            'low': {'score': 0.2, 'response_time': '24h'},
            'medium': {'score': 0.4, 'response_time': '6h'},
            'high': {'score': 0.6, 'response_time': '2h'},
            'critical': {'score': 0.8, 'response_time': '15min'}
        }
        
        # Poids des composantes pour le score consolidé
        self.component_weights = {
            'viral_detection': 0.30,
            'social_amplification': 0.25,
            'escalation_prediction': 0.25,
            'media_noise': 0.15,
            'sentiment_momentum': 0.05
        }
        
        logger.info("🎭 Viral Orchestra Service initialisé - Système nerveux central actif")
    
    def _get_mongo_client(self) -> Optional[MongoClient]:
        mongo_url = os.environ.get("MONGO_URL", "").strip()
        if not mongo_url:
            return None
        try:
            client = MongoClient(mongo_url, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)
            client.admin.command("ping")
            return client
        except Exception as e:
            logger.error(f"Erreur MongoDB orchestra: {e}")
            return None
    
    def _get_database(self):
        if not self.mongo_client:
            return None
        return self.mongo_client[os.environ.get("MONGO_DB_NAME", "veille_media")]
    
    async def comprehensive_viral_assessment(self, target_content: Optional[str] = None, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Évaluation virale complète orchestrant tous les services"""
        assessment_start = datetime.now()
        
        try:
            logger.info(f"🎭 Démarrage évaluation virale complète - Target: {target_content or 'auto-detect'}")
            
            # 1. Détection virale (service principal)
            viral_analysis = await self._run_viral_detection(target_content)
            
            # 2. Analyse d'amplification sociale
            amplification_analysis = await self._run_amplification_tracking(target_content)
            
            # 3. Prédiction d'escalade
            escalation_prediction = await self._run_escalation_prediction(viral_analysis, amplification_analysis, context)
            
            # 4. Analyse du bruit médiatique
            media_noise_analysis = await self._run_media_noise_analysis(target_content)
            
            # 5. Analyse de sentiment consolidée
            sentiment_analysis = await self._run_sentiment_analysis(target_content, viral_analysis)
            
            # 6. Calcul du niveau de menace consolidé
            threat_level = self._calculate_consolidated_threat_level(
                viral_analysis, amplification_analysis, escalation_prediction,
                media_noise_analysis, sentiment_analysis
            )
            
            # 7. Génération des recommandations stratégiques
            strategic_recommendations = self._generate_strategic_recommendations(
                threat_level, viral_analysis, amplification_analysis, escalation_prediction
            )
            
            # 8. Évaluation de l'impact populationnel
            population_impact = await self._assess_population_impact(
                target_content, threat_level, sentiment_analysis
            )
            
            # 9. Compilation du rapport final
            comprehensive_report = {
                'assessment_id': f"viral_assessment_{int(assessment_start.timestamp())}",
                'timestamp': assessment_start.isoformat(),
                'target_content': target_content,
                'context': context,
                'threat_level': asdict(threat_level),
                'component_analyses': {
                    'viral_detection': viral_analysis,
                    'social_amplification': amplification_analysis,
                    'escalation_prediction': asdict(escalation_prediction) if escalation_prediction else None,
                    'media_noise': media_noise_analysis,
                    'sentiment_analysis': sentiment_analysis
                },
                'strategic_recommendations': strategic_recommendations,
                'population_impact': population_impact,
                'analysis_metadata': {
                    'duration_seconds': (datetime.now() - assessment_start).total_seconds(),
                    'services_involved': self._get_active_services(),
                    'confidence_level': threat_level.confidence,
                    'assessment_version': '2.0'
                }
            }
            
            # 10. Stockage et déclenchement d'alertes si nécessaire
            await self._process_assessment_results(comprehensive_report, threat_level)
            
            self.last_full_analysis = datetime.now()
            
            logger.info(f"✅ Évaluation complète terminée - Threat level: {threat_level.level} ({threat_level.score:.3f})")
            
            return comprehensive_report
            
        except Exception as e:
            logger.error(f"Erreur évaluation virale complète: {e}")
            return await self._generate_error_report(str(e), assessment_start)
    
    async def _run_viral_detection(self, target_content: Optional[str]) -> Dict[str, Any]:
        """Exécute l'analyse de détection virale"""
        try:
            if hasattr(viral_detector, 'comprehensive_viral_analysis'):
                return viral_detector.comprehensive_viral_analysis(target_content, auto_detect=True)
            else:
                return {'error': 'Viral detector service unavailable', 'score': 0}
        except Exception as e:
            logger.error(f"Erreur viral detection: {e}")
            return {'error': str(e), 'score': 0}
    
    async def _run_amplification_tracking(self, target_content: Optional[str]) -> Dict[str, Any]:
        """Exécute l'analyse d'amplification sociale"""
        try:
            if hasattr(social_amplification, 'detect_amplification_patterns'):
                content_hash = self._generate_content_hash(target_content) if target_content else None
                return social_amplification.detect_amplification_patterns(content_hash, hours_back=6)
            else:
                return {'error': 'Social amplification service unavailable', 'amplification_score': {'composite_score': 0}}
        except Exception as e:
            logger.error(f"Erreur amplification tracking: {e}")
            return {'error': str(e), 'amplification_score': {'composite_score': 0}}
    
    async def _run_escalation_prediction(self, viral_analysis: Dict, amplification_analysis: Dict, context: Optional[Dict]):
        """Exécute la prédiction d'escalade"""
        try:
            if hasattr(escalation_predictor, 'predict_escalation'):
                combined_metrics = {
                    **viral_analysis,
                    **amplification_analysis
                }
                return escalation_predictor.predict_escalation(combined_metrics, context)
            else:
                return None
        except Exception as e:
            logger.error(f"Erreur escalation prediction: {e}")
            return None
    
    async def _run_media_noise_analysis(self, target_content: Optional[str]) -> Dict[str, Any]:
        """Exécute l'analyse du bruit médiatique"""
        try:
            if hasattr(media_noise_service, 'calculate_media_noise'):
                # Analyser les dernières 24h avec focus sur le contenu cible
                return media_noise_service.calculate_media_noise(period="24h")
            else:
                return {'error': 'Media noise service unavailable', 'noise_score': 0}
        except Exception as e:
            logger.error(f"Erreur media noise analysis: {e}")
            return {'error': str(e), 'noise_score': 0}
    
    async def _run_sentiment_analysis(self, target_content: Optional[str], viral_analysis: Dict) -> Dict[str, Any]:
        """Exécute l'analyse de sentiment consolidée"""
        try:
            if target_content and hasattr(gpt_sentiment_analyzer, 'analyze_sentiment'):
                sentiment_result = gpt_sentiment_analyzer.analyze_sentiment(target_content)
                
                # Enrichir avec les données du momentum viral
                sentiment_momentum = viral_analysis.get('sentiment_momentum', {})
                sentiment_result['viral_momentum'] = sentiment_momentum
                
                return sentiment_result
            else:
                return {'error': 'No content to analyze or sentiment service unavailable', 'score': 0}
        except Exception as e:
            logger.error(f"Erreur sentiment analysis: {e}")
            return {'error': str(e), 'score': 0}
    
    def _calculate_consolidated_threat_level(self, viral_analysis: Dict, amplification_analysis: Dict, 
                                           escalation_prediction, media_noise_analysis: Dict, 
                                           sentiment_analysis: Dict) -> ViralThreatLevel:
        """Calcule le niveau de menace consolidé"""
        try:
            # Extraction des scores individuels
            viral_score = viral_analysis.get('viral_score', {}).get('composite_score', 0)
            amplification_score = amplification_analysis.get('amplification_score', {}).get('composite_score', 0)
            escalation_score = escalation_prediction.probability if escalation_prediction else 0
            media_noise_score = media_noise_analysis.get('noise_score', 0) / 100  # Normaliser sur 0-1
            sentiment_momentum_score = abs(sentiment_analysis.get('score', 0))
            
            # Score consolidé pondéré
            weights = self.component_weights
            consolidated_score = (
                viral_score * weights['viral_detection'] +
                amplification_score * weights['social_amplification'] +
                escalation_score * weights['escalation_prediction'] +
                media_noise_score * weights['media_noise'] +
                sentiment_momentum_score * weights['sentiment_momentum']
            )
            
            # Détermination du niveau de menace
            threat_level_name = 'minimal'
            for level, threshold in sorted(self.threat_thresholds.items(), key=lambda x: x[1]['score'], reverse=True):
                if consolidated_score >= threshold['score']:
                    threat_level_name = level
                    break
            
            # Collecte des facteurs de risque
            risk_factors = []
            if viral_score > 0.5:
                risk_factors.extend(viral_analysis.get('risk_assessment', {}).get('risk_factors', []))
            if amplification_score > 0.5:
                risk_factors.append('high_social_amplification')
            if escalation_score > 0.6:
                risk_factors.append('escalation_probable')
            if media_noise_score > 0.6:
                risk_factors.append('high_media_noise')
            if sentiment_momentum_score > 0.4:
                risk_factors.append('significant_sentiment_shift')
            
            # Estimation du pic
            estimated_peak = datetime.now() + timedelta(hours=6)  # Par défaut
            if escalation_prediction:
                estimated_peak = escalation_prediction.peak_time
            
            # Actions recommandées
            recommended_actions = self._generate_threat_actions(threat_level_name, risk_factors)
            
            # Calcul de la confiance
            confidence = self._calculate_confidence_score(viral_analysis, amplification_analysis, escalation_prediction)
            
            return ViralThreatLevel(
                level=threat_level_name,
                score=round(consolidated_score, 3),
                components={
                    'viral_detection': round(viral_score, 3),
                    'social_amplification': round(amplification_score, 3),
                    'escalation_prediction': round(escalation_score, 3),
                    'media_noise': round(media_noise_score, 3),
                    'sentiment_momentum': round(sentiment_momentum_score, 3)
                },
                risk_factors=list(set(risk_factors)),
                estimated_peak=estimated_peak,
                recommended_actions=recommended_actions,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"Erreur calcul threat level: {e}")
            return ViralThreatLevel(
                level='minimal',
                score=0.0,
                components={},
                risk_factors=['calculation_error'],
                estimated_peak=datetime.now(),
                recommended_actions=['Vérifier les services'],
                confidence=0.0
            )
    
    def _generate_threat_actions(self, threat_level: str, risk_factors: List[str]) -> List[str]:
        """Génère les actions recommandées selon le niveau de menace"""
        actions = []
        
        if threat_level == 'critical':
            actions.extend([
                "🚨 ACTIVATION CELLULE DE CRISE IMMÉDIATE",
                "📱 Notification direction générale",
                "📺 Préparation communication médias",
                "🎯 Monitoring temps réel toutes plateformes",
                "⚡ Réponse proactive dans les 15 minutes"
            ])
        
        elif threat_level == 'high':
            actions.extend([
                "⚠️ Alerte équipe communication - Niveau élevé",
                "📋 Activation protocole surveillance renforcée",
                "📝 Préparation éléments de réponse",
                "🔍 Identification sources d'amplification",
                "⏱️ Réponse dans les 2 heures"
            ])
        
        elif threat_level == 'medium':
            actions.extend([
                "👀 Surveillance attentive continue",
                "📊 Collecte données complémentaires",
                "💬 Préparation messages préventifs",
                "🌐 Monitoring étendu réseaux sociaux"
            ])
        
        elif threat_level == 'low':
            actions.extend([
                "📈 Monitoring de routine renforcé",
                "📋 Documentation pattern détecté"
            ])
        
        # Actions spécifiques aux facteurs de risque
        if 'high_social_amplification' in risk_factors:
            actions.append("🌐 Coordination réponse multi-plateformes")
        
        if 'escalation_probable' in risk_factors:
            actions.append("⏰ Préparation escalade rapide")
        
        if 'significant_sentiment_shift' in risk_factors:
            actions.append("💭 Stratégie gestion sentiment")
        
        return actions
    
    def _generate_strategic_recommendations(self, threat_level: ViralThreatLevel, viral_analysis: Dict, 
                                          amplification_analysis: Dict, escalation_prediction) -> Dict[str, Any]:
        """Génère les recommandations stratégiques consolidées"""
        recommendations = {
            'immediate_actions': threat_level.recommended_actions,
            'communication_strategy': [],
            'monitoring_priorities': [],
            'resource_allocation': {},
            'timeline': {}
        }
        
        # Stratégie de communication selon le niveau
        if threat_level.level in ['critical', 'high']:
            recommendations['communication_strategy'] = [
                "Message proactif et transparent",
                "Ton empathique et responsable",
                "Faits vérifiés et sources fiables",
                "Réponse coordonnée multi-canaux"
            ]
        elif threat_level.level == 'medium':
            recommendations['communication_strategy'] = [
                "Surveillance des narratifs émergents",
                "Préparation éléments de langage",
                "Identification relais positifs"
            ]
        
        # Priorités de monitoring
        if viral_analysis.get('cross_platform_analysis', {}).get('is_cross_platform', False):
            recommendations['monitoring_priorities'].append("Surveillance multi-plateformes")
        
        if amplification_analysis.get('amplification_score', {}).get('amplification_level') in ['high', 'viral']:
            recommendations['monitoring_priorities'].append("Tracking influenceurs et amplificateurs")
        
        # Allocation des ressources
        if threat_level.level == 'critical':
            recommendations['resource_allocation'] = {
                'communication_team': '100% - Mobilisation complète',
                'monitoring_team': '24/7 - Surveillance continue',
                'decision_makers': 'Disponibilité immédiate'
            }
        elif threat_level.level == 'high':
            recommendations['resource_allocation'] = {
                'communication_team': '75% - Préparation active',
                'monitoring_team': 'Renforcée - Vérifications fréquentes'
            }
        
        # Timeline d'actions
        if escalation_prediction:
            recommendations['timeline'] = {
                'immediate': '0-30 min - Actions prioritaires',
                'short_term': f"30 min - 2h - Avant pic estimé à {escalation_prediction.peak_time.strftime('%H:%M')}",
                'medium_term': '2-8h - Gestion post-pic',
                'follow_up': '8-24h - Évaluation et apprentissage'
            }
        
        return recommendations
    
    async def _assess_population_impact(self, target_content: Optional[str], threat_level: ViralThreatLevel, 
                                       sentiment_analysis: Dict) -> Dict[str, Any]:
        """Évalue l'impact sur la population"""
        try:
            impact_assessment = {
                'estimated_reach': 0,
                'affected_demographics': [],
                'emotional_impact': 'neutral',
                'behavioral_predictions': [],
                'geographic_impact': {}
            }
            
            # Estimer la portée selon le niveau de menace
            base_reach = {
                'minimal': 1000,
                'low': 5000,
                'medium': 15000,
                'high': 50000,
                'critical': 150000
            }
            
            impact_assessment['estimated_reach'] = base_reach.get(threat_level.level, 1000)
            
            # Impact émotionnel basé sur le sentiment
            sentiment_score = sentiment_analysis.get('score', 0)
            if sentiment_score < -0.3:
                impact_assessment['emotional_impact'] = 'négatif_fort'
                impact_assessment['behavioral_predictions'] = [
                    'Discussions accrues réseaux sociaux',
                    'Possible mobilisation citoyenne',
                    'Demandes d\'informations officielles'
                ]
            elif sentiment_score > 0.3:
                impact_assessment['emotional_impact'] = 'positif'
                impact_assessment['behavioral_predictions'] = [
                    'Partages et engagement positifs',
                    'Amplification naturelle du message'
                ]
            
            # Utiliser le prédicteur de réaction si disponible
            if target_content and 'PopulationReactionPredictor' in globals():
                try:
                    reaction_predictor = PopulationReactionPredictor()
                    population_reaction = reaction_predictor.analyze_population_reaction(target_content)
                    impact_assessment['detailed_reaction'] = population_reaction
                except Exception as e:
                    logger.warning(f"Population reaction predictor error: {e}")
            
            return impact_assessment
            
        except Exception as e:
            logger.error(f"Erreur évaluation impact population: {e}")
            return {'error': str(e), 'estimated_reach': 0}
    
    async def _process_assessment_results(self, report: Dict, threat_level: ViralThreatLevel):
        """Traite les résultats d'évaluation (stockage, alertes)"""
        try:
            # 1. Stockage en base
            if self.db:
                self.db.viral_assessments.insert_one(report)
            
            # 2. Créer un événement viral si nécessaire
            if threat_level.level in ['medium', 'high', 'critical']:
                event = ViralEvent(
                    event_id=report['assessment_id'],
                    detection_time=datetime.fromisoformat(report['timestamp'].replace('Z', '')),
                    threat_level=threat_level,
                    content_hash=self._generate_content_hash(report.get('target_content')),
                    affected_platforms=self._extract_affected_platforms(report),
                    geographic_spread=report.get('component_analyses', {}).get('viral_detection', {}).get('geographic_spread', {}),
                    sentiment_analysis=report.get('component_analyses', {}).get('sentiment_analysis', {}),
                    prediction=report.get('component_analyses', {}).get('escalation_prediction', {}),
                    response_status='detected'
                )
                
                self.active_viral_events[event.event_id] = event
            
            # 3. Déclenchement d'alertes
            if threat_level.level in ['high', 'critical']:
                await self._send_alert(report, threat_level)
            
        except Exception as e:
            logger.error(f"Erreur traitement résultats: {e}")
    
    async def _send_alert(self, report: Dict, threat_level: ViralThreatLevel):
        """Envoie une alerte consolidée"""
        try:
            alert_message = self._format_alert_message(report, threat_level)
            
            # Alerte Telegram
            if hasattr(telegram_alerts, 'send_alert_sync'):
                success = telegram_alerts.send_alert_sync(alert_message)
                if success:
                    logger.info("✅ Alerte consolidée envoyée via Telegram")
                else:
                    logger.warning("⚠️ Échec envoi alerte Telegram")
            
        except Exception as e:
            logger.error(f"Erreur envoi alerte: {e}")
    
    def _format_alert_message(self, report: Dict, threat_level: ViralThreatLevel) -> str:
        """Formate le message d'alerte consolidé"""
        content = report.get('target_content', 'Contenu auto-détecté')[:100]
        timestamp = datetime.now().strftime('%d/%m/%Y à %H:%M')
        
        alert_message = f"""🎭 ALERTE VIRALE CONSOLIDÉE

🚨 **Niveau de menace:** {threat_level.level.upper()}
📊 **Score consolidé:** {threat_level.score:.3f}/1.0
🎯 **Contenu:** {content}{'...' if len(content) >= 100 else ''}

📈 **Composantes détectées:**
• Détection virale: {threat_level.components.get('viral_detection', 0):.2f}
• Amplification sociale: {threat_level.components.get('social_amplification', 0):.2f}
• Prédiction escalade: {threat_level.components.get('escalation_prediction', 0):.2f}
• Bruit médiatique: {threat_level.components.get('media_noise', 0):.2f}

⚠️ **Facteurs de risque:**
{chr(10).join(f"• {factor}" for factor in threat_level.risk_factors[:5])}

🎯 **Actions recommandées:**
{chr(10).join(f"• {action}" for action in threat_level.recommended_actions[:3])}

⏰ **Pic estimé:** {threat_level.estimated_peak.strftime('%d/%m à %H:%M')}
🎯 **Confiance:** {threat_level.confidence:.1%}

⏰ **Détecté le:** {timestamp}
🎭 **Orchestra Service v2.0**"""

        return alert_message
    
    def start_orchestra_monitoring(self, interval_minutes: int = 20):
        """Démarre le monitoring orchestré"""
        if self.orchestra_active:
            logger.warning("Orchestra monitoring déjà actif")
            return
        
        self.orchestra_active = True
        self.orchestra_thread = threading.Thread(
            target=self._orchestra_loop,
            args=(interval_minutes,),
            daemon=True
        )
        self.orchestra_thread.start()
        logger.info(f"🎭 Orchestra monitoring démarré (intervalle: {interval_minutes}min)")
    
    def stop_orchestra_monitoring(self):
        """Arrête le monitoring orchestré"""
        self.orchestra_active = False
        if self.orchestra_thread:
            self.orchestra_thread.join(timeout=60)
        logger.info("🎭 Orchestra monitoring arrêté")
    
    def _orchestra_loop(self, interval_minutes: int):
        """Boucle principale d'orchestration"""
        while self.orchestra_active:
            try:
                # Évaluation complète asynchrone
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                assessment = loop.run_until_complete(
                    self.comprehensive_viral_assessment()
                )
                
                threat_level = assessment.get('threat_level', {})
                logger.info(f"🎭 Assessment orchestré: {threat_level.get('level', 'unknown')} ({threat_level.get('score', 0):.3f})")
                
                loop.close()
                
            except Exception as e:
                logger.error(f"Erreur orchestra loop: {e}")
            
            time.sleep(interval_minutes * 60)
    
    def _generate_content_hash(self, content: Optional[str]) -> Optional[str]:
        """Génère un hash du contenu pour tracking"""
        if not content:
            return None
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()
    
    def _extract_affected_platforms(self, report: Dict) -> List[str]:
        """Extrait les plateformes affectées du rapport"""
        platforms = []
        
        # Viral analysis
        viral_platforms = report.get('component_analyses', {}).get('viral_detection', {}).get('cross_platform_analysis', {}).get('platforms_detected', [])
        platforms.extend(viral_platforms)
        
        # Amplification analysis
        amp_platforms = report.get('component_analyses', {}).get('social_amplification', {}).get('detected_patterns', [])
        for pattern in amp_platforms:
            platform = pattern.get('platform')
            if platform and platform not in platforms:
                platforms.append(platform)
        
        return platforms
    
    def _calculate_confidence_score(self, viral_analysis: Dict, amplification_analysis: Dict, escalation_prediction) -> float:
        """Calcule le score de confiance global"""
        confidence_factors = []
        
        # Confiance de chaque composant
        viral_conf = viral_analysis.get('analysis_metadata', {}).get('confidence', 0.5)
        confidence_factors.append(viral_conf)
        
        amp_conf = 0.7  # Fixe pour l'amplification (basé sur des métriques observables)
        confidence_factors.append(amp_conf)
        
        if escalation_prediction:
            pred_conf = 0.6  # Confiance prédictive modérée
            confidence_factors.append(pred_conf)
        
        # Ajustements basés sur la cohérence des résultats
        if len(confidence_factors) > 1:
            std_dev = np.std(confidence_factors)
            if std_dev < 0.1:  # Résultats cohérents
                base_confidence = np.mean(confidence_factors) * 1.1
            else:
                base_confidence = np.mean(confidence_factors) * 0.9
        else:
            base_confidence = confidence_factors[0] if confidence_factors else 0.5
        
        return min(max(base_confidence, 0.0), 1.0)
    
    def _get_active_services(self) -> List[str]:
        """Retourne la liste des services actifs"""
        services = []
        service_checks = [
            ('viral_detector', 'viral_detection'),
            ('social_amplification', 'social_amplification'),
            ('escalation_predictor', 'escalation_prediction'),
            ('media_noise_service', 'media_noise'),
            ('gpt_sentiment_analyzer', 'sentiment_analysis'),
            ('telegram_alerts', 'telegram_alerts')
        ]
        
        for service_var, service_name in service_checks:
            try:
                if service_var in globals():
                    services.append(service_name)
            except:
                pass
        
        return services
    
    async def _generate_error_report(self, error_msg: str, start_time: datetime) -> Dict[str, Any]:
        """Génère un rapport d'erreur"""
        return {
            'assessment_id': f"error_{int(start_time.timestamp())}",
            'timestamp': start_time.isoformat(),
            'error': error_msg,
            'threat_level': {
                'level': 'unknown',
                'score': 0.0,
                'confidence': 0.0
            },
            'status': 'error'
        }
    
    def get_orchestra_status(self) -> Dict[str, Any]:
        """Status de l'orchestrateur"""
        return {
            'orchestra_active': self.orchestra_active,
            'active_viral_events': len(self.active_viral_events),
            'last_full_analysis': self.last_full_analysis.isoformat() if self.last_full_analysis else None,
            'active_services': self._get_active_services(),
            'threat_thresholds': self.threat_thresholds,
            'component_weights': self.component_weights,
            'database_connected': self.db is not None,
            'service_status': 'operational' if self.db else 'degraded'
        }

# Instance globale
viral_orchestra = ViralOrchestraService()