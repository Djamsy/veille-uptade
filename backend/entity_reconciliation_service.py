# backend/entity_reconciliation_service.py
"""
Service de réconciliation des entités et affaires
===================================================
PRINCIPE : Les articles scrapés sont la SOURCE DE VÉRITÉ.
Les transcriptions radio (Whisper) déforment souvent les noms.

FLUX :
1. On maintient un index glissant des articles récents (2-3 jours)
   avec leurs entités correctes + contexte (thème, mots-clés, lieux)
2. Quand une transcription arrive, on extrait son contexte
3. On cherche les articles qui partagent le même contexte (thème + mots-clés)
4. Si match contextuel suffisant :
   - On adopte les entités de l'article (noms corrects)
   - On lie la transcription à l'affaire de l'article
5. On recalcule le BMG avec les entités normalisées

AVANTAGES vs regex statique (tags_index) :
- Pas besoin de deviner comment Whisper a déformé un nom
- Les entités viennent directement du texte journalistique
- Le lien article↔transcription permet le suivi d'affaire cross-média
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict, Counter
from difflib import SequenceMatcher

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger("entity_reconciliation")


# ============================================================
# CONFIGURATION
# ============================================================
CONTEXT_WINDOW_DAYS = 3          # Fenêtre de recherche d'articles
MIN_CONTEXT_SCORE = 0.35         # Seuil minimum de matching contextuel
MIN_FUZZY_NAME_RATIO = 0.65      # Seuil de similarité floue pour les noms
ENTITY_BOOST_WEIGHT = 0.25       # Poids du bonus entité dans le score
KEYWORD_MATCH_WEIGHT = 0.35      # Poids des mots-clés dans le score
THEME_MATCH_WEIGHT = 0.25        # Poids du thème dans le score
TEMPORAL_WEIGHT = 0.15           # Poids de la proximité temporelle

# Mots vides à ignorer dans le matching contextuel
STOPWORDS_FR = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
    "est", "a", "au", "aux", "ce", "ces", "qui", "que", "son", "sa",
    "ses", "sur", "par", "pour", "dans", "avec", "pas", "ne", "plus",
    "se", "ou", "il", "elle", "ils", "ont", "ete", "nous", "vous",
    "leur", "cette", "aussi", "tres", "tout", "fait", "bien", "mais",
    "comme", "peut", "etre", "autre", "entre", "apres", "avant",
}


# ============================================================
# SERVICE PRINCIPAL
# ============================================================
class EntityReconciliationService:
    """
    Réconcilie les transcriptions radio avec les articles scrapés.
    Utilise le contexte (thème, mots-clés, lieux, temporalité)
    plutôt que le matching direct de noms.
    """

    def __init__(self, db=None):
        """
        Initialise le service avec une connexion MongoDB.
        Si db n'est pas fourni, tente de se connecter.
        """
        self.db = db
        if self.db is None:
            self._connect_db()

        # Collections
        if self.db is not None:
            self.articles_col = self.db["articles_guadeloupe"]
            self.transcriptions_col = self.db["radio_transcriptions"]
            self.affairs_col = self.db["affairs"]
            self.reconciliation_log = self.db["reconciliation_log"]
        else:
            logger.error("❌ Pas de connexion MongoDB — service inopérant")

        # Cache en mémoire de l'index articles (rechargé périodiquement)
        self._article_index: List[Dict[str, Any]] = []
        self._index_built_at: Optional[datetime] = None
        self._index_ttl_minutes = 30  # Rebuild toutes les 30 min

        logger.info("✅ EntityReconciliationService initialisé")

    def _connect_db(self):
        """Connexion MongoDB si pas fournie."""
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
            logger.info("🔗 Reconciliation service connecté à MongoDB")
        except Exception as e:
            logger.error(f"❌ MongoDB indisponible: {e}")
            self.db = None

    # ============================================================
    # INDEX DES ARTICLES RÉCENTS
    # ============================================================
    def build_article_index(self, force: bool = False) -> int:
        """
        Construit/rafraîchit l'index des articles récents.
        Chaque entrée contient :
        - _id, title, entities, theme, keywords, date, affair_id
        - context_tokens : mots significatifs du titre + contenu (nettoyés)
        """
        if not force and self._index_built_at:
            age = (datetime.utcnow() - self._index_built_at).total_seconds() / 60
            if age < self._index_ttl_minutes and self._article_index:
                return len(self._article_index)

        if self.db is None:
            return 0

        cutoff = datetime.utcnow() - timedelta(days=CONTEXT_WINDOW_DAYS)

        # Requête : articles récents avec au moins un titre
        query = {
            "$or": [
                {"scraped_at": {"$gte": cutoff.isoformat()}},
                {"published_at": {"$gte": cutoff.isoformat()}},
                {"date": {"$gte": cutoff.isoformat()}},
                # Fallback numérique pour les dates stockées autrement
                {"created_at": {"$gte": cutoff}},
            ]
        }

        try:
            cursor = self.articles_col.find(
                query,
                {
                    "_id": 1,
                    "title": 1,
                    "content": 1,
                    "elected": 1,
                    "institutions": 1,
                    "entities": 1,
                    "theme": 1,
                    "keywords_found": 1,
                    "is_affair": 1,
                    "affair_id": 1,
                    "affair_type": 1,
                    "gravity_score": 1,
                    "importance_score": 1,
                    "source": 1,
                    "site": 1,
                    "scraped_at": 1,
                    "published_at": 1,
                    "date": 1,
                }
            ).limit(500)

            self._article_index = []
            for doc in cursor:
                entry = self._build_index_entry(doc)
                if entry:
                    self._article_index.append(entry)

            self._index_built_at = datetime.utcnow()
            logger.info(
                f"📚 Index articles reconstruit : {len(self._article_index)} articles "
                f"(fenêtre {CONTEXT_WINDOW_DAYS}j)"
            )
            return len(self._article_index)

        except Exception as e:
            logger.error(f"❌ Erreur construction index: {e}")
            return 0

    def _build_index_entry(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Construit une entrée d'index à partir d'un document article."""
        title = (doc.get("title") or "").strip()
        if not title or len(title) < 10:
            return None

        content = doc.get("content") or ""
        full_text = f"{title} {content}"

        # Extraction des tokens de contexte significatifs
        context_tokens = self._extract_context_tokens(full_text)
        if len(context_tokens) < 3:
            return None

        # Entités normalisées
        entities = set()
        for e in (doc.get("elected") or []):
            entities.add(self._normalize_name(e))
        for e in (doc.get("institutions") or []):
            entities.add(self._normalize_name(e))
        for e in (doc.get("entities") or []):
            entities.add(self._normalize_name(e))

        return {
            "_id": str(doc["_id"]),
            "title": title,
            "entities": entities,
            "theme": doc.get("theme", "general"),
            "keywords": set(doc.get("keywords_found") or []),
            "context_tokens": context_tokens,
            "is_affair": doc.get("is_affair", False),
            "affair_id": doc.get("affair_id"),
            "affair_type": doc.get("affair_type", "routine"),
            "gravity_score": doc.get("gravity_score", 0),
            "importance_score": doc.get("importance_score", 0),
            "source": doc.get("source") or doc.get("site", ""),
            "date": doc.get("scraped_at") or doc.get("published_at") or doc.get("date"),
        }

    # ============================================================
    # RECONCILIATION D'UNE TRANSCRIPTION
    # ============================================================
    def reconcile_transcription(
        self, transcription: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal.
        Prend une transcription (dict), la réconcilie avec les articles,
        et retourne la transcription enrichie/corrigée.
        """
        # 1. S'assurer que l'index est à jour
        self.build_article_index()

        if not self._article_index:
            logger.warning("⚠️ Index articles vide — pas de réconciliation")
            transcription["_reconciliation"] = {
                "status": "skipped",
                "reason": "no_articles_in_window",
            }
            return transcription

        # 2. Extraire le contexte de la transcription
        trans_text = transcription.get("text") or transcription.get("content") or ""
        trans_title = transcription.get("summary") or transcription.get("title") or ""
        full_trans_text = f"{trans_title} {trans_text}"

        trans_context = {
            "tokens": self._extract_context_tokens(full_trans_text),
            "theme": transcription.get("theme", ""),
            "keywords": set(transcription.get("keywords_found") or []),
            "raw_entities": self._extract_raw_names(full_trans_text),
            "date": transcription.get("captured_at") or transcription.get("date"),
        }

        if len(trans_context["tokens"]) < 3:
            transcription["_reconciliation"] = {
                "status": "skipped",
                "reason": "transcription_too_short",
            }
            return transcription

        # 3. Trouver les articles qui matchent le contexte
        matches = self._find_context_matches(trans_context)

        if not matches:
            transcription["_reconciliation"] = {
                "status": "no_match",
                "reason": "no_contextual_match_found",
                "tokens_count": len(trans_context["tokens"]),
            }
            return transcription

        # 4. Appliquer la réconciliation
        best_match = matches[0]  # Meilleur match par score
        reconciled = self._apply_reconciliation(transcription, best_match, matches)

        # 5. Loguer la réconciliation
        self._log_reconciliation(transcription, best_match, matches)

        return reconciled

    def _find_context_matches(
        self, trans_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Trouve les articles dont le contexte matche la transcription.
        Score composite : tokens communs + thème + keywords + proximité temporelle + noms flous
        """
        scored_matches = []

        for article in self._article_index:
            score = self._compute_context_score(trans_context, article)
            if score >= MIN_CONTEXT_SCORE:
                scored_matches.append({
                    "article": article,
                    "score": round(score, 4),
                })

        # Trier par score décroissant
        scored_matches.sort(key=lambda m: m["score"], reverse=True)
        return scored_matches[:10]  # Top 10 max

    def _compute_context_score(
        self, trans_context: Dict[str, Any], article: Dict[str, Any]
    ) -> float:
        """
        Calcule un score de matching contextuel entre transcription et article.
        """
        score = 0.0

        # --- 1. Tokens de contexte communs (le plus important) ---
        trans_tokens = trans_context["tokens"]
        art_tokens = article["context_tokens"]
        common_tokens = trans_tokens & art_tokens

        if not common_tokens:
            return 0.0  # Pas de mots communs → pas de match

        # Jaccard pondéré (normalise par la taille du plus petit ensemble)
        min_size = min(len(trans_tokens), len(art_tokens))
        if min_size > 0:
            token_ratio = len(common_tokens) / min_size
        else:
            token_ratio = 0
        score += token_ratio * KEYWORD_MATCH_WEIGHT

        # --- 2. Thème commun ---
        if trans_context["theme"] and article["theme"]:
            if trans_context["theme"] == article["theme"]:
                score += THEME_MATCH_WEIGHT
            elif self._themes_related(trans_context["theme"], article["theme"]):
                score += THEME_MATCH_WEIGHT * 0.5

        # --- 3. Keywords communs ---
        common_kw = trans_context["keywords"] & article["keywords"]
        if common_kw:
            kw_ratio = len(common_kw) / max(
                len(trans_context["keywords"] | article["keywords"]), 1
            )
            score += kw_ratio * KEYWORD_MATCH_WEIGHT

        # --- 4. Matching flou des noms (si la transcription a détecté des noms) ---
        if trans_context["raw_entities"] and article["entities"]:
            name_score = self._fuzzy_name_match_score(
                trans_context["raw_entities"], article["entities"]
            )
            score += name_score * ENTITY_BOOST_WEIGHT

        # --- 5. Proximité temporelle ---
        temporal_score = self._temporal_proximity(
            trans_context.get("date"), article.get("date")
        )
        score += temporal_score * TEMPORAL_WEIGHT

        return score

    # ============================================================
    # APPLICATION DE LA RÉCONCILIATION
    # ============================================================
    def _apply_reconciliation(
        self,
        transcription: Dict[str, Any],
        best_match: Dict[str, Any],
        all_matches: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Applique les corrections de la réconciliation à la transcription.
        """
        article = best_match["article"]
        match_score = best_match["score"]

        # Collecter toutes les entités des articles matchés (top 3)
        reconciled_entities: Set[str] = set()
        reconciled_institutions: Set[str] = set()
        affair_ids: Set[str] = set()

        for m in all_matches[:3]:
            art = m["article"]
            for e in art["entities"]:
                # Séparer personnalités et institutions
                if e.upper() == e or e in {
                    "CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF",
                    "Préfecture", "Rectorat",
                }:
                    reconciled_institutions.add(e)
                else:
                    reconciled_entities.add(e)
            if art.get("affair_id"):
                affair_ids.add(art["affair_id"])

        # Conserver les entités originales de la transcription pour traçabilité
        original_entities = transcription.get("elected") or transcription.get("entities") or []

        # Mettre à jour la transcription
        transcription.update({
            # Entités réconciliées (source : articles)
            "elected": sorted(reconciled_entities),
            "institutions": sorted(reconciled_institutions),
            "entities": sorted(reconciled_entities | reconciled_institutions),

            # Thème réconcilié (celui de l'article si confiance haute)
            "theme": article["theme"] if match_score > 0.5 else transcription.get("theme", "general"),

            # Affaire liée
            "affair_id": article.get("affair_id") or (
                list(affair_ids)[0] if affair_ids else None
            ),
            "is_affair": article.get("is_affair", False) or transcription.get("is_affair", False),
            "affair_type": article.get("affair_type") or transcription.get("affair_type", "routine"),
            "gravity_score": max(
                article.get("gravity_score", 0),
                transcription.get("gravity_score", 0),
            ),
            "importance_score": max(
                article.get("importance_score", 0),
                transcription.get("importance_score", 0),
            ),

            # Métadonnées de réconciliation
            "_reconciliation": {
                "status": "reconciled",
                "match_score": match_score,
                "matched_article_id": article["_id"],
                "matched_article_title": article["title"],
                "matched_source": article["source"],
                "original_entities": original_entities,
                "reconciled_entities": sorted(reconciled_entities | reconciled_institutions),
                "all_matched_articles": [
                    {"id": m["article"]["_id"], "title": m["article"]["title"], "score": m["score"]}
                    for m in all_matches[:5]
                ],
                "reconciled_at": datetime.utcnow().isoformat(),
            },

            # Articles liés (pour le suivi cross-média)
            "linked_articles": [m["article"]["_id"] for m in all_matches[:5]],
        })

        logger.info(
            f"✅ Transcription réconciliée (score={match_score:.2f}) "
            f"avec article '{article['title'][:60]}...' — "
            f"entités: {sorted(reconciled_entities)}"
        )

        return transcription

    # ============================================================
    # RÉCONCILIATION DES AFFAIRES
    # ============================================================
    def reconcile_affair(self, affair: Dict[str, Any]) -> Dict[str, Any]:
        """
        Réconcilie une affaire en consolidant les entités
        depuis tous les articles et transcriptions liés.
        """
        self.build_article_index()

        affair_id = str(affair.get("_id", ""))
        title = affair.get("title") or affair.get("name") or ""

        if not title:
            return affair

        # Chercher tous les articles liés à cette affaire
        linked_articles = []
        for art in self._article_index:
            if art.get("affair_id") == affair_id:
                linked_articles.append(art)

        # Chercher aussi par contexte (le titre de l'affaire)
        affair_context = {
            "tokens": self._extract_context_tokens(title),
            "theme": affair.get("theme", ""),
            "keywords": set(affair.get("keywords_found") or []),
            "raw_entities": [],
            "date": affair.get("created_at"),
        }

        context_matches = self._find_context_matches(affair_context)

        # Consolider les entités depuis toutes les sources
        all_entities: Counter = Counter()
        all_institutions: Counter = Counter()

        for art in linked_articles:
            for e in art["entities"]:
                if e.upper() == e or e in {
                    "CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF",
                    "Préfecture", "Rectorat",
                }:
                    all_institutions[e] += 1
                else:
                    all_entities[e] += 1

        for m in context_matches:
            for e in m["article"]["entities"]:
                if e.upper() == e or e in {
                    "CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF",
                    "Préfecture", "Rectorat",
                }:
                    all_institutions[e] += 1
                else:
                    all_entities[e] += 1

        # Prendre les entités les plus fréquentes (consensus)
        top_entities = [e for e, _ in all_entities.most_common(10)]
        top_institutions = [e for e, _ in all_institutions.most_common(5)]

        if top_entities or top_institutions:
            affair.update({
                "elected": top_entities,
                "institutions": top_institutions,
                "entities": top_entities + top_institutions,
                "_reconciliation": {
                    "status": "reconciled",
                    "sources_count": len(linked_articles) + len(context_matches),
                    "entity_consensus": dict(all_entities.most_common(10)),
                    "reconciled_at": datetime.utcnow().isoformat(),
                },
            })
            logger.info(
                f"✅ Affaire '{title[:50]}' réconciliée — "
                f"entités consensus: {top_entities}"
            )

        return affair

    # ============================================================
    # BATCH : RÉCONCILIER LES TRANSCRIPTIONS EXISTANTES
    # ============================================================
    def reconcile_recent_transcriptions(
        self, days: int = 3, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Réconcilie en batch toutes les transcriptions des N derniers jours.
        En mode dry_run, ne modifie pas la base.
        """
        if self.db is None:
            return {"error": "No DB connection"}

        self.build_article_index(force=True)

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = {
            "$or": [
                {"captured_at": {"$gte": cutoff.isoformat()}},
                {"date": {"$gte": cutoff.isoformat()}},
                {"created_at": {"$gte": cutoff}},
            ]
        }

        transcriptions = list(self.transcriptions_col.find(query).limit(200))
        logger.info(f"📻 {len(transcriptions)} transcriptions à réconcilier")

        stats = {
            "total": len(transcriptions),
            "reconciled": 0,
            "no_match": 0,
            "skipped": 0,
            "errors": 0,
            "details": [],
        }

        for trans in transcriptions:
            try:
                result = self.reconcile_transcription(dict(trans))
                recon_status = result.get("_reconciliation", {}).get("status", "unknown")

                if recon_status == "reconciled":
                    stats["reconciled"] += 1
                    if not dry_run:
                        # Mettre à jour en base
                        self.transcriptions_col.update_one(
                            {"_id": trans["_id"]},
                            {"$set": {
                                "elected": result.get("elected", []),
                                "institutions": result.get("institutions", []),
                                "entities": result.get("entities", []),
                                "theme": result.get("theme"),
                                "affair_id": result.get("affair_id"),
                                "is_affair": result.get("is_affair"),
                                "affair_type": result.get("affair_type"),
                                "gravity_score": result.get("gravity_score"),
                                "importance_score": result.get("importance_score"),
                                "linked_articles": result.get("linked_articles", []),
                                "_reconciliation": result.get("_reconciliation"),
                            }}
                        )
                    stats["details"].append({
                        "id": str(trans["_id"]),
                        "matched_article": result["_reconciliation"].get("matched_article_title", ""),
                        "score": result["_reconciliation"].get("match_score", 0),
                        "entities": result.get("elected", []),
                    })
                elif recon_status == "no_match":
                    stats["no_match"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(f"❌ Erreur réconciliation transcription {trans.get('_id')}: {e}")
                stats["errors"] += 1

        logger.info(
            f"📊 Réconciliation batch terminée : "
            f"{stats['reconciled']}/{stats['total']} réconciliées, "
            f"{stats['no_match']} sans match, "
            f"{stats['skipped']} ignorées, "
            f"{stats['errors']} erreurs"
        )
        return stats

    def reconcile_recent_affairs(self, days: int = 7, dry_run: bool = False) -> Dict[str, Any]:
        """
        Réconcilie en batch toutes les affaires récentes.
        """
        if self.db is None:
            return {"error": "No DB connection"}

        self.build_article_index(force=True)

        cutoff = datetime.utcnow() - timedelta(days=days)
        query = {
            "$or": [
                {"created_at": {"$gte": cutoff.isoformat()}},
                {"date": {"$gte": cutoff.isoformat()}},
                {"updated_at": {"$gte": cutoff.isoformat()}},
            ]
        }

        affairs = list(self.affairs_col.find(query).limit(100))
        logger.info(f"📁 {len(affairs)} affaires à réconcilier")

        stats = {"total": len(affairs), "reconciled": 0, "unchanged": 0, "errors": 0}

        for affair in affairs:
            try:
                result = self.reconcile_affair(dict(affair))
                recon = result.get("_reconciliation", {})

                if recon.get("status") == "reconciled":
                    stats["reconciled"] += 1
                    if not dry_run:
                        self.affairs_col.update_one(
                            {"_id": affair["_id"]},
                            {"$set": {
                                "elected": result.get("elected", []),
                                "institutions": result.get("institutions", []),
                                "entities": result.get("entities", []),
                                "_reconciliation": recon,
                            }}
                        )
                else:
                    stats["unchanged"] += 1

            except Exception as e:
                logger.error(f"❌ Erreur réconciliation affaire {affair.get('_id')}: {e}")
                stats["errors"] += 1

        logger.info(
            f"📊 Réconciliation affaires : "
            f"{stats['reconciled']}/{stats['total']} réconciliées"
        )
        return stats

    # ============================================================
    # UTILITAIRES
    # ============================================================
    def _extract_context_tokens(self, text: str) -> Set[str]:
        """
        Extrait les mots significatifs d'un texte (minuscules, sans accents, sans stopwords).
        """
        if not text:
            return set()
        # Normaliser
        text = self._strip_accents(text.lower())
        # Extraire les mots de 3+ caractères
        words = re.findall(r"[a-z]{3,}", text)
        # Supprimer les stopwords
        return {w for w in words if w not in STOPWORDS_FR and len(w) >= 3}

    def _extract_raw_names(self, text: str) -> List[str]:
        """
        Extrait les noms potentiels du texte (mots commençant par une majuscule
        qui se suivent, typique des noms propres).
        """
        if not text:
            return []
        # Pattern : séquences de 2+ mots capitalisés
        pattern = r"\b([A-ZÀÂÉÈÊËÏÎÔÙÛÜŸÇ][a-zàâéèêëïîôùûüÿç]+(?:\s+[A-ZÀÂÉÈÊËÏÎÔÙÛÜŸÇ][a-zàâéèêëïîôùûüÿç]+)+)\b"
        matches = re.findall(pattern, text)
        # Filtrer les faux positifs courants
        filtered = []
        noise = {"Le Président", "Le Conseil", "La Région", "Le Département",
                 "La Préfecture", "Le Préfet", "La Mairie", "Le Maire",
                 "Les Abymes", "Pointe Pitre", "Basse Terre", "Belle Eau"}
        for m in matches:
            if m not in noise and len(m) > 4:
                filtered.append(m)
        return filtered

    def _fuzzy_name_match_score(
        self, raw_names: List[str], article_entities: Set[str]
    ) -> float:
        """
        Score de matching flou entre les noms bruts de la transcription
        et les entités normalisées des articles.
        """
        if not raw_names or not article_entities:
            return 0.0

        best_scores = []
        for raw in raw_names:
            raw_norm = self._normalize_name(raw)
            for entity in article_entities:
                entity_norm = self._normalize_name(entity)
                ratio = SequenceMatcher(None, raw_norm, entity_norm).ratio()
                if ratio >= MIN_FUZZY_NAME_RATIO:
                    best_scores.append(ratio)

        if not best_scores:
            return 0.0

        # Moyenne des meilleurs matchs
        return sum(best_scores) / max(len(raw_names), 1)

    def _normalize_name(self, name: str) -> str:
        """Normalise un nom pour comparaison floue."""
        if not name:
            return ""
        name = self._strip_accents(name.lower().strip())
        name = re.sub(r"[^a-z\s]", "", name)
        name = re.sub(r"\s+", " ", name)
        return name

    def _strip_accents(self, text: str) -> str:
        """Supprime les accents."""
        import unicodedata
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

    def _themes_related(self, theme1: str, theme2: str) -> bool:
        """Vérifie si deux thèmes sont proches."""
        related_groups = [
            {"eau_env", "catastrophes_risques"},
            {"politique_institutions", "economie_emploi"},
            {"sante_social", "education"},
            {"securite_justice", "catastrophes_risques"},
            {"energie_transports", "economie_emploi"},
        ]
        for group in related_groups:
            if theme1 in group and theme2 in group:
                return True
        return False

    def _temporal_proximity(
        self, date1: Any, date2: Any
    ) -> float:
        """Score de proximité temporelle (1.0 = même jour, 0.0 = > 3 jours)."""
        try:
            d1 = self._parse_date(date1)
            d2 = self._parse_date(date2)
            if d1 is None or d2 is None:
                return 0.5  # Pas de date → score neutre

            delta_hours = abs((d1 - d2).total_seconds()) / 3600
            if delta_hours <= 6:
                return 1.0
            elif delta_hours <= 24:
                return 0.8
            elif delta_hours <= 48:
                return 0.5
            elif delta_hours <= 72:
                return 0.3
            else:
                return 0.0
        except Exception:
            return 0.5

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """Parse une date en datetime, quel que soit le format."""
        if date_val is None:
            return None
        if isinstance(date_val, datetime):
            return date_val
        if isinstance(date_val, str):
            for fmt in [
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]:
                try:
                    return datetime.strptime(date_val[:len(fmt) + 2], fmt)
                except (ValueError, IndexError):
                    continue
        return None

    def _log_reconciliation(
        self, transcription: Dict, best_match: Dict, all_matches: List
    ):
        """Logue la réconciliation dans une collection dédiée."""
        if self.db is None:
            return
        try:
            self.reconciliation_log.insert_one({
                "transcription_id": str(transcription.get("_id", "")),
                "matched_article_id": best_match["article"]["_id"],
                "matched_article_title": best_match["article"]["title"],
                "match_score": best_match["score"],
                "total_matches": len(all_matches),
                "reconciled_entities": transcription.get("elected", []),
                "original_entities": transcription.get("_reconciliation", {}).get("original_entities", []),
                "timestamp": datetime.utcnow(),
            })
        except Exception as e:
            logger.debug(f"Log réconciliation échoué: {e}")

    # ============================================================
    # API PUBLIQUE : SANTÉ DU SERVICE
    # ============================================================
    def health_check(self) -> Dict[str, Any]:
        """État du service de réconciliation."""
        return {
            "status": "operational" if self.db is not None else "degraded",
            "article_index_size": len(self._article_index),
            "index_age_minutes": (
                round((datetime.utcnow() - self._index_built_at).total_seconds() / 60, 1)
                if self._index_built_at else None
            ),
            "context_window_days": CONTEXT_WINDOW_DAYS,
            "min_context_score": MIN_CONTEXT_SCORE,
        }


# ============================================================
# INSTANCE SINGLETON
# ============================================================
_service: Optional[EntityReconciliationService] = None


def get_reconciliation_service(db=None) -> EntityReconciliationService:
    """Retourne l'instance singleton du service."""
    global _service
    if _service is None:
        _service = EntityReconciliationService(db=db)
    return _service
