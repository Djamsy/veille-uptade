# backend/services/media_library_service.py
"""
Médiathèque de l'Espace Publications : visuels pré-enregistrés (logos, bandeaux, lieux,
portraits…) que n'importe quel admin dépose une fois et que tout le monde sélectionne
ensuite en un clic dans une publication.

Collection `media_library` (métadonnées en clair : ce ne sont pas des contenus sensibles,
les fichiers eux-mêmes sont hébergés sur Cloudinary comme les autres médias) :
  { name, tags[], url, kind: image|video, bytes, width, height, uploaded_by, created_at,
    updated_at, uses, last_used_at }
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

logger = logging.getLogger("veille.publications.library")

COLLECTION = "media_library"
FAMILIES = ["logo", "bandeau", "evenement", "lieu", "elu", "autre"]


def _db():
    from backend.db import get_db
    return get_db()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_tag(t: str) -> str:
    from backend.services.google_sheets_service import strip_accents
    return " ".join(strip_accents(str(t or "")).lower().replace("_", " ").split())[:40]


def normalize_tags(tags: Any) -> List[str]:
    if isinstance(tags, str):
        tags = tags.replace(";", ",").split(",")
    out: List[str] = []
    for t in tags or []:
        n = _norm_tag(t)
        if n and n not in out:
            out.append(n)
    return out[:20]


def _view(doc: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    for k in ("created_at", "updated_at", "last_used_at"):
        v = d.get(k)
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _ensure_indexes(db) -> None:
    try:
        db[COLLECTION].create_index("url", unique=True)
        db[COLLECTION].create_index("tags")
        db[COLLECTION].create_index([("created_at", -1)])
    except Exception as e:
        logger.debug("index media_library : %s", e)


def add_media(url: str, name: str, tags: Any = None, kind: str = "image", size_bytes: int = 0,
              width: Optional[int] = None, height: Optional[int] = None, uploaded_by: str = "", db=None) -> Dict[str, Any]:
    db = db if db is not None else _db()
    _ensure_indexes(db)
    if not url:
        raise ValueError("URL du média requise")
    name = (name or "").strip()[:120] or url.split("/")[-1].split("?")[0][:120]
    now = _now()
    doc = {"name": name, "tags": normalize_tags(tags), "url": url, "kind": "video" if kind == "video" else "image",
           "bytes": int(size_bytes or 0), "width": width, "height": height, "uploaded_by": uploaded_by,
           "created_at": now, "updated_at": now, "uses": 0, "last_used_at": None}
    existing = db[COLLECTION].find_one({"url": url})
    if existing:
        return _view(existing)
    res = db[COLLECTION].insert_one(doc)
    doc["_id"] = res.inserted_id
    logger.info("🖼 Médiathèque : « %s » ajouté par %s (%s)", name, uploaded_by, doc["kind"])
    return _view(doc)


def list_media(tag: Optional[str] = None, q: Optional[str] = None, limit: int = 300, db=None) -> List[Dict[str, Any]]:
    db = db if db is not None else _db()
    query: Dict[str, Any] = {}
    if tag:
        query["tags"] = _norm_tag(tag)
    docs = list(db[COLLECTION].find(query).sort([("uses", -1), ("created_at", -1)]).limit(max(1, min(limit, 1000))))
    if q:
        nq = _norm_tag(q)
        docs = [d for d in docs if nq in _norm_tag(d.get("name", "")) or any(nq in t for t in d.get("tags", []))]
    return [_view(d) for d in docs]


def tag_counts(db=None) -> Dict[str, int]:
    db = db if db is not None else _db()
    counts: Dict[str, int] = {}
    for d in db[COLLECTION].find({}, {"tags": 1}):
        for t in d.get("tags", []):
            counts[t] = counts.get(t, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def update_media(media_id: str, name: Optional[str] = None, tags: Any = None, db=None) -> Dict[str, Any]:
    db = db if db is not None else _db()
    try:
        oid = ObjectId(media_id)
    except Exception:
        raise ValueError("Identifiant invalide")
    update: Dict[str, Any] = {"updated_at": _now()}
    if name is not None:
        update["name"] = str(name).strip()[:120]
    if tags is not None:
        update["tags"] = normalize_tags(tags)
    res = db[COLLECTION].find_one_and_update({"_id": oid}, {"$set": update}, return_document=True)
    if not res:
        raise ValueError("Média introuvable")
    return _view(res)


def delete_media(media_id: str, db=None) -> bool:
    db = db if db is not None else _db()
    try:
        oid = ObjectId(media_id)
    except Exception:
        raise ValueError("Identifiant invalide")
    return db[COLLECTION].delete_one({"_id": oid}).deleted_count == 1


def resolve_ids(ids: List[str], db=None) -> List[str]:
    """Identifiants → URL (ordre conservé) et compteur d'utilisation incrémenté."""
    db = db if db is not None else _db()
    urls: List[str] = []
    oids = []
    for i in ids or []:
        try:
            oids.append(ObjectId(str(i)))
        except Exception:
            continue
    if not oids:
        return urls
    by_id = {d["_id"]: d for d in db[COLLECTION].find({"_id": {"$in": oids}})}
    for oid in oids:
        d = by_id.get(oid)
        if d and d.get("url") and d["url"] not in urls:
            urls.append(d["url"])
    if urls:
        db[COLLECTION].update_many({"_id": {"$in": [o for o in oids if o in by_id]}},
                                   {"$inc": {"uses": 1}, "$set": {"last_used_at": _now()}})
    return urls


def stats(db=None) -> Dict[str, Any]:
    db = db if db is not None else _db()
    return {"count": db[COLLECTION].count_documents({}), "tags": tag_counts(db)}
