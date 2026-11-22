# backend/services/publication_validation_service.py
"""
Publications « pour validation » — contenu chiffré de bout en bout côté stockage.

Flux :
  1. Le planning hebdomadaire Google Sheets (un onglet par semaine : Date, Événement,
     Heure, Prestation nécessaire, Lieu, Précisions / consignes, Prestataire affecté,
     Statut, Source / flyer) ou un admin, à la main, décrit une publication. Chaque
     événement « Confirmé » / « Réalisé » du planning devient un post à valider.
  2. Le service crée un document `pending_publications` dont TOUT le contenu
     sensible est chiffré (AES-256-GCM, voir crypto_service) : titre, texte,
     médias, réseaux, demandeur, statut, décision, résultat de publication, journal.
     Restent en clair : identifiant, dates, source, numéro de ligne, empreintes.
  3. Un jeton de validation (256 bits, non devinable) est généré. Seule son
     empreinte HMAC est stockée. Le lien /valider/<jeton> est envoyé aux
     validateurs (Telegram / e-mail Brevo) — il n'est jamais réaffiché ensuite.
  4. Le validateur consulte, corrige éventuellement le texte, valide ou refuse.
  5. Validée → statut écrit en retour dans la feuille ; notification. La publication
     Buffer est ensuite lancée MANUELLEMENT par un admin (/admin/publications).

Configuration (variables d'environnement) :
  PUBLICATION_ENCRYPTION_KEY            — voir crypto_service.py (obligatoire en prod)
  GOOGLE_SERVICE_ACCOUNT_JSON / PUBLICATION_SHEET_ID / PUBLICATION_SHEET_TAB — voir google_sheets_service.py
  PUBLICATION_SHEET_IMPORT_STATUSES     — statuts du planning à importer (défaut "confirmé,réalisé" ; "*" = tous)
  PUBLICATION_VIDEO_IMPORT_STATUSES     — colonne Validation du tableau « Livraisons » (défaut "validé" ; "*" = toutes)
  PUBLICATION_SHEET_WRITEBACK_COLUMN    — colonne où écrire l'état de validation (défaut "Publication",
                                           créée si absente ; "" = aucun retour dans la feuille).
                                           La colonne « Statut » du planning n'est JAMAIS modifiée.
  PUBLICATION_VALIDATION_BASE_URL       — URL publique du front (ex. https://veille.exemple.gp)
  PUBLICATION_VALIDATION_TTL_HOURS      — durée de vie d'un lien (défaut 72)
  PUBLICATION_VALIDATION_NOTIFY_EMAILS  — destinataires des liens (défaut : EMAIL_ALERT_TO)
  PUBLICATION_VALIDATION_NOTIFY_TELEGRAM — 1 (défaut) : envoyer aussi le lien sur Telegram
"""

import os
import re
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from backend.services import crypto_service as crypto

logger = logging.getLogger("veille.publications")

COLLECTION = "pending_publications"

# ── Statuts ────────────────────────────────────────────────
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
PUBLISHED = "published"
PUBLISH_FAILED = "publish_failed"
EXPIRED = "expired"
CANCELLED = "cancelled"
ALL_STATUSES = [PENDING, APPROVED, REJECTED, PUBLISHED, PUBLISH_FAILED, EXPIRED, CANCELLED]

STATUS_LABELS_FR = {
    PENDING: "En attente de validation",
    APPROVED: "Validée",
    REJECTED: "Refusée",
    PUBLISHED: "Publiée",
    PUBLISH_FAILED: "Échec de publication",
    EXPIRED: "Lien expiré",
    CANCELLED: "Annulée",
}

# Statuts du planning à importer (normalisés), surchargés par PUBLICATION_SHEET_IMPORT_STATUSES
DEFAULT_IMPORT_STATUSES = ["confirme", "realise", "confirmee", "realisee"]

# En-têtes reconnus (normalisés : minuscules, sans accents, sans ponctuation).
# Calés sur le planning « Suivi hebdomadaire des prestataires audiovisuels » + alias génériques.
COLUMN_ALIASES: Dict[str, List[str]] = {
    "id": ["id", "ref", "reference", "n", "no", "ndeg", "num", "numero"],
    "title": ["evenement", "event", "titre", "title", "sujet", "objet", "accroche"],
    "text": ["precisions consignes", "precisions", "consignes", "texte", "text", "message", "contenu",
             "post", "publication", "legende", "corps", "description"],
    "date": ["date", "date de publication", "date publication", "quand", "echeance", "date souhaitee", "publier le"],
    "time": ["heure", "horaire", "time"],
    "location": ["lieu", "localisation", "adresse", "endroit"],
    "service": ["prestation necessaire", "prestation", "couverture", "type de prestation"],
    "provider": ["prestataire affecte", "prestataire", "affecte a", "couvert par"],
    "sheet_status": ["statut", "status", "etat", "suivi"],
    "source": ["source flyer", "source", "flyer", "visuel", "visuels", "media", "medias", "image", "images",
               "video", "videos", "photo", "photos", "lien media", "url media", "fichier", "fichiers", "lien", "liens"],
    "networks": ["reseaux", "reseau", "reseaux sociaux", "plateformes", "plateforme", "canaux", "canal",
                 "channels", "networks", "cibles", "ou publier"],
    "requester": ["demandeur", "auteur", "redacteur", "emetteur"],
    "requester_email": ["email", "e mail", "mail", "courriel", "contact"],
    "campaign": ["campagne", "campaign", "operation", "thematique"],
    "notes": ["notes", "note", "commentaire", "commentaires", "remarque", "remarques"],
}
HEADER_MARKERS = ["date", "evenement"]  # repère la ligne d'en-têtes dans un onglet du planning

