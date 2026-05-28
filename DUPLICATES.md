# DUPLICATES.md — inventaire des doublons backend

> Inventaire initial : 2026-05-28 (audit grep).
> Première vague de suppressions : 2026-05-28 sur `chore/dead-code-2026-05-28`
> (3 commits, 33 fichiers supprimés / 1 déplacé, ~13 600 lignes en moins).
>
> Méthodo : pour chaque famille, on compte les importeurs **dans `backend/`**, en
> excluant les fichiers `.bak` / `.backup` (déjà morts), les scripts one-shot
> et les modules qui ont eux-mêmes 0 importeur (mort transitif).

## État après la 1ère vague (2026-05-28)

| Section | Avant | Supprimé | Reste à traiter |
|---|---|---|---|
| 1. LLM | 4 fichiers | 2 morts | ✅ `ai_service.py` conservé (shim pour scripts) — voir vague 2 |
| 2. Sentiment | 7 fichiers | 4 morts | `sentiment_service.py` vs `_analysis_` vs `gpt_` à unifier |
| 3. Scheduler | 3 fichiers | 1 mort | enhanced / service à unifier (chantier séparé) |
| 4. Scrapers | 5 fichiers | 2 morts | déjà propre |
| 5. Social | 6 fichiers | 2 morts | `intelligent_social_monitor` à vérifier |
| 6. .bak/.backup | 3 | 3 | ✅ vide |
| 7. Scripts racine | 23 | 21 supprimés + 1 déplacé | ✅ il reste `dev_run.sh` seulement |
| Module mort hors liste | — | `media_noise_detection_mistral.py` (SyntaxError) | — |
| **Vague 2 (2026-05-28)** | | | |
| Routers non wirés | 2 | 2 (`transcription_ai_routes.py`, `advanced_classification_routes.py`) | ✅ |
| Scripts d'enrichissement | 2 | 1 doublon supprimé + 1 déplacé vers `backend/scripts/` | ✅ |

**Total** :
- **Vague 1** : 33 fichiers / ~13 600 lignes
- **Vague 2** : 3 fichiers supprimés (~1 315 L) + 1 déplacé

Aucune régression dans `tests/unit/` ni `tests/eval/`.

## Légende

- 🟢 **Actif** — référencé depuis du code servant en prod (server.py, routers wirés, scheduler)
- 🟡 **À fusionner** — actif mais redondant avec un autre
- 🔴 **Mort** — 0 importeur réel (ou seulement depuis du mort transitif / scripts orphelins)

---

## 1. LLM / clients IA — 4 implémentations

| Fichier | Dernier commit | Importeurs réels | Verdict |
|---|---|---|---|
| `backend/ai_groq_service.py` (2 317 L) | 2026-04-04 | server, affair_lifecycle, enhanced_scheduler, scheduler_service, apify_social_scraper, entity_presence | 🟢 **Actif principal** |
| `backend/ai_service.py` (94 L) | 2026-03-17 | seulement scripts one-shot et `social_analysis_service.py` (lui-même mort) | 🔴 **Mort transitif** |
| `backend/ai_service_no_ollama.py` (678 L) | 2026-03-17 | 0 | 🔴 **Mort** |
| `backend/ai_service_unified.py` (519 L) | 2026-03-17 | 0 | 🔴 **Mort** |

**Action proposée** : supprimer les 3 morts. Garder `ai_groq_service.py` comme implémentation unique. Si une logique manque depuis les morts (à vérifier au cas par cas), la porter dans `ai_groq_service.py` avant suppression.

**Économie** : ~1 291 lignes supprimées.

---

## 2. Sentiment — 7 implémentations

| Fichier | Dernier commit | Importeurs | Verdict |
|---|---|---|---|
| `backend/sentiment_analysis_service.py` | 2026-03-17 | 5 | 🟢 **Actif principal** |
| `backend/gpt_sentiment_service.py` | 2026-03-17 | 3 | 🟡 **Co-actif** — fusionner derrière une interface |
| `backend/sentiment_service.py` | 2026-03-17 | 2 | 🟡 **Co-actif** — voir si redondant avec `_analysis_` |
| `backend/sentiment_service_v2.py` | 2026-03-17 | 0 | 🔴 **Mort** |
| `backend/async_sentiment_service.py` | 2026-03-17 | 0 | 🔴 **Mort** |
| `backend/async_sentiment_service copie.py` | 2026-03-17 | 0 | 🔴 **Mort** — nom interdit (` copie`) |
| `backend/personality_sentiment_service.py` | 2026-03-17 | 0 | 🔴 **Mort** |

**Action proposée immédiate** :
1. Supprimer les 4 morts (~1 200 L estimées).
2. **Cible** (chantier séparé) : un seul module `sentiment/` avec une interface `SentimentProvider` (local / GPT) et un sélecteur par config (`FORCE_LOCAL_SENTIMENT`, `DISABLE_GPT_SENTIMENT` qui existent déjà côté env).

---

## 3. Scheduler — 3 implémentations

