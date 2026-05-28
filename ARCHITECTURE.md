# ARCHITECTURE — état actuel (2026-05-28)

Ce document décrit **ce qui existe**, pas la cible. Pour la cible, voir
la review « si je recommençais à 0 » dans la mémoire `project_audit_fiabilisation`
et les recommandations de refacto.

## Vue d'ensemble

```
Frontend Next.js 14 (App Router)
    └─ /api/* → FastAPI (backend/server.py)
                    ├─ MongoDB Atlas
                    ├─ APScheduler (jobs)
                    ├─ Apify (scraping social)
                    └─ OpenAI / Mistral (LLM)
```

## Backend

### Entrée

- **`backend/server.py`** (2 746 L) — point d'entrée, instancie `app = FastAPI()`,
  enregistre les routers via `app.include_router(...)`. Contient aussi une grosse
  partie de logique métier qui devrait être ailleurs (cache mémoire,
  validation d'entités, etc.). **À découper, voir DUPLICATES.md.**
- Lancée par `dev_run.sh` en local, par `render.yaml` en production
  (`uvicorn backend.server:app`).

### Routers (prefix → fichier)

| Prefix | Fichier | Sujet |
|---|---|---|
| `/api` (divers) | `backend/api_routes.py` | Endpoints généraux |
| `/api/auth` | `backend/auth_routes.py` | Login, JWT |
| `/api/admin` | `backend/admin_routes.py` | Backoffice |
| `/api/affairs` | `backend/affair_lifecycle_routes.py` | Lecture/écriture affaires |
| `/api/affairs/monitor` | `backend/affairs_monitor_routes.py` | Surveillance & alertes |
| `/api/presence` | `backend/presence_routes.py` | Présence médiatique élus |
| `/api/reconciliation` | `backend/reconciliation_routes.py` | Dédup entités |
| `/api/ai` (advanced) | `backend/advanced_classification_routes.py` | Classification LLM |
| `/api/scheduler` | (interne — depuis `enhanced_scheduler.py`) | Statut jobs |
| `/api/social` | `backend/social_*_routes.py` (plusieurs) | Réseaux sociaux |
| `/api/transcriptions` | `backend/transcription_*_routes.py` | Radio + IA |
| `/api/veille` | `backend/veille_routes.py` | Veille agrégée |
| `/api/digest/pdf` | `backend/digest_routes.py`, `pdf_routes.py` | Génération PDF |
| `/telegram` | `backend/telegram_routes.py` | Bot Telegram |

⚠️ **23 fichiers `*_routes.py`** posés à plat — pas de hiérarchie par domaine.

### Services (couche métier)

Posés à plat dans `backend/`. Familles principales :

| Famille | Fichiers | État |
|---|---|---|
| Affaires (cœur métier) | `affair_lifecycle_service.py` (**5 653 L**) | Monolithe à découper |
| Reconciliation d'entités | `entity_reconciliation_service.py`, `entity_presence_service.py`, `entity_aliases.py` | OK |
| Sentiment | `sentiment_service.py`, `sentiment_service_v2.py`, `async_sentiment_service.py`, `gpt_sentiment_service.py`, `personality_sentiment_service.py`, `async_sentiment_service copie.py` | **6 implémentations, à fusionner** — voir DUPLICATES.md |
| LLM | `ai_service.py`, `ai_service_no_ollama.py`, `ai_service_unified.py`, `ai_groq_service.py` | **4 implémentations** |
| Scheduler | `scheduler_service.py`, `enhanced_scheduler.py`, `simple_scheduler.py` | **3 implémentations** |
| Scraping | `scraper_service.py`, `enhanced_scraper.py`, `enhanced_scraper_with_themes.py`, `apify_social_scraper.py`, `social_stats_scraper.py` | À consolider |
| Briefing / digest | `briefing_service.py`, `daily_report_service.py`, `summary_service.py` | OK |
| Social | `apify_social_service.py`, `modern_social_service.py`, `social_media_service.py`, `intelligent_social_monitor.py`, `social_amplification_tracker.py` | À consolider |
| Bruit médiatique (BMG) | `media_noise_service.py` | OK |
| Réactions / viral | `population_reaction_service.py`, `viral_detection_service.py` | OK |
| Embeddings | `embedding_service.py` | OK |
| Cache | `cache_service.py` + cache mémoire inline dans `server.py` | À unifier |
| Push (notifications) | `push_service.py` | OK |
| Personnalités (élus) | `personalities_service.py`, `elus_database.py` | OK |

### Jobs APScheduler (`enhanced_scheduler.py`)

Le scheduler actif (les deux autres sont morts ou legacy).

| Job ID | Fréquence | Description |
|---|---|---|
| `enhanced_scraping` | toutes les heures (`min 0`) | Scraping presse locale |
| `sentiment_batch` | toutes les 30 min | Analyse sentiment en lot |
| `media_noise_calculation` | toutes les 2 h (`min 15`) | Calcul BMG |
| `daily_digest` | 12 h | Génération du digest quotidien |
| `cleanup` | 2 h du matin | Nettoyage cache / vieux docs |
| `affair_lifecycle` | toutes les 30 min | Réévaluation gravité affaires |
| `storage_monitor` | toutes les 6 h | Surveillance quota Atlas |
| `telegram_morning_digest` | 7 h | Digest matinal Telegram |
| `gpt_affair_cleanup` | toutes les 6 h | Validation LLM affaires |
| `stale_active_crosscheck` | toutes les 30 min | Détection affaires fantômes |
| `classify_communes` | toutes les heures (`min 20`) | Classification géo |
| `facebook_telegram_sync` | chaque minute | Sync FB → Telegram |
| `social_stats_scrape` | toutes les 48 h | Stats sociales |

### MongoDB — collections principales

Référencées dans le code (extraction par grep, à consolider) :

- `articles`, `national_articles`, `scraped_articles`, `articles_guadeloupe`
- `affairs`, `affaires_guadeloupe` (⚠️ **deux nommages**, à fusionner)
- `radio_transcriptions`
- `daily_digests`
- `bmg_history`
- `sentiment_analysis_cache`, `sentiment_analytics`
- `apify_runs`, `scheduler_logs`
- `comments`, `instagram_comments`
- `external_alerts`, `critical_alerts`, `alerts_config`
- `amplification_events`, `buzz_analysis_cache`, `reaction_predictions`
- `app_cache`

⚠️ **Pas de schéma documenté** — Pydantic models présents mais pas systématiques.
Pas de migrations versionnées. À mettre en place.

### Intégrations externes

| Service | Usage | Variable env |
|---|---|---|
| OpenAI | Sentiment, résumés, classification | `OPENAI_API_KEY` |
| Mistral | Fallback LLM | `MISTRAL_API_KEY` |
| Apify | Scraping FB / IG / TikTok | `APIFY_API_TOKEN` |
| Telegram | Alertes + digest | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Buffer | Publication réseaux | `BUFFER_ACCESS_TOKEN` |
| Cloudinary | Stockage médias | `CLOUDINARY_*` |
| Google CSE | Search | `GOOGLE_API_KEY`, `GOOGLE_CSE_ID` |
| YouTube Data | Vidéos | `YOUTUBE_API_KEY` |
| Twitter Bearer | Tweets | `TWITTER_BEARER_TOKEN` |
| Facebook Graph | Pages | `FACEBOOK_ACCESS_TOKEN` |

## Frontend

### Routes principales (`frontend/app/`)

```
/                  page.tsx (1 739 L — dashboard, à découper)
/landing
/auth/login
/dashboard
/affairs/, /affairs/[id]
/articles
/social        (1 726 L — à découper)
/analytics
/briefing
/radio
/carte
/admin/, /admin/presence, /admin/affairs-monitor
/elections
/departement
/region
/share
/profile
```

### Bibliothèque cliente

- **`frontend/lib/api.ts`** (1 165 L) — toutes les fonctions d'appel API.
  Source unique pour le typage `unknown` côté client. À découper par domaine.

### Composants

- `GuadeloupeMap.tsx`, `PresenceMap.tsx` — cartes Mapbox / SVG
- `BmgGauge.tsx` — jauge BMG
- `Sidebar.tsx`, `BottomNav.tsx`, `ClientLayout.tsx` — chrome
- `ServiceWorkerRegistration.tsx` — PWA
- `AuthGuard.tsx` — protection routes

⚠️ Deux dossiers `affairs` existent : `frontend/app/affairs/` (utilisé) et
`frontend/affairs/` (orphelin probable, à confirmer avant suppression).

## Déploiement

- **Backend** : Render, `render.yaml`, `uvicorn backend.server:app --workers=2`.
  Python **3.11.9** (alors que `runtime.txt` dit 3.9.19 — incohérence à corriger).
- **Frontend** : (à confirmer — Vercel ou Render).

## Conventions actuelles vs cibles

| Sujet | Actuel | Cible (cf. roadmap fondations) |
|---|---|---|
| Organisation backend | Flat (111 fichiers) | Modules par domaine (`domain/affaires/`, etc.) |
| Taille fichier max | Aucune limite (5 653 L max) | 1 500 L bloquant en pre-commit |
| Variantes de service | Multiples `_v2`, `_unified`, ` copie` | Une seule, switch par config |
| Tests | Scripts ad-hoc | pytest dans `tests/`, CI bloquante |
| Eval qualité affaires | Aucune | Harness dans `tests/eval/affaires/` |
| Doc archi | Inexistante | Ce fichier + DUPLICATES.md |
| Secrets en clair | Présents dans `.env` local | OK ; rotation OpenAI à faire (SECURITY.md) |
