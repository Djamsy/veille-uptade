# backend/social_analysis_service.py
"""Service d'analyse des posts réseaux sociaux avec métriques de bruit médiatique"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pymongo import MongoClient
import os
import re

# Import du service AI existant
try:
    from backend._attic.ai_service import ai_service
    AI_SERVICE_AVAILABLE = True
    logger = logging.getLogger("backend.social_analysis")
    logger.info("Service AI importé avec succès")
except ImportError:
    AI_SERVICE_AVAILABLE = False
    ai_service = None
    logger = logging.getLogger("backend.social_analysis")
    logger.warning("Service AI non disponible")

logger.setLevel(logging.INFO)

class SocialAnalysisService:
    def __init__(self):
        """Initialise le service d'analyse sociale avec métriques de buzz"""
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            self.social_collection = self.db.social_media_posts
            self.affairs_collection = self.db.affaires_guadeloupe
            self.articles_collection = self.db.articles_guadeloupe
            logger.info("Service d'analyse sociale initialisé")
        except Exception as e:
            logger.error(f"Erreur connexion MongoDB: {e}")
            self.client = None

    def is_important_post(self, content: str, author: str = "", engagement: Dict[str, Any] = None) -> tuple[bool, float, str]:
        """Détermine si un post est d'importance suffisante"""
        content_lower = content.lower()
        author_lower = author.lower()
        
        critical_keywords = [
            'enquête', 'justice', 'tribunal', 'corruption', 'scandale',
            'arrestation', 'mise en examen', 'détournement', 'fraude',
            'crise', 'urgence', 'catastrophe', 'accident grave'
        ]
        
        important_figures = [
            'guy losbar', 'ary chalus', 'maire', 'préfet', 'député',
            'sénateur', 'ministre', 'président', 'gouverneur'
        ]
        
        critical_sectors = [
            'hôpital', 'chu', 'école', 'collège', 'lycée', 'université',
            'edf', 'eau', 'transport', 'port', 'aéroport', 'sécurité'
        ]
        
        score = 0.0
        reasons = []
        
        for keyword in critical_keywords:
            if keyword in content_lower:
                score += 0.8
                reasons.append(f"critique: {keyword}")
        
        for figure in important_figures:
            if figure in content_lower or figure in author_lower:
                score += 0.6
                reasons.append(f"personnalité: {figure}")
        
        for sector in critical_sectors:
            if sector in content_lower:
                score += 0.4
                reasons.append(f"secteur: {sector}")
        
        # Bonus engagement
        if engagement and isinstance(engagement, dict):
            total_engagement = engagement.get('total', 0)
            if total_engagement > 100:
                score += 0.2
                reasons.append("fort engagement")
        
        is_important = score >= 0.5
        reason = "; ".join(reasons) if reasons else "aucune"
        return is_important, score, reason

    def calculate_buzz_metrics(self, affair_id: str, entity_keywords: List[str] = None) -> Dict[str, Any]:
        """Calcule les métriques de bruit médiatique pour une affaire"""
        if not self.client:
            return {'error': 'Service non disponible'}
        
        try:
            # Récupérer l'affaire
            affair = self.affairs_collection.find_one({'affaire_id': affair_id})
            if not affair:
                return {'error': 'Affaire non trouvée'}
            
            # Mots-clés pour la recherche
            if not entity_keywords:
                entity_keywords = [
                    affair.get('primary_entity', ''),
                    affair.get('entite_principale', ''),
                    affair.get('affaire_titre', '')
                ]
                entity_keywords = [k for k in entity_keywords if k and len(k) > 3]
            
            # Période d'analyse (7 derniers jours)
            since_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            # Comptage posts par plateforme
            buzz_metrics = {
                'affair_id': affair_id,
                'calculated_at': datetime.now().isoformat(),
                'period_days': 7,
                'keywords_used': entity_keywords,
                'platforms': {},
                'totals': {
                    'posts': 0,
                    'comments': 0,
                    'shares': 0,
                    'likes': 0,
                    'total_engagement': 0
                },
                'sentiment': {
                    'positive': 0,
                    'negative': 0,
                    'neutral': 0
                },
                'buzz_score': 0.0,
                'buzz_level': 'minimal'
            }
            
            # Recherche par mots-clés dans les posts
            keyword_regex = '|'.join(re.escape(k.lower()) for k in entity_keywords if k)
            if not keyword_regex:
                return buzz_metrics
            
            query = {
                'date': {'$gte': since_date},
                'content': {'$regex': keyword_regex, '$options': 'i'}
            }
            
            matching_posts = list(self.social_collection.find(query))
            
            for post in matching_posts:
                platform = post.get('platform', 'unknown')
                if platform not in buzz_metrics['platforms']:
                    buzz_metrics['platforms'][platform] = {
                        'posts': 0,
                        'comments': 0,
                        'total_engagement': 0,
                        'top_posts': []
                    }
                
                # Comptage
                buzz_metrics['platforms'][platform]['posts'] += 1
                buzz_metrics['totals']['posts'] += 1
                
                # Engagement
                engagement = post.get('engagement', {})
                if isinstance(engagement, dict):
                    likes = engagement.get('likes', 0) or engagement.get('like_count', 0)
                    comments = engagement.get('comments', 0) or engagement.get('reply_count', 0)
                    shares = engagement.get('shares', 0) or engagement.get('retweet_count', 0)
                    
                    post_engagement = likes + comments + shares
                    buzz_metrics['platforms'][platform]['total_engagement'] += post_engagement
                    buzz_metrics['totals']['total_engagement'] += post_engagement
                    buzz_metrics['totals']['likes'] += likes
                    buzz_metrics['totals']['comments'] += comments
                    buzz_metrics['totals']['shares'] += shares
                
                # Top posts (engagement élevé)
                if post_engagement > 50:  # Seuil d'engagement notable
                    buzz_metrics['platforms'][platform]['top_posts'].append({
                        'id': post.get('id', str(post.get('_id'))),
                        'content': post.get('content', '')[:200],
                        'author': post.get('author', ''),
                        'engagement': post_engagement,
                        'platform': platform,
                        'url': post.get('url', ''),
                        'created_at': post.get('created_at')
                    })
                
                # Analyse sentiment basique
                content_lower = post.get('content', '').lower()
                if any(word in content_lower for word in ['bien', 'bon', 'excellent', 'super', 'bravo']):
                    buzz_metrics['sentiment']['positive'] += 1
                elif any(word in content_lower for word in ['mal', 'mauvais', 'scandale', 'honte', 'nul']):
                    buzz_metrics['sentiment']['negative'] += 1
                else:
                    buzz_metrics['sentiment']['neutral'] += 1
            
            # Trier les top posts par engagement
            for platform_data in buzz_metrics['platforms'].values():
                platform_data['top_posts'] = sorted(
                    platform_data['top_posts'], 
                    key=lambda x: x['engagement'], 
                    reverse=True
                )[:10]  # Top 10 par plateforme
            
            # Calcul du score de buzz
            total_posts = buzz_metrics['totals']['posts']
            total_engagement = buzz_metrics['totals']['total_engagement']
            
            # Score basé sur volume et engagement
            volume_score = min(total_posts / 20, 1.0)  # Normalisé sur 20 posts = score max
            engagement_score = min(total_engagement / 1000, 1.0)  # Normalisé sur 1000 interactions
            
            buzz_metrics['buzz_score'] = (volume_score * 0.6 + engagement_score * 0.4) * 10  # Score sur 10
            
            # Niveau de buzz
            if buzz_metrics['buzz_score'] >= 7:
                buzz_metrics['buzz_level'] = 'viral'
            elif buzz_metrics['buzz_score'] >= 5:
                buzz_metrics['buzz_level'] = 'élevé'
            elif buzz_metrics['buzz_score'] >= 3:
                buzz_metrics['buzz_level'] = 'modéré'
            elif buzz_metrics['buzz_score'] >= 1:
                buzz_metrics['buzz_level'] = 'faible'
            else:
                buzz_metrics['buzz_level'] = 'minimal'
            
            # Interprétation
            if total_posts > 0:
                sentiment_dominant = max(buzz_metrics['sentiment'], key=buzz_metrics['sentiment'].get)
                buzz_metrics['interpretation'] = f"L'affaire génère {total_posts} posts sur 7 jours avec {total_engagement} interactions. Sentiment dominant: {sentiment_dominant}."
            else:
                buzz_metrics['interpretation'] = "Aucune activité détectée sur les réseaux sociaux pour cette affaire."
            
            return buzz_metrics
            
        except Exception as e:
            logger.error(f"Erreur calcul métriques buzz: {e}")
            return {'error': str(e)}

    def get_affair_comments(self, affair_id: str, limit: int = 50) -> Dict[str, Any]:
        """Récupère les commentaires liés à une affaire avec sélection"""
        if not self.client:
            return {'error': 'Service non disponible'}
            
        try:
            # Récupérer l'affaire
            affair = self.affairs_collection.find_one({'affaire_id': affair_id})
            if not affair:
                return {'error': 'Affaire non trouvée'}
            
            # Mots-clés de l'affaire
            entity_keywords = [
                affair.get('primary_entity', ''),
                affair.get('entite_principale', ''),
                affair.get('affaire_titre', '')
            ]
            entity_keywords = [k for k in entity_keywords if k and len(k) > 3]
            
            if not entity_keywords:
                return {'error': 'Aucun mot-clé trouvé pour cette affaire'}
            
            # Recherche posts liés
            keyword_regex = '|'.join(re.escape(k.lower()) for k in entity_keywords if k)
            since_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            query = {
                'date': {'$gte': since_date},
                'content': {'$regex': keyword_regex, '$options': 'i'}
            }
            
            posts = list(self.social_collection.find(query).sort('created_at', -1).limit(limit))
            
            # Sélection intelligente des meilleurs commentaires
            selected_comments = []
            
            for post in posts:
                content = post.get('content', '')
                engagement = post.get('engagement', {})
                
                # Score de pertinence
                relevance_score = 0
                
                # Bonus pour engagement
                total_engagement = 0
                if isinstance(engagement, dict):
                    total_engagement = (
                        engagement.get('likes', 0) + 
                        engagement.get('comments', 0) + 
                        engagement.get('shares', 0)
                    )
                    relevance_score += min(total_engagement / 100, 2.0)
                
                # Bonus pour longueur du contenu (plus informatif)
                if len(content) > 100:
                    relevance_score += 1.0
                
                # Bonus pour mots-clés critiques
                content_lower = content.lower()
                critical_words = ['important', 'urgent', 'scandale', 'justice', 'enquête']
                for word in critical_words:
                    if word in content_lower:
                        relevance_score += 0.5
                
                # Sentiment
                sentiment = 'neutre'
                if any(word in content_lower for word in ['bien', 'bon', 'excellent', 'bravo']):
                    sentiment = 'positif'
                elif any(word in content_lower for word in ['mal', 'scandale', 'honte', 'grave']):
                    sentiment = 'négatif'
                
                selected_comments.append({
                    'id': post.get('id', str(post.get('_id'))),
                    'content': content,
                    'author': post.get('author', 'Anonyme'),
                    'platform': post.get('platform', 'unknown'),
                    'created_at': post.get('created_at'),
                    'engagement': {
                        'likes': engagement.get('likes', 0),
                        'comments': engagement.get('comments', 0),
                        'shares': engagement.get('shares', 0),
                        'total': total_engagement
                    },
                    'sentiment': sentiment,
                    'relevance_score': relevance_score,
                    'url': post.get('url', '')
                })
            
            # Tri par score de pertinence
            selected_comments = sorted(selected_comments, key=lambda x: x['relevance_score'], reverse=True)
            
            # Statistiques
            total_comments = len(selected_comments)
            total_engagement = sum(c['engagement']['total'] for c in selected_comments)
            
            sentiment_counts = {'positif': 0, 'négatif': 0, 'neutre': 0}
            for comment in selected_comments:
                sentiment_counts[comment['sentiment']] += 1
            
            return {
                'affair_id': affair_id,
                'total_comments': total_comments,
                'total_engagement': total_engagement,
                'sentiment_distribution': sentiment_counts,
                'comments': selected_comments[:limit],  # Limiter le nombre retourné
                'keywords_used': entity_keywords,
                'period_days': 30,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération commentaires: {e}")
            return {'error': str(e)}

    def analyze_existing_posts(self, limit: int = 20, days_back: int = 7) -> Dict[str, Any]:
        """Analyse les posts existants avec calcul de buzz pour chaque affaire"""
        if not self.client:
            return {'error': 'Service non disponible'}
        
        stats = {
            'posts_processed': 0,
            'posts_analyzed': 0,
            'posts_important': 0,
            'posts_linked': 0,
            'affairs_enriched': 0,
            'buzz_calculated': 0,
            'errors': 0,
            'platforms_processed': {}
        }
        
        try:
            since_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            logger.info(f"Recherche posts depuis {since_date}")
            
            # Traitement par plateforme avec limite
            platforms = ['twitter', 'facebook', 'instagram', 'youtube', 'news']
            
            for platform in platforms:
                logger.info(f"Traitement plateforme: {platform}")
                
                platform_query = {
                    'date': {'$gte': since_date},
                    'platform': platform
                }
                
                platform_posts = list(
                    self.social_collection
                    .find(platform_query)
                    .sort('created_at', -1)
                    .limit(20)
                )
                
                stats['platforms_processed'][platform] = len(platform_posts)
                logger.info(f"{platform}: {len(platform_posts)} posts")
                
                for post in platform_posts:
                    stats['posts_processed'] += 1
                    
                    try:
                        if not isinstance(post, dict):
                            logger.error(f"Post invalide (type: {type(post)})")
                            stats['errors'] += 1
                            continue
                            
                        content = post.get('content', '')
                        author = post.get('author', '')
                        
                        logger.info(f"Post ID: {post.get('id', 'unknown')}, Content: {content[:30]}...")
                        
                        engagement = post.get('engagement', {})
                        is_important, importance_score, reasons = self.is_important_post(content, author, engagement)
                        
                        if not is_important:
                            logger.info(f"Post non-important ignoré: {content[:50]}...")
                            continue
                        
                        stats['posts_important'] += 1
                        logger.info(f"Post important trouvé (score: {importance_score:.2f}): {reasons}")
                        
                        # Analyse AI pour posts importants
                        if AI_SERVICE_AVAILABLE and ai_service:
                            analysis = self.simple_ai_analysis(post)
                            if analysis:
                                stats['posts_analyzed'] += 1
                                
                                ai_score = analysis.get('gravite_score', 0)
                                if ai_score >= 0.6:
                                    logger.info(f"Score AI élevé ({ai_score:.2f}) - candidat affaire")
                                    stats['posts_linked'] += 1
                        
                    except Exception as e:
                        stats['errors'] += 1
                        logger.error(f"Erreur post {platform}: {e}")
            
            # Calcul du buzz médiatique pour toutes les affaires actives
            try:
                active_affairs = list(self.affairs_collection.find({'status': {'$ne': 'closed'}}).limit(20))
                for affair in active_affairs:
                    affair_id = affair.get('affaire_id')
                    if affair_id:
                        buzz_metrics = self.calculate_buzz_metrics(affair_id)
                        if 'error' not in buzz_metrics:
                            stats['buzz_calculated'] += 1
                            logger.info(f"Buzz calculé pour {affair_id}: {buzz_metrics['buzz_level']}")
                            
                            # Mettre à jour l'affaire avec les métriques
                            self.affairs_collection.update_one(
                                {'affaire_id': affair_id},
                                {'$set': {
                                    'media_buzz': buzz_metrics,
                                    'buzz_last_calculated': datetime.now().isoformat()
                                }}
                            )
                            stats['affairs_enriched'] += 1
            except Exception as e:
                logger.error(f"Erreur calcul buzz affaires: {e}")
            
            logger.info(f"Analyse terminée: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Erreur analyse posts: {e}")
            stats['error'] = str(e)
            return stats

    def simple_ai_analysis(self, post: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyse AI simplifiée"""
        try:
            content = post.get('content', '')
            if len(content) < 20:
                return None
                
            logger.info("Appel enrich_article...")
            
            article_data = {
                'content': content,
                'title': f"Post {post.get('platform', 'social')}",
                'author': post.get('author', ''),
                'url': post.get('url', '')
            }
            
            result = ai_service.enrich_article(article_data)
            
            if result:
                logger.info(f"AI réussi: score={result.get('gravite_score', 0)}")
                return result
            else:
                logger.info("AI n'a pas retourné de résultat")
                return None
            
        except Exception as e:
            logger.warning(f"Erreur analyse simple: {e}")
            return None

    def get_analysis_stats(self) -> Dict[str, Any]:
        """Statistiques d'analyse"""
        if not self.client:
            return {'error': 'Service non disponible'}
            
        try:
            total_posts = self.social_collection.count_documents({})
            analyzed_posts = self.social_collection.count_documents({'analyzed_simple': True})
            
            # Statistiques buzz médiatique
            affairs_with_buzz = self.affairs_collection.count_documents({'media_buzz': {'$exists': True}})
            
            return {
                'total_posts': total_posts,
                'analyzed_posts': analyzed_posts,
                'affairs_with_buzz_metrics': affairs_with_buzz,
                'ai_service_available': AI_SERVICE_AVAILABLE,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erreur stats: {e}")
            return {'error': str(e)}

    def get_affair_social_posts(self, affair_id: str) -> Dict[str, Any]:
        """Posts liés à une affaire avec métriques détaillées"""
        buzz_metrics = self.calculate_buzz_metrics(affair_id)
        comments_data = self.get_affair_comments(affair_id, limit=30)
        
        return {
            'affair_id': affair_id,
            'buzz_metrics': buzz_metrics,
            'comments': comments_data,
            'generated_at': datetime.now().isoformat()
        }

# Instance globale
social_analyzer = SocialAnalysisService()
