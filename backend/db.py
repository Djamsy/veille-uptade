# backend/db.py
"""Point d'accès UNIQUE à MongoDB pour tout le backend.

Toute connexion passe par ici : un seul MongoClient partagé par le process
(pymongo est thread-safe et gère son propre pool de connexions).

Pourquoi : avant, chaque service ouvrait son propre client, et certaines routes
en ouvraient un nouveau à CHAQUE requête sans le fermer. Résultat : connexions
qui s'accumulent côté Atlas, et impossible de basculer sur une base de secours
sans toucher à une dizaine de fichiers.

API :
    get_client()      -> MongoClient partagé du cluster principal (création paresseuse)
    get_db()          -> Database partagée (proxy avec bascule si un secours est configuré)
    is_available()    -> bool, ping court mis en cache quelques secondes
    get_db_or_none()  -> Database si MongoDB répond, sinon None
    is_degraded()     -> True si l'app tourne sur le cluster de secours
    get_primary_db()  -> Database brute du principal (ex. GridFS)
    get_failover_status() -> état de la bascule (pour /health)

Bascule automatique : voir backend/db_failover.py (active si MONGO_URL_FALLBACK).

Ne JAMAIS appeler .close() sur le client partagé depuis un service.

Variables d'environnement :
    MONGO_URL               URL de connexion (défaut : mongodb://localhost:27017/veille_media)
    MONGO_URL_FALLBACK      URL du cluster de secours (optionnel, active la bascule)
    MONGO_FALLBACK_MIRROR   collections recopiées sur le secours (défaut : users,alerts_config,
                            watchlist,campaigns,push_subscriptions)
    MONGO_FAILOVER_TELEGRAM 0 pour couper les alertes Telegram de bascule
    MONGO_DB_NAME / DB_NAME nom de la base (sinon : chemin de l'URL, sinon veille_media)
    MONGO_MAX_POOL_SIZE     taille du pool partagé (défaut 25)
    MONGO_SOCKET_TIMEOUT_MS timeout d'une opération réseau (défaut 60000)
"""
import os
import time
import logging
import threading
from functools import lru_cache
from typing import Optional

import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.database import Database

try:
    import certifi
except ImportError:
    certifi = None

logger = logging.getLogger(__name__)

DEFAULT_MONGO_URL = "mongodb://localhost:27017/veille_media"
DEFAULT_DB_NAME = "veille_media"


def get_mongo_url() -> str:
    return (os.getenv("MONGO_URL") or DEFAULT_MONGO_URL).strip()


def _resolve_db_name(mongo_url: str, fallback: str = DEFAULT_DB_NAME) -> str:
    """Déduit le nom de la base depuis le chemin de l'URL, sinon fallback.

    mongodb+srv://u:p@cluster0.x.mongodb.net/veille_media?retryWrites=true -> veille_media
    mongodb://localhost:27017                                              -> fallback
    """
    try:
        rest = mongo_url.split("://", 1)[1]
        if "/" not in rest:
            return fallback
        name = rest.split("/", 1)[1].split("?", 1)[0].strip()
        return name or fallback
    except Exception:
        return fallback


def get_db_name() -> str:
    """Priorité : MONGO_DB_NAME > DB_NAME > chemin de MONGO_URL > veille_media."""
    explicit = (os.getenv("MONGO_DB_NAME") or os.getenv("DB_NAME") or "").strip()
    return explicit or _resolve_db_name(get_mongo_url())


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _make_client(mongo_url: str) -> MongoClient:
    options = dict(
        serverSelectionTimeoutMS=20000,
        connectTimeoutMS=20000,
        socketTimeoutMS=_int_env("MONGO_SOCKET_TIMEOUT_MS", 60000),
        retryWrites=True,
        retryReads=True,
        maxPoolSize=_int_env("MONGO_MAX_POOL_SIZE", 25),
    )
    # Atlas (mongodb+srv) => CA bundle de certifi si dispo
    if mongo_url.startswith("mongodb+srv://") and certifi is not None:
        options["tlsCAFile"] = certifi.where()
    return MongoClient(mongo_url, **options)


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    """Client MongoDB partagé du cluster principal. Créé une seule fois, à la demande."""
    return _make_client(get_mongo_url())


# Alias historique (ancien nom privé)
_client = get_client


def get_fallback_url() -> str:
    return (os.getenv("MONGO_URL_FALLBACK") or "").strip()