# Tableau secondaire « Livraisons » (vidéos montées) : Vidéo | Prestataire | Validée le | Validation |
# Fichier reçu de Purevision | Envoi aux médias | Envoyé le | Lien WeTransfer | Retours / prochaine étape
VIDEO_ALIASES: Dict[str, List[str]] = {
    "title": ["video", "videos", "montage", "film", "livrable", "titre"],
    "provider": ["prestataire", "prestataire affecte", "realise par"],
    "validated_on": ["validee le", "valide le", "date de validation", "validation le"],
    "validation": ["validation", "valide", "statut", "status", "etat"],
    "file": ["fichier recu de purevision", "fichier recu", "fichier", "lien purevision", "purevision", "lien fichier"],
    "sent": ["envoi aux medias", "envoi", "diffusion"],
    "sent_on": ["envoye le", "envoyee le", "date d envoi"],
    "link": ["lien wetransfer", "wetransfer", "lien de telechargement", "lien"],
    "feedback": ["retours prochaine etape", "retours", "prochaine etape", "remarque", "remarques", "commentaire"],
}
DEFAULT_VIDEO_IMPORT_STATUSES = ["valide", "validee", "ok", "approuve", "approuvee"]

# Exceptions métier (le router les traduit en codes HTTP)
class TokenInvalid(Exception): ...
class TokenExpired(Exception): ...
class AlreadyDecided(Exception): ...
class NotFound(Exception): ...


# ── Helpers ────────────────────────────────────────────────

