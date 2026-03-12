# backend/entity_aliases.py
"""
Base d'alias d'entités pour la Guadeloupe.

Résout le problème de déduplication :
"Guy Losbar" / "M. Losbar" / "le président du Département" → même entité.

Deux niveaux :
1. Alias statiques : dictionnaire codé en dur (personnalités et institutions connues)
2. Normalisation : suppression accents, casse, abréviations courantes
"""

import re
import unicodedata
import logging
from typing import Dict, Set, Optional, List, Tuple

logger = logging.getLogger("entity_aliases")


# ============================================================
# ALIAS STATIQUES — Personnalités guadeloupéennes
# Clé = forme canonique, valeurs = variantes connues
# ============================================================

ELECTED_ALIASES: Dict[str, List[str]] = {
    "Guy Losbar": [
        "guy losbar", "m. losbar", "losbar", "président du département",
        "president du departement", "le président losbar",
    ],
    "Ary Chalus": [
        "ary chalus", "m. chalus", "chalus", "président de la région",
        "president de la region", "le président chalus",
        "président du conseil régional",
    ],
    "Victorin Lurel": [
        "victorin lurel", "m. lurel", "lurel", "sénateur lurel",
        "senateur lurel", "ancien ministre lurel",
    ],
    "Éric Jalton": [
        "éric jalton", "eric jalton", "m. jalton", "jalton",
        "maire de pointe-à-pitre", "maire de pointe-a-pitre",
        "le maire jalton",
    ],
    "Josette Borel-Lincertin": [
        "josette borel-lincertin", "borel-lincertin", "josette borel",
        "mme borel-lincertin",
    ],
    "Max Mathiasin": [
        "max mathiasin", "m. mathiasin", "mathiasin",
    ],
    "Harry Durimel": [
        "harry durimel", "m. durimel", "durimel",
        "maire de pointe-noire",
    ],
    "Hélène Vainqueur-Christophe": [
        "hélène vainqueur-christophe", "helene vainqueur-christophe",
        "vainqueur-christophe", "hélène vainqueur",
    ],
    "Dominique Théophile": [
        "dominique théophile", "dominique theophile",
        "m. théophile", "m. theophile", "théophile", "theophile",
        "sénateur théophile",
    ],
    "Justine Bénin": [
        "justine bénin", "justine benin", "mme bénin",
        "mme benin", "bénin", "benin",
    ],
    "Olivier Serva": [
        "olivier serva", "m. serva", "serva",
        "député serva", "depute serva",
    ],
    "Christian Baptiste": [
        "christian baptiste", "m. baptiste", "baptiste",
        "maire du gosier",
    ],
    "Ferdy Louisy": [
        "ferdy louisy", "m. louisy", "louisy",
    ],
    "Marie-Luce Penchard": [
        "marie-luce penchard", "penchard", "mme penchard",
    ],
    "Lucette Michaux-Chevry": [
        "lucette michaux-chevry", "michaux-chevry",
        "mme michaux-chevry", "lucette michaux",
    ],
    "Cedric Cornet": [
        "cedric cornet", "cédric cornet", "m. cornet", "cornet",
        "maire des abymes",
    ],
    "Jocelyn Sapotille": [
        "jocelyn sapotille", "m. sapotille", "sapotille",
        "maire de lamentin",
    ],
    # ── Conseillers départementaux (mandature 2021-2028) ──
    "Marylène Adhel": [
        "marylène adhel", "marylene adhel", "adhel", "mme adhel",
        "conseillère départementale abymes 3",
    ],
    "Louis Galantine": [
        "louis galantine", "galantine", "m. galantine",
        "conseiller départemental abymes 3",
    ],
    "Francesca Faithful": [
        "francesca faithful", "faithful", "mme faithful",
        "conseillère départementale abymes 1",
    ],
    "Eliane Guiougou-Firpion": [
        "eliane guiougou-firpion", "guiougou-firpion", "guiougou",
        "conseillère départementale abymes 2",
    ],
    "Fabert Michely": [
        "fabert michely", "michely", "m. michely",
        "conseiller départemental abymes 2",
    ],
    "Henry Angélique": [
        "henry angélique", "henry angelique", "angélique", "angelique",
        "conseiller départemental pointe-à-pitre",
    ],
    "Tania Galvani": [
        "tania galvani", "galvani", "mme galvani",
        "conseillère départementale pointe-à-pitre",
    ],
    "Catherine Joab": [
        "catherine joab", "joab", "mme joab",
        "conseillère départementale gosier",
    ],
    "Elie Califer": [
        "elie califer", "califer", "m. califer",
        "conseiller départemental basse-terre",
    ],
    "Jean Dartron": [
        "jean dartron", "dartron", "m. dartron",
        "conseiller départemental morne-à-l'eau",
    ],
    "Daniel Dulac": [
        "daniel dulac", "dulac", "m. dulac",
        "conseiller départemental moule",
    ],
    "Gabrielle Louis-Carabin": [
        "gabrielle louis-carabin", "louis-carabin", "mme louis-carabin",
        "conseillère départementale moule",
    ],
    "Michel Mado": [
        "michel mado", "mado", "m. mado",
        "conseiller départemental baie-mahault",
    ],
    "Jimmy Fausta": [
        "jimmy fausta", "fausta", "m. fausta",
        "conseiller départemental trois-rivières",
    ],
    "Jean-Philippe Courtois": [
        "jean-philippe courtois", "courtois", "m. courtois",
        "conseiller départemental capesterre-belle-eau",
    ],
    "Lydia Faro-Couriol": [
        "lydia faro-couriol", "faro-couriol", "faro couriol",
        "conseillère départementale sainte-anne",
    ],
    "Eric Latchoumanin": [
        "eric latchoumanin", "latchoumanin", "m. latchoumanin",
        "conseiller départemental sainte-anne",
    ],
    "Maryse Etzol": [
        "maryse etzol", "etzol", "mme etzol",
        "conseillère départementale marie-galante",
    ],
    "Jean-Claude Maës": [
        "jean-claude maës", "jean-claude maes", "maës", "maes",
        "conseiller départemental marie-galante",
    ],
    "Isabelle Amireille-Jomie": [
        "isabelle amireille-jomie", "amireille-jomie", "amireille",
        "conseillère départementale sainte-rose",
    ],
    "Fred Goubin": [
        "fred goubin", "goubin", "m. goubin",
        "conseiller départemental sainte-rose",
    ],
    "Nicole De La Rederdière-Ramillon": [
        "nicole de la rederdière-ramillon", "rederdière-ramillon",
        "mme ramillon", "ramillon",
    ],
    "Adrien Baron": [
        "adrien baron", "baron", "m. baron",
        "conseiller départemental sainte-rose 2",
    ],
}

