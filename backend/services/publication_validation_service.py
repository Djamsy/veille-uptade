# backend/services/publication_validation_service.py
"""
Publications « pour validation » — contenu chiffré de bout en bout côté stockage.

Flux :
  1. Un tableau Google Sheets (ou un admin, à la main) décrit une publication.
  2. Le service crée un document `pending_publications` dont TOUT le contenu
     sensible est chiffré (AES-256-GCM, voir crypto_service) : titre, texte,
     médias, réseaux, demandeur, statut, décision, résultat de publication, journal.
     Restent en clair : identifiant, dates, source, numéro de ligne, empreintes.
  3. Un jeton de validation (256 bits, non devinable) est généré. Seule son
     empreinte HMAC est stockée. Le lien /valider/<jeton> est envoyé aux
     validateurs (Telegram / e-mail Brevo) — il n'est jamais réaffiché ensuite.
  4. Le validateur consulte, corrige éventuellement le texte, valide ou refuse.
  5. Validée → publication Buffer (immédiate par défaut) ; statut écrit en retour
     dans la feuille ; notification.

Configuration (variables d'environnement) :
  PUBLICATION_ENCRYPTION_KEY            — voir crypto_service.py (obligatoire en prod)
  GOOGLE_SERVICE_ACCOUNT_JSON / PUBLICATION_SHEET_ID / PUBLICATION_SHEET_TAB — voir google_sheets_service.py
  PUBLICATION_VALIDATION_BASE_URL       — URL publique du front (ex. https://veille.exemple.gp)
  PUBLICATION_VALIDATION_TTL_HOURS      — durée de vie d'un lien (défaut 72)
  PUBLICATION_AUTO_PUBLISH              — 1 (défaut) : publier dès validation ; 0 : attendre un admin
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

# Valeurs du tableau considérées comme « à importer »
IMPORTABLE_STATUS_CELLS = {"", "a valider", "avalider", "en attente", "pending", "nouveau", "new", "a publier", "apublier"}

# En-têtes reconnus (normalisés : minuscules, sans accents, sans ponctuation)
COLUMN_ALIASES: Dict[str, List[str]] = {
    "id": ["id", "ref", "reference", "n", "no", "ndeg", "num", "numero"],
    "title": ["titre", "title", "sujet", "objet", "accroche"],
    "text": ["texte", "text", "message", "contenu", "post", "publication", "legende", "corps", "description"],
    "media": ["media", "medias", "image", "images", "video", "videos", "visuel", "visuels", "photo", "photos",
              "lien media", "url media", "fichier", "fichiers", "lien", "liens"],
    "networks": ["reseaux", "reseau", "reseaux sociaux", "plateformes", "plateforme", "canaux", "canal",
                 "channels", "networks", "cibles", "ou publier"],
    "scheduled_for": ["date", "date de publication", "date publication", "quand", "programmation",
                      "echeance", "date souhaitee", "publier le"],
    "requester": ["demandeur", "auteur", "nom", "redacteur", "service", "direction", "de", "emetteur"],
    "requester_email": ["email", "e mail", "mail", "courriel", "contact"],
    "campaign": ["campagne", "campaign", "evenement", "operation", "thematique"],
    "status": ["statut", "status", "etat", "validation", "etat validation", "suivi"],
    "notes": ["notes", "note", "commentaire", "commentaires", "remarque", "remarques", "consignes"],
}

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


def auto_publish_enabled() -> bool:
    return os.getenv("PUBLICATION_AUTO_PUBLISH", "1").strip() not in ("0", "false", "no", "off")


def _base_url() -> str:
    return (os.getenv("PUBLICATION_VALIDATION_BASE_URL") or os.getenv("FRONTEND_URL") or "").rstrip("/")


def validation_url(token: str) -> str:
    return f"{_base_url()}/valider/{token}"


def _norm(s: str) -> str:
    """Normalisation d'en-tête / de cellule : minuscules, sans accents ni ponctuation."""
    try:
        from unidecode import unidecode
        s = unidecode(s or "")
    except Exception:
        s = s or ""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


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
        "status": crypto.decrypt_str(doc.get("status_enc"), aad),
        "payload": payload,
        "decision": crypto.decrypt_json(doc.get("decision_enc"), aad, default=None),
        "publish": crypto.decrypt_json(doc.get("publish_enc"), aad, default=None),
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
    }


def create_pending(payload: Dict[str, Any], source: str = "manual", sheet_row: Optional[int] = None,
                   fingerprint: Optional[str] = None, actor: str = "", ttl_hours: Optional[int] = None,
                   notify: bool = True, db=None) -> Dict[str, Any]:
    """Crée une publication à valider. Renvoie {id, token, url, ...} — le jeton n'est
    JAMAIS récupérable ensuite (seule son empreinte est stockée)."""
    db = db or _db()
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
    db = db or _db()
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
    db = db or _db()
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
    db = db or _db()
    return {s: db[COLLECTION].count_documents({"status_idx": crypto.blind_index(s)}) for s in ALL_STATUSES}


