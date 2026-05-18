# backend/tags_index.py
"""
Système de classification pour la Guadeloupe
✅ Détection STRICTE avec regex — ZÉRO faux positif
✅ CHU ne matche PAS "chuté"
✅ Noms complets exigés (pas juste le nom de famille)
✅ Scoring de gravité pour les affaires (0.0-1.0)
✅ Détection d'institutions (CHU, SMGEAG, EDF, Préfecture…)
✅ Personnalités avec patterns précis
✅ Analyse de sentiment
✅ Classification des types d'affaires
✅ Patterns pré-compilés au chargement du module (performance)
"""
from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

# =========================
# NORMALISATION
# =========================
_word = re.compile(r"[a-z0-9\-']{2,}")

def strip_accents(s: str) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))

def normalize(text: str) -> str:
    if not text:
        return ""
    text = strip_accents(text).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokens(text: str) -> List[str]:
    return _word.findall(normalize(text))

# =========================
# TAXONOMIE DES THÈMES
# =========================
THEME_TAXONOMY: Dict[str, List[str]] = {
    "eau_env": [
        "eau", "robinet", "coupure", "canalisation", "chateau d eau",
        "usine d eau", "siaeag", "sng", "saur", "pollution", "environnement",
        "biodiversite", "mangrove", "dechet", "decharges", "traitement des eaux",
        "assainissement", "rivieres", "barrage", "reseau d eau", "potable",
        "sargasse", "sargasses", "algues brunes", "smgeag",
        "eaux usees", "lagune", "recifs coralliens", "metaux lourds",
        "qualite de l eau", "office de l eau",
    ],
    "energie_transports": [
        "edf", "energie", "electricite", "coupure de courant", "carburant",
        "prix a la pompe", "transport", "bus", "tcsp", "route",
        "embouteillage", "rond point", "port", "aeroport", "mobilite",
        "navette", "bateau", "vol", "liaison", "rn", "deviation",
        "sara", "raffinerie", "carburant", "hydrocarbure",
    ],
    "sante_social": [
        "chu", "hopital", "clinique", "urgence", "sante", "soins", "vaccin",
        "epidemie", "virus", "dengue", "covid", "grippe", "handicap", "rsa",
        "solidarite", "famille", "insertion", "chomage partiel", "greve", "syndicat",
        "personnel soignant", "medecin", "infirmier", "maternite", "maternelle",
        "aide alimentaire", "banque alimentaire",
    ],
    "education": [
        "rentree", "scolaire", "ecole", "college", "lycee", "universite",
        "uag", "uagm", "rectorat", "enseignant", "eleve", "cantine", "bourse",
        "illettrisme", "orientation", "apprentissage", "jeunesse", "etudiant",
        "formation professionnelle", "pôle emploi formation",
    ],
    "economie_emploi": [
        "entreprise", "emploi", "investissement", "tourisme", "hotel",
        "subvention", "aide", "tpe", "pme", "chomage", "commerce", "zone d activite",
        "agriculture", "banane", "rhum", "canne", "peche", "industrie",
        "economie", "croissance", "pib", "budget", "fiscalite", "taxe",
        "medef", "chambre de commerce",
    ],
    "culture_patrimoine": [
        "carnaval", "festival", "patrimoine", "culture", "musee", "exposition",
        "concert", "gwo ka", "musique", "theatre", "danse", "tradition",
        "histoire", "memoire", "artiste", "gastronomie", "artisanat",
        "gwoka", "biguine", "zouk",
    ],
    "securite_justice": [
        "insecurite", "delinquance", "violence", "police", "gendarmerie",
        "brigade", "tribunal", "justice", "parquet", "procureur", "prison",
        "incendie", "pompiers", "secours", "accident", "controle", "douane",
        "homicide", "agression", "vol", "cambriolage", "meurtre",
        "correctionnel", "correctionnelle", "poursuivi", "poursuivie", "poursuites",
        "convoque", "convoquee", "mise en examen", "garde a vue", "condamne",
        "condamnation", "cour d appel", "chambre correctionnelle", "enquete",
        "instruction", "jugement", "inculpe", "prevenu", "detournement",
        "corruption", "abus de confiance", "escroquerie", "blanchiment",
        "trafic de drogue", "stupefiant", "cocaïne", "cannabis",
        "tir", "fusillade", "coup de feu",
    ],
    "politique_institutions": [
        "departement", "region", "collectivite", "prefet", "prefecture",
        "mairie", "municipal", "municipales", "gouvernement", "ministere", "assemblee",
        "conseil municipal", "conseil regional", "conseil departemental",
        "commission", "budget primitif", "deliberation", "depute", "senateur",
        "election", "elections", "vote", "scrutin", "candidat", "candidate",
        "liste", "campagne electorale", "premier tour", "second tour",
        "intercommunalite", "capex", "contrat de plan",
    ],
    "catastrophes_risques": [
        "cyclone", "ouragan", "tempete", "vigilance", "pluie", "inondation",
        "seisme", "tsunami", "eruption", "volcan", "orages", "alerte meteo",
        "depression", "rafale", "degats", "risques majeurs", "catastrophe",
        "alerte rouge", "alerte orange", "submersion",
    ],
    "chlordecone": [
        "chlordecone", "pesticide", "pollution agricole",
        "cancer", "contamination", "bananeraies", "scandale sanitaire",
        "aresag", "indemnisation", "victimes", "plan chlordecone",
        "action de groupe", "chlordecone iv", "opex", "contamination des sols",
    ],
}

