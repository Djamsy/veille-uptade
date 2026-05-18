from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import os
import logging

from collections import defaultdict, deque
import time as _time

from fastapi import APIRouter, Depends, HTTPException, Request, status, Body
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pymongo import MongoClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])  # ✅ CORRECTION ICI

# ── Rate-limit dédié au login (anti brute-force) ──────────────
# Buckets séparés par IP et par email-cible. 10 essais / 15 min chacun.
_LOGIN_WINDOW = 900        # 15 minutes
_LOGIN_MAX_PER_IP = 10
_LOGIN_MAX_PER_EMAIL = 10
_login_ip_attempts: Dict[str, deque] = defaultdict(deque)
_login_email_attempts: Dict[str, deque] = defaultdict(deque)

# Hash factice pour neutraliser le timing-attack quand l'email n'existe pas.
# bcrypt sur cette valeur prend ~250ms — même latence qu'une vraie comparaison.
_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuMh7TyM5p9w6f3kKDjxhz1qP6c7K0vO."

def _check_login_rate_limit(ip: str, email: str) -> None:
    """Lève HTTPException 429 si trop d'essais récents pour cette IP ou cet email."""
    now = _time.time()
    cutoff = now - _LOGIN_WINDOW
    for bucket, max_count, label in (
        (_login_ip_attempts[ip], _LOGIN_MAX_PER_IP, "IP"),
        (_login_email_attempts[email], _LOGIN_MAX_PER_EMAIL, "email"),
    ):
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_count:
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives ({label}). Réessayer dans 15 minutes.",
                headers={"Retry-After": str(_LOGIN_WINDOW)},
            )

def _record_login_attempt(ip: str, email: str) -> None:
    now = _time.time()
    _login_ip_attempts[ip].append(now)
    _login_email_attempts[email].append(now)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY or SECRET_KEY == "dev-secret-change-me":
    # Sécurité : on refuse de démarrer avec un secret faible/par défaut.
    # Définir JWT_SECRET dans l'environnement (Render: Environment Variables).
    raise RuntimeError(
        "JWT_SECRET environment variable is required and must not be the default value. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# Contexte de chiffrement
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Singleton MongoClient — évite le leak de connexions sous charge
_mongo_client: Optional[MongoClient] = None

def get_db():
    """Connexion MongoDB (singleton)."""
    global _mongo_client
    if _mongo_client is None:
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        _mongo_client = MongoClient(MONGO_URL)
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "veille_media")
    return _mongo_client[MONGO_DB_NAME]