# ── Gestion des jetons (admin) ─────────────────────────────

def regenerate_token(pub_id: str, actor: str = "", ttl_hours: Optional[int] = None, db=None) -> Dict[str, Any]:
    db = db or _db()
    doc = _find(db, pub_id)
    status = crypto.decrypt_str(doc.get("status_enc"), _aad(doc["_id"]))
    if status in (EXPIRED,):
        _set_status(db, doc, PENDING)
    elif status != PENDING:
        raise AlreadyDecided(f"Publication déjà traitée ({STATUS_LABELS_FR.get(status, status)})")
    token = _issue_token(db, doc, actor, ttl_hours)
    return {"id": pub_id, "token": token, "url": validation_url(token), "expires_at": _iso(doc["token_expires_at"])}


def revoke_token(pub_id: str, actor: str = "", db=None) -> None:
    db = db or _db()
    doc = _find(db, pub_id)
    db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"token_revoked": True, "updated_at": _now()}})
    _append_audit(db, doc, "token_revoked", actor)


def cancel_publication(pub_id: str, actor: str = "", db=None) -> None:
    db = db or _db()
    doc = _find(db, pub_id)
    _set_status(db, doc, CANCELLED, {"token_revoked": True})
    _append_audit(db, doc, "cancelled", actor)
    _write_sheet_status(doc, CANCELLED)


def delete_publication(pub_id: str, db=None) -> None:
    db = db or _db()
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
    db = db or _db()
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
        "decision": view["decision"],
        "publish": {"ok": (view["publish"] or {}).get("ok"), "published_at": (view["publish"] or {}).get("published_at"),
                    "platforms": (view["publish"] or {}).get("platforms")} if view["publish"] else None,
        "auto_publish": auto_publish_enabled(),
    }


def decide(token: str, decision: str, validator: str = "", comment: str = "", edited_text: Optional[str] = None,
           ip: Optional[str] = None, db=None) -> Dict[str, Any]:
    """Valide ou refuse. decision ∈ {"approve", "reject"}."""
    db = db or _db()
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
    if auto_publish_enabled():
        pub = publish_now(str(doc["_id"]), actor=f"auto après validation par {validator}", db=db)
        result.update({"status": pub["status"], "status_label": STATUS_LABELS_FR[pub["status"]], "publish": pub.get("publish")})
    return result


# ── Publication Buffer ─────────────────────────────────────

def _compose_text(p: Dict[str, Any]) -> str:
    title, text = p.get("title", "").strip(), p.get("text", "").strip()
    body = f"{title}\n\n{text}" if title and text and not text.startswith(title) else (text or title)
    tags = [h for h in p.get("hashtags", []) if f"#{h}" not in body]
    if tags:
        body += "\n\n" + " ".join(f"#{h}" for h in tags)
    return body.strip()


def publish_now(pub_id: str, actor: str = "", db=None) -> Dict[str, Any]:
    """Publie une publication validée via Buffer (admin ou auto)."""
    db = db or _db()
    doc = _find(db, pub_id)
    aad = _aad(doc["_id"])
    status = crypto.decrypt_str(doc.get("status_enc"), aad)
    if status not in (APPROVED, PUBLISH_FAILED):
        raise AlreadyDecided(f"Publication non publiable (statut : {STATUS_LABELS_FR.get(status, status)})")
    payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}

    from backend.services.campaign_service import (publish_to_buffer, upload_to_cloudinary, save_post,
                                                    detect_campaign, get_campaign)

    text = _compose_text(payload)
    media_urls: List[str] = []
    for url in payload.get("media_urls", []):
        if not url.lower().startswith("http"):
            continue
        rtype = "video" if re.search(r"\.(mp4|mov|m4v|webm)(\?|$)", url, re.I) else "image"
        hosted = upload_to_cloudinary(url, rtype) or url
        media_urls.append(hosted)

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

def _map_headers(headers: List[str]) -> Dict[str, int]:
    """{champ: index de colonne} d'après COLUMN_ALIASES.
    Passe 1 : en-tête égal à un alias. Passe 2 : en-tête contenant un alias (mot entier,
    ≥ 3 lettres) — ex. « Texte du post » → text, « Date de publication » → scheduled_for."""
    norm = [_norm(h) for h in headers]
    mapping: Dict[str, int] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for i, h in enumerate(norm):
            if h and h in aliases and i not in mapping.values():
                mapping[field] = i
                break
    for field, aliases in COLUMN_ALIASES.items():
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


