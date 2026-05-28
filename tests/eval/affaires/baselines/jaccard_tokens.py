"""Baseline triviale : Jaccard sur les tokens.

But : poser une référence basse. Toute baseline plus sérieuse (similarité
hybride du lifecycle, embeddings + entités, etc.) doit faire mieux que ça.
Sinon il y a un problème.
"""

from __future__ import annotations

from typing import Any


def score(article_a: dict[str, Any], article_b: dict[str, Any]) -> float:
    """Score Jaccard sur les tokens. Renvoie 0..1."""
    tokens_a = set(article_a.get("tokens") or [])
    tokens_b = set(article_b.get("tokens") or [])
    if not tokens_a and not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


# Le runner cherche ces deux variables dans chaque baseline.
NAME = "jaccard_tokens"
DEFAULT_THRESHOLD = 0.30