# =========================
# MOTS-CLÉS DE GRAVITÉ
# =========================
KEYWORDS_GRAVITY: Dict[str, float] = {
    # CRITIQUES (0.85-0.95) - Crises majeures
    "mort": 0.95,
    "deces": 0.95,
    "tue": 0.95,
    "tues": 0.95,
    "decede": 0.95,
    "homicide": 0.95,
    "meurtre": 0.95,
    "assassinat": 0.95,
    "fusillade": 0.90,
    "coup de feu": 0.90,
    "tir": 0.85,
    "disparition": 0.90,
    "enlevement": 0.90,
    "kidnapping": 0.90,
    "prise d otage": 0.92,
    "attentat": 0.95,
    "explosion": 0.90,
    "incendie criminel": 0.88,
    "catastrophe": 0.90,
    "cyclone": 0.88,
    "ouragan": 0.88,
    "seisme": 0.90,
    "tsunami": 0.95,
    "epidemie": 0.85,
    "contamination massive": 0.88,
    "accident mortel": 0.85,
    "collision mortelle": 0.82,
    "mort sur la route": 0.85,
    "noyade": 0.78,
    "mort violente": 0.90,
    "feminicide": 0.92,
    "trafic d armes": 0.88,

    # GRAVES (0.70-0.84) - Affaires sérieuses
    "accident grave": 0.80,
    "blesse grave": 0.78,
    "agression": 0.75,
    "vol a main armee": 0.80,
    "braquage": 0.70,
    "viol": 0.85,
    "crise sanitaire": 0.82,
    "corruption": 0.78,
    "detournement": 0.78,
    "fraude": 0.75,
    "malversation": 0.75,
    "scandale": 0.78,
    "greve generale": 0.80,
    "manifestation violente": 0.78,
    "emeute": 0.82,
    "panne majeure": 0.75,
    "coupure d eau": 0.72,
    "penurie d eau": 0.72,
    "eau potable": 0.68,
    "coupure generale": 0.75,
    "coupure electrique": 0.68,
    "inondation": 0.78,
    "pollution grave": 0.75,
    "mise en examen": 0.90,
    "condamnation": 0.85,
    "garde a vue": 0.80,
    "trafic de drogue": 0.90,
    "saisie de drogue": 0.85,
    "stupefiant": 0.82,

    # IMPORTANTES (0.55-0.69) - Incidents significatifs
    "accident": 0.65,
    "blesse": 0.62,
    "incendie": 0.68,
    "vol": 0.60,
    "cambriolage": 0.60,
    "greve": 0.62,
    "manifestation": 0.58,
    "blocage": 0.60,
    "panne": 0.58,
    "coupure": 0.58,
    "dysfonctionnement": 0.55,
    "retard": 0.50,
    "perturbation": 0.55,
    "probleme": 0.52,
    "difficulte": 0.50,
    "tension": 0.58,
    "conflit": 0.60,
    "litige": 0.58,
    "plainte": 0.55,
    "vigilance rouge": 0.75,
    "vigilance orange": 0.65,
    "sargasses": 0.62,
    "smgeag": 0.60,

    # MODÉRÉES (0.30-0.54) - Incidents mineurs
    "incident": 0.45,
    "alerte": 0.48,
    "vigilance": 0.42,
    "rappel": 0.38,
    "conseil": 0.30,
    "recommandation": 0.30,
    "amelioration": 0.30,
    "renforcement": 0.35,
    "prevention": 0.35,

    # POLITIQUE & ÉLECTIONS (0.45-0.65) - Sujets de veille importants
    "election": 0.55,
    "elections": 0.55,
    "elections municipales": 0.65,
    "municipales": 0.60,
    "municipales 2026": 0.65,
    "candidat": 0.50,
    "candidate": 0.50,
    "candidature": 0.55,
    "liste electorale": 0.55,
    "campagne electorale": 0.55,
    "premier tour": 0.60,
    "second tour": 0.60,
    "scrutin": 0.55,
    "vote": 0.45,
    "bureau de vote": 0.50,
    "resultat": 0.45,
    "ballottage": 0.60,
    "coalition": 0.50,
    "programme electoral": 0.50,
    "conseil municipal": 0.45,
    "maire": 0.45,
    "adjointe": 0.40,
    "adjoint": 0.40,
    "opposition": 0.45,
    "majorite": 0.40,

    # ÉVÉNEMENTS POSITIFS (< 0.30) — ne créent pas d'affaire
    "festival": 0.15,
    "concert": 0.15,
    "exposition": 0.15,
    "inauguration": 0.20,
    "visite": 0.25,
    "reunion": 0.20,
    "conference": 0.20,
    "celebration": 0.15,
}

