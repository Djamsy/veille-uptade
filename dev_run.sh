#!/usr/bin/env bash
set -euo pipefail

# se placer dans le dossier du script
cd "$(dirname "$0")"

# créer & activer le venv si besoin
if [ ! -d ".venv" ]; then
  echo "[dev_run] .venv introuvable, création..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# charger .env si présent (ignorer les lignes commentées)
if [ -f ".env" ]; then
  echo "[dev_run] Chargement de .env"
  # charger toutes les variables définies dans .env
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

# valeurs par défaut si pas fournies
: "${ENVIRONMENT:=development}"
: "${ALLOWED_ORIGINS:=http://localhost:3000}"
: "${MONGO_URL:=}"

export ENVIRONMENT ALLOWED_ORIGINS MONGO_URL

echo "[dev_run] ENVIRONMENT=$ENVIRONMENT"
echo "[dev_run] ALLOWED_ORIGINS=$ALLOWED_ORIGINS"
if [ -n "$MONGO_URL" ]; then
  echo "[dev_run] MONGO_URL défini"
else
  echo "[dev_run] MONGO_URL vide (toléré en dev)"
fi

# installer les dépendances si tu as un requirements (optionnel)
if [ -f "backend/requirements.txt" ]; then
  python -m pip install -r backend/requirements.txt
fi

# démarrer le serveur
exec python -m uvicorn backend.server:app --reload --host=127.0.0.1 --port=8000