"""
Health check script for production deployment
Vérifie que toutes les dépendances critiques sont disponibles
"""

import sys
import os
import logging

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_critical_dependencies():
    """Vérifier les dépendances critiques pour le déploiement"""
    
    critical_errors = []
    warnings = []
    
    print("🔍 Vérification des dépendances critiques...")
    
    # 1. Vérifier les imports essentiels
    essential_modules = [
        'fastapi',
        'uvicorn', 
        'pymongo',
        'requests',
        'beautifulsoup4',
        'openai',
        'nltk',
        'pandas',
        'numpy',
        'reportlab'
    ]
    
    for module_name in essential_modules:
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except ImportError as e:
            critical_errors.append(f"❌ Module critique manquant: {module_name} - {e}")
    
    # 2. Vérifier les modules optionnels
    optional_modules = [
        ('snscrape', 'Scraping Twitter/X - peut utiliser fallback RSS'),
        ('aiohttp', 'Requêtes asynchrones - peut utiliser requests'),
        ('streamlink', 'Capture radio - fonctionnalité optionnelle'),
        ('ffmpeg', 'Traitement audio - fonctionnalité optionnelle')
    ]
    
    for module_name, description in optional_modules:
        try:
            __import__(module_name)
            print(f"✅ {module_name} (optionnel)")
        except ImportError:
            warnings.append(f"⚠️ Module optionnel manquant: {module_name} - {description}")
    
    # 3. Vérifier la configuration MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'non configuré')
    if mongo_url == 'non configuré':
        critical_errors.append("❌ Variable MONGO_URL non configurée")
    else:
        print(f"✅ MONGO_URL configuré: {mongo_url[:50]}...")
        
        # Test de connection MongoDB
        try:
            from pymongo import MongoClient
            if 'mongodb+srv://' in mongo_url or 'atlas' in mongo_url.lower():
                client = MongoClient(
                    mongo_url,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000
                )
            else:
                client = MongoClient(mongo_url)
            
            client.admin.command('ping')
            print("✅ Connection MongoDB réussie")
            client.close()
        except Exception as e:
            critical_errors.append(f"❌ Erreur connection MongoDB: {e}")
    
    # 4. Vérifier les variables d'environnement optionnelles
    env_vars = [
        ('OPENAI_API_KEY', 'Clé API OpenAI pour GPT et Whisper'),
        ('ENVIRONMENT', 'Environnement (development/production)'),
        ('TELEGRAM_BOT_TOKEN', 'Token Telegram pour alertes'),
        ('TWITTER_API_KEY', 'Clé API Twitter pour réseaux sociaux')
    ]
    
    for var_name, description in env_vars:
        value = os.environ.get(var_name)
        if value:
            print(f"✅ {var_name} configuré")
        else:
            warnings.append(f"⚠️ Variable optionnelle manquante: {var_name} - {description}")
    
    # 5. Résultats
    print("\n" + "="*60)
    
    if critical_errors:
        print("🚨 ERREURS CRITIQUES:")
        for error in critical_errors:
            print(error)
        print("\n❌ Déploiement échouera probablement")
        return False
    else:
        print("✅ Toutes les dépendances critiques sont disponibles")
    
    if warnings:
        print("\n⚠️ AVERTISSEMENTS (non critiques):")
        for warning in warnings:
            print(warning)
        print("\n🟡 Déploiement possible avec fonctionnalités limitées")
    else:
        print("\n🎉 Toutes les dépendances sont parfaitement configurées")
    
    return True

def check_file_structure():
    """Vérifier la structure des fichiers essentiels"""
    
    print("\n🔍 Vérification de la structure des fichiers...")
    
    essential_files = [
        'server.py',
        'scraper_service.py',
        'requirements.txt'
    ]
    
    missing_files = []
    
    for filename in essential_files:
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            print(f"✅ {filename}")
        else:
            missing_files.append(filename)
            print(f"❌ {filename} manquant")
    
    if missing_files:
        print(f"\n❌ Fichiers manquants: {', '.join(missing_files)}")
        return False
    
    print("\n✅ Structure des fichiers correcte")
    return True

def main():
    """Point d'entrée principal du health check"""
    
    print("🏥 Health Check - Veille Média Guadeloupe")
    print("="*60)
    
    # Vérifications
    deps_ok = check_critical_dependencies()
    files_ok = check_file_structure()
    
    print("\n" + "="*60)
    
    if deps_ok and files_ok:
        print("🎉 HEALTH CHECK RÉUSSI - Prêt pour le déploiement")
        sys.exit(0)
    else:
        print("🚨 HEALTH CHECK ÉCHOUÉ - Corrections nécessaires")
        sys.exit(1)

if __name__ == "__main__":
    main()