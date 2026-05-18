# backend/db.py
import os
import time
import logging
from functools import lru_cache
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT

try:
    import certifi
except ImportError:
    certifi = None

logger = logging.getLogger(__name__)

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
            maxPoolSize=10,
        )
    # Connexion locale / standard
    return MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=20000,
        connectTimeoutMS=20000,
        socketTimeoutMS=20000,
        retryWrites=True,
        retryReads=True,
        maxPoolSize=10,
    )

def get_db():
    """Renvoie la base définie par MONGO_DB_NAME ou extraite de MONGO_URL."""
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017/veille_media")
    db_name = os.getenv("MONGO_DB_NAME") or _resolve_db_name(mongo_url)
    return _client()[db_name]


# ── Index Setup (appelé une seule fois au démarrage) ──

_indexes_created = False

def ensure_api_indexes(db=None):
    """Crée les index critiques pour les collections API.

    Idempotent — ne s'exécute qu'une fois par process grâce au flag _indexes_created.
    Inclut : text index pour la recherche full-text, compound indexes pour les
    requêtes fréquentes (filtrées, triées, paginées).
    """
    global _indexes_created
    if _indexes_created:
        return
    if db is None:
        db = get_db()

    try:
        articles = db["articles_guadeloupe"]

        # ── Text index pour la recherche full-text ──
        # Remplace les $regex lents par $text (utilise un index inversé)
        try:
            articles.create_index(
                [("title", TEXT), ("summary", TEXT), ("ai_summary", TEXT)],
                default_language="french",
                name="idx_articles_text_search",
            )
            logger.info("✅ Text index créé sur articles_guadeloupe")
        except Exception as e:
            # L'index existe peut-être déjà ou conflit avec un autre text index
            if "already exists" not in str(e).lower() and "exists with different" not in str(e).lower():
                logger.warning(f"⚠️ Text index articles: {e}")

        # ── Compound indexes pour requêtes fréquentes ──
        _safe_index(articles, [("date", DESCENDING), ("source", ASCENDING)], "idx_date_source")
        _safe_index(articles, [("date", DESCENDING), ("scraped_at", DESCENDING)], "idx_date_scraped")
        _safe_index(articles, [("source", ASCENDING), ("scraped_at", DESCENDING)], "idx_source_scraped")
        _safe_index(articles, [("scraped_at", DESCENDING)], "idx_scraped_at")

        # ── Radio transcriptions ──
        radio = db["radio_transcriptions"]
        _safe_index(radio, [("date", DESCENDING), ("captured_at", DESCENDING)], "idx_radio_date_captured")
        _safe_index(radio, [("captured_at", DESCENDING)], "idx_radio_captured")

        # ── Social media posts ──
        social = db["social_media_posts"]
        _safe_index(social, [("scraped_at", DESCENDING)], "idx_social_scraped")
        try:
            social.create_index(
                [("content", TEXT)],
                default_language="french",
                name="idx_social_text_search",
            )
        except Exception:
            pass  # text index peut déjà exister

        # TTL social posts : 90 jours (moins critique que les articles)
        try:
            social.create_index(
                [("scraped_at", ASCENDING)],
                name="idx_social_ttl_90d",
                expireAfterSeconds=90 * 24 * 3600,
            )
        except Exception:
            pass

        # ── Radio transcriptions TTL : 90 jours ──
        try:
            radio.create_index(
                [("captured_at", ASCENDING)],
                name="idx_radio_ttl_90d",
                expireAfterSeconds=90 * 24 * 3600,
            )
        except Exception:
            pass

        # ── Dedup indexes UNIQUES pour bloquer les doublons à l'insert ──
        # Supprimer les anciens index non-uniques s'ils existent
        for old_name in ["idx_article_id_dedup", "idx_title_hash_dedup"]:
            try:
                articles.drop_index(old_name)
                logger.info(f"🗑️ Ancien index {old_name} supprimé")
            except Exception:
                pass  # n'existait pas

        try:
            articles.create_index(
                [("article_id", ASCENDING)],
                unique=True,
                sparse=True,  # ignore les docs sans article_id
                name="idx_article_id_unique",
            )
            logger.info("✅ Index unique article_id créé")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"⚠️ Index unique article_id: {e}")
        try:
            articles.create_index(
                [("title_hash", ASCENDING)],
                unique=True,
                sparse=True,
                name="idx_title_hash_unique",
            )
            logger.info("✅ Index unique title_hash créé")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"⚠️ Index unique title_hash: {e}")
        # Index content_hash (non-unique car optionnel, mais indexé pour les lookups rapides)
        _safe_index(articles, [("content_hash", ASCENDING)], "idx_content_hash")

        # ── Index UNIQUE content_hash (anti-doublons) ──
        # Bloque toute insertion d'un article au contenu identique à un existant,
        # peu importe la formule d'article_id utilisée par le scraper.
        # Sparse → ignore les docs sans content_hash (les anciens, les RSS sans contenu).
        # Si la création échoue parce qu'il y a déjà des doublons, on log clairement
        # et on continue (l'index non-unique ci-dessus reste en place).
        try:
            articles.create_index(
                [("content_hash", ASCENDING)],
                name="idx_content_hash_unique",
                unique=True,
                sparse=True,
                background=True,
            )
            logger.info("✅ Index unique content_hash créé (anti-doublons)")
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err or "exists with different" in err:
                # OK, déjà créé lors d'un boot précédent
                pass
            elif "duplicate key" in err or "e11000" in err:
                # Il y a déjà des doublons en base — on ne peut pas créer l'index
                # tant qu'ils ne sont pas nettoyés. L'index non-unique reste actif.
                logger.error(
                    "❌ Index unique content_hash IMPOSSIBLE — doublons existants. "
                    "L'index continuera de bloquer les NOUVEAUX doublons une fois la base assainie. "
                    "Détails de l'erreur : %s",
                    str(e)[:200],
                )
            else:
                logger.warning(f"⚠️ Index unique content_hash: {e}")

        # ── TTL : suppression automatique des vieux articles (120 jours) ──
        # Réduit le stockage Atlas Flex qui grossit à l'infini.
        # IMPORTANT: filtre partiel pour PROTÉGER les articles liés à une affaire
        # (sinon les affaires stale/archivées ont des refs ObjectId dangling).
        # On supprime SEULEMENT les articles sans _affair_id (orphelins).
        #
        # L'ancien index sans partialFilterExpression doit être supprimé pour
        # créer le nouveau (Mongo refuse de re-créer un TTL avec options changées).
        try:
            existing_indexes = {idx.get("name") for idx in articles.list_indexes()}
            if "idx_articles_ttl_120d" in existing_indexes:
                # Vérifier si l'index existant a déjà le partialFilterExpression
                needs_recreate = True
                for idx in articles.list_indexes():
                    if idx.get("name") == "idx_articles_ttl_120d":
                        if idx.get("partialFilterExpression"):
                            needs_recreate = False
                        break
                if needs_recreate:
                    logger.info("🔧 TTL articles: drop + recreate avec partialFilterExpression (protège FK affaires)")
                    articles.drop_index("idx_articles_ttl_120d")
                    existing_indexes.discard("idx_articles_ttl_120d")

            if "idx_articles_ttl_120d" not in existing_indexes:
                articles.create_index(
                    [("scraped_at", ASCENDING)],
                    name="idx_articles_ttl_120d",
                    expireAfterSeconds=120 * 24 * 3600,  # 120 jours
                    partialFilterExpression={"_affair_id": {"$exists": False}},
                )
                logger.info("✅ TTL 120j créé sur articles orphelins (sans _affair_id)")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"⚠️ TTL articles: {e}")

        # ── Comments ──
        _safe_index(db["comments"], [("created_at", DESCENDING)], "idx_comments_created")

        # ── Affairs ──
        affairs = db["affairs"]
        _safe_index(affairs, [("status", ASCENDING), ("created_at", DESCENDING)], "idx_affairs_status_created")
        _safe_index(affairs, [("status", ASCENDING), ("gravity_score", DESCENDING)], "idx_affairs_status_gravity")
        _safe_index(affairs, [("status", ASCENDING), ("updated_at", DESCENDING)], "idx_affairs_status_updated")

        # ── Entity Presence (feature « carte de présence d'élus ») ──
        # Aucune TTL : durée d'observation indéfinie.
        presences = db["entity_presences"]
        _safe_index(presences, [("entity_canonical", ASCENDING), ("published_at", DESCENDING)], "idx_presence_entity_date")
        _safe_index(presences, [("commune", ASCENDING), ("published_at", DESCENDING)], "idx_presence_commune_date")
        _safe_index(presences, [("published_at", DESCENDING)], "idx_presence_date")
        # Dedup UNIQUE : empêche les doublons (article × entity × commune)
        # sous backfill concurrent. Sparse pour tolérer les anciennes lignes
        # qui n'auraient pas tous ces champs.
        _safe_index(
            presences,
            [("article_id", ASCENDING), ("entity_canonical", ASCENDING), ("commune", ASCENDING)],
            "idx_presence_dedup",
            unique=True,
            sparse=True,
        )

        _indexes_created = True
        logger.info("✅ Tous les index API créés avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur création index API: {e}")


