# backend/admin_routes.py
"""
Routes d'administration pour le pilotage manuel des affaires.
Permet de fusionner, séparer, lier/délier des articles, reclassifier.

Rôles :
- admin   : toutes les actions
- editor  : merge, link, unlink, reclassify (pas de suppression)
- viewer  : lecture seule (pas d'accès à ces routes)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from bson import ObjectId
import os

logger = logging.getLogger("admin_routes")
router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Auth ──────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_service = None


def set_service(service):
    global _service
    _service = service


def _svc():
    if _service is None:
        raise HTTPException(503, "AffairLifecycleService non disponible")
    return _service


def _get_db():
    from pymongo import MongoClient
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "veille_media")
    client = MongoClient(MONGO_URL)
    return client[MONGO_DB_NAME]


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Décode le JWT et retourne l'utilisateur."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(401, "Token invalide")
    except JWTError:
        raise HTTPException(401, "Token invalide ou expiré")

    db = _get_db()
    user = db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(401, "Utilisateur non trouvé")

    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "user"),
    }


def require_role(*allowed_roles):
    """Dependency : vérifie que l'utilisateur a un rôle autorisé."""
    async def check(user: Dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                403,
                f"Rôle '{user['role']}' non autorisé. Requis : {', '.join(allowed_roles)}"
            )
        return user
    return check


# ══════════════════════════════════════════════════════════════
#  GESTION DES UTILISATEURS (admin uniquement)
# ══════════════════════════════════════════════════════════════

@router.get("/users")
async def list_users(user: Dict = Depends(require_role("admin"))):
    """Liste tous les utilisateurs avec leurs rôles."""
    db = _get_db()
    users = list(db["users"].find({}, {
        "password_hash": 0,  # Ne JAMAIS exposer le hash
    }).sort("created_at", -1))

    for u in users:
        u["_id"] = str(u["_id"])

    return {"users": users, "total": len(users)}


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    admin: Dict = Depends(require_role("admin")),
):
    """Change le rôle d'un utilisateur. Rôles valides : admin, editor, viewer, user."""
    new_role = payload.get("role", "").strip().lower()
    valid_roles = {"admin", "editor", "viewer", "user"}

    if new_role not in valid_roles:
        raise HTTPException(400, f"Rôle invalide. Valides : {', '.join(sorted(valid_roles))}")

    # Empêcher de se retirer son propre rôle admin
    if user_id == admin["id"] and new_role != "admin":
        raise HTTPException(400, "Impossible de retirer votre propre rôle admin")

    db = _get_db()
    try:
        result = db["users"].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"role": new_role, "role_updated_at": datetime.now(timezone.utc).isoformat(),
                       "role_updated_by": admin["email"]}}
        )
    except Exception:
        raise HTTPException(400, "ID utilisateur invalide")

    if result.modified_count == 0:
        raise HTTPException(404, "Utilisateur non trouvé")

    return {"success": True, "user_id": user_id, "new_role": new_role}


# ══════════════════════════════════════════════════════════════
#  PILOTAGE MANUEL DES AFFAIRES
# ══════════════════════════════════════════════════════════════

@router.post("/affairs/merge")
async def merge_affairs(
    payload: Dict[str, Any] = Body(...),
    user: Dict = Depends(require_role("admin", "editor")),
):
    """
    Fusionner 2+ affaires en une seule.
    Body : { "keep_id": "...", "merge_ids": ["...", "..."], "reason": "optionnel" }
    L'affaire keep_id absorbe les autres.
    """
    svc = _svc()
    keep_id = payload.get("keep_id", "").strip()
    merge_ids = [m.strip() for m in payload.get("merge_ids", []) if m and m.strip()]
    reason = payload.get("reason", "Fusion manuelle")

    if not keep_id or not merge_ids:
        raise HTTPException(400, "keep_id et merge_ids requis")
    if keep_id in merge_ids:
        raise HTTPException(400, "keep_id ne peut pas être dans merge_ids")

    try:
        keep_affair = svc.affairs.find_one({"_id": ObjectId(keep_id)})
    except Exception:
        raise HTTPException(400, "keep_id invalide")
    if not keep_affair:
        raise HTTPException(404, f"Affaire {keep_id} non trouvée")

    merged_count = 0
    for mid in merge_ids:
        try:
            source = svc.affairs.find_one({"_id": ObjectId(mid)})
        except Exception:
            continue
        if not source:
            continue

        # Transférer les articles, radio, social
        svc.affairs.update_one(
            {"_id": ObjectId(keep_id)},
            {
                "$addToSet": {
                    "articles": {"$each": source.get("articles", [])},
                    "radio_transcriptions": {"$each": source.get("radio_transcriptions", [])},
                    "social_posts": {"$each": source.get("social_posts", [])},
                    "sources": {"$each": source.get("sources", [])},
                },
                "$inc": {"item_count": source.get("item_count", 0)},
                "$max": {"gravity_score": source.get("gravity_score", 0)},
                "$set": {"last_activity": datetime.now(timezone.utc)},
            }
        )
        # Archiver l'affaire source
        svc.affairs.update_one(
            {"_id": ObjectId(mid)},
            {"$set": {
                "status": "archived",
                "archived_at": datetime.now(timezone.utc),
                "_merged_into": keep_id,
                "_merged_by": user["email"],
            }}
        )
        # Timeline
        svc.timeline.insert_one({
            "affair_id": keep_id,
            "event": "manual_merge",
            "details": {
                "merged_from": mid,
                "merged_title": source.get("title", ""),
                "reason": reason,
                "by": user["email"],
            },
            "timestamp": datetime.now(timezone.utc),
        })
        merged_count += 1

    # Recalculer BMG
    updated = svc.affairs.find_one({"_id": ObjectId(keep_id)})
    if updated:
        bmg = svc.calculate_bmg(updated)
        svc.affairs.update_one(
            {"_id": ObjectId(keep_id)},
            {"$set": {"bmg": bmg.get("bmg", 0), "bmg_details": bmg}}
        )

    return {"success": True, "merged": merged_count, "keep_id": keep_id}