def sync_from_sheet(notify: bool = True, db=None) -> Dict[str, Any]:
    """Lit le tableau et crée une publication à valider par nouvelle ligne."""
    from backend.services import google_sheets_service as sheets
    if not sheets.is_configured():
        return {"ok": False, "error": "Google Sheets non configuré (GOOGLE_SERVICE_ACCOUNT_JSON, PUBLICATION_SHEET_ID)"}
    db = db or _db()
    _ensure_indexes(db)

    table = sheets.read_table()
    headers, rows = table["headers"], table["rows"]
    mapping = _map_headers(headers)
    if "text" not in mapping:
        return {"ok": False, "error": f"Colonne texte introuvable. En-têtes lus : {headers}", "mapping": mapping}

    def cell(row: Dict[str, Any], field: str) -> str:
        idx = mapping.get(field)
        if idx is None or idx >= len(headers):
            return ""
        return row["values"].get(headers[idx], "")

    created, skipped, superseded, errors = [], 0, 0, []
    for row in rows:
        try:
            text, title = cell(row, "text"), cell(row, "title")
            if not text and not title:
                skipped += 1
                continue
            if _norm(cell(row, "status")) not in IMPORTABLE_STATUS_CELLS:
                skipped += 1
                continue
            fp = crypto.fingerprint(sheets.sheet_id(), table["tab"], row["row_number"], title, text,
                                    cell(row, "media"), cell(row, "networks"), cell(row, "scheduled_for"))
            if db[COLLECTION].find_one({"fingerprint": fp}, {"_id": 1}):
                skipped += 1
                continue
            # Même ligne, contenu modifié → l'ancienne demande en attente est annulée
            for old in db[COLLECTION].find({"sheet_row": row["row_number"], "source": "sheet",
                                            "status_idx": crypto.blind_index(PENDING)}):
                _set_status(db, old, CANCELLED, {"token_revoked": True})
                _append_audit(db, old, "superseded", "sheet-sync")
                superseded += 1

            res = create_pending({
                "title": title, "text": text, "media_urls": cell(row, "media"), "networks": cell(row, "networks"),
                "scheduled_for": cell(row, "scheduled_for"), "requester": cell(row, "requester"),
                "requester_email": cell(row, "requester_email"), "campaign_name": cell(row, "campaign"),
                "notes": cell(row, "notes"), "external_id": cell(row, "id"),
            }, source="sheet", sheet_row=row["row_number"], fingerprint=fp, actor="sheet-sync",
                notify=notify, db=db)
            created.append({"id": res["id"], "row": row["row_number"]})
            if "status" in mapping:
                sheets.write_cell(row["row_number"], mapping["status"], STATUS_LABELS_FR[PENDING], tab=table["tab"])
        except Exception as e:
            logger.warning("Ligne %s : %s", row.get("row_number"), e)
            errors.append({"row": row.get("row_number"), "error": str(e)[:200]})

    logger.info("📋 Sync feuille : %d créées, %d ignorées, %d remplacées, %d erreurs",
                len(created), skipped, superseded, len(errors))
    return {"ok": True, "tab": table["tab"], "rows": len(rows), "created": created, "skipped": skipped,
            "superseded": superseded, "errors": errors, "mapping": {k: headers[v] for k, v in mapping.items()}}


def _write_sheet_status(doc: Dict[str, Any], status: str, detail: Optional[str] = None) -> None:
    """Retour d'état dans la feuille (si la ligne vient de la feuille et qu'une colonne statut existe)."""
    if doc.get("source") != "sheet" or not doc.get("sheet_row"):
        return
    try:
        from backend.services import google_sheets_service as sheets
        if not sheets.is_configured():
            return
        table = sheets.read_table()
        mapping = _map_headers(table["headers"])
        if "status" not in mapping:
            return
        label = STATUS_LABELS_FR.get(status, status)
        if detail:
            label = f"{label} — {detail}"[:200]
        sheets.write_cell(int(doc["sheet_row"]), mapping["status"], label, tab=table["tab"])
    except Exception as e:
        logger.debug("retour feuille : %s", e)


def expire_stale(db=None) -> int:
    """Passe en « expiré » les demandes en attente dont le lien est périmé."""
    db = db or _db()
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
    return {
        "encryption": crypto.status(),
        "sheet": sheets.status(),
        "buffer_configured": buffer_ok,
        "auto_publish": auto_publish_enabled(),
        "ttl_hours": _ttl_hours(),
        "base_url": _base_url() or "(relatif)",
        "notify_emails": len(_notify_emails()),
        "notify_telegram": _telegram_enabled(),
    }