# =========================
# BASE DE DONNÉES DES PERSONNALITÉS
# =========================
# Clé unique par personnalité — patterns regex STRICTS (PRÉNOM + NOM exigés)
PERSONALITIES: Dict[str, Dict[str, Any]] = {
    # CONSEIL DÉPARTEMENTAL — Direction
    "Guy Losbar": {
        "patterns": [r"\bguy\s+losbar\b", r"\bg\.\s*losbar\b"],
        "fonction": "Président du Conseil Départemental",
        "importance": 0.95,
    },
    "Jean-Philippe Courtois": {
        "patterns": [r"\bjean[\s\-]philippe\s+courtois\b", r"\bj[\s\-]p\.?\s*courtois\b"],
        "fonction": "1er Vice-président CD971",
        "importance": 0.85,
    },
    "Maryse Etzol": {
        "patterns": [r"\bmaryse\s+etzol\b", r"\bm\.\s*etzol\b"],
        "fonction": "2ème Vice-présidente CD971",
        "importance": 0.80,
    },
    "Blaise Mornal": {
        "patterns": [r"\bblaise\s+mornal\b", r"\bb\.\s*mornal\b"],
        "fonction": "3ème Vice-président CD971",
        "importance": 0.75,
    },
    "Gabrielle Louis Carabin": {
        "patterns": [r"\bgabrielle\s+louis[\s\-]carabin\b"],
        "fonction": "4ème Vice-présidente CD971",
        "importance": 0.75,
    },
    "Ferdy Louisy": {
        "patterns": [r"\bferdy\s+louisy\b", r"\bf\.\s*louisy\b"],
        "fonction": "5ème Vice-président CD971",
        "importance": 0.75,
    },
    "Jocelyn Sapotille": {
        "patterns": [r"\bjocelyn\s+sapotille\b"],
        "fonction": "Conseiller départemental",
        "importance": 0.65,
    },
    "Marylène Adhel": {
        "patterns": [r"\bmarylene\s+adhel\b"],
        "fonction": "Conseillère départementale",
        "importance": 0.65,
    },
    "Sabrina Roger": {
        "patterns": [r"\bsabrina\s+roger\b"],
        "fonction": "Conseillère départementale",
        "importance": 0.65,
    },
    "Adrien Baron": {
        "patterns": [r"\badrien\s+baron\b"],
        "fonction": "9ème Vice-président CD971",
        "importance": 0.70,
    },
    "Jimmy Fausta": {
        "patterns": [r"\bjimmy\s+fausta\b"],
        "fonction": "Conseiller départemental",
        "importance": 0.65,
    },
    "Josette Borel-Lincertin": {
        "patterns": [r"\bjosette\s+borel[\s\-]lincertin\b", r"\bborel[\s\-]lincertin\b"],
        "fonction": "Ex-présidente CD971 / Conseillère",
        "importance": 0.80,
    },

    # CONSEIL RÉGIONAL — Direction
    "Ary Chalus": {
        "patterns": [r"\bary\s+chalus\b", r"\ba\.\s*chalus\b"],
        "fonction": "Président du Conseil Régional",
        "importance": 0.95,
    },
    "Jean-Marie Hubert": {
        "patterns": [r"\bjean[\s\-]marie\s+hubert\b", r"\bj[\s\-]m\.?\s*hubert\b"],
        "fonction": "1er Vice-président CR",
        "importance": 0.85,
    },
    "Marie-Luce Penchard": {
        "patterns": [r"\bmarie[\s\-]luce\s+penchard\b", r"\bm[\s\-]l\.?\s*penchard\b"],
        "fonction": "2ème Vice-présidente CR",
        "importance": 0.80,
    },
    "Jean Bardail": {
        "patterns": [r"\bjean\s+bardail\b", r"\bj\.\s*bardail\b"],
        "fonction": "3ème Vice-président CR",
        "importance": 0.75,
    },
    "Jim Lapin": {
        "patterns": [r"\bjim\s+lapin\b"],
        "fonction": "Conseiller régional",
        "importance": 0.65,
    },
    "Patrick Sellin": {
        "patterns": [r"\bpatrick\s+sellin\b"],
        "fonction": "Conseiller régional",
        "importance": 0.65,
    },

    # MAIRES PRINCIPAUX
    "Harry Durimel": {
        "patterns": [r"\bharry\s+durimel\b", r"\bh\.\s*durimel\b"],
        "fonction": "Maire de Pointe-à-Pitre",
        "importance": 0.85,
    },
    "Eric Jalton": {
        "patterns": [r"\beric\s+jalton\b", r"\be\.\s*jalton\b"],
        "fonction": "Maire des Abymes",
        "importance": 0.85,
    },
    "André Atallah": {
        "patterns": [r"\bandre\s+atallah\b", r"\ba\.\s*atallah\b"],
        "fonction": "Maire de Basse-Terre",
        "importance": 0.80,
    },
    "Jeanny Marc": {
        "patterns": [r"\bjeanny\s+marc\b"],
        "fonction": "Maire de Capesterre-Belle-Eau",
        "importance": 0.70,
    },
    "Cédric Cornet": {
        "patterns": [r"\bcedric\s+cornet\b", r"\bc\.\s*cornet\b"],
        "fonction": "Maire de Sainte-Rose",
        "importance": 0.65,
    },
    "Claudy Numa": {
        "patterns": [r"\bcloudy\s+numa\b", r"\bclaudy\s+numa\b"],
        "fonction": "Maire du Gosier",
        "importance": 0.70,
    },
    "Max Orville": {
        "patterns": [r"\bmax\s+orville\b", r"\bm\.\s*orville\b"],
        "fonction": "Maire de Baie-Mahault",
        "importance": 0.70,
    },
    "Jean-Claude Mounien": {
        "patterns": [r"\bjean[\s\-]claude\s+mounien\b"],
        "fonction": "Maire de Trois-Rivières",
        "importance": 0.65,
    },

    # DÉPUTÉS
    "Olivier Serva": {
        "patterns": [r"\bolivier\s+serva\b", r"\bo\.\s*serva\b"],
        "fonction": "Député 1ère circonscription",
        "importance": 0.85,
    },
    "Christian Baptiste": {
        "patterns": [r"\bchristian\s+baptiste\b", r"\bc\.\s*baptiste\b"],
        "fonction": "Député 2ème circonscription",
        "importance": 0.85,
    },
    "Max Mathiasin": {
        "patterns": [r"\bmax\s+mathiasin\b", r"\bm\.\s*mathiasin\b"],
        "fonction": "Député 3ème circonscription",
        "importance": 0.85,
    },
    "Elie Califer": {
        "patterns": [r"\belie\s+califer\b", r"\be\.\s*califer\b"],
        "fonction": "Député 4ème circonscription",
        "importance": 0.85,
    },

    # SÉNATEURS
    "Victorin Lurel": {
        "patterns": [r"\bvictorin\s+lurel\b", r"\bv\.\s*lurel\b"],
        "fonction": "Sénateur de la Guadeloupe",
        "importance": 0.85,
    },
    "Dominique Théophile": {
        "patterns": [r"\bdominique\s+theophile\b", r"\bd\.\s*theophile\b"],
        "fonction": "Sénatrice de la Guadeloupe",
        "importance": 0.85,
    },

    # PRÉFETS / ÉTAT
    "Xavier Lefort": {
        "patterns": [r"\bxavier\s+lefort\b"],
        "fonction": "Préfet de la Guadeloupe",
        "importance": 0.85,
    },
}