def create_access_token(data: Dict[str, Any]) -> str:
    """Créer un token JWT avec exp et iat."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.update({
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/register")
def register(user: Dict[str, Any] = Body(...)):
    """Inscription utilisateur"""
    email = user.get("email", "").strip().lower()
    password = user.get("password", "")
    name = user.get("name", "").strip()

    if not email or not password:
        raise HTTPException(400, "email et password requis")

    db = get_db()
    users_col = db["users"]

    if users_col.find_one({"email": email}):
        raise HTTPException(409, "Email déjà utilisé")

    # Tronquer le mot de passe à 72 bytes avant hashing
    password_truncated = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')

    doc = {
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": pwd_context.hash(password_truncated),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "role": "user",
        "active": True,
    }

    result = users_col.insert_one(doc)

    return {
        "success": True,
        "user": {
            "id": str(result.inserted_id),
            "email": email,
            "name": doc["name"]
        }
    }


@router.post("/init-admin")
def init_admin(payload: Dict[str, Any] = Body(...)):
    """Créer le premier compte admin. Ne fonctionne que s'il n'y a aucun admin en base.

    Protection : exige le header X-Bootstrap-Token == os.getenv("BOOTSTRAP_TOKEN")
    dès lors que BOOTSTRAP_TOKEN est défini. Empêche un attaquant de
    revendiquer le rôle admin si la collection users est vide ou réinitialisée.
    """
    bootstrap_token_expected = os.getenv("BOOTSTRAP_TOKEN", "")
    if bootstrap_token_expected:
        provided = payload.get("bootstrap_token", "")
        import hmac as _hmac
        if not _hmac.compare_digest(provided, bootstrap_token_expected):
            raise HTTPException(401, "Bootstrap token invalide")

    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    name = payload.get("name", "").strip()

    if not email or not password:
        raise HTTPException(400, "email et password requis")

    db = get_db()
    users_col = db["users"]

    # Bloquer si un admin existe déjà
    existing_admin = users_col.find_one({"role": "admin"})
    if existing_admin:
        raise HTTPException(403, "Un admin existe déjà. Utilisez /register puis promouvez via l'interface admin.")

    # Supprimer un éventuel compte existant avec cet email (pour upgrader un compte user)
    users_col.delete_one({"email": email})

    password_truncated = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')

    doc = {
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": pwd_context.hash(password_truncated),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "role": "admin",
        "active": True,
    }

    result = users_col.insert_one(doc)
    token = create_access_token({"sub": email, "role": "admin"})

    return {
        "success": True,
        "message": "Compte admin créé avec succès",
        "access_token": token,
        "token": token,
        "user": {
            "id": str(result.inserted_id),
            "email": email,
            "name": doc["name"],
            "role": "admin",
        }
    }

@router.post("/login")
def login(payload: Dict[str, Any] = Body(...), request: Request = None):
    """Connexion utilisateur — rate-limited + constant-time."""
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if not email or not password:
        raise HTTPException(400, "Email et password requis")

    # Rate-limit dédié AVANT tout work (évite que le brute-force épuise le CPU bcrypt)
    client_ip = (request.client.host if request and request.client else "unknown")
    _check_login_rate_limit(client_ip, email)

    # ✅ Tronquer AVANT tout traitement (bcrypt limite à 72 bytes)
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        password = password_bytes.decode('utf-8', errors='ignore')

    db = get_db()
    users_col = db["users"]
    user = users_col.find_one({"email": email})

    # ── Constant-time : toujours appeler pwd_context.verify ──
    # Si l'utilisateur n'existe pas, on vérifie contre un hash factice
    # pour ne pas révéler l'existence du compte par mesure de latence.
    target_hash = user.get("password_hash") if user else _DUMMY_HASH
    try:
        password_ok = pwd_context.verify(password, target_hash)
    except ValueError as e:
        logger.error(f"Hash bcrypt invalide pour {email}: {e}")
        password_ok = False

    if not user or not password_ok:
        _record_login_attempt(client_ip, email)
        raise HTTPException(401, "Identifiants invalides")

    user_role = user.get("role", "user")
    token = create_access_token({"sub": user["email"], "role": user_role})

    return {
        "success": True,
        "access_token": token,
        "token": token,  # compat avec le frontend existant
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "name": user.get("name", ""),
            "role": user_role,
        }
    }
@router.get("/me")
async def me(token: str = Depends(oauth2_scheme)):
    """Informations utilisateur connecté"""
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True, "require_sub": True, "verify_exp": True},
        )
        email = payload.get("sub")
        
        db = get_db()
        user = db["users"].find_one({"email": email})
        
        if not user:
            raise HTTPException(401, "Utilisateur non trouvé")
            
        return {
            "success": True,
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "name": user.get("name", ""),
                "role": user.get("role", "user")
            }
        }
    except JWTError:
        raise HTTPException(401, "Token invalide")


# ============================================================
# CRÉATION DE COMPTES PAR UN ADMIN
# ============================================================

def _require_admin_auth(token: str = Depends(oauth2_scheme)):
    """Vérifie que l'appelant est admin."""
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True, "require_sub": True, "verify_exp": True},
        )
        email = payload.get("sub")
        role = payload.get("role", "user")
    except JWTError:
        raise HTTPException(401, "Token invalide ou expiré")
    if role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    db = get_db()
    user = db["users"].find_one({"email": email})
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return {"email": email, "role": "admin"}


# Alias public — à utiliser dans les autres modules
# from auth_routes import require_admin
# @app.post("/...")(admin: dict = Depends(require_admin))
require_admin = _require_admin_auth


@router.post("/create-user")
def admin_create_user(
    payload: Dict[str, Any] = Body(...),
    admin: dict = Depends(_require_admin_auth),
):
    """Crée un compte utilisateur avec le rôle souhaité. (Admin uniquement)"""
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    name = payload.get("name", "").strip()
    role = payload.get("role", "viewer")

    if not email or not password:
        raise HTTPException(400, "email et password requis")

    if role not in ("admin", "editor", "viewer", "user"):
        raise HTTPException(400, "Rôle invalide. Valides : admin, editor, viewer, user")

    if len(password) < 6:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 6 caractères")

    db = get_db()
    users_col = db["users"]

    if users_col.find_one({"email": email}):
        raise HTTPException(409, "Email déjà utilisé")

    password_truncated = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')

    doc = {
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": pwd_context.hash(password_truncated),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin["email"],
        "role": role,
        "active": True,
    }

    result = users_col.insert_one(doc)

    logger.info(f"👤 Compte créé par admin {admin['email']}: {email} (rôle: {role})")

    return {
        "success": True,
        "user": {
            "id": str(result.inserted_id),
            "email": email,
            "name": doc["name"],
            "role": role,
        }
    }