def _db():
    from backend.db import get_db
    return get_db()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """pymongo renvoie des datetimes naïfs (UTC) : on les rend comparables."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    dt = _as_utc(dt)
    return dt.isoformat() if dt else None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _ttl_hours() -> int:
    return max(1, _env_int("PUBLICATION_VALIDATION_TTL_HOURS", 72))


def _import_statuses() -> List[str]:
    raw = os.getenv("PUBLICATION_SHEET_IMPORT_STATUSES", "")
    if raw.strip() == "*":
        return ["*"]
    lst = [_norm(x) for x in raw.split(",") if x.strip()]
    return lst or DEFAULT_IMPORT_STATUSES


def _video_import_statuses() -> List[str]:
    raw = os.getenv("PUBLICATION_VIDEO_IMPORT_STATUSES", "")
    if raw.strip() == "*":
        return ["*"]
    lst = [_norm(x) for x in raw.split(",") if x.strip()]
    return lst or DEFAULT_VIDEO_IMPORT_STATUSES


_DIRECT_MEDIA_RE = re.compile(r"\.(jpe?g|png|gif|webp|mp4|mov|m4v|webm)(\?|$)", re.I)


def is_direct_media(url: str) -> bool:
    """URL de fichier exploitable par Cloudinary/Buffer (extension média, ou déjà Cloudinary).
    Les pages WeTransfer, Filemail, Drive… sont des liens, pas des médias."""
    u = (url or "").strip().lower()
    return u.startswith("http") and (bool(_DIRECT_MEDIA_RE.search(u)) or "res.cloudinary.com" in u)


def _writeback_column() -> str:
    return os.getenv("PUBLICATION_SHEET_WRITEBACK_COLUMN", "Publication").strip()


def _base_url() -> str:
    return (os.getenv("PUBLICATION_VALIDATION_BASE_URL") or os.getenv("FRONTEND_URL") or "").rstrip("/")


def validation_url(token: str) -> str:
    return f"{_base_url()}/valider/{token}"


def _norm(s: str) -> str:
    """Normalisation d'en-tête / de cellule : minuscules, sans accents ni ponctuation.
    Bibliothèque standard uniquement (pas d'unidecode : son absence rendait « Confirmé » → « confirm »
    et écartait silencieusement toutes les lignes)."""
    from backend.services.google_sheets_service import strip_accents
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(s or "").lower()).strip()


def _ip_hash(ip: Optional[str]) -> str:
    return hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else ""


def _split_list(cell: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,\n;|]+", cell or "") if p.strip()]


def _aad(doc_id: ObjectId) -> str:
    """Données authentifiées : lie chaque champ chiffré à son document (anti-permutation)."""
    return f"pending_publications/{doc_id}"


def _ensure_indexes(db) -> None:
    try:
        col = db[COLLECTION]
        col.create_index("token_hash", unique=True, sparse=True)
        col.create_index("fingerprint")
        col.create_index([("status_idx", 1), ("created_at", -1)])
    except Exception as e:
        logger.debug("index pending_publications : %s", e)


# ── (Dé)chiffrement d'un document ─────────────────────────

def _read(doc: Dict[str, Any], include_audit: bool = False) -> Dict[str, Any]:
    """Document Mongo → vue déchiffrée (jamais le jeton)."""
    aad = _aad(doc["_id"])
    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
    out = {
        "id": str(doc["_id"]),
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
        "source": doc.get("source"),
        "sheet_row": doc.get("sheet_row"),
        "sheet_tab": doc.get("sheet_tab"),
        "status": crypto.decrypt_str(doc.get("status_enc"), aad),
        "payload": payload,
        "decision": crypto.decrypt_json(doc.get("decision_enc"), aad, default=None),
        "publish": crypto.decrypt_json(doc.get("publish_enc"), aad, default=None),
        "seen": crypto.decrypt_json(doc.get("seen_enc"), aad, default=None),
        "token": {
            "active": bool(doc.get("token_hash")) and not doc.get("token_revoked"),
            "revoked": bool(doc.get("token_revoked")),
            "created_at": _iso(doc.get("token_created_at")),
            "expires_at": _iso(doc.get("token_expires_at")),
            "expired": bool(doc.get("token_expires_at")) and _as_utc(doc["token_expires_at"]) < _now(),
        },
        "key_version": doc.get("key_version"),
    }
    if include_audit:
        out["audit"] = crypto.decrypt_json(doc.get("audit_enc"), aad, default=[]) or []
    return out


def _set_status(db, doc: Dict[str, Any], status: str, extra: Optional[Dict[str, Any]] = None) -> None:
    aad = _aad(doc["_id"])
    update = {
        "status_enc": crypto.encrypt_str(status, aad),
        "status_idx": crypto.blind_index(status),
        "updated_at": _now(),
    }
    if extra:
        update.update(extra)
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)


def _append_audit(db, doc: Dict[str, Any], action: str, actor: str = "", ip: Optional[str] = None,
                  detail: Optional[str] = None) -> None:
    aad = _aad(doc["_id"])
    audit = crypto.decrypt_json(doc.get("audit_enc"), aad, default=[]) or []
    entry = {"at": _iso(_now()), "action": action, "actor": actor or "", "ip": _ip_hash(ip)}
    if detail:
        entry["detail"] = detail[:300]
    audit.append(entry)
    enc = crypto.encrypt_json(audit, aad)
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"audit_enc": enc}})
    doc["audit_enc"] = enc


def _issue_token(db, doc: Dict[str, Any], actor: str = "", ttl_hours: Optional[int] = None) -> str:
    """Génère un nouveau jeton (le précédent devient invalide). Renvoie le jeton en clair, une seule fois."""
    token = crypto.new_token(32)
    now = _now()
    update = {
        "token_hash": crypto.hash_token(token),
        "token_created_at": now,
        "token_expires_at": now + timedelta(hours=ttl_hours or _ttl_hours()),
        "token_revoked": False,
        "updated_at": now,
    }
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)
    _append_audit(db, doc, "token_issued", actor)
    return token


# ── Création ───────────────────────────────────────────────

def _clean_payload(p: Dict[str, Any]) -> Dict[str, Any]:
    text = str(p.get("text") or "").strip()
    title = str(p.get("title") or "").strip()
    if not text and not title:
        raise ValueError("Le texte de la publication est requis")
    media = p.get("media_urls") or []
    if isinstance(media, str):
        media = _split_list(media)
    networks = p.get("networks") or []
    if isinstance(networks, str):
        networks = _split_list(networks)
    hashtags = p.get("hashtags")
    if hashtags is None:
        hashtags = re.findall(r"#(\w+)", f"{title} {text}")
    return {
        "title": title[:300],
        "text": text[:5000],
        "hashtags": [str(h) for h in hashtags][:30],
        "media_urls": [str(m)[:1000] for m in media][:10],
        "networks": [str(n)[:50] for n in networks][:10],
        "scheduled_for": str(p.get("scheduled_for") or "")[:100],
        "requester": str(p.get("requester") or "")[:200],
        "requester_email": str(p.get("requester_email") or "")[:200],
        "campaign_id": str(p.get("campaign_id") or "")[:50],
        "campaign_name": str(p.get("campaign_name") or "")[:200],
        "notes": str(p.get("notes") or "")[:2000],
        "external_id": str(p.get("external_id") or "")[:100],
        "links": [str(u)[:1000] for u in (p.get("links") or [])][:10],
        "kind": str(p.get("kind") or "event")[:20],
        "location": str(p.get("location") or "")[:200],
        "event_time": str(p.get("event_time") or "")[:50],
        "service": str(p.get("service") or "")[:100],
        "provider": str(p.get("provider") or "")[:200],
    }


def create_pending(payload: Dict[str, Any], source: str = "manual", sheet_row: Optional[int] = None,
                   fingerprint: Optional[str] = None, actor: str = "", ttl_hours: Optional[int] = None,
                   notify: bool = True, sheet_tab: Optional[str] = None, sheet_writeback_col: Optional[int] = None,
                   db=None) -> Dict[str, Any]:
    """Crée une publication à valider. Renvoie {id, token, url, ...} — le jeton n'est
    JAMAIS récupérable ensuite (seule son empreinte est stockée)."""
    db = db if db is not None else _db()
    _ensure_indexes(db)
    clean = _clean_payload(payload)
    doc_id = ObjectId()
    aad = _aad(doc_id)
    now = _now()
    doc = {
        "_id": doc_id,
        "created_at": now,
        "updated_at": now,
        "source": source,
        "sheet_row": sheet_row,
        "sheet_tab": sheet_tab,
        "sheet_writeback_col": sheet_writeback_col,
        "fingerprint": fingerprint,
        "status_enc": crypto.encrypt_str(PENDING, aad),
        "status_idx": crypto.blind_index(PENDING),
        "payload_enc": crypto.encrypt_json(clean, aad),
        "decision_enc": None,
        "publish_enc": None,
        "audit_enc": crypto.encrypt_json([{"at": _iso(now), "action": "created", "actor": actor, "source": source}], aad),
        "token_hash": None,
        "token_revoked": False,
        "key_version": crypto.CURRENT_VERSION,
    }
    db[COLLECTION].insert_one(doc)
    token = _issue_token(db, doc, actor, ttl_hours)
    url = validation_url(token)
    logger.info("📝 Publication à valider créée (%s, source=%s)", doc_id, source)
    if notify:
        _notify_new_link(clean, url, doc)
    return {"id": str(doc_id), "token": token, "url": url, "expires_at": _iso(doc["token_expires_at"])}


# ── Lecture admin ──────────────────────────────────────────

def list_publications(status: Optional[str] = None, limit: int = 100, db=None) -> List[Dict[str, Any]]:
    db = db if db is not None else _db()
    q: Dict[str, Any] = {}
    if status:
        q["status_idx"] = crypto.blind_index(status)
    cur = db[COLLECTION].find(q).sort("created_at", -1).limit(max(1, min(limit, 500)))
    out = []
    for d in cur:
        try:
            out.append(_read(d))
        except ValueError:
            out.append({"id": str(d["_id"]), "created_at": _iso(d.get("created_at")), "status": "unreadable",
                        "payload": {}, "error": "Donnée chiffrée illisible (clé changée ?)"})
    return out


def get_publication(pub_id: str, db=None) -> Dict[str, Any]:
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    return _read(doc, include_audit=True)


def _find(db, pub_id: str) -> Dict[str, Any]:
    try:
        oid = ObjectId(pub_id)
    except Exception:
        raise NotFound("Identifiant invalide")
    doc = db[COLLECTION].find_one({"_id": oid})
    if not doc:
        raise NotFound("Publication introuvable")
    return doc


def counts(db=None) -> Dict[str, int]:
    db = db if db is not None else _db()
    return {s: db[COLLECTION].count_documents({"status_idx": crypto.blind_index(s)}) for s in ALL_STATUSES}


# ── Gestion des jetons (admin) ─────────────────────────────

def regenerate_token(pub_id: str, actor: str = "", ttl_hours: Optional[int] = None, notify: bool = False,
                     db=None) -> Dict[str, Any]:
    """Nouveau lien (l'ancien est invalidé). notify=True : renvoie le lien aux validateurs (Telegram / e-mail)."""
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    aad = _aad(doc["_id"])
    status = crypto.decrypt_str(doc.get("status_enc"), aad)
    if status in (EXPIRED,):
        _set_status(db, doc, PENDING)
    elif status != PENDING:
        raise AlreadyDecided(f"Publication déjà traitée ({STATUS_LABELS_FR.get(status, status)})")
    token = _issue_token(db, doc, actor, ttl_hours)
    url = validation_url(token)
    if notify:
        _notify_new_link(crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}, url, doc)
        _append_audit(db, doc, "link_sent", actor)
    return {"id": pub_id, "token": token, "url": url, "expires_at": _iso(doc["token_expires_at"])}