@lru_cache(maxsize=1)
def _get_router():
    """Routeur de bascule, ou None si aucun cluster de secours n'est configuré."""
    fallback_url = get_fallback_url()
    if not fallback_url:
        return None
    if fallback_url == get_mongo_url():
        logger.error("❌ MONGO_URL_FALLBACK identique à MONGO_URL — bascule désactivée")
        return None
    from backend.db_failover import FailoverRouter
    router = FailoverRouter(get_client(), _make_client(fallback_url), get_db_name())
    if os.getenv("MONGO_FAILOVER_MONITOR", "1").strip().lower() not in ("0", "false", "no", "off"):
        router.start_monitor()
    logger.info("🛟 Cluster MongoDB de secours configuré — bascule automatique active")
    return router


def get_failover_router():
    return _get_router()


def get_db() -> Database:
    """Renvoie la base partagée. N'effectue aucun appel réseau.

    Avec un cluster de secours : proxy qui choisit la base active à chaque opération.
    """
    router = _get_router()
    if router is None:
        return get_client()[get_db_name()]
    from backend.db_failover import FailoverDatabase
    return FailoverDatabase(router)


def get_primary_db() -> Database:
    """Database brute du cluster principal (pour les API qui exigent une vraie Database)."""
    return get_client()[get_db_name()]


def is_degraded() -> bool:
    """True si l'app tourne actuellement sur le cluster de secours."""
    router = _get_router()
    return router is not None and router.is_degraded()


def get_failover_status() -> dict:
    router = _get_router()
    if router is None:
        return {"fallback_configured": False, "active": "primary", "degraded": False}
    return router.status()


# ── Disponibilité (ping court, résultat mis en cache) ──

_availability_lock = threading.Lock()
_availability: dict = {"ok": None, "checked_at": 0.0}


def is_available(timeout_s: float = 5.0, max_age_s: float = 30.0) -> bool:
    """True si MongoDB répond à un ping.

    Le résultat est gardé max_age_s secondes : si la base est down au démarrage,
    les services qui s'initialisent à la suite ne paient pas chacun le timeout.
    """
    now = time.monotonic()
    with _availability_lock:
        if _availability["ok"] is not None and now - _availability["checked_at"] < max_age_s:
            return _availability["ok"]
        router = _get_router()
        if router is not None:
            # Avec secours : disponible si la base active répond, ou si on peut basculer
            ok = router.ping(router.active, timeout_s)
            if not ok and not router.is_degraded():
                ok = router.switch_to_fallback("principal injoignable")
            if not ok:
                logger.error(f"❌ MongoDB indisponible (principal et secours): {router.last_error}")
        else:
            try:
                with pymongo.timeout(timeout_s):
                    get_client().admin.command("ping")
                ok = True
            except Exception as e:
                logger.error(f"❌ MongoDB indisponible: {e}")
                ok = False
        _availability["ok"] = ok
        _availability["checked_at"] = time.monotonic()
        return ok


def get_db_or_none(timeout_s: float = 5.0) -> Optional[Database]:
    """Database si MongoDB répond, sinon None (pour les services qui se dégradent proprement)."""
    return get_db() if is_available(timeout_s=timeout_s) else None


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
        # Réduit le stockage Atlas Flex qui grossit à l'infini
        try:
            articles.create_index(
                [("scraped_at", ASCENDING)],
                name="idx_articles_ttl_120d",
                expireAfterSeconds=120 * 24 * 3600,  # 120 jours
            )
            logger.info("✅ TTL 120j créé sur articles_guadeloupe.scraped_at")
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
        _safe_index(presences, [("article_id", ASCENDING), ("entity_canonical", ASCENDING), ("commune", ASCENDING)], "idx_presence_dedup")

        # ── Observatoire social : snapshots historiques des comptes RS ──
        # Aucune TTL : l'historique d'évolution doit être conservé durablement.
        # Un snapshot par (plateforme, date) — l'index unique garantit l'idempotence
        # (un seul snapshot par jour et par plateforme, ré-exécution = upsert).
        snapshots = db["account_snapshots"]
        _safe_index(snapshots, [("platform", ASCENDING), ("snapshot_date", DESCENDING)], "idx_snapshot_platform_date")
        _safe_index(snapshots, [("snapshot_date", DESCENDING)], "idx_snapshot_date")
        try:
            snapshots.create_index(
                [("platform", ASCENDING), ("snapshot_date", ASCENDING)],
                name="idx_snapshot_unique",
                unique=True,
                background=True,
            )
        except Exception:
            pass  # index déjà existant

        _indexes_created = True
        logger.info("✅ Tous les index API créés avec succès")
    except Exception as e:
        logger.error(f"❌ Erreur création index API: {e}")


def _safe_index(collection, keys, name):
    """Crée un index en ignorant les erreurs (déjà existant, etc.)."""
    try:
        collection.create_index(keys, name=name, background=True)
    except Exception:
        pass  # index déjà existant ou en cours de construction


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