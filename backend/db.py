# backend/db.py
import os
from functools import lru_cache
from pymongo import MongoClient

try:
    import certifi
except ImportError:
    certifi = None

def _resolve_db_name(mongo_url: str, fallback: str = "veille_media") -> str:
    """Déduit le nom de la base depuis l'URL (après le dernier /), sinon fallback."""
    try:
        part = mongo_url.rsplit("/", 1)[-1]
        name = part.split("?", 1)[0]
        return name or fallback
    except Exception:
        return fallback

@lru_cache(maxsize=1)
def _client() -> MongoClient:
    """Crée une connexion MongoDB (Atlas ou locale) avec timeouts raisonnables."""
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/veille_media")

    # Atlas (mongodb+srv) => utiliser le CA bundle de certifi si dispo
    if mongo_url.startswith("mongodb+srv://") and certifi is not None:
        return MongoClient(
            mongo_url,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            retryWrites=True,
            retryReads=True,
            maxPoolSize=20,
        )
    # Connexion locale / standard
    return MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=20000,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000,
        retryWrites=True,
        retryReads=True,
        maxPoolSize=20,
    )

def get_db():
    """Renvoie la base définie par MONGO_DB_NAME ou extraite de MONGO_URL."""
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/veille_media")
    db_name = os.getenv("MONGO_DB_NAME") or _resolve_db_name(mongo_url)
    return _client()[db_name]