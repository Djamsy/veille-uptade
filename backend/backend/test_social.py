#!/usr/bin/env python3

from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

def test_modern_service():
    print("📱 TEST MODERN SOCIAL SERVICE")
    print("=" * 35)
    
    try:
        from modern_social_service import modern_social_scraper
        print("✅ Service moderne importé")
        
        keywords = ["Guy Losbar", "CD971"]
        results = modern_social_scraper.scrape_all_modern_sources(keywords)
        
        total = results.get('total_posts', 0)
        print(f"📊 Total posts: {total}")
        
        if total > 0:
            all_posts = []
            for source in ['twitter_api', 'twitter_nitter', 'rss_official']:
                all_posts.extend(results.get(source, []))
            
            saved = modern_social_scraper.save_posts_to_db(all_posts)
            print(f"💾 Posts sauvegardés: {saved}")
            
            return True
        else:
            print("⚠️ Aucun post trouvé")
            return False
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def test_classic_service():
    print("\n🔄 TEST CLASSIC SOCIAL SERVICE")
    print("=" * 35)
    
    try:
        from social_media_service import social_scraper
        print("✅ Service classique importé")
        
        results = social_scraper.start_scrape(["Guy Losbar", "CD971"])
        
        total_scraped = results.get('total_scraped', 0)
        total_saved = results.get('total_saved', 0)
        
        print(f"📊 Scraped: {total_scraped}")
        print(f"💾 Saved: {total_saved}")
        
        return total_saved > 0
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def check_stats():
    print("\n📈 VÉRIFICATION STATS")
    print("=" * 25)
    
    try:
        from pymongo import MongoClient
        import certifi
        
        mongo_url = os.getenv('MONGO_URL', '').strip('"')
        
        if mongo_url.startswith('mongodb+srv'):
            client = MongoClient(mongo_url, tlsCAFile=certifi.where())
        else:
            client = MongoClient(mongo_url)
            
        db = client['veille_media']
        collection = db['social_media_posts']
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        total_today = collection.count_documents({'date': today})
        guy_posts = collection.count_documents({'keyword_searched': 'Guy Losbar'})
        cd971_posts = collection.count_documents({'keyword_searched': 'CD971'})
        
        print(f"📅 Posts aujourd'hui: {total_today}")
        print(f"👤 Posts Guy Losbar: {guy_posts}")
        print(f"🏛️ Posts CD971: {cd971_posts}")
        
        # Échantillon
        recent = list(collection.find({'date': today}).limit(2))
        if recent:
            print("\n📄 Échantillon:")
            for i, post in enumerate(recent):
                platform = post.get('platform', '?')
                content = str(post.get('content', ''))[:40]
                print(f"   {i+1}. [{platform}] {content}...")
                
        return True
        
    except Exception as e:
        print(f"❌ Erreur stats: {e}")
        return False

if __name__ == "__main__":
    print("🚀 TEST SYSTÈME SCRAPING RS COMPLET")
    print("=" * 50)
    
    modern_ok = test_modern_service()
    classic_ok = test_classic_service()
    stats_ok = check_stats()
    
    print("\n" + "=" * 50)
    print("🎯 RÉSUMÉ:")
    print(f"   Modern Service: {'✅' if modern_ok else '❌'}")
    print(f"   Classic Service: {'✅' if classic_ok else '❌'}")
    print(f"   Stats MongoDB: {'✅' if stats_ok else '❌'}")
    
    if any([modern_ok, classic_ok]):
        print("\n✅ Système de scraping RS opérationnel!")
        print("🎛️ Prêt pour Smart Media Buzz")
    else:
        print("\n⚠️ Aucun service de scraping fonctionnel")
