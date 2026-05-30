# backend/media_noise_detection_mistral.py
"""
Détection du bruit médiatique basée sur les classifications Mistral
Analyse la saturation informationnelle et les patterns de désinformation
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict
import json

logger = logging.getLogger("media_noise_detection")

class MediaNoiseDetectionMistral:
    """Détecteur de bruit médiatique utilisant les données enrichies Mistral"""
    
    def __init__(self, db, guadeloupe_scraper, ai_service):
        self.db = db
        self.scraper = guadeloupe_scraper
        self.ai_service = ai_service
        
        # Seuils de bruit médiatique
        self.noise_thresholds = {
            'volume_spike': 5.0,           # Articles/heure vs normal
            'repetition_ratio': 0.6,       # Contenu répétitif
            'low_importance_flood': 0.7,   # Flood d'articles peu importants
            'entity_saturation': 4.0,      # Sur-représentation entité
            'theme_monopolization': 0.8    # Monopolisation thématique
        }
        
        # Patterns de désinformation détectables
        self.disinfo_patterns = {
            'emotional_amplifiers': ['scandale', 'choc', 'incroyable', 'urgent', 'alerte'],
            'polarization_markers': ['tous', 'jamais', 'toujours', 'impossible', 'catastrophique'],
            'authority_attacks': ['incompétent', 'menteur', 'corruption', 'trahison'],
            'fake_exclusivity': ['exclusif', 'révélation', 'caché', 'secret']
        }
        
        logger.info("🔊 Détecteur de bruit médiatique Mistral initialisé")
    
    def detect_media_noise(self, hours_back: int = 12) -> Dict[str, Any]:
        """Détecte le bruit médiatique global"""
        try:
            since = datetime.now() - timedelta(hours=hours_back)
            
            # 1. Récupérer les articles avec classifications
            articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {"$gte": since.isoformat()},
                "analysis_method": {"$in": ["mistral_optimized", "mistral"]}
            }).sort("scraped_at", -1))
            
            if not articles:
                return {'noise_level': 'low', 'noise_score': 0}
            
            # 2. Analyser les composants du bruit
            volume_analysis = self._analyze_volume_patterns(articles, hours_back)
            repetition_analysis = self._analyze_content_repetition(articles)
            importance_analysis = self._analyze_importance_distribution(articles)
            entity_analysis = self._analyze_entity_saturation(articles)
            theme_analysis = self._analyze_theme_distribution(articles)
            
            # 3. Détecter les patterns de désinformation
            disinfo_analysis = self._detect_disinformation_patterns(articles)
            
            # 4. Analyser les réseaux sociaux si disponibles
            social_noise = await self._analyze_social_media_noise(hours_back)
            
            # 5. Calcul du score de bruit composite
            noise_components = {
                'volume_spike': volume_analysis.get('spike_factor', 0),
                'content_repetition': repetition_analysis.get('repetition_score', 0),
                'low_importance_flood': importance_analysis.get('flood_score', 0),
                'entity_saturation': entity_analysis.get('saturation_score', 0),
                'theme_monopolization': theme_analysis.get('monopolization_score', 0),
                'disinformation_indicators': disinfo_analysis.get('disinfo_score', 0),
                'social_amplification': social_noise.get('amplification_score', 0)
            }
            
            composite_noise_score = self._calculate_composite_noise_score(noise_components)
            noise_level = self._classify_noise_level(composite_noise_score)
            
            return {
                'noise_score': composite_noise_score,
                'noise_level': noise_level,
                'analysis_period': f"{hours_back}h",
                'articles_analyzed': len(articles),
                'components': noise_components,
                'detailed_analysis': {
                    'volume_patterns': volume_analysis,
                    'repetition_analysis': repetition_analysis,
                    'importance_distribution': importance_analysis,
                    'entity_saturation': entity_analysis,
                    'theme_distribution': theme_analysis,
                    'disinformation_patterns': disinfo_analysis,
                    'social_media_noise': social_noise
                },
                'recommendations': self._generate_noise_recommendations(noise_level, noise_components),
                'analyzed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur détection bruit médiatique: {e}")
            return {'noise_score': 0, 'error': str(e)}
    
    def _analyze_volume_patterns(self, articles: List[Dict], hours_back: int) -> Dict[str, Any]:
        """Analyse les patterns de volume de publication"""
        try:
            # Compter par heure
            hourly_counts = defaultdict(int)
            for article in articles:
                scraped_at = datetime.fromisoformat(article.get('scraped_at', ''))
                hour_key = scraped_at.strftime('%Y-%m-%d-%H')
                hourly_counts[hour_key] += 1
            
            if not hourly_counts:
                return {'spike_factor': 0}
            
            # Calculer baseline (moyenne des 7 derniers jours, même heures)
            baseline_start = datetime.now() - timedelta(days=7)
            baseline_end = datetime.now() - timedelta(hours=hours_back)
            
            baseline_articles = list(self.db.articles_guadeloupe.find({
                "scraped_at": {
                    "$gte": baseline_start.isoformat(),
                    "$lt": baseline_end.isoformat()
                }
            }, {"scraped_at": 1}))
            
            baseline_hourly = defaultdict(int)
            for article in baseline_articles:
                scraped_at = datetime.fromisoformat(article.get('scraped_at', ''))
                hour_key = scraped_at.strftime('%H')  # Juste l'heure
                baseline_hourly[hour_key] += 1
            
            # Calculer le spike factor
            current_rate = len(articles) / hours_back
            baseline_rate = sum(baseline_hourly.values()) / (7 * 24) * hours_back
            spike_factor = current_rate / max(baseline_rate, 1)
            
            return {
                'current_rate': round(current_rate, 2),
                'baseline_rate': round(baseline_rate, 2),
                'spike_factor': round(spike_factor, 2),
                'is_spike': spike_factor >= self.noise_thresholds['volume_spike'],
                'hourly_distribution': dict(hourly_counts)
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse volume: {e}")
            return {'spike_factor': 0}
    
    def _analyze_content_repetition(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyse la répétition de contenu"""
        try:
            # Analyser les titres similaires
            title_similarity = defaultdict(list)
            entity_repetition = Counter()
            theme_repetition = Counter()
            
            for article in articles:
                title = article.get('title', '').lower()
                entity = article.get('primary_entity', 'Aucune')
                theme = article.get('theme', 'general')
                
                # Regrouper par entité
                entity_repetition[entity] += 1
                theme_repetition[theme] += 1
                
                # Analyser similarité des titres (mots communs)
                title_words = set(title.split())
                if len(title_words) > 3:
                    title_key = ' '.join(sorted(title_words)[:4])  # 4 premiers mots triés
                    title_similarity[title_key].append(article)
            
            # Détecter les répétitions excessives
            repetitive_titles = {k: v for k, v in title_similarity.items() if len(v) > 2}
            repetitive_entities = {k: v for k, v in entity_repetition.items() if v > 3 and k != 'Aucune'}
            
            # Score de répétition
            total_articles = len(articles)
            repetition_count = sum(len(v) for v in repetitive_titles.values())
            repetition_score = repetition_count / total_articles if total_articles > 0 else 0
            
            return {
                'repetition_score': round(repetition_score, 3),
                'repetitive_titles': len(repetitive_titles),
                'repetitive_entities': repetitive_entities,
                'theme_concentration': dict(theme_repetition.most_common(5)),
                'is_repetitive': repetition_score >= self.noise_thresholds['repetition_ratio']
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse répétition: {e}")
            return {'repetition_score': 0}
    
    def _analyze_importance_distribution(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyse la distribution des scores d'importance"""
        try:
            importance_scores = [article.get('importance_score', 0) for article in articles]
            
            if not importance_scores:
                return {'flood_score': 0}
            
            # Statistiques de distribution
            avg_importance = sum(importance_scores) / len(importance_scores)
            low_importance_count = sum(1 for score in importance_scores if score < 0.4)
            high_importance_count = sum(1 for score in importance_scores if score >= 0.7)
            
            # Score de flood (trop d'articles peu importants)
            low_importance_ratio = low_importance_count / len(importance_scores)
            flood_score = low_importance_ratio if low_importance_count > 5 else 0
            
            return {
                'avg_importance': round(avg_importance, 3),
                'low_importance_ratio': round(low_importance_ratio, 3),
                'high_importance_count': high_importance_count,
                'flood_score': round(flood_score, 3),
                'is_flood': flood_score >= self.noise_thresholds['low_importance_flood'],
                'distribution': {
                    'low': low_importance_count,
                    'medium': len(importance_scores) - low_importance_count - high_importance_count,
                    'high': high_importance_count
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse importance: {e}")
            return {'flood_score': 0}
    
    def _analyze_entity_saturation(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyse la saturation par entité"""
        try:
            entity_counts = Counter()
            entity_importance = defaultdict(list)
            
            for article in articles:
                entity = article.get('primary_entity', 'Aucune')
                importance = article.get('importance_score', 0)
                
                if entity != 'Aucune':
                    entity_counts[entity] += 1
                    entity_importance[entity].append(importance)
            
            # Détecter la saturation
            saturated_entities = []
            total_articles = len(articles)
            
            for entity, count in entity_counts.most_common(10):
                ratio = count / total_articles
                avg_importance = sum(entity_importance[entity]) / len(entity_importance[entity])
                
                # Saturation = beaucoup d'articles mais importance faible
                saturation_factor = (ratio * 10) / max(avg_importance, 0.1)
                
                if saturation_factor >= self.noise_thresholds['entity_saturation']:
                    saturated_entities.append({
                        'entity': entity,
                        'article_count': count,
                        'ratio': round(ratio, 3),
                        'avg_importance': round(avg_importance, 3),
                        'saturation_factor': round(saturation_factor, 2)
                    })
            
            max_saturation = max([e['saturation_factor'] for e in saturated_entities]) if saturated_entities else 0
            
            return {
                'saturated_entities': saturated_entities,
                'saturation_score': min(max_saturation / 10, 1.0),
                'entity_distribution': dict(entity_counts.most_common(5)),
                'is_saturated': len(saturated_entities) > 0
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse saturation entité: {e}")
            return {'saturation_score': 0}
    
    def _analyze_theme_distribution(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyse la monopolisation thématique"""
        try:
            theme_counts = Counter()
            for article in articles:
                theme = article.get('theme', 'general')
                theme_counts[theme] += 1
            
            if not theme_counts:
                return {'monopolization_score': 0}
            
            # Calculer l'entropie thématique (diversité)
            total = sum(theme_counts.values())
            entropy = 0
            
            for count in theme_counts.values():
                p = count / total
                if p > 0:
                    entropy -= p * (p.bit_length() - 1)  # Approximation log2
            
            # Score de monopolisation (inverse de la diversité)
            max_possible_entropy = (len(theme_counts).bit_length() - 1) if len(theme_counts) > 1 else 1
            monopolization_score = 1 - (entropy / max_possible_entropy) if max_possible_entropy > 0 else 0
            
            # Thème dominant
            dominant_theme = theme_counts.most_common(1)[0] if theme_counts else ('general', 0)
            dominance_ratio = dominant_theme[1] / total if total > 0 else 0
            
            return {
                'monopolization_score': round(monopolization_score, 3),
                'theme_entropy': round(entropy, 3),
                'dominant_theme': dominant_theme[0],
                'dominance_ratio': round(dominance_ratio, 3),
                'theme_distribution': dict(theme_counts),
                'is_monopolized': monopolization_score >= self.noise_thresholds['theme_monopolization']
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse thèmes: {e}")
            return {'monopolization_score': 0}
    
    def _detect_disinformation_patterns(self, articles: List[Dict]) -> Dict[str, Any]:
        """Détecte les patterns de désinformation"""
        try:
            disinfo_indicators = defaultdict(int)
            suspicious_articles = []
            
            for article in articles:
                title = article.get('title', '').lower()
                content = article.get('content', '').lower()
                full_text = f"{title} {content}"
                
                article_indicators = []
                article_score = 0
                
                # Analyser chaque pattern
                for pattern_type, keywords in self.disinfo_patterns.items():
                    matches = sum(1 for keyword in keywords if keyword in full_text)
                    if matches > 0:
                        disinfo_indicators[pattern_type] += matches
                        article_indicators.append(f"{pattern_type}:{matches}")
                        article_score += matches * 0.2
                
                # Articles suspects (score élevé + faible importance Mistral)
                importance = article.get('importance_score', 0)
                if article_score > 1.0 and importance < 0.5:
                    suspicious_articles.append({
                        'title': article.get('title', '')[:100],
                        'source': article.get('source', ''),
                        'disinfo_score': round(article_score, 2),
                        'importance': importance,
                        'indicators': article_indicators
                    })
            
            # Score global de désinformation
            total_indicators = sum(disinfo_indicators.values())
            disinfo_score = min(total_indicators / max(len(articles), 1) / 5, 1.0)  # Normaliser
            
            return {
                'disinfo_score': round(disinfo_score, 3),
                'total_indicators': total_indicators,
                'pattern_breakdown': dict(disinfo_indicators),
                'suspicious_articles': suspicious_articles[:5],  # Top 5
                'risk_level': 'HIGH' if disinfo_score > 0.6 else 'MEDIUM' if disinfo_score > 0.3 else 'LOW'
            }
            
        except Exception as e:
            logger.error(f"Erreur détection désinformation: {e}")
            return {'disinfo_score': 0}
    
    async def _analyze_social_media_noise(self, hours_back: int) -> Dict[str, Any]:
        """Analyse le bruit sur les réseaux sociaux avec IA"""
        try:
            since = datetime.now() - timedelta(hours=hours_back)
            
            # Récupérer les posts récents
            social_posts = list(self.db.social_media_posts.find({
                "scraped_at": {"$gte": since.isoformat()}
            }).limit(50))  # Limiter pour performance
            
            if not social_posts:
                return {'amplification_score': 0, 'message': 'Pas de données sociales'}
            
            # Analyser avec Mistral si beaucoup de contenu
            if len(social_posts) > 10:
                analyzed_posts = []
                
                for post in social_posts[:20]:  # Analyser 20 max
                    content = post.get('content', '')
                    if len(content) > 50:  # Contenu substantiel
                        try:
                            # Analyse Mistral du post social
                            analysis = self.ai_service.analyze_social_content(
                                content=content,
                                platform=post.get('platform', 'unknown'),
                                engagement=post.get('engagement', {})
                            )
                            analyzed_posts.append({
                                'platform': post.get('platform'),
                                'content_preview': content[:100],
                                'engagement': post.get('engagement', {}),
                                'mistral_analysis': analysis
                            })
                        except Exception as e:
                            logger.warning(f"Erreur analyse post social: {e}")
                            continue
                
                # Calculer l'amplification
                total_engagement = sum(
                    post.get('engagement', {}).get('total', 0) 
                    for post in social_posts
                )
                avg_engagement = total_engagement / len(social_posts) if social_posts else 0
                
                # Score d'amplification basé sur engagement et volume
                amplification_score = min((len(social_posts) * avg_engagement) / 1000, 1.0)
                
                return {
                    'amplification_score': round(amplification_score, 3),
                    'posts_analyzed': len(social_posts),
                    'mistral_analyzed': len(analyzed_posts),
                    'avg_engagement': round(avg_engagement, 1),
                    'platform_breakdown': dict(Counter(p.get('platform') for p in social_posts)),
                    'analyzed_samples': analyzed_posts[:5]
                }
            else:
                return {
                    'amplification_score': 0.1,
                    'posts_analyzed': len(social_posts),
                    'message': 'Volume social faible'
                }
            
        except Exception as e:
            logger.error(f"Erreur analyse social: {e}")
            return {'amplification_score': 0, 'error': str(e)}
    
    def _calculate_composite_noise_score(self, components: Dict[str, float]) -> float:
        """Calcule le score composite de bruit médiatique"""
        weights = {
            'volume_spike': 0.20,
            'content_repetition': 0.15,
            'low_importance_flood': 0.15,
            'entity_saturation': 0.15,
            'theme_monopolization': 0.15,
            'disinformation_indicators': 0.10,
            'social_amplification': 0.10
        }
        
        weighted_score = sum(
            components.get(component, 0) * weight
            for component, weight in weights.items()
        )
        
        return min(weighted_score, 1.0)
    
    def _classify_noise_level(self, score: float) -> str:
        """Classifie le niveau de bruit"""
        if score >= 0.8:
            return 'critical'
        elif score >= 0.6:
            return 'high'
        elif score >= 0.4:
            return 'medium'
        elif score >= 0.2:
            return 'low'
        else:
            return 'minimal'
    
    def _generate_noise_recommendations(self, noise_level: str, components: Dict[str, float]) -> List[str]:
        """Génère des recommandations basées sur le niveau de bruit"""
        recommendations = []
        
        if noise_level in ['critical', 'high']:
            recommendations.append("🔊 BRUIT MÉDIATIQUE ÉLEVÉ - Filtrage renforcé recommandé")
            
        if components.get('volume_spike', 0) > 0.5:
            recommendations.append("📈 Pic de volume détecté - Vérifier les sources")
            
        if components.get('content_repetition', 0) > 0.5:
            recommendations.append("🔄 Contenu répétitif - Possibles campagnes coordonnées")
            
        if components.get('disinformation_indicators', 0) > 0.5:
            recommendations.append("⚠️ Indicateurs de désinformation - Fact-checking requis")
            
        if components.get('social_amplification', 0) > 0.5:
            recommendations.append("📱 Amplification sociale détectée - Surveiller l'évolution")
            
        if not recommendations:
            recommendations.append("✅ Niveau de bruit acceptable - Surveillance normale")
            
        return recommendations

# Factory function pour intégration
def create_media_noise_detector(db, scraper, ai_service):
    """Crée une instance du détecteur de bruit médiatique"""
    try:
        return MediaNoiseDetectionMistral(db, scraper, ai_service)
    except Exception as e:
        logger.error(f"Erreur création détecteur bruit: {e}")
        return None