# =========================
# INSTITUTIONS
# =========================
# Institutions détectées avec casse stricte (CHU, EDF…) ou insensible
_CASE_SENSITIVE_INSTITUTIONS = frozenset(["CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF", "SARA", "DAAF", "DEAL", "BRGM"])

INSTITUTIONS: Dict[str, Dict[str, Any]] = {
    "CHU": {
        "patterns": [
            r"\bCHU\b",
            r"\bC\.H\.U\.\b",
            r"\bcentre\s+hospitalier\s+universitaire\b",
        ],
        "nom": "CHU de Pointe-à-Pitre",
        "importance": 0.80,
    },
    "SMGEAG": {
        "patterns": [r"\bSMGEAG\b", r"\bS\.M\.G\.E\.A\.G\.\b"],
        "nom": "Syndicat Mixte de Gestion de l'Eau",
        "importance": 0.75,
    },
    "EDF Guadeloupe": {
        "patterns": [r"\bEDF\b", r"\bE\.D\.F\.\b", r"\bedf\s+guadeloupe\b"],
        "nom": "EDF Guadeloupe",
        "importance": 0.75,
    },
    "ARS": {
        "patterns": [r"\bARS\b", r"\bA\.R\.S\.\b", r"\bagence\s+regionale\s+de\s+sante\b"],
        "nom": "Agence Régionale de Santé",
        "importance": 0.75,
    },
    "CAF": {
        "patterns": [r"\bCAF\b", r"\bcaisse\s+d\s*allocations\s+familiales\b"],
        "nom": "CAF Guadeloupe",
        "importance": 0.70,
    },
    "SARA": {
        "patterns": [r"\bSARA\b", r"\braffinerie\s+des\s+antilles\b", r"\braffinerie\s+sara\b"],
        "nom": "SARA — Raffinerie des Antilles",
        "importance": 0.70,
    },
    "DAAF": {
        "patterns": [r"\bDAAF\b", r"\bdirection\s+de\s+l\s*alimentation\b"],
        "nom": "DAAF Guadeloupe",
        "importance": 0.65,
    },
    "DEAL": {
        "patterns": [r"\bDEAL\b", r"\bdirection\s+de\s+l\s*environnement\b"],
        "nom": "DEAL Guadeloupe",
        "importance": 0.65,
    },
    "BRGM": {
        "patterns": [r"\bBRGM\b"],
        "nom": "BRGM Guadeloupe",
        "importance": 0.65,
    },
    "Préfecture": {
        "patterns": [
            r"\bprefecture\b",
            r"\bprefet\b(?!\s+de\s+police)",
            r"\bsous[\s\-]prefecture\b",
        ],
        "nom": "Préfecture de la Guadeloupe",
        "importance": 0.75,
    },
    "Rectorat": {
        "patterns": [r"\brectorat\b", r"\brecteur\b", r"\brectrice\b"],
        "nom": "Rectorat de la Guadeloupe",
        "importance": 0.70,
    },
}

