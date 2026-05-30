# backend/embedding_service.py
"""
Service d'embeddings sémantiques pour la Veille Média Guadeloupe.

Utilise OpenAI text-embedding-3-small pour générer des vecteurs 1536D
qui permettent le clustering par similarité sémantique.

Coût estimé : ~$0.02/million tokens → quasi gratuit pour notre volume.
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("embedding_service")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

_client = None


def _get_client():
    """Initialise le client OpenAI (lazy loading)."""
    global _client
    if _client is not None:
        return _client
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info(f"✅ Embedding client initialisé ({EMBEDDING_MODEL})")
        return _client
    except Exception as e:
        logger.error(f"❌ Impossible d'initialiser le client embedding: {e}")
        return None


def is_available() -> bool:
    """Vérifie si le service d'embeddings est disponible."""
    return bool(OPENAI_API_KEY and _get_client())


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Génère un embedding pour un texte donné.
    Retourne un vecteur de 1536 dimensions ou None si échec.
    """
    client = _get_client()
    if not client:
        return None

    if not text or len(text.strip()) < 10:
        return None

    try:
        # Limiter à ~8000 tokens (~32000 chars) pour rester dans les limites
        text = text[:32000]
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"⚠️ Erreur embedding: {e}")
        return None


def get_embeddings_batch(texts: List[str], batch_size: int = 50) -> List[Optional[List[float]]]:
    """
    Génère des embeddings pour un lot de textes.
    Retourne une liste de vecteurs (None pour les échecs).
    """
    client = _get_client()
    if not client:
        return [None] * len(texts)

    results = [None] * len(texts)

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # Nettoyer les textes vides
        clean_batch = []
        indices = []
        for j, text in enumerate(batch):
            if text and len(text.strip()) >= 10:
                clean_batch.append(text[:32000])
                indices.append(i + j)

        if not clean_batch:
            continue

        try:
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=clean_batch,
            )
            for k, emb_data in enumerate(resp.data):
                results[indices[k]] = emb_data.embedding
        except Exception as e:
            logger.warning(f"⚠️ Erreur batch embedding ({len(clean_batch)} textes): {e}")

    return results


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    if not vec_a or not vec_b:
        return 0.0
    a = np.array(vec_a)
    b = np.array(vec_b)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def cosine_similarity_matrix(vectors: List[List[float]]) -> List[List[float]]:
    """
    Calcule la matrice de similarité cosinus NxN pour une liste de vecteurs.
    Retourne une matrice NxN de similarités.
    """
    if not vectors:
        return []
    mat = np.array(vectors)
    # Normaliser
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1  # Éviter division par zéro
    mat_norm = mat / norms
    # Produit scalaire = similarité cosinus sur vecteurs normalisés
    sim_matrix = np.dot(mat_norm, mat_norm.T)
    return sim_matrix.tolist()


def build_text_for_embedding(item: Dict[str, Any], source_type: str = "article") -> str:
    """
    Construit le texte à vectoriser pour un item (article, transcription, post social).
    Priorise : titre + résumé IA + entités + thème
    """
    parts = []

    title = item.get("title", "")
    if title:
        parts.append(f"Titre: {title}")

    # Résumé IA (plus discriminant que le contenu brut)
    ai_summary = item.get("ai_summary", "")
    if ai_summary:
        parts.append(f"Résumé: {ai_summary}")

    # Événement structuré si disponible
    event = item.get("event_structured", {})
    if event:
        subj = event.get("subject", "")
        action = event.get("action", "")
        obj = event.get("object", "")
        if subj and action:
            parts.append(f"Événement: {subj} {action} {obj}".strip())

    # Entités (importent pour la discrimination)
    elected = item.get("elected", [])
    institutions = item.get("institutions", [])
    if elected:
        parts.append(f"Personnalités: {', '.join(elected)}")
    if institutions:
        parts.append(f"Institutions: {', '.join(institutions)}")

    # Thème
    theme = item.get("theme", "")
    if theme and theme != "general":
        parts.append(f"Thème: {theme}")

    # Si pas de résumé, utiliser un extrait du contenu
    if not ai_summary:
        content = item.get("content", "") or item.get("text", "")
        if content:
            # Premiers 500 mots max
            words = content.split()[:500]
            parts.append(f"Contenu: {' '.join(words)}")

    return "\n".join(parts)


def enrich_item_with_embedding(
    item: Dict[str, Any],
    source_type: str = "article",
    db_collection=None,
) -> Optional[List[float]]:
    """
    Génère et stocke l'embedding pour un item.
    Met à jour l'item en base si db_collection est fourni.
    Retourne le vecteur ou None.
    """
    text = build_text_for_embedding(item, source_type)
    if not text:
        return None

    embedding = get_embedding(text)
    if embedding is None:
        return None

    if db_collection is not None:
        try:
            db_collection.update_one(
                {"_id": item["_id"]},
                {"$set": {
                    "embedding": embedding,
                    "embedding_model": EMBEDDING_MODEL,
                    "embedding_at": datetime.utcnow().isoformat(),
                }}
            )
        except Exception as e:
            logger.warning(f"⚠️ Sauvegarde embedding en base: {e}")

    return embedding


def enrich_batch_with_embeddings(
    items: List[Dict[str, Any]],
    source_type: str = "article",
    db_collection=None,
) -> int:
    """
    Génère les embeddings pour un lot d'items et les stocke en base.
    Retourne le nombre d'items enrichis.
    """
    if not items:
        return 0

    # Construire les textes
    texts = [build_text_for_embedding(item, source_type) for item in items]

    # Générer les embeddings en batch
    embeddings = get_embeddings_batch(texts)

    enriched = 0
    for i, (item, emb) in enumerate(zip(items, embeddings)):
        if emb is None:
            continue

        if db_collection is not None:
            try:
                db_collection.update_one(
                    {"_id": item["_id"]},
                    {"$set": {
                        "embedding": emb,
                        "embedding_model": EMBEDDING_MODEL,
                        "embedding_at": datetime.utcnow().isoformat(),
                    }}
                )
                enriched += 1
            except Exception as e:
                logger.warning(f"⚠️ Sauvegarde embedding batch: {e}")
        else:
            item["embedding"] = emb
            enriched += 1

    logger.info(f"🧮 Embeddings: {enriched}/{len(items)} items enrichis")
    return enriched