EDITABLE_FIELDS = ("title", "text", "networks", "scheduled_for", "requester", "requester_email",
                   "campaign_id", "campaign_name", "notes", "location", "event_time", "service", "provider", "links")


def update_publication(pub_id: str, changes: Dict[str, Any], actor: str = "", add_media: Optional[List[str]] = None,
                       remove_media: Optional[List[str]] = None, db=None) -> Dict[str, Any]:
    """Modifie le contenu d'une publication tant qu'elle n'est pas décidée (en attente ou lien expiré).
    `changes` : champs de EDITABLE_FIELDS (texte, titre, réseaux…) ; `add_media` : URL déjà hébergées à
    ajouter ; `remove_media` : URL à retirer. Le texte d'origine est conservé (original_text) et chaque
    modification est journalisée. Le lien en cours reste valable : la page du validateur lit la version à jour."""
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    aad = _aad(doc["_id"])
    status = crypto.decrypt_str(doc.get("status_enc"), aad)
    if status not in (PENDING, EXPIRED):
        raise AlreadyDecided(f"Modification impossible : {STATUS_LABELS_FR.get(status, status)}")
    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
    changed: List[str] = []

    for field in EDITABLE_FIELDS:
        if field not in changes or changes[field] is None:
            continue
        val = changes[field]
        if field in ("networks", "links"):
            val = _split_list(val) if isinstance(val, str) else [str(x) for x in (val or [])]
        else:
            val = str(val).strip()
        if payload.get(field, [] if field in ("networks", "links") else "") != val:
            if field == "text":
                payload.setdefault("original_text", payload.get("text", ""))
                payload["edited_by"] = actor
                payload["hashtags"] = re.findall(r"#(\w+)", f"{changes.get('title', payload.get('title', ''))} {val}")
            payload[field] = val
            changed.append(field)

    media = list(payload.get("media_urls", []))
    for u in remove_media or []:
        if u in media:
            media.remove(u)
            changed.append("media-")
    for u in add_media or []:
        if u and u not in media:
            media.append(u)
            changed.append("media+")
    payload["media_urls"] = media[:10]

    if not changed:
        return {"id": pub_id, "changed": [], "payload": payload}
    clean = _clean_payload({**payload, "hashtags": payload.get("hashtags")})
    # _clean_payload ne connaît pas les champs d'historique : on les remet
    for k in ("original_text", "edited_by"):
        if k in payload:
            clean[k] = payload[k]
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"payload_enc": crypto.encrypt_json(clean, aad),
                                                            "updated_at": _now()}})
    _append_audit(db, doc, "edited", actor, detail=", ".join(dict.fromkeys(changed)))
    logger.info("✏️ Publication %s modifiée (%s)", pub_id, ", ".join(dict.fromkeys(changed)))
    return {"id": pub_id, "changed": list(dict.fromkeys(changed)), "payload": clean}


def notify_existing_link(pub_id: str, url: str, actor: str = "", db=None) -> Dict[str, Any]:
    """Envoie le lien de validation fourni par le front (obtenu à la création) — après vérification
    qu'il correspond bien au jeton actif de cette publication (empreinte)."""
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    token = (url or "").rstrip("/").split("/")[-1]
    if not token or crypto.hash_token(token) != doc.get("token_hash") or doc.get("token_revoked"):
        raise ValueError("Ce lien ne correspond pas au jeton actif de la publication")
    aad = _aad(doc["_id"])
    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
    _notify_new_link(payload, validation_url(token), doc)
    _append_audit(db, doc, "link_sent", actor)
    return {"id": pub_id, "notified": True}


def revoke_token(pub_id: str, actor: str = "", db=None) -> None:
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"token_revoked": True, "updated_at": _now()}})
    _append_audit(db, doc, "token_revoked", actor)


def cancel_publication(pub_id: str, actor: str = "", db=None) -> None:
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    _set_status(db, doc, CANCELLED, {"token_revoked": True})
    _append_audit(db, doc, "cancelled", actor)
    _write_sheet_status(doc, CANCELLED)


def delete_publication(pub_id: str, db=None) -> None:
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    db[COLLECTION].delete_one({"_id": doc["_id"]})


# ── Accès par jeton (validateur) ───────────────────────────

def _find_by_token(db, token: str) -> Dict[str, Any]:
    if not token or len(token) < 20 or len(token) > 128:
        raise TokenInvalid("Lien invalide")
    doc = db[COLLECTION].find_one({"token_hash": crypto.hash_token(token)})
    if not doc:
        raise TokenInvalid("Lien invalide")
    if doc.get("token_revoked"):
        raise TokenInvalid("Lien révoqué")
    exp = _as_utc(doc.get("token_expires_at"))
    if exp and exp < _now():
        status = crypto.decrypt_str(doc.get("status_enc"), _aad(doc["_id"]))
        if status == PENDING:
            _set_status(db, doc, EXPIRED)
            _write_sheet_status(doc, EXPIRED)
        raise TokenExpired("Lien expiré")
    return doc


