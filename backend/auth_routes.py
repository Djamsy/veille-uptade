# backend/auth_routes.py
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .server import get_db  # réutilise la connexion Mongo du serveur

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# --- Config JWT ---
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "120"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_users_col():
    db = get_db()
    col = db["users"]
    # Index unique email (idempotent)
    try:
        col.create_index("email", unique=True)
    except Exception:
        pass
    return col

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return get_users_col().find_one({"email": email})

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_email(email)
    if not user or not user.get("password_hash"):
        return None
    if not verify_password(password, user["password_hash"]):
        return None
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
    user = get_user_by_email(email)
    if not user:
        raise credentials_exception
    # Ne retourne jamais le hash au client
    user.pop("password_hash", None)
    user["_id"] = str(user.get("_id"))
    return user

# --------- Routes ---------

@router.post("/register")
def register(user: Dict[str, Any] = Body(...)):
    """
    Body JSON: { "email": "...", "password": "...", "name": "..." }
    """
    email = (user.get("email") or "").strip().lower()
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
        "password_hash": get_password_hash(password),
        "created_at": datetime.utcnow().isoformat(),
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
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    user = authenticate_user(email, password)
    if not user:
        raise HTTPException(401, "Identifiants invalides")

    token = create_access_token({"sub": user["email"]})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"success": True, "user": current_user}
