"""Tests pytest qui exposent l'eval harness à la CI / au dev.

Pour l'instant : seuils volontairement bas (le dataset est minuscule, 5 paires).
À mesure que le dataset grandit, durcir les seuils minimum_f1.
"""

from __future__ import annotations

import pytest

from tests.eval.affaires.runner import evaluate


@pytest.mark.eval
def test_baseline_jaccard_tokens_runs() -> None:
    """Le runner tourne et produit des métriques cohérentes."""
    r = evaluate("jaccard_tokens")
    assert r.n > 0, "fixtures.jsonl vide"
    assert 0.0 <= r.metrics.precision <= 1.0
    assert 0.0 <= r.metrics.recall <= 1.0
    assert 0.0 <= r.metrics.f1 <= 1.0


@pytest.mark.eval
def test_baseline_jaccard_plus_entities_bat_jaccard_seul() -> None:
    """Ajouter les entités doit améliorer (ou au minimum ne pas dégrader) le F1.

    Si cette assertion casse, c'est probablement le signe que :
    - le dataset est trop petit et bruité (à étoffer),
    - ou les entités sont mal exploitées dans la baseline.
    """
    base = evaluate("jaccard_tokens")
    enriched = evaluate("jaccard_plus_entities")
    assert enriched.metrics.f1 >= base.metrics.f1 - 0.05, (
        f"Régression : jaccard_tokens F1={base.metrics.f1:.2f}, "
        f"jaccard_plus_entities F1={enriched.metrics.f1:.2f}"
    )


@pytest.mark.eval
def test_dataset_has_both_polarities() -> None:
    """Dataset doit avoir au moins une paire positive et une négative."""
    r = evaluate("jaccard_tokens")
    assert r.n_positive >= 1, "Aucune paire should_merge=true dans fixtures"
    assert r.n_negative >= 1, "Aucune paire should_merge=false dans fixtures"
