"""Baseline intermédiaire : Jaccard tokens + bonus entités communes.

Sert d'étape entre la baseline triviale et la similarité hybride réelle
du lifecycle. Permet de mesurer combien d'F1 vient juste des entités.
"""

from __future__ import annotations

from typing import Any


def score(article_a: dict[str, Any], article_b: dict[str, Any]) -> float:
    tokens_a = set(article_a.get("tokens") or [])
    tokens_b = set(article_b.get("tokens") or [])
    ent_a = set(article_a.get("entities") or [])
    ent_b = set(article_b.get("entities") or [])

    token_score = 0.0
    if tokens_a or tokens_b:
        union = tokens_a | tokens_b
        token_score = len(tokens_a & tokens_b) / len(union) if union else 0.0

    entity_score = 0.0
    if ent_a or ent_b:
        union = ent_a | ent_b
        entity_score = len(ent_a & ent_b) / len(union) if union else 0.0

    # Pondération arbitraire à ajuster
    return 0.6 * token_score + 0.4 * entity_score


NAME = "jaccard_plus_entities"
DEFAULT_THRESHOLD = 0.30
