# backend/elus_database.py
"""
Base d'élus officielle pour la Guadeloupe.

Source : Répertoire national des élus (data.gouv.fr), filtré sur la région
Guadeloupe et limité à 3 scopes en V1 :
  - municipal : 32 maires en exercice
  - departemental : 42 conseillers départementaux
  - regional : 39 conseillers régionaux
Total : 113 élus.

Fichier source : backend/data/elus_guadeloupe.json (regénéré depuis les JSON officiels).
À mettre à jour à chaque renouvellement de mandat.

Cette base remplace l'ancien dictionnaire manuel `ELECTED_ALIASES` dans
`entity_aliases.py`. Les alias sont générés dynamiquement à partir des données :
  - canonical (Prénom Nom)
  - nom de famille seul (si longueur ≥ 5)
  - « M. NOM » / « Mme NOM »
  - « le maire de COMMUNE » / « le/la maire NOM » pour les maires
  - « le président du conseil régional » / « le président du conseil départemental »
    pour les présidents en exercice

Le module expose aussi `MANDAT_COMMUNES` qui mappe chaque élu à sa commune
de mandat principale (pour audit des présences hors-mandat).
"""

from __future__ import annotations

import json
import logging
import os
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("elus_database")

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "elus_guadeloupe.json")


def _normalize(s: str) -> str:
    """Minuscule, sans accents, espaces collapsés."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = " ".join(s.split())
    return s


@lru_cache(maxsize=1)
def load_elus() -> List[Dict[str, Any]]:
    """Charge la base d'élus depuis le JSON. Mis en cache (1 lecture par process)."""
    if not os.path.exists(_DATA_FILE):
        logger.warning(f"⚠️ Fichier {_DATA_FILE} introuvable")
        return []
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"✅ {len(data)} élus chargés depuis {_DATA_FILE}")
        return data
    except Exception as e:
        logger.error(f"❌ Erreur chargement {_DATA_FILE}: {e}")
        return []


def _generate_aliases(elu: Dict[str, Any]) -> List[str]:
    """Génère la liste d'alias pour un élu donné."""
    aliases: Set[str] = set()
    first = (elu.get("first_name") or "").strip()
    last = (elu.get("last_name") or "").strip()
    role = (elu.get("role") or "").strip()
    commune = elu.get("commune")
    scope = elu.get("scope")

    # Forme canonique
    aliases.add(f"{first} {last}".lower())

    # Nom seul (si suffisamment long pour limiter les faux positifs)
    if len(last) >= 5:
        aliases.add(last.lower())

    # Civilité + nom
    aliases.add(f"m. {last}".lower())
    aliases.add(f"mme {last}".lower())
    aliases.add(f"monsieur {last}".lower())
    aliases.add(f"madame {last}".lower())

    # Initiale + nom : "É. Jalton", "H. Durimel"
    if first:
        aliases.add(f"{first[0]}. {last}".lower())

    # Spécifique au mandat
    if scope == "municipal" and commune:
        aliases.add(f"maire de {commune}".lower())
        aliases.add(f"maire des {commune}".lower())  # « maire des Abymes »
        aliases.add(f"maire du {commune}".lower())   # « maire du Gosier »
        aliases.add(f"le maire {last}".lower())
        aliases.add(f"la maire {last}".lower())
    elif scope == "regional" and "président" in role.lower():
        aliases.add("président du conseil régional")
        aliases.add("president du conseil regional")
        aliases.add("président de la région")
        aliases.add(f"le président {last}".lower())
    elif scope == "departemental" and "président" in role.lower():
        aliases.add("président du conseil départemental")
        aliases.add("president du conseil departemental")
        aliases.add("président du département")
        aliases.add(f"le président {last}".lower())

    # On retire les vides
    return sorted(a for a in aliases if a and len(a) >= 3)


@lru_cache(maxsize=1)
def build_aliases_index() -> Dict[str, List[str]]:
    """
    Construit le dict { canonical_name → [aliases] } à partir de la base.

    Compatible drop-in avec l'ancien `ELECTED_ALIASES`.
    Si un même nom canonique existe avec plusieurs scopes, on fusionne les alias.
    """
    elus = load_elus()
    out: Dict[str, List[str]] = {}
    for e in elus:
        canonical = e.get("canonical")
        if not canonical:
            continue
        aliases = _generate_aliases(e)
        if canonical in out:
            existing = set(out[canonical])
            existing.update(aliases)
            out[canonical] = sorted(existing)
        else:
            out[canonical] = aliases
    return out


@lru_cache(maxsize=1)
def build_mandat_communes() -> Dict[str, Optional[str]]:
    """
    Mappe chaque élu (canonical name) à sa commune de mandat principale.
    Pour les conseillers départementaux : la commune chef-lieu du canton.
    Pour les conseillers régionaux : None (mandat régional).
    """
    elus = load_elus()
    out: Dict[str, Optional[str]] = {}
    for e in elus:
        canonical = e.get("canonical")
        if not canonical:
            continue
        commune = e.get("commune")  # municipal → commune ; sinon None
        if canonical in out:
            # Garde la commune si une version a une commune (préfère municipal)
            if not out[canonical] and commune:
                out[canonical] = commune
        else:
            out[canonical] = commune
    return out


@lru_cache(maxsize=1)
def build_elu_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Métadonnées par élu : { canonical → { role, commune, canton, scope, since, ... } }
    Si un élu cumule (rare), on garde la première entrée et on note les autres scopes.
    """
    elus = load_elus()
    out: Dict[str, Dict[str, Any]] = {}
    for e in elus:
        canonical = e.get("canonical")
        if not canonical:
            continue
        if canonical not in out:
            out[canonical] = {
                "role": e.get("role"),
                "commune": e.get("commune"),
                "canton": e.get("canton"),
                "scope": e.get("scope"),
                "since": e.get("since"),
                "scopes": [e.get("scope")],
            }
        else:
            if e.get("scope") not in out[canonical]["scopes"]:
                out[canonical]["scopes"].append(e.get("scope"))
    return out


def get_mandat_commune(entity_canonical: str) -> Optional[str]:
    """Helper : retourne la commune de mandat d'un élu (None si régional ou inconnu)."""
    return build_mandat_communes().get(entity_canonical)


__all__ = [
    "load_elus",
    "build_aliases_index",
    "build_mandat_communes",
    "build_elu_metadata",
    "get_mandat_commune",
]
