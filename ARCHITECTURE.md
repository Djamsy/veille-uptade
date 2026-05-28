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
| `/api/scheduler` | (interne — depuis `enhanced_scheduler.py`) | Statut jobs |
| `/api/social` | `backend/social_*_routes.py` (plusieurs) | Réseaux sociaux |
| `/api/transcriptions` | `backend/transcription_*_routes.py` | Radio + IA |
| `/api/veille` | `backend/veille_routes.py` | Veille agrégée |
| `/api/digest/pdf` | `backend/digest_routes.py`, `pdf_routes.py` | Génération PDF |
| `/telegram` | `backend/telegram_routes.py` | Bot Telegram |

> Note : `transcription_ai_routes.py` (`/api/ai/*`) et `advanced_classification_routes.py` (`/api/transcriptions/advanced/*`) ont été supprimés le 2026-05-28 — ils définissaient des routers mais n'étaient **pas wirés dans server.py**. Mort effectif. Voir DUPLICATES.md.

⚠️ **Fichiers `*_routes.py`** posés à plat — pas de hiérarchie par domaine (chantier ouvert).

### Services (couche métier)

Posés à plat dans `backend/`. Familles principales :

| Famille | Fichiers | État |
|---|---|---|
| Affaires (cœur métier) | `affair_lifecycle_service.py` (**5 653 L**) | Monolithe à découper |
| Reconciliation d'entités | `entity_reconciliation_service.py`, `entity_presence_service.py`, `entity_aliases.py` | OK |
| Sentiment | `sentiment_service.py`, `sentiment_analysis_service.py`, `gpt_sentiment_service.py` (+ `gpt_sentiment_validation.py`) | 3 implémentations à fusionner (chantier ouvert) — voir DUPLICATES.md |
| LLM | `ai_groq_service.py` (principal), `ai_service.py` (shim trivial pour scripts) | OK depuis 2026-05-28 |
| Scheduler | `scheduler_service.py`, `enhanced_scheduler.py` | 2 actifs à unifier (chantier ouvert) |
| Scraping | `scraper_service.py`, `enhanced_scraper.py`, `enhanced_scraper_with_themes.py`, `apify_social_scraper.py`, `social_stats_scraper.py` | À consolider |
| Briefing / digest | `briefing_service.py`, `daily_report_service.py`, `summary_service.py` | OK |
| Social | `apify_social_service.py`, `modern_social_service.py`, `social_media_service.py`, `intelligent_social_monitor.py`, `social_amplification_tracker.py` | À consolider |
| Bruit médiatique (BMG) | calculé dans `scheduler_service.job_affair_cycle` + utilisé dans `affair_lifecycle_service.compute_priority` | OK. ⚠️ `media_noise_service.py` est une implémentation legacy parallèle non wirée — voir BROKEN.md |
| Réactions / viral | `population_reaction_service.py` (actif). `viral_detection_service.py`, `viral_automation_service.py`, `viral_orchestra_service.py` (mort, candidats vague 3) | partiellement mort |
| Embeddings | `embedding_service.py` | OK |
| Cache | `cache_service.py` + cache mémoire inline dans `server.py` | À unifier |
| Push (notifications) | `push_service.py` | OK |
| Personnalités (élus) | `personalities_service.py`, `elus_database.py` | OK |

### Jobs APScheduler

Le scheduler **actif en prod** est `backend/scheduler_service.py` (démarré
par `attach_scheduler(app)` dans `server.py`). 12 jobs :

| Job ID | Fréquence | Description |
|---|---|---|
| `full_pipeline` | toutes les 5 min | Pipeline complet (scrape → enrichissement → affaires) |
| `update_affairs` | toutes les 15 min | Mise à jour affaires |
| `radio_capture` | toutes les 5 min | Capture flux radio |
| `radio_health_check` | minute 5 et 35 | Santé des flux radio |
| `social_scrape` | 7h10, 13h10, 19h10 | Scraping réseaux sociaux (Apify) |
| `buffer_stats_sync` | 6h, 10h, 13h, 16h, 22h, 23h | Sync stats Buffer |
| `apify_comments_scrape` | 8h, 19h | Scrape commentaires (~$0.43/run) |
| `campaign_auto_analysis` | (cf. code) | Analyse auto campagnes |
| `predictive_analysis` | (cf. code) | Analyse prédictive |
| `daily_report` | (cf. code) | Rapport quotidien |
| `morning_briefing` | (cf. code) | Briefing matinal |
| `watchlist_check` | (cf. code) | Vérif watchlist |

> ⚠️ `backend/enhanced_scheduler.py` définit aussi 13 jobs (`enhanced_scraping`,
> `sentiment_batch`, `media_noise_calculation`, etc.) mais **aucun n'est démarré**.
> Seule la fonction `telegram_morning_digest_job` y est utilisée depuis `server.py`
> (endpoint manuel). Le reste est du code mort. Voir BROKEN.md et DUPLICATES.md.

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