@router.post("/affairs/split")
async def split_affair(
    payload: Dict[str, Any] = Body(...),
    user: Dict = Depends(require_role("admin", "editor")),
):
    """
    Séparer des articles d'une affaire pour créer une nouvelle affaire.
    Body : { "source_id": "...", "article_ids": ["..."], "new_title": "..." }
    """
    svc = _svc()
    source_id = payload.get("source_id", "").strip()
    article_ids = [a.strip() for a in payload.get("article_ids", []) if a and a.strip()]
    new_title = payload.get("new_title", "").strip()

    if not source_id or not article_ids:
        raise HTTPException(400, "source_id et article_ids requis")

    try:
        source = svc.affairs.find_one({"_id": ObjectId(source_id)})
    except Exception:
        raise HTTPException(400, "source_id invalide")
    if not source:
        raise HTTPException(404, "Affaire source non trouvée")

    # Vérifier que les articles existent dans l'affaire source
    existing_articles = set(source.get("articles", []))
    valid_ids = [a for a in article_ids if a in existing_articles]
    if not valid_ids:
        raise HTTPException(400, "Aucun des article_ids n'appartient à cette affaire")

    # Récupérer le premier article pour les métadonnées
    first_art = None
    try:
        first_art = svc.articles.find_one({"_id": ObjectId(valid_ids[0])})
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    new_affair = {
        "title": new_title or (first_art.get("title", "Nouvelle affaire") if first_art else "Affaire séparée"),
        "description": first_art.get("ai_summary", "")[:300] if first_art else "",
        "primary_entity": None,
        "entities": list(set(e.lower() for e in (first_art or {}).get("elected", []) + (first_art or {}).get("institutions", []) if e)),
        "elected": (first_art or {}).get("elected", []),
        "institutions": (first_art or {}).get("institutions", []),
        "theme": (first_art or {}).get("theme", "general"),
        "gravity_score": (first_art or {}).get("gravity_score", 0.5),
        "affair_type": "fait_divers",
        "priority": "minor",
        "sentiment": (first_art or {}).get("sentiment", "neutre"),
        "sentiment_history": [(first_art or {}).get("sentiment", "neutre")],
        "status": "active",
        "articles": valid_ids,
        "radio_transcriptions": [],
        "social_posts": [],
        "sources": [first_art.get("source", "")] if first_art else [],
        "source_types": ["article"],
        "item_count": len(valid_ids),
        "created_at": now,
        "last_activity": now,
        "promoted_at": now,
        "bmg": 0, "bmg_details": {}, "bmg_history": [],
        "_creation_method": "manual_split",
        "_split_from": source_id,
        "_split_by": user["email"],
    }

    result = svc.affairs.insert_one(new_affair)
    new_id = str(result.inserted_id)

    # Retirer les articles de l'affaire source
    svc.affairs.update_one(
        {"_id": ObjectId(source_id)},
        {
            "$pull": {"articles": {"$in": valid_ids}},
            "$inc": {"item_count": -len(valid_ids)},
        }
    )

    # Mettre à jour les articles pour pointer vers la nouvelle affaire
    for aid in valid_ids:
        try:
            svc.articles.update_one(
                {"_id": ObjectId(aid)},
                {"$set": {"_affair_id": new_id}}
            )
        except Exception:
            pass

    # Timeline
    svc.timeline.insert_one({
        "affair_id": source_id,
        "event": "manual_split",
        "details": {
            "new_affair_id": new_id,
            "articles_moved": valid_ids,
            "by": user["email"],
        },
        "timestamp": now,
    })
    svc.timeline.insert_one({
        "affair_id": new_id,
        "event": "created",
        "details": {"method": "manual_split", "from": source_id, "by": user["email"]},
        "timestamp": now,
    })

    return {"success": True, "new_affair_id": new_id, "articles_moved": len(valid_ids)}


