# veille-uptade

Plateforme de veille médiatique pour la Guadeloupe : presse locale, réseaux sociaux,
radio (transcription), cartographie d'élus, suivi d'affaires, briefings.

- **Backend** : FastAPI + MongoDB Atlas, déployé sur Render
- **Frontend** : Next.js 14 (App Router) + Tailwind + Mapbox

## Démarrer en local

### 1. Backend

```bash
cp backend/.env.example backend/.env
# Renseigner au minimum : MONGO_URL, OPENAI_API_KEY
./dev_run.sh
# → http://localhost:8000
```

### 2. Frontend

```bash
cd frontend
cp ../.env.example .env.local         # NEXT_PUBLIC_API_URL, NEXT_PUBLIC_MAPBOX_TOKEN
npm install
npm run dev
# → http://localhost:3000
```

### Vérifier que tout tourne

```bash
curl http://localhost:8000/api/health
```

## Où trouver quoi

| Sujet | Aller voir |
|---|---|
| Architecture (modules, jobs, données) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Sécurité, secrets, rotation de clés | [SECURITY.md](SECURITY.md) |
| État des doublons backend (chantier) | [DUPLICATES.md](DUPLICATES.md) |
| Tests & eval harness | [tests/README.md](tests/README.md) |
| Direction UI canonique | mémoire `project_ui_rework` — `claude/pensive-volhard-dc1a52` (pas `main`) |
| Qualité des affaires (chantier ouvert) | mémoire `project_affaires_quality` |
| Historique des chantiers IA | [HISTORIQUE_claude.md](HISTORIQUE_claude.md) |

## Branches importantes

- **`main`** : tronc. **UI obsolète** (dark V3). À éviter pour les démos.
- **`claude/pensive-volhard-dc1a52`** : direction UI canonique « Carte vivante » +
  travaux sur la qualité des affaires. Inclut tout `main`.
- **`claude/fondations-2026-05-28`** : ce chantier (docs, CI, eval harness, sécu).

## Stack

```
[Next.js 14 / App Router]  ──REST──▶  [FastAPI / Uvicorn]
        Tailwind                              │
        Mapbox GL                             ├─▶ [MongoDB Atlas]
        TanStack Query                        ├─▶ Apify (scraping social)
                                              ├─▶ OpenAI (sentiment, résumés)
                                              ├─▶ Telegram (alertes)
                                              ├─▶ Buffer (publication)
                                              └─▶ Cloudinary (médias)
```

## Versions Python — à harmoniser

⚠️ Incohérence connue : `runtime.txt` dit `python-3.9.19`, `render.yaml` dit `3.11.9`.
La cible est **3.11** (cf. CI). À aligner.

## Contribuer

1. Brancher depuis `main` : `git checkout -b feat/<sujet>` ou `fix/<sujet>`.
2. Lint + types verts : `ruff check . && mypy backend`.
3. PR vers `main`. CI doit passer.
4. Pas de fichier `.py` au-delà de 1500 lignes (pre-commit refuse). Pas de noms `*_v2.py`, `*_new.py`, `*_unified.py`, `* copie.py`.

## Licence

Privé — usage interne.
