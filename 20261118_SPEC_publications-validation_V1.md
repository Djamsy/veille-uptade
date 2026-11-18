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

## Feuille Google attendue

Première ligne = en-têtes, repérés par leur nom (insensible aux accents / casse, correspondance partielle) :
`Titre`, `Texte` (obligatoire), `Médias` (URL, séparées par virgule ou saut de ligne), `Réseaux`, `Date`,
`Demandeur`, `E-mail`, `Campagne`, `Notes`, `Statut` (colonne écrite en retour), `ID` (facultatif).

Règles d'import : lignes dont le statut est vide ou « à valider » ; dédoublonnage par
empreinte du contenu ; une ligne modifiée après import annule l'ancienne demande en attente et en crée une nouvelle.

## Mise en service

1. Générer la clé et la poser dans Render : `PUBLICATION_ENCRYPTION_KEY`.
2. Créer un compte de service Google (API Sheets activée), télécharger le JSON,
   le coller dans `GOOGLE_SERVICE_ACCOUNT_JSON`, partager la feuille avec l'adresse du compte (Éditeur).
3. Renseigner `PUBLICATION_SHEET_ID`, `PUBLICATION_VALIDATION_BASE_URL` (URL du front).
4. Vérifier dans `/admin/publications` le panneau « Configuration », puis « Lire la feuille ».

## Hypothèses prises (à confirmer)

- Validateurs externes via le lien ; l'admin connecté supervise.
- Publication manuelle par un admin, sur tous les canaux Buffer connectés (la colonne Réseaux est informative en V1).
- La colonne Date est informative (pas de programmation à l'heure dite en V1).
