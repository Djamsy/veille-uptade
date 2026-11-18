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

def list_tabs() -> List[str]:
    """Noms des onglets, dans l'ordre de la feuille."""
    r = requests.get(f"{SHEETS_API}/{sheet_id()}", params={"fields": "sheets.properties.title"},
                     headers=_headers(), timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Google Sheets {r.status_code}: {r.text[:200]}")
    return [sh["properties"]["title"] for sh in r.json().get("sheets", [])]


def _col_letter(idx: int) -> str:
    """0 → A, 25 → Z, 26 → AA."""
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _detect_header_row(values: List[List[str]], required: Optional[List[str]] = None, max_scan: int = 15) -> int:
    """Index (0-based) de la ligne d'en-têtes : première ligne, parmi les `max_scan` premières,
    contenant au moins 3 cellules non vides et, si `required` est fourni, tous ces mots
    (comparaison insensible à la casse/accents). Repli : ligne 0."""
    def norm(x: str) -> str:
        try:
            from unidecode import unidecode
            x = unidecode(x)
        except Exception:
            pass
        return x.lower().strip()

    req = [norm(r) for r in (required or [])]
    best, best_count = 0, 0
    for i, line in enumerate(values[:max_scan]):
        cells = [norm(str(c)) for c in line if str(c).strip()]
        if len(cells) < 3:
            continue
        if req and all(any(r == c for c in cells) for r in req):
            return i
        if len(cells) > best_count:
            best, best_count = i, len(cells)
    return best


def _parse_table(tab: str, values: List[List[str]], header_markers: Optional[List[str]] = None) -> Dict[str, Any]:
    if not values:
        return {"tab": tab, "headers": [], "header_row": 1, "rows": []}
    h = _detect_header_row(values, header_markers)
    headers = [str(x).strip() for x in values[h]]
    rows = []
    for i, line in enumerate(values[h + 1:], start=h + 2):
        if not any(str(c).strip() for c in line):
            continue
        cells = {}
        for j, name in enumerate(headers):
            if not name or name in cells:  # en-têtes dupliqués : la 1re occurrence gagne
                continue
            cells[name] = str(line[j]).strip() if j < len(line) else ""
        # colonnes dupliquées (ex. 2e bloc « Précisions / consignes ») → suffixe « (2) »
        seen: Dict[str, int] = {}
        for j, name in enumerate(headers):
            if not name:
                continue
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                cells[f"{name} ({seen[name]})"] = str(line[j]).strip() if j < len(line) else ""
        rows.append({"row_number": i, "values": cells})
    return {"tab": tab, "headers": headers, "header_row": h + 1, "rows": rows}


def read_tables(tabs: Optional[List[str]] = None, header_markers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Lit plusieurs onglets en UN appel (values:batchGet).
    Renvoie [{"tab", "headers", "header_row", "rows": [{"row_number", "values"}]}].
    row_number / header_row sont des numéros de ligne réels (1-based)."""
    tabs = tabs or ([sheet_tab()] if sheet_tab() else list_tabs())
    if not tabs:
        return []
    params = [("valueRenderOption", "FORMATTED_VALUE"), ("majorDimension", "ROWS")]
    params += [("ranges", f"'{t}'") for t in tabs]
    r = requests.get(f"{SHEETS_API}/{sheet_id()}/values:batchGet", params=params, headers=_headers(), timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google Sheets {r.status_code}: {r.text[:200]}")
    out = []
    for tab, vr in zip(tabs, r.json().get("valueRanges", [])):
        out.append(_parse_table(tab, vr.get("values", []), header_markers))
    return out


def read_table(header_markers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Un seul onglet (PUBLICATION_SHEET_TAB ou le premier)."""
    tabs = [sheet_tab()] if sheet_tab() else list_tabs()[:1]
    res = read_tables(tabs, header_markers)
    return res[0] if res else {"tab": tabs[0] if tabs else "", "headers": [], "header_row": 1, "rows": []}


# ── Écriture ───────────────────────────────────────────────

def write_cell(row_number: int, header_index: int, value: str, tab: Optional[str] = None) -> bool:
    """Écrit une cellule (colonne repérée par l'index 0-based de son en-tête)."""
    try:
        tab = tab or sheet_tab() or list_tabs()[0]
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


def ensure_column(table: Dict[str, Any], name: str) -> Optional[int]:
    """Index 0-based de la colonne `name` dans l'onglet ; la crée (en-tête écrit à droite
    des en-têtes existants) si absente. None si l'écriture échoue."""
    headers = table["headers"]
    for i, h in enumerate(headers):
        if h.strip().lower() == name.strip().lower():
            return i
    idx = len(headers)
    if write_cell(table["header_row"], idx, name, tab=table["tab"]):
        headers.append(name)
        return idx
    return None