def get_by_token(token: str, ip: Optional[str] = None, db=None) -> Dict[str, Any]:
    """Vue validateur : contenu + état, sans données d'administration."""
    db = db if db is not None else _db()
    doc = _find_by_token(db, token)
    view = _read(doc)
    p = view["payload"]
    return {
        "id": view["id"],
        "status": view["status"],
        "status_label": STATUS_LABELS_FR.get(view["status"], view["status"]),
        "created_at": view["created_at"],
        "expires_at": view["token"]["expires_at"],
        "title": p.get("title", ""),
        "text": p.get("text", ""),
        "hashtags": p.get("hashtags", []),
        "media_urls": p.get("media_urls", []),
        "networks": p.get("networks", []),
        "scheduled_for": p.get("scheduled_for", ""),
        "requester": p.get("requester", ""),
        "campaign_name": p.get("campaign_name", ""),
        "notes": p.get("notes", ""),
        "links": p.get("links", []),
        "kind": p.get("kind", "event"),
        "location": p.get("location", ""),
        "event_time": p.get("event_time", ""),
        "service": p.get("service", ""),
        "provider": p.get("provider", ""),
        "decision": view["decision"],
        "publish": {"ok": (view["publish"] or {}).get("ok"), "published_at": (view["publish"] or {}).get("published_at"),
                    "platforms": (view["publish"] or {}).get("platforms")} if view["publish"] else None,
    }


def decide(token: str, decision: str, validator: str = "", comment: str = "", edited_text: Optional[str] = None,
           ip: Optional[str] = None, db=None) -> Dict[str, Any]:
    """Valide ou refuse. decision ∈ {"approve", "reject"}."""
    db = db if db is not None else _db()
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise ValueError("decision doit valoir approve ou reject")
    validator = (validator or "").strip()[:120]
    if not validator:
        raise ValueError("Le nom du validateur est requis")
    comment = (comment or "").strip()[:2000]

    doc = _find_by_token(db, token)
    aad = _aad(doc["_id"])
    status = crypto.decrypt_str(doc.get("status_enc"), aad)
    if status != PENDING:
        raise AlreadyDecided(f"Déjà traitée : {STATUS_LABELS_FR.get(status, status)}")

    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
    if edited_text is not None and edited_text.strip() and edited_text.strip() != payload.get("text", ""):
        payload["original_text"] = payload.get("text", "")
        payload["text"] = edited_text.strip()[:5000]
        payload["hashtags"] = re.findall(r"#(\w+)", f"{payload.get('title', '')} {payload['text']}")
        payload["edited_by"] = validator
        db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"payload_enc": crypto.encrypt_json(payload, aad)}})
        _append_audit(db, doc, "text_edited", validator, ip)

    record = {"decision": decision, "by": validator, "comment": comment, "at": _iso(_now()), "ip": _ip_hash(ip)}
    new_status = APPROVED if decision == "approve" else REJECTED
    # Le lien devient à usage unique : révoqué dès la décision.
    _set_status(db, doc, new_status, {"decision_enc": crypto.encrypt_json(record, aad), "token_revoked": True})
    _append_audit(db, doc, new_status, validator, ip, comment or None)

    result: Dict[str, Any] = {"id": str(doc["_id"]), "status": new_status, "status_label": STATUS_LABELS_FR[new_status]}

    if new_status == REJECTED:
        _write_sheet_status(doc, REJECTED, f"Refusée par {validator}" + (f" — {comment}" if comment else ""))
        _notify_decision(payload, record, new_status)
        return result

    _write_sheet_status(doc, APPROVED, f"Validée par {validator}")
    _notify_decision(payload, record, new_status)
    # Pas de publication automatique : un admin publie depuis /admin/publications.
    return result


# ── Publication Buffer ─────────────────────────────────────

def _compose_text(p: Dict[str, Any]) -> str:
    title, text = p.get("title", "").strip(), p.get("text", "").strip()
    body = f"{title}\n\n{text}" if title and text and not text.startswith(title) else (text or title)
    tags = [h for h in p.get("hashtags", []) if f"#{h}" not in body]
    if tags:
        body += "\n\n" + " ".join(f"#{h}" for h in tags)
    return body.strip()


def publish_now(pub_id: str, actor: str = "", extra_media_urls: Optional[List[str]] = None, db=None) -> Dict[str, Any]:
    """Publie une publication validée via Buffer (action manuelle d'un admin).
    extra_media_urls : médias déjà hébergés (ex. vidéo uploadée sur Cloudinary par l'admin) ajoutés au post."""
    db = db if db is not None else _db()
    doc = _find(db, pub_id)
    aad = _aad(doc["_id"])
    status = crypto.decrypt_str(doc.get("status_enc"), aad)
    if status not in (APPROVED, PUBLISH_FAILED):
        raise AlreadyDecided(f"Publication non publiable (statut : {STATUS_LABELS_FR.get(status, status)})")
    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}

    from backend.services.campaign_service import (publish_to_buffer, upload_to_cloudinary, save_post,
                                                    detect_campaign, get_campaign)

    text = _compose_text(payload)
    media_urls: List[str] = list(extra_media_urls or [])
    for url in payload.get("media_urls", []):
        if not is_direct_media(url):
            continue  # liens WeTransfer / Filemail / Drive : non exploitables par Buffer
        rtype = "video" if re.search(r"\.(mp4|mov|m4v|webm)(\?|$)", url, re.I) else "image"
        hosted = upload_to_cloudinary(url, rtype) or url
        media_urls.append(hosted)
    if not media_urls and (payload.get("links") or payload.get("kind") == "video"):
        logger.warning("Publication %s : aucun média direct (liens seulement) — post texte, ou joindre un fichier", pub_id)

    campaign_name, campaign_id = payload.get("campaign_name", ""), payload.get("campaign_id", "")
    try:
        if campaign_id:
            c = get_campaign(campaign_id, db=db)
            campaign_name = (c or {}).get("name", campaign_name)
        if not campaign_name:
            c = detect_campaign(text, db=db)
            campaign_name, campaign_id = (c or {}).get("name", "Institutionnel"), str((c or {}).get("_id", ""))
    except Exception as e:
        logger.debug("campagne : %s", e)

    res = publish_to_buffer(text=text, media_urls=media_urls, immediate=True)
    if not res.get("ok") and media_urls:
        import time as _t
        _t.sleep(3)
        res = publish_to_buffer(text=text, media_urls=media_urls, immediate=True)

    record = {
        "ok": bool(res.get("ok")),
        "published_at": _iso(_now()),
        "buffer_ids": res.get("buffer_ids", []),
        "platforms": res.get("profiles_count", 0),
        "error": None if res.get("ok") else str(res.get("error", ""))[:500],
        "skipped": res.get("skipped"),
        "actor": actor,
        "media_count": len(media_urls),
    }
    new_status = PUBLISHED if record["ok"] else PUBLISH_FAILED
    _set_status(db, doc, new_status, {"publish_enc": crypto.encrypt_json(record, aad)})
    _append_audit(db, doc, new_status, actor, detail=record["error"])

    if record["ok"]:
        try:
            title, body = payload.get("title", ""), payload.get("text", "")
            save_post({"title": title, "body": body, "hashtags": payload.get("hashtags", []),
                       "media_url": media_urls[0] if media_urls else "",
                       "media_type": "video" if media_urls and "video" in media_urls[0] else ("photo" if media_urls else "text"),
                       "campaign_id": campaign_id, "campaign_name": campaign_name,
                       "buffer_ids": record["buffer_ids"], "telegram_user": "", "source": "validation_sheet"}, db=db)
        except Exception as e:
            logger.warning("save_post après validation : %s", e)

    _write_sheet_status(doc, new_status, None if record["ok"] else record["error"])
    _notify_publish(payload, record)
    return {"id": pub_id, "status": new_status, "publish": record}


