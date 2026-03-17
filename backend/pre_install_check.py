#!/usr/bin/env python3
"""
Script de vérification pre-install pour éviter les dépendances problématiques
À exécuter AVANT pip install -r requirements.txt
"""

import sys
import os
import re
import subprocess

def check_requirements_file():
    """Vérifier que requirements.txt ne contient pas de dépendances problématiques"""
    
    problematic_packages = [
        'spacy',
        'fr-core-news-sm',
        'fr_core_news_sm',
        'torch',
        'torchaudio',
        'transformers',
        'playwright',
        'selenium',
        'tensorflow'
    ]
    
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    
    if not os.path.exists(requirements_path):
        print(f"❌ requirements.txt not found at {requirements_path}")
        return False
    
    print(f"🔍 Checking {requirements_path} for problematic dependencies...")
    
    with open(requirements_path, 'r') as f:
        content = f.read().lower()
    
    found_problems = []
    
    for package in problematic_packages:
        # Chercher le package avec différents patterns
        patterns = [
            f'^{package}==',  # Exact version
            f'^{package}>=',  # Minimum version
            f'^{package}$',   # Just package name
            f'/{package}',    # In URL
            package.replace('-', '_'),  # Alternative naming
            package.replace('_', '-')   # Alternative naming
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE):
                found_problems.append(f"Found '{package}' with pattern '{pattern}'")
    
    if found_problems:
        print("❌ PROBLEMATIC DEPENDENCIES FOUND:")
        for problem in found_problems:
            print(f"  - {problem}")
        return False
    
    print("✅ No problematic dependencies found in requirements.txt")
    return True

def clean_pip_cache():
    """Nettoyer le cache pip pour éviter les installations cachées"""
    try:
        print("🧹 Cleaning pip cache...")
        subprocess.run([sys.executable, '-m', 'pip', 'cache', 'purge'], 
                      capture_output=True, check=False)
        print("✅ Pip cache cleaned")
    except Exception as e:
        print(f"⚠️ Warning: Could not clean pip cache: {e}")

def verify_python_version():
    """Vérifier la version Python"""
    version = sys.version_info
    print(f"🐍 Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3 or version.minor < 8:
        print("⚠️ Warning: Python 3.8+ recommended")
    else:
        print("✅ Python version compatible")

def main():
    """Point d'entrée principal"""
    print("🔧 Pre-install Dependency Check")
    print("=" * 50)
    
    # Vérifications
    checks_passed = True
    
    # 1. Vérifier Python
    verify_python_version()
    
    # 2. Nettoyer le cache pip
    clean_pip_cache()
    
    # 3. Vérifier requirements.txt
    if not check_requirements_file():
        checks_passed = False
    
    # 4. Afficher les résultats
    print("\n" + "=" * 50)
    
    if checks_passed:
        print("🎉 PRE-INSTALL CHECK PASSED")
        print("✅ Safe to run: pip install -r requirements.txt")
        sys.exit(0)
    else:
        print("🚨 PRE-INSTALL CHECK FAILED")
        print("❌ Fix requirements.txt before installing")
        sys.exit(1)

if __name__ == "__main__":
    main()