# backend/services/google_sheets_service.py
"""
Lecture / écriture d'une feuille Google Sheets via un compte de service.

Aucune dépendance supplémentaire : le JWT RS256 est signé avec python-jose
(déjà présent) et les appels REST passent par `requests`.

Configuration (variables d'environnement) :
  GOOGLE_SERVICE_ACCOUNT_JSON — contenu du fichier JSON du compte de service (brut, base64,
                                ou chemin d'un fichier). D'autres noms sont acceptés, voir
                                SERVICE_ACCOUNT_ENV_NAMES ; à défaut, toute variable contenant
                                un JSON « service_account » ou un fichier sous /etc/secrets.
                                Le compte doit être ajouté en partage (Éditeur) sur la feuille.
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


# Noms de variables acceptés pour le compte de service (le 1er trouvé gagne). Chacune peut
# contenir le JSON brut, le JSON en base64, ou le CHEMIN d'un fichier (ex. Secret File Render
# monté sous /etc/secrets/...).
SERVICE_ACCOUNT_ENV_NAMES = [
    "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT", "GOOGLE_SERVICE_ACCOUNT_KEY",
    "GOOGLE_CREDENTIALS_JSON", "GOOGLE_CREDENTIALS", "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_SHEETS_CREDENTIALS", "GSHEETS_CREDENTIALS",
    "GCP_SERVICE_ACCOUNT", "GCP_SA_KEY", "SERVICE_ACCOUNT_JSON",
]
SECRET_FILE_DIRS = ["/etc/secrets", "/run/secrets"]

_sa_cache: Dict[str, Any] = {"loaded": False, "data": None, "origin": ""}


def _looks_base64(v: str) -> bool:
    v = v.strip()
    return len(v) > 200 and " " not in v and all(c.isalnum() or c in "+/=_-\n\r" for c in v)


def _parse_sa(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return None
    if len(raw) < 1024 and raw.startswith("/") and os.path.isfile(raw):  # chemin de fichier
        in_secret_dir = any(raw.startswith(d + "/") for d in SECRET_FILE_DIRS)
        if not (raw.lower().endswith(".json") or in_secret_dir):
            return None  # SHELL, PATH, binaires… : on ne lit que des .json ou des fichiers secrets
        try:
            if os.path.getsize(raw) > 64 * 1024:
                return None
            with open(raw, "r", encoding="utf-8") as f:
                raw = f.read().strip()
        except Exception as e:
            logger.debug("Compte de service : fichier illisible %s (%s)", raw, e)
            return None
    if not raw.startswith("{"):
        if not _looks_base64(raw):
            return None
        try:
            raw = base64.b64decode(raw, validate=False).decode("utf-8")
        except Exception:
            try:
                raw = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
            except Exception:
                return None
    try:
        data = json.loads(raw)
    except Exception:
        # JSON collé avec des retours à la ligne échappés (\n → vrais sauts) : seconde chance
        try:
            data = json.loads(raw.replace("\\n", "\n").replace("\n", "\\n"))
        except Exception:
            return None
    if not isinstance(data, dict) or data.get("type") != "service_account":
        return None
    if not data.get("client_email") or not data.get("private_key"):
        return None
    return data


def _service_account() -> Optional[Dict[str, Any]]:
    """Trouve le compte de service : variables connues, puis n'importe quelle variable
    d'environnement contenant un JSON « service_account » (brut ou base64), puis les fichiers secrets."""
    if _sa_cache["loaded"]:
        return _sa_cache["data"]
    data, origin = None, ""
    for name in SERVICE_ACCOUNT_ENV_NAMES:
        data = _parse_sa(os.getenv(name, ""))
        if data:
            origin = f"env:{name}"
            break
    if not data:
        for name, val in os.environ.items():
            if '"service_account"' in val or _looks_base64(val) or (val.strip().startswith("/") and len(val) < 512):
                data = _parse_sa(val)
                if data:
                    origin = f"env:{name}"
                    break
    if not data:
        for d in SECRET_FILE_DIRS:
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                data = _parse_sa(os.path.join(d, fn))
                if data:
                    origin = f"file:{os.path.join(d, fn)}"
                    break
            if data:
                break
    if data:
        logger.info("🔑 Compte de service Google chargé (%s) : %s", origin, data.get("client_email"))
    else:
        logger.info("Compte de service Google : introuvable (variables %s, fichiers %s)",
                    ", ".join(SERVICE_ACCOUNT_ENV_NAMES[:3]) + "…", ", ".join(SECRET_FILE_DIRS))
    _sa_cache.update({"loaded": True, "data": data, "origin": origin})
    return data


def diagnostics() -> Dict[str, Any]:
    """Aide au repérage du compte de service : NOMS des variables candidates (jamais les valeurs)
    et fichiers secrets présents, avec une description de leur forme."""
    cands = []
    for name, val in sorted(os.environ.items()):
        n = name.upper()
        hint = None
        if any(k in n for k in ("GOOGLE", "GCP", "GSHEET", "SHEET", "SERVICE_ACCOUNT", "CREDENTIAL", "SA_KEY")):
            hint = "nom évocateur"
        v = val.strip()
        shape = ("json" if v.startswith("{") else "chemin" if v.startswith("/") else
                 "identifiant client OAuth (…apps.googleusercontent.com) — ce n'est PAS une clé de compte de service"
                 if v.endswith(".apps.googleusercontent.com") else
                 "base64 ?" if _looks_base64(v) else "texte")
        if '"service_account"' in v:
            hint = (hint + ", " if hint else "") + "contient service_account"
        if hint:
            reason = []
            if v.startswith("{"):
                try:
                    json.loads(v)
                except Exception as e:
                    reason.append(f"JSON invalide : {str(e)[:60]}")
            cands.append({"name": name, "shape": shape, "length": len(v), "hint": hint,
                          "problem": "; ".join(reason) or None})
    files = []
    for d in SECRET_FILE_DIRS:
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                p = os.path.join(d, fn)
                try:
                    size = os.path.getsize(p)
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        head = f.read(2).strip()
                    files.append({"path": p, "size": size, "shape": "json" if head.startswith("{") else "texte"})
                except Exception as e:
                    files.append({"path": p, "error": str(e)[:80]})
    return {"candidate_env_vars": cands, "secret_files": files, "checked_dirs": SECRET_FILE_DIRS,
            "known_names": SERVICE_ACCOUNT_ENV_NAMES}


def is_configured() -> bool:
    return bool(sheet_id() and _service_account())


def status() -> Dict[str, Any]:
    sa = _service_account()
    return {
        "configured": is_configured(),
        "sheet_id_set": bool(sheet_id()),
        "service_account": (sa or {}).get("client_email", "") if sa else "",
        "service_account_origin": _sa_cache.get("origin", ""),
        "tab": sheet_tab() or "(premier onglet)",
        "diagnostics": None if sa else diagnostics(),
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
