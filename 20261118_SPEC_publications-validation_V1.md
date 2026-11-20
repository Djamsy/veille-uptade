# Publications pour validation — spécification V1

> Date : 2026-11-18 · Branche : `claude/dazzling-gates-76jng6`

## Objet

Un tableau Google Sheets alimenté par les demandeurs est lu périodiquement. Chaque
nouvelle ligne devient une **publication pour validation** : le contenu est stocké
**chiffré**, un **lien à jeton** est envoyé aux validateurs, et la décision
(valider / refuser, texte corrigé éventuel) est écrite en retour dans la feuille.
La publication sur les réseaux via Buffer est ensuite **lancée manuellement** par un
admin depuis `/admin/publications` (pas de publication automatique).

## Sécurité

| Donnée | Stockage Mongo | Remarque |
|---|---|---|
| titre, texte, hashtags, médias, réseaux, date, demandeur, campagne, notes | chiffré (payload_enc) | AES-256-GCM, nonce aléatoire, AAD = identifiant du document |
| état de validation | chiffré (status_enc) + index aveugle HMAC (status_idx) | l'index permet de filtrer sans révéler la valeur |
| décision (qui, quand, commentaire, IP hachée) | chiffré (decision_enc) | |
| résultat de publication Buffer | chiffré (publish_enc) | |
| journal d'audit | chiffré (audit_enc) | |
| jeton de validation | **jamais stocké** : empreinte HMAC seulement (token_hash) | un dump de la base ne permet pas de fabriquer un lien |
| identifiant, dates, source, n° de ligne, empreinte de contenu | en clair | nécessaires au tri et au dédoublonnage |

- Clé : `PUBLICATION_ENCRYPTION_KEY` (32 octets). Sous-clés dérivées par HKDF pour
  le chiffrement, l'index aveugle et le hachage des jetons. Rotation possible via
  `PUBLICATION_ENCRYPTION_KEY_OLD` + `PUBLICATION_ENCRYPTION_KEY_VERSION`.
- **Fail closed** : sans clé en production, le router n'est pas monté.
- Lien : 256 bits aléatoires, durée de vie 72 h (configurable), **usage unique**
  (révoqué dès la décision), révocable et régénérable par un admin.
- Routes par jeton : limitation de débit par IP (60 lectures/min, 10 écritures/min,
  10 jetons inconnus / 5 min), en-têtes `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`.
- Les notifications (Telegram / e-mail) ne contiennent que le titre et le lien, pas le texte.
- Les logs ne contiennent que des identifiants, jamais le contenu.

## Fichiers

Backend
- `backend/services/crypto_service.py` — chiffrement, index aveugle, jetons.
- `backend/services/google_sheets_service.py` — compte de service Google, lecture / écriture (sans dépendance nouvelle : JWT RS256 via python-jose).
- `backend/services/publication_validation_service.py` — modèle, import feuille, décision, publication, notifications.
- `backend/routers/publication_validation_routes.py` — routes admin + routes par jeton (`/api/publications/*`).
- `backend/services/scheduler_service.py` — job `publication_sheet_sync` toutes les 10 min (import + expiration).
- `backend/server.py` — montage du router (aucune route ajoutée dans server.py, conformément à la règle de gel).

Frontend
- `frontend/app/valider/[token]/page.tsx` — page du validateur (sans connexion).
- `frontend/app/admin/publications/page.tsx` — suivi, création manuelle, liens, publication, diagnostic.
- `frontend/lib/api.ts`, `frontend/components/Sidebar.tsx` — client API et entrée « Validations ».

## Soumission directe (sans la feuille)

