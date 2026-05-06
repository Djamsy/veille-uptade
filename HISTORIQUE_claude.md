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
- Quartier : champ stocké, mais pas encore de gazetteer dédié. Le LLM le remplit s'il est nommé explicitement, sinon `null`. Gazetteer manuel à prévoir en V1.1.

### LIVRÉ — V1.1 (même session, après déploiement V1)

**Étape 6 — auto-extraction dans le pipeline d'enrichissement**
- `backend/scheduler_service.py` (job_enrich) : après le `bulk_write` des enrichissements, le job parcourt les articles enrichis et appelle `extract_presences_from_article`. Insertion idempotente grâce à `idx_presence_dedup`. Failures isolées (debug log), n'échoue jamais le job principal. Désormais chaque cycle d'enrichissement alimente automatiquement `entity_presences` — plus besoin de backfill manuel pour les nouveaux articles.

**Étape 7 — carte choropleth SVG**
- `frontend/components/GuadeloupeMap.tsx` : export de `GUADELOUPE_COMMUNE_PATHS` (les paths Bézier).
- `frontend/components/PresenceMap.tsx` (nouveau) : carte choropleth réutilisant les paths, échelle bleue (Faible / Modérée / Forte / Très forte), tooltip avec top élus + dernière date, click pour copier le nom de la commune.
- `frontend/app/admin/presence/page.tsx` : carte branchée au-dessus de la table.

### LIVRÉ — V1.2 monitoring création d'affaires (étape 8)

Décision Djamsy : avant de basculer sur un modèle « affaires journalières », on tente un ultime clear et on observe le pipeline en temps réel pour voir si le fix ea88e5f tient.

**Backend**
- `backend/affairs_monitor_routes.py` (nouveau) — router admin `/api/affairs/monitor/*` :
  - GET `/overview?hours` : KPIs (créations, processés, en attente, ignorés, distributions thèmes/statuts/raisons).
  - GET `/recent-affairs?limit` : derniers documents `affairs` triés par created_at desc.
  - GET `/timeline?event&limit` : flux brut de `affair_timeline`.
  - GET `/blocked-articles?hours&limit` : articles avec `_affair_ignored=true` et leur `_ignore_reason`.
  - POST `/reset?confirm=yes-reset-affairs` : ultime clear (affairs + timeline + clusters + candidates + reset flags articles). Logué avec l'email admin.
- Branchement dans `server.py` après le router presence.

**Frontend**
- `frontend/components/AuthGuard.tsx` : route `/admin/affairs-monitor` ajoutée.
- `frontend/app/admin/affairs-monitor/page.tsx` (nouveau) — dashboard avec auto-refresh 30 s :
  - KPIs (4 chiffres clés)
  - 3 distributions (statut / thème / raison de blocage)
  - Table des 50 dernières affaires
  - Flux timeline (80 derniers événements) + table articles refusés (50, fenêtre 2× hours)
  - Bouton « ⚠️ Ultime clear » avec window.confirm

**Usage attendu**
1. Aller sur `/admin/affairs-monitor`.
2. Cliquer « ⚠️ Ultime clear » et confirmer.
3. Attendre les prochains cycles d'enrichissement (10-15 min selon le scheduler).
4. Observer : combien d'affaires sont créées, combien d'articles sont absorbés vs bloqués, et pour quelles raisons.
5. Si la « raison de blocage » majoritaire est `commune_diff` ou `theme_incoherent`, c'est que les gardes-fous tiennent. Si on voit beaucoup de fusions cluster→affaire avec des thèmes hétéroclites, le modèle est toujours problématique → basculer en daily affairs.

### À DÉCIDER — passer aux « affaires journalières »
Djamsy (2026-05-06) : « je crois qu'il faut complètement abandonner le suivi d'affaire dans le temps et passer en affaire journalière ».

Implication majeure : abandonner le modèle `affair_lifecycle_service.py` (5 653 lignes, status active/stale, consolidation 24h, cross-check, etc.) au profit d'un modèle où **chaque journée produit son propre cluster d'affaires**, sans liaison cross-day.

**À discuter avant tout code** :
- Qu'est-ce qu'on perd ? (vue « histoire qui se développe », trend sur la semaine, BMG cumulatif)
- Qu'est-ce qu'on gagne ? (zéro boule de neige, logique simple, audit clair)
- Migration : que devient la collection `affairs` actuelle ?
- Est-ce qu'on peut faire tourner les deux modèles en parallèle pour comparer ?
- Impact UI : page `/affairs`, dashboard, BMG, briefing, digest Telegram — tous dépendent du modèle actuel.

---

## Conventions
- **Nommage des livrables figés (PDF, images)** : `AAAAMMJJ_TYPE_nom-du-fichier_V` (ex : `20260506_REVUE_projet_V1.docx`). Réécriture autorisée, on incrémente le V.
- **Autres fichiers** (md, code, configs) : nommage libre, Djamsy précisera s'il faut respecter la convention.
- **Ce fichier** est une exception « evergreen » : un seul fichier qui s'allonge.
- **Sources** : quand je cite un commit, un fichier ou une route, je mets le chemin exact pour qu'on puisse vérifier.
