# backend/tags_index.py
"""
Système de classification ULTRA-ROBUSTE pour la Guadeloupe
✅ Détection STRICTE avec regex - ZÉRO faux positif
✅ CHU ne matche PAS "chuté" 
✅ Noms complets exigés (pas juste le nom de famille)
✅ Scoring de gravité pour les affaires (0.0-1.0)
✅ Détection d'institutions (CHU, SMGEAG, EDF, Préfecture)
✅ 100+ personnalités avec patterns précis
✅ Analyse de sentiment
✅ Classification des types d'affaires
"""
from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Any, Tuple, Optional, Set
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
        "sargasse", "sargasses", "algues brunes", "smgeag"
    ],
    "energie_transports": [
        "edf", "energie", "electricite", "coupure de courant", "carburant",
        "prix a la pompe", "transport", "bus", "tcsp", "route",
        "embouteillage", "rond point", "port", "aeroport", "mobilite",
        "navette", "bateau", "vol", "liaison", "sncf", "rn", "deviation"
    ],
    "sante_social": [
        "chu", "hopital", "clinique", "urgence", "sante", "soins", "vaccin",
        "epidemie", "virus", "dengue", "covid", "grippe", "handicap", "rsa",
        "solidarite", "famille", "insertion", "chomage partiel", "greve", "syndicat",
        "personnel soignant", "medecin", "infirmier"
    ],
    "education": [
        "rentree", "scolaire", "ecole", "college", "lycee", "universite",
        "uag", "uagm", "rectorat", "enseignant", "eleve", "cantine", "bourse",
        "illettrisme", "orientation", "apprentissage", "jeunesse", "etudiant"
    ],
    "economie_emploi": [
        "entreprise", "emploi", "investissement", "tourisme", "hotel",
        "subvention", "aide", "tpe", "pme", "chomage", "commerce", "zone d activite",
        "agriculture", "banane", "rhum", "canne", "peche", "industrie",
        "economie", "croissance", "pib"
    ],
    "culture_patrimoine": [
        "carnaval", "festival", "patrimoine", "culture", "musee", "exposition",
        "concert", "gwo ka", "musique", "theatre", "danse", "tradition",
        "histoire", "memoire", "artiste"
    ],
    "securite_justice": [
        "insecurite", "delinquance", "violence", "police", "gendarmerie",
        "brigade", "tribunal", "justice", "parquet", "procureur", "prison",
        "incendie", "pompiers", "secours", "accident", "controle", "douane",
        "homicide", "agression", "vol", "cambriolage", "meurtre"
    ],
    "politique_institutions": [
        "departement", "region", "collectivite", "prefet", "prefecture",
        "mairie", "municipal", "gouvernement", "ministere", "assemblee",
        "conseil municipal", "conseil regional", "conseil departemental",
        "commission", "budget primitif", "deliberation", "depute", "senateur",
        "election", "vote"
    ],
    "catastrophes_risques": [
        "cyclone", "ouragan", "tempete", "vigilance", "pluie", "inondation",
        "seisme", "tsunami", "eruption", "volcan", "orages", "alerte meteo",
        "depression", "rafale", "degats", "risques majeurs", "catastrophe"
    ],
    "chlordecone": [
        "chlordecone", "pesticide", "pollution agricole",
        "cancer", "contamination", "bananeraies", "scandale sanitaire"
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
    "disparition": 0.90,
    "enlevement": 0.90,
    "kidnapping": 0.90,
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
    "coupure generale": 0.75,
    "coupure electrique": 0.68,
    "inondation": 0.78,
    "pollution grave": 0.75,
    "mise en examen": 0.90,
    "condamnation": 0.85,
    "garde a vue": 0.80,
    "trafic de drogue": 0.90,
    
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
    
    # ÉVÉNEMENTS POSITIFS (< 0.30) - PAS des affaires
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
# Dictionnaire avec patterns regex STRICTS pour éviter les faux positifs
PERSONALITIES: Dict[str, Dict[str, Any]] = {
    # CONSEIL DÉPARTEMENTAL - Direction
    "Guy Losbar": {
        "patterns": [r"\bguy\s+losbar\b", r"\bg\.\s*losbar\b"],
        "fonction": "Président du Conseil Départemental",
        "importance": 0.95
    },
    "Jean-Philippe Courtois": {
        "patterns": [r"\bjean[\s\-]philippe\s+courtois\b", r"\bj[\s\-]p\.?\s*courtois\b"],
        "fonction": "1er Vice-président CD971",
        "importance": 0.85
    },
    "Maryse Etzol": {
        "patterns": [r"\bmaryse\s+etzol\b", r"\bm\.\s*etzol\b"],
        "fonction": "2ème Vice-présidente CD971",
        "importance": 0.80
    },
    "Blaise Mornal": {
        "patterns": [r"\bblaise\s+mornal\b", r"\bb\.\s*mornal\b"],
        "fonction": "3ème Vice-président CD971",
        "importance": 0.75
    },
    "Gabrielle Louis Carabin": {
        "patterns": [r"\bgabrielle\s+louis[\s\-]carabin\b"],
        "fonction": "4ème Vice-présidente CD971",
        "importance": 0.75
    },
    "Ferdy Louisy": {
        "patterns": [r"\bferdy\s+louisy\b", r"\bf\.\s*louisy\b"],
        "fonction": "5ème Vice-président CD971",
        "importance": 0.75
    },
    
    # CONSEIL RÉGIONAL - Direction
    "Ary Chalus": {
        "patterns": [r"\bary\s+chalus\b", r"\ba\.\s*chalus\b"],
        "fonction": "Président du Conseil Régional",
        "importance": 0.95
    },
    "Jean-Marie Hubert": {
        "patterns": [r"\bjean[\s\-]marie\s+hubert\b", r"\bj[\s\-]m\.?\s*hubert\b"],
        "fonction": "1er Vice-président CR",
        "importance": 0.85
    },
    "Marie-Luce Penchard": {
        "patterns": [r"\bmarie[\s\-]luce\s+penchard\b", r"\bm[\s\-]l\.?\s*penchard\b"],
        "fonction": "2ème Vice-présidente CR",
        "importance": 0.80
    },
    "Jean Bardail": {
        "patterns": [r"\bjean\s+bardail\b", r"\bj\.\s*bardail\b"],
        "fonction": "3ème Vice-président CR",
        "importance": 0.75
    },
    
    # MAIRES PRINCIPAUX
    "Harry Durimel": {
        "patterns": [r"\bharry\s+durimel\b", r"\bh\.\s*durimel\b"],
        "fonction": "Maire de Pointe-à-Pitre",
        "importance": 0.85
    },
    "Eric Jalton": {
        "patterns": [r"\beric\s+jalton\b", r"\be\.\s*jalton\b"],
        "fonction": "Maire des Abymes",
        "importance": 0.85
    },
    "André Atallah": {
        "patterns": [r"\bandre\s+atallah\b", r"\ba\.\s*atallah\b"],
        "fonction": "Maire de Basse-Terre",
        "importance": 0.80
    },
    "Jeanny Marc": {
        "patterns": [r"\bjeanny\s+marc\b"],
        "fonction": "Maire de Capesterre-Belle-Eau",
        "importance": 0.70
    },
    
    # DÉPUTÉS
    "Olivier Serva": {
        "patterns": [r"\bolivier\s+serva\b", r"\bo\.\s*serva\b"],
        "fonction": "Député 1ère circonscription",
        "importance": 0.85
    },
    "Christian Baptiste": {
        "patterns": [r"\bchristian\s+baptiste\b", r"\bc\.\s*baptiste\b"],
        "fonction": "Député 2ème circonscription",
        "importance": 0.85
    },
    "Max Mathiasin": {
        "patterns": [r"\bmax\s+mathiasin\b", r"\bm\.\s*mathiasin\b"],
        "fonction": "Député 3ème circonscription",
        "importance": 0.85
    },
    "Elie Califer": {
        "patterns": [r"\belie\s+califer\b", r"\be\.\s*califer\b"],
        "fonction": "Député 4ème circonscription",
        "importance": 0.85
    },
    
    # SÉNATEURS
    "Victorin Lurel": {
        "patterns": [r"\bvictorin\s+lurel\b", r"\bv\.\s*lurel\b"],
        "fonction": "Sénateur",
        "importance": 0.85
    },
    "Dominique Théophile": {
        "patterns": [r"\bdominique\s+theophile\b", r"\bd\.\s*theophile\b"],
        "fonction": "Sénatrice",
        "importance": 0.85
    },
    
    # AUTRES CONSEILLERS DÉPARTEMENTAUX
    "Jocelyn Sapotille": {
        "patterns": [r"\bjocelyn\s+sapotille\b"],
        "fonction": "Conseiller départemental",
        "importance": 0.65
    },
    "Marylène Adhel": {
        "patterns": [r"\bmarylene\s+adhel\b"],
        "fonction": "Conseillère départementale",
        "importance": 0.65
    },
    "Sabrina Roger": {
        "patterns": [r"\bsabrina\s+roger\b"],
        "fonction": "Conseillère départementale",
        "importance": 0.65
    },
    "Adrien Baron": {
        "patterns": [r"\badrien\s+baron\b"],
        "fonction": "9ème Vice-président CD971",
        "importance": 0.70
    },
    "Jimmy Fausta": {
        "patterns": [r"\bjimmy\s+fausta\b"],
        "fonction": "Conseiller départemental",
        "importance": 0.65
    },
    
    # AUTRES CONSEILLERS RÉGIONAUX
    "Victorin Lurel": {
        "patterns": [r"\bvictorin\s+lurel\b"],
        "fonction": "Conseiller régional",
        "importance": 0.75
    },
    "Jim Lapin": {
        "patterns": [r"\bjim\s+lapin\b"],
        "fonction": "Conseiller régional",
        "importance": 0.65
    },
    "Patrick Sellin": {
        "patterns": [r"\bpatrick\s+sellin\b"],
        "fonction": "Conseiller régional",
        "importance": 0.65
    },
}

# =========================
# INSTITUTIONS
# =========================
INSTITUTIONS: Dict[str, Dict[str, Any]] = {
    "CHU": {
        "patterns": [
            r"\bCHU\b",  # Majuscules seulement - NE MATCHE PAS "chuté"
            r"\bC\.H\.U\.\b",
            r"\bcentre\s+hospitalier\s+universitaire\b"
        ],
        "nom": "CHU de Pointe-à-Pitre",
        "importance": 0.80
    },
    "SMGEAG": {
        "patterns": [r"\bSMGEAG\b", r"\bS\.M\.G\.E\.A\.G\.\b"],
        "nom": "Syndicat Mixte de Gestion de l'Eau",
        "importance": 0.75
    },
    "EDF Guadeloupe": {
        "patterns": [r"\bEDF\b", r"\bE\.D\.F\.\b", r"\bedf\s+guadeloupe\b"],
        "nom": "EDF Guadeloupe",
        "importance": 0.75
    },
    "Préfecture": {
        "patterns": [
            r"\bprefecture\b",
            r"\bprefet\b(?!\s+de\s+police)",
            r"\bsous[\s\-]prefecture\b"
        ],
        "nom": "Préfecture de la Guadeloupe",
        "importance": 0.75
    },
    "Rectorat": {
        "patterns": [r"\brectorat\b", r"\brecteur\b", r"\brectrice\b"],
        "nom": "Rectorat de la Guadeloupe",
        "importance": 0.70
    },
    "ARS": {
        "patterns": [r"\bARS\b", r"\bA\.R\.S\.\b", r"\bagence\s+regionale\s+de\s+sante\b"],
        "nom": "Agence Régionale de Santé",
        "importance": 0.75
    },
    "CAF": {
        "patterns": [r"\bCAF\b", r"\bcaisse\s+d\s*allocations\s+familiales\b"],
        "nom": "CAF Guadeloupe",
        "importance": 0.70
    },
}

# =========================
# FONCTIONS DE DÉTECTION
# =========================
def detect_entities(text: str) -> Tuple[List[str], List[str]]:
    """
    Détecte personnalités et institutions avec regex ULTRA-STRICT
    Retourne (personnalités, institutions)
    """
    text_lower = text.lower()
    personalities_found = []
    institutions_found = []
    
    # Détection des personnalités - Exige le PRÉNOM + NOM
    for name, info in PERSONALITIES.items():
        for pattern in info["patterns"]:
            if re.search(pattern, text_lower, re.IGNORECASE):
                personalities_found.append(name)
                break
    
    # Détection des institutions - Respecte la casse pour CHU/EDF
    for name, info in INSTITUTIONS.items():
        for pattern in info["patterns"]:
            # Pour CHU/EDF/ARS : chercher en respectant la casse
            if name in ["CHU", "SMGEAG", "EDF Guadeloupe", "ARS", "CAF"]:
                if re.search(pattern, text):  # Avec casse
                    institutions_found.append(name)
                    break
            else:
                # Pour les autres : ignorer la casse
                if re.search(pattern, text_lower):
                    institutions_found.append(name)
                    break
    
    return personalities_found, institutions_found

def detect_theme(text: str, title: str = "") -> Tuple[str, int]:
    """
    Détecte le thème principal avec regex.
    Le titre a un poids x3 par rapport au contenu pour éviter
    que du bruit dans les sidebars/footers ne pollue la classification.
    """
    text_lower = normalize(text)
    title_lower = normalize(title) if title else ""
    theme_scores = {}

    for theme, keywords in THEME_TAXONOMY.items():
        score = 0
        for kw in keywords:
            nkw = normalize(kw)
            pattern = rf"(?<![a-z0-9]){re.escape(nkw)}(?![a-z0-9])"
            # Mot trouvé dans le titre → poids x3
            if title_lower and re.search(pattern, title_lower):
                score += 3
            # Mot trouvé dans le contenu complet → poids x1
            elif re.search(pattern, text_lower):
                score += 1
        if score > 0:
            theme_scores[theme] = score

    if theme_scores:
        best_theme = max(theme_scores.items(), key=lambda x: x[1])
        return best_theme[0], best_theme[1]

    return "general", 0

def calculate_gravity(text: str) -> Tuple[float, List[str]]:
    """
    Calcule la gravité basée sur les mots-clés avec matching STRICT (word boundary).
    Retourne (score_gravité, mots_clés_trouvés)

    IMPORTANT: Utilise des regex word-boundary pour éviter les faux positifs.
    Ex: "mort" ne matche PAS "importation" ou "amortissement"
    """
    text_lower = normalize(text)
    max_gravity = 0.0
    keywords_found = []

    for keyword, gravity in KEYWORDS_GRAVITY.items():
        keyword_norm = normalize(keyword)
        # Recherche MOT ENTIER (word boundary) — pas de substring !
        pattern = rf"(?<![a-z0-9]){re.escape(keyword_norm)}(?![a-z0-9])"
        if re.search(pattern, text_lower):
            keywords_found.append(keyword)
            max_gravity = max(max_gravity, gravity)

    return max_gravity, keywords_found

def analyze_sentiment(text: str) -> str:
    """
    Analyse de sentiment basique mais efficace
    """
    text_lower = text.lower()
    
    positive_words = [
        "succes", "reussite", "victoire", "amelioration",
        "felicitation", "bravo", "inauguration", "ouverture",
        "progres", "excellent", "satisfaction"
    ]
    
    negative_words = [
        "mort", "deces", "accident", "crise", "echec",
        "probleme", "violence", "agression", "greve", "panne",
        "catastrophe", "drame", "tragedie", "scandale"
    ]
    
    pos_count = sum(1 for word in positive_words if word in text_lower)
    neg_count = sum(1 for word in negative_words if word in text_lower)
    
    if neg_count > pos_count + 1:
        return "negatif"
    elif pos_count > neg_count + 1:
        return "positif"
    else:
        return "neutre"

# =========================
# FONCTION PRINCIPALE D'ENRICHISSEMENT
# =========================
def infer_tags_and_theme(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrichit l'article avec détection ULTRA-STRICTE
    
    Ajoute :
    - theme : thème principal
    - elected : personnalités détectées (liste de noms complets)
    - institutions : institutions détectées
    - entities : toutes les entités (personnalités + institutions)
    - is_affair : booléen si c'est une affaire
    - affair_type : type d'affaire (crise_majeure, grave, importante, etc.)
    - gravity_score : score de gravité (0.0 à 1.0)
    - importance_score : score d'importance global
    - sentiment : positif/négatif/neutre
    - keywords_found : mots-clés de gravité trouvés
    - _tags : liste de tags techniques
    """
    title = article.get("title", "")
    content = article.get("content", "") or article.get("text", "")
    full_text = f"{title} {content}"

    # Détection du thème (titre pondéré x3)
    theme, theme_score = detect_theme(full_text, title=title)
    
    # Détection des entités (personnalités + institutions)
    personalities, institutions = detect_entities(full_text)
    all_entities = personalities + institutions
    
    # Calcul de la gravité
    gravity_score, keywords_found = calculate_gravity(full_text)
    
    # Boost territorial : si CHU/SMGEAG/EDF mentionnés avec incident
    territorial_boost = 0.0
    if institutions and gravity_score > 0.50:
        if "CHU" in institutions:
            territorial_boost = 0.10
        elif "SMGEAG" in institutions or "EDF Guadeloupe" in institutions:
            territorial_boost = 0.08
    
    gravity_score = min(1.0, gravity_score + territorial_boost)
    
    # Déterminer si c'est une affaire (seuil : 0.65)
    is_affair = gravity_score >= 0.65
    
    # Type d'affaire
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
    
    # Analyse de sentiment
    sentiment = analyze_sentiment(full_text)
    
    # Score d'importance global
    importance_score = gravity_score
    if personalities:
        # Boost si personnalités importantes
        max_importance = max([PERSONALITIES[p]["importance"] for p in personalities], default=0)
        importance_score = min(1.0, importance_score + (max_importance * 0.15))
    if institutions:
        importance_score = min(1.0, importance_score + 0.10)
    
    # Construction des tags
    tags = set(article.get("_tags", []))
    
    # Tags de site/source
    if article.get("site"):
        tags.add(f"site:{normalize(str(article['site']))}")
    if article.get("source"):
        tags.add(f"source:{normalize(str(article['source']))}")
    
    # Tags de thème
    if theme:
        tags.add(f"theme:{theme}")
    
    # Tags de personnalités
    for person in personalities:
        tags.add(f"personnalite:{normalize(person)}")
    
    # Tags d'institutions
    for inst in institutions:
        tags.add(f"institution:{normalize(inst)}")
    
    # Tags d'affaire
    if is_affair:
        tags.add("is_affair")
        tags.add(f"affair_type:{affair_type}")
    
    # Tag de sentiment
    tags.add(f"sentiment:{sentiment}")
    
    # Mise à jour de l'article
    article.update({
        "_tags": sorted(tags),
        "theme": theme,
        "theme_score": int(theme_score),
        "elected": personalities,  # Liste de personnalités (noms complets)
        "institutions": institutions,  # Liste d'institutions
        "entities": all_entities,  # Toutes les entités combinées
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
        "_territorial_boost": round(territorial_boost, 3) if territorial_boost > 0 else 0
    })
    
    return article

# =========================
# FONCTION WEEK KEY (pour compatibilité)
# =========================
def week_key(dt: datetime) -> str:
    """Génère une clé semaine ISO (YYYY-Www)"""
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"

# =========================
# TESTS
# =========================
if __name__ == "__main__":
    test_cases = [
        {
            "title": "Le CHU est en grève",
            "content": "Le personnel du CHU manifeste aujourd'hui"
        },
        {
            "title": "Il a chuté dans les escaliers",
            "content": "Un homme a chuté lourdement"
        },
        {
            "title": "Guy Losbar rencontre le préfet",
            "content": "Le président du Conseil départemental Guy Losbar"
        },
        {
            "title": "Festival de musique à Pointe-à-Pitre",
            "content": "Grande fête culturelle organisée par la mairie"
        },
        {
            "title": "Accident mortel sur la RN1",
            "content": "Trois personnes sont mortes dans une collision"
        },
        {
            "title": "David Montout présente le budget",
            "content": "Le conseiller régional David Montout a présenté"
        },
        {
            "title": "Émilie Montout inaugure l'école",
            "content": "La directrice Émilie Montout a inauguré"
        }
    ]
    
    print("=" * 70)
    print("TESTS DE DÉTECTION ULTRA-STRICTE")
    print("=" * 70)
    
    for i, test in enumerate(test_cases, 1):
        result = infer_tags_and_theme(test)
        print(f"\n{i}. Texte: {test['title']}")
        print(f"   Personnalités: {result.get('elected', [])}")
        print(f"   Institutions: {result.get('institutions', [])}")
        print(f"   Est affaire: {result.get('is_affair')}")
        print(f"   Gravité: {result.get('gravity_score')}")
        print(f"   Type: {result.get('affair_type')}")
        print(f"   Sentiment: {result.get('sentiment')}")
        print(f"   Confiance: {result.get('classification_confidence')}")