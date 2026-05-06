# Historique collaboration Claude — projet veille-uptade

> Journal vivant des échanges, décisions et arbitrages.
> Mis à jour par Claude à chaque session significative.
> Tu peux relire, corriger, biffer librement.

---

## 2026-05-06 — Revue de projet & cadrage feature « présence d'élus »

### Livrables produits
- `20260506_REVUE_projet-veille-uptade_V1.docx` — revue technique (suivi de l'audit du 28/04), axes d'optimisation, roadmap 4 sprints.

### Décisions actées par Djamsy

**Sécurité / .env**
- Les fichiers .env ne sont **pas** versionnés sur GitHub → priorité « rotation immédiate des secrets » abaissée à moyenne.
- Restent prioritaires malgré tout :
  - `JWT_SECRET = "dev-secret-change-me"` doit lever une exception au boot si la variable est absente.
  - `CORS allow_origins="*"` + `allow_credentials=True` à corriger (liste explicite).

**Refactoring server.py**
- Pas de découpage agressif : la prod tourne, on n'expose pas à un refacto risqué.
- Stratégie retenue : **gel + extraction incrémentale**.
  - Règle d'arrêt : aucune nouvelle route n'est ajoutée à server.py — toute nouveauté part dans un router dédié.
  - Extraction au compte-gouttes, un router à la fois, déployable et reverté indépendamment.
  - Refacto franc seulement quand des tests d'intégration couvrent la matrice de routes.

**Feature « carte de présence d'entités »**
- Périmètre : **personnes physiques uniquement** (élus, personnalités publiques en exercice).
- Type de présence : **politique/professionnelle** (mandat, terrain, communication, officiel) — pas de loisirs, pas de vie privée.
- Visibilité : **admin-only** (côté API + côté UI, comme la page social/RS).
- Priorité commune > quartier : on identifie d'abord la commune de l'événement, le quartier vient si possible (gazetteer manuel pour les 5-6 communes les plus actives en V1).
- Justification : l'agrégation cartographique de déplacements de personnes — même publiques — est un produit sensible (RGPD, biais médiatique, risque d'instrumentalisation).

### Plan technique préliminaire (à raffiner)
1. **Modèle de données** : collection `entity_presences` avec `presence_type` distinguant présence physique vs mention contextuelle.
2. **Pipeline d'extraction** : appel structuré Groq (moins cher qu'OpenAI) sur articles enrichis ; réconciliation via `entity_reconciliation_service.py` et `entity_aliases.py`.
3. **Quartier** : gazetteer manuel pour communes prioritaires, fallback OSM Overpass, fallback LLM avec seuil de confiance.
4. **UI** : remplacer la map du dashboard par deux modes — choropleth agrégé par commune, vue entité (heatmap + timeline).
5. **Garde-fous** : normalisation par volume d'articles/commune (anti biais média), liste curatée d'élus pour limiter faux positifs.

### Recommandation
Sprint « fondations présence » (modèle + pipeline commune) avant la refonte UI carte. Backfill 2-3 semaines pour valider la qualité d'extraction avant d'exposer.

### Arbitrages complémentaires (même session)

**Périmètre V1 figé**
- Élus suivis = ceux déjà présents en base, c'est-à-dire `ELECTED_ALIASES` dans `backend/entity_aliases.py` (40 personnalités) complété par `known_personalities` dans `backend/personalities_service.py` (17 personnalités, sous-ensemble qui se recoupe).
- Pas d'enrichissement manuel de la liste en V1 — on travaille avec l'existant pour valider la chaîne d'extraction.
- Avantage : la réconciliation d'alias est déjà résolue, on évite les faux positifs sur les noms communs.

**Profondeur temporelle**
- Durée d'observation **indéfinie** — on n'élague pas l'historique.
- Côté UI, sélecteur de période (7 j / 30 j / 6 mois / 12 mois / personnalisé) pour filtrer la vue carte.
- Côté stockage : pas de TTL sur la collection `entity_presences` (contrairement à `social` qui expire à 90 j).

**Convention de nommage — clarification**
- Le format `AAAAMMJJ_TYPE_nom-du-fichier_V` s'applique surtout aux **PDF et images** (livrables figés).
- Pour les autres fichiers (markdown, code, configs), exception possible et nommage libre — Djamsy le précisera dans la consigne au cas par cas.
- Réécrire un livrable existant (incrémenter le V) reste autorisé.

### Liste V1 — élus en base (extraite de entity_aliases.ELECTED_ALIASES)

Région / Département / Parlementaires : Ary Chalus, Guy Losbar, Victorin Lurel, Josette Borel-Lincertin, Olivier Serva, Max Mathiasin, Justine Bénin, Hélène Vainqueur-Christophe, Dominique Théophile, Marie-Luce Penchard, Lucette Michaux-Chevry.

