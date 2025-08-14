from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os, time, jwt

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME = os.getenv("AUTH_USERNAME", "admin")
PASSWORD = os.getenv("AUTH_PASSWORD", "admin")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))
JWT_ALG = "HS256"
JWT_ISS = os.getenv("JWT_ISSUER", "veille-api")

class LoginBody(BaseModel):
    username: str
    password: str

def create_token(sub: str) -> str:
    now = int(time.time())
    exp = now + JWT_EXPIRE_MINUTES * 60
    payload = {"sub": sub, "iat": now, "exp": exp, "iss": JWT_ISS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG], options={"require": ["exp", "iat", "sub"]})

bearer = HTTPBearer(auto_error=True)

@router.post("/login")
def login(body: LoginBody):
    if body.username != USERNAME or body.password != PASSWORD:
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    token = create_token(body.username)
    return {"access_token": token, "token_type": "bearer", "expires_in": JWT_EXPIRE_MINUTES * 60}

@router.get("/me")
def me(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        payload = decode_token(credentials.credentials)
        return {"username": payload["sub"], "exp": payload["exp"]}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide")
