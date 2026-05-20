# backend/affair_lifecycle_service.py
"""
Service de cycle de vie des affaires — REFONTE COMPLÈTE
========================================================

ANCIEN SYSTÈME (problèmes) :
- 1 article > seuil gravité → affaire créée immédiatement
- Corrélation par mots-clés simples → faux positifs massifs
- Transcriptions jamais liées → BMG toujours à zéro
- Pas de cycle de vie → affaires orphelines à l'infini

NOUVEAU SYSTÈME :
1. INGESTION : chaque item (article/transcription/social) entre dans
   la collection `topic_candidates` avec son contexte extrait
2. CLUSTERING : un job périodique regroupe les candidats par
   similarité contextuelle (pas juste les mots-clés)
3. PROMOTION : un cluster devient une AFFAIRE quand il remplit
   les critères (multi-source, multi-jour, gravité suffisante)
4. SUIVI : l'affaire vivante accumule les nouveaux items,
   son BMG évolue, elle peut être résolue/archivée
5. RÉCONCILIATION : le service de réconciliation corrige les
   entités des transcriptions via les articles (noms corrects)

COLLECTIONS MONGO :
- topic_candidates : items en attente de clustering
- topic_clusters   : groupes contextuels (pré-affaires)
- affairs          : affaires promues (existante, on la garde)
- affair_timeline  : historique des événements d'une affaire
"""

import os
import re
import logging
import hashlib
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from pymongo import MongoClient, DESCENDING

# Notifications Telegram (optionnel)
try:
    from backend.telegram_service import (
        notify_new_affair as _tg_notify,
        notify_affair_merged as _tg_merged,
        notify_affair_unlinked as _tg_unlinked,
        notify_snowball_alert as _tg_snowball,
    )
    _telegram_ok = True
except ImportError:
    try:
        from telegram_service import (
            notify_new_affair as _tg_notify,
            notify_affair_merged as _tg_merged,
            notify_affair_unlinked as _tg_unlinked,
            notify_snowball_alert as _tg_snowball,
        )
        _telegram_ok = True
    except ImportError:
        _telegram_ok = False
        _tg_notify = None
        _tg_merged = None
        _tg_unlinked = None
        _tg_snowball = None
# Notifications Push (optionnel)
try:
    from backend.push_service import notify_new_affair as _push_notify
    _push_ok = True
except ImportError:
    try:
        from push_service import notify_new_affair as _push_notify
        _push_ok = True
    except ImportError:
        _push_ok = False
        _push_notify = None

from bson import ObjectId

# Dédup IA (optionnel)
try:
    from backend.ai_groq_service import detect_duplicate_affairs as _ai_dedup
    from backend.ai_groq_service import validate_article_affair_relevance as _ai_relevance
    from backend.ai_groq_service import detect_stale_active_matches as _ai_stale_active
    from backend.ai_groq_service import match_article_to_affairs as _ai_match_article
    from backend.ai_groq_service import detect_commune_ai as _ai_detect_commune
    from backend.ai_groq_service import rewrite_affair_title as _ai_rewrite_title
    _ai_dedup_ok = True
    _ai_relevance_ok = True
    _ai_stale_active_ok = True
    _ai_match_ok = True
    _ai_commune_ok = True
except ImportError:
    try:
        from ai_groq_service import detect_duplicate_affairs as _ai_dedup
        from ai_groq_service import validate_article_affair_relevance as _ai_relevance
        from ai_groq_service import detect_stale_active_matches as _ai_stale_active
        from ai_groq_service import match_article_to_affairs as _ai_match_article
        from ai_groq_service import detect_commune_ai as _ai_detect_commune
        from ai_groq_service import rewrite_affair_title as _ai_rewrite_title
        _ai_dedup_ok = True
        _ai_relevance_ok = True
        _ai_stale_active_ok = True
        _ai_match_ok = True
        _ai_commune_ok = True
    except ImportError:
        _ai_dedup_ok = False
        _ai_dedup = None
        _ai_relevance_ok = False
        _ai_relevance = None
        _ai_stale_active_ok = False
        _ai_stale_active = None
        _ai_match_ok = False
        _ai_match_article = None
        _ai_commune_ok = False
        _ai_detect_commune = None
        _ai_rewrite_title = None

# ── Correction auto des noms/lieux (optionnel) ──
try:
    from backend.entity_aliases import correct_text_stt as _correct_stt, correct_entities_list as _correct_entities, resolve_entity as _resolve_entity
    _entity_aliases_ok = True
except ImportError:
    try:
        from entity_aliases import correct_text_stt as _correct_stt, correct_entities_list as _correct_entities, resolve_entity as _resolve_entity
        _entity_aliases_ok = True
    except ImportError:
        _entity_aliases_ok = False
        _correct_stt = None
        _correct_entities = None
        _resolve_entity = None

logger = logging.getLogger("affair_lifecycle")

# ============================================================
# CLASSIFICATION PAR COMMUNE — REGEX + IA FALLBACK
# ============================================================

# Les 32 communes de Guadeloupe + variantes sans accents
COMMUNES_GUADELOUPE = {
    "Pointe-à-Pitre": ["pointe a pitre", "pointe-a-pitre", "pointe à pitre", "pap", "pointe-à-pitre"],
    "Les Abymes": ["les abymes", "abymes", "petit-pérou", "petit perou", "raizet"],
    "Baie-Mahault": ["baie-mahault", "baie mahault", "jarry", "destrellan"],
    "Le Moule": ["le moule", "moule"],
    "Sainte-Anne": ["sainte-anne", "sainte anne", "ste-anne", "ste anne", "st-anne"],
    "Saint-François": ["saint-françois", "saint-francois", "saint françois", "st-françois", "st-francois"],
    "Le Gosier": ["le gosier", "gosier"],
    "Petit-Bourg": ["petit-bourg", "petit bourg"],
    "Capesterre-Belle-Eau": ["capesterre-belle-eau", "capesterre belle eau", "capesterre"],
    "Sainte-Rose": ["sainte-rose", "sainte rose", "ste-rose", "ste rose"],
    "Deshaies": ["deshaies", "déhaies"],
    "Bouillante": ["bouillante"],
    "Trois-Rivières": ["trois-rivières", "trois-rivieres", "trois rivières", "trois rivieres"],
    "Basse-Terre": ["basse-terre", "basse terre"],
    "Morne-à-l'Eau": ["morne-à-l'eau", "morne a l'eau", "morne-a-l'eau", "morne à l'eau"],
    "Port-Louis": ["port-louis", "port louis"],
    "Lamentin": ["lamentin"],
    "Goyave": ["goyave"],
    "Vieux-Habitants": ["vieux-habitants", "vieux habitants"],
    "Pointe-Noire": ["pointe-noire", "pointe noire"],
    "Saint-Claude": ["saint-claude", "saint claude", "st-claude"],
    "Gourbeyre": ["gourbeyre"],
    "Vieux-Fort": ["vieux-fort", "vieux fort"],
    "Marie-Galante": ["marie-galante", "marie galante"],
    "La Désirade": ["la désirade", "la desirade", "désirade", "desirade"],
    "Terre-de-Haut": ["terre-de-haut", "terre de haut", "les saintes"],
    "Terre-de-Bas": ["terre-de-bas", "terre de bas"],
    "Anse-Bertrand": ["anse-bertrand", "anse bertrand"],
    "Petit-Canal": ["petit-canal", "petit canal"],
    "Grand-Bourg": ["grand-bourg", "grand bourg"],
    "Capesterre-de-Marie-Galante": ["capesterre-de-marie-galante", "capesterre de marie galante"],
    "Saint-Louis": ["saint-louis", "saint louis", "st-louis"],
}

# Quartiers connus → commune
QUARTIER_TO_COMMUNE = {
    "petit-pérou": "Les Abymes", "petit perou": "Les Abymes",
    "raizet": "Les Abymes", "grand-camp": "Les Abymes",
    "jarry": "Baie-Mahault", "destrellan": "Baie-Mahault", "convenance": "Baie-Mahault",
    "bergevin": "Pointe-à-Pitre", "lauricisque": "Pointe-à-Pitre",
    "carénage": "Pointe-à-Pitre", "carenage": "Pointe-à-Pitre",
    "assainissement": "Pointe-à-Pitre",
    "baimbridge": "Les Abymes", "dugazon": "Les Abymes",
    "providence": "Le Gosier", "bas-du-fort": "Le Gosier",
    "saint-félix": "Le Gosier", "saint-felix": "Le Gosier",
    "gourdeliane": "Baie-Mahault",
    "vernou": "Petit-Bourg", "montebello": "Petit-Bourg",
    "rivière-salée": "Petit-Bourg", "riviere-salee": "Petit-Bourg",
    "matouba": "Saint-Claude",
    "pigeon": "Bouillante",
    "malendure": "Bouillante",
    "desmarais": "Capesterre-Belle-Eau",
    "sainte-marthe": "Capesterre-Belle-Eau",
}


def detect_communes_regex(text: str) -> List[str]:
    """
    Détecte les communes de Guadeloupe dans un texte par regex.
    Retourne une liste de noms normalisés (ex: ['Pointe-à-Pitre', 'Les Abymes']).
    """
    if not text:
        return []

    text_lower = text.lower()
    found = set()

    # 1. Chercher les quartiers connus → mapper à la commune
    for quartier, commune in QUARTIER_TO_COMMUNE.items():
        if quartier in text_lower:
            found.add(commune)

    # 2. Chercher les noms de communes (variantes)
    for commune_norm, variants in COMMUNES_GUADELOUPE.items():
        for variant in variants:
            # Chercher le variant comme mot entier (bordures de mot)
            pattern = r'\b' + re.escape(variant) + r'\b'
            if re.search(pattern, text_lower):
                found.add(commune_norm)
                break

    return list(found)


def classify_article_commune(article: Dict[str, Any]) -> List[str]:
    """
    Classifie un article par commune(s) de Guadeloupe.
    Stratégie en 2 passes :
    1. Regex sur titre + contenu + résumé + event_structured.location
    2. Si rien trouvé → fallback IA (GPT)

    Retourne la liste des communes détectées.
    """
    # Texte à analyser
    title = article.get("title", "")
    summary = article.get("ai_summary", "") or ""
    content = article.get("content", "") or ""
    event_loc = ""
    event_struct = article.get("event_structured", {})
    if isinstance(event_struct, dict):
        event_loc = event_struct.get("location", "") or ""

    # Concaténer tous les textes utiles
    full_text = f"{title} {summary} {event_loc} {content[:1000]}"

    # Passe 1 : regex
    communes = detect_communes_regex(full_text)

    if communes:
        return communes

    # Passe 2 : IA fallback (seulement si regex n'a rien trouvé)
    if _ai_commune_ok and _ai_detect_commune:
        try:
            ai_result = _ai_detect_commune(title, summary, content[:500])
            if ai_result:
                # Normaliser les résultats IA contre notre liste officielle
                normalized = []
                for c in ai_result:
                    c_lower = c.lower().strip()
                    for commune_norm, variants in COMMUNES_GUADELOUPE.items():
                        if c_lower in variants or c_lower == commune_norm.lower():
                            normalized.append(commune_norm)
                            break
                return normalized
        except Exception as e:
            logger.warning(f"⚠️ Commune IA fallback: {e}")

    return []

# ============================================================
# CONFIGURATION
# ============================================================

# --- Clustering ---
CLUSTER_WINDOW_HOURS = 72              # Fenêtre de clustering (3 jours)
MIN_CLUSTER_ITEMS = 2                  # Minimum d'items pour former un cluster
CLUSTER_SIMILARITY_THRESHOLD = 0.35    # Seuil de similarité contextuelle (relevé de 0.30)
CLUSTER_SIMILARITY_BROAD_THEME = 0.50  # Seuil rehaussé pour thèmes larges (relevé de 0.45)
CLUSTER_MERGE_THRESHOLD = 0.55         # Seuil pour fusionner deux clusters (relevé de 0.50)

# Thèmes trop larges qui regroupent des événements sans lien
BROAD_THEMES = {
    "securite_justice", "sante_social", "general",
    "culture_patrimoine", "politique_institutions",
    "eau_env", "economie_emploi", "energie_transports",
}

# --- Promotion en affaire ---
PROMOTION_MIN_SOURCES = 1              # Au moins 1 source (assoupli, était 2)
PROMOTION_MIN_MEDIA_TYPES = 1          # Au moins 1 type de média (article OU transcription)
PROMOTION_MIN_GRAVITY = 0.50           # Gravité minimum du cluster
PROMOTION_MIN_ITEMS = 2                # Minimum d'items — 1 seul article ne fait pas une affaire

# --- Cycle de vie ---
AFFAIR_ACTIVE_DAYS = 21                # Durée de vie active (3 semaines, était 7j)
AFFAIR_STALE_DAYS = 10                 # Jours sans activité → statut "stale" (était 4j)
MAX_ACTIVE_AFFAIRS = 100               # Maximum d'affaires actives — le frontend gère via priorités

# --- Anti boule de neige ---
SNOWBALL_MERGE_THRESHOLD = 5           # Nombre de fusions récentes (24h) déclenchant l'alerte
SNOWBALL_MAX_ITEMS = 25                # Au-delà de ce nb d'items, l'affaire est signalée
SNOWBALL_WINDOW_HOURS = 24             # Fenêtre de détection des fusions récentes

# --- Anti-fusion : cooldown entre tentatives ---
MAX_MATCH_ATTEMPTS = 4                 # Abandon définitif après 4 tentatives
MATCH_COOLDOWN_CYCLES = 3              # Attendre 3 cycles (~1h30 à 30min/cycle) entre chaque retry

# --- Fenêtre temporelle de fusion ---
# Un article n'est comparé qu'aux affaires dont la plage temporelle
# [premier article → dernier article] est à ±N jours de sa propre date.
# Empêche les fusions absurdes entre événements temporellement éloignés.
#
# La fenêtre est DÉPENDANTE DE LA CATÉGORIE D'ÉVÉNEMENT :
#   - Faits divers (meurtre, accident, noyade)  → cycle court (~3 jours)
#   - Sociétal (violences, grèves, épidémies)   → cycle moyen (~7 jours)
#   - Judiciaire / politique                    → cycle long (~14 jours)
#   - Mémoriel / économique                     → cycle très long (~10 jours)
#
# La valeur par défaut FUSION_TIME_WINDOW_DAYS est utilisée quand aucune
# catégorie n'est détectée. Ajustable via env var FUSION_TIME_WINDOW_DAYS.
try:
    FUSION_TIME_WINDOW_DAYS = int(os.environ.get("FUSION_TIME_WINDOW_DAYS", "5"))
except (ValueError, TypeError):
    FUSION_TIME_WINDOW_DAYS = 5

# Fenêtres spécifiques par catégorie d'événement (en jours).
# Ces valeurs ont été calibrées à partir de l'analyse des cycles d'actualité
# typiques en presse locale : les faits divers chauds durent 2-3 jours,
# les affaires judiciaires s'étalent sur 1-2 semaines (mise en examen →
# procès → verdict), les événements politiques suivent des cycles longs
# (élection → résultats → installation). Utilisez scripts/analyze_affair_spans.py
# sur la base réelle pour affiner ces valeurs si besoin.
FUSION_WINDOW_BY_CATEGORY = {
    # Faits divers à burst court : couverture intense 1-3 jours puis oubli
    "meurtre_arme": 3,
    "deces_retrouve_sans_vie": 3,
    "noyade_accident_mer": 3,
    "accident_route": 3,

    # Sociétal : cycle d'une semaine (développements, réactions, suites)
    "violence_conjugale": 7,
    "greve_mouvement_social": 7,
    "sante_epidemie": 7,
    "catastrophe_naturelle": 7,
    "trafic_drogue": 7,

    # Cycles longs : enquêtes, procès, campagnes
    "justice_proces": 14,
    "election_politique": 14,

    # Cycles récurrents / mémoriels / économiques
    "agriculture_economie": 10,
    "memoire_esclavage": 10,
    "commemoration_ceremonie": 10,
}

# --- Priorité des affaires ---
# 3 niveaux : hot (rouge), watch (jaune), minor (vert)
# IMPORTANT : avec la calibration IA stricte, gravity 0.70+ = vraiment grave
PRIORITY_HOT_GRAVITY = 0.75           # Gravité >= 0.75 → priorité HOT (meurtre, cyclone, crise)
PRIORITY_WATCH_GRAVITY = 0.55         # Gravité >= 0.55 → priorité WATCH (scandale, grève générale)
# En dessous → MINOR (tout le reste : faits divers, travaux, événements locaux)

# --- BMG ---
CANAL_WEIGHTS = {
    "radio": 0.35,
    "television": 0.30,
    "presse": 0.25,
    "reseaux_sociaux": 0.10,
}

PRESSE_WEIGHTS = {
    "France-Antilles Guadeloupe": 1.0,
    "France-Antilles": 1.0,
    "RCI Guadeloupe": 0.9,
    "RCI": 0.9,
    "La 1ère Guadeloupe": 0.7,
    "La 1ère": 0.7,
    "KaribInfo": 0.65,
    "Outremers360": 0.8,
}

RADIO_WEIGHTS = {
    "RCI": 1.0,
    "Guadeloupe La 1ère": 0.8,
    "NRJ Antilles": 0.4,
    "TRACE FM": 0.35,
}

# Mots vides pour le contexte
STOPWORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
    "est", "au", "aux", "ce", "qui", "que", "son", "sa", "ses",
    "sur", "par", "pour", "dans", "avec", "pas", "ne", "plus",
    "se", "ou", "il", "elle", "ont", "nous", "vous", "leur",
    "cette", "aussi", "tres", "tout", "fait", "bien", "mais",
    "comme", "peut", "etre", "autre", "entre", "apres", "avant",
    "avoir", "dire", "voir", "aller", "faire", "venir",
}