# ── Import depuis Google Sheets ────────────────────────────

def _map_headers(headers: List[str], aliases_map: Optional[Dict[str, List[str]]] = None) -> Dict[str, int]:
    """{champ: index de colonne} d'après COLUMN_ALIASES (ou un autre jeu d'alias).
    Passe 1 : en-tête égal à un alias. Passe 2 : en-tête contenant un alias (mot entier,
    ≥ 3 lettres) — ex. « Texte du post » → text, « Date de publication » → scheduled_for."""
    aliases_map = aliases_map or COLUMN_ALIASES
    norm = [_norm(h) for h in headers]
    mapping: Dict[str, int] = {}
    for field, aliases in aliases_map.items():
        for i, h in enumerate(norm):
            if h and h in aliases and i not in mapping.values():
                mapping[field] = i
                break
    for field, aliases in aliases_map.items():
        if field in mapping:
            continue
        for i, h in enumerate(norm):
            if not h or i in mapping.values():
                continue
            words = set(h.split())
            if any(len(a) >= 3 and (a in words or (" " in a and a in h)) for a in aliases):
                mapping[field] = i
                break
    return mapping


_URL_RE = re.compile(r"https?://[^\s,;|<>\"']+", re.I)


def _compose_from_planning(ev: str, date: str, time_: str, place: str, details: str) -> str:
    """Texte de post proposé au validateur à partir d'une ligne du planning (modifiable ensuite)."""
    head = " · ".join(x for x in [date, time_] if x and _norm(x) not in ("non precisee", "non precise", "a definir"))
    lines = []
    if head:
        lines.append(f"📅 {head}")
    if place and _norm(place) not in ("non precise", "a definir"):
        lines.append(f"📍 {place}")
    if details:
        lines.append("")
        lines.append(details)
    return "\n".join(lines).strip() or ev


