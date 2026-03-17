#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(__file__))

from scraper_service import guadeloupe_scraper
from datetime import datetime

def retag_today():
    """Re-tague les articles d'aujourd'hui"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Récupérer articles d'aujourd'hui
    articles = list(guadeloupe_scraper.articles_collection.find({
        "date": today
    }))
    
    print(f"Trouvé {len(articles)} articles à re-tagger pour {today}")
    
    updated_count = 0
    for article in articles:
        try:
            print(f"Re-tagging: {article['title'][:50]}...")
            
            # Re-analyser avec nouvelle logique
            enriched = guadeloupe_scraper.enrich_article_with_mistral_force(article)
            
            # Mettre à jour
            result = guadeloupe_scraper.articles_collection.update_one(
                {"id": article["id"]},
                {"$set": {
                    "primary_entity": enriched["primary_entity"],
                    "importance_score": enriched["importance_score"],
                    "theme": enriched["theme"],
                    "sentiment": enriched["sentiment"],
                    "analysis_method": enriched["analysis_method"],
                    "retagged_at": datetime.now().isoformat()
                }}
            )
            
            if result.modified_count > 0:
                updated_count += 1
                
        except Exception as e:
            print(f"Erreur: {e}")
    
    print(f"Migration terminée: {updated_count}/{len(articles)} articles mis à jour")

if __name__ == "__main__":
    retag_today()