# ============================================================
# SERVICE PRINCIPAL
# ============================================================
class AffairLifecycleService:
    """Gère le cycle de vie complet des affaires."""

    def __init__(self, db=None):
        self.db = db
        if self.db is None:
            self._connect()

        if self.db is not None:
            # Collections
            self.candidates = self.db["topic_candidates"]
            self.clusters = self.db["topic_clusters"]
            self.affairs = self.db["affairs"]
            self.timeline = self.db["affair_timeline"]
            self.articles = self.db["articles_guadeloupe"]
            self.transcriptions = self.db["radio_transcriptions"]
            self.social = self.db["social_media_posts"]

            # Index
            self._ensure_indexes()
            logger.info("✅ AffairLifecycleService initialisé")
        else:
            logger.error("❌ Pas de DB — service inopérant")

    def _connect(self):
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("MONGO_DB_NAME", "veille_media")
        try:
            import certifi
            client = MongoClient(
                mongo_url,
                tlsCAFile=certifi.where() if "mongodb+srv" in mongo_url else None,
                serverSelectionTimeoutMS=10000,
            )
            client.admin.command("ping")
            self.db = client[db_name]
        except Exception as e:
            logger.error(f"❌ MongoDB: {e}")
            self.db = None

    def _ensure_indexes(self):
        """Crée les index nécessaires (simples + compound pour les requêtes fréquentes)."""
        try:
            # ── Candidates ──
            self.candidates.create_index([("created_at", DESCENDING)], background=True)
            self.candidates.create_index("cluster_id", background=True)
            self.candidates.create_index("source_type", background=True)
            self.candidates.create_index(
                [("source_type", 1), ("created_at", DESCENDING)],
                name="idx_cand_type_created", background=True,
            )

            # ── Clusters ──
            self.clusters.create_index([("created_at", DESCENDING)], background=True)
            self.clusters.create_index("status", background=True)
            self.clusters.create_index(
                [("status", 1), ("created_at", DESCENDING)],
                name="idx_clust_status_created", background=True,
            )

            # ── Affairs (requêtes les plus fréquentes) ──
            self.affairs.create_index([("created_at", DESCENDING)], background=True)
            self.affairs.create_index("status", background=True)
            self.affairs.create_index("priority", background=True)
            self.affairs.create_index([("last_activity", DESCENDING)], background=True)
            # Compound: status + tri (utilisé par le listing/filtrage front)
            self.affairs.create_index(
                [("status", 1), ("gravity_score", DESCENDING)],
                name="idx_aff_status_gravity", background=True,
            )
            self.affairs.create_index(
                [("status", 1), ("updated_at", DESCENDING)],
                name="idx_aff_status_updated", background=True,
            )
            self.affairs.create_index(
                [("status", 1), ("created_at", DESCENDING)],
                name="idx_aff_status_created", background=True,
            )

            # ── Timeline ──
            self.timeline.create_index("affair_id", background=True)
            self.timeline.create_index([("timestamp", DESCENDING)], background=True)
            self.timeline.create_index(
                [("affair_id", 1), ("timestamp", DESCENDING)],
                name="idx_tl_affair_ts", background=True,
            )

            # ── Articles (index compound pour les requêtes de recherche) ──
            try:
                self.articles.create_index(
                    [("date", DESCENDING), ("scraped_at", DESCENDING)],
                    name="idx_art_date_scraped", background=True,
                )
                self.articles.create_index(
                    [("source", 1), ("scraped_at", DESCENDING)],
                    name="idx_art_source_scraped", background=True,
                )
            except Exception:
                pass  # articles peut être dans une autre collection

            logger.info("✅ Index lifecycle créés avec succès")
        except Exception as e:
            logger.warning(f"⚠️ Index creation: {e}")

    # ============================================================
    # NORMALISATION AUTO — NOMS, LIEUX, TITRES
    # ============================================================

    @staticmethod
    def normalize_affair_data(affair_dict: dict) -> dict:
        """Corrige automatiquement les noms, lieux et titres dans un dict affaire.

        - Corrige le titre (STT + noms propres + lieux)
        - Corrige la description
        - Normalise les entités (elected, institutions)
        - Normalise les communes

        Retourne le dict modifié in-place.
        """
        if not _entity_aliases_ok:
            return affair_dict

        # 1. Corriger le titre (noms propres, lieux, STT)
        title = affair_dict.get("title", "")
        if title and _correct_stt:
            corrected_title = _correct_stt(title)
            if corrected_title != title:
                logger.info(f"✏️ Titre corrigé: '{title[:50]}' → '{corrected_title[:50]}'")
                affair_dict["title"] = corrected_title

        # 2. Corriger la description
        desc = affair_dict.get("description", "")
        if desc and _correct_stt:
            affair_dict["description"] = _correct_stt(desc)

        # 3. Normaliser les entités élues
        elected = affair_dict.get("elected", [])
        if elected and _correct_entities:
            affair_dict["elected"] = _correct_entities(elected)

        # 4. Normaliser les institutions
        institutions = affair_dict.get("institutions", [])
        if institutions and _correct_entities:
            affair_dict["institutions"] = _correct_entities(institutions)

        # 5. Normaliser les entités génériques
        entities = affair_dict.get("entities", [])
        if entities and _correct_entities:
            affair_dict["entities"] = _correct_entities(entities)

        # 6. Normaliser le primary_entity
        pe = affair_dict.get("primary_entity")
        if pe and _resolve_entity:
            affair_dict["primary_entity"] = _resolve_entity(pe)

        # 7. Reformulation du titre via GPT (contextualiser avec lieu/entités)
        if _ai_rewrite_title:
            try:
                new_title = _ai_rewrite_title(
                    raw_title=affair_dict.get("title", ""),
                    description=affair_dict.get("description", ""),
                    elected=affair_dict.get("elected", []),
                    institutions=affair_dict.get("institutions", []),
                    communes=affair_dict.get("communes", []),
                    theme=affair_dict.get("theme", ""),
                )
                if new_title:
                    affair_dict["_original_title"] = affair_dict.get("title", "")
                    affair_dict["title"] = new_title
            except Exception as e:
                logger.debug(f"Reformulation titre: {e}")

        return affair_dict

    # ============================================================
    # PRIORITÉ DES AFFAIRES
    # ============================================================
    @staticmethod
    def compute_priority(gravity: float, bmg: float = 0, item_count: int = 1,
                          sentiment: str = "neutre") -> str:
        """
        Calcule le niveau de priorité d'une affaire.
        - 'hot'   : crise avérée — toujours visible en premier
        - 'watch' : affaire sérieuse à surveiller
        - 'minor' : affaire mineure — repliée par défaut dans le frontend

        Le sentiment négatif boost la priorité (une affaire négative est plus urgente).
        """
        # Sentiment négatif = boost de gravity effectif pour le calcul de priorité
        sentiment_boost = 0.0
        if sentiment in ("négatif", "negatif", "très négatif", "tres negatif", "critique"):
            sentiment_boost = 0.08
        elif sentiment in ("mitigé", "mitige", "controversé"):
            sentiment_boost = 0.04
        effective_gravity = gravity + sentiment_boost

        # HOT : crise réelle (gravity très haute OU BMG élevé avec plusieurs sources)
        if bmg >= 0.65 and item_count >= 2:
            return "hot"
        if effective_gravity >= PRIORITY_HOT_GRAVITY:
            return "hot"
        # WATCH : affaire sérieuse
        if effective_gravity >= PRIORITY_WATCH_GRAVITY:
            return "watch"
        if bmg >= 0.35 and item_count >= 2:
            return "watch"
        # MINOR : tout le reste
        return "minor"

    @staticmethod
    def _dominant_sentiment(sentiments: list) -> str:
        """Retourne le sentiment le plus fréquent. En cas d'égalité, le plus négatif prime."""
        if not sentiments:
            return "neutre"
        counter = Counter(sentiments)
        # Ordre de priorité : le plus négatif l'emporte en cas d'égalité
        priority = ["très négatif", "tres negatif", "critique", "négatif", "negatif",
                     "mitigé", "mitige", "controversé", "neutre", "positif", "très positif"]
        max_count = max(counter.values())
        for sent in priority:
            if counter.get(sent, 0) == max_count:
                return sent
        return counter.most_common(1)[0][0]

    def _provisional_bmg(self, source_name: str, source_type: str = "article") -> dict:
        """Calcule un BMG provisoire à la création depuis la source de l'article fondateur.
        Sera recalculé correctement par _recalculate_active_bmg() au cycle suivant.
        """
        source_lower = (source_name or "").lower()

        # Pondérations presse (même ordre que PRESSE_WEIGHTS)
        press_lookup = {
            "france-antilles": 1.0, "france antilles": 1.0,
            "rci": 0.9, "la 1ère": 0.7, "la 1ere": 0.7,
            "outremers360": 0.8, "karibinfo": 0.65,
            "guadeloupe la 1ère": 0.7, "gwada": 0.5,
        }

        # Pondérations radio
        radio_lookup = {
            "rci": 1.0, "guadeloupe la 1ère": 0.8,
            "nrj antilles": 0.4, "trace fm": 0.35,
        }

        canal = "presse"
        source_weight = 0.2  # source inconnue → poids faible

        if source_type in ("transcription", "radio"):
            canal = "radio"
            for key, w in radio_lookup.items():
                if key in source_lower:
                    source_weight = w
                    break
        else:
            for key, w in press_lookup.items():
                if key in source_lower:
                    source_weight = w
                    break

        canal_weight = CANAL_WEIGHTS.get(canal, 0.25)
        bmg_value = round(canal_weight * source_weight, 3)

        return {
            "bmg": bmg_value,
            "bmg_details": {
                "bmg": bmg_value,
                "niveau_alerte": "vert" if bmg_value < 0.25 else "orange",
                "contributions": [{"canal": canal, "source": source_name,
                                   "weight": source_weight, "contribution": bmg_value}],
                "provisional": True,
                "note": "BMG provisoire (1 source) — recalculé après consolidation",
            },
            "bmg_history": [{"bmg": bmg_value, "at": datetime.utcnow().isoformat(), "provisional": True}],
        }

    # ============================================================
    # ÉTAPE 1 : INGESTION — Enregistrer un candidat
    # ============================================================
    def ingest_item(
        self, item: Dict[str, Any], source_type: str = "article"
    ) -> Dict[str, Any]:
        """
        Point d'entrée : enregistre un article/transcription/post
        comme candidat au clustering.

        source_type : 'article' | 'transcription' | 'social'
        """
        if self.db is None:
            return {"success": False, "error": "no_db"}

        # Extraire le contexte — PRIORITÉ : ai_summary > content > title
        # Le résumé IA est bien plus discriminant que le contenu brut
        # (3000 mots de contenu = trop de bruit, mots génériques partagés)
        title = item.get("title") or ""
        ai_summary = item.get("ai_summary") or ""
        content = item.get("content") or item.get("text") or ""

        if ai_summary:
            # Résumé IA disponible : utiliser titre + résumé (le plus ciblé)
            context_source = f"{title} {ai_summary}"
        elif content and len(content) > 100:
            # Pas de résumé IA : utiliser titre + premiers 500 mots du contenu
            # (limiter pour éviter la dilution par les mots génériques)
            words = content.split()[:500]
            context_source = f"{title} {' '.join(words)}"
        else:
            context_source = title

        context_tokens = self._extract_context_tokens(context_source, item)
        if len(context_tokens) < 3:
            return {"success": False, "reason": "too_short"}

        # Construire le candidat
        candidate = {
            "item_id": str(item.get("_id", "")),
            "source_type": source_type,
            "source_name": (
                item.get("source") or item.get("site") or
                item.get("radio") or item.get("stream_name") or
                item.get("platform") or "unknown"
            ),
            "title": title[:200],
            "context_tokens": list(context_tokens),
            "entities": item.get("elected") or item.get("entities") or [],
            "institutions": item.get("institutions") or [],
            "theme": item.get("theme", "general"),
            "keywords": item.get("keywords_found") or [],
            "gravity_score": item.get("gravity_score", 0),
            "importance_score": item.get("importance_score", 0),
            "sentiment": item.get("sentiment", "neutre"),
            "is_affair_candidate": item.get("gravity_score", 0) >= 0.40,
            "cluster_id": None,  # Sera rempli par le clustering
            "created_at": datetime.utcnow(),
            "item_date": self._parse_date(
                item.get("scraped_at") or item.get("captured_at") or
                item.get("date") or item.get("created_at")
            ) or datetime.utcnow(),
        }

        try:
            # Éviter les doublons
            existing = self.candidates.find_one({
                "item_id": candidate["item_id"],
                "source_type": source_type,
            })
            if existing:
                return {"success": True, "action": "already_exists", "id": str(existing["_id"])}

            result = self.candidates.insert_one(candidate)
            logger.debug(f"📥 Candidat ingéré: {source_type} '{title[:50]}'")
            return {
                "success": True,
                "action": "ingested",
                "id": str(result.inserted_id),
                "is_affair_candidate": candidate["is_affair_candidate"],
            }
        except Exception as e:
            logger.error(f"❌ Ingestion: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # ÉTAPE 2 : CLUSTERING — Regrouper les candidats par contexte
    # ============================================================
    def run_clustering(self) -> Dict[str, Any]:
        """
        Job principal de clustering.
        STRATÉGIE : IA d'abord (Grok regroupe les titres par événement),
        puis fallback sur similarité tokens si IA indisponible.
        """
        if self.db is None:
            return {"error": "no_db"}

        cutoff = datetime.utcnow() - timedelta(hours=CLUSTER_WINDOW_HOURS)

        # Récupérer les candidats non-clusterisés dans la fenêtre
        unclustered = list(self.candidates.find({
            "cluster_id": None,
            "created_at": {"$gte": cutoff},
        }).sort("created_at", DESCENDING).limit(500))

        if not unclustered:
            return {"clustered": 0, "new_clusters": 0, "merged": 0}

        logger.info(f"🔄 Clustering: {len(unclustered)} candidats à traiter")

        # Charger les clusters actifs existants
        active_clusters = list(self.clusters.find({
            "status": "active",
            "created_at": {"$gte": cutoff},
        }))

        stats = {"assigned_to_existing": 0, "new_clusters_created": 0, "merged": 0, "method": "tokens"}

        # Phase 1 : essayer de rattacher aux clusters existants (rapide, pas besoin d'IA)
        still_unassigned = []
        for cand in unclustered:
            assigned = self._try_assign_to_cluster(cand, active_clusters)
            if assigned:
                stats["assigned_to_existing"] += 1
            else:
                still_unassigned.append(cand)

        # Phase 2 : créer de nouveaux clusters — PRIORITÉ IA
        new_clusters = []
        if len(still_unassigned) >= MIN_CLUSTER_ITEMS:
            new_clusters = self._create_clusters_with_ai(still_unassigned)
            if new_clusters:
                stats["method"] = "ai"

        # Phase 2b : fallback tokens si IA indisponible ou échouée
        if not new_clusters and len(still_unassigned) >= MIN_CLUSTER_ITEMS:
            new_clusters = self._create_new_clusters(still_unassigned)
            stats["method"] = "tokens_fallback"

        stats["new_clusters_created"] = len(new_clusters)
        active_clusters.extend(new_clusters)

        # Phase 3 : tenter de fusionner les clusters proches
        merge_count = self._merge_similar_clusters(active_clusters)
        stats["merged"] = merge_count

        total = stats["assigned_to_existing"] + sum(
            len(c.get("items", [])) for c in new_clusters
        )
        logger.info(
            f"📊 Clustering terminé ({stats['method']}): {total} assignés, "
            f"{stats['new_clusters_created']} nouveaux clusters, "
            f"{stats['merged']} fusions"
        )
        return stats

    # ----------------------------------------------------------
    # Clustering par IA (Grok / xAI)
    # ----------------------------------------------------------
    def _create_clusters_with_ai(self, candidates: List[Dict]) -> List[Dict]:
        """
        Envoie les titres+résumés des candidats à l'IA et crée les clusters
        à partir de son regroupement sémantique.
        Traite par batchs de 40 articles max (limites tokens).
        """
        try:
            from backend.ai_groq_service import cluster_articles_with_ai, is_available
            if not is_available():
                return []
        except ImportError:
            try:
                from ai_groq_service import cluster_articles_with_ai, is_available
                if not is_available():
                    return []
            except ImportError:
                return []

        all_new_clusters = []
        batch_size = 40  # Max articles par appel IA

        for batch_start in range(0, len(candidates), batch_size):
            batch = candidates[batch_start:batch_start + batch_size]
            if len(batch) < MIN_CLUSTER_ITEMS:
                continue

            # Préparer les données pour l'IA
            articles_for_ai = []
            for cand in batch:
                articles_for_ai.append({
                    "title": cand.get("title", ""),
                    "ai_summary": "",  # On va chercher depuis l'article original
                    "date": cand.get("item_date"),
                })
                # Essayer de récupérer le résumé IA depuis l'article original
                item_id = cand.get("item_id", "")
                if item_id:
                    try:
                        orig = self.articles.find_one({"_id": ObjectId(item_id)})
                        if orig:
                            articles_for_ai[-1]["ai_summary"] = orig.get("ai_summary", "")
                    except Exception:
                        pass

            # Appel IA
            result = cluster_articles_with_ai(articles_for_ai)
            if not result or not result.get("groups"):
                continue

            # Créer les clusters à partir des groupes IA
            for group in result["groups"]:
                indices = group.get("articles", [])
                if len(indices) < MIN_CLUSTER_ITEMS:
                    continue

                # Indices IA sont 1-based → mapper aux candidats du batch
                group_candidates = []
                for idx in indices:
                    real_idx = idx - 1  # 1-based → 0-based
                    if 0 <= real_idx < len(batch):
                        group_candidates.append(batch[real_idx])

                if len(group_candidates) >= MIN_CLUSTER_ITEMS:
                    cluster = self._create_cluster(group_candidates)
                    if cluster:
                        # Enrichir le titre du cluster avec le label IA
                        ai_label = group.get("label", "")
                        if ai_label:
                            self.clusters.update_one(
                                {"_id": cluster["_id"]},
                                {"$set": {"ai_label": ai_label}}
                            )
                            cluster["ai_label"] = ai_label
                        all_new_clusters.append(cluster)

            logger.info(
                f"🤖 Batch IA: {len(batch)} candidats → "
                f"{len([g for g in result['groups'] if len(g.get('articles', [])) >= 2])} groupes"
            )

        return all_new_clusters

    def _try_assign_to_cluster(
        self, candidate: Dict, clusters: List[Dict]
    ) -> bool:
        """Essaye de rattacher un candidat à un cluster existant."""
        cand_tokens = set(candidate.get("context_tokens", []))
        cand_theme = candidate.get("theme", "")
        cand_entities = set(candidate.get("entities", []))
        cand_date = candidate.get("item_date")

        best_cluster = None
        best_score = 0

        for cluster in clusters:
            cl_theme = cluster.get("dominant_theme", "")
            cl_entities = set(cluster.get("all_entities", []))

            # Protection thèmes larges : exiger entité commune
            is_broad = cand_theme in BROAD_THEMES or cl_theme in BROAD_THEMES
            if is_broad and not (cand_entities & cl_entities):
                continue

            score = self._candidate_cluster_similarity(
                cand_tokens, cand_theme, cand_entities, cluster,
                cand_date=cand_date,
            )
            threshold = CLUSTER_SIMILARITY_BROAD_THEME if is_broad else CLUSTER_SIMILARITY_THRESHOLD
            if score > best_score and score >= threshold:
                best_score = score
                best_cluster = cluster

        if best_cluster:
            cluster_id = best_cluster["_id"]
            # Mettre à jour le candidat
            self.candidates.update_one(
                {"_id": candidate["_id"]},
                {"$set": {"cluster_id": str(cluster_id)}}
            )
            # Mettre à jour le cluster
            self.clusters.update_one(
                {"_id": cluster_id},
                {
                    "$push": {"items": {
                        "candidate_id": str(candidate["_id"]),
                        "item_id": candidate["item_id"],
                        "source_type": candidate["source_type"],
                        "source_name": candidate["source_name"],
                        "title": candidate["title"],
                        "score": best_score,
                    }},
                    "$addToSet": {
                        "all_entities": {"$each": candidate.get("entities", [])},
                        "all_sources": candidate["source_name"],
                        "all_source_types": candidate["source_type"],
                        "all_tokens": {"$each": list(cand_tokens)[:30]},
                    },
                    "$max": {"max_gravity": candidate.get("gravity_score", 0)},
                    "$set": {"last_activity": datetime.utcnow()},
                    "$inc": {"item_count": 1},
                }
            )
            # Mettre à jour le cache local
            best_cluster.setdefault("all_tokens_set", set()).update(cand_tokens)
            return True

        return False

    def _create_new_clusters(self, candidates: List[Dict]) -> List[Dict]:
        """Crée de nouveaux clusters à partir des candidats non-assignés."""
        if len(candidates) < MIN_CLUSTER_ITEMS:
            return []

        new_clusters = []
        used = set()

        for i, cand_a in enumerate(candidates):
            if i in used:
                continue

            group = [cand_a]
            group_tokens = set(cand_a.get("context_tokens", []))
            group_entities = set(cand_a.get("entities", []))
            group_theme = cand_a.get("theme", "")

            date_a = cand_a.get("item_date")

            for j, cand_b in enumerate(candidates):
                if j <= i or j in used:
                    continue

                b_tokens = set(cand_b.get("context_tokens", []))
                b_entities = set(cand_b.get("entities", []))
                b_theme = cand_b.get("theme", "")
                date_b = cand_b.get("item_date")

                sim = self._pairwise_similarity(
                    group_tokens, group_theme, group_entities,
                    b_tokens, b_theme, b_entities,
                    date_a=date_a, date_b=date_b,
                )

                # Seuil adaptatif : plus strict pour les thèmes larges
                is_broad = group_theme in BROAD_THEMES or b_theme in BROAD_THEMES
                threshold = CLUSTER_SIMILARITY_BROAD_THEME if is_broad else CLUSTER_SIMILARITY_THRESHOLD

                # Pour les thèmes larges, exiger au moins 1 entité commune
                # sinon un incendie se retrouve avec un procès politique
                has_entity_overlap = bool(group_entities & b_entities)
                if is_broad and not has_entity_overlap:
                    continue  # Pas d'entité commune + thème large → pas de regroupement

                if sim >= threshold:
                    group.append(cand_b)
                    group_tokens.update(b_tokens)
                    group_entities.update(b_entities)
                    used.add(j)

            if len(group) >= MIN_CLUSTER_ITEMS:
                used.add(i)
                cluster = self._create_cluster(group)
                if cluster:
                    new_clusters.append(cluster)

        return new_clusters

    def _create_cluster(self, candidates: List[Dict]) -> Optional[Dict]:
        """Crée un cluster en base depuis une liste de candidats."""
        all_tokens = set()
        all_entities = set()
        all_sources = set()
        all_source_types = set()
        max_gravity = 0
        themes = Counter()

        items_list = []
        for c in candidates:
            all_tokens.update(c.get("context_tokens", []))
            all_entities.update(c.get("entities", []))
            all_sources.add(c.get("source_name", ""))
            all_source_types.add(c.get("source_type", ""))
            max_gravity = max(max_gravity, c.get("gravity_score", 0))
            themes[c.get("theme", "general")] += 1
            items_list.append({
                "candidate_id": str(c["_id"]),
                "item_id": c["item_id"],
                "source_type": c["source_type"],
                "source_name": c["source_name"],
                "title": c["title"],
            })

        # Titre du cluster = titre du candidat avec la plus haute gravité
        best_title = max(candidates, key=lambda c: c.get("gravity_score", 0)).get("title", "")
        dominant_theme = themes.most_common(1)[0][0] if themes else "general"

        cluster_doc = {
            "title": best_title[:200],
            "dominant_theme": dominant_theme,
            "all_entities": sorted(all_entities),
            "all_sources": sorted(all_sources),
            "all_source_types": sorted(all_source_types),
            "all_tokens": sorted(list(all_tokens)[:100]),
            "max_gravity": max_gravity,
            "item_count": len(candidates),
            "items": items_list,
            "status": "active",
            "promoted_to_affair": False,
            "affair_id": None,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
        }

        try:
            result = self.clusters.insert_one(cluster_doc)
            cluster_id = result.inserted_id

            # Lier les candidats au cluster
            cand_ids = [c["_id"] for c in candidates]
            self.candidates.update_many(
                {"_id": {"$in": cand_ids}},
                {"$set": {"cluster_id": str(cluster_id)}}
            )

            cluster_doc["_id"] = cluster_id
            cluster_doc["all_tokens_set"] = all_tokens
            logger.info(
                f"🆕 Cluster créé: '{best_title[:50]}' "
                f"({len(candidates)} items, {len(all_sources)} sources)"
            )
            return cluster_doc
        except Exception as e:
            logger.error(f"❌ Création cluster: {e}")
            return None

    def _merge_similar_clusters(self, clusters: List[Dict]) -> int:
        """Fusionne les clusters trop similaires."""
        merged = 0
        merged_ids = set()

        for i, cl_a in enumerate(clusters):
            if str(cl_a.get("_id", "")) in merged_ids:
                continue
            for j, cl_b in enumerate(clusters):
                if j <= i or str(cl_b.get("_id", "")) in merged_ids:
                    continue

                sim = self._cluster_cluster_similarity(cl_a, cl_b)
                if sim >= CLUSTER_MERGE_THRESHOLD:
                    # Vérifier cohérence sémantique avant fusion
                    coherent, block_reason = self._titles_are_coherent(
                        cl_a.get("title", ""), cl_b.get("title", ""),
                        cl_a.get("description", ""), cl_b.get("description", ""),
                    )
                    if not coherent:
                        logger.warning(f"🚫 Fusion cluster↔cluster BLOQUÉE: {block_reason}")
                        continue
                    self._do_merge(cl_a, cl_b)
                    merged_ids.add(str(cl_b["_id"]))
                    merged += 1

        return merged

    def _do_merge(self, keep: Dict, absorb: Dict):
        """Fusionne `absorb` dans `keep`."""
        try:
            # Déplacer les items de absorb vers keep
            self.clusters.update_one(
                {"_id": keep["_id"]},
                {
                    "$push": {"items": {"$each": absorb.get("items", [])}},
                    "$addToSet": {
                        "all_entities": {"$each": absorb.get("all_entities", [])},
                        "all_sources": {"$each": absorb.get("all_sources", [])},
                        "all_source_types": {"$each": absorb.get("all_source_types", [])},
                        "all_tokens": {"$each": absorb.get("all_tokens", [])[:50]},
                    },
                    "$max": {"max_gravity": absorb.get("max_gravity", 0)},
                    "$inc": {"item_count": absorb.get("item_count", 0)},
                    "$set": {"last_activity": datetime.utcnow()},
                }
            )
            # Marquer absorb comme fusionné
            self.clusters.update_one(
                {"_id": absorb["_id"]},
                {"$set": {"status": "merged", "merged_into": str(keep["_id"])}}
            )
            # Relien les candidats
            self.candidates.update_many(
                {"cluster_id": str(absorb["_id"])},
                {"$set": {"cluster_id": str(keep["_id"])}}
            )
            logger.info(f"🔗 Clusters fusionnés: {absorb.get('title', '')[:40]} → {keep.get('title', '')[:40]}")
        except Exception as e:
            logger.error(f"❌ Fusion clusters: {e}")

    # ============================================================
    # ÉTAPE 3 : PROMOTION — Cluster → Affaire
    # ============================================================
    def run_promotion(self) -> Dict[str, Any]:
        """
        Évalue chaque cluster actif et promeut en affaire
        ceux qui remplissent les critères.
        """
        if self.db is None:
            return {"error": "no_db"}

        active_clusters = list(self.clusters.find({
            "status": "active",
            "promoted_to_affair": False,
        }))

        stats = {"evaluated": len(active_clusters), "promoted": 0, "details": []}

        for cluster in active_clusters:
            should_promote, reasons = self._evaluate_promotion(cluster)

            if should_promote:
                affair_id = self._promote_to_affair(cluster)
                if affair_id:
                    stats["promoted"] += 1
                    stats["details"].append({
                        "cluster_title": cluster.get("title", "")[:60],
                        "affair_id": affair_id,
                        "reasons": reasons,
                        "items": cluster.get("item_count", 0),
                        "sources": cluster.get("all_sources", []),
                    })

        logger.info(
            f"📊 Promotion: {stats['promoted']}/{stats['evaluated']} clusters promus"
        )
        return stats

    def _evaluate_promotion(self, cluster: Dict) -> Tuple[bool, List[str]]:
        """Évalue si un cluster mérite d'être promu en affaire."""
        reasons = []

        item_count = cluster.get("item_count", 0)
        sources = cluster.get("all_sources", [])
        source_types = cluster.get("all_source_types", [])
        max_gravity = cluster.get("max_gravity", 0)

        # Critère 1 : assez d'items
        if item_count >= PROMOTION_MIN_ITEMS:
            reasons.append(f"items={item_count}")
        else:
            return False, [f"pas assez d'items ({item_count}<{PROMOTION_MIN_ITEMS})"]

        # Critère 2 : multi-source
        unique_sources = len(set(sources))
        if unique_sources >= PROMOTION_MIN_SOURCES:
            reasons.append(f"sources={unique_sources}")
        else:
            # Exception : si gravité très haute (crise), une source suffit
            if max_gravity >= 0.85 and item_count >= 3:
                reasons.append(f"haute_gravité_bypass (gravity={max_gravity})")
            else:
                return False, [f"pas assez de sources ({unique_sources}<{PROMOTION_MIN_SOURCES})"]

        # Critère 3 : gravité suffisante
        if max_gravity >= PROMOTION_MIN_GRAVITY:
            reasons.append(f"gravity={max_gravity}")
        else:
            return False, [f"gravité insuffisante ({max_gravity}<{PROMOTION_MIN_GRAVITY})"]

        # Critère 4 : multi-type (bonus, pas bloquant)
        if len(set(source_types)) >= 2:
            reasons.append("cross_media")

        return True, reasons

    def _promote_to_affair(self, cluster: Dict) -> Optional[str]:
        """Crée une affaire depuis un cluster promu."""
        try:
            # Vérifier s'il existe déjà une affaire très similaire
            existing = self._find_similar_affair(cluster)
            if existing:
                # Fusionner avec l'affaire existante
                self._merge_cluster_into_affair(cluster, existing)
                return str(existing["_id"])

            # Construire l'entité dominante
            entities = cluster.get("all_entities", [])
            entity_counts = Counter(entities)
            primary_entity = entity_counts.most_common(1)[0][0] if entity_counts else None

            # Construire les listes d'IDs par type
            article_ids = []
            transcription_ids = []
            social_ids = []
            for item in cluster.get("items", []):
                iid = item.get("item_id", "")
                if item["source_type"] == "article":
                    article_ids.append(iid)
                elif item["source_type"] == "transcription":
                    transcription_ids.append(iid)
                elif item["source_type"] == "social":
                    social_ids.append(iid)

            # Créer l'affaire — utiliser le label IA s'il existe (plus clair)
            ai_label = cluster.get("ai_label", "")
            affair_title = ai_label if ai_label else cluster.get("title", "Affaire sans titre")
            affair = {
                "title": affair_title,
                "description": self._generate_affair_description(cluster),
                "primary_entity": primary_entity,
                "entities": sorted(set(entities)),
                "elected": [e for e in entities if not self._is_institution(e)],
                "institutions": [e for e in entities if self._is_institution(e)],
                "keywords": cluster.get("all_tokens", [])[:20],
                "theme": cluster.get("dominant_theme", "general"),
                "gravity_score": cluster.get("max_gravity", 0),
                "affair_type": self._classify_affair_type_cluster(cluster),
                "status": "active",
                "articles": article_ids,
                "radio_transcriptions": transcription_ids,
                "social_posts": social_ids,
                "sources": cluster.get("all_sources", []),
                "source_types": cluster.get("all_source_types", []),
                "item_count": cluster.get("item_count", 0),
                "cluster_id": str(cluster["_id"]),
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "promoted_at": datetime.utcnow(),
                "bmg": 0,
                "bmg_details": {},
                "bmg_history": [],
            }

            # Calculer le BMG initial
            bmg_result = self.calculate_bmg(affair)
            affair["bmg"] = bmg_result["bmg"]
            affair["bmg_details"] = bmg_result
            affair["priority"] = self.compute_priority(
                affair["gravity_score"], affair["bmg"], affair.get("item_count", 1)
            )

            result = self.affairs.insert_one(affair)
            affair_id = str(result.inserted_id)

            # Marquer le cluster comme promu
            self.clusters.update_one(
                {"_id": cluster["_id"]},
                {"$set": {
                    "promoted_to_affair": True,
                    "affair_id": affair_id,
                    "promoted_at": datetime.utcnow(),
                }}
            )

            # Timeline
            self.timeline.insert_one({
                "affair_id": affair_id,
                "event": "created",
                "details": {
                    "from_cluster": str(cluster["_id"]),
                    "items": cluster.get("item_count", 0),
                    "sources": cluster.get("all_sources", []),
                    "gravity": cluster.get("max_gravity", 0),
                },
                "timestamp": datetime.utcnow(),
            })

            logger.info(
                f"🎯 AFFAIRE CRÉÉE: '{affair['title'][:60]}' "
                f"(BMG={bmg_result['bmg']:.2f}, {affair['item_count']} items, "
                f"sources={affair['sources']})"
            )

            # 🔔 Notification push
            if _push_ok and _push_notify:
                try:
                    _push_notify(affair)
                except Exception as push_err:
                    logger.debug(f"Push notification: {push_err}")

            # Auto-génération du contexte IA
            try:
                self.generate_affair_context(affair_id)
            except Exception as ctx_err:
                logger.debug(f"Auto-contexte IA cluster: {ctx_err}")
            return affair_id

        except Exception as e:
            logger.error(f"❌ Promotion: {e}")
            return None

    def _find_similar_affair(self, cluster: Dict) -> Optional[Dict]:
        """Cherche une affaire existante similaire au cluster.

        Détection doublons renforcée :
        - Comparaison titre (SequenceMatcher) : seuil 0.60
        - Entités communes pondérées (spécifiques vs génériques)
        - Score combiné titre + entités + tokens
        """
        cluster_entities = set(cluster.get("all_entities", []))
        cluster_tokens = set(cluster.get("all_tokens", []))
        cluster_title = cluster.get("title", "").lower().strip()

        # Fenêtre temporelle : ne considérer que les affaires dont la plage
        # [created_at → last_activity] est à ±FUSION_TIME_WINDOW_DAYS de la
        # date du cluster. On charge d'abord les affaires actives standard
        # puis on applique le filtre span-based en Python (plus précis qu'un
        # filtre Mongo simple sur created_at).
        cluster_date = (
            self._parse_dt(cluster.get("created_at"))
            or self._parse_dt(cluster.get("last_activity"))
            or datetime.utcnow()
        )
        active_floor = datetime.utcnow() - timedelta(days=AFFAIR_ACTIVE_DAYS)
        all_active = self.affairs.find({
            "status": "active",
            "$or": [
                {"last_activity": {"$gte": active_floor}},
                {"created_at": {"$gte": active_floor}},
            ],
        })
        recent_affairs = self._filter_affairs_by_time_window(
            list(all_active), cluster_date
        )

        best = None
        best_score = 0

        for affair in recent_affairs:
            aff_entities = set(affair.get("entities", []))
            aff_tokens = set(affair.get("keywords", []))
            aff_title = affair.get("title", "").lower().strip()

            # 1) Similarité titre (SequenceMatcher) — détecte les quasi-doublons
            title_sim = SequenceMatcher(None, cluster_title, aff_title).ratio()
            if title_sim >= 0.65:
                # Vérifier cohérence sémantique avant de conclure doublon
                coherent, block_reason = self._titles_are_coherent(
                    cluster.get("title", ""), affair.get("title", ""),
                    cluster.get("description", ""), affair.get("description", ""),
                )
                if not coherent:
                    logger.warning(f"🚫 Doublon titre BLOQUÉ (cluster→affaire): {block_reason}")
                    continue
                # Titres quasi-identiques + cohérents → c'est un doublon
                logger.info(f"   🔗 Doublon détecté par titre (sim={title_sim:.2f}): "
                           f"'{cluster_title[:40]}' ≈ '{aff_title[:40]}'")
                return affair

            # 2) Entités communes (pondérées)
            common_entities = cluster_entities & aff_entities
            # Filtrer les entités génériques pour le scoring
            specific_common = set()
            for e in common_entities:
                if e.lower() not in self.GENERIC_ELECTED:
                    specific_common.add(e)
            entity_score = (len(specific_common) * 2 + len(common_entities - specific_common)) / max(len(cluster_entities | aff_entities), 1)

            # 3) Tokens communs
            common_tokens = cluster_tokens & aff_tokens
            token_score = len(common_tokens) / max(min(len(cluster_tokens), len(aff_tokens)), 1)

            # 4) Bonus titre partiel
            title_bonus = title_sim * 0.3 if title_sim >= 0.4 else 0

            combined = entity_score * 0.5 + token_score * 0.3 + title_bonus
            if combined > best_score and combined >= 0.35:
                # Vérifier cohérence sémantique
                coherent, block_reason = self._titles_are_coherent(
                    cluster.get("title", ""), affair.get("title", ""),
                    cluster.get("description", ""), affair.get("description", ""),
                )
                if not coherent:
                    logger.warning(f"🚫 Fusion cluster→affaire BLOQUÉE: {block_reason}")
                    continue
                best_score = combined
                best = affair

        return best

    def _merge_cluster_into_affair(self, cluster: Dict, affair: Dict):
        """Fusionne un cluster dans une affaire existante."""
        new_articles = []
        new_transcriptions = []
        new_social = []

        for item in cluster.get("items", []):
            iid = item.get("item_id", "")
            if item["source_type"] == "article":
                new_articles.append(iid)
            elif item["source_type"] == "transcription":
                new_transcriptions.append(iid)
            elif item["source_type"] == "social":
                new_social.append(iid)

        update = {
            "$addToSet": {
                "entities": {"$each": cluster.get("all_entities", [])},
                "sources": {"$each": cluster.get("all_sources", [])},
                "source_types": {"$each": cluster.get("all_source_types", [])},
            },
            "$push": {},
            "$max": {"gravity_score": cluster.get("max_gravity", 0)},
            "$inc": {"item_count": cluster.get("item_count", 0)},
            "$set": {"last_activity": datetime.utcnow()},
        }

        if new_articles:
            update["$addToSet"]["articles"] = {"$each": new_articles}
        if new_transcriptions:
            update["$addToSet"]["radio_transcriptions"] = {"$each": new_transcriptions}
        if new_social:
            update["$addToSet"]["social_posts"] = {"$each": new_social}

        # Cleanup empty $push
        if not update["$push"]:
            del update["$push"]

        self.affairs.update_one({"_id": affair["_id"]}, update)

        # Recalculer BMG
        updated_affair = self.affairs.find_one({"_id": affair["_id"]})
        if updated_affair:
            bmg = self.calculate_bmg(updated_affair)
            self.affairs.update_one(
                {"_id": affair["_id"]},
                {"$set": {"bmg": bmg["bmg"], "bmg_details": bmg}}
            )

        # Marquer cluster
        self.clusters.update_one(
            {"_id": cluster["_id"]},
            {"$set": {
                "promoted_to_affair": True,
                "affair_id": str(affair["_id"]),
                "merged_into_existing": True,
            }}
        )

        # Timeline
        self.timeline.insert_one({
            "affair_id": str(affair["_id"]),
            "event": "cluster_merged",
            "details": {
                "cluster_id": str(cluster["_id"]),
                "new_items": cluster.get("item_count", 0),
                "new_sources": cluster.get("all_sources", []),
            },
            "timestamp": datetime.utcnow(),
        })

        logger.info(
            f"🔗 Cluster fusionné dans affaire '{affair.get('title', '')[:50]}'"
        )

    # ============================================================
    # ÉTAPE 4 : CALCUL BMG — Bruit Médiatique Global
    # ============================================================
    def _safe_object_ids(self, ids: list) -> list:
        """Convertit une liste d'IDs en ObjectId de manière robuste.
        Accepte: str, ObjectId, ou tout format valide."""
        result = []
        for a in ids:
            if not a:
                continue
            if isinstance(a, ObjectId):
                result.append(a)
            else:
                try:
                    result.append(ObjectId(str(a)))
                except Exception:
                    pass
        return result

    def calculate_bmg(self, affair: Dict) -> Dict[str, Any]:
        """
        Calcule le BMG d'une affaire à partir de ses items réels.
        Formule : BMG = Σ (BNP_canal × poids_canal)
        BNP_canal = Σ (importance × engagement × poids_média) / Σ poids_média
        """
        canal_data = {
            "presse": {"score_sum": 0, "weight_sum": 0, "count": 0, "items": []},
            "radio": {"score_sum": 0, "weight_sum": 0, "count": 0, "items": []},
            "television": {"score_sum": 0, "weight_sum": 0, "count": 0, "items": []},
            "reseaux_sociaux": {"score_sum": 0, "weight_sum": 0, "count": 0, "items": []},
        }

        affair_title = affair.get("title", "?")[:40]

        # Presse (articles)
        article_ids = affair.get("articles", [])
        if article_ids:
            try:
                obj_ids = self._safe_object_ids(article_ids)
                logger.info(f"   📊 BMG '{affair_title}': {len(article_ids)} articles IDs → "
                           f"{len(obj_ids)} ObjectId valides")
                docs = list(self.articles.find({"_id": {"$in": obj_ids}})) if obj_ids else []
                logger.info(f"   📊 BMG '{affair_title}': {len(docs)} articles trouvés en base")
                for doc in docs:
                    importance = doc.get("importance_score") or doc.get("gravity_score", 0.3)
                    source = doc.get("source", "")
                    weight = self._get_presse_weight(source)
                    engagement = min(1.0, 0.5 + (doc.get("word_count", 0) / 3000) * 0.3)

                    bnp = importance * engagement * weight
                    canal_data["presse"]["score_sum"] += bnp
                    canal_data["presse"]["weight_sum"] += weight
                    canal_data["presse"]["count"] += 1
                    canal_data["presse"]["items"].append({
                        "source": source, "importance": round(importance, 2),
                        "bnp": round(bnp, 3),
                    })
            except Exception as e:
                logger.debug(f"BMG presse: {e}")

        # Radio (transcriptions)
        trans_ids = affair.get("radio_transcriptions", [])
        if trans_ids:
            try:
                obj_ids = self._safe_object_ids(trans_ids)
                docs = list(self.transcriptions.find({"_id": {"$in": obj_ids}})) if obj_ids else []
                for doc in docs:
                    importance = doc.get("importance_score") or doc.get("score_importance", 0.4)
                    station = doc.get("radio") or doc.get("stream_name", "")
                    weight = self._get_radio_weight(station)
                    # Durée de mention comme proxy d'engagement
                    text_len = len(doc.get("text", ""))
                    engagement = min(1.0, 0.4 + (text_len / 5000) * 0.4)

                    bnp = importance * engagement * weight
                    canal_data["radio"]["score_sum"] += bnp
                    canal_data["radio"]["weight_sum"] += weight
                    canal_data["radio"]["count"] += 1
                    canal_data["radio"]["items"].append({
                        "station": station, "importance": round(importance, 2),
                        "bnp": round(bnp, 3),
                    })
            except Exception as e:
                logger.debug(f"BMG radio: {e}")

        # Réseaux sociaux — utilise gravity_score IA si disponible
        social_ids = affair.get("social_posts", [])
        if social_ids:
            try:
                obj_ids = self._safe_object_ids(social_ids)
                docs = list(self.social.find({"_id": {"$in": obj_ids}})) if obj_ids else []
                for doc in docs:
                    likes = doc.get("likes", 0) or doc.get("reactions", 0)
                    shares = doc.get("shares", 0) or doc.get("retweets", 0)
                    comments = doc.get("comments_count", 0) or doc.get("comments", 0) or doc.get("replies", 0)
                    engagement = min(1.0, (likes + shares * 3 + comments * 2) / 500)

                    # Utiliser gravity_score IA si enrichi, sinon fallback
                    importance = doc.get("gravity_score") or doc.get("relevance_score", 0.3)

                    # Poids selon la plateforme
                    platform = doc.get("platform", "")
                    if platform == "facebook":
                        weight = 0.6  # Pages médias locales = haute valeur
                    elif platform == "twitter":
                        weight = 0.5
                    else:
                        weight = 0.4  # Instagram

                    bnp = importance * max(engagement, 0.1) * weight
                    canal_data["reseaux_sociaux"]["score_sum"] += bnp
                    canal_data["reseaux_sociaux"]["weight_sum"] += weight
                    canal_data["reseaux_sociaux"]["count"] += 1
                    canal_data["reseaux_sociaux"]["items"].append({
                        "platform": platform, "author": doc.get("author", ""),
                        "importance": round(importance, 2), "bnp": round(bnp, 3),
                    })
            except Exception as e:
                logger.debug(f"BMG social: {e}")

        # Calculer BNP par canal
        # Le BNP intègre un facteur de volume (log) borné pour préserver la
        # granularité du tri en haut de classement. Sans cap, log2(count+1)
        # combiné aux boosts multi-canal saturait à 1.0 dès 3 canaux × 4 articles
        # et tout le top 10 finissait avec un BMG identique.
        import math
        VOLUME_FACTOR_CAP = 2.0  # ≈ 7 articles donne le boost max
        bnp_by_canal = {}
        for canal, data in canal_data.items():
            if data["weight_sum"] > 0:
                base_bnp = data["score_sum"] / data["weight_sum"]
                # Facteur volume : log2(count+1), borné à 2.0
                # (1→1.0, 2→1.58, 4→2.0, 7→2.0, 16→2.0)
                volume_factor = min(math.log2(data["count"] + 1), VOLUME_FACTOR_CAP)
                bnp_by_canal[canal] = min(1.0, base_bnp * volume_factor)
            else:
                bnp_by_canal[canal] = 0

        # BMG global
        bmg = sum(bnp_by_canal.get(c, 0) * w for c, w in CANAL_WEIGHTS.items())

        # Bonus multi-canal : si l'affaire est présente sur 2+ canaux, boost
        active_canals = sum(1 for d in canal_data.values() if d["count"] > 0)
        if active_canals >= 3:
            bmg *= 1.25  # 3+ canaux = forte amplification
        elif active_canals >= 2:
            bmg *= 1.12  # 2 canaux = boost notable

        # Bonus nombre total de sources uniques
        unique_sources = len(set(affair.get("sources", [])))
        if unique_sources >= 4:
            bmg *= 1.15  # 4+ médias différents qui en parlent
        elif unique_sources >= 2:
            bmg *= 1.05

        bmg = min(1.0, bmg)

        # Niveau d'alerte
        if bmg >= 0.75:
            niveau = "CRITIQUE"
        elif bmg >= 0.55:
            niveau = "ÉLEVÉ"
        elif bmg >= 0.35:
            niveau = "MODÉRÉ"
        elif bmg >= 0.15:
            niveau = "FAIBLE"
        else:
            niveau = "MINIMAL"

        total_items = sum(d["count"] for d in canal_data.values())
        dominant = max(bnp_by_canal, key=bnp_by_canal.get) if any(bnp_by_canal.values()) else None

        logger.info(f"   📊 BMG '{affair_title}': {round(bmg, 3)} ({niveau}) — "
                    f"presse={round(bnp_by_canal.get('presse', 0), 3)} "
                    f"radio={round(bnp_by_canal.get('radio', 0), 3)} "
                    f"tv={round(bnp_by_canal.get('television', 0), 3)} "
                    f"social={round(bnp_by_canal.get('reseaux_sociaux', 0), 3)} — "
                    f"{total_items} items, {active_canals} canaux")

        return {
            "bmg": round(bmg, 3),
            "bnp_by_canal": {k: round(v, 3) for k, v in bnp_by_canal.items()},
            "niveau_alerte": niveau,
            "total_items": total_items,
            "active_canals": active_canals,
            "dominant_canal": dominant,
            "canal_details": {
                k: {"count": v["count"], "items": v["items"][:5]}
                for k, v in canal_data.items() if v["count"] > 0
            },
            "multi_canal_bonus": active_canals >= 2,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    # ============================================================
    # ÉTAPE 5 : CYCLE DE VIE — Mise à jour périodique
    # ============================================================
    def update_affair_lifecycle(self) -> Dict[str, Any]:
        """
        Job périodique : met à jour le statut des affaires.
        - Recalcule le BMG
        - Passe en 'stale' si pas d'activité
        - Archive les affaires trop vieilles
        """
        if self.db is None:
            return {"error": "no_db"}

        stats = {"updated": 0, "stale": 0, "archived": 0}
        now = datetime.utcnow()

        active_affairs = list(self.affairs.find({"status": "active"}))

        for affair in active_affairs:
            affair_id = str(affair["_id"])
            last_activity = affair.get("last_activity") or affair.get("created_at", now)

            if isinstance(last_activity, str):
                try:
                    last_activity = datetime.fromisoformat(last_activity)
                except ValueError:
                    last_activity = now

            days_inactive = (now - last_activity).days

            # Bonus de durée selon l'importance de l'affaire :
            # Plus une affaire a d'articles/gravité, plus elle reste active longtemps
            item_count = affair.get("item_count", 1)
            affair_gravity = affair.get("gravity_score", 0)
            is_hot = affair.get("priority") == "hot"
            # Bonus : +3j si >5 articles, +5j si >10, +7j si hot, +3j si gravité > 0.7
            bonus_days = 0
            if item_count >= 10:
                bonus_days += 5
            elif item_count >= 5:
                bonus_days += 3
            if is_hot:
                bonus_days += 7
            if affair_gravity >= 0.7:
                bonus_days += 3

            effective_stale_days = AFFAIR_STALE_DAYS + bonus_days
            effective_active_days = AFFAIR_ACTIVE_DAYS + bonus_days

            if days_inactive >= effective_active_days:
                # Archiver
                self.affairs.update_one(
                    {"_id": affair["_id"]},
                    {"$set": {"status": "archived", "archived_at": now}}
                )
                self.timeline.insert_one({
                    "affair_id": affair_id,
                    "event": "archived",
                    "details": {"days_inactive": days_inactive, "effective_limit": effective_active_days},
                    "timestamp": now,
                })
                stats["archived"] += 1

            elif days_inactive >= effective_stale_days:
                # Stale
                self.affairs.update_one(
                    {"_id": affair["_id"]},
                    {"$set": {"status": "stale"}}
                )
                stats["stale"] += 1

            else:
                # Recalculer BMG
                bmg = self.calculate_bmg(affair)
                old_bmg = affair.get("bmg", 0)

                new_priority = self.compute_priority(
                    affair.get("gravity_score", 0), bmg["bmg"], affair.get("item_count", 1)
                )
                update_set = {
                    "bmg": bmg["bmg"],
                    "bmg_details": bmg,
                    "priority": new_priority,
                }

                # Sauvegarder l'historique BMG
                self.affairs.update_one(
                    {"_id": affair["_id"]},
                    {
                        "$set": update_set,
                        "$push": {"bmg_history": {
                            "$each": [{"bmg": bmg["bmg"], "at": now.isoformat()}],
                            "$slice": -30,  # Garder les 30 derniers
                        }},
                    }
                )
                stats["updated"] += 1

                # Timeline si changement significatif
                if abs(bmg["bmg"] - old_bmg) >= 0.1:
                    self.timeline.insert_one({
                        "affair_id": affair_id,
                        "event": "bmg_change",
                        "details": {
                            "old_bmg": old_bmg,
                            "new_bmg": bmg["bmg"],
                            "niveau": bmg["niveau_alerte"],
                        },
                        "timestamp": now,
                    })

        logger.info(
            f"🔄 Lifecycle: {stats['updated']} MAJ, "
            f"{stats['stale']} stale, {stats['archived']} archivées"
        )
        return stats

    # ============================================================
    # CYCLE SIMPLIFIÉ — Créer d'abord, consolider ensuite
    # ============================================================
    def run_simple_cycle(self) -> Dict[str, Any]:
        """
        Cycle simplifié et efficace :
        1. Chaque article enrichi non traité → crée une affaire (ou fusionne si similaire)
        2. Consolide : cherche dans les 24h si d'autres sources parlent du même sujet
        3. Met à jour le lifecycle (stale/archive)
        4. Recalcule BMG

        Protégé par un lock distribué Mongo — si un autre replica/process tient
        déjà le lock, on retourne immédiatement (skip ce tick).
        """
        if self.db is None:
            return {"error": "no_db"}

        # Lock distribué — TTL 30 min (un cycle complet ne devrait jamais excéder).
        # Évite que 2 workers Render exécutent le cycle en parallèle et écrivent
        # des affaires en double que le _merge_duplicate_affairs ne rattrape pas
        # toujours (cf. audit C8).
        try:
            from backend.distributed_lock import distributed_lock
        except ImportError:
            from distributed_lock import distributed_lock  # type: ignore

        with distributed_lock("affair_simple_cycle", ttl_seconds=1800) as acquired:
            if not acquired:
                logger.info("🔒 run_simple_cycle: lock détenu ailleurs, skip")
                return {"method": "simple_cycle", "skipped": "locked"}
            return self._run_simple_cycle_inner()

    def _run_simple_cycle_inner(self) -> Dict[str, Any]:
        """Implémentation réelle de run_simple_cycle (sans lock — appelée
        seulement après acquisition par run_simple_cycle)."""
        logger.info("=" * 50)
        logger.info("🔄 CYCLE SIMPLIFIÉ (créer → consolider)")
        logger.info("=" * 50)

        now = datetime.utcnow()
        # Fenêtre large (14j) pour rattraper le backlog d'articles enrichis
        cutoff_14d_dt = now - timedelta(days=14)
        cutoff_14d_str = cutoff_14d_dt.isoformat()
        stats = {
            "method": "simple_cycle",
            "created": 0,
            "merged": 0,
            "consolidated": 0,
            "radio_linked": 0,
        }

        # ── ÉTAPE 1 : Récupérer les articles enrichis non traités ──
        # IMPORTANT: scraped_at peut être datetime OU string ISO en base
        # SÉCURITÉ: exclure les articles en cooldown ou ayant atteint MAX_MATCH_ATTEMPTS
        cooldown_before = (now - timedelta(minutes=30 * MATCH_COOLDOWN_CYCLES)).isoformat()
        unprocessed = list(self.articles.find({
            "$and": [
                {"_analysis_method": {"$exists": True}},
                {"$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                ]},
                # Exclure les articles qui ont atteint le max de tentatives
                {"$or": [
                    {"_match_attempts": {"$exists": False}},
                    {"_match_attempts": {"$lt": MAX_MATCH_ATTEMPTS}},
                ]},
                # Cooldown : ne pas reprendre un article tenté récemment
                {"$or": [
                    {"_match_last_attempt": {"$exists": False}},
                    {"_match_last_attempt": {"$lte": cooldown_before}},
                ]},
                {"$or": [
                    {"scraped_at": {"$gte": cutoff_14d_dt}},
                    {"scraped_at": {"$gte": cutoff_14d_str}},
                ]},
            ]
        }).sort("gravity_score", -1).limit(200))

        # ── DIAGNOSTIC : état de la base ──
        total_articles = self.articles.estimated_document_count()
        total_enriched = self.articles.count_documents({"_analysis_method": {"$exists": True}})
        total_processed = self.articles.count_documents({"_affair_processed": True})
        total_affairs = self.affairs.estimated_document_count()
        active_count = self.affairs.count_documents({"status": "active"})
        logger.info(f"📊 DB: {total_articles} articles total, {total_enriched} enrichis, "
                     f"{total_processed} déjà traités (affaires), "
                     f"{total_affairs} affaires ({active_count} actives)")
        logger.info(f"📰 {len(unprocessed)} articles non traités trouvés (enrichis, 14j)")

        if len(unprocessed) == 0 and total_enriched > 0:
            # Diagnostic : pourquoi aucun article non traité ?
            recent_enriched = self.articles.count_documents({"$or": [
                {"scraped_at": {"$gte": cutoff_14d_dt}, "_analysis_method": {"$exists": True}},
                {"scraped_at": {"$gte": cutoff_14d_str}, "_analysis_method": {"$exists": True}},
            ]})
            recent_not_processed = self.articles.count_documents({"$and": [
                {"_analysis_method": {"$exists": True}},
                {"$or": [{"_affair_processed": {"$exists": False}}, {"_affair_processed": False}]},
                {"$or": [{"scraped_at": {"$gte": cutoff_14d_dt}}, {"scraped_at": {"$gte": cutoff_14d_str}}]},
            ]})
            logger.warning(f"⚠️ Diagnostic 0 articles: {recent_enriched} enrichis en 3j, "
                          f"{recent_not_processed} non traités parmi eux")
            # Examiner un exemple
            sample = self.articles.find_one({
                "_analysis_method": {"$exists": True},
                "$or": [{"scraped_at": {"$gte": cutoff_14d_dt}}, {"scraped_at": {"$gte": cutoff_14d_str}}],
            })
            if sample:
                logger.warning(f"   Exemple: scraped_at={sample.get('scraped_at')} "
                              f"(type={type(sample.get('scraped_at')).__name__}), "
                              f"_affair_processed={sample.get('_affair_processed', 'ABSENT')}, "
                              f"_analysis_method={sample.get('_analysis_method')}")

        # Charger les affaires actives
        active_affairs = list(self.affairs.find({"status": "active"}))

        # ── ÉTAPE 1b : Classifier les articles par commune ──
        commune_stats = {"regex": 0, "ai": 0, "none": 0}
        for art in unprocessed:
            if art.get("communes"):
                continue  # Déjà classifié
            communes = classify_article_commune(art)
            if communes:
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"communes": communes}}
                )
                art["communes"] = communes
                commune_stats["regex" if detect_communes_regex(
                    f"{art.get('title', '')} {art.get('ai_summary', '')}") else "ai"] += 1
            else:
                commune_stats["none"] += 1
        logger.info(f"📍 Communes: {commune_stats}")

        # ── DIAGNOSTIC FUSION IA ──
        _ai_available = False
        try:
            from backend.ai_groq_service import is_available as _ai_is_available
            _ai_available = _ai_is_available()
        except Exception:
            pass
        logger.info(f"🔧 DIAGNOSTIC FUSION: ai_match_ok={_ai_match_ok}, "
                     f"ai_available={_ai_available}, "
                     f"active_affairs={len(active_affairs)}, "
                     f"articles_a_traiter={len(unprocessed)}")
        if not _ai_available:
            logger.warning("⚠️ IA NON DISPONIBLE — vérifiez OPENAI_API_KEY dans les variables d'environnement !")

        # ── ÉTAPE 2 : Pour chaque article → COMPARAISON IA INDIVIDUELLE ──
        # NOUVEAU FLOW : 1 article = 1 affaire d'abord, puis match IA contre existantes
        ignored_count = 0
        # Compteur de fusions par affaire dans ce cycle (anti boule de neige)
        _affair_merge_counts: dict = {}
        MAX_MERGES_PER_CYCLE = 5  # max fusions auto par affaire et par cycle
        for art in unprocessed:
            art_id = str(art["_id"])
            gravity = art.get("gravity_score", 0)

            # ── Filtre titre vide ──
            # Les transcriptions radio sans titre enrichi arrivent avec title=None ou title='?'.
            # Envoyer '?' à GPT est inutile et coûteux — on marque définitivement processed.
            _art_title = (art.get("title") or "").strip()
            if not _art_title or _art_title in {"?", "-", "unknown", "sans titre", "untitled", "n/a"}:
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_ignored": True,
                              "_ignore_reason": "no_title"}}
                )
                ignored_count += 1
                logger.debug(f"   ⏭️ Ignoré (titre vide/invalide): {art_id}")
                continue

            # ── SÉCURITÉ ANTI-FUSION : cooldown + max tentatives ──
            match_attempts = art.get("_match_attempts", 0)
            if match_attempts >= MAX_MATCH_ATTEMPTS:
                logger.info(f"   🛑 Max tentatives ({MAX_MATCH_ATTEMPTS}) atteintes, abandon définitif: {art.get('title', '?')[:60]}")
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_ignored": True,
                              "_ignore_reason": f"max_attempts_{MAX_MATCH_ATTEMPTS}"}}
                )
                stats["ignored"] = stats.get("ignored", 0) + 1
                continue
            # Incrémenter le compteur + marquer le timestamp (cooldown entre tentatives)
            self.articles.update_one(
                {"_id": art["_id"]},
                {"$inc": {"_match_attempts": 1},
                 "$set": {"_match_last_attempt": now.isoformat()}}
            )
            if match_attempts > 0:
                logger.info(f"   🔄 Tentative {match_attempts + 1}/{MAX_MATCH_ATTEMPTS}: {art.get('title', '?')[:60]}")

            # Ignorer les contenus sous le seuil d'affaire (gravity < 0.30)
            if gravity < 0.30:
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_ignored": True}}
                )
                ignored_count += 1
                logger.debug(f"   ⏭️ Ignoré (gravity={gravity:.2f} < 0.30): {art.get('title', '?')[:60]}")
                continue

            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            )
            art_entities = art_elected | art_institutions
            art_theme = art.get("theme", "general")

            # ── Filtre géographique : focus Guadeloupe ──
            if gravity < 0.70 and not self._is_guadeloupe_related(art):
                logger.debug(f"   🌍 Hors Guadeloupe, ignoré: {art.get('title', '?')[:60]}")
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_ignored": True,
                              "_ignore_reason": "hors_guadeloupe"}}
                )
                stats["ignored"] = stats.get("ignored", 0) + 1
                continue

            # ── NOUVEAU : COMPARAISON IA INDIVIDUELLE ──
            # Chaque article est comparé individuellement par GPT à toutes les affaires
            # Seul GPT décide si l'article matche une affaire existante (pas de score heuristique)
            logger.info(f"   📄 Art: '{art.get('title', '?')[:60]}' | gravity={gravity:.2f} "
                        f"| élus={list(art_elected)[:3]} | thème={art_theme}")

            best_match = None
            ai_match_used = False

            # ── FENÊTRE TEMPORELLE : ne comparer qu'aux affaires récentes ──
            # Réduit le bruit, accélère l'appel IA et évite les fusions
            # temporellement absurdes (article d'avril vs affaire de février).
            art_date = (
                self._parse_dt(art.get("published_at"))
                or self._parse_dt(art.get("date"))
                or self._parse_dt(art.get("scraped_at"))
                or self._parse_dt(art.get("created_at"))
                or now
            )
            candidate_affairs = self._filter_affairs_by_time_window(
                active_affairs, art_date
            )
            if len(candidate_affairs) != len(active_affairs):
                logger.info(
                    f"      🕒 Fenêtre temporelle ±{FUSION_TIME_WINDOW_DAYS}j : "
                    f"{len(candidate_affairs)}/{len(active_affairs)} affaires candidates"
                )

            if _ai_match_ok and _ai_match_article and candidate_affairs:
                try:
                    result = _ai_match_article(art, candidate_affairs)
                    if result is None:
                        # IA indisponible (clé manquante, erreur API, etc.)
                        # → laisser le fallback heuristique prendre le relais
                        ai_match_used = False
                        logger.warning(f"      ⚠️ IA retourne None → fallback heuristique")
                    elif result.get("match") != "no_match":
                        match_id = result["match"]
                        confidence = result.get("confidence", "medium")
                        reason = result.get("reason", "")
                        # Trouver l'affaire correspondante
                        for aff in candidate_affairs:
                            if str(aff.get("_id", "")) == match_id:
                                best_match = aff
                                ai_match_used = True
                                logger.info(
                                    f"      🎯 IA MATCH ({confidence}): → '{aff.get('title', '?')[:50]}' "
                                    f"({reason})"
                                )
                                break
                        if not best_match:
                            logger.warning(f"      ⚠️ IA match ID introuvable: {match_id} → fallback")
                            ai_match_used = False
                    else:
                        # IA dit explicitement "no_match" → on fait confiance
                        ai_match_used = True
                        logger.info(f"      🆕 IA: aucun match → nouvelle affaire")
                except Exception as e:
                    logger.warning(f"      ⚠️ IA match error: {e} → fallback heuristique")
                    ai_match_used = False

            # Fallback : si IA indisponible, matching STRICT par titre uniquement
            # On compare le titre de l'article au titre de chaque affaire active.
            # Seuls les titres très similaires (SequenceMatcher >= 0.65) sont fusionnés.
            # (La fenêtre temporelle s'applique aussi ici.)
            if not ai_match_used and candidate_affairs:
                art_title_norm = self._normalize_title(art.get("title", ""))
                best_ratio = 0.0
                for affair in candidate_affairs:
                    aff_title_norm = self._normalize_title(affair.get("title", ""))
                    if not aff_title_norm or not art_title_norm:
                        continue
                    ratio = SequenceMatcher(None, art_title_norm, aff_title_norm).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = affair
                # Seuil strict : 0.65 = titres très proches (même événement formulé différemment)
                if best_match and best_ratio < 0.65:
                    best_match = None
                if best_match:
                    logger.info(f"      📊 Fallback TITRE: ratio={best_ratio:.2f} → fusion avec '{best_match.get('title', '?')[:50]}'")

            if best_match:
                # ── Cap anti boule de neige ──
                _mid = str(best_match.get("_id", ""))
                _item_count = best_match.get("item_count", 0)
                if _item_count >= SNOWBALL_MAX_ITEMS:
                    logger.warning(
                        f"      🌀 Boule de neige détectée: '{best_match.get('title', '?')[:40]}' "
                        f"a déjà {_item_count} items — fusion automatique suspendue"
                    )
                    best_match = None
                elif _affair_merge_counts.get(_mid, 0) >= MAX_MERGES_PER_CYCLE:
                    logger.warning(
                        f"      🔒 Cap cycle ({MAX_MERGES_PER_CYCLE}) atteint pour "
                        f"'{best_match.get('title', '?')[:40]}' — skip ce cycle"
                    )
                    best_match = None

            if best_match:
                # ── Filtre anti boule de neige ──
                coherent, block_reason = self._titles_are_coherent(
                    art.get("title", ""), best_match.get("title", ""),
                    art.get("ai_summary", ""), best_match.get("description", ""),
                )
                if not coherent:
                    logger.warning(f"      🚫 FUSION BLOQUÉE: {block_reason}")
                    best_match = None

            if best_match:
                # Fusionner avec l'affaire existante
                logger.info(f"      ✅ FUSION avec: '{best_match.get('title', '?')[:50]}'")
                merged_gravity = max(gravity, best_match.get("gravity_score", 0))
                merged_bmg = best_match.get("bmg", 0)
                merged_items = best_match.get("item_count", 1) + 1
                merge_sentiment = art.get("sentiment", "neutre")
                existing_sentiments = best_match.get("sentiment_history", []) or []
                updated_sentiments = existing_sentiments + [merge_sentiment]
                dominant_sentiment = self._dominant_sentiment(updated_sentiments)
                new_priority = self.compute_priority(merged_gravity, merged_bmg, merged_items,
                                                     sentiment=dominant_sentiment)

                # Ajouter les communes de l'article à l'affaire
                art_communes = art.get("communes", [])

                update_ops = {
                    "$addToSet": {
                        "articles": art_id,
                        "sources": art.get("source", ""),
                    },
                    "$push": {"sentiment_history": merge_sentiment},
                    "$inc": {"item_count": 1},
                    "$set": {"last_activity": now, "priority": new_priority,
                             "sentiment": dominant_sentiment},
                    "$max": {"gravity_score": gravity},
                }
                if art_communes:
                    update_ops["$addToSet"]["communes"] = {"$each": art_communes}

                self.affairs.update_one({"_id": best_match["_id"]}, update_ops)
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_id": str(best_match["_id"])}}
                )
                stats["merged"] += 1
                # Incrémenter le compteur de fusions pour cette affaire
                _affair_merge_counts[str(best_match["_id"])] = \
                    _affair_merge_counts.get(str(best_match["_id"]), 0) + 1

                # Notification Telegram fusion auto
                if _telegram_ok and _tg_merged:
                    try:
                        # Construire un "reason" cohérent selon la méthode de match utilisée
                        if ai_match_used:
                            merge_reason = "Match IA sémantique"
                        elif 'best_ratio' in locals() and best_ratio:
                            merge_reason = f"Titre similaire (ratio={best_ratio:.2f})"
                        else:
                            merge_reason = ""
                        _tg_merged(
                            best_match,
                            {"title": art.get("title", ""), "gravity_score": gravity, "item_count": 1},
                            merge_type="auto",
                            reason=merge_reason,
                        )
                    except Exception as _tg_err:
                        logger.debug(f"Telegram notify_affair_merged error: {_tg_err}")
            else:
                # Créer une nouvelle affaire
                # NOUVEAU SEUIL : gravity >= 0.35 (on crée plus facilement car GPT décide des fusions)
                has_key_entity = len(art_elected) >= 1
                if gravity >= 0.35 or (gravity >= 0.30 and has_key_entity):
                    title = art.get("title", "Nouvelle affaire")[:200]
                    art_sentiment = art.get("sentiment", "neutre")
                    # ── Texte de référence : contenu du 1er article fondateur ──
                    # Utilisé par l'IA pour comparer les prochains articles au CONTENU réel
                    # de l'affaire et non seulement à son titre (évite les fusions erronées).
                    ref_summary = (art.get("ai_summary", "") or "").strip()
                    ref_content = (art.get("content", "") or art.get("full_text", "") or "").strip()
                    # reference_text structuré : champs explicites pour meilleur matching IA
                    art_communes_str = ", ".join(art.get("communes", [])[:3]) or "non précisé"
                    reference_text = (
                        f"TITRE: {title}\n"
                        f"CATÉGORIE: {self._classify_affair_type(art)}\n"
                        f"THÈME: {art_theme}\n"
                        f"ÉLUS: {', '.join(list(art_elected)[:5]) or 'aucun'}\n"
                        f"INSTITUTIONS: {', '.join(list(art_institutions)[:5]) or 'aucune'}\n"
                        f"COMMUNES: {art_communes_str}\n"
                        f"RÉSUMÉ: {ref_summary[:400]}\n"
                        f"CONTENU: {ref_content[:500]}"
                    )[:1800]
                    new_affair = {
                        "title": title,
                        "description": (art.get("ai_summary", "") or "")[:300],
                        "reference_text": reference_text,
                        "reference_title": title,
                        "reference_source": art.get("source", ""),
                        "reference_article_id": art_id,
                        "reference_created_at": now,
                        "primary_entity": list(art_elected)[0] if art_elected else None,
                        "entities": list(art_entities)[:20],
                        "elected": list(art_elected)[:10],
                        "institutions": list(art_institutions)[:10],
                        "keywords": art.get("keywords_found", []) or [],
                        "theme": art_theme,
                        "event_structured": art.get("event_structured", {}),
                        "gravity_score": round(gravity, 3),
                        "affair_type": self._classify_affair_type(art),
                        "priority": self.compute_priority(gravity, sentiment=art_sentiment),
                        "sentiment": art_sentiment,
                        "sentiment_history": [art_sentiment],
                        "status": "active",
                        "articles": [art_id],
                        "radio_transcriptions": [],
                        "social_posts": [],
                        "sources": [art.get("source", "")],
                        "source_types": ["article"],
                        "item_count": 1,
                        "created_at": now,
                        "last_activity": now,
                        "promoted_at": now,
                        **self._provisional_bmg(art.get("source", ""), "article"),
                        "founding_elected": list(art_elected)[:10],
                        "founding_institutions": list(art_institutions)[:10],
                        "communes": art.get("communes", []),
                        "ai_managed": True,
                        "_creation_method": "simple_cycle_v2",
                    }
                    # Stocker l'embedding de l'article fondateur sur l'affaire
                    art_embedding = art.get("embedding")
                    if art_embedding:
                        new_affair["embedding"] = art_embedding
                    self.normalize_affair_data(new_affair)
                    result = self.affairs.insert_one(new_affair)
                    new_id = str(result.inserted_id)
                    new_affair["_id"] = result.inserted_id

                    self.articles.update_one(
                        {"_id": art["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_id": new_id}}
                    )
                    self.timeline.insert_one({
                        "affair_id": new_id,
                        "event": "created",
                        "details": {"method": "simple_cycle", "title": title[:80],
                                    "source": art.get("source", ""), "gravity": gravity},
                        "timestamp": now,
                    })
                    active_affairs.append(new_affair)
                    stats["created"] += 1
                    logger.info(f"🆕 Affaire: '{title[:50]}' (gravity={gravity:.2f}, "
                                f"élus={list(art_elected)[:2]}, source={art.get('source', '')})")
                    # Notification Telegram
                    if _telegram_ok and _tg_notify:
                        try:
                            _tg_notify(new_affair, source_type="article")
                        except Exception as tg_err:
                            logger.debug(f"Telegram notify: {tg_err}")
                    # 🔔 Notification push
                    if _push_ok and _push_notify:
                        try:
                            _push_notify(new_affair)
                        except Exception as push_err:
                            logger.debug(f"Push notification: {push_err}")
                    # Auto-génération du contexte IA
                    try:
                        self.generate_affair_context(new_id)
                    except Exception as ctx_err:
                        logger.debug(f"Auto-contexte IA: {ctx_err}")
                else:
                    # Gravity trop basse pour créer une affaire seule, marquer comme traité
                    self.articles.update_one(
                        {"_id": art["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_ignored": True,
                                  "_affair_ignore_reason": f"gravity={gravity:.2f} < seuil création"}}
                    )
                    ignored_count += 1
                    logger.debug(f"   ⏭️ Pas assez grave pour créer une affaire (gravity={gravity:.2f}): "
                                 f"{art.get('title', '?')[:60]}")

        # ── ÉTAPE 3 : Consolidation — chercher d'autres sources 24h ──
        stats["consolidated"] = self._consolidate_affairs_24h(active_affairs)

        # ── ÉTAPE 3b : Fusion inter-affaires (doublons même batch) ──
        stats["inter_merged"] = self._merge_duplicate_affairs(active_affairs)

        # ── ÉTAPE 3c : Nettoyage géographique (affaires hors-Guadeloupe) ──
        stats["geo_cleaned"] = self._cleanup_non_guadeloupe_affairs()

        # ── ÉTAPE 3d : Dédup IA — GPT compare les affaires actives ──
        stats["ai_deduped"] = self._ai_dedup_affairs(active_affairs)

        # Recharger active_affairs après fusions/archivages
        if stats["inter_merged"] > 0 or stats["geo_cleaned"] > 0 or stats["ai_deduped"] > 0:
            active_affairs = list(self.affairs.find({"status": "active"}))

        # ── ÉTAPE 4 : Enrichir les transcriptions radio avec l'IA ──
        stats["radio_enriched"] = self._enrich_radio_transcriptions()

        # ── ÉTAPE 5 : Lier les transcriptions radio ──
        stats["radio_linked"] = self._link_radio_to_affairs(active_affairs)

        # ── ÉTAPE 5b : Lier les posts sociaux ──
        stats["social_linked"] = self._link_social_to_affairs(active_affairs)

        # ── ÉTAPE 5c : Créer des affaires à partir des topics radio non liés ──
        stats["radio_created"] = self._create_affairs_from_radio(active_affairs)

        # ── ÉTAPE 6 : Enforcer la limite ──
        self._enforce_max_affairs()

        # ── ÉTAPE 7 : Recalculer BMG ──
        self._recalculate_active_bmg()

        # ── ÉTAPE 8 : Lifecycle ──
        stats["lifecycle"] = self.update_affair_lifecycle()

        # ── ÉTAPE 9 : Cross-check stale ↔ active (GPT) ──
        # Après le lifecycle qui peut avoir passé des affaires en stale,
        # on vérifie si des stale et des actives parlent du même sujet
        stats["stale_active_merged"] = self._cross_check_stale_active()

        # ── ÉTAPE 10 : Détection boule de neige ──
        stats["snowball_alerts"] = self._detect_snowball_affairs()

        logger.info(
            f"✅ Cycle simplifié: {stats['created']} créées, {stats['merged']} fusionnées, "
            f"{stats['consolidated']} consolidées, {stats.get('inter_merged', 0)} inter-fusionnées, "
            f"{stats.get('ai_deduped', 0)} dédup-IA, {stats.get('geo_cleaned', 0)} hors-GP archivées, "
            f"{stats['radio_enriched']} radio enrichies, "
            f"{stats['radio_linked']} radio liées, {stats.get('radio_created', 0)} radio→affaires, "
            f"{stats.get('stale_active_merged', 0)} stale↔active fusionnées, "
            f"{ignored_count} ignorées (gravity<0.30 ou seuil création)"
        )
        logger.info(f"📊 Bilan: {len(active_affairs)} affaires actives maintenant")
        return stats

    # Institutions trop génériques — présentes dans beaucoup d'articles
    # sans lien direct. Ne comptent PAS comme signal de matching.
    GENERIC_INSTITUTIONS = {
        "préfecture", "prefecture", "préfecture de guadeloupe",
        "parquet", "parquet de pointe-à-pitre", "parquet de pointe-a-pitre",
        "tribunal", "tribunal administratif", "tribunal administratif de la guadeloupe",
        "agence régionale de santé", "agence regionale de sante", "ars",
        "conseil départemental", "conseil departemental", "conseil régional", "conseil regional",
        "rectorat", "académie", "academie",
        "insee", "institut national de la statistique et des études économiques",
        "france travail", "pôle emploi", "pole emploi",
        "caisse générale de sécurité sociale", "cgss",
        "edf", "edf guadeloupe",
        "sdis", "sdis guadeloupe",
        "chambre des métiers", "chambre des metiers",
        "parc national", "parc national de la guadeloupe",
        "ordre des avocats",
        "gendarmerie", "samu", "pompiers", "sapeurs-pompiers",
        "centre régional opérationnel de surveillance et de sauvetage",
    }

    # Élus/personnalités trop génériques — présents dans beaucoup de contextes
    # différents. Comptent MOINS (2 pts au lieu de 5) car leur présence
    # dans un article n'implique pas qu'il s'agit de la même affaire.
    GENERIC_ELECTED = {
        "victorin lurel", "ary chalus", "eric jalton", "éric jalton",
        "guy losbar", "josette borel-lincertin", "max mathiasin",
        "harry durimel", "hélène vainqueur-christophe", "helene vainqueur-christophe",
        "dominique théophile", "dominique theophile", "justine bénin", "justine benin",
        "olivier serva", "christian baptiste", "ferdy louisy",
        "marie-luce penchard", "lucette michaux-chevry",
    }

    # Mots de titre trop génériques — présents dans beaucoup de titres
    # sans valeur discriminante. Ne comptent PAS pour le matching.
    GENERIC_TITLE_WORDS = {
        "guadeloupe", "guadeloupe.", "antilles", "martinique", "caraïbes",
        "france", "français", "française", "nouveau", "nouvelle",
        "pourquoi", "comment", "situation", "premier", "première",
        "département", "région", "municipales", "elections",
        "selon", "encore", "depuis", "toujours", "également",
        "vidéo", "après", "dans", "pour", "avec", "plus", "vers",
        "cette", "tout", "tous", "très", "fait", "être", "avoir",
    }

    # ── CATÉGORIES D'ÉVÉNEMENTS INCOMPATIBLES (anti boule de neige) ──
    # Deux affaires dans des catégories DIFFÉRENTES ne doivent JAMAIS être fusionnées,
    # même si elles partagent des entités ou un thème. Chaque catégorie est un set
    # de mots-clés présents dans le titre ou la description.
    EVENT_CATEGORIES = {
        "meurtre_arme": {
            "meurtre", "tué", "tuée", "tué par balles", "tuée par balles",
            "assassiné", "assassinée", "homicide", "coups de couteau",
            "coups de feu", "fusillade", "balle", "balles",
            "poignardé", "poignardée", "féminicide", "tentative de meurtre",
            "arme", "arme à feu", "arme blanche", "tir", "tirs",
        },
        "deces_retrouve_sans_vie": {
            "retrouvé sans vie", "retrouvée sans vie", "retrouvé mort",
            "retrouvée morte", "corps retrouvé", "corps sans vie",
            "décédé", "décédée", "décès", "mort suspecte",
            "mort naturelle", "malaise", "malaise cardiaque",
            "cadavre", "dépouille",
        },
        "violence_conjugale": {
            "violence conjugale", "violences conjugales", "violences intrafamiliales",
            "femme battue", "conjoint violent", "ex-compagnon",
        },
        "noyade_accident_mer": {
            "noyade", "noyé", "noyée", "noyés", "plongeur décédé", "plongée",
            "disparition en mer", "baignade", "accident maritime", "chavire",
            "corps repêché", "recherches en mer", "sauvetage en mer",
        },
        "accident_route": {
            "accident de la route", "collision", "accident mortel",
            "renversé", "percuté", "véhicule", "chauffard", "excès de vitesse",
            "motocycliste", "piéton fauché", "sortie de route",
        },
        "election_politique": {
            "élection", "election", "élu", "élue", "candidat", "candidate",
            "scrutin", "vote", "campagne électorale", "municipales",
            "législatives", "sénatoriales", "résultats élections",
            "gagné les élections", "victoire électorale", "second tour",
        },
        "catastrophe_naturelle": {
            "cyclone", "ouragan", "tempête tropicale", "séisme", "tremblement",
            "inondation", "glissement de terrain", "éruption", "tsunami",
            "alerte météo", "vigilance rouge", "vigilance orange",
        },
        "greve_mouvement_social": {
            "grève", "greve", "manifestation", "blocage", "barrage",
            "mobilisation", "piquet", "mouvement social", "revendication",
            "syndicat", "débrayage",
        },
        "sante_epidemie": {
            "dengue", "épidémie", "pandémie", "covid", "virus",
            "contamination", "cas positifs", "hospitalisés", "décès covid",
            "chlordécone", "sargasses", "intoxication",
        },
        "justice_proces": {
            "procès", "proces", "tribunal", "condamné", "condamnée",
            "jugement", "audience", "garde à vue", "mis en examen",
            "détention", "incarcéré", "incarcérée", "acquitté",
            "réquisitions", "verdict", "assises",
        },
        "trafic_drogue": {
            "trafic de drogue", "stupéfiants", "cocaïne", "cocaine",
            "cannabis", "saisie de drogue", "trafiquant", "go fast",
            "crack", "réseau de drogue", "deal", "dealer",
        },
        "agriculture_economie": {
            "campagne sucrière", "sucre", "sucrière", "sucriere", "canne",
            "cannier", "récolte", "plantation", "agricole", "agriculture",
            "banane", "bananier", "rhum", "distillerie", "usine",
            "filière", "production", "exportation", "pêche", "pecheur",
        },
        "memoire_esclavage": {
            "esclavage", "esclave", "esclaves", "abolition", "traite",
            "négrière", "negriere", "commémoration", "mémorial", "memorial",
            "22 mai", "27 mai", "10 mai", "marronnage", "marron",
            "colonisation", "déportation", "mémoire", "ancêtres",
        },
        "commemoration_ceremonie": {
            "commémoration", "cérémonie", "hommage", "anniversaire",
            "souvenir", "recueillement", "gerbe", "monument", "mémorial",
            "memorial", "dépôt de gerbe", "minute de silence",
        },
    }

    def _detect_event_category(self, text: str) -> Optional[str]:
        """Détecte la catégorie d'événement à partir du titre/description.
        Utilise normalize() (sans accents) pour rester robuste aux variantes orthographiques.
        Retourne le nom de la catégorie ou None si non classifiable."""
        if not text:
            return None
        t = text.lower()
        text_norm = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
        best_cat = None
        best_score = 0
        for cat_name, keywords in self.EVENT_CATEGORIES.items():
            score = 0
            for kw in keywords:
                kw_norm = "".join(ch for ch in unicodedata.normalize("NFKD", kw.lower()) if not unicodedata.combining(ch))
                if kw_norm in text_norm:
                    score += 1
            if score > best_score:
                best_score = score
                best_cat = cat_name
        return best_cat if best_score >= 1 else None

    def _detect_geo_zone(self, text: str) -> str:
        """Détecte la zone géographique d'un texte.

        Retourne:
          - "guadeloupe" si marqueurs locaux détectés
          - "hors_guadeloupe" si lieux étrangers détectés SANS marqueur local
          - "inconnu" si rien de détecté
        """
        if not text:
            return "inconnu"
        text_lower = text.lower()

        has_local = any(m in text_lower for m in self.GUADELOUPE_MARQUEURS)
        has_foreign = any(lieu in text_lower for lieu in self.HORS_GUADELOUPE_LIEUX)

        if has_local:
            return "guadeloupe"
        if has_foreign:
            return "hors_guadeloupe"
        return "inconnu"

    def _locations_are_coherent(self, title_a: str, title_b: str, desc_a: str = "", desc_b: str = "") -> tuple:
        """Vérifie si deux affaires sont dans la même zone géographique.

        Bloque la fusion si une affaire est clairement en Guadeloupe et l'autre
        clairement hors Guadeloupe (ex: meurtre aux Abymes vs meurtre en RDC).

        Retourne (is_coherent: bool, reason: str).
        """
        text_a = f"{title_a} {desc_a}".strip()
        text_b = f"{title_b} {desc_b}".strip()

        zone_a = self._detect_geo_zone(text_a)
        zone_b = self._detect_geo_zone(text_b)

        # Si une des deux est inconnue → on laisse passer
        if zone_a == "inconnu" or zone_b == "inconnu":
            return (True, "")

        # Si même zone → cohérent
        if zone_a == zone_b:
            return (True, "")

        # Zones différentes → BLOQUER
        return (
            False,
            f"zones géographiques incompatibles: {zone_a} vs {zone_b} "
            f"('{title_a[:50]}' ≠ '{title_b[:50]}')"
        )

    # Champs sémantiques mutuellement exclusifs : si A touche un champ et B un autre → BLOQUER
    EXCLUSIVE_SEMANTIC_FIELDS = {
        "agriculture": {"campagne sucrière", "sucrière", "sucriere", "canne", "récolte",
                        "plantation", "agricole", "agriculture", "banane", "rhum",
                        "distillerie", "usine sucrière", "filière canne"},
        "esclavage_memoire": {"esclavage", "esclave", "abolition", "traite négrière",
                              "négrière", "negriere", "marronnage", "marron",
                              "crime contre l'humanité", "crime de l'esclavage",
                              "déportation", "chaînes", "colonisation"},
        "election": {"élection", "election", "candidat", "scrutin", "vote",
                     "campagne électorale", "second tour", "résultat"},
        "sport": {"match", "championnat", "tournoi", "compétition", "victoire sportive",
                  "équipe", "joueur", "joueuse", "entraîneur", "stade"},
        "meteo_cyclone": {"cyclone", "ouragan", "tempête", "alerte météo",
                          "vigilance rouge", "vigilance orange", "inondation"},
        "meurtre_arme_feu": {"tué par balles", "tuée par balles", "fusillade",
                              "coups de feu", "arme à feu", "arme blanche",
                              "poignardé", "poignardée", "assassiné", "assassinée"},
        "deces_naturel_suspect": {"retrouvé sans vie", "retrouvée sans vie",
                                   "retrouvé mort", "retrouvée morte", "corps sans vie",
                                   "mort suspecte", "malaise", "décédé"},
    }

    # ============================================================
    # Filtre temporel de fusion
    # ============================================================
    @staticmethod
    def _parse_dt(value) -> Optional[datetime]:
        """Parse un champ date/datetime Mongo (datetime, str ISO, ou None)."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Gérer "Z" suffix et formats ISO variés
                v = value.replace("Z", "+00:00") if value.endswith("Z") else value
                dt = datetime.fromisoformat(v)
                # Normaliser en naive UTC pour comparaison homogène
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt
            except (ValueError, TypeError):
                return None
        return None

    def _window_days_for_affair(self, affair: Dict) -> int:
        """Retourne la fenêtre temporelle en jours adaptée à la catégorie de l'affaire.

        Détecte la catégorie via le titre + description et retourne la valeur
        de FUSION_WINDOW_BY_CATEGORY, ou FUSION_TIME_WINDOW_DAYS (défaut) si
        aucune catégorie n'est détectée.
        """
        text = f"{affair.get('title', '')} {affair.get('description', '')}"
        cat = self._detect_event_category(text)
        if cat and cat in FUSION_WINDOW_BY_CATEGORY:
            return FUSION_WINDOW_BY_CATEGORY[cat]
        return FUSION_TIME_WINDOW_DAYS

    def _affair_time_span(self, affair: Dict) -> Optional[Tuple[datetime, datetime]]:
        """Retourne la plage temporelle (début, fin) d'une affaire.

        Utilise (created_at, last_activity) comme bornes — chaque fois qu'un
        nouvel article est fusionné dans une affaire, `last_activity` est mis
        à jour, donc cette plage couvre effectivement [premier article → dernier
        article] de l'affaire.

        Retourne None si aucune date exploitable.
        """
        start = self._parse_dt(affair.get("created_at") or affair.get("promoted_at"))
        end = self._parse_dt(affair.get("last_activity")) or start
        if start is None and end is None:
            return None
        # Si une seule borne est dispo, l'utiliser pour les deux
        if start is None:
            start = end
        if end is None:
            end = start
        # Garantir start <= end
        if start > end:
            start, end = end, start
        return (start, end)

    def _filter_affairs_by_time_window(
        self,
        affairs: List[Dict],
        reference_date: Optional[datetime],
        window_days: Optional[int] = None,
    ) -> List[Dict]:
        """Filtre les affaires candidates pour la fusion selon une fenêtre temporelle.

        Une affaire est GARDÉE si la `reference_date` (typiquement la date d'un
        nouvel article) est à moins de `window_days` jours de la plage temporelle
        complète de l'affaire [created_at → last_activity]. Autrement dit : il
        suffit qu'un article de l'affaire soit dans ±window_days de la nouvelle
        date pour que la fusion soit envisagée.

        Exemple avec window_days=3 :
          - Affaire : articles du 1er au 3 avril (span = [1er avril, 3 avril])
          - Nouvel article du 6 avril → distance = 3j → GARDÉE
          - Nouvel article du 7 avril → distance = 4j → FILTRÉE

        Si `reference_date` est None → retourne toutes les affaires (pas de filtre).
        Si `window_days` est None → utilise FUSION_TIME_WINDOW_DAYS.
        Les affaires sans date sont CONSERVÉES (prudence — fail-safe).
        """
        if reference_date is None:
            return affairs
        # Si window_days est fourni → fenêtre uniforme.
        # Sinon → on calcule une fenêtre par affaire selon sa catégorie
        # (cf. FUSION_WINDOW_BY_CATEGORY : meurtre=3j, grève=7j, procès=14j…).
        uniform_wd = window_days
        if uniform_wd is not None and uniform_wd <= 0:
            return affairs

        filtered = []
        for aff in affairs:
            span = self._affair_time_span(aff)
            if span is None:
                # Pas de date exploitable → on garde (fail-safe)
                filtered.append(aff)
                continue
            wd = uniform_wd if uniform_wd is not None else self._window_days_for_affair(aff)
            if wd <= 0:
                filtered.append(aff)
                continue
            delta = timedelta(days=wd)
            start, end = span
            # Distance entre reference_date et la plage [start, end] :
            # - 0 si reference_date est dans la plage
            # - start - reference_date si avant
            # - reference_date - end si après
            if reference_date < start:
                gap = start - reference_date
            elif reference_date > end:
                gap = reference_date - end
            else:
                gap = timedelta(0)
            if gap <= delta:
                filtered.append(aff)
        return filtered

    def _titles_are_coherent(self, title_a: str, title_b: str, desc_a: str = "", desc_b: str = "") -> tuple:
        """Vérifie si deux affaires sont sémantiquement cohérentes pour une fusion.

        Vérifie 3 critères :
        1. Zones géographiques compatibles (Guadeloupe ≠ RDC)
        2. Catégories d'événements compatibles (meurtre ≠ élection)
        3. Champs sémantiques exclusifs (agriculture ≠ esclavage)

        Retourne (is_coherent: bool, reason: str).

        Fast-path : si les titres sont ≥90 % identiques (SequenceMatcher), on
        passe TOUS les blockers. Des titres quasi-identiques sont la preuve la
        plus forte possible que les deux affaires parlent du même événement,
        quelle que soit la catégorie ou la zone géographique détectée.
        """
        from difflib import SequenceMatcher
        t_a = (title_a or "").strip().lower()
        t_b = (title_b or "").strip().lower()
        if t_a and t_b:
            ratio = SequenceMatcher(None, t_a, t_b).ratio()
            if ratio >= 0.90:
                return (True, "")   # titres quasi-identiques → même événement, skip all blockers

        # ── Check 1 : géographie ──
        geo_ok, geo_reason = self._locations_are_coherent(title_a, title_b, desc_a, desc_b)
        if not geo_ok:
            return (False, geo_reason)

        # ── Check 2 : catégories d'événements ──
        text_a = f"{title_a} {desc_a}".strip()
        text_b = f"{title_b} {desc_b}".strip()

        cat_a = self._detect_event_category(text_a)
        cat_b = self._detect_event_category(text_b)

        # Si les deux ont une catégorie ET elles sont différentes → BLOQUER
        if cat_a is not None and cat_b is not None and cat_a != cat_b:
            return (
                False,
                f"catégories incompatibles: {cat_a} vs {cat_b} "
                f"('{title_a[:40]}' ≠ '{title_b[:40]}')"
            )

        # ── Check 3 : champs sémantiques exclusifs ──
        text_a_lower = text_a.lower()
        text_b_lower = text_b.lower()

        fields_a = set()
        fields_b = set()
        for field_name, keywords in self.EXCLUSIVE_SEMANTIC_FIELDS.items():
            if any(kw in text_a_lower for kw in keywords):
                fields_a.add(field_name)
            if any(kw in text_b_lower for kw in keywords):
                fields_b.add(field_name)

        # Si A et B touchent des champs différents et non vides → BLOQUER
        if fields_a and fields_b and not (fields_a & fields_b):
            return (
                False,
                f"champs sémantiques exclusifs: {fields_a} vs {fields_b} "
                f"('{title_a[:40]}' ≠ '{title_b[:40]}')"
            )

        return (True, "")

    # Communes de Guadeloupe pour extraction depuis les titres
    COMMUNES_GUADELOUPE = {
        "abymes", "les abymes", "anse-bertrand", "baie-mahault",
        "basse-terre", "bouillante", "capesterre-belle-eau", "capesterre",
        "deshaies", "gourbeyre", "goyave", "grand-bourg",
        "lamentin", "le lamentin", "le gosier", "gosier",
        "le moule", "moule", "morne-à-l'eau", "morne-a-l'eau",
        "petit-bourg", "petit-canal", "pointe-à-pitre", "pointe-a-pitre",
        "pointe-noire", "port-louis", "saint-claude",
        "saint-françois", "saint-francois", "sainte-anne", "sainte-rose",
        "terre-de-bas", "terre-de-haut", "trois-rivières", "trois-rivieres",
        "vieux-fort", "vieux-habitants",
        # Marie-Galante
        "marie-galante", "capesterre-de-marie-galante", "grand-bourg marie-galante",
        "saint-louis marie-galante",
        # La Désirade
        "la désirade", "la desirade", "désirade",
        # Les Saintes
        "les saintes",
    }

    def _titles_have_different_communes(self, title_a: str, title_b: str) -> Optional[str]:
        """Extrait les communes mentionnées dans deux titres.
        Si les deux titres mentionnent des communes DIFFÉRENTES, retourne la raison de blocage.
        Retourne None si pas de conflit détecté.
        """
        title_a_lower = title_a.lower()
        title_b_lower = title_b.lower()

        communes_a = set()
        communes_b = set()
        for commune in self.COMMUNES_GUADELOUPE:
            if commune in title_a_lower:
                communes_a.add(commune)
            if commune in title_b_lower:
                communes_b.add(commune)

        # Si les deux titres mentionnent des communes et elles sont différentes → conflit
        if communes_a and communes_b and not (communes_a & communes_b):
            return (
                f"communes différentes dans les titres: {communes_a} vs {communes_b} "
                f"('{title_a[:40]}' ≠ '{title_b[:40]}')"
            )
        return None

    # Lieux hors-Guadeloupe — si l'article mentionne ces lieux SANS mentionner
    # la Guadeloupe, on le considère comme hors périmètre.
    HORS_GUADELOUPE_LIEUX = {
        "martinique", "ducos", "fort-de-france", "lamentin martinique",
        "guyane", "cayenne", "kourou", "saint-laurent-du-maroni",
        "réunion", "saint-denis de la réunion", "saint-pierre réunion",
        "mayotte", "mamoudzou",
        "israël", "israel", "gaza", "liban", "ukraine", "russie",
        "palestine", "syrie", "iran", "irak",
        "haïti", "haiti", "port-au-prince", "jovenel moïse",
        "états-unis", "etats-unis", "washington", "new york",
        "chine", "pékin", "tokyo", "moscou",
        # Afrique
        "rdc", "congo", "république démocratique du congo", "republique democratique du congo",
        "kinshasa", "goma", "nord-kivu", "sud-kivu", "lubumbashi",
        "sénégal", "senegal", "dakar", "côte d'ivoire", "cote d'ivoire", "abidjan",
        "cameroun", "yaoundé", "yaounde", "douala",
        "mali", "bamako", "niger", "niamey", "burkina faso", "ouagadougou",
        "nigeria", "lagos", "abuja", "afrique du sud", "johannesburg",
        "algérie", "algerie", "alger", "maroc", "rabat", "casablanca",
        "tunisie", "tunis", "egypte", "le caire",
        "kenya", "nairobi", "éthiopie", "ethiopie", "addis-abeba",
        # Europe (hors France métro)
        "londres", "berlin", "madrid", "rome", "bruxelles",
        # Amérique latine
        "brésil", "bresil", "rio de janeiro", "sao paulo", "colombie", "bogota",
        "mexique", "mexico", "venezuela", "caracas",
        # Asie / Moyen-Orient
        "inde", "new delhi", "mumbai", "pakistan", "islamabad",
        "arabie saoudite", "riyad", "dubaï", "dubai",
        # Océan Indien / Pacifique
        "madagascar", "antananarivo", "nouvelle-calédonie", "nouvelle-caledonie", "nouméa", "noumea",
        "polynésie", "polynesie", "tahiti", "papeete",
    }

    # Marqueurs Guadeloupe — si un de ces termes est présent, l'article est local
    GUADELOUPE_MARQUEURS = {
        "guadeloupe", "pointe-à-pitre", "pointe-a-pitre", "basse-terre",
        "les abymes", "baie-mahault", "le moule", "sainte-anne",
        "saint-françois", "le gosier", "petit-bourg", "capesterre",
        "sainte-rose", "deshaies", "bouillante", "goyave", "lamentin",
        "trois-rivières", "vieux-habitants", "petit-canal",
        "port-louis", "anse-bertrand", "morne-à-l'eau",
        "marie-galante", "les saintes", "la désirade",
        "pointe-noire", "vieux-fort", "terre-de-haut", "terre-de-bas",
        "saint-louis marie-galante", "grand-bourg", "capesterre-de-marie-galante",
        "route des mamelles", "la traversée", "l'autre-bord", "l'autre bord",
        "étang buisson", "albioma guadeloupe",
        "971", "gwadloup", "antilles françaises",
        "smgeag", "chu guadeloupe", "ars guadeloupe",
        "france-antilles", "rci guadeloupe", "guadeloupe 1ère",
        "karibinfo", "france-antilles guadeloupe",
    }

    def _is_guadeloupe_related(self, article: dict) -> bool:
        """Vérifie si un article concerne la Guadeloupe.
        Retourne True si local, False si clairement hors-périmètre."""
        text_parts = [
            (article.get("title", "") or "").lower(),
            (article.get("ai_summary", "") or "")[:300].lower(),
            " ".join((article.get("entities", []) or [])[:10]).lower(),
            " ".join((article.get("elected", []) or [])[:10]).lower(),
            " ".join((article.get("institutions", []) or [])[:10]).lower(),
            (article.get("source", "") or "").lower(),
        ]
        full = " ".join(text_parts)

        # Si un marqueur Guadeloupe est présent → c'est local
        for m in self.GUADELOUPE_MARQUEURS:
            if m in full:
                return True

        # Si un lieu hors-Guadeloupe est trouvé sans marqueur local → hors périmètre
        for lieu in self.HORS_GUADELOUPE_LIEUX:
            if lieu in full:
                return False

        # Par défaut, on laisse passer (les sources locales scrapent surtout du local)
        return True

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalise un titre pour le matching : retire accents, tirets, ponctuation."""
        t = title.lower().strip()
        t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
        t = t.replace("-", " ").replace("–", " ").replace("—", " ")
        t = re.sub(r"[«»\"'\[\]\(\):;,\.!\?…]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _fuzzy_entity_match(set_a: set, set_b: set, threshold: float = 0.75) -> int:
        """Compte le nombre de paires fuzzy-matchées entre deux ensembles d'entités."""
        if not set_a or not set_b:
            return 0
        matches = 0
        used_b = set()
        for a in set_a:
            for b in set_b:
                if b in used_b:
                    continue
                # Match exact
                if a == b:
                    matches += 1
                    used_b.add(b)
                    break
                # Substring match (gendarmerie ⊂ gendarmerie de saint-anne)
                if a in b or b in a:
                    matches += 1
                    used_b.add(b)
                    break
                # Fuzzy match (naïma moukcho ≈ naïna moutchou)
                ratio = SequenceMatcher(None, a, b).ratio()
                if ratio >= threshold:
                    matches += 1
                    used_b.add(b)
                    break
        return matches

    def _match_score(
        self, art_elected: set, art_institutions: set, art_entities: set,
        art_theme: str, art_title_words: set, affair: dict,
        art_embedding: list = None,
    ) -> int:
        """Calcule un score de similarité entre un article et une affaire.

        RÈGLES DE MATCHING v5 (STRICTES — même événement, pas même type) :
        - Titre normalisé + SequenceMatcher
        - Fuzzy entity matching
        - Embeddings en bonus MODÉRÉ (deux meurtres ≠ même meurtre)
        - SEUIL DE FUSION = 8 (effectif depuis le fix anti boule de neige)
        - Sur thème large sans entité spécifique : seuil porté à 12 dans la
          consolidation 24h pour éviter les rattachements opportunistes.
        """
        # Entités de l'affaire
        aff_elected = set(
            e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
        )
        aff_institutions_raw = set(
            e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
        )
        aff_institutions = aff_institutions_raw - self.GENERIC_INSTITUTIONS
        art_institutions_filtered = art_institutions - self.GENERIC_INSTITUTIONS

        aff_theme = affair.get("theme", "general")

        # ── Mots du titre normalisés (>= 4 chars, pas génériques) ──
        aff_title_norm = self._normalize_title(affair.get("title", ""))
        art_title_norm = self._normalize_title(" ".join(art_title_words) if art_title_words else "")

        aff_title_words = set(
            w for w in aff_title_norm.split()
            if len(w) >= 4 and w not in self.GENERIC_TITLE_WORDS
        )
        art_title_words_strict = set(
            w for w in self._normalize_title(" ".join(art_title_words)).split()
            if len(w) >= 4 and w not in self.GENERIC_TITLE_WORDS
        )

        # Calcul des intersections
        common_elected_exact = art_elected & aff_elected
        common_institutions_exact = art_institutions_filtered & aff_institutions
        same_theme = (art_theme == aff_theme and art_theme not in BROAD_THEMES and art_theme != "")
        common_title = art_title_words_strict & aff_title_words

        # ── Fuzzy entity matching ──
        fuzzy_elected = self._fuzzy_entity_match(art_elected, aff_elected)
        fuzzy_institutions = self._fuzzy_entity_match(
            art_institutions_filtered, aff_institutions
        )

        # ── Scoring ──
        score = 0

        # Élus : exact match = 5 pts (spécifiques), 2 pts (génériques)
        for elu in common_elected_exact:
            if elu in self.GENERIC_ELECTED:
                score += 2
            else:
                score += 5
        # Fuzzy-matched élus (ceux pas déjà comptés en exact)
        fuzzy_extra_elected = max(0, fuzzy_elected - len(common_elected_exact))
        score += fuzzy_extra_elected * 4  # Légèrement moins que exact

        # Institutions spécifiques (exact)
        score += len(common_institutions_exact) * 3
        # Fuzzy institutions
        fuzzy_extra_instit = max(0, fuzzy_institutions - len(common_institutions_exact))
        score += fuzzy_extra_instit * 2

        # Thème = indice très faible (1 pt), seulement si entité commune
        if same_theme and (fuzzy_elected > 0 or fuzzy_institutions > 0):
            score += 1

        # Mots du titre en commun (max 3 pts)
        score += min(len(common_title), 3)

        # ── Bonus titre quasi-identique (word overlap) ──
        # ATTENTION : word overlap seul = insuffisant (deux meurtres ≠ même meurtre)
        # Le bonus ne s'applique que si >70% overlap (quasi-identique)
        if len(aff_title_words) >= 2 and len(art_title_words_strict) >= 2:
            overlap = len(common_title) / min(len(aff_title_words), len(art_title_words_strict))
            if overlap >= 0.70:
                score += 5  # Quasi-doublon détecté (seuil relevé de 0.50 à 0.70)
            elif overlap >= 0.50:
                score += 2  # Titres proches (réduit de 6 à 2)

        # ── Bonus SequenceMatcher sur titre complet normalisé ──
        # STRICT : seuls les titres quasi-identiques (>=0.85) donnent un gros bonus
        # "Meurtre aux Abymes d'une femme" ≠ "Meurtre aux Abymes d'un homme"
        art_raw_title_norm = self._normalize_title(
            " ".join(art_title_words) if art_title_words else ""
        )
        if aff_title_norm and art_raw_title_norm:
            seq_ratio = SequenceMatcher(None, art_raw_title_norm, aff_title_norm).ratio()
            if seq_ratio >= 0.90:
                score += 7  # Titre quasi-identique (seuil relevé)
            elif seq_ratio >= 0.75:
                score += 3  # Titre similaire (réduit)
            # Supprimé: le palier 0.50 donnait trop de faux positifs

        # ── Bonus embedding sémantique ──
        # MODÉRÉ : les embeddings captent la similarité thématique, pas l'identité d'événement.
        # Deux meurtres différents auront un embedding très proche → réduire le bonus.
        if art_embedding:
            aff_embedding = affair.get("embedding")
            if aff_embedding:
                try:
                    from backend.embedding_service import cosine_similarity
                    sim = cosine_similarity(art_embedding, aff_embedding)
                    if sim >= 0.90:
                        score += 5  # Embedding quasi-identique (réduit de 6)
                    elif sim >= 0.80:
                        score += 3  # Embedding proche (réduit de 4)
                    elif sim >= 0.70:
                        score += 1  # Embedding vaguement similaire (réduit de 2)
                except ImportError:
                    pass

        if score >= 3:
            logger.debug(
                f"      🔍 Score={score} vs '{affair.get('title', '?')[:40]}': "
                f"élus_exact={list(common_elected_exact)}, fuzzy_e={fuzzy_elected}, "
                f"instit_exact={list(common_institutions_exact)}, fuzzy_i={fuzzy_institutions}, "
                f"thème={'✓' if same_theme else '✗'}, mots_titre={list(common_title)[:5]}"
            )
        return score

    def _merge_duplicate_affairs(self, active_affairs: list) -> int:
        """Passe inter-affaires: fusionne les affaires actives trop similaires entre elles.
        Résout le cas où 2+ articles du même batch créent chacun une affaire séparée."""
        if len(active_affairs) < 2:
            return 0

        merged_count = 0
        merged_ids = set()  # IDs déjà absorbées

        for i, affair_a in enumerate(active_affairs):
            if str(affair_a["_id"]) in merged_ids:
                continue
            span_a = self._affair_time_span(affair_a)
            wd_a = self._window_days_for_affair(affair_a)
            for j in range(i + 1, len(active_affairs)):
                affair_b = active_affairs[j]
                if str(affair_b["_id"]) in merged_ids:
                    continue

                # ── Fenêtre temporelle : distance entre les deux plages ──
                # Deux affaires sont mergeables si leurs plages [start, end]
                # sont distantes de <= max(window_a, window_b) (fenêtre adaptée
                # à la catégorie d'événement — cf. FUSION_WINDOW_BY_CATEGORY).
                span_b = self._affair_time_span(affair_b)
                if span_a and span_b:
                    s_a, e_a = span_a
                    s_b, e_b = span_b
                    if e_a < s_b:
                        gap = s_b - e_a
                    elif e_b < s_a:
                        gap = s_a - e_b
                    else:
                        gap = timedelta(0)  # chevauchement
                    wd_b = self._window_days_for_affair(affair_b)
                    pair_delta = timedelta(days=max(wd_a, wd_b))
                    if gap > pair_delta:
                        continue

                # Comparer les titres normalisés
                title_a = self._normalize_title(affair_a.get("title", ""))
                title_b = self._normalize_title(affair_b.get("title", ""))
                seq_ratio = SequenceMatcher(None, title_a, title_b).ratio()

                # FUSION INTER-AFFAIRES v4 : titre similaire >=0.70 ET au moins 1
                # entité spécifique commune (élu nommé OU institution spécifique).
                # Sinon, deux faits divers homonymes ("Meurtre aux Abymes" avec
                # 2 victimes différentes, ou 2 réunions municipales d'agendas
                # différents) peuvent fusionner à tort.
                should_merge = False
                reason = ""

                if seq_ratio >= 0.70:
                    elected_a = {
                        e.lower().strip() for e in (affair_a.get("elected", []) or [])
                        if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_ELECTED
                    }
                    elected_b = {
                        e.lower().strip() for e in (affair_b.get("elected", []) or [])
                        if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_ELECTED
                    }
                    inst_a = {
                        e.lower().strip() for e in (affair_a.get("institutions", []) or [])
                        if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_INSTITUTIONS
                    }
                    inst_b = {
                        e.lower().strip() for e in (affair_b.get("institutions", []) or [])
                        if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_INSTITUTIONS
                    }
                    has_specific_overlap = bool(elected_a & elected_b) or bool(inst_a & inst_b)

                    if has_specific_overlap:
                        should_merge = True
                        reason = f"titres_similaires={seq_ratio:.2f}+entité_commune"
                    elif seq_ratio >= 0.92:
                        # Très haute similarité titre (≥0.92) : on accepte sans
                        # entité commune (cas typique : titres quasi-identiques
                        # d'un même événement reformulé par 2 sources).
                        should_merge = True
                        reason = f"titres_quasi_identiques={seq_ratio:.2f}"
                    else:
                        logger.debug(
                            f"🚫 FUSION inter-affaires REFUSÉE (titre {seq_ratio:.2f} mais "
                            f"aucune entité spécifique en commun): "
                            f"'{affair_a.get('title', '?')[:40]}' vs '{affair_b.get('title', '?')[:40]}'"
                        )

                # ── Filtre anti boule de neige ──
                if should_merge:
                    coherent, block_reason = self._titles_are_coherent(
                        affair_a.get("title", ""), affair_b.get("title", ""),
                        affair_a.get("description", ""), affair_b.get("description", ""),
                    )
                    if not coherent:
                        logger.warning(f"🚫 FUSION inter-affaires BLOQUÉE: {block_reason}")
                        should_merge = False

                if should_merge:
                    # Garder l'affaire avec la plus haute gravité / plus d'items
                    keep, absorb = (affair_a, affair_b) if (
                        affair_a.get("gravity_score", 0) >= affair_b.get("gravity_score", 0)
                    ) else (affair_b, affair_a)

                    logger.info(
                        f"🔀 FUSION inter-affaires ({reason}): "
                        f"'{keep.get('title', '?')[:40]}' absorbe "
                        f"'{absorb.get('title', '?')[:40]}'"
                    )

                    # Transférer articles, sources, etc.
                    absorb_articles = absorb.get("articles", [])
                    absorb_sources = absorb.get("sources", [])
                    absorb_radio = absorb.get("radio_transcriptions", [])
                    absorb_social = absorb.get("social_posts", [])

                    self.affairs.update_one(
                        {"_id": keep["_id"]},
                        {
                            "$addToSet": {
                                "articles": {"$each": absorb_articles},
                                "sources": {"$each": absorb_sources},
                                "radio_transcriptions": {"$each": absorb_radio},
                                "social_posts": {"$each": absorb_social},
                            },
                            "$inc": {"item_count": absorb.get("item_count", 1)},
                            "$max": {"gravity_score": absorb.get("gravity_score", 0)},
                            "$set": {"last_activity": datetime.utcnow()},
                        }
                    )

                    # Archiver l'affaire absorbée
                    self.affairs.update_one(
                        {"_id": absorb["_id"]},
                        {"$set": {
                            "status": "merged",
                            "_merged_into": str(keep["_id"]),
                            "_merged_at": datetime.utcnow(),
                            "_merge_reason": reason,
                        }}
                    )
                    merged_ids.add(str(absorb["_id"]))
                    merged_count += 1

                    # Notification Telegram fusion inter-affaires
                    if _telegram_ok and _tg_merged:
                        try:
                            _tg_merged(keep, absorb, merge_type="inter", reason=reason)
                        except Exception:
                            pass

        if merged_count > 0:
            logger.info(f"🔀 {merged_count} affaires fusionnées entre elles")
        return merged_count

    def _cleanup_non_guadeloupe_affairs(self) -> int:
        """Désactive les affaires hors-Guadeloupe qui ont glissé avant le filtre."""
        non_local = []
        active = list(self.affairs.find({"status": "active"}))
        for a in active:
            gravity = a.get("gravity_score", 0)
            if gravity >= 0.70:
                continue  # On garde les graves même si hors périmètre
            # Construire le texte de l'affaire
            text_parts = [
                (a.get("title", "") or "").lower(),
                (a.get("description", "") or "")[:300].lower(),
                " ".join((a.get("elected", []) or [])[:10]).lower(),
                " ".join((a.get("institutions", []) or [])[:10]).lower(),
            ]
            full = " ".join(text_parts)

            has_local = any(m in full for m in self.GUADELOUPE_MARQUEURS)
            has_foreign = any(m in full for m in self.HORS_GUADELOUPE_LIEUX)

            if has_foreign and not has_local:
                non_local.append(a)

        for a in non_local:
            self.affairs.update_one(
                {"_id": a["_id"]},
                {"$set": {"status": "archived", "_archive_reason": "hors_guadeloupe"}}
            )
            logger.info(f"🌍 Archivée (hors Guadeloupe): '{a.get('title', '?')[:50]}'")

        if non_local:
            logger.info(f"🌍 {len(non_local)} affaires hors-Guadeloupe archivées")
        return len(non_local)

    def _ai_dedup_affairs(self, active_affairs: list) -> int:
        """Utilise GPT pour identifier les doublons sémantiques que le matching
        par mots/entités ne peut pas détecter (ex: 'Décès plongeur' ≈ 'Mort touriste').

        Appelle GPT avec la liste compacte des affaires (titres + entités + actions).
        GPT retourne les groupes à fusionner. On applique les fusions.
        """
        if not _ai_dedup_ok or not _ai_dedup:
            return 0

        if len(active_affairs) < 2:
            return 0

        try:
            duplicates = _ai_dedup(active_affairs)
        except Exception as e:
            logger.warning(f"⚠️ Dédup IA échoué: {e}")
            return 0

        if not duplicates:
            return 0

        # Fenêtre temporelle : pour chaque paire de dédup, on exige que les
        # plages temporelles des deux affaires soient à moins de
        # max(window_keep, window_absorb) jours (fenêtre adaptée à la
        # catégorie d'événement — cf. FUSION_WINDOW_BY_CATEGORY).

        merged_count = 0
        for dup_group in duplicates:
            keep_id = dup_group.get("keep_id")
            merge_ids = dup_group.get("merge_ids", [])
            reason = dup_group.get("reason", "doublon IA")

            if not keep_id or not merge_ids:
                continue

            # Trouver l'affaire à garder
            keep_affair = None
            for a in active_affairs:
                if str(a.get("_id")) == keep_id:
                    keep_affair = a
                    break
            if not keep_affair:
                continue

            for mid in merge_ids:
                # Trouver l'affaire à absorber
                absorb_affair = None
                for a in active_affairs:
                    if str(a.get("_id")) == mid:
                        absorb_affair = a
                        break
                if not absorb_affair:
                    continue

                # ── Filtre 0 : fenêtre temporelle ──
                # Distance entre les plages temporelles [created_at → last_activity]
                # des deux affaires. Budget = max des deux fenêtres catégorielles.
                span_keep = self._affair_time_span(keep_affair)
                span_absorb = self._affair_time_span(absorb_affair)
                if span_keep and span_absorb:
                    sk, ek = span_keep
                    sa, ea = span_absorb
                    if ek < sa:
                        gap = sa - ek
                    elif ea < sk:
                        gap = sk - ea
                    else:
                        gap = timedelta(0)
                    wd_keep = self._window_days_for_affair(keep_affair)
                    wd_absorb = self._window_days_for_affair(absorb_affair)
                    pair_delta = timedelta(days=max(wd_keep, wd_absorb))
                    if gap > pair_delta:
                        logger.warning(
                            f"🚫 Dédup IA BLOQUÉ (fenêtre temporelle): "
                            f"'{keep_affair.get('title','?')[:40]}' [{sk.date()}→{ek.date()}] "
                            f"vs '{absorb_affair.get('title','?')[:40]}' [{sa.date()}→{ea.date()}] "
                            f"gap={gap.days}j > ±{max(wd_keep, wd_absorb)}j"
                        )
                        continue

                # ── Filtre 1 : vérification stricte des communes ──
                # Si les deux affaires ont des communes connues et DIFFÉRENTES → bloquer
                communes_a = set(c.lower().strip() for c in (keep_affair.get("communes", []) or []) if c)
                communes_b = set(c.lower().strip() for c in (absorb_affair.get("communes", []) or []) if c)
                if communes_a and communes_b and not (communes_a & communes_b):
                    block_reason = (
                        f"communes différentes: {communes_a} vs {communes_b} "
                        f"('{keep_affair.get('title', '?')[:40]}' ≠ '{absorb_affair.get('title', '?')[:40]}')"
                    )
                    logger.warning(f"🚫 FUSION IA BLOQUÉE: {block_reason}")
                    if _telegram_ok and _tg_merged:
                        try:
                            _tg_merged(
                                keep_affair, absorb_affair, merge_type="ia",
                                reason=f"⛔ BLOQUÉE — {block_reason}",
                            )
                        except Exception:
                            pass
                    continue

                # ── Filtre 2 : vérification des communes extraites du titre ──
                # Fallback si communes[] est vide : chercher dans le titre
                title_communes_conflict = self._titles_have_different_communes(
                    keep_affair.get("title", ""),
                    absorb_affair.get("title", ""),
                )
                if title_communes_conflict:
                    block_reason = title_communes_conflict
                    logger.warning(f"🚫 FUSION IA BLOQUÉE: {block_reason}")
                    if _telegram_ok and _tg_merged:
                        try:
                            _tg_merged(
                                keep_affair, absorb_affair, merge_type="ia",
                                reason=f"⛔ BLOQUÉE — {block_reason}",
                            )
                        except Exception:
                            pass
                    continue

                # ── Filtre 3 : cohérence sémantique des titres ──
                coherent, block_reason = self._titles_are_coherent(
                    keep_affair.get("title", ""),
                    absorb_affair.get("title", ""),
                    keep_affair.get("description", ""),
                    absorb_affair.get("description", ""),
                )
                if not coherent:
                    logger.warning(
                        f"🚫 FUSION IA BLOQUÉE: {block_reason}"
                    )
                    if _telegram_ok and _tg_merged:
                        try:
                            _tg_merged(
                                keep_affair, absorb_affair, merge_type="ia",
                                reason=f"⛔ BLOQUÉE — {block_reason}",
                            )
                        except Exception:
                            pass
                    continue

                # ── Filtre 4 : même catégorie de décès/violence → vérifier entités ──
                # Deux décès/meurtres dans la même catégorie DOIVENT avoir une entité
                # spécifique en commun pour être fusionnés (même victime, même suspect)
                cat_a = self._detect_event_category(
                    f"{keep_affair.get('title', '')} {keep_affair.get('description', '')}")
                cat_b = self._detect_event_category(
                    f"{absorb_affair.get('title', '')} {absorb_affair.get('description', '')}")
                DEATH_CATEGORIES = {"meurtre_arme", "deces_retrouve_sans_vie", "violence_conjugale", "noyade_accident_mer", "accident_route"}
                if (cat_a in DEATH_CATEGORIES and cat_b in DEATH_CATEGORIES):
                    # Deux décès → exiger au moins une entité spécifique commune
                    ent_a = set(e.lower() for e in (keep_affair.get("entities", []) or []) if e)
                    ent_b = set(e.lower() for e in (absorb_affair.get("entities", []) or []) if e)
                    el_a = set(e.lower() for e in (keep_affair.get("elected", []) or []) if e)
                    el_b = set(e.lower() for e in (absorb_affair.get("elected", []) or []) if e)
                    all_common = (ent_a & ent_b) | (el_a & el_b)
                    # Retirer entités génériques
                    all_common -= self.GENERIC_ELECTED
                    all_common -= self.GENERIC_INSTITUTIONS
                    if not all_common:
                        block_reason = (
                            f"deux décès/incidents sans entité commune spécifique: "
                            f"cat={cat_a}/{cat_b}, "
                            f"('{keep_affair.get('title', '?')[:40]}' ≠ '{absorb_affair.get('title', '?')[:40]}')"
                        )
                        logger.warning(f"🚫 FUSION IA BLOQUÉE: {block_reason}")
                        if _telegram_ok and _tg_merged:
                            try:
                                _tg_merged(
                                    keep_affair, absorb_affair, merge_type="ia",
                                    reason=f"⛔ BLOQUÉE — {block_reason}",
                                )
                            except Exception:
                                pass
                        continue

                logger.info(
                    f"🤖 FUSION IA: '{keep_affair.get('title', '?')[:40]}' "
                    f"absorbe '{absorb_affair.get('title', '?')[:40]}' "
                    f"({reason})"
                )

                # Transférer articles, sources, etc.
                self.affairs.update_one(
                    {"_id": keep_affair["_id"]},
                    {
                        "$addToSet": {
                            "articles": {"$each": absorb_affair.get("articles", [])},
                            "sources": {"$each": absorb_affair.get("sources", [])},
                            "radio_transcriptions": {"$each": absorb_affair.get("radio_transcriptions", [])},
                            "social_posts": {"$each": absorb_affair.get("social_posts", [])},
                        },
                        "$inc": {"item_count": absorb_affair.get("item_count", 1)},
                        "$max": {"gravity_score": absorb_affair.get("gravity_score", 0)},
                        "$set": {"last_activity": datetime.utcnow()},
                    }
                )

                # Archiver l'affaire absorbée
                self.affairs.update_one(
                    {"_id": absorb_affair["_id"]},
                    {"$set": {
                        "status": "merged",
                        "_merged_into": keep_id,
                        "_merged_at": datetime.utcnow(),
                        "_merge_reason": f"ai_dedup: {reason}",
                    }}
                )
                merged_count += 1

                # Notification Telegram fusion IA
                if _telegram_ok and _tg_merged:
                    try:
                        _tg_merged(keep_affair, absorb_affair, merge_type="ia", reason=reason)
                    except Exception:
                        pass

        if merged_count > 0:
            logger.info(f"🤖 Dédup IA: {merged_count} affaires fusionnées")
        return merged_count

    def _cross_check_stale_active(self) -> int:
        """Compare les affaires en veille (stale) aux affaires actives via GPT.
        Si GPT détecte que deux affaires traitent du même sujet,
        fusionne la stale dans l'active (transfère articles, réactive le contenu).

        Évite de recréer des doublons quand un sujet ancien revient dans l'actualité.
        """
        if not _ai_stale_active_ok or not _ai_stale_active:
            logger.info("⏭️ Cross-check stale↔active: IA non disponible, skip")
            return 0

        stale_affairs = list(self.affairs.find({"status": "stale"}))
        active_affairs = list(self.affairs.find({"status": "active"}))

        if not stale_affairs or not active_affairs:
            logger.info(f"⏭️ Cross-check stale↔active: {len(stale_affairs)} stale, {len(active_affairs)} active — rien à comparer")
            return 0

        logger.info(f"🔄 Cross-check stale↔active: {len(stale_affairs)} stale vs {len(active_affairs)} active")

        try:
            matches = _ai_stale_active(stale_affairs, active_affairs)
        except Exception as e:
            logger.warning(f"⚠️ Cross-check stale↔active échoué: {e}")
            return 0

        if not matches:
            return 0

        merged_count = 0
        now = datetime.utcnow()

        for match in matches:
            stale_id = match.get("stale_id")
            active_id = match.get("active_id")
            confidence = match.get("confidence", "medium")
            reason = match.get("reason", "match IA stale↔active")

            # Ne fusionner que les matches "high" confidence
            # Pour "medium", on ne fusionne que si le score de matching est aussi bon
            if confidence not in ("high", "medium"):
                continue

            stale_affair = None
            active_affair = None
            for a in stale_affairs:
                if str(a.get("_id")) == stale_id:
                    stale_affair = a
                    break
            for a in active_affairs:
                if str(a.get("_id")) == active_id:
                    active_affair = a
                    break

            if not stale_affair or not active_affair:
                continue

            # Vérifier le score heuristique pour TOUTES les confidences (même high)
            # car l'IA peut confondre "même type d'événement" avec "même événement"
            aff_elected = set(
                e.lower().strip() for e in (stale_affair.get("elected", []) or []) if e and len(e) > 3
            )
            aff_institutions = set(
                e.lower().strip() for e in (stale_affair.get("institutions", []) or []) if e and len(e) > 3
            )
            aff_entities = aff_elected | aff_institutions
            aff_title_words = set(
                w.lower() for w in (stale_affair.get("title", "").split()) if len(w) > 4
            )
            score = self._match_score(
                aff_elected, aff_institutions, aff_entities,
                stale_affair.get("theme", "general"), aff_title_words, active_affair,
            )

            # High confidence: score minimum 4 (filet de sécurité)
            # Medium confidence: score minimum 8 (relevé de 4)
            min_score = 4 if confidence == "high" else 8
            if score < min_score:
                logger.info(
                    f"   ⏭️ {confidence} confidence mais score={score} < {min_score}, skip: "
                    f"'{stale_affair.get('title', '?')[:40]}' ↔ '{active_affair.get('title', '?')[:40]}'"
                )
                continue

            # ── Filtre anti boule de neige ──
            coherent, block_reason = self._titles_are_coherent(
                stale_affair.get("title", ""), active_affair.get("title", ""),
                stale_affair.get("description", ""), active_affair.get("description", ""),
            )
            if not coherent:
                logger.warning(f"🚫 FUSION stale→active BLOQUÉE: {block_reason}")
                continue

            logger.info(
                f"🔗 FUSION stale→active [{confidence}]: "
                f"'{stale_affair.get('title', '?')[:40]}' → '{active_affair.get('title', '?')[:40]}' "
                f"({reason})"
            )

            # Transférer tous les contenus de la stale vers l'active
            self.affairs.update_one(
                {"_id": active_affair["_id"]},
                {
                    "$addToSet": {
                        "articles": {"$each": stale_affair.get("articles", [])},
                        "sources": {"$each": stale_affair.get("sources", [])},
                        "radio_transcriptions": {"$each": stale_affair.get("radio_transcriptions", [])},
                        "social_posts": {"$each": stale_affair.get("social_posts", [])},
                    },
                    "$inc": {"item_count": stale_affair.get("item_count", 0)},
                    "$max": {"gravity_score": stale_affair.get("gravity_score", 0)},
                    "$set": {"last_activity": now},
                }
            )

            # Marquer la stale comme fusionnée
            self.affairs.update_one(
                {"_id": stale_affair["_id"]},
                {"$set": {
                    "status": "merged",
                    "_merged_into": active_id,
                    "_merged_at": now,
                    "_merge_reason": f"stale_active_gpt: {reason}",
                }}
            )

            # Mettre à jour les articles de la stale pour pointer vers la nouvelle affaire
            for art_ref in stale_affair.get("articles", []):
                self.articles.update_one(
                    {"_id": art_ref if not isinstance(art_ref, str) else ObjectId(art_ref)},
                    {"$set": {"_affair_id": active_id}},
                )

            # Timeline
            self.timeline.insert_one({
                "affair_id": active_id,
                "event": "stale_merged",
                "details": {
                    "merged_from": stale_id,
                    "merged_title": stale_affair.get("title", "")[:80],
                    "confidence": confidence,
                    "reason": reason,
                    "items_transferred": stale_affair.get("item_count", 0),
                },
                "timestamp": now,
            })

            merged_count += 1

            # Notification Telegram fusion stale→active
            if _telegram_ok and _tg_merged:
                try:
                    _tg_merged(active_affair, stale_affair, merge_type="stale", reason=reason)
                except Exception:
                    pass

        if merged_count > 0:
            logger.info(f"🤖 Cross-check stale↔active: {merged_count} affaires en veille fusionnées")
        return merged_count

    def _consolidate_affairs_24h(self, active_affairs: list) -> int:
        """Cherche dans les 24h si des articles non traités correspondent
        à des affaires récemment créées. Consolide multi-source."""
        now = datetime.utcnow()
        cutoff_24h_dt = now - timedelta(hours=24)
        cutoff_24h_str = cutoff_24h_dt.isoformat()
        consolidated = 0

        # Articles des 24h, même ceux déjà "ignorés" avec peu de tentatives
        # IMPORTANT: scraped_at peut être datetime OU string ISO
        candidates = list(self.articles.find({
            "$and": [
                {"_analysis_method": {"$exists": True}},
                {"$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                    {"_affair_ignored": True, "_match_attempts": {"$lt": MAX_MATCH_ATTEMPTS}},
                    # Compat docs anciens (avant unification des compteurs)
                    {"_affair_ignored": True, "_affair_attempts": {"$lt": MAX_MATCH_ATTEMPTS}},
                ]},
                {"$or": [
                    {"scraped_at": {"$gte": cutoff_24h_dt}},
                    {"scraped_at": {"$gte": cutoff_24h_str}},
                ]},
            ]
        }).limit(100))

        logger.info(f"🔗 Consolidation 24h: {len(candidates)} candidats, {len(active_affairs)} affaires actives")

        for art in candidates:
            art_id = str(art["_id"])
            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            )
            art_entities = art_elected | art_institutions
            art_theme = art.get("theme", "general")
            art_title_words = set(
                w.lower() for w in (art.get("title", "").split()) if len(w) > 4
            )

            best_match = None
            best_score = 0
            for affair in active_affairs:
                # Ne pas re-matcher un article déjà dans cette affaire
                if art_id in [str(a) for a in affair.get("articles", [])]:
                    continue
                score = self._match_score(
                    art_elected, art_institutions, art_entities,
                    art_theme, art_title_words, affair
                )
                if score > best_score:
                    best_score = score
                    best_match = affair

            if best_match and best_score >= 8:
                # ── Anti boule de neige : gardes-fous locaux AVANT GPT ──
                # Bloque la consolidation si :
                #  - les titres mentionnent des communes différentes
                #  - les catégories d'événements sont incompatibles (meurtre vs élection…)
                #  - les champs sémantiques sont exclusifs (agriculture vs esclavage…)
                # Évite que des articles sans lien réel ne s'agrègent à une affaire en cours.
                _art_title = art.get("title", "") or ""
                _aff_title = best_match.get("title", "") or ""
                _aff_desc = best_match.get("description", "") or best_match.get("gpt_context", "") or ""
                _art_summary = art.get("summary", "") or art.get("gpt_analysis", "") or ""

                _commune_block = self._titles_have_different_communes(_art_title, _aff_title)
                if _commune_block:
                    logger.info(f"   🚫 Consolidation BLOQUÉE ({_commune_block}): "
                                f"'{_art_title[:50]}' ↛ '{_aff_title[:40]}'")
                    self.articles.update_one(
                        {"_id": art["_id"]},
                        {"$inc": {"_match_attempts": 1}}
                    )
                    continue

                _coherent, _block_reason = self._titles_are_coherent(
                    _art_title, _aff_title, _art_summary, _aff_desc,
                )
                if not _coherent:
                    logger.info(f"   🚫 Consolidation BLOQUÉE ({_block_reason}): "
                                f"'{_art_title[:50]}' ↛ '{_aff_title[:40]}'")
                    self.articles.update_one(
                        {"_id": art["_id"]},
                        {"$inc": {"_match_attempts": 1}}
                    )
                    continue

                # ── Anti-générique : si le score n'est pas porté par des entités
                # spécifiques (élu non-générique ou institution spécifique), exiger
                # un score plus élevé pour limiter les rattachements opportunistes
                # sur thèmes larges (santé, sécurité, général).
                _has_specific_entity = (
                    bool(art_elected & set(
                        e.lower().strip() for e in (best_match.get("elected", []) or [])
                        if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_ELECTED
                    ))
                    or bool(
                        (art_institutions - self.GENERIC_INSTITUTIONS) & set(
                            e.lower().strip() for e in (best_match.get("institutions", []) or [])
                            if e and len(e) > 3 and e.lower().strip() not in self.GENERIC_INSTITUTIONS
                        )
                    )
                )
                if not _has_specific_entity and art_theme in ("", "general", "sante_social", "securite_justice"):
                    if best_score < 12:
                        logger.info(f"   🚫 Consolidation BLOQUÉE (thème large sans entité spécifique, "
                                    f"score={best_score}<12): '{_art_title[:50]}' ↛ '{_aff_title[:40]}'")
                        self.articles.update_one(
                            {"_id": art["_id"]},
                            {"$inc": {"_match_attempts": 1}}
                        )
                        continue

                # ── GPT validation gate (même logique que le matching principal) ──
                if best_score < 15 and _ai_relevance_ok and _ai_relevance:
                    try:
                        art_summary = art.get("summary", "") or art.get("gpt_analysis", "") or ""
                        aff_desc = best_match.get("description", "") or best_match.get("gpt_context", "") or ""
                        is_relevant = _ai_relevance(
                            article_title=art.get("title", ""),
                            article_summary=art_summary[:300],
                            affair_title=best_match.get("title", ""),
                            affair_description=aff_desc[:300],
                        )
                        if is_relevant is False:
                            logger.info(f"   🚫 GPT REJET consolidation: '{art.get('title', '?')[:50]}'")
                            self.articles.update_one(
                                {"_id": art["_id"]},
                                {"$inc": {"_match_attempts": 1}}
                            )
                            continue
                    except Exception as e:
                        logger.warning(f"   ⚠️ GPT consolidation relevance error: {e}")
                        if best_score < 8:
                            continue

                logger.info(f"   🔗 Consolidé: '{art.get('title', '?')[:50]}' → "
                           f"affaire '{best_match.get('title', '?')[:40]}' (score={best_score})")
                self.affairs.update_one(
                    {"_id": best_match["_id"]},
                    {
                        "$addToSet": {
                            "articles": art_id,
                            "sources": art.get("source", ""),
                        },
                        "$inc": {"item_count": 1},
                        "$set": {"last_activity": now},
                    }
                )
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_id": str(best_match["_id"]),
                              "_affair_ignored": False}}
                )
                self.timeline.insert_one({
                    "affair_id": str(best_match["_id"]),
                    "event": "consolidated",
                    "details": {"title": art.get("title", "")[:80],
                                "source": art.get("source", ""), "score": best_score},
                    "timestamp": now,
                })
                consolidated += 1

        logger.info(f"🔗 Consolidation 24h: {consolidated}/{len(candidates)} articles rattachés")
        return consolidated

    def generate_affair_context(self, affair_id: str) -> Dict:
        """Génère un contexte IA pour une affaire et le sauvegarde.

        Séquence en 2 étapes GPT :
          1. Vérification des personnes/lieux (anti-hallucination)
          2. Génération du contexte avec évaluation LIBRE du bruit et du sentiment

        GPT est la source PRIMAIRE : ses scores bruit_score et sentiment_ia
        ÉCRASENT les valeurs système (BMG, sentiment calculé).
        Le BMG formulaire devient le fallback quand le contexte IA n'existe pas.
        """
        from bson import ObjectId
        try:
            from backend.ai_groq_service import generate_affair_context as _gen_ctx
        except ImportError:
            try:
                from ai_groq_service import generate_affair_context as _gen_ctx
            except ImportError:
                return {"error": "Service IA non disponible"}

        affair = self.affairs.find_one({"_id": ObjectId(affair_id)})
        if not affair:
            return {"error": "Affaire introuvable"}

        # Récupérer les titres d'articles liés
        article_ids = affair.get("articles", [])
        articles_titles = []
        for art_ref in article_ids[:15]:
            art = self.articles.find_one(
                {"_id": ObjectId(art_ref) if isinstance(art_ref, str) else art_ref},
                {"title": 1}
            )
            if art and art.get("title"):
                articles_titles.append(art["title"])

        # Récupérer les résumés radio
        radio_ids = affair.get("radio_transcriptions", [])
        radio_summaries = []
        for r_ref in radio_ids[:10]:
            radio = self.transcriptions.find_one(
                {"_id": ObjectId(r_ref) if isinstance(r_ref, str) else r_ref},
                {"summary": 1, "ai_topics": 1}
            )
            if radio:
                if radio.get("ai_topics"):
                    for topic in radio["ai_topics"][:2]:
                        radio_summaries.append(topic.get("summary", topic.get("title", "")))
                elif radio.get("summary"):
                    radio_summaries.append(radio["summary"][:200])

        item_count = affair.get("item_count", 0)

        # Générer le contexte via GPT (2 étapes séquencées, évaluation LIBRE)
        ctx = _gen_ctx(
            title=affair.get("title", ""),
            description=affair.get("description", ""),
            elected=affair.get("elected", []),
            institutions=affair.get("institutions", []),
            theme=affair.get("theme", "general"),
            articles_titles=articles_titles,
            radio_summaries=radio_summaries,
            item_count=item_count,
        )

        if not ctx:
            return {"error": "Génération du contexte échouée"}

        # Sauvegarder le contexte dans l'affaire
        ctx["generated_at"] = datetime.utcnow().isoformat()

        # GPT = SOURCE PRIMAIRE — ses scores écrasent le système
        old_bmg = affair.get("bmg", 0)
        old_sentiment = affair.get("sentiment", "neutre")

        update_fields = {"ai_context": ctx}

        # bruit_score GPT (0-100) → bmg de l'affaire (0-1 float, source de vérité)
        # Le frontend affiche bmg * 100, donc on divise par 100 pour rester compatible
        bruit_score = ctx.get("bruit_score", 0)
        bmg_normalized = round(bruit_score / 100, 3)
        update_fields["bmg"] = bmg_normalized
        # Conserver l'ancien BMG calculé comme référence
        update_fields["bmg_formula"] = old_bmg

        # sentiment GPT → sentiment de l'affaire (source de vérité)
        sentiment_ia = ctx.get("sentiment_ia", "")
        if sentiment_ia:
            sentiment_map = {
                "très_négatif": "très négatif",
                "négatif": "négatif",
                "mitigé": "mitigé",
                "neutre": "neutre",
                "positif": "positif",
                "très_positif": "très positif",
            }
            mapped = sentiment_map.get(sentiment_ia, sentiment_ia)
            update_fields["sentiment"] = mapped
            update_fields["sentiment_formula"] = old_sentiment
            # Ajouter dans l'historique
            self.affairs.update_one(
                {"_id": affair["_id"]},
                {"$push": {"sentiment_history": f"ia:{mapped}"}}
            )

        # Recalculer la priorité avec le nouveau BMG (0-1)
        gravity = affair.get("gravity_score", 0.5)
        new_sentiment = update_fields.get("sentiment", old_sentiment)
        update_fields["priority"] = self.compute_priority(
            gravity, bmg_normalized, affair.get("item_count", 1), sentiment=new_sentiment
        )

        self.affairs.update_one(
            {"_id": affair["_id"]},
            {"$set": update_fields}
        )

        # Ajouter un event timeline
        self.timeline.insert_one({
            "affair_id": affair_id,
            "event": "context_generated",
            "details": {
                "bruit_score_ia": bruit_score,
                "bmg_new": bmg_normalized,
                "bmg_old_formula": old_bmg,
                "sentiment_ia": sentiment_ia,
                "sentiment_old": old_sentiment,
                "enjeux_count": len(ctx.get("enjeux", [])),
            },
            "timestamp": datetime.utcnow(),
        })

        logger.info(
            f"🧠 Contexte IA → affaire '{affair.get('title', '?')[:50]}' "
            f"| bmg: {old_bmg:.2f}→{bmg_normalized:.2f} (GPT {bruit_score}/100) "
            f"| sentiment: {old_sentiment}→{new_sentiment}"
        )

        return {
            "affair_id": affair_id,
            "ai_context": ctx,
            "bmg_updated": True,
            "sentiment_updated": bool(sentiment_ia),
            "old_bmg": round(old_bmg * 100),
            "new_bmg": bruit_score,
        }

    def cleanup_affair(self, affair_id: str) -> Dict:
        """Nettoie une affaire en retirant les articles sans lien réel.

        Compare chaque article de l'affaire à son titre/entités de référence.
        Les articles qui ne matchent pas (score < seuil) sont dissociés.
        """
        from bson import ObjectId
        affair = self.affairs.find_one({"_id": ObjectId(affair_id)})
        if not affair:
            return {"error": "Affaire introuvable"}

        aff_elected = set(
            e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
        )
        aff_title = affair.get("title", "")
        aff_theme = affair.get("theme", "general")

        article_ids = affair.get("articles", [])
        kept = []
        removed = []

        for art_ref in article_ids:
            art = self.articles.find_one({"_id": ObjectId(art_ref) if isinstance(art_ref, str) else art_ref})
            if not art:
                continue

            # Extraire les entités de l'article
            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            )
            art_entities = art_elected | art_institutions
            art_title_words = set(
                w.lower() for w in (art.get("title", "").split()) if len(w) > 4
            )

            # Calculer le score de matching
            score = self._match_score(
                art_elected, art_institutions, art_entities,
                art.get("theme", "general"), art_title_words, affair,
            )

            if score >= 15:
                # Score très élevé → garder sans vérification
                kept.append(art_ref)
            elif score >= 4:
                # Score borderline → vérifier avec GPT
                should_keep = True
                if _ai_relevance_ok and _ai_relevance:
                    try:
                        art_summary = art.get("summary", "") or art.get("gpt_analysis", "") or ""
                        aff_desc = affair.get("description", "") or affair.get("gpt_context", "") or ""
                        is_relevant = _ai_relevance(
                            article_title=art.get("title", ""),
                            article_summary=art_summary[:300],
                            affair_title=aff_title,
                            affair_description=aff_desc[:300],
                        )
                        if is_relevant is False:
                            should_keep = False
                    except Exception:
                        pass  # En cas d'erreur GPT, on garde l'article par défaut

                if should_keep:
                    kept.append(art_ref)
                else:
                    removed.append({
                        "id": str(art_ref),
                        "title": art.get("title", "?")[:80],
                        "score": score,
                        "reason": "gpt_rejected",
                    })
                    self.articles.update_one(
                        {"_id": art["_id"]},
                        {"$unset": {"_affair_id": "", "_affair_processed": ""},
                         "$set": {"_affair_ignored": False}}
                    )
            else:
                removed.append({
                    "id": str(art_ref),
                    "title": art.get("title", "?")[:80],
                    "score": score,
                    "reason": "low_score",
                })
                # Libérer l'article pour qu'il puisse être réassigné
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$unset": {"_affair_id": "", "_affair_processed": ""},
                     "$set": {"_affair_ignored": False}}
                )

        if removed:
            self.affairs.update_one(
                {"_id": affair["_id"]},
                {
                    "$set": {
                        "articles": kept,
                        "item_count": len(kept),
                        "last_activity": datetime.utcnow(),
                    }
                }
            )

        logger.info(f"🧹 Cleanup affaire '{aff_title[:50]}': "
                     f"gardé {len(kept)}, retiré {len(removed)}")

        return {
            "affair_id": affair_id,
            "title": aff_title,
            "kept": len(kept),
            "removed": len(removed),
            "removed_articles": removed,
        }

    def cleanup_all_affairs(self) -> Dict:
        """Nettoie TOUTES les affaires actives en retirant les articles mal groupés."""
        active = list(self.affairs.find({"status": "active"}))
        total_removed = 0
        results = []
        for affair in active:
            r = self.cleanup_affair(str(affair["_id"]))
            if r.get("removed", 0) > 0:
                results.append(r)
                total_removed += r["removed"]
        return {
            "affairs_cleaned": len(results),
            "total_articles_removed": total_removed,
            "details": results,
        }

    def _enrich_radio_transcriptions(self) -> int:
        """Enrichit les transcriptions radio récentes avec l'IA (split_radio_transcription).
        Extrait les sujets, entités, thèmes et gravité de chaque transcription."""
        try:
            from backend.ai_groq_service import split_radio_transcription
        except ImportError:
            try:
                from ai_groq_service import split_radio_transcription
            except ImportError:
                logger.warning("⚠️ split_radio_transcription non disponible — pas d'enrichissement radio")
                return 0

        now = datetime.utcnow()
        cutoff_dt = now - timedelta(days=3)
        cutoff_str = cutoff_dt.isoformat()

        # Transcriptions non encore enrichies (pas de ai_topics)
        unenriched = list(self.transcriptions.find({
            "$and": [
                {"$or": [
                    {"captured_at": {"$gte": cutoff_dt}},
                    {"captured_at": {"$gte": cutoff_str}},
                ]},
                {"$or": [
                    {"ai_topics": {"$exists": False}},
                    {"ai_topics": []},
                    {"ai_topics": None},
                ]},
                {"status": "completed"},
            ]
        }).sort("captured_at", -1).limit(10))

        logger.info(f"🎙️ Enrichissement radio: {len(unenriched)} transcriptions à enrichir")

        enriched_count = 0
        for trans in unenriched:
            text = trans.get("text") or trans.get("transcription") or ""
            if len(text) < 50:
                logger.debug(f"   ⏭️ Transcription trop courte ({len(text)} chars): {trans.get('name', '?')}")
                continue

            radio_name = trans.get("radio") or trans.get("stream_name") or trans.get("name") or ""
            try:
                topics = split_radio_transcription(text, radio_name=radio_name)
            except Exception as e:
                logger.warning(f"   ⚠️ Erreur split_radio pour '{radio_name}': {e}")
                continue

            if topics:
                all_entities = []
                all_themes = []
                max_gravity = 0.0
                summary_parts = []
                for topic in topics:
                    all_entities.extend(topic.get("entities", []))
                    all_themes.append(topic.get("theme", "general"))
                    max_gravity = max(max_gravity, topic.get("gravity", 0))
                    # Construire le résumé texte pour l'affichage
                    t_title = topic.get("title", "").strip()
                    t_summary = topic.get("summary", "").strip()
                    if t_title and t_summary:
                        summary_parts.append(f"{t_title} — {t_summary}")
                    elif t_title:
                        summary_parts.append(t_title)

                ai_summary = "\n\n".join(summary_parts) if summary_parts else ""

                self.transcriptions.update_one(
                    {"_id": trans["_id"]},
                    {"$set": {
                        "ai_topics": topics,
                        "ai_topics_count": len(topics),
                        "ai_summary": ai_summary,
                        "entities": list(set(all_entities)),
                        "themes": list(set(all_themes)),
                        "gravity_score": round(max_gravity, 3),
                        "enriched_at": now.isoformat(),
                        "_analysis_method": "ai_split",
                    }}
                )
                enriched_count += 1
                logger.info(f"   🎙️ {radio_name}: {len(topics)} sujets extraits "
                           f"(entités: {all_entities[:5]}, gravity: {max_gravity:.2f})")
            else:
                logger.info(f"   ℹ️ {radio_name}: aucun sujet extrait par l'IA")

        logger.info(f"🎙️ Enrichissement radio: {enriched_count}/{len(unenriched)} transcriptions enrichies")
        return enriched_count

    def _link_radio_to_affairs(self, active_affairs: list) -> int:
        """Lie les transcriptions radio récentes aux affaires par entités."""
        now = datetime.utcnow()
        cutoff_dt = now - timedelta(days=3)
        cutoff_str = cutoff_dt.isoformat()
        linked = 0

        transcriptions = list(self.transcriptions.find({
            "$or": [
                {"captured_at": {"$gte": cutoff_dt}},
                {"captured_at": {"$gte": cutoff_str}},
            ],
            "_affair_processed": {"$ne": True},
        }).limit(30))

        logger.info(f"📻 Liaison radio: {len(transcriptions)} transcriptions non traitées, "
                    f"{len(active_affairs)} affaires actives")

        for trans in transcriptions:
            trans_id = str(trans["_id"])
            trans_entities = set()
            for e in (trans.get("entities", []) or []):
                if e and len(e) > 3:
                    trans_entities.add(e.lower().strip())

            # Aussi chercher dans ai_topics si disponible
            for topic in (trans.get("ai_topics", []) or []):
                for e in (topic.get("entities", []) or []):
                    if e and len(e) > 3:
                        trans_entities.add(e.lower().strip())

            if not trans_entities:
                continue

            # Normaliser les entités STT via entity_aliases (correct les noms mal transcrits)
            if _entity_aliases_ok and _correct_entities and trans_entities:
                try:
                    _corrected = _correct_entities(list(trans_entities))
                    trans_entities = set(
                        e.lower().strip() for e in _corrected if e and len(e) > 3
                    )
                except Exception:
                    pass  # Normalisation optionnelle — on continue avec les entités brutes

            for affair in active_affairs:
                aff_elected = set(
                    e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
                )
                aff_institutions = set(
                    e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
                ) - self.GENERIC_INSTITUTIONS
                aff_entities = aff_elected | aff_institutions

                common = trans_entities & aff_entities
                # Exiger 2+ entités communes (une transcription mentionne des dizaines de sujets)
                # OU 1 élu spécifique (pas un politicien omniprésent)
                specific_common = common - self.GENERIC_ELECTED
                match = (
                    len(common) >= 2
                    or len(specific_common) >= 1
                )
                if match:
                    # ── GPT validation pour radio aussi ──
                    # Une radio qui mentionne Chalus dans les résultats d'élections
                    # ne devrait pas être liée à son affaire judiciaire
                    if _ai_relevance_ok and _ai_relevance and len(common) < 3:
                        try:
                            # Construire un résumé de la transcription
                            trans_summary = ""
                            for t in (trans.get("ai_topics", []) or []):
                                if any(c in (t.get("title", "").lower() + " " + " ".join(t.get("entities", [])).lower())
                                       for c in common):
                                    trans_summary = t.get("title", "") + " - " + t.get("summary", "")
                                    break
                            if not trans_summary:
                                trans_summary = trans.get("summary", "") or trans.get("text", "")[:200] or ""

                            radio_relevant = _ai_relevance(
                                article_title=trans_summary[:200] or f"Radio {trans.get('station', '?')}",
                                article_summary=trans_summary[:300],
                                affair_title=affair.get("title", ""),
                                affair_description=(affair.get("description", "") or "")[:300],
                            )
                            if radio_relevant is False:
                                logger.info(
                                    f"   🚫 GPT REJET radio: '{trans.get('station', '?')}' "
                                    f"pas lié à '{affair.get('title', '?')[:40]}'"
                                )
                                continue  # Skip this affair, try next one
                        except Exception as e:
                            logger.warning(f"   ⚠️ GPT radio relevance error: {e}")

                    logger.info(f"   📻 Radio '{trans.get('station', '?')}' → "
                               f"affaire '{affair.get('title', '?')[:40]}' "
                               f"(entités communes: {list(common)[:3]})")
                    self.affairs.update_one(
                        {"_id": affair["_id"]},
                        {
                            "$addToSet": {"radio_transcriptions": trans_id,
                                          "source_types": "transcription"},
                            "$inc": {"item_count": 1},
                            "$set": {"last_activity": now},
                        }
                    )
                    self.transcriptions.update_one(
                        {"_id": trans["_id"]},
                        {"$set": {"_affair_processed": True}}
                    )
                    linked += 1
                    break  # 1 affaire par transcription suffit

        logger.info(f"📻 {linked}/{len(transcriptions)} transcriptions radio liées à des affaires")
        return linked

    def _create_affairs_from_radio(self, active_affairs: list) -> int:
        """Crée des affaires à partir des topics radio enrichis non encore liés.

        Chaque topic de transcription radio qui a une gravity suffisante et des entités
        peut devenir une affaire s'il ne matche pas une affaire existante.
        """
        now = datetime.utcnow()
        cutoff_dt = now - timedelta(days=7)
        cutoff_str = cutoff_dt.isoformat()
        created = 0

        # Transcriptions enrichies mais pas encore traitées pour création d'affaires
        enriched_radio = list(self.transcriptions.find({
            "$and": [
                {"$or": [
                    {"captured_at": {"$gte": cutoff_dt}},
                    {"captured_at": {"$gte": cutoff_str}},
                ]},
                {"ai_topics": {"$exists": True}},
                {"ai_topics": {"$ne": []}},
                {"ai_topics": {"$ne": None}},
                {"_affair_topics_processed": {"$ne": True}},
            ]
        }).sort("captured_at", -1).limit(30))

        logger.info(f"📻 Création affaires radio: {len(enriched_radio)} transcriptions à analyser")

        for trans in enriched_radio:
            trans_id = str(trans["_id"])
            topics = trans.get("ai_topics", []) or []

            for topic in topics:
                gravity = topic.get("gravity", 0)
                if gravity < 0.35:
                    continue

                topic_entities = set()
                topic_elected = set()
                topic_institutions = set()
                for e in (topic.get("entities", []) or []):
                    if e and len(e) > 3:
                        clean = e.strip()
                        topic_entities.add(clean.lower())
                        # Heuristique : les institutions contiennent souvent des mots-clés
                        if any(kw in clean.lower() for kw in [
                            "conseil", "mairie", "commune", "région", "département",
                            "ars", "chu", "smgeag", "préfecture", "cgt", "medef",
                            "rectorat", "tribunal", "chambre", "port", "aéroport"
                        ]):
                            topic_institutions.add(clean)
                        else:
                            topic_elected.add(clean)

                if not topic_entities:
                    continue

                # Vérifier si ce topic matche une affaire existante
                matched = False
                for affair in active_affairs:
                    aff_entities = set(
                        e.lower().strip() for e in
                        (affair.get("elected", []) or []) + (affair.get("institutions", []) or [])
                        if e and len(e) > 3
                    ) - self.GENERIC_INSTITUTIONS
                    common = topic_entities & aff_entities
                    if len(common) >= 1:
                        # Lier le topic à l'affaire existante plutôt que créer
                        topic_info = {
                            "transcription_id": trans_id,
                            "radio": trans.get("radio", trans.get("station", "radio")),
                            "captured_at": trans.get("captured_at", ""),
                            "topic_title": topic.get("title", "")[:200],
                            "topic_summary": topic.get("summary", "")[:300],
                            "gravity": round(gravity, 3),
                            "entities": list(topic_entities)[:10],
                            "theme": topic.get("theme", "general"),
                        }
                        self.affairs.update_one(
                            {"_id": affair["_id"]},
                            {
                                "$addToSet": {"radio_transcriptions": trans_id,
                                              "source_types": "transcription",
                                              "radio_topics": topic_info},
                                "$inc": {"item_count": 1},
                                "$set": {"last_activity": now},
                                "$max": {"gravity_score": gravity},
                            }
                        )
                        matched = True
                        break

                if matched:
                    continue

                # Pas de match → créer une nouvelle affaire à partir de ce topic radio
                title = topic.get("title", "Sujet radio")[:200]
                description = topic.get("summary", "")[:300]
                theme = topic.get("theme", "general")

                radio_source = trans.get("radio", trans.get("station", "radio"))
                topic_info = {
                    "transcription_id": trans_id,
                    "radio": radio_source,
                    "captured_at": trans.get("captured_at", ""),
                    "topic_title": title,
                    "topic_summary": description,
                    "gravity": round(gravity, 3),
                    "entities": list(topic_entities)[:10],
                    "theme": theme,
                }
                # Texte de référence construit depuis le topic radio fondateur
                radio_ref_text = f"{title}. {description}"[:1800]
                new_affair = {
                    "title": title,
                    "description": description,
                    "reference_text": radio_ref_text,
                    "reference_title": title,
                    "reference_source": radio_source,
                    "reference_article_id": trans_id,
                    "reference_created_at": now,
                    "primary_entity": list(topic_elected)[0] if topic_elected else None,
                    "entities": list(topic_entities)[:20],
                    "elected": list(topic_elected)[:10],
                    "institutions": list(topic_institutions)[:10],
                    "keywords": topic.get("keywords", []) or [],
                    "theme": theme,
                    "event_structured": topic.get("event", {}),
                    "gravity_score": round(gravity, 3),
                    "affair_type": self._classify_affair_type_by_gravity(gravity),
                    "priority": self.compute_priority(gravity, sentiment=topic.get("sentiment", "neutre")),
                    "sentiment": topic.get("sentiment", "neutre"),
                    "sentiment_history": [topic.get("sentiment", "neutre")],
                    "status": "active",
                    "articles": [],
                    "radio_transcriptions": [trans_id],
                    "social_posts": [],
                    "sources": [radio_source],
                    "source_types": ["transcription"],
                    "item_count": 1,
                    "created_at": now,
                    "last_activity": now,
                    "promoted_at": now,
                    "bmg": 0, "bmg_details": {}, "bmg_history": [],
                    "ai_managed": False,
                    "_creation_method": "radio_topic",
                    "radio_topics": [topic_info],
                }
                self.normalize_affair_data(new_affair)
                result = self.affairs.insert_one(new_affair)
                new_affair["_id"] = result.inserted_id
                active_affairs.append(new_affair)
                created += 1

                self.timeline.insert_one({
                    "affair_id": str(result.inserted_id),
                    "event": "created",
                    "details": {"method": "radio_topic", "title": title[:80],
                                "source": trans.get("radio", ""), "gravity": gravity},
                    "timestamp": now,
                })
                logger.info(f"🆕📻 Affaire radio: '{title[:50]}' (gravity={gravity:.2f}, "
                           f"entités={list(topic_entities)[:3]})")
                # Notification Telegram
                if _telegram_ok and _tg_notify:
                    try:
                        _tg_notify(new_affair, source_type="transcription")
                    except Exception as tg_err:
                        logger.debug(f"Telegram notify radio: {tg_err}")
                # Auto-génération du contexte IA
                try:
                    self.generate_affair_context(str(result.inserted_id))
                except Exception as ctx_err:
                    logger.debug(f"Auto-contexte IA radio: {ctx_err}")

            # Marquer la transcription comme traitée pour création d'affaires
            self.transcriptions.update_one(
                {"_id": trans["_id"]},
                {"$set": {"_affair_topics_processed": True}}
            )

        logger.info(f"📻 {created} affaires créées depuis les topics radio")
        return created

    def _link_social_to_affairs(self, active_affairs: list) -> int:
        """Lie les posts sociaux enrichis par IA aux affaires.

        Utilise les champs IA (elected, institutions, theme, gravity_score)
        extraits par enrich_social_posts_batch — même logique que _match_score.
        Ignore les posts non pertinents (ai_relevant=false).
        """
        now = datetime.utcnow()
        cutoff_dt = now - timedelta(days=3)
        linked = 0

        # Seulement les posts enrichis par IA et pertinents
        posts = list(self.social.find({
            "scraped_at": {"$gte": cutoff_dt},
            "_affair_processed": {"$ne": True},
            "ai_enriched": True,
            "ai_relevant": True,
        }).limit(100))

        # Aussi traiter les posts NON enrichis pour les marquer comme traités
        non_enriched = list(self.social.find({
            "scraped_at": {"$gte": cutoff_dt},
            "_affair_processed": {"$ne": True},
            "$or": [
                {"ai_enriched": {"$ne": True}},
                {"ai_relevant": {"$ne": True}},
            ],
        }).limit(200))

        # Marquer les non-pertinents/non-enrichis comme traités
        for post in non_enriched:
            self.social.update_one({"_id": post["_id"]}, {"$set": {"_affair_processed": True}})

        logger.info(f"📱 Liaison social: {len(posts)} posts IA pertinents, "
                    f"{len(non_enriched)} ignorés (non enrichis/non pertinents), "
                    f"{len(active_affairs)} affaires actives")

        for post in posts:
            post_id = str(post["_id"])

            # Utiliser les entités enrichies par IA
            post_elected = set(
                e.lower().strip() for e in (post.get("elected", []) or []) if e and len(e) > 3
            )
            post_institutions = set(
                e.lower().strip() for e in (post.get("institutions", []) or []) if e and len(e) > 3
            ) - self.GENERIC_INSTITUTIONS
            post_theme = post.get("theme", "general")
            post_keywords = set(
                w.lower() for w in (post.get("keywords_found", []) or []) if len(w) > 4
            )

            best_affair = None
            best_score = 0

            for affair in active_affairs:
                aff_elected = set(
                    e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
                )
                aff_institutions = set(
                    e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
                ) - self.GENERIC_INSTITUTIONS

                aff_theme = affair.get("theme", "general")
                aff_keywords = set(
                    w.lower() for w in (affair.get("keywords", []) or []) if len(w) > 4
                )

                score = 0

                # Élus communs (IA vs affaire)
                common_elected = post_elected & aff_elected
                for elu in common_elected:
                    if elu in self.GENERIC_ELECTED:
                        score += 2
                    else:
                        score += 5

                # Institutions communes
                common_institutions = post_institutions & aff_institutions
                score += len(common_institutions) * 3

                # Thème = bonus faible, seulement si entité commune (et thème spécifique)
                same_theme = (post_theme == aff_theme and post_theme not in BROAD_THEMES and post_theme != "")
                if same_theme and (common_elected or common_institutions):
                    score += 1

                # Keywords communs (max 2 pts)
                common_kw = post_keywords & aff_keywords
                score += min(len(common_kw), 2)

                if score > best_score:
                    best_score = score
                    best_affair = affair

            # Seuil 5 : un élu spécifique OU une institution + keywords
            if best_affair and best_score >= 5:
                # ── GPT validation pour posts sociaux ──
                if best_score < 12 and _ai_relevance_ok and _ai_relevance:
                    try:
                        post_text = post.get("ai_summary", "") or post.get("text", "") or ""
                        aff_desc = best_affair.get("description", "") or best_affair.get("gpt_context", "") or ""
                        is_relevant = _ai_relevance(
                            article_title=post_text[:200],
                            article_summary=post_text[:300],
                            affair_title=best_affair.get("title", ""),
                            affair_description=aff_desc[:300],
                        )
                        if is_relevant is False:
                            logger.info(f"   🚫 GPT REJET social: '{post_text[:50]}'")
                            self.social.update_one({"_id": post["_id"]}, {"$set": {"_affair_processed": True}})
                            continue
                    except Exception as e:
                        logger.warning(f"   ⚠️ GPT social relevance error: {e}")

                logger.info(f"   📱 Post '{post.get('ai_summary', post.get('text', '?'))[:50]}' → "
                           f"affaire '{best_affair.get('title', '?')[:40]}' (score={best_score})")
                self.affairs.update_one(
                    {"_id": best_affair["_id"]},
                    {
                        "$addToSet": {"social_posts": post_id, "source_types": "social"},
                        "$inc": {"item_count": 1},
                        "$set": {"last_activity": now},
                    }
                )
                linked += 1

            self.social.update_one({"_id": post["_id"]}, {"$set": {"_affair_processed": True}})

        logger.info(f"📱 {linked}/{len(posts)} posts sociaux liés à des affaires")
        return linked

    # ============================================================
    # SYSTÈME IA — Gestion directe des affaires par l'IA (legacy)
    # ============================================================
    def run_ai_managed_cycle(self) -> Dict[str, Any]:
        """
        Cycle piloté par l'IA :
        1. Récupère les affaires actives (max 20)
        2. Récupère les articles non encore assignés à une affaire
        3. Envoie tout à l'IA qui décide des assignations/créations
        4. Applique les décisions de l'IA
        5. Expire les affaires > 7 jours sans activité
        6. Fournit le contexte de la semaine passée pour continuité
        """
        if self.db is None:
            return {"error": "no_db"}

        logger.info("=" * 50)
        logger.info("🤖 CYCLE IA AFFAIRES (gestion directe)")
        logger.info("=" * 50)

        stats = {
            "method": "ai_managed",
            "articles_processed": 0,
            "assigned_to_existing": 0,
            "new_affairs_created": 0,
            "gravity_updates": 0,
            "expired": 0,
            "ignored": 0,
        }

        # 1. Récupérer les affaires actives
        active_affairs = list(
            self.affairs.find({"status": "active"})
            .sort("gravity_score", -1)
            .limit(MAX_ACTIVE_AFFAIRS)
        )
        # Sérialiser les _id pour l'IA
        affairs_for_ai = []
        affair_map = {}  # id_str → ObjectId
        for aff in active_affairs:
            id_str = str(aff["_id"])
            affair_map[id_str] = aff["_id"]
            affairs_for_ai.append({
                "_id": id_str,
                "title": aff.get("title", ""),
                "gravity_score": aff.get("gravity_score", 0),
                "item_count": aff.get("item_count", 0),
                "last_activity": aff.get("last_activity", ""),
            })

        # 2. Récupérer les articles enrichis non encore traités
        # IMPORTANT : utiliser datetime aware (UTC) car radio_service stocke
        # captured_at avec timezone (+00:00). Comparaison string MongoDB exige
        # le même format pour que $gte fonctionne correctement.
        try:
            from zoneinfo import ZoneInfo
            cutoff = datetime.now(ZoneInfo("UTC")) - timedelta(days=3)
        except Exception:
            cutoff = datetime.utcnow() - timedelta(days=3)
        existing_article_ids = set()
        for aff in active_affairs:
            for aid in aff.get("articles", []):
                existing_article_ids.add(str(aid))

        cutoff_str = cutoff.isoformat()
        new_articles_raw = list(
            self.articles.find({
                "_analysis_method": {"$exists": True},
                "$or": [
                    {"scraped_at": {"$gte": cutoff}},
                    {"scraped_at": {"$gte": cutoff_str}},
                ],
                "_affair_processed": {"$ne": True},
            })
            .sort("scraped_at", -1)
            .limit(60)
        )

        # Filtrer ceux déjà dans une affaire
        new_articles = []
        for art in new_articles_raw:
            if str(art["_id"]) not in existing_article_ids:
                new_articles.append(art)

        # 2b. Récupérer et découper les transcriptions radio récentes
        #     Chaque transcription = plusieurs sujets → chaque sujet est traité
        #     comme un "article virtuel" pour l'assignation IA
        radio_topics = []
        try:
            from backend.ai_groq_service import split_radio_transcription
        except ImportError:
            try:
                from ai_groq_service import split_radio_transcription
            except ImportError:
                split_radio_transcription = None

        if split_radio_transcription:
            existing_radio_ids = set()
            for aff in active_affairs:
                for rid in aff.get("radio_transcriptions", []):
                    existing_radio_ids.add(str(rid))

            new_transcriptions = list(
                self.transcriptions.find({
                    "$or": [
                        {"captured_at": {"$gte": cutoff}},
                        {"captured_at": {"$gte": cutoff_str}},
                    ],
                    "_affair_processed": {"$ne": True},
                })
                .sort("captured_at", -1)
                .limit(20)
            )
            logger.info(
                f"📻 {len(new_transcriptions)} transcriptions radio non traitées trouvées"
            )

            for trans in new_transcriptions:
                trans_id = str(trans["_id"])
                if trans_id in existing_radio_ids:
                    continue

                text = trans.get("text") or trans.get("transcription") or ""
                if len(text) < 50:
                    continue

                radio_name = trans.get("radio") or trans.get("stream_name") or trans.get("name") or ""
                topics = split_radio_transcription(text, radio_name=radio_name)

                if topics:
                    # Persister l'analyse sur le document transcription
                    all_entities = []
                    all_themes = []
                    max_gravity = 0.0
                    for topic in topics:
                        all_entities.extend(topic.get("entities", []))
                        all_themes.append(topic.get("theme", "general"))
                        max_gravity = max(max_gravity, topic.get("gravity", 0))

                        # Créer un "article virtuel" pour chaque sujet radio
                        radio_topics.append({
                            "_id": trans["_id"],  # ID de la transcription source
                            "_is_radio_topic": True,
                            "_transcription_id": trans_id,
                            "title": topic.get("title", "Sujet radio"),
                            "ai_summary": topic.get("summary", ""),
                            "source": radio_name,
                            "source_type": "transcription",
                            "gravity_score": topic.get("gravity", 0.3),
                            "entities": topic.get("entities", []),
                            "elected": [e for e in topic.get("entities", [])
                                        if not self._is_institution(e)],
                            "institutions": [e for e in topic.get("entities", [])
                                             if self._is_institution(e)],
                            "theme": topic.get("theme", "general"),
                            "date": trans.get("captured_at", ""),
                            "text_excerpt": topic.get("text_excerpt", ""),
                        })

                    # Sauvegarder l'enrichissement sur la transcription
                    self.transcriptions.update_one(
                        {"_id": trans["_id"]},
                        {"$set": {
                            "ai_topics": topics,
                            "ai_topics_count": len(topics),
                            "entities": list(set(all_entities)),
                            "themes": list(set(all_themes)),
                            "gravity_score": round(max_gravity, 3),
                            "enriched_at": datetime.utcnow().isoformat(),
                            "_analysis_method": "ai_split",
                        }}
                    )

                    logger.info(
                        f"📻 {radio_name}: {len(topics)} sujets extraits et sauvegardés"
                    )

            stats["radio_transcriptions_processed"] = len(new_transcriptions)
            stats["radio_topics_extracted"] = len(radio_topics)

        # Combiner articles + sujets radio pour envoi à l'IA
        all_items_for_ai = new_articles + radio_topics

        if not all_items_for_ai:
            logger.info("ℹ️ Pas de nouveaux contenus à traiter")
            lifecycle_stats = self.update_affair_lifecycle()
            stats["lifecycle"] = lifecycle_stats
            return stats

        stats["articles_processed"] = len(new_articles)
        stats["total_items_for_ai"] = len(all_items_for_ai)

        # 3. Contexte semaine passée (affaires archivées/expirées récemment)
        week_ago = datetime.utcnow() - timedelta(days=7)
        last_week_affairs = list(
            self.affairs.find({
                "status": {"$in": ["archived", "stale"]},
                "created_at": {"$gte": week_ago},
            })
            .sort("gravity_score", -1)
            .limit(10)
        )
        last_week_for_ai = []
        for aff in last_week_affairs:
            last_week_for_ai.append({
                "title": aff.get("title", ""),
                "gravity_score": aff.get("gravity_score", 0),
            })

        # 4. Appel IA
        try:
            from backend.ai_groq_service import manage_affairs_with_ai
        except ImportError:
            try:
                from ai_groq_service import manage_affairs_with_ai
            except ImportError:
                logger.warning("⚠️ manage_affairs_with_ai non disponible, fallback clustering")
                return self.run_full_cycle()

        ai_result = manage_affairs_with_ai(
            active_affairs=affairs_for_ai,
            new_articles=all_items_for_ai,  # Articles + sujets radio combinés
            last_week_affairs=last_week_for_ai if last_week_for_ai else None,
        )

        if ai_result is None:
            logger.warning("⚠️ IA indisponible, fallback sur cycle classique")
            return self.run_full_cycle()

        # 5. Appliquer les décisions de l'IA
        now = datetime.utcnow()

        # 5a. Assignations (article/radio → affaire existante ou nouvelle)
        for assignment in ai_result.get("assignments", []):
            art_idx = assignment.get("article_index", 0) - 1  # 1-based → 0-based
            if art_idx < 0 or art_idx >= len(all_items_for_ai):
                continue

            item = all_items_for_ai[art_idx]
            item_id = str(item["_id"])
            is_radio = item.get("_is_radio_topic", False)
            affair_id = assignment.get("affair_id")

            if affair_id and affair_id in affair_map:
                # Assigner à une affaire existante
                if is_radio:
                    # C'est un sujet radio → ajouter la transcription
                    trans_id = item.get("_transcription_id", item_id)
                    self.affairs.update_one(
                        {"_id": affair_map[affair_id]},
                        {
                            "$addToSet": {
                                "radio_transcriptions": trans_id,
                                "sources": item.get("source", ""),
                                "source_types": "transcription",
                                "entities": {"$each": item.get("entities", []) or []},
                            },
                            "$inc": {"item_count": 1},
                            "$set": {"last_activity": now},
                        }
                    )
                    self.transcriptions.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"_affair_processed": True}}
                    )
                    stats["assigned_to_existing"] += 1
                else:
                    # C'est un article
                    self.affairs.update_one(
                        {"_id": affair_map[affair_id]},
                        {
                            "$addToSet": {
                                "articles": item_id,
                                "sources": item.get("source", ""),
                                "entities": {"$each": item.get("entities", []) or []},
                            },
                            "$inc": {"item_count": 1},
                            "$set": {"last_activity": now},
                        }
                    )
                    self.articles.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_id": affair_id}}
                    )
                    stats["assigned_to_existing"] += 1

                # Timeline
                event_type = "radio_topic_added" if is_radio else "article_added"
                self.timeline.insert_one({
                    "affair_id": affair_id,
                    "event": event_type,
                    "details": {
                        "item_id": item_id,
                        "title": item.get("title", "")[:80],
                        "source": item.get("source", ""),
                        "reason": assignment.get("reason", ""),
                    },
                    "timestamp": now,
                })

            elif affair_id is None:
                # Créer une nouvelle affaire
                new_title = assignment.get("new_affair_title", item.get("title", "Nouvelle affaire"))
                new_gravity = float(assignment.get("gravity", item.get("gravity_score", 0.5)))

                # Texte de référence construit depuis l'item fondateur
                _item_summary = (item.get("ai_summary", "") or item.get("summary", "") or "").strip()
                _item_content = (item.get("content", "") or item.get("full_text", "") or "").strip()
                _item_ref_text = f"{new_title[:200]}. {_item_summary}"
                if _item_content:
                    _item_ref_text = f"{_item_ref_text} {_item_content}"[:1800]
                else:
                    _item_ref_text = _item_ref_text[:1800]
                new_affair = {
                    "title": new_title[:200],
                    "description": f"Affaire créée par IA: {assignment.get('reason', '')}",
                    "reference_text": _item_ref_text,
                    "reference_title": new_title[:200],
                    "reference_source": item.get("source", ""),
                    "reference_article_id": item_id,
                    "reference_created_at": now,
                    "primary_entity": (item.get("elected", [None]) or [None])[0],
                    "entities": item.get("entities", []) or [],
                    "elected": item.get("elected", []) or [],
                    "institutions": item.get("institutions", []) or [],
                    "keywords": item.get("keywords_found", []) or [],
                    "theme": item.get("theme", "general"),
                    "gravity_score": round(min(1.0, max(0.0, new_gravity)), 3),
                    "affair_type": self._classify_affair_type_by_gravity(new_gravity),
                    "status": "active",
                    "articles": [item_id] if not is_radio else [],
                    "radio_transcriptions": [item.get("_transcription_id", item_id)] if is_radio else [],
                    "social_posts": [],
                    "sources": [item.get("source", "")],
                    "source_types": ["transcription" if is_radio else "article"],
                    "item_count": 1,
                    "created_at": now,
                    "last_activity": now,
                    "promoted_at": now,
                    "bmg": 0,
                    "bmg_details": {},
                    "bmg_history": [],
                    "ai_managed": True,
                }
                self.normalize_affair_data(new_affair)

                result = self.affairs.insert_one(new_affair)
                new_affair_id = str(result.inserted_id)

                # Marquer comme traité
                if is_radio:
                    self.transcriptions.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"_affair_processed": True}}
                    )
                else:
                    self.articles.update_one(
                        {"_id": item["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_id": new_affair_id}}
                    )

                # Timeline
                self.timeline.insert_one({
                    "affair_id": new_affair_id,
                    "event": "created",
                    "details": {
                        "method": "ai_managed",
                        "gravity": new_gravity,
                        "reason": assignment.get("reason", ""),
                        "first_item": item.get("title", "")[:80],
                        "source_type": "radio" if is_radio else "article",
                    },
                    "timestamp": now,
                })

                stats["new_affairs_created"] += 1
                src_label = "📻 Radio" if is_radio else "📰 Article"
                logger.info(
                    f"🆕 Affaire IA créée ({src_label}): '{new_title[:50]}' (gravity={new_gravity:.1f})"
                )

        # 5b. Mises à jour de gravité
        for gupdate in ai_result.get("gravity_updates", []):
            aff_id = gupdate.get("affair_id", "")
            if aff_id in affair_map:
                new_grav = float(gupdate.get("new_gravity", 0))
                old_affair = self.affairs.find_one({"_id": affair_map[aff_id]})
                old_grav = old_affair.get("gravity_score", 0) if old_affair else 0

                self.affairs.update_one(
                    {"_id": affair_map[aff_id]},
                    {"$set": {
                        "gravity_score": round(min(1.0, max(0.0, new_grav)), 3),
                        "affair_type": self._classify_affair_type_by_gravity(new_grav),
                    }}
                )
                stats["gravity_updates"] += 1

                # Timeline si changement significatif
                if abs(new_grav - old_grav) >= 0.1:
                    self.timeline.insert_one({
                        "affair_id": aff_id,
                        "event": "gravity_update",
                        "details": {
                            "old": round(old_grav, 2),
                            "new": round(new_grav, 2),
                            "reason": gupdate.get("reason", ""),
                        },
                        "timestamp": now,
                    })

        # 5c. Expirer les affaires signalées par l'IA
        for exp_id in ai_result.get("expired_affairs", []):
            if exp_id in affair_map:
                self.affairs.update_one(
                    {"_id": affair_map[exp_id]},
                    {"$set": {"status": "archived", "archived_at": now}}
                )
                self.timeline.insert_one({
                    "affair_id": exp_id,
                    "event": "archived",
                    "details": {"reason": "expired_by_ai"},
                    "timestamp": now,
                })
                stats["expired"] += 1

        # 5d. Marquer les items ignorés — NE PAS les bloquer définitivement
        # On incrémente le compteur de tentatives unifié (_match_attempts).
        # Après MAX_MATCH_ATTEMPTS tentatives, on les marque processed.
        for ign_idx in ai_result.get("ignored_articles", []):
            real_idx = ign_idx - 1
            if 0 <= real_idx < len(all_items_for_ai):
                ignored_item = all_items_for_ai[real_idx]
                is_radio = ignored_item.get("_is_radio_topic", False)
                col = self.transcriptions if is_radio else self.articles
                doc = col.find_one({"_id": ignored_item["_id"]})
                # Lit prioritairement _match_attempts, fallback _affair_attempts pour les docs anciens
                prev_attempts = 0
                if doc:
                    prev_attempts = doc.get("_match_attempts") or doc.get("_affair_attempts") or 0
                attempts = prev_attempts + 1
                if attempts >= MAX_MATCH_ATTEMPTS:
                    col.update_one(
                        {"_id": ignored_item["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_ignored": True,
                                  "_match_attempts": attempts},
                         "$unset": {"_affair_attempts": ""}}
                    )
                else:
                    col.update_one(
                        {"_id": ignored_item["_id"]},
                        {"$set": {"_affair_ignored": True, "_match_attempts": attempts},
                         "$unset": {"_affair_processed": "", "_affair_attempts": ""}}
                    )
                stats["ignored"] += 1

        # 6. Ré-affilier les orphelins récents aux affaires nouvellement créées
        if stats["new_affairs_created"] > 0:
            reaffiliated = self._reaffiliate_orphans()
            stats["reaffiliated"] = reaffiliated

        # 7. Enforcer la limite de 20 affaires actives
        self._enforce_max_affairs()

        # 8. Recalculer BMG des affaires touchées
        self._recalculate_active_bmg()

        # 9. Lifecycle classique (stale/archive par date)
        lifecycle_stats = self.update_affair_lifecycle()
        stats["lifecycle"] = lifecycle_stats

        logger.info(
            f"✅ Cycle IA terminé: {stats['assigned_to_existing']} assignés, "
            f"{stats['new_affairs_created']} créées, {stats['gravity_updates']} MAJ gravité, "
            f"{stats['expired']} expirées, {stats['ignored']} ignorés, "
            f"{stats.get('reaffiliated', 0)} ré-affiliés"
        )
        return stats

    def _enforce_max_affairs(self):
        """Expire les affaires les moins graves si on dépasse MAX_ACTIVE_AFFAIRS."""
        active_count = self.affairs.count_documents({"status": "active"})
        if active_count <= MAX_ACTIVE_AFFAIRS:
            return

        excess = active_count - MAX_ACTIVE_AFFAIRS
        # Les moins graves en premier
        weakest = list(
            self.affairs.find({"status": "active"})
            .sort("gravity_score", 1)
            .limit(excess)
        )
        now = datetime.utcnow()
        for aff in weakest:
            self.affairs.update_one(
                {"_id": aff["_id"]},
                {"$set": {"status": "archived", "archived_at": now}}
            )
            self.timeline.insert_one({
                "affair_id": str(aff["_id"]),
                "event": "archived",
                "details": {"reason": f"max_affairs_exceeded ({active_count}>{MAX_ACTIVE_AFFAIRS})"},
                "timestamp": now,
            })
            logger.info(f"📤 Affaire expirée (limite {MAX_ACTIVE_AFFAIRS}): '{aff.get('title', '')[:40]}'")

    def _detect_snowball_affairs(self) -> int:
        """Détecte les affaires qui accumulent trop de fusions récentes (effet boule de neige).

        Vérifie dans la timeline combien de fusions chaque affaire active a reçu
        dans les dernières SNOWBALL_WINDOW_HOURS heures. Si ça dépasse le seuil,
        envoie une alerte Telegram et marque l'affaire comme suspecte.

        Retourne le nombre d'alertes envoyées.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=SNOWBALL_WINDOW_HOURS)
        alerts_sent = 0

        # Chercher les événements de fusion récents dans la timeline
        merge_events = [
            "manual_merge", "cluster_merged", "consolidated",
            "stale_merged", "article_added", "radio_topic_added",
            "article_reaffiliated",
        ]

        # Compter les fusions par affaire dans la fenêtre
        pipeline = [
            {"$match": {
                "event": {"$in": merge_events},
                "timestamp": {"$gte": cutoff},
            }},
            {"$group": {
                "_id": "$affair_id",
                "merge_count": {"$sum": 1},
            }},
            {"$match": {
                "merge_count": {"$gte": SNOWBALL_MERGE_THRESHOLD},
            }},
        ]

        try:
            results = list(self.timeline.aggregate(pipeline))
        except Exception as e:
            logger.warning(f"⚠️ Snowball detection: {e}")
            return 0

        for result in results:
            affair_id = result["_id"]
            merge_count = result["merge_count"]

            affair = self.affairs.find_one({"_id": ObjectId(affair_id)}) if ObjectId.is_valid(affair_id) else None
            if not affair:
                continue

            # Vérifier aussi le nombre total d'items
            item_count = affair.get("item_count", 0)
            already_flagged = affair.get("_snowball_flagged", False)

            if merge_count >= SNOWBALL_MERGE_THRESHOLD or item_count >= SNOWBALL_MAX_ITEMS:
                # Marquer l'affaire comme suspecte (ne pas la bloquer, juste alerter)
                if not already_flagged:
                    self.affairs.update_one(
                        {"_id": affair["_id"]},
                        {"$set": {
                            "_snowball_flagged": True,
                            "_snowball_flagged_at": now,
                            "_snowball_merge_count": merge_count,
                        }}
                    )

                    self.timeline.insert_one({
                        "affair_id": affair_id,
                        "event": "snowball_alert",
                        "details": {
                            "merge_count_24h": merge_count,
                            "item_count": item_count,
                            "threshold": SNOWBALL_MERGE_THRESHOLD,
                        },
                        "timestamp": now,
                    })

                    # Notification Telegram
                    if _telegram_ok and _tg_snowball:
                        try:
                            _tg_snowball(affair, merge_count, SNOWBALL_MERGE_THRESHOLD)
                        except Exception:
                            pass

                    logger.warning(
                        f"⚠️ BOULE DE NEIGE: '{affair.get('title', '')[:50]}' "
                        f"— {merge_count} fusions en {SNOWBALL_WINDOW_HOURS}h, "
                        f"{item_count} items total"
                    )
                    alerts_sent += 1

        if alerts_sent > 0:
            logger.info(f"⚠️ {alerts_sent} alertes boule de neige envoyées")
        return alerts_sent

    def _recalculate_active_bmg(self):
        """Recalcule le BMG de toutes les affaires actives.

        Respecte la hiérarchie GPT > formule :
        - Si l'affaire a un ai_context.bruit_score, le BMG GPT est la source
          de vérité ; on n'écrit que bmg_formula et bmg_details.
        - Sinon, le BMG formulaic est écrit en bmg ET bmg_formula.
        """
        active = list(self.affairs.find({"status": "active"}))
        for aff in active:
            try:
                bmg = self.calculate_bmg(aff)
                formula_value = bmg["bmg"]

                ai_ctx = aff.get("ai_context") or {}
                has_gpt_bmg = isinstance(ai_ctx, dict) and ai_ctx.get("bruit_score") is not None

                set_fields: Dict[str, Any] = {
                    "bmg_formula": formula_value,
                    "bmg_details": bmg,
                }
                if not has_gpt_bmg:
                    # Pas de BMG GPT → la formule reste la source de vérité
                    set_fields["bmg"] = formula_value

                self.affairs.update_one(
                    {"_id": aff["_id"]},
                    {
                        "$set": set_fields,
                        "$push": {"bmg_history": {
                            "$each": [{
                                "bmg": aff.get("bmg") if has_gpt_bmg else formula_value,
                                "bmg_formula": formula_value,
                                "at": datetime.utcnow().isoformat(),
                            }],
                            "$slice": -30,
                        }},
                    }
                )
            except Exception as e:
                logger.error(f"❌ BMG recalc pour '{aff.get('title', '?')[:40]}': {e}", exc_info=True)

    def _reaffiliate_orphans(self) -> int:
        """Ré-essaye de lier les articles orphelins récents aux affaires actives.
        Utilise un matching plus souple : 1 entité spécifique (personne) suffit,
        ou 1 entité + même thème."""
        cutoff_dt = datetime.utcnow() - timedelta(days=5)
        cutoff_str = cutoff_dt.isoformat()

        orphans = list(self.articles.find({
            "$and": [
                {"_analysis_method": {"$exists": True}},
                {"$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                ]},
                {"$or": [
                    {"scraped_at": {"$gte": cutoff_dt}},
                    {"scraped_at": {"$gte": cutoff_str}},
                ]},
            ]
        }).limit(50))

        if not orphans:
            return 0

        active_affairs = list(self.affairs.find({"status": "active"}))
        if not active_affairs:
            return 0

        reaffiliated = 0
        now = datetime.utcnow()

        for art in orphans:
            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            )
            art_entities = art_elected | art_institutions
            art_theme = art.get("theme", "general")

            if not art_entities:
                continue

            best_match = None
            best_score = 0

            for affair in active_affairs:
                aff_elected = set(
                    e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
                )
                aff_institutions = set(
                    e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
                )
                aff_entities = aff_elected | aff_institutions
                aff_theme = affair.get("theme", "general")

                # Entités en commun
                common = art_entities & aff_entities
                common_elected = art_elected & aff_elected  # personnes en commun (plus fiable)

                if not common:
                    continue

                # Score de match — distinguer génériques (Chalus, Lurel...) vs spécifiques
                score = 0
                for elu in common_elected:
                    if elu in self.GENERIC_ELECTED:
                        score += 1  # élu générique = signal faible (anti boule de neige)
                    else:
                        score += 3  # élu spécifique = fort signal
                # Institutions en commun
                score += len(common - common_elected) * 1
                # Bonus même thème (hors général)
                if art_theme == aff_theme and art_theme not in BROAD_THEMES and art_theme != "":
                    score += 2

                # Seuil : au moins 3 points
                # 1 élu générique (1pt) + même thème (2pt) = 3 → OK si même sujet
                # 1 élu spécifique (3pt) = OK
                # 1 élu générique seul (1pt) = PAS assez → anti boule de neige
                if score >= 3 and score > best_score:
                    best_score = score
                    best_match = affair

            if best_match:
                art_id = str(art["_id"])
                # IMPORTANT : NE PAS ajouter les entités de l'article dans l'affaire
                # pour éviter l'effet boule de neige (une affaire qui absorbe tout)
                self.affairs.update_one(
                    {"_id": best_match["_id"]},
                    {
                        "$addToSet": {
                            "articles": art_id,
                            "sources": art.get("source", ""),
                        },
                        "$inc": {"item_count": 1},
                        "$set": {"last_activity": now},
                    }
                )
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {
                        "_affair_processed": True,
                        "_affair_id": str(best_match["_id"]),
                        "_affair_reaffiliated": True,
                    }}
                )
                self.timeline.insert_one({
                    "affair_id": str(best_match["_id"]),
                    "event": "article_reaffiliated",
                    "details": {
                        "item_id": art_id,
                        "title": art.get("title", "")[:80],
                        "source": art.get("source", ""),
                        "match_score": best_score,
                    },
                    "timestamp": now,
                })
                reaffiliated += 1

        if reaffiliated:
            logger.info(f"🔗 Ré-affiliation: {reaffiliated} articles orphelins rattachés")
        return reaffiliated

    def _classify_affair_type_by_gravity(self, gravity: float) -> str:
        """Classifie le type d'affaire selon le score de gravité."""
        if gravity >= 0.85:
            return "crise_majeure"
        elif gravity >= 0.75:
            return "affaire_grave"
        elif gravity >= 0.65:
            return "affaire_importante"
        elif gravity >= 0.50:
            return "incident_significatif"
        else:
            return "sujet_suivi"

    def _classify_affair_type(self, art: dict) -> str:
        """Classifie le type d'affaire depuis le contenu de l'article.
        Priorité : affair_type Groq > mapping thème > catégorie détectée > fallback gravité.
        """
        # Priorité 1 : affair_type explicite fourni par Groq à l'enrichissement
        art_affair_type = (art.get("affair_type") or "").strip()
        if art_affair_type and art_affair_type not in ("general", "sujet_suivi", "sujet_local", ""):
            return art_affair_type

        # Priorité 2 : mapping theme Groq → type sémantique
        THEME_TO_TYPE = {
            "securite_justice": "affaire_judiciaire",
            "politique_institutions": "affaire_politique",
            "sante_social": "crise_sanitaire",
            "economie_emploi": "affaire_economique",
            "energie_transports": "incident_infrastructure",
            "eau_env": "crise_environnementale",
            "culture_patrimoine": "evenement_culturel",
        }
        theme = (art.get("theme") or "general").strip()
        if theme in THEME_TO_TYPE:
            return THEME_TO_TYPE[theme]

        # Priorité 3 : catégorie d'événement détectée dans titre + résumé
        text = f"{art.get('title', '')} {art.get('ai_summary', '')}".strip()
        cat = self._detect_event_category(text)
        if cat:
            return cat

        # Fallback : classification par gravité (ancienne méthode)
        return self._classify_affair_type_by_gravity(art.get("gravity_score", 0))

    # ============================================================
    # JOB COMBINÉ — À appeler par le scheduler
    # ============================================================
    def run_full_cycle(self) -> Dict[str, Any]:
        """
        Exécute le cycle complet classique (fallback si IA indisponible) :
        1. Création directe d'affaires pour articles haute gravité
        2. Clustering des nouveaux candidats
        3. Promotion des clusters éligibles
        4. Ré-affiliation des orphelins
        5. Mise à jour du cycle de vie
        """
        logger.info("=" * 50)
        logger.info("🔄 CYCLE CLASSIQUE AFFAIRES (fallback)")
        logger.info("=" * 50)

        results = {}

        # 0. Création directe : articles enrichis à haute gravité sans affaire
        results["direct_creation"] = self._direct_create_from_enriched()

        # 1. Clustering
        results["clustering"] = self.run_clustering()

        # 2. Promotion
        results["promotion"] = self.run_promotion()

        # 3. Ré-affiliation des orphelins
        results["reaffiliated"] = self._reaffiliate_orphans()

        # 4. Lifecycle
        results["lifecycle"] = self.update_affair_lifecycle()

        # 5. BMG
        self._recalculate_active_bmg()

        # 6. Cross-check stale ↔ active (GPT)
        results["stale_active_merged"] = self._cross_check_stale_active()

        logger.info(f"✅ Cycle classique terminé: {results}")
        return results

    def _direct_create_from_enriched(self) -> Dict[str, Any]:
        """
        Filet de sécurité : crée des affaires directement à partir d'articles
        enrichis qui ont une gravité suffisante et ne sont pas encore traités.
        Pas besoin de clustering ni d'IA — chaque article notable = 1 affaire.
        On fusionne si un article ressemble fortement à une affaire existante.
        """
        if self.db is None:
            return {"error": "no_db"}

        now = datetime.utcnow()
        cutoff_dt = now - timedelta(days=3)
        cutoff_str = cutoff_dt.isoformat()

        # Articles enrichis non traités avec gravité >= 0.30
        unprocessed = list(self.articles.find({
            "$and": [
                {"_analysis_method": {"$exists": True}},
                {"gravity_score": {"$gte": 0.30}},
                {"$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                ]},
                {"$or": [
                    {"scraped_at": {"$gte": cutoff_dt}},
                    {"scraped_at": {"$gte": cutoff_str}},
                ]},
            ]
        }).sort("gravity_score", -1).limit(30))

        if not unprocessed:
            return {"created": 0, "merged": 0}

        active_affairs = list(self.affairs.find({"status": "active"}))
        stats = {"created": 0, "merged": 0, "skipped": 0}

        for art in unprocessed:
            art_id = str(art["_id"])
            art_elected = set(
                e.lower().strip() for e in (art.get("elected", []) or []) if e and len(e) > 3
            )
            art_institutions = set(
                e.lower().strip() for e in (art.get("institutions", []) or []) if e and len(e) > 3
            )
            art_entities = art_elected | art_institutions
            art_theme = art.get("theme", "general")
            gravity = art.get("gravity_score", 0)

            # Chercher une affaire existante similaire
            best_match = None
            best_score = 0
            for affair in active_affairs:
                aff_elected = set(
                    e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
                )
                aff_entities = aff_elected | set(
                    e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
                )
                common = art_entities & aff_entities
                common_elected = art_elected & aff_elected
                same_theme = (art_theme == affair.get("theme", "") and art_theme not in BROAD_THEMES and art_theme != "")

                score = len(common_elected) * 3 + len(common - common_elected) + (2 if same_theme else 0)
                if score >= 3 and score > best_score:
                    best_score = score
                    best_match = affair

            if best_match:
                # Fusionner avec l'affaire existante
                self.affairs.update_one(
                    {"_id": best_match["_id"]},
                    {
                        "$addToSet": {
                            "articles": art_id,
                            "sources": art.get("source", ""),
                            "entities": {"$each": list(art_entities)[:10]},
                        },
                        "$inc": {"item_count": 1},
                        "$set": {"last_activity": now},
                        "$max": {"gravity_score": gravity},
                    }
                )
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_id": str(best_match["_id"])}}
                )
                stats["merged"] += 1
            else:
                # Créer une nouvelle affaire
                title = art.get("title", "Nouvelle affaire")[:200]
                _legacy_summary = (art.get("ai_summary", "") or "").strip()
                _legacy_content = (art.get("content", "") or "").strip()
                _legacy_ref = f"{title}. {_legacy_summary}"
                if _legacy_content:
                    _legacy_ref = f"{_legacy_ref} {_legacy_content}"[:1800]
                else:
                    _legacy_ref = _legacy_ref[:1800]
                new_affair = {
                    "title": title,
                    "description": art.get("ai_summary", "")[:300] or f"Affaire créée automatiquement depuis: {title}",
                    "reference_text": _legacy_ref,
                    "reference_title": title,
                    "reference_source": art.get("source", ""),
                    "reference_article_id": art_id,
                    "reference_created_at": now,
                    "primary_entity": (list(art_elected) or [None])[0] if art_elected else None,
                    "entities": list(art_entities)[:20],
                    "elected": list(art_elected)[:10],
                    "institutions": list(art_institutions)[:10],
                    "keywords": art.get("keywords_found", []) or [],
                    "theme": art_theme,
                    "gravity_score": round(gravity, 3),
                    "affair_type": self._classify_affair_type_by_gravity(gravity),
                    "status": "active",
                    "articles": [art_id],
                    "radio_transcriptions": [],
                    "social_posts": [],
                    "sources": [art.get("source", "")],
                    "source_types": ["article"],
                    "item_count": 1,
                    "created_at": now,
                    "last_activity": now,
                    "promoted_at": now,
                    "bmg": 0,
                    "bmg_details": {},
                    "bmg_history": [],
                    "ai_managed": False,
                    "_creation_method": "direct_from_enriched",
                }
                self.normalize_affair_data(new_affair)
                result = self.affairs.insert_one(new_affair)
                new_id = str(result.inserted_id)
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_id": new_id}}
                )
                self.timeline.insert_one({
                    "affair_id": new_id,
                    "event": "created",
                    "details": {
                        "method": "direct_from_enriched",
                        "gravity": gravity,
                        "title": title[:80],
                        "source": art.get("source", ""),
                    },
                    "timestamp": now,
                })
                # Ajouter à la liste pour les prochaines itérations
                active_affairs.append(new_affair)
                stats["created"] += 1
                logger.info(f"🆕 Affaire directe: '{title[:50]}' (gravity={gravity:.2f})")
                # Auto-génération du contexte IA
                try:
                    self.generate_affair_context(new_id)
                except Exception as ctx_err:
                    logger.debug(f"Auto-contexte IA direct: {ctx_err}")

        self._enforce_max_affairs()
        logger.info(f"📊 Création directe: {stats['created']} créées, {stats['merged']} fusionnées")
        return stats

    # ============================================================
    # UTILITAIRES
    # ============================================================
    def _extract_tokens(self, text: str) -> Set[str]:
        """Extraction basique de tokens (utilisé par le clustering interne)."""
        if not text:
            return set()
        import unicodedata
        text = unicodedata.normalize("NFKD", text.lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        words = re.findall(r"[a-z]{3,}", text)
        return {w for w in words if w not in STOPWORDS}

    def _extract_context_tokens(
        self, text: str, item: Dict[str, Any]
    ) -> Set[str]:
        """
        Extraction enrichie de tokens pour l'ingestion.
        Combine le texte (résumé IA ou contenu limité) avec les
        entités nommées et mots-clés de l'enrichissement pour
        produire un ensemble de tokens discriminant.
        """
        # Tokens du texte (résumé IA ou contenu limité)
        base_tokens = self._extract_tokens(text)

        # Ajouter les entités nommées (très discriminantes)
        for entity in (item.get("elected") or []):
            if entity and len(entity) > 2:
                # Découper les noms composés : "Ary Chalus" → {"ary", "chalus"}
                base_tokens.update(
                    w.lower() for w in entity.split() if len(w) > 2
                )
        for inst in (item.get("institutions") or []):
            if inst and len(inst) > 2:
                base_tokens.update(
                    w.lower() for w in inst.split() if len(w) > 2
                )

        # Ajouter les mots-clés trouvés par l'enrichissement
        for kw in (item.get("keywords_found") or []):
            if kw and len(kw) > 2:
                base_tokens.update(
                    w.lower() for w in kw.split() if len(w) > 2
                )

        # Filtrer les mots trop génériques pour la Guadeloupe
        # (présents dans presque tous les articles, donc non discriminants)
        noise_words = {
            "guadeloupe", "antilles", "caraibe", "caraibes", "france",
            "outre", "mer", "ile", "iles", "region", "departement",
            "commune", "ville", "population", "habitants", "territoire",
            "article", "information", "infos", "selon", "aussi",
            "plus", "tous", "tout", "toute", "toutes", "tres",
            "cette", "dans", "avec", "pour", "depuis", "lors",
            # Mots culturels/historiques trop génériques (présents dans beaucoup de sujets différents)
            "histoire", "historique", "memoire", "patrimoine", "culture",
            "culturel", "culturelle", "commemoration", "hommage", "tradition",
            "traditionnel", "traditionnelle", "societe", "social", "sociale",
            "communaute", "identite", "heritage", "local", "locale",
        }
        base_tokens -= noise_words
        base_tokens -= STOPWORDS

        return base_tokens

    def _pairwise_similarity(
        self,
        tokens_a: Set[str], theme_a: str, entities_a: Set[str],
        tokens_b: Set[str], theme_b: str, entities_b: Set[str],
        date_a: Optional[datetime] = None,
        date_b: Optional[datetime] = None,
        embedding_a: Optional[List] = None,
        embedding_b: Optional[List] = None,
    ) -> float:
        """Similarité hybride entre deux items :
        - 0.55 similarité sémantique (embeddings) ou tokens fallback
        - 0.25 entités communes (avec résolution d'alias)
        - 0.20 proximité temporelle

        Si embeddings non disponibles, fallback sur tokens + thème.
        """
        # ── 1. Similarité sémantique (55%) ──
        semantic_score = 0.0
        if embedding_a and embedding_b:
            try:
                from backend.embedding_service import cosine_similarity
                semantic_score = max(0, cosine_similarity(embedding_a, embedding_b))
            except ImportError:
                pass

        if not embedding_a or not embedding_b:
            # Fallback : tokens + thème
            common_tokens = tokens_a & tokens_b
            if not common_tokens and not (entities_a & entities_b):
                return 0.0
            min_size = min(len(tokens_a), len(tokens_b))
            token_score = len(common_tokens) / max(min_size, 1)
            # Pas de bonus pour les thèmes larges qui regroupent des événements sans lien
            theme_bonus = 0.2 if (theme_a and theme_a == theme_b and theme_a not in BROAD_THEMES) else 0.0
            semantic_score = min(1.0, token_score + theme_bonus)

        # ── 2. Entités communes (25%) ──
        entity_score = 0.0
        if entities_a or entities_b:
            # Résolution d'alias
            try:
                from backend.entity_aliases import entities_match
                common_ent, jaccard = entities_match(list(entities_a), list(entities_b))
                entity_score = jaccard
                # Bonus : entité spécifique commune vaut plus
                for e in common_ent:
                    if e.lower() not in self.GENERIC_ELECTED:
                        entity_score = min(1.0, entity_score + 0.3)
                        break
            except ImportError:
                common_entities = entities_a & entities_b
                entity_score = len(common_entities) / max(len(entities_a | entities_b), 1)

        # ── 3. Proximité temporelle (20%) ──
        temporal_score = 0.5  # Défaut si pas de dates
        if date_a and date_b:
            try:
                delta_hours = abs((date_a - date_b).total_seconds()) / 3600
                if delta_hours <= 12:
                    temporal_score = 1.0
                elif delta_hours <= 24:
                    temporal_score = 0.8
                elif delta_hours <= 48:
                    temporal_score = 0.5
                elif delta_hours <= 72:
                    temporal_score = 0.3
                else:
                    temporal_score = 0.1
            except (TypeError, ValueError):
                temporal_score = 0.5

        # ── Score final pondéré ──
        return semantic_score * 0.55 + entity_score * 0.25 + temporal_score * 0.20

    def _candidate_cluster_similarity(
        self, cand_tokens: Set[str], cand_theme: str, cand_entities: Set[str],
        cluster: Dict,
        cand_date: Optional[datetime] = None,
    ) -> float:
        """Similarité entre un candidat et un cluster."""
        cl_tokens = cluster.get("all_tokens_set") or set(cluster.get("all_tokens", []))
        cl_theme = cluster.get("dominant_theme", "")
        cl_entities = set(cluster.get("all_entities", []))
        cl_date = cluster.get("last_activity") or cluster.get("created_at")
        return self._pairwise_similarity(
            cand_tokens, cand_theme, cand_entities,
            cl_tokens, cl_theme, cl_entities,
            date_a=cand_date, date_b=cl_date,
        )

    def _cluster_cluster_similarity(self, cl_a: Dict, cl_b: Dict) -> float:
        """Similarité entre deux clusters."""
        return self._pairwise_similarity(
            cl_a.get("all_tokens_set") or set(cl_a.get("all_tokens", [])),
            cl_a.get("dominant_theme", ""),
            set(cl_a.get("all_entities", [])),
            cl_b.get("all_tokens_set") or set(cl_b.get("all_tokens", [])),
            cl_b.get("dominant_theme", ""),
            set(cl_b.get("all_entities", [])),
            date_a=cl_a.get("last_activity") or cl_a.get("created_at"),
            date_b=cl_b.get("last_activity") or cl_b.get("created_at"),
        )

    def _classify_affair_type_cluster(self, cluster: Dict) -> str:
        g = cluster.get("max_gravity", 0)
        if g >= 0.85:
            return "crise_majeure"
        elif g >= 0.75:
            return "affaire_grave"
        elif g >= 0.65:
            return "affaire_importante"
        elif g >= 0.50:
            return "incident_significatif"
        else:
            return "sujet_suivi"

    def _generate_affair_description(self, cluster: Dict) -> str:
        titles = [item.get("title", "") for item in cluster.get("items", [])[:5]]
        sources = cluster.get("all_sources", [])
        return (
            f"Affaire détectée à partir de {cluster.get('item_count', 0)} éléments "
            f"provenant de {len(sources)} source(s) ({', '.join(sources[:3])}). "
            f"Sujets : {' | '.join(t for t in titles[:3] if t)}"
        )

    def _is_institution(self, entity: str) -> bool:
        institutions = {"CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF", "Préfecture", "Rectorat"}
        return entity in institutions or entity.upper() == entity

    def _get_presse_weight(self, source: str) -> float:
        for name, weight in PRESSE_WEIGHTS.items():
            if name.lower() in source.lower():
                return weight
        return 0.4

    def _get_radio_weight(self, station: str) -> float:
        for name, weight in RADIO_WEIGHTS.items():
            if name.lower() in station.lower():
                return weight
        return 0.3

    def _parse_date(self, val: Any) -> Optional[datetime]:
        """Délégué à _parse_dt qui gère correctement Z/+00:00 (cf. audit C5/S10).
        L'ancienne implémentation tronquait `val[:len(fmt)+2]` et ignorait
        complètement les suffixes timezone — toutes les dates ISO+TZ
        tombaient en None.
        """
        return self._parse_dt(val)

    # ============================================================
    # SANTÉ
    # ============================================================
    def health_check(self) -> Dict[str, Any]:
        if self.db is None:
            return {"status": "down"}

        try:
            return {
                "status": "operational",
                "candidates_total": self.candidates.estimated_document_count(),
                "candidates_unclustered": self.candidates.count_documents({"cluster_id": None}),
                "clusters_active": self.clusters.count_documents({"status": "active"}),
                "affairs_active": self.affairs.count_documents({"status": "active"}),
                "affairs_stale": self.affairs.count_documents({"status": "stale"}),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ============================================================
# SINGLETON
# ============================================================
_instance: Optional[AffairLifecycleService] = None

def get_affair_lifecycle_service(db=None) -> AffairLifecycleService:
    global _instance
    if _instance is None:
        _instance = AffairLifecycleService(db=db)
    return _instance
