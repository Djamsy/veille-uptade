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

## Baselines disponibles

| Baseline | Description | F1 actuel | Seuil |
|---|---|---|---|
| `jaccard_tokens` | Référence basse : intersection / union de tokens | 0.50 | 0.30 |
| `jaccard_plus_entities` | Token Jaccard + bonus entités | **0.86** | 0.30 |
| `lifecycle_pairwise` | **Vraie fonction prod** (fallback sans embeddings) | **0.86** | 0.35 |

### Finding actuel (5 paires, à étoffer)

`lifecycle_pairwise` **égalise** `jaccard_plus_entities` — la complexité
supplémentaire (résolution d'alias, anti-bonus `GENERIC_ELECTED`, score temporel
pondéré) ne fait pas la différence sur ce dataset, parce que :

- Les deux ratent **`ex-004`** pour la même raison : Harry Durimel est dans
  `GENERIC_ELECTED` → le bonus +0.30 est bien bloqué, **mais** les tokens
  « harry/durimel/maire » partagés font monter la similarité sémantique
  au-dessus du seuil 0.35. La protection est partielle.
- C'est exactement le bug que la mémoire `project_affaires_quality` documente.

→ Une fois le dataset à 30-50 paires, on saura si la fonction prod bat
vraiment la baseline naïve ou si elle est juste plus chère à calculer.

## Pourquoi un harness avant un refacto

Réécrire la similarité sans baseline mesurée, c'est faire de la décoration.
Le harness donne le filet : tu sais immédiatement si une modif fait monter
ou tomber le F1. Sans ça, chaque correctif est une croyance.
