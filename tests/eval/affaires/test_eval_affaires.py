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


@pytest.mark.eval
def test_lifecycle_pairwise_runs() -> None:
    """La 3ᵉ baseline (vraie fonction prod) tourne et produit des métriques cohérentes.

    NB : importe `affair_lifecycle_service` (5653 L). Si ce module devenait non
    importable sans Mongo, ce test casserait — signal utile.
    """
    r = evaluate("lifecycle_pairwise")
    assert r.n > 0
    assert 0.0 <= r.metrics.precision <= 1.0
    assert 0.0 <= r.metrics.recall <= 1.0
    assert 0.0 <= r.metrics.f1 <= 1.0


@pytest.mark.eval
def test_lifecycle_pairwise_matches_or_beats_jaccard_plus_entities() -> None:
    """La fonction prod doit au moins égaler la baseline Jaccard+entités.

    Si elle perd, c'est qu'on a une régression — ou que la baseline naïve
    est juste meilleure sur le dataset, ce qui est un finding majeur à
    diagnostiquer avant de continuer à tuner la fonction prod.

    Seuil de tolérance : prod doit faire au moins (jaccard+entities - 0.05).
    """
    prod = evaluate("lifecycle_pairwise")
    naive = evaluate("jaccard_plus_entities")
    assert prod.metrics.f1 >= naive.metrics.f1 - 0.05, (
        f"REGRESSION : lifecycle_pairwise F1={prod.metrics.f1:.2f} "
        f"< jaccard_plus_entities F1={naive.metrics.f1:.2f}. "
        f"La fonction prod (`AffairLifecycleService._pairwise_similarity`) "
        f"est battue par une baseline triviale Jaccard+entités. "
        f"À diagnostiquer avant tout tuning."
    )


@pytest.mark.eval
def test_known_overgrouping_bug_is_still_present() -> None:
    """Marque la fixture ex-004 (Durimel cité dans 2 contextes) comme bug
    connu — la fonction prod sur-groupe.

    Quand ce test commencera à échouer, c'est qu'on aura corrigé le sur-groupage
    par entité partagée. Le retirer alors.

    Référence : mémoire `project_affaires_quality` (3 systèmes de similarité
    divergents) + BROKEN.md (sur-groupage par entité partagée).
    """
    prod = evaluate("lifecycle_pairwise")
    err_ids = {e["id"] for e in prod.errors}
    assert "ex-004-split-meme-personne-deux-affaires" in err_ids, (
        "🎉 Le sur-groupage par entité partagée semble corrigé sur ex-004 ! "
        "Retire ce test (qui servait juste à marquer le bug). "
        "Et ajoute une nouvelle fixture qui exhibe le bug suivant."
    )
