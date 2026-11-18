# backend/services/google_sheets_service.py
"""
Lecture / écriture d'une feuille Google Sheets via un compte de service.

Aucune dépendance supplémentaire : le JWT RS256 est signé avec python-jose
(déjà présent) et les appels REST passent par `requests`.

Configuration (variables d'environnement) :
  GOOGLE_SERVICE_ACCOUNT_JSON — contenu du fichier JSON du compte de service
                                (brut, ou encodé en base64). Le compte doit être
                                ajouté en partage (Éditeur) sur la feuille.
  PUBLICATION_SHEET_ID        — identifiant de la feuille (dans l'URL, entre /d/ et /edit)
  PUBLICATION_SHEET_TAB       — (optionnel) nom de l'onglet. Défaut : premier onglet.

Mise en forme attendue : première ligne = en-têtes. Les colonnes sont repérées
par leur en-tête (insensible à la casse et aux accents), voir COLUMN_ALIASES
dans publication_validation_service.py.
"""

import os
import json
import time
import base64
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("veille.sheets")

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets"

_token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0}


def sheet_id() -> str:
    return os.getenv("PUBLICATION_SHEET_ID", "").strip()


def sheet_tab() -> str:
    return os.getenv("PUBLICATION_SHEET_TAB", "").strip()


def _service_account() -> Optional[Dict[str, Any]]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    if not raw.startswith("{"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON : ni JSON ni base64 valide")
            return None
    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON : JSON invalide (%s)", e)
        return None
    if not data.get("client_email") or not data.get("private_key"):
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON : client_email / private_key manquants")
        return None
    return data


def is_configured() -> bool:
    return bool(sheet_id() and _service_account())


def status() -> Dict[str, Any]:
    sa = _service_account()
    return {
        "configured": is_configured(),
        "sheet_id_set": bool(sheet_id()),
        "service_account": (sa or {}).get("client_email", "") if sa else "",
        "tab": sheet_tab() or "(premier onglet)",
    }


# ── OAuth2 compte de service ───────────────────────────────

def _access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    sa = _service_account()
    if not sa:
        raise RuntimeError("Compte de service Google non configuré")

    from jose import jwt  # python-jose[cryptography] — RS256 supporté
    claims = {
        "iss": sa["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": int(now),
        "exp": int(now) + 3600,
    }
    assertion = jwt.encode(claims, sa["private_key"], algorithm="RS256",
                           headers={"kid": sa.get("private_key_id", "")})
    r = requests.post(TOKEN_URL, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Google OAuth {r.status_code}: {r.text[:200]}")
    body = r.json()
    _token_cache["access_token"] = body["access_token"]
    _token_cache["expires_at"] = now + int(body.get("expires_in", 3600))
    return body["access_token"]


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"}


# ── Lecture ────────────────────────────────────────────────

def _resolve_tab() -> str:
    tab = sheet_tab()
    if tab:
        return tab
    r = requests.get(f"{SHEETS_API}/{sheet_id()}", params={"fields": "sheets.properties.title"},
                     headers=_headers(), timeout=15)
    r.raise_for_status()
    sheets = r.json().get("sheets", [])
    if not sheets:
        raise RuntimeError("Feuille sans onglet")
    return sheets[0]["properties"]["title"]


def _col_letter(idx: int) -> str:
    """0 → A, 25 → Z, 26 → AA."""
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def read_table() -> Dict[str, Any]:
    """Renvoie {"tab", "headers": [...], "rows": [{"row_number": n, "values": {header: cell}}]}.
    row_number est le numéro de ligne réel dans la feuille (en-tête = 1)."""
    tab = _resolve_tab()
    rng = quote(f"'{tab}'", safe="")
    r = requests.get(f"{SHEETS_API}/{sheet_id()}/values/{rng}",
                     params={"valueRenderOption": "FORMATTED_VALUE"},
                     headers=_headers(), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Google Sheets {r.status_code}: {r.text[:200]}")
    values: List[List[str]] = r.json().get("values", [])
    if not values:
        return {"tab": tab, "headers": [], "rows": []}

    headers = [str(h).strip() for h in values[0]]
    rows = []
    for i, line in enumerate(values[1:], start=2):
        if not any(str(c).strip() for c in line):
            continue
        cells = {headers[j]: (str(line[j]).strip() if j < len(line) else "")
                 for j in range(len(headers)) if headers[j]}
        rows.append({"row_number": i, "values": cells})
    return {"tab": tab, "headers": headers, "rows": rows}


# ── Écriture ───────────────────────────────────────────────

def write_cell(row_number: int, header_index: int, value: str, tab: Optional[str] = None) -> bool:
    """Écrit une cellule (colonne repérée par l'index 0-based de son en-tête)."""
    try:
        tab = tab or _resolve_tab()
        a1 = f"'{tab}'!{_col_letter(header_index)}{row_number}"
        r = requests.put(f"{SHEETS_API}/{sheet_id()}/values/{quote(a1, safe='')}",
                         params={"valueInputOption": "RAW"},
                         json={"range": a1, "majorDimension": "ROWS", "values": [[value]]},
                         headers=_headers(), timeout=15)
        if r.status_code != 200:
            logger.warning("Sheets write %s : %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning("Sheets write échoué : %s", e)
        return False