# ============================================================
# ALIAS STATIQUES — Institutions guadeloupéennes
# ============================================================

INSTITUTION_ALIASES: Dict[str, List[str]] = {
    "SMGEAG": [
        "smgeag", "syndicat mixte de gestion de l'eau",
        "syndicat mixte de gestion de l eau",
        "syndicat des eaux", "régie des eaux",
        "siaeag",  # ancien nom
    ],
    "CHU de Guadeloupe": [
        "chu de guadeloupe", "chu guadeloupe", "chu pointe-à-pitre",
        "chu pointe-a-pitre", "chu abymes", "centre hospitalier",
        "chu", "hôpital",
    ],
    "ARS Guadeloupe": [
        "ars guadeloupe", "ars", "agence régionale de santé",
        "agence regionale de sante",
    ],
    "Préfecture de Guadeloupe": [
        "préfecture de guadeloupe", "prefecture de guadeloupe",
        "préfecture", "prefecture", "le préfet", "le prefet",
    ],
    "Conseil Départemental": [
        "conseil départemental", "conseil departemental",
        "département de la guadeloupe", "departement",
    ],
    "Conseil Régional": [
        "conseil régional", "conseil regional",
        "région guadeloupe", "region guadeloupe",
    ],
    "Rectorat de Guadeloupe": [
        "rectorat de guadeloupe", "rectorat", "académie",
        "academie", "recteur", "la rectrice",
    ],
    "EDF Guadeloupe": [
        "edf guadeloupe", "edf", "electricité de france",
        "électricité de france",
    ],
    "SDIS 971": [
        "sdis 971", "sdis guadeloupe", "sdis",
        "sapeurs-pompiers", "pompiers", "service d'incendie",
    ],
    "Parquet de Pointe-à-Pitre": [
        "parquet de pointe-à-pitre", "parquet de pointe-a-pitre",
        "parquet", "procureur", "le procureur",
    ],
    "DEAL Guadeloupe": [
        "deal guadeloupe", "deal", "direction de l'environnement",
    ],
    "IEDOM": [
        "iedom", "institut d'émission des départements d'outre-mer",
    ],
    "CAF Guadeloupe": [
        "caf guadeloupe", "caf", "caisse d'allocations familiales",
    ],
    "CGSS": [
        "cgss", "caisse générale de sécurité sociale",
        "sécurité sociale guadeloupe",
    ],
    "France Travail Guadeloupe": [
        "france travail guadeloupe", "france travail",
        "pôle emploi", "pole emploi",
    ],
    "CTIG": [
        "ctig", "communauté d'agglomération cap excellence",
        "cap excellence",
    ],
    "EPSM de Guadeloupe": [
        "epsm", "epsm de guadeloupe", "établissement public de santé mentale",
        "etablissement public de sante mentale", "santé mentale",
    ],
    "Gardel": [
        "gardel", "usine gardel", "sucrerie gardel",
    ],
    "Chambre Régionale des Comptes": [
        "chambre régionale des comptes", "chambre regionale des comptes",
        "crc", "la crc",
    ],
    "Tribunal de Basse-Terre": [
        "tribunal de basse-terre", "cour d'assises de basse-terre",
        "tribunal judiciaire de basse-terre",
    ],
    "Port Autonome de Guadeloupe": [
        "port autonome", "port autonome de guadeloupe",
        "grand port maritime", "gpmg",
    ],
    "CRESS Guadeloupe": [
        "cress", "cress guadeloupe",
        "chambre régionale de l'économie sociale et solidaire",
    ],
}


