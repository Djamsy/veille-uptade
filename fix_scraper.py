import re

print("Correction du scraper...")

with open('backend/scraper_service.py', 'r') as f:
    content = f.read()

# Correction URL France-Antilles
content = content.replace(
    'https://www.franceantilles.fr/actualite/guadeloupe/',
    'https://www.guadeloupe.franceantilles.fr/'
)

print("URL France-Antilles corrigée")

# Correction MongoDB push
content = re.sub(
    r'"recent_articles": \{\s*"title"[^}]+\}',
    '"recent_articles": {\n                                "$each": [{\n                                    "title": article["title"],\n                                    "date": article["date"],\n                                    "url": article.get("url")\n                                }],\n                                "$slice": -10\n                            }',
    content
)

print("MongoDB push corrigé")

with open('backend/scraper_service.py', 'w') as f:
    f.write(content)

print("Corrections terminées")