def sync_from_sheet(notify: bool = True, db=None) -> Dict[str, Any]:
    """Lit tous les onglets du planning (un appel) et crée une publication à valider
    par événement nouveau dont le statut du planning est importable."""
    from backend.services import google_sheets_service as sheets
    if not sheets.is_configured():
        return {"ok": False, "error": "Google Sheets non configuré (GOOGLE_SERVICE_ACCOUNT_JSON, PUBLICATION_SHEET_ID)"}
    db = db if db is not None else _db()
    _ensure_indexes(db)

    tables = sheets.read_tables(header_markers=HEADER_MARKERS)
    statuses = _import_statuses()
    video_statuses = _video_import_statuses()
    wb_name = _writeback_column()
    created, skipped, superseded, errors, tabs_report = [], 0, 0, [], []
    skipped_reasons: Dict[str, int] = {}
    seen_statuses: Dict[str, int] = {}

    def _skip(reason: str) -> None:
        nonlocal skipped
        skipped += 1
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    def _supersede(tab: str, row_number: int) -> int:
        n = 0
        for old in db[COLLECTION].find({"sheet_tab": tab, "sheet_row": row_number, "source": "sheet",
                                        "status_idx": crypto.blind_index(PENDING)}):
            _set_status(db, old, CANCELLED, {"token_revoked": True})
            _append_audit(db, old, "superseded", "sheet-sync")
            n += 1
        return n

    for table in tables:
        tab = table["tab"]
        main_headers = table["headers"]
        mapping = _map_headers(main_headers)
        if "title" not in mapping and "text" not in mapping:
            tabs_report.append({"tab": tab, "skipped": "aucune colonne Événement/Texte", "headers": main_headers[:8]})
            continue
        wb_idx = None
        if wb_name:
            wb_idx = sheets.ensure_column(table, wb_name)
            if wb_idx is None:
                errors.append({"tab": tab, "error": f"impossible de créer la colonne « {wb_name} »"})
        tab_created, tab_videos = 0, 0

        def _already_marked(row: Dict[str, Any], headers: List[str]) -> bool:
            # colonne de retour renseignée → déjà traitée (le bloc principal porte l'en-tête ; les
            # blocs secondaires n'ont pas cet en-tête mais partagent la colonne : on lit la cellule brute)
            if wb_idx is None:
                return False
            if wb_idx < len(headers) and headers[wb_idx]:
                return bool(row["values"].get(headers[wb_idx], ""))
            raw = row.get("raw") or []
            return wb_idx < len(raw) and bool(raw[wb_idx])

        for block in table.get("blocks") or [{"kind": "main", "headers": main_headers, "rows": table["rows"]}]:
            headers, rows = block["headers"], block["rows"]
            if block["kind"] == "main":
                bmap = mapping
            else:
                bmap = _map_headers(headers, VIDEO_ALIASES)
                if "title" not in bmap or "validation" not in bmap:
                    continue  # ex. tableau des téléchargements par destinataire : pas une livraison

            def cell(row: Dict[str, Any], field: str, _m=bmap, _h=headers) -> str:
                idx = _m.get(field)
                if idx is None or idx >= len(_h):
                    return ""
                return row["values"].get(_h[idx], "")

            for row in rows:
                try:
                    if _already_marked(row, headers):
                        _skip("deja_traitee")
                        continue
                    if block["kind"] == "main":
                        title, details = cell(row, "title"), cell(row, "text")
                        if not title and not details:
                            _skip("ligne_vide")  # ligne de date pré-remplie, ou titre de section
                            continue
                        st = _norm(cell(row, "sheet_status"))
                        seen_statuses[st or "(vide)"] = seen_statuses.get(st or "(vide)", 0) + 1
                        if statuses != ["*"] and "sheet_status" in bmap and st not in statuses:
                            _skip(f"statut:{st or '(vide)'}")
                            continue
                        date, time_, place = cell(row, "date"), cell(row, "time"), cell(row, "location")
                        source = cell(row, "source")
                        extra_details = row["values"].get(f"{headers[bmap['text']]} (2)", "") if "text" in bmap else ""
                        fp = crypto.fingerprint(sheets.sheet_id(), tab, row["row_number"], title, details, extra_details,
                                                date, time_, place, source)
                        if db[COLLECTION].find_one({"fingerprint": fp}, {"_id": 1}):
                            _skip("deja_importee")
                            continue
                        superseded += _supersede(tab, row["row_number"])
                        urls = _URL_RE.findall(source)
                        media = [u for u in urls if is_direct_media(u)]
                        links = [u for u in urls if not is_direct_media(u)]
                        notes_parts = [x for x in [
                            f"Prestation : {cell(row, 'service')}" if cell(row, "service") else "",
                            f"Prestataire : {cell(row, 'provider')}" if cell(row, "provider") else "",
                            f"Source : {source}" if source and not urls else "",
                            extra_details, cell(row, "notes"),
                        ] if x]
                        payload = {
                            "kind": "event", "title": title or details[:120],
                            "text": _compose_from_planning(title, date, time_, place, details),
                            "media_urls": media, "links": links, "networks": cell(row, "networks"),
                            "scheduled_for": " · ".join(x for x in [date, time_] if x),
                            "location": place, "event_time": time_, "service": cell(row, "service"),
                            "provider": cell(row, "provider"), "requester": cell(row, "requester"),
                            "requester_email": cell(row, "requester_email"), "campaign_name": cell(row, "campaign"),
                            "notes": " · ".join(notes_parts), "external_id": cell(row, "id"),
                        }
                    else:
                        title = cell(row, "title")
                        if not title or _norm(title) in ("total", "totaux"):
                            _skip("ligne_vide")
                            continue
                        st = _norm(cell(row, "validation"))
                        if video_statuses != ["*"] and st not in video_statuses:
                            _skip(f"video_validation:{st or '(vide)'}")
                            continue
                        provider, validated_on = cell(row, "provider"), cell(row, "validated_on")
                        file_url, link_url, feedback = cell(row, "file"), cell(row, "link"), cell(row, "feedback")
                        fp = crypto.fingerprint(sheets.sheet_id(), tab, row["row_number"], title, provider,
                                                validated_on, file_url, link_url)
                        if db[COLLECTION].find_one({"fingerprint": fp}, {"_id": 1}):
                            _skip("deja_importee")
                            continue
                        superseded += _supersede(tab, row["row_number"])
                        urls = _URL_RE.findall(" ".join([file_url, link_url]))
                        media = [u for u in urls if is_direct_media(u)]
                        links = [u for u in urls if not is_direct_media(u)]
                        text_lines = [f"🎬 Vidéo réalisée par {provider}" if provider else "🎬 Vidéo"]
                        notes_parts = [x for x in [
                            f"Vidéo validée le {validated_on}" if validated_on else "",
                            f"Envoi aux médias : {cell(row, 'sent')} {cell(row, 'sent_on')}".strip() if cell(row, "sent") else "",
                            f"Retours : {feedback}" if feedback else "",
                            "Le fichier vidéo doit être joint au moment de publier (liens WeTransfer / Purevision non exploitables directement)."
                            if links and not media else "",
                        ] if x]
                        payload = {
                            "kind": "video", "title": title, "text": "\n".join(text_lines),
                            "media_urls": media, "links": links, "provider": provider,
                            "service": "Vidéo", "scheduled_for": f"Validée le {validated_on}" if validated_on else "",
                            "notes": " · ".join(notes_parts),
                        }
                    res = create_pending(payload, source="sheet", sheet_row=row["row_number"], sheet_tab=tab,
                                         sheet_writeback_col=wb_idx, fingerprint=fp, actor="sheet-sync",
                                         notify=notify, db=db)
                    created.append({"id": res["id"], "tab": tab, "row": row["row_number"], "title": payload["title"][:80],
                                    "kind": payload["kind"]})
                    tab_created += 1
                    tab_videos += payload["kind"] == "video"
                    if wb_idx is not None:
                        sheets.write_cell(row["row_number"], wb_idx, STATUS_LABELS_FR[PENDING], tab=tab)
                except Exception as e:
                    logger.warning("%s ligne %s : %s", tab, row.get("row_number"), e)
                    errors.append({"tab": tab, "row": row.get("row_number"), "error": str(e)[:200]})
        tabs_report.append({"tab": tab, "rows": len(table["rows"]), "blocks": len(table.get("blocks") or []),
                            "created": tab_created, "videos": tab_videos,
                            "mapping": {k: main_headers[v] for k, v in mapping.items()}})

    logger.info("📋 Sync planning : %d onglets, %d créées, %d ignorées, %d remplacées, %d erreurs",
                len(tables), len(created), skipped, superseded, len(errors))
    return {"ok": True, "tabs": tabs_report, "created": created, "skipped": skipped,
            "skipped_reasons": skipped_reasons, "statuses_seen": seen_statuses,
            "superseded": superseded, "errors": errors, "import_statuses": statuses,
            "video_import_statuses": video_statuses, "writeback_column": wb_name}