@router.delete("/delete-user/{user_id}")
def admin_delete_user(
    user_id: str,
    admin: dict = Depends(_require_admin_auth),
):
    """Supprime un compte utilisateur. (Admin uniquement)"""
    from bson import ObjectId
    db = get_db()
    users_col = db["users"]

    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        raise HTTPException(400, "ID invalide")

    if not user:
        raise HTTPException(404, "Utilisateur non trouvé")

    # Empêcher la suppression du dernier admin
    if user.get("role") == "admin":
        admin_count = users_col.count_documents({"role": "admin"})
        if admin_count <= 1:
            raise HTTPException(400, "Impossible de supprimer le dernier administrateur")

    users_col.delete_one({"_id": ObjectId(user_id)})
    logger.info(f"👤 Compte supprimé par admin {admin['email']}: {user.get('email')}")

    return {"success": True, "message": f"Utilisateur {user.get('email')} supprimé"}


@router.put("/change-password")
def change_password(
    payload: Dict[str, Any] = Body(...),
    token: str = Depends(oauth2_scheme),
):
    """Permet à un utilisateur connecté de changer son mot de passe."""
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = decoded.get("sub")
    except JWTError:
        raise HTTPException(401, "Token invalide ou expiré")

    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")

    if not current_password or not new_password:
        raise HTTPException(400, "Ancien et nouveau mot de passe requis")
    if len(new_password) < 6:
        raise HTTPException(400, "Le nouveau mot de passe doit contenir au moins 6 caractères")

    db = get_db()
    users_col = db["users"]
    user = users_col.find_one({"email": email})

    if not user:
        raise HTTPException(404, "Utilisateur non trouvé")

    # Vérifier l'ancien mot de passe
    current_truncated = current_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    try:
        if not pwd_context.verify(current_truncated, user.get("password_hash", "")):
            raise HTTPException(401, "Mot de passe actuel incorrect")
    except ValueError:
        raise HTTPException(401, "Mot de passe actuel incorrect")

    # Hasher et sauvegarder le nouveau
    new_truncated = new_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    new_hash = pwd_context.hash(new_truncated)
    users_col.update_one({"email": email}, {"$set": {"password_hash": new_hash}})

    logger.info(f"🔑 Mot de passe changé pour {email}")
    return {"success": True, "message": "Mot de passe mis à jour"}


@router.get("/system-health")
def system_health(admin: dict = Depends(_require_admin_auth)):
    """Retourne l'état de santé du système (Admin uniquement)."""
    from datetime import datetime, timezone
    db = get_db()

    now = datetime.now(timezone.utc)

    # Dernier scraping
    last_article = db["articles_guadeloupe"].find_one(sort=[("scraped_at", -1)])
    last_scrape = last_article.get("scraped_at") if last_article else None

    # Dernier enrichissement
    last_enriched = db["articles_guadeloupe"].find_one(
        {"enriched": True}, sort=[("enriched_at", -1)]
    )
    last_enrich = last_enriched.get("enriched_at") if last_enriched else None

    # Stats scheduler
    last_log = db["scheduler_logs"].find_one(sort=[("timestamp", -1)])
    last_scheduler = last_log.get("timestamp") if last_log else None
    scheduler_status = last_log.get("status") if last_log else "unknown"

    # Dernière radio
    last_radio = db["radio_transcriptions"].find_one(sort=[("captured_at", -1)])
    last_radio_at = last_radio.get("captured_at") if last_radio else None

    # Dernier rapport PDF
    last_report = db["daily_reports"].find_one(sort=[("generated_at", -1)])
    last_report_at = last_report.get("generated_at") if last_report else None

    # Compteurs
    total_articles = db["articles_guadeloupe"].estimated_document_count()
    total_affairs = db["affairs"].count_documents({"status": "active"})
    total_radio = db["radio_transcriptions"].estimated_document_count()
    total_social = db["social_media_posts"].estimated_document_count()
    total_users = db["users"].estimated_document_count()

    # Erreurs récentes (dernières 24h)
    from datetime import timedelta
    yesterday = (now - timedelta(hours=24)).isoformat()
    recent_errors = db["scheduler_logs"].count_documents({
        "status": "error",
        "timestamp": {"$gte": yesterday}
    })

    return {
        "success": True,
        "health": {
            "last_scrape": last_scrape,
            "last_enrichment": last_enrich,
            "last_scheduler_run": last_scheduler,
            "scheduler_last_status": scheduler_status,
            "last_radio_capture": last_radio_at,
            "last_daily_report": last_report_at,
            "recent_errors_24h": recent_errors,
        },
        "counts": {
            "articles": total_articles,
            "affairs_active": total_affairs,
            "radio_transcriptions": total_radio,
            "social_posts": total_social,
            "users": total_users,
        },
        "timestamp": now.isoformat(),
    }