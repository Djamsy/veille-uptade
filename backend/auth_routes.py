# backend/auth_routes.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .server import get_db  # connexion Mongo partagée

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# --- Config JWT ---
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "120"))

# ✅ Accepte argon2 et bcrypt ; rehash si nécessaire
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

# ⚠️ Ajuste ce tokenUrl selon comment tu montes le router dans server.py :
# - si app.include_router(..., prefix="/api") -> tokenUrl DOIT être "/api/auth/login"
# - sinon -> "/auth/login"
OAUTH_TOKEN_URL = os.getenv("OAUTH_TOKEN_URL", "/api/auth/login")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=OAUTH_TOKEN_URL)

def _norm_email(v: str) -> str:
    return (v or "").strip().lower()

def get_users_col():
    db = get_db()
    col = db["users"]
    # Index unique sur email (idempotent)
    try:
        col.create_index("email", unique=True)
    except Exception:
        pass
    return col

def get_user_by_email_or_username(email: str) -> Optional[Dict[str, Any]]:
    col = get_users_col()
    u = col.find_one({"email": email})
    if not u:
        # fallback éventuel si des anciens comptes utilisaient "username" comme clé de login
        u = col.find_one({"username": email})
    return u

def _get_stored_hash(user: Dict[str, Any]) -> Optional[str]:
    return user.get("password_hash") or user.get("password")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def maybe_rehash(user: Dict[str, Any], plain_password: str, hashed_password: str) -> None:
    try:
        if pwd_context.needs_update(hashed_password):
            new_hash = pwd_context.hash(plain_password)
            get_users_col().update_one({"_id": user["_id"]}, {"$set": {"password_hash": new_hash}})
    except Exception:
        # On ne bloque pas si la mise à niveau échoue
        pass

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email_or_username(email)
    if not user:
        return None
    stored = _get_stored_hash(user)
    if not stored:
        return None
    if not verify_password(password, stored):
        return None
    # rehash si ancien format
    maybe_rehash(user, password, stored)
    return user

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_email_or_username(_norm_email(email))
    if not user:
        raise credentials_exception
    user.pop("password_hash", None)
    user.pop("password", None)
    user["_id"] = str(user.get("_id"))
    return user

# --------- Routes ---------

@router.post("/register")
def register(user: Dict[str, Any] = Body(...)):
    """
    Body JSON: { "email": "...", "password": "...", "name": "..." }
    """
    email = _norm_email(user.get("email"))
    password = user.get("password") or ""
    name = (user.get("name") or "").strip()

    if not email or not password:
        raise HTTPException(400, "email et password sont requis")

    col = get_users_col()
    if col.find_one({"email": email}):
        raise HTTPException(409, "Un compte existe déjà avec cet email")

    doc = {
        "email": email,
        "name": name or email.split("@")[0],
        "password_hash": pwd_context.hash(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "role": "user",
        "active": True,
    }
    res = col.insert_one(doc)
    return {"success": True, "user": {"id": str(res.inserted_id), "email": email, "name": doc["name"]}}

@router.post("/login")
def login(payload: Dict[str, Any] = Body(...)):
    """
    Body JSON: { "email": "...", "password": "..." }
    Retourne: { access_token, token_type }
    """
    email = _norm_email(payload.get("email"))
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(400, "Email/mot de passe requis")

    user = authenticate_user(email, password)
    if not user:
        raise HTTPException(401, "Identifiants invalides")

    token = create_access_token({"sub": user["email"]})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"success": True, "user": current_user}