| Fichier | Dernier commit | Importeurs | Verdict |
|---|---|---|---|
| `backend/enhanced_scheduler.py` (1 163 L) | 2026-04-27 | server.py (`telegram_morning_digest_job`) | 🟢 **Actif** — définit la majorité des jobs |
| `backend/scheduler_service.py` (1 480 L) | 2026-05-06 | server.py (`router`, `attach_scheduler`) | 🟢 **Actif** — expose le router HTTP du scheduler |
| `backend/simple_scheduler.py` | 2026-03-17 | 0 | 🔴 **Mort** |

**Note** : `enhanced_scheduler` et `scheduler_service` ne sont pas des doublons stricts — l'un définit les jobs, l'autre l'API HTTP. **Mais la frontière est floue** : les deux contiennent des `add_job`, les deux importent APScheduler. À unifier (cible : un seul module `scheduler/` avec `jobs.py` et `routes.py`).

**Action proposée immédiate** : supprimer `simple_scheduler.py`. Unification = chantier séparé.

---

## 4. Scrapers — 5 implémentations

| Fichier | Dernier commit | Importeurs | Verdict |
|---|---|---|---|
| `backend/scraper_service.py` | 2026-04-02 | 6 | 🟢 **Actif principal** |
| `backend/apify_social_scraper.py` | 2026-05-08 | 3 | 🟢 **Actif** — spécifique Apify |
| `backend/social_stats_scraper.py` | 2026-05-08 | 1 | 🟢 **Actif** — spécifique stats |
| `backend/enhanced_scraper.py` | 2026-03-17 | 0 | 🔴 **Mort** |
| `backend/enhanced_scraper_with_themes.py` (858 L) | 2026-03-17 | 0 | 🔴 **Mort** |

**Action proposée** : supprimer les 2 morts (~1 100 L).

---

## 5. Services « social » — 6 implémentations

| Fichier | Dernier commit | Importeurs | Verdict |
|---|---|---|---|
| `backend/modern_social_service.py` | 2026-03-17 | 2 | 🟢 **Actif** |
| `backend/social_media_service.py` | 2026-03-17 | 2 | 🟢 **Actif** |
| `backend/intelligent_social_monitor.py` (751 L) | 2026-03-17 | 1 | 🟡 **Vérifier l'importeur** |
| `backend/apify_social_service.py` | 2026-05-08 | 0 | 🔴 **Mort** (mais récent — vérifier si écrit pour être bientôt câblé) |
| `backend/social_amplification_tracker.py` | 2026-03-17 | 0 | 🔴 **Mort** |
| `backend/social_analysis_service.py` | 2026-03-17 | 0 | 🔴 **Mort** (consomme `ai_service.py` mort) |

**Action** : confirmer l'intention pour `apify_social_service.py` (commit récent). Supprimer les 2 autres morts.

---

## 6. Fichiers de sauvegarde manuelle

À supprimer sans hésitation :

- `backend/server.py.backup_20251016_152315`
- `backend/server.py.bak`
- `backend/social_demo_data.py.backup`

→ git c'est précisément fait pour ça.

---

## 7. Scripts orphelins à la racine du repo

24 fichiers `.py` à la racine de `veille-uptade/` au lieu de `backend/scripts/`.
La plupart sont des scripts de test/debug à déplacer ou supprimer :

```
backend_test.py                   backend_test_new.py             backend_test_priority.py
critical_services_test.py         quick_backend_test.py           quick_test.py
scrapers_test.py                  social_media_diagnostic_test.py modern_social_test.py
gpt_sentiment_test.py             test.py                         test_transcribe.py
test_new_features.py              "test_new_features 2.py"        ← espace + chiffre = nom interdit
facebook_all_comments.py          facebook_comments_dedicated.py  facebook_pages_scraper.py
facebook_with_engagement.py
clear_mongodb.py                  retag_transcriptions.py         fix_scraper.py
real_pages_apify_service.py       simple_apify_service.py         simple_apify_service_v2.py
```

**Action proposée** :
- Déplacer les utilitaires utiles vers `backend/scripts/` (`clear_mongodb.py`, `retag_transcriptions.py`).
- Supprimer les `*_test.py` à la racine (la vraie suite est dans `tests/`).
- Supprimer les `simple_apify_service*` (semblent être des essais avant la version actuelle).

---

## Récap chiffré

| Famille | Fichiers morts | Lignes mortes (estim.) |
|---|---|---|
| LLM | 3 | ~1 291 |
| Sentiment | 4 | ~1 200 |
| Scheduler | 1 | ~300 |
| Scrapers | 2 | ~1 100 |
| Social | 3 (+1 à confirmer) | ~700 |
| `.backup` / `.bak` | 3 | quelques milliers |
| Scripts à la racine | ~20 | ~3 000 |
| **Total** | **~36 fichiers** | **~7 500 lignes** |

→ Le repo backend peut perdre **~13 % de son code** sans rien casser, à condition que les vérifs case-par-case confirment l'absence d'importeurs cachés (réflexion, eval, configs YAML).

## Procédure de suppression (quand validée)

1. Branche dédiée : `chore/dead-code-removal-2026-XX-XX`.
2. Une suppression à la fois, **commit individuel**, ordre : `.bak` → fichiers 0 importeur → puis vérifier que la CI smoke (test_smoke_imports) passe encore.
3. Pas de `git rm` en masse : laisse `pytest --collect-only` détecter les importeurs cachés que grep aurait ratés.
