# SECURITY — actions urgentes & politique

> Dernière mise à jour : 2026-05-28
> Le dépôt est **public** : `https://github.com/Djamsy/veille-uptade`.

## 🚨 Actions à mener par Djamsy — MAINTENANT

Audit de l'historique git effectué le 2026-05-28. Constats :

### 1. Clé OpenAI fuitée dans l'historique
- **Pattern trouvé** : `sk-proj-…`
- **Commit** : `b9df0ec — feat: redesign visuel + PWA + optimisation mobile`
- **Fichiers** : `veille_backend.log`, `veille_media.log` (logs commités par erreur)
- **Impact** : repo public → la clé est indexée sur GitHub.

**À faire** :
1. Aller sur https://platform.openai.com/api-keys → **révoquer** la clé concernée
2. Générer une nouvelle clé
3. La poser uniquement dans `backend/.env` (jamais en log)
4. Vérifier la consommation OpenAI des 30 derniers jours pour détecter un usage anormal

### 2. Credentials Mongo Atlas — à vérifier
Le pattern `mongodb+srv://user:password@cluster0…` apparaît dans plusieurs commits via `DEPLOYMENT_FIXES.md` (versions anciennes du fichier). Le fichier actuel sur `main` est nettoyé, **mais l'historique reste accessible**.

**À faire** :
1. Mongo Atlas → Database Access → rotate password de l'utilisateur `djamalloiseau`
2. Mettre à jour `MONGO_URL` dans Render env vars + `backend/.env`

### 3. Faux positifs vérifiés
- `AKIA…` détecté uniquement dans `venv/lib/python3.9/site-packages/PIL/ImageFont.py` (chaîne `AKIAchen` interne à Pillow). **Pas un secret AWS.**
- `apify_api_…` : aucune occurrence dans l'historique. **OK.**

## Pourquoi pas de `git filter-repo` ?

Réécrire l'historique d'un repo public :
- Ne supprime pas les copies déjà clonées / déjà indexées par GitHub
- Casse tous les clones existants (collaborateurs, déploiements)
- **Ne dispense pas de la rotation** — la rotation est de toute façon la mitigation réelle

→ Rotation immédiate des clés. La purge d'historique est une option secondaire si tu veux nettoyer la trace publique, à faire en connaissance de cause.

## Politique secrets (à partir de maintenant)

1. **Aucun secret en clair dans le code, jamais.** Lecture via `os.getenv()` uniquement.
2. **`.env` ignoré dur** — vérifier avec `git check-ignore backend/.env` (doit renvoyer le chemin).
3. **`.env.example` est la source de vérité** des variables attendues. Toute nouvelle variable y est ajoutée avec une valeur factice.
4. **Logs jamais commités.** `*.log` est dans `.gitignore`. Avant tout commit, `git status` ne doit pas montrer de `.log`.
5. **Pre-commit hook** (à venir, cf. `.pre-commit-config.yaml`) scanne les diffs pour les patterns de secrets connus (`sk-`, `apify_api_`, `mongodb+srv://[^:]+:[^@]+@`, `ghp_`, `AKIA[0-9A-Z]{16}`).
6. **Render env vars** = source de vérité en production. Le `backend/.env` local n'est que pour le dev.

## Si tu trouves un secret commité par erreur (futur)

1. **Révoque-le d'abord**, c'est la seule mitigation qui compte.
2. Ouvre une issue interne avec le SHA du commit et le pattern fuité.
3. Décide ensuite si tu réécris l'historique (rare, et seulement avant que d'autres aient cloné).

## Endpoints publics — état

L'audit fiabilisation du 2026-05-18 a fermé 8 endpoints. Tous les endpoints d'écriture (POST / PUT / DELETE) doivent passer par `Depends(get_current_user)` ou un token de bot dédié (`PUBLICATION_BOT_TOKEN`). À vérifier lors de l'ajout de nouvelles routes.