@router.post("/affairs/link-article")
async def link_article_to_affair(
    payload: Dict[str, Any] = Body(...),
    user: Dict = Depends(require_role("admin", "editor")),
):
    """
    Lier manuellement un article à une affaire.
    Body : { "affair_id": "...", "article_id": "..." }
    """
    svc = _svc()
    affair_id = payload.get("affair_id", "").strip()
    article_id = payload.get("article_id", "").strip()

    if not affair_id or not article_id:
        raise HTTPException(400, "affair_id et article_id requis")

    try:
        affair = svc.affairs.find_one({"_id": ObjectId(affair_id)})
    except Exception:
        raise HTTPException(400, "affair_id invalide")
    if not affair:
        raise HTTPException(404, "Affaire non trouvée")

    try:
        article = svc.articles.find_one({"_id": ObjectId(article_id)})
    except Exception:
        raise HTTPException(400, "article_id invalide")
    if not article:
        raise HTTPException(404, "Article non trouvé")

    # Ajouter l'article
    svc.affairs.update_one(
        {"_id": ObjectId(affair_id)},
        {
            "$addToSet": {
                "articles": article_id,
                "sources": article.get("source", ""),
            },
            "$inc": {"item_count": 1},
            "$max": {"gravity_score": article.get("gravity_score", 0)},
            "$set": {"last_activity": datetime.now(timezone.utc)},
        }
    )

    # Marquer l'article comme traité
    svc.articles.update_one(
        {"_id": ObjectId(article_id)},
        {"$set": {"_affair_processed": True, "_affair_id": affair_id,
                  "_linked_manually": True, "_linked_by": user["email"]}}
    )

    svc.timeline.insert_one({
        "affair_id": affair_id,
        "event": "manual_link",
        "details": {
            "article_id": article_id,
            "article_title": article.get("title", ""),
            "by": user["email"],
        },
        "timestamp": datetime.now(timezone.utc),
    })

    return {"success": True, "affair_id": affair_id, "article_id": article_id}


@router.post("/affairs/unlink-article")
async def unlink_article_from_affair(
    payload: Dict[str, Any] = Body(...),
    user: Dict = Depends(require_role("admin", "editor")),
):
    """
    Délier un article d'une affaire (le remettre en orphelin).
    Body : { "affair_id": "...", "article_id": "..." }
    """
    svc = _svc()
    affair_id = payload.get("affair_id", "").strip()
    article_id = payload.get("article_id", "").strip()

    if not affair_id or not article_id:
        raise HTTPException(400, "affair_id et article_id requis")

    # Retirer l'article de l'affaire
    svc.affairs.update_one(
        {"_id": ObjectId(affair_id)},
        {
            "$pull": {"articles": article_id},
            "$inc": {"item_count": -1},
            "$set": {"last_activity": datetime.now(timezone.utc)},
        }
    )

    # Remettre l'article comme non traité
    svc.articles.update_one(
        {"_id": ObjectId(article_id)},
        {"$set": {"_affair_processed": False, "_affair_id": None,
                  "_unlinked_manually": True, "_unlinked_by": user["email"]}}
    )

    svc.timeline.insert_one({
        "affair_id": affair_id,
        "event": "manual_unlink",
        "details": {"article_id": article_id, "by": user["email"]},
        "timestamp": datetime.now(timezone.utc),
    })

    return {"success": True}


