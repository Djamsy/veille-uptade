# backend/social_media_routes.py
"""
Routes API unifiées pour tous les réseaux sociaux
- Facebook, Twitter, Instagram, TikTok
- Scraping standard et ciblé par affaires
- Déclenchement intelligent avec analyse Mistral
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks

# Import des services
try:
    from backend.facebook_service import facebook_service
    from backend.twitter_service import twitter_service
    from backend.instagram_service import instagram_service
    from backend.tiktok_service import tiktok_service
except ImportError:
    from facebook_service import facebook_service
    from twitter_service import twitter_service
    from instagram_service import instagram_service
    from tiktok_service import tiktok_service

router = APIRouter(prefix="/api/social", tags=["social-media"])
logger = logging.getLogger("social_routes")
logger.setLevel(logging.INFO)

# =================
# ROUTES GÉNÉRALES
# =================

@router.get("/stats", summary="Statistiques globales réseaux sociaux")
def get_global_stats():
    """Statistiques agrégées de tous les réseaux sociaux"""
    try:
        stats = {
            'facebook': facebook_service.get_facebook_stats(),
            'twitter': twitter_service.get_twitter_stats(),
            'instagram': instagram_service.get_instagram_stats(),
            'tiktok': tiktok_service.get_tiktok_stats(),
            'last_updated': datetime.now().isoformat()
        }
        
        # Calculer totaux
        total_posts = sum([
            stats['facebook'].get('total_posts', 0),
            stats['twitter'].get('total_tweets', 0),
            stats['instagram'].get('total_posts', 0),
            stats['tiktok'].get('total_posts', 0)
        ])
        
        total_comments = sum([
            stats['facebook'].get('total_comments', 0),
            stats['twitter'].get('total_replies', 0),
            stats['instagram'].get('total_comments', 0),
            stats['tiktok'].get('total_comments', 0)
        ])
        
        stats['summary'] = {
            'total_posts': total_posts,
            'total_comments': total_comments,
            'platforms_active': 4
        }
        
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.exception("Erreur récupération stats globales")
        raise HTTPException(status_code=500, detail=f"Erreur interne: {e}")

@router.post("/scrape-all", summary="Scraping complet tous réseaux")
def scrape_all_platforms(background_tasks: BackgroundTasks):
    """Déclencher scraping de tous les réseaux sociaux en arrière-plan"""
    
    def run_full_scraping():
        results = {
            'facebook': {'posts': 0, 'comments': 0},
            'twitter': {'posts': 0},
            'instagram': {'posts': 0, 'comments': 0},
            'tiktok': {'posts': 0, 'comments': 0}
        }
        
        try:
            # Facebook
            fb_posts = facebook_service.scrape_facebook_posts()
            results['facebook']['posts'] = facebook_service.save_posts_to_db(fb_posts)
            
            # Commentaires Facebook des top posts
            top_fb_urls = facebook_service.get_top_posts_for_comments()
            fb_comments = facebook_service.scrape_facebook_comments(top_fb_urls)
            results['facebook']['comments'] = facebook_service.save_comments_to_db(fb_comments)
            
            # Twitter
            tw_posts = twitter_service.scrape_twitter_posts()
            results['twitter']['posts'] = twitter_service.save_tweets_to_db(tw_posts)
            
            # Instagram
            ig_posts = instagram_service.scrape_instagram_posts()
            results['instagram']['posts'] = instagram_service.save_posts_to_db(ig_posts)
            
            # Commentaires Instagram
            top_ig_urls = instagram_service.get_top_posts_for_comments()
            ig_comments = instagram_service.scrape_instagram_comments(top_ig_urls)
            results['instagram']['comments'] = instagram_service.save_comments_to_db(ig_comments)
            
            # TikTok
            tt_posts = tiktok_service.scrape_tiktok_posts()
            results['tiktok']['posts'] = tiktok_service.save_posts_to_db(tt_posts)
            
            # Commentaires TikTok
            top_tt_ids = tiktok_service.get_top_posts_for_comments()
            tt_comments = tiktok_service.scrape_tiktok_comments(top_tt_ids)
            results['tiktok']['comments'] = tiktok_service.save_comments_to_db(tt_comments)
            
            logger.info(f"Scraping complet terminé: {results}")
            
        except Exception as e:
            logger.error(f"Erreur scraping complet: {e}")
    
    background_tasks.add_task(run_full_scraping)
    
    return {
        "success": True,
        "message": "Scraping complet lancé en arrière-plan",
        "estimated_duration": "15-20 minutes",
        "timestamp": datetime.now().isoformat()
    }

@router.post("/scrape-targeted", summary="Scraping ciblé par mots-clés")
def scrape_targeted(
    payload: Dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = None
):
    """
    Scraping ciblé sur des mots-clés spécifiques
    Body: {
        "keywords": ["Guy Losbar", "CD971"],
        "platforms": ["facebook", "twitter", "instagram", "tiktok"],
        "include_comments": true,
        "max_posts_per_platform": 20
    }
    """
    
    keywords = payload.get("keywords", [])
    platforms = payload.get("platforms", ["facebook", "twitter", "instagram", "tiktok"])
    include_comments = payload.get("include_comments", True)
    max_posts = payload.get("max_posts_per_platform", 20)
    
    if not keywords:
        raise HTTPException(status_code=400, detail="Au moins un mot-clé requis")
    
    def run_targeted_scraping():
        results = {}
        
        try:
            if "facebook" in platforms:
                # Facebook posts + commentaires ciblés
                fb_posts = facebook_service.scrape_facebook_posts(keywords[:3])
                results['facebook_posts'] = facebook_service.save_posts_to_db(fb_posts)
                
                if include_comments:
                    fb_urls = [post['url'] for post in fb_posts if post.get('url')][:5]
                    fb_comments = facebook_service.scrape_facebook_comments(fb_urls)
                    results['facebook_comments'] = facebook_service.save_comments_to_db(fb_comments)
            
            if "twitter" in platforms:
                # Twitter recherche par mots-clés
                tw_total = 0
                for keyword in keywords[:3]:
                    tw_posts = twitter_service.search_tweets_api(keyword, max_posts)
                    tw_total += twitter_service.save_tweets_to_db(tw_posts)
                results['twitter_posts'] = tw_total
            
            if "instagram" in platforms:
                # Instagram posts standard (limitation des recherches)
                ig_posts = instagram_service.scrape_instagram_posts()
                results['instagram_posts'] = instagram_service.save_posts_to_db(ig_posts)
            
            if "tiktok" in platforms:
                # TikTok posts standard
                tt_posts = tiktok_service.scrape_tiktok_posts()
                results['tiktok_posts'] = tiktok_service.save_posts_to_db(tt_posts)
            
            logger.info(f"Scraping ciblé terminé: {results}")
            
        except Exception as e:
            logger.error(f"Erreur scraping ciblé: {e}")
    
    if background_tasks:
        background_tasks.add_task(run_targeted_scraping)
        return {
            "success": True,
            "message": f"Scraping ciblé lancé pour {len(keywords)} mots-clés",
            "keywords": keywords,
            "platforms": platforms,
            "timestamp": datetime.now().isoformat()
        }
    else:
        run_targeted_scraping()
        return {
            "success": True,
            "message": "Scraping ciblé exécuté",
            "timestamp": datetime.now().isoformat()
        }

# ===================
# ROUTES FACEBOOK
# ===================

@router.get("/facebook/stats")
def get_facebook_stats():
    """Statistiques Facebook détaillées"""
    try:
        stats = facebook_service.get_facebook_stats()
        return {"success": True, "facebook_stats": stats}
    except Exception as e:
        logger.exception("Erreur stats Facebook")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/facebook/scrape")
def scrape_facebook(
    keywords: List[str] = Body(default=[]),
    include_comments: bool = Body(default=True),
    background_tasks: BackgroundTasks = None
):
    """Scraper Facebook posts et commentaires"""
    
    def run_facebook_scraping():
        try:
            # Posts
            posts = facebook_service.scrape_facebook_posts(keywords if keywords else None)
            posts_saved = facebook_service.save_posts_to_db(posts)
            
            comments_saved = 0
            if include_comments:
                # Commentaires des top posts
                top_urls = facebook_service.get_top_posts_for_comments()
                comments = facebook_service.scrape_facebook_comments(top_urls)
                comments_saved = facebook_service.save_comments_to_db(comments)
            
            logger.info(f"Facebook: {posts_saved} posts, {comments_saved} commentaires")
            return {"posts": posts_saved, "comments": comments_saved}
            
        except Exception as e:
            logger.error(f"Erreur scraping Facebook: {e}")
            return {"error": str(e)}
    
    if background_tasks:
        background_tasks.add_task(run_facebook_scraping)
        return {
            "success": True,
            "message": "Scraping Facebook lancé en arrière-plan",
            "timestamp": datetime.now().isoformat()
        }
    else:
        result = run_facebook_scraping()
        return {"success": True, "result": result}

# ===================
# ROUTES TWITTER
# ===================

@router.get("/twitter/stats")
def get_twitter_stats():
    """Statistiques Twitter détaillées"""
    try:
        stats = twitter_service.get_twitter_stats()
        return {"success": True, "twitter_stats": stats}
    except Exception as e:
        logger.exception("Erreur stats Twitter")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/twitter/scrape")
def scrape_twitter(
    keywords: List[str] = Body(default=[]),
    accounts: List[str] = Body(default=[]),
    max_tweets: int = Body(default=50)
):
    """Scraper Twitter par mots-clés ou comptes"""
    try:
        if keywords:
            # Recherche par mots-clés
            all_tweets = []
            for keyword in keywords[:5]:
                tweets = twitter_service.search_tweets_api(keyword, max_tweets)
                all_tweets.extend(tweets)
        else:
            # Scraping standard
            all_tweets = twitter_service.scrape_twitter_posts(keywords, accounts)
        
        saved = twitter_service.save_tweets_to_db(all_tweets)
        
        return {
            "success": True,
            "tweets_found": len(all_tweets),
            "tweets_saved": saved,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.exception("Erreur scraping Twitter")
        raise HTTPException(status_code=500, detail=str(e))

# ===================
# ROUTES INSTAGRAM
# ===================

@router.get("/instagram/stats")
def get_instagram_stats():
    """Statistiques Instagram détaillées"""
    try:
        stats = instagram_service.get_instagram_stats()
        return {"success": True, "instagram_stats": stats}
    except Exception as e:
        logger.exception("Erreur stats Instagram")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/instagram/scrape")
def scrape_instagram(
    include_comments: bool = Body(default=True),
    background_tasks: BackgroundTasks = None
):
    """Scraper Instagram posts et commentaires"""
    
    def run_instagram_scraping():
        try:
            # Posts
            posts = instagram_service.scrape_instagram_posts()
            posts_saved = instagram_service.save_posts_to_db(posts)
            
            comments_saved = 0
            if include_comments:
                # Commentaires des top posts
                top_urls = instagram_service.get_top_posts_for_comments()
                comments = instagram_service.scrape_instagram_comments(top_urls)
                comments_saved = instagram_service.save_comments_to_db(comments)
            
            logger.info(f"Instagram: {posts_saved} posts, {comments_saved} commentaires")
            return {"posts": posts_saved, "comments": comments_saved}
            
        except Exception as e:
            logger.error(f"Erreur scraping Instagram: {e}")
            return {"error": str(e)}
    
    if background_tasks:
        background_tasks.add_task(run_instagram_scraping)
        return {
            "success": True,
            "message": "Scraping Instagram lancé en arrière-plan",
            "timestamp": datetime.now().isoformat()
        }
    else:
        result = run_instagram_scraping()
        return {"success": True, "result": result}

# ===================
# ROUTES TIKTOK
# ===================

@router.get("/tiktok/stats")
def get_tiktok_stats():
    """Statistiques TikTok détaillées"""
    try:
        stats = tiktok_service.get_tiktok_stats()
        return {"success": True, "tiktok_stats": stats}
    except Exception as e:
        logger.exception("Erreur stats TikTok")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tiktok/scrape")
def scrape_tiktok(
    include_comments: bool = Body(default=True),
    background_tasks: BackgroundTasks = None
):
    """Scraper TikTok vidéos et commentaires"""
    
    def run_tiktok_scraping():
        try:
            # Posts/Vidéos
            posts = tiktok_service.scrape_tiktok_posts()
            posts_saved = tiktok_service.save_posts_to_db(posts)
            
            comments_saved = 0
            if include_comments:
                # Commentaires des top vidéos
                top_aweme_ids = tiktok_service.get_top_posts_for_comments()
                comments = tiktok_service.scrape_tiktok_comments(top_aweme_ids)
                comments_saved = tiktok_service.save_comments_to_db(comments)
            
            logger.info(f"TikTok: {posts_saved} vidéos, {comments_saved} commentaires")
            return {"posts": posts_saved, "comments": comments_saved}
            
        except Exception as e:
            logger.error(f"Erreur scraping TikTok: {e}")
            return {"error": str(e)}
    
    if background_tasks:
        background_tasks.add_task(run_tiktok_scraping)
        return {
            "success": True,
            "message": "Scraping TikTok lancé en arrière-plan", 
            "timestamp": datetime.now().isoformat()
        }
    else:
        result = run_tiktok_scraping()
        return {"success": True, "result": result}

# ===================
# ROUTES RECHERCHE
# ===================

@router.get("/search")
def search_posts(
    q: str = Query(..., description="Terme de recherche"),
    platform: str = Query(default="all", description="Plateforme (all|facebook|twitter|instagram|tiktok)"),
    limit: int = Query(default=50, ge=1, le=200),
    date_from: str = Query(default="", description="Date début YYYY-MM-DD"),
    date_to: str = Query(default="", description="Date fin YYYY-MM-DD")
):
    """Rechercher dans tous les posts des réseaux sociaux"""
    try:
        from pymongo import MongoClient
        import os
        
        # Connexion MongoDB
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        client = MongoClient(MONGO_URL)
        db = client.veille_media
        
        # Construction query
        query = {
            '$or': [
                {'content': {'$regex': q, '$options': 'i'}},
                {'title': {'$regex': q, '$options': 'i'}},
                {'author': {'$regex': q, '$options': 'i'}}
            ]
        }
        
        # Filtre plateforme
        if platform != "all":
            if platform == "twitter":
                query['platform'] = {'$regex': 'twitter'}
            else:
                query['platform'] = platform
        
        # Filtre dates
        if date_from or date_to:
            date_query = {}
            if date_from:
                date_query['$gte'] = date_from
            if date_to:
                date_query['$lte'] = date_to
            query['date'] = date_query
        
        # Recherche
        posts = list(db.social_media_posts.find(
            query,
            {
                'content': 1, 'author': 1, 'platform': 1, 'date': 1,
                'engagement': 1, 'url': 1, 'sentiment': 1, 'topic_category': 1
            }
        ).sort('date', -1).limit(limit))
        
        # Convertir ObjectId en string
        for post in posts:
            post['_id'] = str(post['_id'])
        
        return {
            "success": True,
            "query": q,
            "platform": platform,
            "results_count": len(posts),
            "posts": posts,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.exception("Erreur recherche posts")
        raise HTTPException(status_code=500, detail=str(e))

# ===================
# ROUTES ANALYSE
# ===================

@router.get("/sentiment-analysis")
def get_sentiment_analysis(
    platform: str = Query(default="all"),
    days_back: int = Query(default=7, ge=1, le=30)
):
    """Analyse de sentiment des posts récents"""
    try:
        from pymongo import MongoClient
        import os
        
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        client = MongoClient(MONGO_URL)
        db = client.veille_media
        
        # Date limite
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        # Query de base
        match_query = {
            'date': {'$gte': cutoff_date},
            'sentiment': {'$exists': True}
        }
        
        if platform != "all":
            if platform == "twitter":
                match_query['platform'] = {'$regex': 'twitter'}
            else:
                match_query['platform'] = platform
        
        # Agrégation sentiment
        pipeline = [
            {'$match': match_query},
            {'$group': {
                '_id': '$sentiment',
                'count': {'$sum': 1},
                'avg_engagement': {'$avg': '$engagement.total'}
            }},
            {'$sort': {'count': -1}}
        ]
        
        sentiment_stats = list(db.social_media_posts.aggregate(pipeline))
        
        # Stats par plateforme
        platform_pipeline = [
            {'$match': match_query},
            {'$group': {
                '_id': '$platform',
                'total_posts': {'$sum': 1},
                'positive': {'$sum': {'$cond': [{'$eq': ['$sentiment', 'positive']}, 1, 0]}},
                'negative': {'$sum': {'$cond': [{'$eq': ['$sentiment', 'negative']}, 1, 0]}},
                'neutral': {'$sum': {'$cond': [{'$eq': ['$sentiment', 'neutral']}, 1, 0]}}
            }}
        ]
        
        platform_stats = list(db.social_media_posts.aggregate(platform_pipeline))
        
        return {
            "success": True,
            "period_days": days_back,
            "platform": platform,
            "sentiment_distribution": sentiment_stats,
            "platform_breakdown": platform_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.exception("Erreur analyse sentiment")
        raise HTTPException(status_code=500, detail=str(e))

# ===================
# ROUTES AFFAIRES
# ===================

@router.post("/trigger-affair-monitoring", summary="Déclencher monitoring affaire")
def trigger_affair_monitoring(
    payload: Dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = None
):
    """
    Déclencher monitoring renforcé suite à une affaire départementale
    Body: {
        "affair_title": "Affaire budget CD971",
        "keywords": ["Guy Losbar", "budget", "scandale"],
        "gravity_level": "important",
        "duration_hours": 48
    }
    """
    
    affair_title = payload.get("affair_title", "Affaire départementale")
    keywords = payload.get("keywords", [])
    gravity_level = payload.get("gravity_level", "important")
    duration_hours = payload.get("duration_hours", 48)
    
    if not keywords:
        raise HTTPException(status_code=400, detail="Mots-clés requis pour le monitoring")
    
    def run_affair_monitoring():
        try:
            logger.info(f"Démarrage monitoring affaire: {affair_title}")
            
            # Import du scraper principal pour utiliser l'analyse Mistral
            try:
                from scraper_service import guadeloupe_scraper
                ai_service = guadeloupe_scraper.ai_service
            except ImportError:
                from backend.scraper_service import guadeloupe_scraper
                ai_service = guadeloupe_scraper.ai_service
            
            # Phase 1: Scraping complet immédiat avec analyse Mistral
            scrape_all_results = {}
            
            # Facebook
            fb_posts = facebook_service.scrape_facebook_posts()
            scrape_all_results['facebook'] = facebook_service.save_posts_to_db(fb_posts)
            
            # Twitter ciblé
            tw_total = 0
            for keyword in keywords:
                tw_posts = twitter_service.search_tweets_api(keyword, 30)
                tw_total += twitter_service.save_tweets_to_db(tw_posts)
            scrape_all_results['twitter'] = tw_total
            
            # Instagram
            ig_posts = instagram_service.scrape_instagram_posts()
            scrape_all_results['instagram'] = instagram_service.save_posts_to_db(ig_posts)
            
            # TikTok
            tt_posts = tiktok_service.scrape_tiktok_posts()
            scrape_all_results['tiktok'] = tiktok_service.save_posts_to_db(tt_posts)
            
            # Phase 2: Commentaires ciblés avec analyse Mistral
            comments_results = {}
            affair_comments_detected = 0
            
            # Facebook commentaires avec analyse
            top_fb_urls = facebook_service.get_top_posts_for_comments(min_engagement=20)
            fb_comments = facebook_service.scrape_facebook_comments(top_fb_urls)
            
            # Analyser chaque commentaire avec Mistral
            for comment in fb_comments:
                if ai_service and ai_service.available:
                    try:
                        # Adapter le commentaire au format article pour Mistral
                        comment_as_article = {
                            'title': f"Commentaire: {comment.get('text', '')[:50]}...",
                            'content': comment.get('text', ''),
                            'source': 'Facebook Comment'
                        }
                        
                        # Analyser avec Mistral
                        analysis = ai_service.enrich_article(comment_as_article)
                        
                        # Détecter si c'est une affaire départementale
                        importance = analysis.get('gravite_score', 0.3)
                        if importance >= 0.6:  # Même seuil que les articles
                            affair_comments_detected += 1
                            
                            # Marquer le commentaire comme lié à une affaire
                            comment['is_affair_related'] = True
                            comment['affair_importance'] = importance
                            comment['affair_theme'] = analysis.get('theme_principal', 'general')
                            comment['affair_entities'] = analysis.get('entites', [])
                            
                            logger.info(f"🚨 COMMENTAIRE AFFAIRE DÉTECTÉ: {comment.get('text', '')[:80]}... (importance: {importance:.2f})")
                    
                    except Exception as e:
                        logger.error(f"Erreur analyse Mistral commentaire: {e}")
            
            comments_results['facebook'] = facebook_service.save_comments_to_db(fb_comments)
            comments_results['facebook_affairs'] = affair_comments_detected
            
            # Instagram commentaires avec analyse similaire
            top_ig_urls = instagram_service.get_top_posts_for_comments(min_engagement=30)
            ig_comments = instagram_service.scrape_instagram_comments(top_ig_urls)
            
            ig_affair_comments = 0
            for comment in ig_comments:
                if ai_service and ai_service.available:
                    try:
                        comment_as_article = {
                            'title': f"Commentaire IG: {comment.get('text', '')[:50]}...",
                            'content': comment.get('text', ''),
                            'source': 'Instagram Comment'
                        }
                        
                        analysis = ai_service.enrich_article(comment_as_article)
                        importance = analysis.get('gravite_score', 0.3)
                        
                        if importance >= 0.6:
                            ig_affair_comments += 1
                            comment['is_affair_related'] = True
                            comment['affair_importance'] = importance
                            comment['affair_theme'] = analysis.get('theme_principal', 'general')
                            
                    except Exception as e:
                        logger.error(f"Erreur analyse Mistral commentaire IG: {e}")
            
            comments_results['instagram'] = instagram_service.save_comments_to_db(ig_comments)
            comments_results['instagram_affairs'] = ig_affair_comments
            
            total_posts = sum([v for k, v in scrape_all_results.items() if isinstance(v, int)])
            total_comments = sum([v for k, v in comments_results.items() if isinstance(v, int)])
            total_affair_comments = affair_comments_detected + ig_affair_comments
            
            logger.info(f"Monitoring affaire terminé: {total_posts} posts, {total_comments} commentaires")
            logger.info(f"🎯 COMMENTAIRES AFFAIRES DÉTECTÉS: {total_affair_comments}")
            
            # Si des commentaires d'affaires détectés, déclencher nouveau scraping dans 1h
            if total_affair_comments > 5:
                logger.info("🔄 DÉCLENCHEMENT SCRAPING DIFFÉRÉ (1h) - Nombreux commentaires affaires détectés")
                # Ici on pourrait programmer un scraping différé
            
            return {
                'posts': total_posts,
                'comments': total_comments, 
                'affair_comments': total_affair_comments
            }
            
        except Exception as e:
            logger.error(f"Erreur monitoring affaire: {e}")
            return {'error': str(e)}
    
    if background_tasks:
        background_tasks.add_task(run_affair_monitoring)
        return {
            "success": True,
            "message": f"Monitoring affaire '{affair_title}' lancé",
            "keywords": keywords,
            "gravity_level": gravity_level,
            "estimated_duration": f"{duration_hours}h",
            "timestamp": datetime.now().isoformat()
        }
    else:
        run_affair_monitoring()
        return {
            "success": True,
            "message": "Monitoring affaire exécuté",
            "timestamp": datetime.now().isoformat()
        }