`/admin/publications` : formulaire **Texte** + **Photos / vidéos** (dépôt de fichiers, 10 max, images recompressées à 1920 px,
200 Mo max par fichier) + options (titre, réseaux, demandeur, consignes, validité du lien). « Soumettre à validation » envoie un
`multipart/form-data` à `POST /api/publications/pending` : les fichiers sont hébergés sur Cloudinary (URL directes, sans
expiration), la demande est chiffrée, le lien personnel est affiché une fois et envoyé aux validateurs. Le validateur voit
texte et médias sur `/valider/<jeton>`, corrige éventuellement le texte, valide ou refuse. L'admin publie ensuite depuis la liste.

## Modification avant validation

Tout ce qui est détecté automatiquement (planning, vidéos livrées) est un brouillon. Dans la liste, « ✏️ Modifier » ouvre
une boîte : titre, texte, réseaux, date, lieu, demandeur, consignes, médias (retrait d'un média existant, ajout de photos ou
vidéos déposées). `PUT /api/publications/pending/{id}` (JSON ou multipart avec `media` et `remove_media`) tant que la
publication est en attente ou le lien expiré ; refus 409 après décision. Le texte d'origine est conservé, chaque
modification est journalisée. Le lien déjà envoyé reste valable et affiche la version à jour ; « Enregistrer et renvoyer un
lien » invalide l'ancien et en envoie un nouveau (`POST /pending/{id}/token` avec `notify: true`).

## Publication constatée sur les réseaux (rapprochement avec le scraping RS)

La publication se fait à la main : rien ne dit au système qu'une publication validée est sortie. Le service
`publication_social_check_service.py` compare les publications **Validée** / **Publiée** aux posts récents de la collection
`social_media_posts` (scraping Apify), restreints aux comptes du Département (`PUBLICATION_OWN_ACCOUNTS`, repérés dans
auteur / URL ; `*` = tous les posts). Score = max(titre normalisé contenu dans le post → 0,95 ; part des mots de la
publication retrouvés dans le post ; ressemblance difflib sur 400 caractères). Au-dessus du seuil
(`PUBLICATION_MATCH_THRESHOLD`, 0,6) : la publication est marquée « vue sur <plateforme> » avec le lien ; si elle n'était
que Validée, elle passe en **Publiée (constatée sur …)**, statut écrit dans la feuille, notification Telegram. Les posts
antérieurs de plus de deux jours à la validation sont ignorés. Résultat stocké chiffré (`seen_enc`) avec les trois
meilleurs candidats ; `seen_at` / `seen_checked_at` en clair (dates seulement).

**Attribution un pour un.** Un post ne peut être rapproché que d'une seule publication : son empreinte (plateforme + URL)
est stockée en clair dans `seen_post_key` avec un index unique ; les posts déjà attribués sont exclus des passages
suivants, et une publication déjà constatée n'est jamais réattribuée. Dans un même passage, toutes les paires
(publication, post) au-dessus du seuil sont triées par score décroissant puis par nombre de mots communs (la publication
la plus précise gagne à égalité) et attribuées tant que ni la publication ni le post ne sont déjà pris. Une course entre
deux passages est rattrapée par l'index unique (l'attribution est abandonnée, pas doublée).

Déclenchement : job `publication_social_check` 3×/jour (7h50, 13h50, 19h50, après le scraping RS), bouton
« 📡 Vérifier sur les réseaux » (`POST /api/publications/check-social`). L'admin voit par publication : « constatée sur
Facebook · mots retrouvés 81 % » (lien vers le post), « pas encore vue sur les réseaux (au mieux 30 %) », ou « à publier à la main ».

## Feuille Google : le planning existant

