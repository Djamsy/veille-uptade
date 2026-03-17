from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pymongo import MongoClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])  # ✅ CORRECTION ICI

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

# Contexte de chiffrement
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_db():
    """Connexion MongoDB"""
    MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "veille_media")
    
    client = MongoClient(MONGO_URL)
    return client[MONGO_DB_NAME]

def create_access_token(data: Dict[str, Any]) -> str:
    """Créer un token JWT"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
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
    """Créer le premier compte admin. Ne fonctionne que s'il n'y a aucun admin en base."""
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
@router.post("/login")
def login(payload: Dict[str, Any] = Body(...)):
    """Connexion utilisateur"""
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    
    if not email or not password:
        raise HTTPException(400, "Email et password requis")

    # ✅ CORRECTION: Tronquer AVANT tout traitement
    # Bcrypt a une limite stricte de 72 bytes
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        password = password_bytes.decode('utf-8', errors='ignore')

    db = get_db()
    users_col = db["users"]
    user = users_col.find_one({"email": email})
    
    if not user:
        raise HTTPException(401, "Identifiants invalides")
    
    # Vérifier le mot de passe
    try:
        if not pwd_context.verify(password, user.get("password_hash", "")):
            raise HTTPException(401, "Identifiants invalides")
    except ValueError as e:
        # Si le hash en DB est corrompu, logger et refuser
        logger.error(f"Hash bcrypt invalide pour {email}: {e}")
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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