# =========================
# ELECTED_INDEX — export attendu par media_noise_service & gpt_sentiment_validation
# =========================
ELECTED_INDEX: Dict[str, Dict[str, Any]] = {
    name: {"function": info["fonction"], "importance": info["importance"]}
    for name, info in PERSONALITIES.items()
}

# =========================
# PRÉ-COMPILATION DES PATTERNS (une seule fois au chargement)
# =========================

# Gravity: (keyword_display, compiled_pattern, score)
_GRAVITY_COMPILED: List[Tuple[str, re.Pattern, float]] = [
    (kw, re.compile(rf"(?<![a-z0-9]){re.escape(normalize(kw))}(?![a-z0-9])"), score)
    for kw, score in KEYWORDS_GRAVITY.items()
]

# Theme: dict[theme] → list of compiled patterns
_THEME_COMPILED: Dict[str, List[re.Pattern]] = {
    theme: [
        re.compile(rf"(?<![a-z0-9]){re.escape(normalize(kw))}(?![a-z0-9])")
        for kw in kws
    ]
    for theme, kws in THEME_TAXONOMY.items()
}

# Personalities: (name, list[compiled pattern]) — text déjà normalisé avant match
_PERSONALITY_COMPILED: List[Tuple[str, List[re.Pattern]]] = [
    (name, [re.compile(p) for p in info["patterns"]])
    for name, info in PERSONALITIES.items()
]

