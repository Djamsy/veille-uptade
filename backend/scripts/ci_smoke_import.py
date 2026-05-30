#!/usr/bin/env python3
"""
Garde-fou CI : vérifie que le backend reste sain SANS dépendre d'une base MongoDB.

Deux contrôles, exécutés sur l'arbre *vivant* (racine + routers/ + services/) :
  1. Syntaxe   — tous les fichiers .py se compilent.
  2. Import    — chaque module live s'importe, puis `backend.server` compose l'app
                 FastAPI complète (app=True). C'est ce que fait Render au boot,
                 mais joué ici sur la PR, avant merge.

Les dossiers `_attic/` (code quarantainé volontairement) et `scripts/` (outils CLI)
sont exclus de l'étape d'import : ils ne font pas partie de l'app de production.

Usage : python backend/scripts/ci_smoke_import.py
Sortie : code 0 si tout passe, 1 sinon.
"""
from __future__ import annotations

import faulthandler
import importlib
import os
import sys
import traceback
from pathlib import Path

# Filet de sécurité : si un import bloque (effet de bord réseau/DB), on dump la pile
# et on échoue au lieu de laisser le runner tourner indéfiniment.
faulthandler.dump_traceback_later(420, exit=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))

# Env factices : on veut prouver que les modules s'importent sans secrets réels.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")
os.environ.setdefault("JWT_SECRET", "ci-smoke-secret-not-used-anywhere-0123456789")
os.environ.setdefault("APIFY_API_TOKEN", "dummy")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RUN_SCHEDULER", "false")


def check_syntax() -> list[str]:
    errors: list[str] = []
    for f in sorted(BACKEND.rglob("*.py")):
        posix = f.as_posix()
        # venv = dépendances tierces ; _attic = code quarantainé volontairement cassé
        if "/venv/" in posix or "/_attic/" in posix:
            continue
        try:
            compile(f.read_text(encoding="utf-8", errors="replace"), str(f), "exec")
        except SyntaxError as e:
            errors.append(f"{f.relative_to(REPO_ROOT)}:{e.lineno} {e.msg}")
    return errors


def live_modules() -> list[str]:
    mods = ["backend.db", "backend.server"]
    for sub in ("routers", "services"):
        for f in sorted((BACKEND / sub).glob("*.py")):
            if f.stem == "__init__":
                continue
            mods.append(f"backend.{sub}.{f.stem}")
    return mods


def check_imports(mods: list[str]) -> list[str]:
    errors: list[str] = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception:  # noqa: BLE001 — on veut tout capturer pour le rapport
            errors.append(f"{m}\n{traceback.format_exc()}")
    return errors


def main() -> int:
    print("== 1) Syntaxe (tout backend/) ==")
    syn = check_syntax()
    if syn:
        print(f"❌ {len(syn)} erreur(s) de syntaxe :")
        for e in syn:
            print(f"   {e}")
        return 1
    print("✅ 0 erreur de syntaxe")

    mods = live_modules()
    print(f"\n== 2) Import de l'arbre vivant ({len(mods)} modules, sans MongoDB) ==")
    imp = check_imports(mods)
    if imp:
        print(f"❌ {len(imp)} module(s) ne s'importent pas :")
        for e in imp:
            print(f"\n--- {e}")
        return 1
    print(f"✅ {len(mods)} modules importés, app FastAPI construite (backend.server)")

    print("\n✅ Garde-fou backend : OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
