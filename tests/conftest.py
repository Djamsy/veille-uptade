"""Configuration pytest partagée."""

import os
import sys
from pathlib import Path

# Ajoute la racine du repo et backend/ au sys.path pour permettre les imports
# `from backend.xxx` et `from xxx` (les deux conventions cohabitent dans le code).
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

# Variables d'env neutres pour les tests : pas de vrai Mongo, pas de vrai OpenAI.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DB_NAME", "veille_media_test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017/veille_media_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("RUN_SCHEDULER", "false")
os.environ.setdefault("RUN_SCRAPING_ON_START", "false")
os.environ.setdefault("DISABLE_GPT_SENTIMENT", "true")
