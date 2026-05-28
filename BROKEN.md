# BROKEN.md — modules cassés à l'import & implications

> Audit du 2026-05-28. Trois ImportError latents restaient cachés par des
> `try/except ImportError: pass` dans le code. Cette page les explicite et
> raconte ce qu'elles signifient vraiment pour la prod.

## TL;DR

**Pas de fonctionnalité prod cassée silencieusement.** Mais beaucoup de code
mort que les `try/except` rendaient invisible. À nettoyer en vague 3.

| Module | Cassure | Wiré en prod ? | Vraie cause |
|---|---|---|---|
| `media_noise_service.py` | `ELECTED_INDEX` / `THEME_TAXONOMY` absents de `tags_index` | ❌ — uniquement dans `enhanced_scheduler` (mort) et 3 `viral_*` (morts) | Implémentation BMG legacy laissée à côté |
| `sentiment_metrics_dashboard.py` | `matplotlib` non installé | ❌ — uniquement dans `social_monitoring_routes` (non wiré) | Dashboard one-shot |
| `pdf_routes.py` | Importait `pdf_digest_service` (fichier renommé en `pdf_service.py`) | ❌ — non wiré | Renommage incomplet — **fixé dans cette PR** |
| `gpt_sentiment_validation.py` | `ELECTED_INDEX` absent | ❌ — 0 importeur | Vraiment mort — **supprimé dans cette PR** |

## Découverte la plus importante de l'audit

**`enhanced_scheduler.py` n'est PAS le scheduler actif en production.**

- `server.py` n'appelle que `attach_scheduler(app)` depuis `scheduler_service.py`
- Seule `telegram_morning_digest_job()` est utilisée depuis `enhanced_scheduler` (endpoint manuel)
- Les **13 jobs** définis dans `enhanced_scheduler.py` (`enhanced_scraping`, `sentiment_batch`, `media_noise_calculation`, `daily_digest`, `cleanup`, `affair_lifecycle`, `storage_monitor`, `telegram_morning_digest`, `gpt_affair_cleanup`, `stale_active_crosscheck`, `classify_communes`, `facebook_telegram_sync`, `social_stats_scrape`) **ne sont jamais déclenchés**

Le scheduler actif est `scheduler_service.py` avec **12 jobs réels** : `full_pipeline`, `update_affairs`, `radio_capture`, `radio_health_check`, `social_scrape`, `buffer_stats_sync`, `apify_comments_scrape`, `campaign_auto_analysis`, `predictive_analysis`, `daily_report`, `morning_briefing`, `watchlist_check`.

→ `ARCHITECTURE.md` corrigé dans cette PR.

## BMG — où ça se passe réellement

Le calcul du Bruit Médiatique Global se fait **dans `scheduler_service.job_affair_cycle`** (commentaire ligne 379 : `4. Lifecycle + BMG`) et est référencé partout dans `affair_lifecycle_service.py` (`compute_priority`, sort par `bmg`, etc.).

`media_noise_service.py` est une **implémentation BMG legacy parallèle**, jamais wirée. C'est probablement la trace d'un refacto pas terminé.

## Modules à supprimer en vague 3 (candidats — à valider)

Tous découverts pendant cet audit, tous à 0 importeur réel (ou seulement par du mort transitif) :

| Fichier | Lignes | Raison |
|---|---|---|
| `backend/enhanced_scheduler.py` | 1 163 | Non démarré, seul `telegram_morning_digest_job` est utilisé — à extraire ailleurs (ex: `backend/telegram_service.py`) avant suppression |
| `backend/media_noise_service.py` | ~700 | Implémentation BMG legacy, jamais wirée |
| `backend/viral_detection_service.py` | 773 | 0 importeur réel |
| `backend/viral_automation_service.py` | ? | 0 importeur réel |
| `backend/viral_orchestra_service.py` | ? | 0 importeur réel |
| `backend/sentiment_metrics_dashboard.py` | ? | Uniquement dans `social_monitoring_routes` (non wiré) |
| `backend/social_monitoring_routes.py` | 485 | Non wiré, 9 endpoints `/api/social/monitor/*` orphelins |

**Estimation** : encore ~4 000 L à retirer si tous confirmés.

## Routes définies mais jamais wirées

Trois fichiers routes existent et ont des endpoints, mais **aucun n'est wiré
dans `server.py`** :

- `pdf_routes.py` (`/api/digest/pdf/today`, `/api/digest/pdf/{date_str}`)
- `digest_routes.py` (9 endpoints `/api/digest/*`)
- `social_monitoring_routes.py` (9 endpoints `/api/social/monitor/*`)

**Décision à prendre** :
- **Si ces routes doivent servir** → les wirer dans `server.py`, ajouter des tests d'intégration
- **Sinon** → suppression (vague 3)

Ne pas trancher sans connaître l'intention produit.

## Ce qui est fixé dans cette PR

1. ✅ `pdf_routes.py` : `pdf_digest_service` → `pdf_service` (2 lignes)
2. ✅ `digest_routes.py` : `pdf_digest_service` → `pdf_service` (4 lignes — comments laissés)
3. ✅ `backend/gpt_sentiment_validation.py` supprimé (mort confirmé)
4. ✅ `ARCHITECTURE.md` corrigé sur le wiring scheduler
5. ✅ Ce document créé

## Ce qui reste un SKIP dans `test_smoke_imports`

Volontairement, après cette PR :

- `media_noise_service` — cassé sur `ELECTED_INDEX` (mort effectif, à supprimer en vague 3)
- `sentiment_metrics_dashboard` — cassé sur `matplotlib` (mort effectif)

Ces 2 SKIP sont des balises : tant qu'elles restent, ces modules sont
identifiés comme suspects. La vague 3 les supprimera.

## Ruff backlog (CI non-bloquante temporairement)

`ruff check .` rapporte **~2 321 erreurs** sur le repo (audit 2026-05-28),
dont **1 827 auto-fixables** (`--fix`) — formatage, imports désordonnés,
syntaxe `Dict` / `List` → `dict` / `list`, etc.

Top des familles d'erreurs (estimées via `--statistics`) :
- `UP006` / `UP035` — annotations typing legacy à moderniser
- `I001` — imports désordonnés
- `B008` / `B904` — bugs courants (FastAPI Depends, raise from)
- `RUF*`, `SIM*` — simplifications diverses
- **2 `invalid-syntax`** — à investiguer en priorité

### Pourquoi non-bloquant maintenant

Si on rend `ruff check` bloquant immédiatement, toutes les PRs en cours
(stack fondations → dead-code → ai-service → import-errors) cassent en CI.
On ne peut pas demander à chaque PR d'absorber un nettoyage de 2 321 erreurs.

### Plan recommandé

1. **PR dédiée** `chore/ruff-cleanup-batch-1` : `ruff check --fix .` puis
   `ruff format .` sur tout le repo (~1 827 corrections sûres). Review en
   un coup d'œil — c'est mécanique.
2. PR suivante : régler les 494 erreurs non-auto-fixables par famille
   (`B904`, `SIM*`, etc.). Une famille = un commit.
3. Quand `ruff check .` rapporte 0 erreur, **retirer `continue-on-error`** dans
   `.github/workflows/ci.yml`.

D'ici là, ruff continue à check (visible dans les logs CI) mais ne bloque pas.
