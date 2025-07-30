"""
Données simulées pour démonstration du système d'analyse de sentiment sur réseaux sociaux
Simule des posts réalistes sur la Guadeloupe pour tester l'analyse de sentiment
"""
from datetime import datetime, timedelta
import random

def generate_realistic_social_posts():
    """Générer des posts simulés réalistes sur la Guadeloupe"""
    
    # Posts positifs
    positive_posts = [
        {
            'content': "Magnifique coucher de soleil sur la plage de la Datcha à Le Gosier ! 🌅 La Guadeloupe nous offre encore un spectacle incroyable #Guadeloupe #Paradise",
            'platform': 'twitter',
            'author': 'GuadaloupeLife',
            'engagement': {'likes': 45, 'retweets': 12, 'replies': 8, 'total': 65},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Excellent festival de musique créole ce weekend à Pointe-à-Pitre ! Ambiance incroyable, artistes talentueux, public au rendez-vous 🎵 Fier de notre culture antillaise",
            'platform': 'facebook',
            'author': 'CultureGuadeloupe',
            'engagement': {'likes': 123, 'comments': 25, 'shares': 18, 'total': 166},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Nouvelle école inaugurée à Basse-Terre ! 500 élèves vont pouvoir étudier dans de meilleures conditions. Bravo pour cet investissement dans notre jeunesse 👏",
            'platform': 'twitter',
            'author': 'EducationGwada',
            'engagement': {'likes': 89, 'retweets': 34, 'replies': 16, 'total': 139},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Les papangues sont de retour dans le parc national ! Excellente nouvelle pour la biodiversité de notre archipel 🦅 #ConservationGuadeloupe",
            'platform': 'instagram',
            'author': 'NatureAntilles',
            'engagement': {'likes': 67, 'comments': 12, 'total': 79},
            'expected_sentiment': 'positive'
        }
    ]
    
    # Posts négatifs
    negative_posts = [
        {
            'content': "Encore des coupures d'eau à Saint-François... Ça devient vraiment insupportable pour les familles. Quand est-ce que ça va s'arrêter ? 😤 #PenurieEau",
            'platform': 'twitter',
            'author': 'CitoyenGwada',
            'engagement': {'likes': 78, 'retweets': 56, 'replies': 43, 'total': 177},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Grave accident sur la route de Gosier ce matin. Plusieurs blessés évacués vers le CHU. Attention sur les routes, conduisez prudemment !",
            'platform': 'facebook',
            'author': 'InfosGuadeloupe',
            'engagement': {'likes': 23, 'comments': 67, 'shares': 89, 'total': 179},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Manifestation des agriculteurs devant la préfecture. La situation économique devient très difficile avec la sécheresse et les problèmes d'irrigation 😟",
            'platform': 'twitter',
            'author': 'AgricultureGwada',
            'engagement': {'likes': 34, 'retweets': 28, 'replies': 19, 'total': 81},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Alerte méteo : risque de cyclone pour les prochains jours. Préparez-vous et restez vigilants ! Pensez à faire vos provisions 🌪️ #AlerteCyclone",
            'platform': 'facebook', 
            'author': 'MeteoAntilles',
            'engagement': {'likes': 156, 'comments': 89, 'shares': 234, 'total': 479},
            'expected_sentiment': 'negative'
        }
    ]
    
    # Posts neutres
    neutral_posts = [
        {
            'content': "Nouveau supermarché qui ouvre à Baie-Mahault la semaine prochaine. Ouverture prévue lundi 8h. Horaires : 8h-20h du lundi au samedi.",
            'platform': 'twitter',
            'author': 'CommerceLocal',
            'engagement': {'likes': 12, 'retweets': 8, 'replies': 3, 'total': 23},
            'expected_sentiment': 'neutral'
        },
        {
            'content': "Réunion du conseil municipal de Deshaies reportée à mercredi prochain. Ordre du jour disponible sur le site de la mairie.",
            'platform': 'facebook',
            'author': 'MairieDeshaies',
            'engagement': {'likes': 5, 'comments': 2, 'shares': 1, 'total': 8},
            'expected_sentiment': 'neutral'
        },
        {
            'content': "Fermeture temporaire de la bibliothèque de Sainte-Anne pour travaux de rénovation du 15 au 30 janvier. Réouverture prévue début février.",
            'platform': 'instagram',
            'author': 'BibliothequeSainteAnne',
            'engagement': {'likes': 18, 'comments': 7, 'total': 25},
            'expected_sentiment': 'neutral'
        }
    ]
    
    # Combiner tous les posts
    all_posts = positive_posts + negative_posts + neutral_posts
    
    # Ajouter les métadonnées communes
    current_time = datetime.now()
    keywords = ['Guadeloupe', 'Pointe-à-Pitre', 'Basse-Terre', 'Antilles', 'Gwada']
    
    processed_posts = []
    for i, post in enumerate(all_posts):
        # Dates réparties sur les derniers jours
        post_time = current_time - timedelta(hours=random.randint(1, 48))
        
        processed_post = {
            'id': f"{post['platform']}_{hash(post['content'] + str(i))}",
            'platform': post['platform'],
            'keyword_searched': random.choice(keywords),
            'content': post['content'],
            'author': post['author'],
            'author_followers': random.randint(50, 5000),
            'created_at': post_time.isoformat(),
            'engagement': post['engagement'],
            'url': f"https://{post['platform']}.com/post/{i}",
            'scraped_at': current_time.isoformat(),
            'date': current_time.strftime('%Y-%m-%d'),
            'is_reply': random.choice([False, False, False, True]),  # 25% de chance d'être une réponse
            'language': 'fr',
            'expected_sentiment': post['expected_sentiment'],  # Pour validation
            'demo_data': True  # Marquer comme données de démonstration
        }
        processed_posts.append(processed_post)
    
    return processed_posts

def get_demo_social_stats():
    """Générer des statistiques de démonstration"""
    return {
        'message': 'Données de démonstration - Twitter/X limits contournées',
        'data_source': 'Simulation réaliste pour tester l\'analyse de sentiment',
        'total_demo_posts': 11,
        'by_platform': {
            'twitter': 5,
            'facebook': 4, 
            'instagram': 2
        },
        'expected_sentiment_distribution': {
            'positive': 4,
            'negative': 4,
            'neutral': 3
        }
    }

if __name__ == "__main__":
    # Test des données simulées
    posts = generate_realistic_social_posts()
    print(f"✅ {len(posts)} posts simulés générés")
    
    for post in posts[:3]:
        print(f"\n📱 {post['platform'].upper()} (@{post['author']})")
        print(f"   {post['content'][:100]}...")
        print(f"   Engagement: {post['engagement']['total']} interactions")
        print(f"   Sentiment attendu: {post['expected_sentiment']}")