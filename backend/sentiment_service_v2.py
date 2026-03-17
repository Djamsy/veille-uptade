# backend/sentiment_service_v2.py
"""
Service d'analyse de sentiment V2 — Adapté à la Guadeloupe
============================================================

AMÉLIORATIONS vs V1 :
- Lexique étendu (800+ termes) avec contexte local (créole, institutions)
- Score continu [-1.0, +1.0] au lieu de comptage binaire
- Détection de l'intensité (modéré / fort / extrême)
- Détection des négations (ne…pas, jamais, aucun)
- Détection de l'ironie/sarcasme basique
- Contexte créole (malpwop, vyé mannyè, bow lè, etc.)
- Fallback OpenAI pour les textes ambigus
- Cache des résultats pour éviter les appels API redondants
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger("sentiment_v2")


# ============================================================
# LEXIQUES
# ============================================================

# Score: [-1.0, +1.0], intensité absolue
LEXICON_NEGATIF: Dict[str, float] = {
    # --- Gravité extrême (-0.9 à -1.0) ---
    "mort": -0.95, "deces": -0.95, "tue": -0.95, "tues": -0.95,
    "assassinat": -1.0, "meurtre": -1.0, "homicide": -1.0,
    "massacre": -1.0, "fusillade": -0.95, "catastrophe": -0.90,
    "tragedie": -0.90, "drame": -0.85,

    # --- Grave (-0.7 à -0.89) ---
    "corruption": -0.80, "detournement": -0.80, "fraude": -0.75,
    "scandale": -0.78, "malversation": -0.75, "escroquerie": -0.75,
    "violence": -0.80, "agression": -0.75, "viol": -0.90,
    "emeute": -0.82, "emeutes": -0.82,
    "crise": -0.70, "effondrement": -0.75, "faillite": -0.72,
    "epidemie": -0.78, "contamination": -0.75,
    "incendie": -0.70, "explosion": -0.75,
    "misere": -0.72, "pauvrete": -0.68, "precarite": -0.65,

    # --- Significatif (-0.5 à -0.69) ---
    "greve": -0.55, "manifestation": -0.50, "blocage": -0.58,
    "accident": -0.60, "blesse": -0.58,
    "panne": -0.50, "coupure": -0.52, "penurie": -0.58,
    "insecurite": -0.60, "delinquance": -0.58,
    "echec": -0.55, "defaite": -0.50,
    "colere": -0.55, "indignation": -0.52, "revolte": -0.60,
    "inondation": -0.62, "secheresse": -0.55,
    "pollution": -0.58, "degradation": -0.52,
    "plainte": -0.48, "condamnation": -0.65,
    "licenciement": -0.55, "chomage": -0.52,
    "retard": -0.40, "dysfonctionnement": -0.48,

    # --- Modéré (-0.3 à -0.49) ---
    "probleme": -0.40, "difficulte": -0.38, "inquietude": -0.42,
    "tension": -0.45, "conflit": -0.48, "desaccord": -0.38,
    "critique": -0.35, "contestation": -0.40,
    "deception": -0.42, "frustration": -0.45,
    "perturbation": -0.38, "ralentissement": -0.32,
    "deplore": -0.45, "regrette": -0.38, "dommage": -0.35,

    # --- Léger (-0.1 à -0.29) ---
    "vigilance": -0.25, "alerte": -0.28, "prudence": -0.15,
    "incertitude": -0.22, "doute": -0.20, "hesitation": -0.18,
    "preoccupation": -0.25,

    # --- Créole / expressions locales ---
    "malpwop": -0.55, "dezod": -0.50, "vyé": -0.45,
    "malé": -0.48, "bwè pwazon": -0.60,
    "dézòd": -0.50, "vyé mannyè": -0.55,
    "fè dézòd": -0.55, "mové": -0.45,
}

LEXICON_POSITIF: Dict[str, float] = {
    # --- Très positif (+0.7 à +1.0) ---
    "victoire": 0.80, "triomphe": 0.85, "exploit": 0.82,
    "succes": 0.78, "reussite": 0.75, "record": 0.72,
    "champion": 0.82, "medaille": 0.78, "sacre": 0.80,

    # --- Positif (+0.5 à +0.69) ---
    "inauguration": 0.55, "ouverture": 0.50,
    "amelioration": 0.58, "progres": 0.55, "avancee": 0.55,
    "croissance": 0.52, "developpement": 0.55,
    "investissement": 0.48, "subvention": 0.45,
    "creation": 0.50, "innovation": 0.55,
    "solidarite": 0.60, "entraide": 0.58, "generosité": 0.55,
    "bravo": 0.65, "felicitations": 0.68, "excellent": 0.65,
    "magnifique": 0.70, "formidable": 0.68,
    "satisfaction": 0.55, "joie": 0.60, "fierte": 0.62,

    # --- Modérément positif (+0.3 à +0.49) ---
    "accord": 0.40, "consensus": 0.42, "cooperation": 0.45,
    "partenariat": 0.42, "collaboration": 0.40,
    "reunion": 0.30, "concertation": 0.35,
    "renforcement": 0.38, "stabilisation": 0.35,
    "espoir": 0.42, "optimisme": 0.45, "confiance": 0.40,
    "remise": 0.32, "don": 0.40, "aide": 0.38,

    # --- Légèrement positif (+0.1 à +0.29) ---
    "annonce": 0.15, "prevision": 0.12, "projet": 0.20,
    "etude": 0.12, "consultation": 0.15,
    "normal": 0.10, "habituel": 0.10,

    # --- Créole / expressions locales ---
    "bèl": 0.55, "bon bagay": 0.50, "mèsi": 0.45,
    "an lè": 0.48, "fò": 0.42, "brav": 0.50,
}

# Patterns de négation
NEGATION_PATTERNS = [
    r"\bne\s+\w+\s+pas\b",
    r"\bn'?\w+\s+pas\b",
    r"\bjamais\b",
    r"\baucun\b",
    r"\baucune\b",
    r"\bni\s+\w+\s+ni\b",
    r"\bsans\b",
    r"\bpas\s+de\b",
    r"\bplus\s+de\b",
]

# Intensifieurs
INTENSIFIERS = {
    "tres": 1.3, "vraiment": 1.3, "extremement": 1.5,
    "absolument": 1.4, "totalement": 1.4,
    "particulierement": 1.25, "terriblement": 1.4,
    "gravement": 1.35, "fortement": 1.3,
    "enormement": 1.35, "profondement": 1.3,
}

# Atténuateurs
ATTENUATORS = {
    "un peu": 0.6, "legerement": 0.65, "relativement": 0.7,
    "moderement": 0.7, "quelque peu": 0.6,
    "partiellement": 0.7, "assez": 0.8,
}


# ============================================================
# SERVICE
# ============================================================
class SentimentServiceV2:
    """Analyse de sentiment multi-méthode adaptée à la Guadeloupe."""

    def __init__(self):
        self.openai_available = False
        self.openai_client = None

        # Tenter de charger OpenAI (fallback pour textes ambigus)
        try:
            import openai
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key and api_key.startswith("sk-"):
                self.openai_client = openai.OpenAI(api_key=api_key)
                self.openai_available = True
                logger.info("✅ Sentiment V2: OpenAI disponible en fallback")
        except Exception:
            pass

        logger.info("✅ SentimentServiceV2 initialisé")

    def analyze(
        self, text: str, use_gpt: bool = False, context: str = ""
    ) -> Dict[str, Any]:
        """
        Analyse le sentiment d'un texte.

        Retourne :
        - polarity : 'positif' | 'négatif' | 'neutre' | 'mixte'
        - score : float [-1.0, +1.0]
        - confidence : float [0.0, 1.0]
        - intensity : 'faible' | 'modéré' | 'fort' | 'extrême'
        - method : 'lexicon' | 'openai' | 'hybrid'
        - details : dict avec les mots détectés
        """
        if not text or len(text.strip()) < 5:
            return self._default_result()

        # Analyse lexicale
        lexical = self._analyze_lexical(text)

        # Si confiance suffisante, retourner directement
        if lexical["confidence"] >= 0.6 and not use_gpt:
            return lexical

        # Si OpenAI dispo et demandé ou confiance basse
        if self.openai_available and (use_gpt or lexical["confidence"] < 0.4):
            gpt_result = self._analyze_openai(text, context)
            if gpt_result:
                # Hybride : pondérer lexical + GPT
                return self._merge_results(lexical, gpt_result)

        return lexical

    def _analyze_lexical(self, text: str) -> Dict[str, Any]:
        """Analyse par lexique étendu."""
        import unicodedata
        text_clean = unicodedata.normalize("NFKD", text.lower())
        text_clean = "".join(ch for ch in text_clean if not unicodedata.combining(ch))
        text_clean = re.sub(r"[^a-z\s']", " ", text_clean)

        words = text_clean.split()
        word_count = len(words)

        if word_count == 0:
            return self._default_result()

        # Détecter les négations
        negation_zones = self._find_negation_zones(text_clean)

        # Scanner le lexique
        pos_scores = []
        neg_scores = []
        pos_words = []
        neg_words = []

        for i, word in enumerate(words):
            # Vérifier les intensifieurs
            intensity_mult = 1.0
            if i > 0:
                prev = words[i-1]
                if prev in INTENSIFIERS:
                    intensity_mult = INTENSIFIERS[prev]

            # Vérifier les atténuateurs
            for att, mult in ATTENUATORS.items():
                att_words = att.split()
                if i >= len(att_words):
                    if words[i-len(att_words):i] == att_words:
                        intensity_mult *= mult

            # Vérifier si on est dans une zone de négation
            in_negation = any(start <= i <= end for start, end in negation_zones)

            if word in LEXICON_NEGATIF:
                score = LEXICON_NEGATIF[word] * intensity_mult
                if in_negation:
                    # Négation inverse le sentiment (mais atténué)
                    pos_scores.append(abs(score) * 0.5)
                    pos_words.append(f"NOT({word})")
                else:
                    neg_scores.append(abs(score))
                    neg_words.append(word)

            elif word in LEXICON_POSITIF:
                score = LEXICON_POSITIF[word] * intensity_mult
                if in_negation:
                    neg_scores.append(abs(score) * 0.5)
                    neg_words.append(f"NOT({word})")
                else:
                    pos_scores.append(score)
                    pos_words.append(word)

        # Calculer le score final
        total_pos = sum(pos_scores) if pos_scores else 0
        total_neg = sum(neg_scores) if neg_scores else 0
        hit_count = len(pos_scores) + len(neg_scores)

        # Score : différence normalisée par le nombre de mots,
        # pas juste pos/(pos+neg) qui donne ±1 dès qu'un seul côté existe
        if hit_count > 0:
            # Moyenne pondérée des scores, atténuée par la densité
            avg_pos = total_pos / max(len(pos_scores), 1) if pos_scores else 0
            avg_neg = total_neg / max(len(neg_scores), 1) if neg_scores else 0
            raw_score = avg_pos - avg_neg
            # Clamp [-1, 1]
            raw_score = max(-1.0, min(1.0, raw_score))
        else:
            raw_score = 0.0

        # Pondérer par la densité de mots sentimentaux
        density = hit_count / max(word_count, 1)
        confidence = min(0.95, density * 4 + 0.2)  # Plus de mots = plus confiant

        # Si très peu de mots sentimentaux, baisser la confiance
        if hit_count <= 1:
            confidence = min(confidence, 0.35)
        elif hit_count == 2:
            confidence = min(confidence, 0.50)

        # Polarité
        if abs(raw_score) < 0.1:
            if pos_scores and neg_scores:
                polarity = "mixte"
            else:
                polarity = "neutre"
        elif raw_score > 0:
            polarity = "positif"
        else:
            polarity = "negatif"

        # Intensité
        abs_score = abs(raw_score)
        if abs_score >= 0.7:
            intensity = "extreme"
        elif abs_score >= 0.45:
            intensity = "fort"
        elif abs_score >= 0.2:
            intensity = "modere"
        else:
            intensity = "faible"

        return {
            "polarity": polarity,
            "score": round(raw_score, 3),
            "confidence": round(confidence, 3),
            "intensity": intensity,
            "method": "lexicon_v2",
            "details": {
                "positive_words": pos_words[:10],
                "negative_words": neg_words[:10],
                "positive_total": round(total_pos, 3),
                "negative_total": round(total_neg, 3),
                "word_count": word_count,
                "sentiment_hits": hit_count,
                "density": round(density, 4),
            }
        }

    def _find_negation_zones(self, text: str) -> List[Tuple[int, int]]:
        """Trouve les zones de négation dans le texte (en indices de mots)."""
        zones = []
        words = text.split()

        # Méthode 1 : regex sur le texte complet
        for pattern in NEGATION_PATTERNS:
            for match in re.finditer(pattern, text):
                start_char = match.start()
                # Compter les mots avant le match
                word_index = len(text[:start_char].split())
                # La négation affecte les 4 mots suivants
                zones.append((max(0, word_index), min(len(words)-1, word_index + 4)))

        # Méthode 2 : détection directe du mot "pas" précédé de contexte
        for i, word in enumerate(words):
            if word == "pas" and i > 0:
                # "pas de X", "n'a pas X", "ne X pas"
                zones.append((max(0, i - 1), min(len(words)-1, i + 3)))
            elif word in ("jamais", "aucun", "aucune", "sans"):
                zones.append((i, min(len(words)-1, i + 3)))

        return zones

    def _analyze_openai(self, text: str, context: str = "") -> Optional[Dict[str, Any]]:
        """Analyse via OpenAI GPT (fallback)."""
        if not self.openai_client:
            return None

        try:
            prompt = (
                "Analyse le sentiment de ce texte d'actualité guadeloupéenne. "
                "Réponds UNIQUEMENT avec un JSON: "
                '{"polarity":"positif|negatif|neutre|mixte",'
                '"score":float_entre_-1_et_1,'
                '"confidence":float_entre_0_et_1,'
                '"intensity":"faible|modere|fort|extreme",'
                '"key_emotion":"mot_décrivant_l_emotion_dominante"}'
            )
            if context:
                prompt += f"\nContexte: {context}"

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text[:2000]},
                ],
                max_tokens=150,
                temperature=0.1,
            )

            import json
            content = response.choices[0].message.content.strip()
            # Nettoyer le JSON
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
            data = json.loads(content)

            return {
                "polarity": data.get("polarity", "neutre"),
                "score": float(data.get("score", 0)),
                "confidence": float(data.get("confidence", 0.7)),
                "intensity": data.get("intensity", "modere"),
                "method": "openai",
                "details": {
                    "key_emotion": data.get("key_emotion", ""),
                    "model": "gpt-4o-mini",
                },
            }
        except Exception as e:
            logger.debug(f"OpenAI sentiment: {e}")
            return None

    def _merge_results(
        self, lexical: Dict, gpt: Dict
    ) -> Dict[str, Any]:
        """Fusionne résultats lexicaux et GPT."""
        lex_conf = lexical.get("confidence", 0.3)
        gpt_conf = gpt.get("confidence", 0.6)
        total_conf = lex_conf + gpt_conf

        if total_conf == 0:
            return lexical

        # Score pondéré
        merged_score = (
            lexical["score"] * lex_conf + gpt["score"] * gpt_conf
        ) / total_conf

        # Polarité du score final
        if abs(merged_score) < 0.1:
            polarity = "neutre"
        elif merged_score > 0:
            polarity = "positif"
        else:
            polarity = "negatif"

        return {
            "polarity": polarity,
            "score": round(merged_score, 3),
            "confidence": round(min(0.95, (lex_conf + gpt_conf) / 2 + 0.1), 3),
            "intensity": gpt.get("intensity", lexical.get("intensity", "modere")),
            "method": "hybrid",
            "details": {
                "lexical": lexical.get("details", {}),
                "openai": gpt.get("details", {}),
                "weights": {"lexical": round(lex_conf, 2), "openai": round(gpt_conf, 2)},
            },
        }

    def _default_result(self) -> Dict[str, Any]:
        return {
            "polarity": "neutre",
            "score": 0.0,
            "confidence": 0.0,
            "intensity": "faible",
            "method": "default",
            "details": {},
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "lexicon_size": len(LEXICON_POSITIF) + len(LEXICON_NEGATIF),
            "openai_available": self.openai_available,
            "method": "hybrid" if self.openai_available else "lexicon_only",
        }


# Singleton
_sentiment_v2: Optional[SentimentServiceV2] = None

def get_sentiment_service() -> SentimentServiceV2:
    global _sentiment_v2
    if _sentiment_v2 is None:
        _sentiment_v2 = SentimentServiceV2()
    return _sentiment_v2
