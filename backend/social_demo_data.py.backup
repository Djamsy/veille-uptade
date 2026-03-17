"""
Données simulées pour démonstration du système d'analyse de sentiment sur réseaux sociaux
Simule des posts réalistes sur la Guadeloupe pour tester l'analyse de sentiment
"""
from datetime import datetime, timedelta
import random

def generate_realistic_social_posts():
    """Générer des posts simulés réalistes sur le Conseil Départemental et Guy Losbar"""
    
    # Posts positifs sur le Conseil Départemental et Guy Losbar
    positive_posts = [
        {
            'content': "Guy Losbar annonce 15 millions d'euros pour la rénovation des collèges de Guadeloupe ! Excellent investissement dans l'éducation de nos jeunes 👏 #CD971 #Education",
            'platform': 'twitter',
            'author': 'EducationGwada971',
            'engagement': {'likes': 89, 'retweets': 34, 'replies': 16, 'total': 139},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Le Conseil Départemental lance un nouveau programme d'aide aux familles monoparentales. Bravo Guy Losbar pour cette initiative sociale ! 500 familles vont être aidées",
            'platform': 'facebook',
            'author': 'SocialGuadeloupe',
            'engagement': {'likes': 156, 'comments': 43, 'shares': 28, 'total': 227},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Inauguration de la nouvelle route départementale à Sainte-Rose par Guy Losbar. Enfin ! Les habitants pourront circuler en sécurité 🚗 #InfrastructuresGwada",
            'platform': 'twitter',
            'author': 'RoutesGuadeloupe',
            'engagement': {'likes': 67, 'retweets': 23, 'replies': 12, 'total': 102},
            'expected_sentiment': 'positive'
        },
        {
            'content': "Guy Losbar présente le budget départemental 2025 : +8% pour le social, +12% pour les routes. Belle progression pour la Guadeloupe ! #Budget2025 #CD971",
            'platform': 'facebook',
            'author': 'PolitiqueGwada',
            'engagement': {'likes': 78, 'comments': 34, 'shares': 19, 'total': 131},
            'expected_sentiment': 'positive'
        }
    ]
    
    # Posts négatifs sur la gestion départementale
    negative_posts = [
        {
            'content': "Encore des retards dans les travaux promis par le Conseil Départemental... Guy Losbar avait annoncé la livraison pour septembre. On est en décembre ! 😤 #PromessesNonTenues",
            'platform': 'twitter',
            'author': 'CitoyenVigilant971',
            'engagement': {'likes': 123, 'retweets': 78, 'replies': 56, 'total': 257},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Grave problème d'assainissement dans plusieurs collèges du département. Les parents s'inquiètent. Quand le CD971 va-t-il réagir ? #CollègesInsalubres",
            'platform': 'facebook',
            'author': 'ParentsGuadeloupe',
            'engagement': {'likes': 89, 'comments': 67, 'shares': 45, 'total': 201},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Manifestation devant le Conseil Départemental : les agents réclament des augmentations salariales. Guy Losbar reste sourd aux revendications depuis 6 mois",
            'platform': 'twitter',
            'author': 'SyndicatCD971',
            'engagement': {'likes': 45, 'retweets': 67, 'replies': 23, 'total': 135},
            'expected_sentiment': 'negative'
        },
        {
            'content': "Budget départemental : polémique sur les dépenses de communication. 2 millions d'euros pour promouvoir Guy Losbar ? Les priorités sont ailleurs ! #GaspillagePublic",
            'platform': 'facebook',
            'author': 'TransparenceGwada',
            'engagement': {'likes': 134, 'comments': 89, 'shares': 67, 'total': 290},
            'expected_sentiment': 'negative'
        }
    ]
    
    # Posts neutres sur l'actualité départementale
    neutral_posts = [
        {
            'content': "Conseil départemental : séance plénière reportée au jeudi 15 janvier. Ordre du jour disponible sur le site cd971.fr",
            'platform': 'twitter',
            'author': 'CD971Officiel',
            'engagement': {'likes': 12, 'retweets': 8, 'replies': 3, 'total': 23},
            'expected_sentiment': 'neutral'
        },
        {
            'content': "Guy Losbar reçoit une délégation de maires demain à 14h au siège du Conseil Départemental de Basse-Terre pour discuter intercommunalité",
            'platform': 'facebook',
            'author': 'InfosInstitutionnelles',
            'engagement': {'likes': 18, 'comments': 5, 'shares': 3, 'total': 26},
            'expected_sentiment': 'neutral'
        },
        {
            'content': "Fermeture exceptionnelle des services du Conseil Départemental le 15 août. Réouverture lundi 18 août à 8h. Numéro d'urgence : 0590 99 XX XX",
            'platform': 'instagram',
            'author': 'ServicesPublicsGwada',
            'engagement': {'likes': 25, 'comments': 7, 'total': 32},
            'expected_sentiment': 'neutral'
        }
    ]
    
    # Combiner tous les posts
    all_posts = positive_posts + negative_posts + neutral_posts
    
    # Ajouter les métadonnées communes
    current_time = datetime.now()
    keywords = ['Guy Losbar', 'Conseil Départemental Guadeloupe', 'CD971', 'Losbar', 'Département Guadeloupe']
    
    processed_posts = []
    for i, post in enumerate(all_posts):
        # Dates réparties sur les derniers jours
        post_time = current_time - timedelta(hours=random.randint(1, 72))
        
        processed_post = {
            'id': f"{post['platform']}_{hash(post['content'] + str(i))}",
            'platform': post['platform'],
            'keyword_searched': random.choice(keywords),
            'content': post['content'],
            'author': post['author'],
            'author_followers': random.randint(100, 8000),
            'created_at': post_time.isoformat(),
            'engagement': post['engagement'],
            'url': f"https://{post['platform']}.com/post/{i}",
            'scraped_at': current_time.isoformat(),
            'date': current_time.strftime('%Y-%m-%d'),
            'is_reply': random.choice([False, False, False, True]),  # 25% de chance d'être une réponse
            'language': 'fr',
            'expected_sentiment': post['expected_sentiment'],
            'demo_data': True,
            'target_entity': 'Conseil Départemental Guadeloupe',  # Nouvelle métadonnée
            'political_figure': 'Guy Losbar' if 'guy losbar' in post['content'].lower() else None
        }
        processed_posts.append(processed_post)
    
    return processed_posts

def get_demo_social_stats():
    """Générer des statistiques de démonstration pour le ciblage CD971/Guy Losbar"""
    return {
        'message': 'Données de démonstration - Focus Conseil Départemental Guadeloupe & Guy Losbar',
        'data_source': 'Simulation réaliste pour surveillance politique locale',
        'total_demo_posts': 11,
        'target_entities': ['Conseil Départemental Guadeloupe', 'Guy Losbar', 'CD971'],
        'by_platform': {
            'twitter': 5,
            'facebook': 4, 
            'instagram': 1
        },
        'expected_sentiment_distribution': {
            'positive': 4,
            'negative': 4,
            'neutral': 3
        },
        'topics_covered': [
            'Budget départemental',
            'Education (collèges)',
            'Routes et infrastructures', 
            'Aide sociale',
            'Gestion politique',
            'Communication institutionnelle'
        ]
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