# Institutions: (name, list[compiled pattern], case_sensitive)
_INSTITUTION_COMPILED: List[Tuple[str, List[re.Pattern], bool]] = [
    (
        name,
        [re.compile(p, 0 if name in _CASE_SENSITIVE_INSTITUTIONS else re.IGNORECASE)
         for p in info["patterns"]],
        name in _CASE_SENSITIVE_INSTITUTIONS,
    )
    for name, info in INSTITUTIONS.items()
]

# Sentiment — module-level pour éviter la recréation à chaque appel
_SENTIMENT_POSITIVE = [
    "succes", "reussite", "victoire", "amelioration",
    "felicitation", "bravo", "inauguration", "ouverture",
    "progres", "excellent", "satisfaction", "accord", "signature",
    "developpement", "avancee",
]
_SENTIMENT_NEGATIVE = [
    "mort", "deces", "accident", "crise", "echec",
    "probleme", "violence", "agression", "greve", "panne",
    "catastrophe", "drame", "tragedie", "scandale",
    "corruption", "fraude", "conflit", "litige",
]

# =========================
# FONCTIONS DE DÉTECTION
# =========================

def detect_entities(text: str) -> Tuple[List[str], List[str]]:
    """
    Détecte personnalités et institutions.

    Utilise normalize() sur le texte pour la correspondance insensible aux accents.
    Les institutions case-sensitive (CHU, EDF…) sont testées sur le texte original.
    """
    text_norm = normalize(text)   # accent-stripped + lowercase
    personalities_found: List[str] = []
    institutions_found: List[str] = []

    for name, patterns in _PERSONALITY_COMPILED:
        for pat in patterns:
            if pat.search(text_norm):
                personalities_found.append(name)
                break

    for name, patterns, is_case_sensitive in _INSTITUTION_COMPILED:
        search_text = text if is_case_sensitive else text_norm
        for pat in patterns:
            if pat.search(search_text):
                institutions_found.append(name)
                break

    return personalities_found, institutions_found