@router.put("/affairs/{affair_id}/reclassify")
async def reclassify_affair(
    affair_id: str,
    payload: Dict[str, Any] = Body(...),
    user: Dict = Depends(require_role("admin", "editor")),
):
    """
    Reclassifier une affaire (titre, thème, priorité, statut, entités).
    Body : { "title": "...", "theme": "...", "priority": "hot|watch|minor",
             "status": "active|stale|archived", "entities": [...] }
    """
    svc = _svc()

    try:
        affair = svc.affairs.find_one({"_id": ObjectId(affair_id)})
    except Exception:
        raise HTTPException(400, "affair_id invalide")
    if not affair:
        raise HTTPException(404, "Affaire non trouvée")

    updates = {}
    if "title" in payload and payload["title"].strip():
        updates["title"] = payload["title"].strip()[:200]
    if "theme" in payload:
        updates["theme"] = payload["theme"]
    if "priority" in payload and payload["priority"] in ("hot", "watch", "minor"):
        updates["priority"] = payload["priority"]
    if "status" in payload and payload["status"] in ("active", "stale", "archived"):
        updates["status"] = payload["status"]
        if payload["status"] == "archived":
            updates["archived_at"] = datetime.now(timezone.utc)
    if "entities" in payload and isinstance(payload["entities"], list):
        updates["entities"] = payload["entities"][:20]
    if "elected" in payload and isinstance(payload["elected"], list):
        updates["elected"] = payload["elected"][:10]

    if not updates:
        raise HTTPException(400, "Aucun champ à modifier")

    updates["_last_manual_edit"] = datetime.now(timezone.utc).isoformat()
    updates["_last_edited_by"] = user["email"]

    svc.affairs.update_one({"_id": ObjectId(affair_id)}, {"$set": updates})

    # Timeline
    svc.timeline.insert_one({
        "affair_id": affair_id,
        "event": "manual_reclassify",
        "details": {"changes": updates, "by": user["email"]},
        "timestamp": datetime.now(timezone.utc),
    })

    return {"success": True, "affair_id": affair_id, "updated_fields": list(updates.keys())}


@router.get("/articles/orphans")
async def list_orphan_articles(
    limit: int = 50,
    user: Dict = Depends(require_role("admin", "editor", "viewer")),
):
    """Liste les articles enrichis non affiliés à une affaire (orphelins)."""
    svc = _svc()
    orphans = list(svc.articles.find(
        {
            "_analysis_method": {"$exists": True},
            "$or": [
                {"_affair_processed": {"$exists": False}},
                {"_affair_processed": False},
                {"_affair_ignored": True},
            ],
        },
        {
            "title": 1, "source": 1, "theme": 1, "gravity_score": 1,
            "sentiment": 1, "elected": 1, "institutions": 1,
            "scraped_at": 1, "url": 1,
        }
    ).sort("scraped_at", -1).limit(limit))

    for a in orphans:
        a["_id"] = str(a["_id"])
        if hasattr(a.get("scraped_at"), "isoformat"):
            a["scraped_at"] = a["scraped_at"].isoformat()

    return {"orphans": orphans, "total": len(orphans)}


@router.get("/affairs/active-summary")
async def active_affairs_summary(
    user: Dict = Depends(require_role("admin", "editor", "viewer")),
):
    """Résumé compact des affaires actives pour la UI admin."""
    svc = _svc()
    affairs = list(svc.affairs.find(
        {"status": {"$in": ["active", "stale"]}},
        {
            "title": 1, "gravity_score": 1, "priority": 1, "status": 1,
            "theme": 1, "item_count": 1, "articles": 1, "bmg": 1,
            "created_at": 1, "last_activity": 1, "entities": 1,
            "elected": 1, "sentiment": 1,
        }
    ).sort("gravity_score", -1))

    for a in affairs:
        a["_id"] = str(a["_id"])
        for k in ("created_at", "last_activity"):
            if hasattr(a.get(k), "isoformat"):
                a[k] = a[k].isoformat()

    return {"affairs": affairs, "total": len(affairs)}


@router.post("/affairs/{affair_id}/archive")
async def archive_affair(
    affair_id: str,
    user: Dict = Depends(require_role("admin")),
):
    """Archiver manuellement une affaire."""
    svc = _svc()
    try:
        result = svc.affairs.update_one(
            {"_id": ObjectId(affair_id)},
            {"$set": {
                "status": "archived",
                "archived_at": datetime.now(timezone.utc),
                "_archived_by": user["email"],
            }}
        )
    except Exception:
        raise HTTPException(400, "affair_id invalide")

    if result.modified_count == 0:
        raise HTTPException(404, "Affaire non trouvée")

    svc.timeline.insert_one({
        "affair_id": affair_id,
        "event": "manual_archive",
        "details": {"by": user["email"]},
        "timestamp": datetime.now(timezone.utc),
    })

    return {"success": True}


@router.get("/activity-log")
async def activity_log(
    limit: int = 50,
    user: Dict = Depends(require_role("admin", "editor", "viewer")),
):
    """Journal des actions manuelles récentes."""
    svc = _svc()
    manual_events = list(svc.timeline.find(
        {"event": {"$regex": "^manual_"}},
    ).sort("timestamp", -1).limit(limit))

    for e in manual_events:
        e["_id"] = str(e["_id"])
        if hasattr(e.get("timestamp"), "isoformat"):
            e["timestamp"] = e["timestamp"].isoformat()

    return {"events": manual_events, "total": len(manual_events)}
