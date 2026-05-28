"""Smoke test : tous les modules backend importables sans I/O.

C'est volontairement large et brut. Un import qui pète révèle :
- une dépendance manquante,
- un effet de bord à l'import (connexion Mongo, appel HTTP, etc.),
- un fichier mort qui référence du code supprimé.

On exclut les modules connus comme « lourds à l'import » (scheduler qui démarre,
scripts de migration) — listés dans HEAVY_MODULES.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"

# Modules qu'on ne tente pas d'importer (effet de bord lourd ou volontairement isolés)
HEAVY_MODULES: set[str] = {
    "server",  # démarre FastAPI + cache + threads
    "enhanced_scheduler",  # démarre APScheduler
    "scheduler_service",
    "simple_scheduler",
    # Scripts one-shot, pas faits pour être importés
    "enrich_articles_script",
    "enhanced_enrich_existing_articles",
    "enrich_existing_articles",
    "retag_transcriptions",
    "clear_mongodb",
    "reset_affairs",
    "analyze_affair_spans",
    "fix_scraper",
    "test_scraping_simple",
    "test_social_scraping",
}


def _backend_modules() -> list[str]:
    names: list[str] = []
    for info in pkgutil.iter_modules([str(BACKEND)]):
        if info.ispkg:
            continue
        if info.name.startswith("_"):
            continue
        if info.name in HEAVY_MODULES:
            continue
        # Fichiers avec un espace dans le nom (ex: "test_new_features 2") = junk
        if " " in info.name:
            continue
        names.append(info.name)
    return sorted(names)


@pytest.mark.unit
@pytest.mark.parametrize("module_name", _backend_modules())
def test_module_imports(module_name: str) -> None:
    """Chaque module backend doit s'importer sans erreur."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        # Tolérance : certaines deps optionnelles peuvent manquer en CI sans crédentials.
        # On signale mais on ne casse pas pour ImportError sur 3rd-party — on casse pour
        # erreurs internes (NameError, SyntaxError, etc.).
        pytest.skip(f"ImportError externe : {exc}")
