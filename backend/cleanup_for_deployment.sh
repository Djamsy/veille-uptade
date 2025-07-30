#!/bin/bash
# Script de nettoyage final pour éviter les erreurs de déploiement

echo "🧹 Nettoyage final pour déploiement production..."

# Supprimer les packages problématiques s'ils existent
pip uninstall -y spacy torch torchaudio fr-core-news-sm transformers tensorflow 2>/dev/null || true

# Nettoyer le cache pip
pip cache purge 2>/dev/null || true

# Nettoyer les répertoires de cache Python
find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find /app -name "*.pyc" -delete 2>/dev/null || true

echo "✅ Nettoyage terminé"

# Vérifier que requirements.txt est propre
echo "🔍 Vérification requirements.txt..."
if grep -i "spacy\|torch\|transformers\|fr-core-news-sm" /app/backend/requirements.txt; then
    echo "❌ Dépendances problématiques trouvées dans requirements.txt"
    exit 1
else
    echo "✅ requirements.txt propre"
fi

# Test d'importation des modules critiques
python3 -c "
import sys
forbidden = ['spacy', 'torch', 'transformers', 'fr_core_news_sm']
for pkg in forbidden:
    try:
        __import__(pkg)
        print(f'❌ Package interdit {pkg} détecté')
        sys.exit(1)
    except ImportError:
        print(f'✅ Package {pkg} absent (correct)')

print('✅ Environnement propre pour déploiement')
"

echo "🎉 Prêt pour déploiement !"