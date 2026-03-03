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
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from pymongo import MongoClient, DESCENDING
from bson import ObjectId

logger = logging.getLogger("affair_lifecycle")

# ============================================================
# CONFIGURATION
# ============================================================

# --- Clustering ---
CLUSTER_WINDOW_HOURS = 72              # Fenêtre de clustering (3 jours)
MIN_CLUSTER_ITEMS = 2                  # Minimum d'items pour former un cluster
CLUSTER_SIMILARITY_THRESHOLD = 0.30    # Seuil de similarité contextuelle
CLUSTER_MERGE_THRESHOLD = 0.50         # Seuil pour fusionner deux clusters

# --- Promotion en affaire ---
PROMOTION_MIN_SOURCES = 1              # Au moins 1 source (assoupli, était 2)
PROMOTION_MIN_MEDIA_TYPES = 1          # Au moins 1 type de média (article OU transcription)
PROMOTION_MIN_GRAVITY = 0.40           # Gravité minimum du cluster (assoupli, était 0.50)
PROMOTION_MIN_ITEMS = 1                # Minimum d'items (assoupli, était 2)

# --- Cycle de vie ---
AFFAIR_ACTIVE_DAYS = 7                 # Durée de vie active (1 semaine)
AFFAIR_STALE_DAYS = 5                  # Jours sans activité → statut "stale"
MAX_ACTIVE_AFFAIRS = 20                # Maximum d'affaires actives simultanées

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
        """Crée les index nécessaires."""
        try:
            self.candidates.create_index([("created_at", DESCENDING)])
            self.candidates.create_index("cluster_id")
            self.candidates.create_index("source_type")
            self.clusters.create_index([("created_at", DESCENDING)])
            self.clusters.create_index("status")
            self.affairs.create_index([("created_at", DESCENDING)])
            self.affairs.create_index("status")
            self.affairs.create_index([("last_activity", DESCENDING)])
            self.timeline.create_index("affair_id")
            self.timeline.create_index([("timestamp", DESCENDING)])
        except Exception as e:
            logger.warning(f"⚠️ Index creation: {e}")

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
            score = self._candidate_cluster_similarity(
                cand_tokens, cand_theme, cand_entities, cluster,
                cand_date=cand_date,
            )
            if score > best_score and score >= CLUSTER_SIMILARITY_THRESHOLD:
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
                if sim >= CLUSTER_SIMILARITY_THRESHOLD:
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
                "affair_type": self._classify_affair_type(cluster),
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
            return affair_id

        except Exception as e:
            logger.error(f"❌ Promotion: {e}")
            return None

    def _find_similar_affair(self, cluster: Dict) -> Optional[Dict]:
        """Cherche une affaire existante similaire au cluster."""
        cluster_entities = set(cluster.get("all_entities", []))
        cluster_tokens = set(cluster.get("all_tokens", []))

        recent_affairs = self.affairs.find({
            "status": "active",
            "created_at": {"$gte": datetime.utcnow() - timedelta(days=AFFAIR_ACTIVE_DAYS)},
        })

        best = None
        best_score = 0

        for affair in recent_affairs:
            aff_entities = set(affair.get("entities", []))
            aff_tokens = set(affair.get("keywords", []))

            # Entités communes
            common_entities = cluster_entities & aff_entities
            entity_score = len(common_entities) / max(len(cluster_entities | aff_entities), 1)

            # Tokens communs
            common_tokens = cluster_tokens & aff_tokens
            token_score = len(common_tokens) / max(min(len(cluster_tokens), len(aff_tokens)), 1)

            combined = entity_score * 0.6 + token_score * 0.4
            if combined > best_score and combined >= 0.4:
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

        # Presse (articles)
        article_ids = affair.get("articles", [])
        if article_ids:
            try:
                obj_ids = [ObjectId(a) for a in article_ids if a and len(a) == 24]
                docs = list(self.articles.find({"_id": {"$in": obj_ids}})) if obj_ids else []
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
                obj_ids = [ObjectId(t) for t in trans_ids if t and len(t) == 24]
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

        # Réseaux sociaux
        social_ids = affair.get("social_posts", [])
        if social_ids:
            try:
                obj_ids = [ObjectId(s) for s in social_ids if s and len(s) == 24]
                docs = list(self.social.find({"_id": {"$in": obj_ids}})) if obj_ids else []
                for doc in docs:
                    likes = doc.get("likes", 0) or doc.get("reactions", 0)
                    shares = doc.get("shares", 0) or doc.get("retweets", 0)
                    comments = doc.get("comments_count", 0) or doc.get("replies", 0)
                    engagement = min(1.0, (likes + shares * 3 + comments * 2) / 500)
                    importance = doc.get("relevance_score", 0.3)
                    weight = 0.5  # Poids moyen RS

                    bnp = importance * max(engagement, 0.1) * weight
                    canal_data["reseaux_sociaux"]["score_sum"] += bnp
                    canal_data["reseaux_sociaux"]["weight_sum"] += weight
                    canal_data["reseaux_sociaux"]["count"] += 1
            except Exception as e:
                logger.debug(f"BMG social: {e}")

        # Calculer BNP par canal
        bnp_by_canal = {}
        for canal, data in canal_data.items():
            if data["weight_sum"] > 0:
                bnp_by_canal[canal] = data["score_sum"] / data["weight_sum"]
            else:
                bnp_by_canal[canal] = 0

        # BMG global
        bmg = sum(bnp_by_canal.get(c, 0) * w for c, w in CANAL_WEIGHTS.items())

        # Bonus multi-canal : si l'affaire est présente sur 2+ canaux, boost
        active_canals = sum(1 for d in canal_data.values() if d["count"] > 0)
        if active_canals >= 3:
            bmg *= 1.15
        elif active_canals >= 2:
            bmg *= 1.08
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

            if days_inactive >= AFFAIR_ACTIVE_DAYS:
                # Archiver
                self.affairs.update_one(
                    {"_id": affair["_id"]},
                    {"$set": {"status": "archived", "archived_at": now}}
                )
                self.timeline.insert_one({
                    "affair_id": affair_id,
                    "event": "archived",
                    "details": {"days_inactive": days_inactive},
                    "timestamp": now,
                })
                stats["archived"] += 1

            elif days_inactive >= AFFAIR_STALE_DAYS:
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

                update_set = {
                    "bmg": bmg["bmg"],
                    "bmg_details": bmg,
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
        """
        if self.db is None:
            return {"error": "no_db"}

        logger.info("=" * 50)
        logger.info("🔄 CYCLE SIMPLIFIÉ (créer → consolider)")
        logger.info("=" * 50)

        now = datetime.utcnow()
        cutoff_3d = (now - timedelta(days=3)).isoformat()
        stats = {
            "method": "simple_cycle",
            "created": 0,
            "merged": 0,
            "consolidated": 0,
            "radio_linked": 0,
        }

        # ── ÉTAPE 1 : Récupérer les articles enrichis non traités ──
        unprocessed = list(self.articles.find({
            "scraped_at": {"$gte": cutoff_3d},
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
            ],
        }).sort("gravity_score", -1).limit(60))

        # ── DIAGNOSTIC : état de la base ──
        total_articles = self.articles.count_documents({})
        total_enriched = self.articles.count_documents({"_analysis_method": {"$exists": True}})
        total_processed = self.articles.count_documents({"_affair_processed": True})
        total_affairs = self.affairs.count_documents({})
        active_count = self.affairs.count_documents({"status": "active"})
        logger.info(f"📊 DB: {total_articles} articles total, {total_enriched} enrichis, "
                     f"{total_processed} déjà traités (affaires), "
                     f"{total_affairs} affaires ({active_count} actives)")
        logger.info(f"📰 {len(unprocessed)} articles non traités trouvés (gravity>=0.15, enrichis, 3j)")

        if len(unprocessed) == 0 and total_enriched > 0:
            # Diagnostic : pourquoi aucun article non traité ?
            recent_enriched = self.articles.count_documents({
                "scraped_at": {"$gte": cutoff_3d},
                "_analysis_method": {"$exists": True},
            })
            recent_not_processed = self.articles.count_documents({
                "scraped_at": {"$gte": cutoff_3d},
                "_analysis_method": {"$exists": True},
                "$or": [
                    {"_affair_processed": {"$exists": False}},
                    {"_affair_processed": False},
                ],
            })
            logger.warning(f"⚠️ Diagnostic 0 articles: {recent_enriched} enrichis en 3j, "
                          f"{recent_not_processed} non traités parmi eux")
            # Examiner un exemple
            sample = self.articles.find_one({
                "scraped_at": {"$gte": cutoff_3d},
                "_analysis_method": {"$exists": True},
            })
            if sample:
                logger.warning(f"   Exemple: scraped_at={sample.get('scraped_at')} "
                              f"(type={type(sample.get('scraped_at')).__name__}), "
                              f"_affair_processed={sample.get('_affair_processed', 'ABSENT')}, "
                              f"_analysis_method={sample.get('_analysis_method')}")

        # Charger les affaires actives
        active_affairs = list(self.affairs.find({"status": "active"}))

        # ── ÉTAPE 2 : Pour chaque article → créer ou fusionner ──
        ignored_count = 0
        for art in unprocessed:
            art_id = str(art["_id"])
            gravity = art.get("gravity_score", 0)

            # Ignorer seulement les contenus vraiment anodins
            if gravity < 0.15:
                self.articles.update_one(
                    {"_id": art["_id"]},
                    {"$set": {"_affair_processed": True, "_affair_ignored": True}}
                )
                ignored_count += 1
                logger.debug(f"   ⏭️ Ignoré (gravity={gravity:.2f}): {art.get('title', '?')[:60]}")
                continue

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

            # Chercher une affaire existante similaire
            best_match = None
            best_score = 0

            for affair in active_affairs:
                score = self._match_score(
                    art_elected, art_institutions, art_entities,
                    art_theme, art_title_words, affair
                )
                if score > best_score:
                    best_score = score
                    best_match = affair

            # Log de la décision de matching
            logger.info(f"   📄 Art: '{art.get('title', '?')[:60]}' | gravity={gravity:.2f} "
                        f"| élus={list(art_elected)[:3]} | instit={list(art_institutions)[:3]} "
                        f"| thème={art_theme}")
            if best_match:
                logger.info(f"      → Meilleur match: '{best_match.get('title', '?')[:50]}' "
                            f"(score={best_score}, seuil=3)")
            else:
                logger.info(f"      → Aucun match trouvé parmi {len(active_affairs)} affaires actives → CRÉATION")

            if best_match and best_score >= 3:
                # Fusionner avec l'affaire existante
                logger.info(f"      ✅ FUSION avec affaire existante (score={best_score})")
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
                new_affair = {
                    "title": title,
                    "description": (art.get("ai_summary", "") or "")[:300],
                    "primary_entity": list(art_elected)[0] if art_elected else None,
                    "entities": list(art_entities)[:20],
                    "elected": list(art_elected)[:10],
                    "institutions": list(art_institutions)[:10],
                    "keywords": art.get("keywords_found", []) or [],
                    "theme": art_theme,
                    "gravity_score": round(max(gravity, 0.3), 3),
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
                    "bmg": 0, "bmg_details": {}, "bmg_history": [],
                    "ai_managed": False,
                    "_creation_method": "simple_cycle",
                }
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
                logger.info(f"🆕 Affaire: '{title[:50]}' (gravity={gravity:.2f}, source={art.get('source', '')})")

        # ── ÉTAPE 3 : Consolidation — chercher d'autres sources 24h ──
        stats["consolidated"] = self._consolidate_affairs_24h(active_affairs)

        # ── ÉTAPE 4 : Lier les transcriptions radio ──
        stats["radio_linked"] = self._link_radio_to_affairs(active_affairs)

        # ── ÉTAPE 5 : Enforcer la limite ──
        self._enforce_max_affairs()

        # ── ÉTAPE 6 : Recalculer BMG ──
        self._recalculate_active_bmg()

        # ── ÉTAPE 7 : Lifecycle ──
        stats["lifecycle"] = self.update_affair_lifecycle()

        logger.info(
            f"✅ Cycle simplifié: {stats['created']} créées, {stats['merged']} fusionnées, "
            f"{stats['consolidated']} consolidées, {stats['radio_linked']} radio liées, "
            f"{ignored_count} ignorées (gravity<0.15)"
        )
        logger.info(f"📊 Bilan: {active_count + stats['created']} affaires actives maintenant")
        return stats

    def _match_score(
        self, art_elected: set, art_institutions: set, art_entities: set,
        art_theme: str, art_title_words: set, affair: dict
    ) -> int:
        """Calcule un score de similarité entre un article et une affaire."""
        aff_elected = set(
            e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
        )
        aff_institutions = set(
            e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
        )
        aff_entities = aff_elected | aff_institutions
        aff_theme = affair.get("theme", "general")
        aff_title_words = set(
            w.lower() for w in (affair.get("title", "").split()) if len(w) > 4
        )

        common_elected = art_elected & aff_elected
        common_institutions = art_institutions & aff_institutions
        common_entities = art_entities & aff_entities
        same_theme = (art_theme == aff_theme and art_theme not in ("", "general"))
        common_title = art_title_words & aff_title_words

        score = 0
        score += len(common_elected) * 4      # Personne en commun = signal fort
        score += len(common_institutions) * 2  # Institution en commun
        score += (2 if same_theme else 0)      # Même thème
        score += min(len(common_title), 3)     # Mots du titre en commun (max 3 pts)

        if score >= 2:  # Log uniquement les matchs significatifs
            logger.debug(
                f"      🔍 Score={score} vs '{affair.get('title', '?')[:40]}': "
                f"élus={list(common_elected)}, instit={list(common_institutions)}, "
                f"thème={'✓' if same_theme else '✗'} ({art_theme}), "
                f"mots_titre={list(common_title)[:5]}"
            )
        return score

    def _consolidate_affairs_24h(self, active_affairs: list) -> int:
        """Cherche dans les 24h si des articles non traités correspondent
        à des affaires récemment créées. Consolide multi-source."""
        cutoff_24h = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        now = datetime.utcnow()
        consolidated = 0

        # Articles des 24h, même ceux déjà "ignorés" avec peu de tentatives
        candidates = list(self.articles.find({
            "scraped_at": {"$gte": cutoff_24h},
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
                {"_affair_ignored": True, "_affair_attempts": {"$lt": 3}},
            ],
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

            if best_match and best_score >= 3:
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

    def _link_radio_to_affairs(self, active_affairs: list) -> int:
        """Lie les transcriptions radio récentes aux affaires par entités."""
        cutoff = (datetime.utcnow() - timedelta(days=3)).isoformat()
        now = datetime.utcnow()
        linked = 0

        transcriptions = list(self.transcriptions.find({
            "captured_at": {"$gte": cutoff},
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

            for affair in active_affairs:
                aff_entities = set(
                    e.lower().strip() for e in (affair.get("elected", []) or []) if e and len(e) > 3
                ) | set(
                    e.lower().strip() for e in (affair.get("institutions", []) or []) if e and len(e) > 3
                )
                common = trans_entities & aff_entities
                if len(common) >= 1:
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

        new_articles_raw = list(
            self.articles.find({
                "_analysis_method": {"$exists": True},
                "scraped_at": {"$gte": cutoff.isoformat()},
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
                    "captured_at": {"$gte": cutoff.isoformat()},
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

                new_affair = {
                    "title": new_title[:200],
                    "description": f"Affaire créée par IA: {assignment.get('reason', '')}",
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
        # On incrémente un compteur de tentatives. Après 3 tentatives, on les marque processed.
        for ign_idx in ai_result.get("ignored_articles", []):
            real_idx = ign_idx - 1
            if 0 <= real_idx < len(all_items_for_ai):
                ignored_item = all_items_for_ai[real_idx]
                is_radio = ignored_item.get("_is_radio_topic", False)
                col = self.transcriptions if is_radio else self.articles
                doc = col.find_one({"_id": ignored_item["_id"]})
                attempts = (doc.get("_affair_attempts", 0) if doc else 0) + 1
                if attempts >= 3:
                    # 3 tentatives : on abandonne
                    col.update_one(
                        {"_id": ignored_item["_id"]},
                        {"$set": {"_affair_processed": True, "_affair_ignored": True,
                                  "_affair_attempts": attempts}}
                    )
                else:
                    # Pas encore 3 tentatives : laisser une chance au prochain cycle
                    col.update_one(
                        {"_id": ignored_item["_id"]},
                        {"$set": {"_affair_ignored": True, "_affair_attempts": attempts},
                         "$unset": {"_affair_processed": ""}}
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

    def _recalculate_active_bmg(self):
        """Recalcule le BMG de toutes les affaires actives."""
        active = list(self.affairs.find({"status": "active"}))
        for aff in active:
            try:
                bmg = self.calculate_bmg(aff)
                self.affairs.update_one(
                    {"_id": aff["_id"]},
                    {
                        "$set": {"bmg": bmg["bmg"], "bmg_details": bmg},
                        "$push": {"bmg_history": {
                            "$each": [{"bmg": bmg["bmg"], "at": datetime.utcnow().isoformat()}],
                            "$slice": -30,
                        }},
                    }
                )
            except Exception as e:
                logger.debug(f"BMG recalc: {e}")

    def _reaffiliate_orphans(self) -> int:
        """Ré-essaye de lier les articles orphelins récents aux affaires actives.
        Utilise un matching plus souple : 1 entité spécifique (personne) suffit,
        ou 1 entité + même thème."""
        cutoff = (datetime.utcnow() - timedelta(days=5)).isoformat()

        orphans = list(self.articles.find({
            "scraped_at": {"$gte": cutoff},
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
            ],
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

                # Score de match
                score = 0
                # 1 personne en commun = fort signal
                if common_elected:
                    score += len(common_elected) * 3
                # Institutions en commun
                score += len(common - common_elected) * 1
                # Bonus même thème
                if art_theme == aff_theme and art_theme != "general":
                    score += 2

                # Seuil : au moins 3 points (1 personne, ou 1 institution + même thème, etc.)
                if score >= 3 and score > best_score:
                    best_score = score
                    best_match = affair

            if best_match:
                art_id = str(art["_id"])
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

        cutoff = (datetime.utcnow() - timedelta(days=3)).isoformat()
        now = datetime.utcnow()

        # Articles enrichis non traités avec gravité >= 0.35
        unprocessed = list(self.articles.find({
            "scraped_at": {"$gte": cutoff},
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
            ],
            "gravity_score": {"$gte": 0.35},
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
                same_theme = (art_theme == affair.get("theme", "") and art_theme not in ("", "general"))

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
                new_affair = {
                    "title": title,
                    "description": art.get("ai_summary", "")[:300] or f"Affaire créée automatiquement depuis: {title}",
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
    ) -> float:
        """Similarité entre deux ensembles de tokens/thème/entités,
        avec prise en compte de la proximité temporelle.

        Même jour  → bonus +0.10 (un "accident" le même jour = probablement le même)
        1 jour     → bonus +0.05
        2+ jours   → pénalité progressive (2 "accidents" à 3j d'écart = probablement différents)
        """
        # Tokens communs (Jaccard)
        common_tokens = tokens_a & tokens_b
        if not common_tokens:
            return 0.0
        min_size = min(len(tokens_a), len(tokens_b))
        token_score = len(common_tokens) / max(min_size, 1)

        # Thème
        theme_score = 1.0 if (theme_a and theme_a == theme_b) else 0.0

        # Entités communes
        common_entities = entities_a & entities_b
        entity_score = len(common_entities) / max(len(entities_a | entities_b), 1) if (entities_a or entities_b) else 0

        base_score = token_score * 0.40 + theme_score * 0.20 + entity_score * 0.30

        # Proximité temporelle (10% du score)
        temporal_score = 0.5  # Défaut si pas de dates
        if date_a and date_b:
            try:
                delta_hours = abs((date_a - date_b).total_seconds()) / 3600
                if delta_hours <= 12:
                    temporal_score = 1.0    # Même demi-journée
                elif delta_hours <= 24:
                    temporal_score = 0.8    # Même jour
                elif delta_hours <= 48:
                    temporal_score = 0.5    # Lendemain
                else:
                    temporal_score = 0.2    # Plus vieux = probablement différent
            except (TypeError, ValueError):
                temporal_score = 0.5

        return base_score + temporal_score * 0.10

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

    def _classify_affair_type(self, cluster: Dict) -> str:
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
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            for fmt in ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(val[:len(fmt)+2], fmt)
                except (ValueError, IndexError):
                    continue
        return None

    # ============================================================
    # SANTÉ
    # ============================================================
    def health_check(self) -> Dict[str, Any]:
        if self.db is None:
            return {"status": "down"}

        try:
            return {
                "status": "operational",
                "candidates_total": self.candidates.count_documents({}),
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
