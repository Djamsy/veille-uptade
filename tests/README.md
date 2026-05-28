# tests/

Trois familles de tests, marqueurs pytest correspondants :

| Dossier | Marker | Rôle |
|---|---|---|
| `unit/` | `unit` | Tests rapides, sans Mongo ni réseau. Doivent tourner en < 5 s en tout. |
| `integration/` | `integration` | Mongo local requis (`MONGO_URL=mongodb://localhost:27017/veille_test`). |
| `eval/` | `eval` | Mesures de qualité produit sur datasets annotés (voir `eval/affaires/`). |

## Lancer

```bash
# Tout
pytest

# Une famille
pytest -m unit
pytest -m integration
pytest -m eval

# Un fichier
pytest tests/unit/test_imports.py -v
```

## CI

- Sur PR : `pytest --collect-only` (vérifie que tout importe).
- À mesure que les tests `unit` deviennent fiables, durcir la CI pour exiger
  `pytest -m unit` vert.
- Les tests `integration` et `eval` tournent à la main pour l'instant.

## Eval — qualité des affaires

Voir [`eval/affaires/README.md`](eval/affaires/README.md). C'est le levier
n°1 pour avancer sur la fusion d'articles en affaires sans casser ce qui marche.