def detect_theme(text: str, title: str = "") -> Tuple[str, int]:
    """
    Détecte le thème principal (titre pondéré ×3).
    Patterns pré-compilés à l'import — O(1) compilation par appel.
    """
    text_norm = normalize(text)
    title_norm = normalize(title) if title else ""
    theme_scores: Dict[str, int] = {}

    for theme, patterns in _THEME_COMPILED.items():
        score = 0
        for pat in patterns:
            if title_norm and pat.search(title_norm):
                score += 3
            elif pat.search(text_norm):
                score += 1
        if score > 0:
            theme_scores[theme] = score

    if theme_scores:
        best = max(theme_scores.items(), key=lambda x: x[1])
        return best[0], best[1]
    return "general", 0


def calculate_gravity(text: str) -> Tuple[float, List[str]]:
    """
    Calcule la gravité basée sur les mots-clés (word-boundary, pré-compilé).
    Retourne (score_gravité, mots_clés_trouvés).
    """
    text_norm = normalize(text)
    max_gravity = 0.0
    keywords_found: List[str] = []

    for kw, pattern, score in _GRAVITY_COMPILED:
        if pattern.search(text_norm):
            keywords_found.append(kw)
            if score > max_gravity:
                max_gravity = score

    return max_gravity, keywords_found


def analyze_sentiment(text: str) -> str:
    """Analyse de sentiment basique. Utilise normalize() pour l'insensibilité aux accents."""
    text_norm = normalize(text)
    pos_count = sum(1 for w in _SENTIMENT_POSITIVE if w in text_norm)
    neg_count = sum(1 for w in _SENTIMENT_NEGATIVE if w in text_norm)

    if neg_count > pos_count + 1:
        return "negatif"
    elif pos_count > neg_count + 1:
        return "positif"
    return "neutre"


