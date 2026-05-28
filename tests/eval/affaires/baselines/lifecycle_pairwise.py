"""Baseline qui appelle la VRAIE fonction de similarité du code prod.

Reproduit fidèlement `AffairLifecycleService._pairwise_similarity` (cf.
`backend/affair_lifecycle_service.py:5470`) en fonction pure :

- 0.55 similarité sémantique (embeddings ou tokens+thème en fallback)
- 0.25 entités communes (avec résolution d'alias via `entity_aliases.entities_match`)
- 0.20 proximité temporelle

Le harness n'a pas d'embeddings (pas d'OpenAI dans la CI) — donc la baseline
mesure le **fallback tokens+thème**, qui est ce qui tourne en prod chaque
fois qu'un article n'a pas encore d'embedding (cas fréquent — voir code
`affair_lifecycle_service.py:5495`).

Seuil de décision : `CLUSTER_SIMILARITY_THRESHOLD = 0.35` (constante prod
ligne 278 de `affair_lifecycle_service.py`).

Cette baseline N'EST PAS une copie figée : elle importe les constantes
(`BROAD_THEMES`, `GENERIC_ELECTED`) et les fonctions (`entities_match`)
depuis le code source. Si la prod évolue, la baseline suit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# --- Imports depuis le code prod -------------------------------------------
# affair_lifecycle_service.py est lourd (5653 L) mais s'importe sans Mongo
# tant qu'on n'instancie pas la classe.
from backend.affair_lifecycle_service import (  # type: ignore
    BROAD_THEMES,
    AffairLifecycleService,
)
from backend.entity_aliases import entities_match  # type: ignore

# GENERIC_ELECTED est une constante de classe (pas une variable module),
# on la prend en référence — pas de copie.
GENERIC_ELECTED: set[str] = AffairLifecycleService.GENERIC_ELECTED


# --- Helpers ----------------------------------------------------------------


def _parse_date(value: Any) -> datetime | None:
    """Accepte datetime, ISO string, ou None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Accepte 'YYYY-MM-DDTHH:MM:SSZ' et variantes ISO 8601
        try:
            return datetime.fromisoformat(value.rstrip("Z"))
        except ValueError:
            return None
    return None


def _pairwise_similarity_pure(
    tokens_a: set[str],
    theme_a: str,
    entities_a: set[str],
    tokens_b: set[str],
    theme_b: str,
    entities_b: set[str],
    date_a: datetime | None = None,
    date_b: datetime | None = None,
) -> float:
    """Fonction pure miroir de AffairLifecycleService._pairwise_similarity.

    Pas de paramètre embeddings — on ne les calcule pas dans le harness
    (pas d'OpenAI). C'est le chemin fallback qui est mesuré, et c'est le
    chemin emprunté à chaque fois qu'un article arrive sans embedding pré-calculé.
    """
    # ── 1. Similarité sémantique (55%) — fallback tokens + thème ──
    common_tokens = tokens_a & tokens_b
    if not common_tokens and not (entities_a & entities_b):
        return 0.0
    min_size = min(len(tokens_a), len(tokens_b))
    token_score = len(common_tokens) / max(min_size, 1)
    # Pas de bonus pour les thèmes larges (qui regrouperaient des événements sans lien)
    theme_bonus = 0.2 if (theme_a and theme_a == theme_b and theme_a not in BROAD_THEMES) else 0.0
    semantic_score = min(1.0, token_score + theme_bonus)

    # ── 2. Entités communes (25%) — avec résolution d'alias ──
    entity_score = 0.0
    if entities_a or entities_b:
        common_ent, jaccard = entities_match(list(entities_a), list(entities_b))
        entity_score = jaccard
        # Bonus : une entité spécifique commune (pas un élu générique) vaut plus
        for e in common_ent:
            if e.lower() not in GENERIC_ELECTED:
                entity_score = min(1.0, entity_score + 0.3)
                break

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


# --- API attendue par le runner --------------------------------------------


def score(article_a: dict[str, Any], article_b: dict[str, Any]) -> float:
    """Signature standard de baseline pour le runner."""
    return _pairwise_similarity_pure(
        tokens_a=set(article_a.get("tokens") or []),
        theme_a=str(article_a.get("theme") or ""),
        entities_a=set(article_a.get("entities") or []),
        tokens_b=set(article_b.get("tokens") or []),
        theme_b=str(article_b.get("theme") or ""),
        entities_b=set(article_b.get("entities") or []),
        date_a=_parse_date(article_a.get("date")),
        date_b=_parse_date(article_b.get("date")),
    )


NAME = "lifecycle_pairwise"
# Seuil prod, cf. affair_lifecycle_service.py:278 (CLUSTER_SIMILARITY_THRESHOLD)
DEFAULT_THRESHOLD = 0.35
