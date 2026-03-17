#!/usr/bin/env python3
"""
Script de sécurité pour vérifier qu'aucune dépendance problématique n'est présente
À exécuter au démarrage de l'application
"""

import sys
import os
import importlib
import logging

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_forbidden_packages():
    """Vérifier qu'aucun package interdit n'est installé"""
    
    forbidden_packages = [
        'spacy',
        'torch', 
        'torchaudio',
        'transformers',
        'tensorflow',
        'fr_core_news_sm'
    ]
    
    installed_forbidden = []
    
    for package in forbidden_packages:
        try:
            importlib.import_module(package)
            installed_forbidden.append(package)
            logger.error(f"❌ Package interdit détecté: {package}")
        except ImportError:
            logger.info(f"✅ Package {package} absent (correct)")
    
    if installed_forbidden:
        logger.error(f"🚨 PACKAGES INTERDITS INSTALLÉS: {installed_forbidden}")
        logger.error("Application peut ne pas fonctionner en production")
        return False
    
    logger.info("✅ Aucun package interdit détecté")
    return True

def check_required_packages():
    """Vérifier que les packages requis sont présents"""
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'pymongo',
        'requests',
        'beautifulsoup4',
        'openai'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            logger.info(f"✅ Package requis présent: {package}")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"❌ Package requis manquant: {package}")
    
    if missing_packages:
        logger.error(f"🚨 PACKAGES REQUIS MANQUANTS: {missing_packages}")
        return False
    
    logger.info("✅ Tous les packages requis sont présents")
    return True

def verify_environment():
    """Vérifier l'environnement d'exécution"""
    
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"📁 Working directory: {os.getcwd()}")
    logger.info(f"🔧 Platform: {sys.platform}")
    
    # Vérifier les variables d'environnement importantes
    mongo_url = os.environ.get('MONGO_URL', 'Non configuré')
    logger.info(f"🗄️ MongoDB: {mongo_url[:50]}...")
    
    environment = os.environ.get('ENVIRONMENT', 'development')
    logger.info(f"🌍 Environment: {environment}")
    
    return True

def main():
    """Point d'entrée principal du check de sécurité"""
    
    logger.info("🔒 Vérification de sécurité des dépendances")
    logger.info("=" * 60)
    
    # Vérifications
    checks = [
        ("Environment", verify_environment),
        ("Forbidden packages", check_forbidden_packages),
        ("Required packages", check_required_packages)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        logger.info(f"\n🔍 {check_name}...")
        try:
            if not check_func():
                logger.error(f"❌ {check_name} FAILED")
                all_passed = False
            else:
                logger.info(f"✅ {check_name} PASSED")
        except Exception as e:
            logger.error(f"❌ {check_name} ERROR: {e}")
            all_passed = False
    
    logger.info("\n" + "=" * 60)
    
    if all_passed:
        logger.info("🎉 TOUTES LES VÉRIFICATIONS RÉUSSIES")
        logger.info("✅ Application prête à démarrer")
        return True
    else:
        logger.error("🚨 VÉRIFICATIONS ÉCHOUÉES")
        logger.error("❌ Corriger les problèmes avant de continuer")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)