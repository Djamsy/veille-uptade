# backend/services/crypto_service.py
"""
Chiffrement applicatif des données sensibles (AES-256-GCM).

Utilisé par le flux « publications pour validation » : texte, titre, médias,
état de validation, décisions et demandeur sont chiffrés AVANT écriture Mongo.
Seuls des identifiants, des dates et des empreintes (hash) restent en clair.

Format d'un champ chiffré : "enc:<version>:<base64url(nonce || ciphertext+tag)>"

Configuration (variables d'environnement) :
  PUBLICATION_ENCRYPTION_KEY       — clé courante, 32 octets en base64url (ou hex 64 car.)
                                      Générer : python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  PUBLICATION_ENCRYPTION_KEY_OLD   — (optionnel) clé précédente, déchiffrement seul,
                                      pour une rotation sans interruption.
  PUBLICATION_ENCRYPTION_KEY_VERSION — (optionnel) numéro de version de la clé courante (défaut 1).

En production la clé est obligatoire : sans elle le module lève RuntimeError et
le router de validation n'est pas chargé (fail closed). En développement, à défaut,
une clé est dérivée de JWT_SECRET avec un avertissement.
"""

import os
import json
import hmac
import base64
import hashlib
import logging
import secrets
from typing import Any, Dict, Iterable, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger("veille.crypto")

ENC_PREFIX = "enc:"
_NONCE_LEN = 12


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _parse_key(value: str, name: str) -> bytes:
    value = (value or "").strip()
    if not value:
        raise RuntimeError(f"{name} est vide")
    try:
        if len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value):
            raw = bytes.fromhex(value)
        else:
            raw = _b64d(value)
    except Exception as e:
        raise RuntimeError(f"{name} illisible (base64url ou hex attendu) : {e}")
    if len(raw) != 32:
        raise RuntimeError(f"{name} doit faire 32 octets (actuellement {len(raw)})")
    return raw


def _load_keys() -> Dict[int, bytes]:
    """Charge {version: clé}. La version courante est la plus grande."""
    env = os.getenv("ENVIRONMENT", "development")
    current = os.getenv("PUBLICATION_ENCRYPTION_KEY", "")
    version = int(os.getenv("PUBLICATION_ENCRYPTION_KEY_VERSION", "1") or 1)
    keys: Dict[int, bytes] = {}

    if current:
        keys[version] = _parse_key(current, "PUBLICATION_ENCRYPTION_KEY")
    elif env == "production":
        raise RuntimeError(
            "PUBLICATION_ENCRYPTION_KEY est obligatoire en production. "
            "Générer : python -c \"import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
        )
    else:
        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret:
            raise RuntimeError("PUBLICATION_ENCRYPTION_KEY (ou JWT_SECRET en dev) requis")
        logger.warning("🔐 PUBLICATION_ENCRYPTION_KEY absente — clé DEV dérivée de JWT_SECRET "
                       "(ne jamais faire ça en production)")
        keys[version] = hashlib.sha256(b"veille-dev-publication-key|" + jwt_secret.encode()).digest()

    old = os.getenv("PUBLICATION_ENCRYPTION_KEY_OLD", "")
    if old:
        keys[version - 1] = _parse_key(old, "PUBLICATION_ENCRYPTION_KEY_OLD")
    return keys


_KEYS: Dict[int, bytes] = _load_keys()
CURRENT_VERSION: int = max(_KEYS)


def _derive(purpose: bytes, version: int = CURRENT_VERSION) -> bytes:
    """Sous-clé dédiée par usage (chiffrement, index aveugle, hachage de jeton)."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose).derive(_KEYS[version])


_AEAD = {v: AESGCM(_derive(b"veille/publications/aead", v)) for v in _KEYS}
_INDEX_KEY = _derive(b"veille/publications/blind-index")
_TOKEN_KEY = _derive(b"veille/publications/token-hash")


# ── Chiffrement de chaînes ─────────────────────────────────

def encrypt_str(plain: Optional[str], aad: str = "") -> Optional[str]:
    """Chiffre une chaîne. None/"" sont renvoyés tels quels."""
    if plain is None or plain == "":
        return plain
    nonce = secrets.token_bytes(_NONCE_LEN)
    ct = _AEAD[CURRENT_VERSION].encrypt(nonce, plain.encode("utf-8"), aad.encode("utf-8") or None)
    return f"{ENC_PREFIX}{CURRENT_VERSION}:{_b64e(nonce + ct)}"


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def decrypt_str(value: Optional[str], aad: str = "") -> Optional[str]:
    """Déchiffre une chaîne produite par encrypt_str. Les valeurs non chiffrées
    sont renvoyées telles quelles (tolérance aux anciens documents)."""
    if not is_encrypted(value):
        return value
    try:
        _, ver, payload = value.split(":", 2)
        aead = _AEAD.get(int(ver))
        if aead is None:
            raise ValueError(f"version de clé inconnue : {ver}")
        raw = _b64d(payload)
        nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return aead.decrypt(nonce, ct, aad.encode("utf-8") or None).decode("utf-8")
    except Exception as e:
        logger.error("🔐 Déchiffrement impossible (%s)", type(e).__name__)
        raise ValueError("Donnée chiffrée illisible") from e


def encrypt_json(obj: Any, aad: str = "") -> str:
    return encrypt_str(json.dumps(obj, ensure_ascii=False, default=str), aad)


def decrypt_json(value: Optional[str], aad: str = "", default: Any = None) -> Any:
    if value is None or value == "":
        return default
    txt = decrypt_str(value, aad)
    try:
        return json.loads(txt)
    except Exception:
        return default


def encrypt_fields(doc: Dict[str, Any], fields: Iterable[str], aad: str = "") -> Dict[str, Any]:
    out = dict(doc)
    for f in fields:
        if f in out and out[f] not in (None, ""):
            out[f] = encrypt_str(str(out[f]), aad)
    return out


def decrypt_fields(doc: Dict[str, Any], fields: Iterable[str], aad: str = "") -> Dict[str, Any]:
    out = dict(doc)
    for f in fields:
        if f in out and is_encrypted(out[f]):
            out[f] = decrypt_str(out[f], aad)
    return out


# ── Index aveugle & jetons ─────────────────────────────────

def blind_index(value: str) -> str:
    """HMAC déterministe : permet de filtrer (ex. par statut) sans stocker la valeur en clair."""
    return hmac.new(_INDEX_KEY, (value or "").strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()


def new_token(nbytes: int = 32) -> str:
    """Jeton d'URL non devinable (256 bits)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Empreinte stockée en base : un dump Mongo ne permet pas de reconstituer le lien."""
    return hmac.new(_TOKEN_KEY, (token or "").encode("utf-8"), hashlib.sha256).hexdigest()


def fingerprint(*parts: Any) -> str:
    """Empreinte de contenu (dédoublonnage), sans clé : stable entre déploiements."""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p if p is not None else "").strip().encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def status() -> Dict[str, Any]:
    return {
        "configured": bool(os.getenv("PUBLICATION_ENCRYPTION_KEY")),
        "dev_derived_key": not bool(os.getenv("PUBLICATION_ENCRYPTION_KEY")),
        "key_version": CURRENT_VERSION,
        "rotation_key_loaded": len(_KEYS) > 1,
        "algorithm": "AES-256-GCM + HKDF-SHA256",
    }
