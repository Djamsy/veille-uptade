#!/usr/bin/env python3
"""
Test simple du scraping réseaux sociaux
"""

import os
import sys
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def test_social_scraping():
    """Test du scraping avec les bons imports"""
    print("🔍 TEST SCRAPING RÉSEAUX SOCIAUX")
    print("=" * 40)
    
    try:
        # Import des services de scraping
        from modern_social_service import modern_social_scraper
        
        print("📱 Service moderne trouvé")
        
        # Mots-clés de test pour le département
        test_keywords = ["Guy Losbar", "CD971"]
        print(f"🎯 Test avec: {', '.join(test_keywords)}")
        
        # Lancement du scraping
        print("⏳ Scraping en cours...")
        results = modern_social_scraper.scrape_all_modern_sources(test_keywords)
        
        # Affichage des résultats
        total = results.get('total_posts', 0)
        twitter_api = len(results.get('twitter_api', []))
        twitter_nitter = len(results.get('twitter_nitter', []))
        rss = len(results.get('rss_official', []))
        methods = results.get('methods_used', [])
        
        print(f"✅ RÉSULTATS SCRAPING:")
        print(f"   📊 Total posts: {total}")
        print(f"   🐦 Twitter API: {twitter_api}")
        print(f"   🔄 Twitter Nitter: {twitter_nitter}")
        print(f"   📡 RSS feeds: {rss}")
        print(f"   🛠️ Méthodes: {', '.join(methods)}")
        
        # Sauvegarder en base
        all_posts = []
        for source in ['twitter_api', 'twitter_nitter', 'rss_official']:
            all_posts.extend(results.get(source, []))
            
        if all_posts:
            print(f"\n💾 Sauvegarde de {len(all_posts)} posts...")
            saved = modern_social_scraper.save_posts_to_db(all_posts)
            print(f"✅ {saved} posts sauvegardés en MongoDB")
            
            # Afficher échantillon
            print("\n📄 ÉCHANTILLON DES POSTS:")
            for i, post in enumerate(all_posts[:3]):
                platform = post.get('platform', '?')
                content = str(post.get('content', ''))[:60]
                date = post.get('date', '?')
                keyword = post.get('keyword_searched', '?')
                print(f"   {i+1}. [{platform}] {keyword} | {content}...")
                
        else:
            print("⚠️ Aucun post récupéré")
            
        return True
        
    except ImportError as e:
        print(f"❌ Service introuvable: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Erreur scraping: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_social_scraping()