def _safe_index(collection, keys, name, unique=False, sparse=False):
    """Crée un index en ignorant les erreurs (déjà existant, etc.)."""
    try:
        collection.create_index(
            keys, name=name, background=True, unique=unique, sparse=sparse,
        )
    except Exception as e:
        # Index déjà existant avec des options différentes → log + continue
        logger.debug(f"Index {name} skip: {e}")
        pass


# ── Cache en mémoire simple pour les stats dashboard ──

_stats_cache: dict = {}
_STATS_TTL = 60  # secondes

def get_cached_stats(key: str, fetcher, ttl: int = _STATS_TTL):
    """Cache en mémoire avec TTL pour les compteurs coûteux.

    Args:
        key: Clé de cache unique
        fetcher: Callable qui retourne la valeur à mettre en cache
        ttl: Durée de vie en secondes (défaut: 60s)

    Returns:
        La valeur depuis le cache ou fraîchement calculée.
    """
    now = time.time()
    if key in _stats_cache:
        val, ts = _stats_cache[key]
        if now - ts < ttl:
            return val
    val = fetcher()
    _stats_cache[key] = (val, now)
    return val


def invalidate_stats_cache(key: str = None):
    """Invalide le cache stats. Sans argument, vide tout le cache."""
    global _stats_cache
    if key is None:
        _stats_cache.clear()
    elif key in _stats_cache:
        del _stats_cache[key]