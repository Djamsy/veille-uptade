# Eval — qualité de la fusion en affaires

> Pourquoi : la mémoire `project_affaires_quality` documente le problème —
> trois systèmes de similarité divergents dans le code, et **aucune mesure**.
> Sans mesure on ne peut pas savoir si un changement améliore ou dégrade la fusion.
> Cet harness est le squelette qui ouvre la mesure.

## Le problème en une phrase

Étant donné deux articles A et B, est-ce qu'on doit les ranger dans la **même
affaire** ou non ? Le code répond avec un score de similarité hybride
(embeddings + entités + temporalité) — voir
[`affair_lifecycle_service._pairwise_similarity`](../../../backend/affair_lifecycle_service.py#L5470).
On veut mesurer **precision/recall/F1** de cette décision sur un dataset
annoté à la main.

## Structure

```
tests/eval/affaires/
├── README.md              ← ce fichier
├── fixtures.jsonl         ← dataset annoté (à étoffer : 5 paires démo)
├── runner.py              ← calcule precision/recall/F1
├── baselines/
│   └── jaccard_tokens.py  ← baseline naïve (référence basse)
└── results/               ← snapshots de runs (suivi temporel)
```

## Format `fixtures.jsonl`

Une ligne JSON par paire d'articles annotée :

```json
{
  "id": "ex-001",
  "should_merge": true,
  "rationale": "Même fait : incident X au lieu Y avec personne Z citée",
  "article_a": {
    "title": "...",
    "description": "...",
    "tokens": ["mot1", "mot2", "..."],
    "entities": ["Personne Z", "Lieu Y"],
    "theme": "securite",
    "date": "2026-05-15T08:00:00Z"
  },
  "article_b": { ... }
}
```

## Lancer

```bash
# Baseline Jaccard sur les tokens (référence basse)
pytest -m eval tests/eval/affaires/ -v

# Lancer le runner directement (sortie détaillée)
python -m tests.eval.affaires.runner --baseline jaccard_tokens
```

Sortie attendue :

```
=== Eval fusion affaires — baseline=jaccard_tokens ===
Dataset: 5 paires (3 positives, 2 négatives)
Seuil de décision : 0.30

Confusion matrix
                predicted_merge   predicted_split
should_merge          2                1
should_split          0                2

Precision : 1.00
Recall    : 0.67
F1        : 0.80

Erreurs :
  ex-003  attendu=merge  prédit=split  score=0.18
```

## Comment ajouter une paire

1. Choisis une paire d'articles **vraiment vue en prod** que tu sais (in)correctement fusionnée.
2. Ajoute une ligne à `fixtures.jsonl` avec `should_merge: true|false` et un `rationale` court.
3. Relance `pytest -m eval` — la baseline va probablement échouer sur ton cas
   (elle est volontairement faible), et c'est exactement le signal qu'on veut.
4. À mesure que le dataset grossit (objectif : 50-100 paires), on durcit
   le seuil de F1 minimum dans le test pytest.

## Brancher la vraie similarité

La baseline actuelle est `jaccard_tokens` (intersection de tokens / union).
Pour câbler `_pairwise_similarity` de `affair_lifecycle_service` :

1. Extraire `_pairwise_similarity` en fonction **pure** (sans `self`, ou avec
   un mock minimal du service).
2. Ajouter un fichier `baselines/lifecycle_pairwise.py` qui importe cette
   fonction et l'expose avec la signature standard du runner.
3. Comparer side-by-side les deux baselines sur le même dataset → on saura
   enfin si la similarité actuelle bat le random.

## Pourquoi un harness avant un refacto

Réécrire la similarité sans baseline mesurée, c'est faire de la décoration.
Le harness donne le filet : tu sais immédiatement si une modif fait monter
ou tomber le F1. Sans ça, chaque correctif est une croyance.