# ============================================================
# INDEX INVERSÉ (alias → canonique)
# ============================================================

def _build_inverse_index() -> Dict[str, str]:
    """Construit l'index inversé alias → forme canonique."""
    idx = {}
    for canonical, aliases in ELECTED_ALIASES.items():
        canonical_lower = canonical.lower()
        idx[canonical_lower] = canonical
        for alias in aliases:
            idx[alias.lower()] = canonical
    for canonical, aliases in INSTITUTION_ALIASES.items():
        canonical_lower = canonical.lower()
        idx[canonical_lower] = canonical
        for alias in aliases:
            idx[alias.lower()] = canonical
    return idx


_ALIAS_INDEX = _build_inverse_index()


def _normalize(text: str) -> str:
    """Normalise un texte : minuscules, supprime accents et ponctuation superflue."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[''`]", "'", text)
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_entity(entity_name: str) -> str:
    """
    Résout un nom d'entité vers sa forme canonique.
    Retourne la forme canonique ou le nom original si pas d'alias trouvé.

    >>> resolve_entity("M. Losbar")
    'Guy Losbar'
    >>> resolve_entity("le préfet")
    'Préfecture de Guadeloupe'
    >>> resolve_entity("Jean-Marc Inconnu")
    'Jean-Marc Inconnu'
    """
    normalized = _normalize(entity_name)

    # 1. Correspondance exacte
    if normalized in _ALIAS_INDEX:
        return _ALIAS_INDEX[normalized]

    # 2. Correspondance partielle (le nom est contenu dans un alias)
    for alias, canonical in _ALIAS_INDEX.items():
        if len(alias) > 5 and alias in normalized:
            return canonical
        if len(normalized) > 5 and normalized in alias:
            return canonical

    return entity_name


def resolve_entities(entities: List[str]) -> List[str]:
    """
    Résout une liste d'entités et déduplique.

    >>> resolve_entities(["Guy Losbar", "M. Losbar", "président du département"])
    ['Guy Losbar']
    """
    resolved = set()
    for e in entities:
        if e and len(e) > 2:
            canonical = resolve_entity(e)
            resolved.add(canonical)
    return sorted(resolved)


def entities_match(entities_a: List[str], entities_b: List[str]) -> Tuple[Set[str], float]:
    """
    Compare deux listes d'entités en résolvant les alias.
    Retourne (entités communes canoniques, score Jaccard).
    """
    resolved_a = set(resolve_entity(e) for e in entities_a if e)
    resolved_b = set(resolve_entity(e) for e in entities_b if e)

    if not resolved_a or not resolved_b:
        return set(), 0.0

    common = resolved_a & resolved_b
    union = resolved_a | resolved_b
    jaccard = len(common) / len(union) if union else 0.0

    return common, jaccard


def is_known_entity(name: str) -> bool:
    """Vérifie si un nom est une entité connue (élu ou institution)."""
    return _normalize(name) in _ALIAS_INDEX


def get_entity_type(name: str) -> Optional[str]:
    """Retourne 'elected' ou 'institution' selon le type d'entité, ou None."""
    canonical = resolve_entity(name)
    if canonical in ELECTED_ALIASES:
        return "elected"
    if canonical in INSTITUTION_ALIASES:
        return "institution"
    return None