def _write_sheet_status(doc: Dict[str, Any], status: str, detail: Optional[str] = None) -> None:
    """Retour d'état dans la colonne de validation du planning (jamais dans « Statut »)."""
    if doc.get("source") != "sheet" or not doc.get("sheet_row") or doc.get("sheet_writeback_col") is None:
        return
    try:
        from backend.services import google_sheets_service as sheets
        if not sheets.is_configured():
            return
        label = STATUS_LABELS_FR.get(status, status)
        if detail:
            label = f"{label} — {detail}"[:200]
        sheets.write_cell(int(doc["sheet_row"]), int(doc["sheet_writeback_col"]), label, tab=doc.get("sheet_tab"))
    except Exception as e:
        logger.debug("retour feuille : %s", e)


def expire_stale(db=None) -> int:
    """Passe en « expiré » les demandes en attente dont le lien est périmé."""
    db = db if db is not None else _db()
    n = 0
    for doc in db[COLLECTION].find({"status_idx": crypto.blind_index(PENDING), "token_expires_at": {"$lt": _now()}}):
        _set_status(db, doc, EXPIRED)
        _append_audit(db, doc, "expired", "scheduler")
        _write_sheet_status(doc, EXPIRED)
        n += 1
    return n


# ── Notifications ──────────────────────────────────────────

def _notify_emails() -> List[str]:
    raw = os.getenv("PUBLICATION_VALIDATION_NOTIFY_EMAILS", "")
    lst = [e.strip() for e in raw.split(",") if "@" in e]
    if lst:
        return lst
    try:
        from backend.services.email_service import recipients
        return recipients()
    except Exception:
        return []


def _telegram_enabled() -> bool:
    return os.getenv("PUBLICATION_VALIDATION_NOTIFY_TELEGRAM", "1").strip() not in ("0", "false", "no", "off")


def _notify_new_link(p: Dict[str, Any], url: str, doc: Dict[str, Any]) -> None:
    """Envoie le lien de validation. Volontairement minimal : titre + lien, pas le texte."""
    title = p.get("title") or (p.get("text", "")[:60] + "…")
    exp = _iso(doc.get("token_expires_at")) or ""
    try:
        if _telegram_enabled():
            from backend.services.telegram_service import send_message
            import html
            send_message(f"📝 <b>Publication à valider</b>\n{html.escape(title)}\n"
                         f"Demandeur : {html.escape(p.get('requester') or '—')}\n"
                         f"🔐 {html.escape(url)}\n<i>Lien valable jusqu'au {exp[:16].replace('T', ' ')} UTC</i>")
    except Exception as e:
        logger.debug("telegram : %s", e)
    try:
        to = _notify_emails()
        if to:
            from backend.services.email_service import send_email
            import html
            send_email(
                f"[Validation] {title[:80]}",
                f"<p>Une publication attend votre validation.</p><p><b>{html.escape(title)}</b><br>"
                f"Demandeur : {html.escape(p.get('requester') or '—')}</p>"
                f"<p><a href=\"{html.escape(url)}\">Ouvrir la page de validation</a></p>"
                f"<p style=\"color:#777;font-size:12px\">Lien personnel, valable jusqu'au {exp[:16].replace('T', ' ')} UTC. "
                f"Ne le transférez pas.</p>",
                text_content=f"Publication à valider : {title}\n{url}\nValable jusqu'au {exp}", to=to)
    except Exception as e:
        logger.debug("email : %s", e)


def _notify_decision(p: Dict[str, Any], record: Dict[str, Any], status: str) -> None:
    try:
        if _telegram_enabled():
            from backend.services.telegram_service import send_message
            import html
            emoji = "✅" if status == APPROVED else "❌"
            title = p.get("title") or p.get("text", "")[:60]
            msg = f"{emoji} <b>{STATUS_LABELS_FR[status]}</b> — {html.escape(title)}\nPar : {html.escape(record.get('by', ''))}"
            if record.get("comment"):
                msg += f"\n💬 {html.escape(record['comment'][:300])}"
            if status == APPROVED:
                msg += "\n👉 À publier manuellement depuis /admin/publications"
            send_message(msg)
    except Exception as e:
        logger.debug("telegram décision : %s", e)


def _notify_publish(p: Dict[str, Any], record: Dict[str, Any]) -> None:
    try:
        if _telegram_enabled():
            from backend.services.telegram_service import send_message
            import html
            title = p.get("title") or p.get("text", "")[:60]
            if record.get("ok"):
                send_message(f"📤 <b>Publiée</b> sur {record.get('platforms', 0)} réseau(x) — {html.escape(title)}")
            else:
                send_message(f"⚠️ <b>Échec de publication</b> — {html.escape(title)}\n{html.escape(str(record.get('error'))[:300])}")
    except Exception as e:
        logger.debug("telegram publication : %s", e)


def status_report() -> Dict[str, Any]:
    from backend.services import google_sheets_service as sheets
    buffer_ok = bool(os.getenv("BUFFER_ACCESS_TOKEN"))
    try:
        from backend.services.campaign_service import cloudinary_configured, LAST_UPLOAD_ERROR
        cloud = {"configured": cloudinary_configured(), "last_error": LAST_UPLOAD_ERROR.get("error"),
                 "last_error_at": LAST_UPLOAD_ERROR.get("at")}
    except Exception as e:
        cloud = {"configured": False, "last_error": str(e)[:100]}
    return {
        "cloudinary": cloud,
        "encryption": crypto.status(),
        "sheet": sheets.status(),
        "buffer_configured": buffer_ok,
        "ttl_hours": _ttl_hours(),
        "base_url": _base_url() or "(relatif)",
        "notify_emails": len(_notify_emails()),
        "notify_telegram": _telegram_enabled(),
        "import_statuses": _import_statuses(),
        "video_import_statuses": _video_import_statuses(),
        "writeback_column": _writeback_column() or None,
        "social_check": _social_check_status(),
    }


def _social_check_status() -> Dict[str, Any]:
    try:
        from backend.services import publication_social_check_service as sc
        return {"accounts": sc.own_accounts(), "threshold": sc.threshold(), "days": sc.window_days(),
                "last": sc.last_run()}
    except Exception as e:
        return {"error": str(e)[:100]}