Source : « Suivi hebdomadaire des prestataires audiovisuels » (id `1JOUzjT49gHf0u4l6e9jLtSiw0P2f3RNOl-tM-EBkE6w`),
un onglet par semaine (`S46 - 09 au 15 nov 2026`, …). Dans chaque onglet : titre, semaine, légende, ligne vide,
puis la ligne d'en-têtes (ligne 5) `Date | Événement | Heure | Prestation nécessaire | Lieu | Précisions / consignes |
Prestataire affecté | Statut | Source / flyer` (+ un second bloc Précisions / Prestataire / Statut / Source), puis trois
lignes pré-remplies par jour avec la date seule.

Lecture : tous les onglets en un appel (`values:batchGet`), ligne d'en-têtes détectée automatiquement (cherche « Date » + « Événement »),
colonnes reconnues par alias (accents / casse ignorés). Le second bloc de colonnes est lu comme complément (notes).

Import (toutes les 10 min) : une ligne devient une publication à valider si Événement est renseigné, si son Statut est
**Confirmé** ou **Réalisé** (`PUBLICATION_SHEET_IMPORT_STATUSES`, `*` pour tout prendre) et si la colonne de retour est vide.
Dédoublonnage par empreinte (onglet + ligne + contenu) ; une ligne modifiée après import annule l'ancienne demande et en crée une nouvelle.

Transformation en post : titre = Événement ; texte proposé = `📅 date · heure` / `📍 lieu` / précisions (modifiable par le
validateur) ; médias = URL trouvées dans Source / flyer ; notes = prestation, prestataire, source non-URL, second bloc.

**Tableaux secondaires « Livraisons »** : sous le planning, un bloc dont l'en-tête commence par `Vidéo` (`Vidéo | Prestataire |
Validée le | Validation | Fichier reçu de Purevision | Envoi aux médias | Envoyé le | Lien WeTransfer | Retours / prochaine étape`)
liste les montages livrés. Chaque ligne dont Validation = **Validé** (`PUBLICATION_VIDEO_IMPORT_STATUSES`) devient une
publication « vidéo livrée » : titre = nom de la vidéo, texte proposé = « 🎬 Vidéo réalisée par <prestataire> », liens
Purevision / WeTransfer conservés comme **liens** (pas comme médias : ce sont des pages, pas des fichiers), retours et dates
en notes. Le bloc « Téléchargements » (suivi par destinataire) est reconnu et ignoré.

**Publication avec fichier joint** : `POST /api/publications/pending/{id}/publish` accepte un `multipart/form-data` avec un
champ `media` (image ou vidéo) hébergé sur Cloudinary puis joint au post Buffer. Seules les URL de fichiers directs
(extension média ou Cloudinary) sont envoyées à Buffer ; les liens sont ignorés côté Buffer. Depuis `/admin/publications`,
le bouton « Publier » ouvre une boîte qui rappelle les liens et permet de joindre le fichier.

Retour : l'état de validation (« En attente de validation », « Validée par X », « Refusée — … », « Publiée ») est écrit dans
une colonne **Publication** ajoutée à droite des en-têtes (`PUBLICATION_SHEET_WRITEBACK_COLUMN`, vide pour désactiver).
**La colonne Statut du planning n'est jamais modifiée.**

## Mise en service

1. Générer la clé et la poser dans Render : `PUBLICATION_ENCRYPTION_KEY`.
2. Compte de service Google : le JSON déjà présent sur Render est détecté automatiquement (noms usuels,
   toute variable contenant un JSON `service_account`, ou Secret File sous `/etc/secrets`). L'API Sheets doit être
   activée sur son projet et la feuille partagée avec son adresse `client_email` (Éditeur). Le panneau
   « Configuration » de `/admin/publications` affiche l'adresse et la variable utilisées.
3. Renseigner `PUBLICATION_SHEET_ID`, `PUBLICATION_VALIDATION_BASE_URL` (URL du front).
4. Vérifier dans `/admin/publications` le panneau « Configuration », puis « Lire la feuille ».

## Hypothèses prises (à confirmer)

- Validateurs externes via le lien ; l'admin connecté supervise.
- Publication manuelle par un admin, sur tous les canaux Buffer connectés.
- Seuls les événements Confirmé / Réalisé du planning sont proposés à la validation (réglable).
- La date de l'événement est reprise dans le texte, pas de programmation à l'heure dite en V1.