# =========================
# FONCTION PRINCIPALE D'ENRICHISSEMENT
# =========================
def infer_tags_and_theme(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrichit l'article avec détection ULTRA-STRICTE.

    Ajoute :
    - theme, theme_score
    - elected, institutions, entities
    - is_affair, affair_type, gravity_score, importance_score
    - sentiment, keywords_found
    - _tags (liste de tags techniques)
    """
    title = article.get("title", "")
    content = article.get("content", "") or article.get("text", "")
    full_text = f"{title} {content}"

    theme, theme_score = detect_theme(full_text, title=title)
    personalities, institutions = detect_entities(full_text)
    all_entities = personalities + institutions
    gravity_score, keywords_found = calculate_gravity(full_text)

    # Boost territorial si institution connue avec incident
    territorial_boost = 0.0
    if institutions and gravity_score > 0.50:
        if "CHU" in institutions:
            territorial_boost = 0.10
        elif "SMGEAG" in institutions or "EDF Guadeloupe" in institutions:
            territorial_boost = 0.08
    gravity_score = min(1.0, gravity_score + territorial_boost)

    is_affair = gravity_score >= 0.65

    if gravity_score >= 0.85:
        affair_type = "crise_majeure"
    elif gravity_score >= 0.75:
        affair_type = "affaire_grave"
    elif gravity_score >= 0.65:
        affair_type = "affaire_importante"
    elif gravity_score >= 0.50:
        affair_type = "incident_mineur"
    else:
        affair_type = "routine"

    sentiment = analyze_sentiment(full_text)

    importance_score = gravity_score
    if personalities:
        max_imp = max(PERSONALITIES[p]["importance"] for p in personalities)
        importance_score = min(1.0, importance_score + max_imp * 0.15)
    if institutions:
        importance_score = min(1.0, importance_score + 0.10)

    tags = set(article.get("_tags", []))
    if article.get("site"):
        tags.add(f"site:{normalize(str(article['site']))}")
    if article.get("source"):
        tags.add(f"source:{normalize(str(article['source']))}")
    if theme:
        tags.add(f"theme:{theme}")
    for person in personalities:
        tags.add(f"personnalite:{normalize(person)}")
    for inst in institutions:
        tags.add(f"institution:{normalize(inst)}")
    if is_affair:
        tags.add("is_affair")
        tags.add(f"affair_type:{affair_type}")
    tags.add(f"sentiment:{sentiment}")

    article.update({
        "_tags": sorted(tags),
        "theme": theme,
        "theme_score": int(theme_score),
        "elected": personalities,
        "institutions": institutions,
        "entities": all_entities,
        "sentiment": sentiment,
        "is_affair": is_affair,
        "affair_type": affair_type,
        "gravity_score": round(gravity_score, 3),
        "importance_score": round(importance_score, 3),
        "keywords_found": keywords_found,
        "classification_confidence": 0.90 if keywords_found and all_entities else 0.75,
        "_analysis_method": "rule_based_ultra_strict",
        "_personalities_detected": len(personalities),
        "_institutions_detected": len(institutions),
        "_territorial_boost": round(territorial_boost, 3) if territorial_boost else 0,
    })
    return article


# =========================
# UTILITAIRES
# =========================
def week_key(dt: datetime) -> str:
    """Génère une clé semaine ISO (YYYY-Www)."""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


# =========================
# TESTS
# =========================
if __name__ == "__main__":
    test_cases = [
        {"title": "Le CHU est en grève", "content": "Le personnel du CHU manifeste aujourd'hui"},
        {"title": "Il a chuté dans les escaliers", "content": "Un homme a chuté lourdement"},
        {"title": "Guy Losbar rencontre le préfet", "content": "Le président du Conseil départemental Guy Losbar"},
        {"title": "Festival de musique à Pointe-à-Pitre", "content": "Grande fête culturelle organisée par la mairie"},
        {"title": "Accident mortel sur la RN1", "content": "Trois personnes sont mortes dans une collision"},
        {"title": "Dominique Théophile demande des explications", "content": "La sénatrice Théophile a interpellé le préfet"},
        {"title": "Victorin Lurel réagit au scandale", "content": "Le sénateur Lurel dénonce une fraude"},
        {"title": "Sargasses : crise sanitaire sur les plages", "content": "Les algues menacent le tourisme et la santé"},
        {"title": "SMGEAG : coupure d'eau dans plusieurs communes", "content": "La SMGEAG annonce une interruption"},
    ]

    print("=" * 70)
    print("TESTS DE DÉTECTION ULTRA-STRICTE")
    print("=" * 70)

    for i, test in enumerate(test_cases, 1):
        result = infer_tags_and_theme(test.copy())
        print(f"\n{i}. {test['title']}")
        print(f"   Personnalités : {result.get('elected', [])}")
        print(f"   Institutions  : {result.get('institutions', [])}")
        print(f"   Est affaire   : {result.get('is_affair')} ({result.get('affair_type')})")
        print(f"   Gravité       : {result.get('gravity_score')}")
        print(f"   Thème         : {result.get('theme')}")
        print(f"   Sentiment     : {result.get('sentiment')}")
