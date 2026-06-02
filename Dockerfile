# Image officielle Playwright Python : Chromium + toutes les libs système
# nécessaires au rendu headless sont déjà installés (la version doit
# correspondre à playwright dans backend/requirements.txt → 1.49.0).
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# 1) Dépendances Python (couche cache séparée du code).
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 2) Code backend (paquet `backend` importable depuis /app).
COPY backend ./backend

ENV PYTHONUNBUFFERED=1 \
    PORT=10000

EXPOSE 10000

# Render injecte $PORT ; même ligne de commande que l'ancien startCommand.
CMD uvicorn backend.server:app \
    --host=0.0.0.0 \
    --port=${PORT:-10000} \
    --workers=1 \
    --loop=uvloop \
    --limit-concurrency=100 \
    --timeout-keep-alive=30 \
    --no-access-log
