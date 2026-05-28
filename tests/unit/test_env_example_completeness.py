"""S'assurer que toute variable d'env lue dans le code apparaît dans backend/.env.example.

Empêche de dériver : si tu ajoutes `os.getenv("FOO")` dans le code, tu dois
aussi documenter `FOO` dans `.env.example`. Sinon les déploiements oublient la variable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
ENV_EXAMPLE = BACKEND / ".env.example"

ENV_VAR_PATTERN = re.compile(
    r"""os\.(?:getenv|environ\.get|environ\[)\s*\(?\s*["']([A-Z_][A-Z0-9_]*)["']"""
)

# Variables tolérées sans doc (alias historiques explicitement mentionnés dans .env.example)
TOLERATED: set[str] = {
    "PORT",  # injecté par Render
    "PYTHON_VERSION",  # buildpack
    "PYTHONPATH",
    "HOME",
    "PATH",
    "TZ",
}


def _vars_used_in_code() -> set[str]:
    found: set[str] = set()
    for py in BACKEND.glob("*.py"):
        # Sauter les venvs accidentels
        if "venv" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in ENV_VAR_PATTERN.finditer(text):
            found.add(m.group(1))
    return found - TOLERATED


def _vars_documented() -> set[str]:
    if not ENV_EXAMPLE.exists():
        return set()
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", text, flags=re.MULTILINE))


@pytest.mark.unit
def test_env_example_documents_all_used_vars() -> None:
    used = _vars_used_in_code()
    documented = _vars_documented()
    missing = used - documented

    if missing:
        msg = (
            "Variables d'env lues dans le code mais absentes de backend/.env.example :\n"
            + "\n".join(f"  - {v}" for v in sorted(missing))
            + "\nAjoute-les à backend/.env.example (avec une valeur factice et un commentaire)."
        )
        pytest.fail(msg)
