#!/usr/bin/env python3

# Corrections rapides pour scraper_service.py
import re

# Lire le fichier
with open('backend/scraper_service.py', 'r') as f:
    content = f.read()

# Correction 1: URL France-Antilles
content = content.replace(
    '"url": "https://www.franceantilles.fr/actualite/guadeloupe/"',
    '"url": "https://www.guadeloupe.franceantilles.fr/"'
)
content = content.replace(
    '"base_url": "https://www.franceantilles.fr"',
    '"base_url": "https://www.guadeloupe.franceantilles.fr"'
)

# Correction 2: Syntaxe MongoDB $push
old_push = '''                        "$push": {
                            "recent_articles": {
                                "title": article["title"],
                                "date": article["date"],
                                "url": article.get("url"),
                                "$each": [],
                                "$slice": -10  # Garder 10 derniers
                            }
                        }'''

new_push = '''                        "$push": {
                            "recent_articles": {
                                "$each": [{
                                    "title": article["title"],
                                    "date": article["date"],
                                    "url": article.get("url")
                                }],
                                "$slice": -10
                            }
                        }'''

content = content.replace(old_push, new_push)

# Sauvegarder
with open('backend/scraper_service.py', 'w') as f:
    f.write(content)

print("Corrections appliquées")
