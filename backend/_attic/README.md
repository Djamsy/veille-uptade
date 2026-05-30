# `_attic/` — modules en quarantaine

Ces modules **ne sont pas atteignables** depuis le point d'entrée de production
(`backend.server:app`, cf. `render.yaml`). Ils ont été déplacés ici lors de la
restructuration pour rendre l'arbre vivant lisible, **sans rien supprimer**.

Tout est récupérable d'un simple `git mv backend/_attic/<module>.py backend/<dossier>/`.

## Catégories

### 🔴 Cassés (à réparer avant toute réactivation)
- `gpt_sentiment_validation.py`, `media_noise_detection_mistral.py` — réfèrent `ELECTED_INDEX` (symbole supprimé de `tags_index`)
- `media_noise_detection_mistral.py` — `await` hors fonction `async` (SyntaxError)
- `pdf_routes.py`, `digest_routes.py` — importent `pdf_digest_service` (module inexistant)
- `population_reaction_service.py` — import à plat non résolu

### 🟡 Routers définis mais jamais branchés (`include_router` absent dans `server.py`)
`api_routes`, `analytics_routes`, `social_routes`, `social_media_routes`,
`social_monitoring_routes`, `sentiment_routes`, `transcription_routes`,
`transcription_ai_routes`, `transcription_sentiment_routes`,
`advanced_classification_routes`, `bmg_routes`, `pdf_routes`, `digest_routes`

### 🟡 Doublons de services (l'implémentation vivante est ailleurs)
- Sentiment : `sentiment_service`, `sentiment_service_v2`, `async_sentiment_service`,
  `gpt_sentiment_service`, `personality_sentiment_service`, `sentiment_metrics_dashboard`
  → vivant : `services/sentiment_analysis_service.py`
- IA : `ai_service`, `ai_service_no_ollama`, `ai_service_unified`, `gpt_analysis_service`
  → vivant : `services/ai_groq_service.py`
- Scheduler : `simple_scheduler` → vivant : `services/scheduler_service.py`, `services/enhanced_scheduler.py`

### 🟢 Intégrations sociales — DORMANTES MAIS CENTRALES POUR L'OBSERVATOIRE
Ces modules ne sont pas branchés aujourd'hui, mais le projet « Observatoire des
réseaux » s'appuiera dessus. **À réactiver / consolider lors de la phase 1 de l'observatoire :**

- `facebook_service.py`, `instagram_service.py`, `twitter_service.py`, `tiktok_service.py`
- `social_media_service.py`, `modern_social_service.py`, `apify_social_service.py`
- `social_analysis_service.py`, `social_amplification_tracker.py`, `intelligent_social_monitor.py`
- `media_buzz_analyzer.py`

> Note : le collecteur de stats vivant (`services/social_stats_scraper.py`,
> `services/campaign_service.py` avec `sync_buffer_stats`) reste en place — c'est la
> base de l'axe A de l'observatoire.