Maires & élus locaux identifiés : Éric Jalton (Pointe-à-Pitre), Harry Durimel, Christian Baptiste, Ferdy Louisy, Cedric Cornet, Jocelyn Sapotille, Marylène Adhel, Louis Galantine, Francesca Faithful, Eliane Guiougou-Firpion, Fabert Michely, Henry Angélique, Tania Galvani, Catherine Joab, Elie Califer, Jean Dartron, Daniel Dulac, Gabrielle Louis-Carabin, Michel Mado, Jimmy Fausta, Jean-Philippe Courtois, Lydia Faro-Couriol, Eric Latchoumanin, Maryse Etzol, Jean-Claude Maës, Isabelle Amireille-Jomie, Fred Goubin, Nicole De La Rederdière-Ramillon, Adrien Baron.

Total : 40 entités.

### Prochaine étape proposée
Sprint « fondations présence » :
1. Créer `backend/entity_presence_service.py` avec extraction Groq (commune + presence_type) sur articles enrichis.
2. Créer collection `entity_presences` + indexes (`entity_id`, `commune`, `published_at`).
3. Backfill 30 jours pour valider la qualité avant d'ouvrir au backfill complet.
4. UI : nouvelle page admin `/admin/presence` (avant de toucher au dashboard public).

### LIVRÉ — sprint « fondations présence » (2026-05-06, fin de session)

**Sécurité (étape 1)**
- `backend/auth_routes.py` : `JWT_SECRET` obligatoire au boot (RuntimeError si absent ou défaut), alias public `require_admin` exporté.
- `backend/server.py` : CORS explicite (localhost + veille-uptade.vercel.app, surchargeable via `CORS_ORIGINS`), import de `require_admin`, garde admin appliquée à 9 routes destructives (`/api/digest/send`, `/api/affairs/{id}/cleanup`, `/api/affairs/cleanup-all`, `/api/affairs/crosscheck-stale`, `/api/affairs/revalidate`, `/api/scrape`, `/api/debug/reset-affairs`, `/api/social-stats/scrape`, `/api/social-stats/scrape-post/{id}`, `/api/social-stats/buffer-sync`).
- ⚠️ À configurer côté Render avant déploiement : `JWT_SECRET` (token_urlsafe 64), `CORS_ORIGINS` si domaines additionnels.

**Backend feature (étapes 2-4)**
- `backend/entity_presence_service.py` (nouveau) — pré-filtre regex sur ELECTED_ALIASES, extraction LLM JSON structurée via `_call_ai` (OpenAI gpt-4o-mini), validation stricte (commune dans la liste officielle, presence_type ∈ {officiel, mandat, terrain, communication}, rejet vie privée/mention sans déplacement), helpers `aggregate_by_commune` et `aggregate_by_entity`.
- `backend/db.py` : 4 indexes ajoutés sur `entity_presences` (entity+date, commune+date, date, dédup).
- `backend/presence_routes.py` (nouveau) — router `/api/presence/*` 100% admin-only :
  - GET `/entities` (liste V1)
  - GET `/communes?period_days&entity` (agrégation map)
  - GET `/entity/{name}?period_days` (détail élu)
  - GET `/feed` (audit/debug)
  - POST `/backfill?days&limit` (idempotent grâce à idx_presence_dedup)
  - POST `/extract/{article_id}` (debug)
- `backend/server.py` : router branché après veille_routes.

**Frontend (étape 5)**
- `frontend/components/AuthGuard.tsx` : route `/admin/presence` mappée sur le rôle `admin`.
- `frontend/app/admin/presence/page.tsx` (nouveau) — UI admin V1 : sélecteur période (7j/30j/6m/12m/all), sélecteur élu (dropdown 40 noms), 3 KPIs, vue détail entité (communes + types), table communes triée par fréquence, bouton « Lancer un backfill (30 j) ». La carte Mapbox choropleth viendra en V1.1.

**Tests**
- `python3 -m py_compile` OK sur tous les modifiés.
- `tsc --noEmit` OK sur le frontend.

**Ce qui n'est PAS encore branché**
- Extraction automatique au moment du scrape : il faudra greffer un appel à `extract_presences_from_article` + `_insert_presences` dans le pipeline d'enrichissement (`enhanced_scraper_with_themes.py` ou `enrich_existing_articles.py`). Pour l'instant, seule la voie manuelle (POST `/api/presence/backfill`) alimente la collection.
- Quartier : champ stocké, mais pas encore de gazetteer dédié. Le LLM le remplit s'il est nommé explicitement, sinon `null`. Gazetteer manuel à prévoir en V1.1.
- Carte Mapbox choropleth : V1 affiche une table triée. Migration vers Mapbox une fois le pipeline validé.

---

## Conventions
- **Nommage des livrables figés (PDF, images)** : `AAAAMMJJ_TYPE_nom-du-fichier_V` (ex : `20260506_REVUE_projet_V1.docx`). Réécriture autorisée, on incrémente le V.
- **Autres fichiers** (md, code, configs) : nommage libre, Djamsy précisera s'il faut respecter la convention.
- **Ce fichier** est une exception « evergreen » : un seul fichier qui s'allonge.
- **Sources** : quand je cite un commit, un fichier ou une route, je mets le chemin exact pour qu'on puisse vérifier.
