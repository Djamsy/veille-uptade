# backend/ai_groq_service.py
"""
Service d'enrichissement IA — supporte Groq ET xAI (Grok)
- Détection automatique du provider selon le format de la clé API
  • clé gsk_* → Groq (api.groq.com)  — modèle mixtral-8x7b-32768
  • clé xai-* → xAI  (api.x.ai)      — modèle grok-2-1212
  • autre     → Groq par défaut
- API OpenAI-compatible dans les deux cas
- Fallback sur tags_index si aucune IA disponible
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ai_groq_service")

# ============================================================
# Configuration — auto-détection Groq vs xAI
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
_user_model = os.environ.get("GROQ_MODEL", "").strip()

if GROQ_API_KEY.startswith("xai-"):
    AI_PROVIDER = "xai"
    AI_BASE_URL = "https://api.x.ai/v1"
    AI_MODEL = _user_model if _user_model and _user_model != "mixtral-8x7b-32768" else "grok-2-1212"
elif GROQ_API_KEY.startswith("gsk_"):
    AI_PROVIDER = "groq"
    AI_BASE_URL = "https://api.groq.com/openai/v1"
    AI_MODEL = _user_model or "mixtral-8x7b-32768"
else:
    AI_PROVIDER = "groq"
    AI_BASE_URL = "https://api.groq.com/openai/v1"
    AI_MODEL = _user_model or "mixtral-8x7b-32768"

# Compat
GROQ_MODEL = AI_MODEL

# ============================================================
# Client IA (via SDK OpenAI — compatible Groq & xAI)
# ============================================================

_client = None


def _get_client():
    """Initialise le client IA (lazy loading)."""
    global _client
    if _client is not None:
        return _client
    if not GROQ_API_KEY:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url=AI_BASE_URL,
        )
        logger.info(f"✅ Client IA initialisé — provider: {AI_PROVIDER}, modèle: {AI_MODEL}, url: {AI_BASE_URL}")
        return _client
    except Exception as e:
        logger.error(f"❌ Impossible d'initialiser le client IA: {e}")
        return None


def is_available() -> bool:
    """Vérifie si le service IA est disponible."""
    return bool(GROQ_API_KEY) and _get_client() is not None


# ============================================================
# Prompt système pour l'analyse médiatique Guadeloupe
# ============================================================

SYSTEM_PROMPT = """Tu es un analyste média spécialisé dans l'actualité de la Guadeloupe et des Antilles françaises.

Analyse l'article fourni et retourne un JSON avec EXACTEMENT ces champs :

{
  "theme": "un parmi: eau_env, energie_transports, sante_social, education, economie_emploi, culture_patrimoine, securite_justice, politique, sport, general",
  "elected": ["liste des personnalités politiques/publiques mentionnées (nom complet)"],
  "institutions": ["liste des institutions mentionnées (CHU, SMGEAG, EDF, Préfecture, etc.)"],
  "sentiment": "positif, negatif ou neutre",
  "gravity_score": 0.0 à 1.0 (0=anodin, 0.5=notable, 0.7+=affaire grave, 0.9+=crise),
  "is_affair": true/false (true si gravity_score >= 0.65),
  "affair_type": "routine, incident_mineur, affaire_importante, affaire_grave ou crise_majeure",
  "summary": "résumé en 1-2 phrases de l'article",
  "keywords": ["mots-clés principaux de l'article"]
}

Règles :
- Sois précis sur les noms : utilise le prénom ET le nom pour les personnalités
- Les institutions locales de Guadeloupe sont importantes : CHU, SMGEAG, EDF Guadeloupe, ARS, Préfecture, Région, Département, CAF
- Un décès, une agression, une grève majeure = gravity >= 0.7
- Une simple annonce culturelle ou sportive = gravity < 0.3
- Réponds UNIQUEMENT en JSON valide, pas de texte autour."""


# ============================================================
# Fonction d'enrichissement par IA
# ============================================================

def enrich_article_with_groq(article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Enrichit un article via Groq API.
    Retourne None si échec (pour permettre le fallback sur tags_index).
    """
    client = _get_client()
    if client is None:
        return None

    title = article.get("title", "")
    content = article.get("content", "") or article.get("text", "")

    if not title and not content:
        return None

    # Limiter le contenu pour rester dans les limites
    text_input = f"Titre: {title}\n\nContenu: {content[:3000]}"

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text_input},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        # Normaliser et valider les champs
        theme = result.get("theme", "general")
        elected = result.get("elected", [])
        institutions = result.get("institutions", [])
        sentiment = result.get("sentiment", "neutre")
        gravity_score = float(result.get("gravity_score", 0.3))
        is_affair = result.get("is_affair", gravity_score >= 0.65)
        affair_type = result.get("affair_type", "routine")
        summary = result.get("summary", "")
        keywords = result.get("keywords", [])

        # S'assurer que les listes sont bien des listes
        if isinstance(elected, str):
            elected = [elected] if elected else []
        if isinstance(institutions, str):
            institutions = [institutions] if institutions else []
        if isinstance(keywords, str):
            keywords = [keywords] if keywords else []

        # Construire entities combinées
        all_entities = list(set(elected + institutions))

        # Mise à jour de l'article (même format que tags_index)
        article.update({
            "theme": theme,
            "elected": elected,
            "institutions": institutions,
            "entities": all_entities,
            "sentiment": sentiment,
            "is_affair": is_affair,
            "affair_type": affair_type,
            "gravity_score": round(min(1.0, max(0.0, gravity_score)), 3),
            "importance_score": round(min(1.0, gravity_score + (0.15 if elected else 0) + (0.10 if institutions else 0)), 3),
            "keywords_found": keywords,
            "ai_summary": summary,
            "classification_confidence": 0.95,
            "_analysis_method": f"{AI_PROVIDER}_{AI_MODEL}",
            "_personalities_detected": len(elected),
            "_institutions_detected": len(institutions),
        })

        return article

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Groq: réponse JSON invalide: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Groq enrichissement échoué: {e}")
        return None


# ============================================================
# Analyse de sentiment seule (pour le service sentiment)
# ============================================================

SENTIMENT_PROMPT = """Analyse le sentiment de ce texte d'actualité de Guadeloupe.
Réponds UNIQUEMENT en JSON :
{
  "sentiment": "positif, negatif ou neutre",
  "score": -1.0 à 1.0 (-1=très négatif, 0=neutre, 1=très positif),
  "confidence": 0.0 à 1.0,
  "aspects": [{"aspect": "sujet", "sentiment": "positif/negatif/neutre"}]
}"""


def analyze_sentiment_groq(text: str) -> Optional[Dict[str, Any]]:
    """Analyse de sentiment via Groq."""
    client = _get_client()
    if client is None:
        return None

    if not text or len(text.strip()) < 20:
        return None

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SENTIMENT_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        return {
            "sentiment": result.get("sentiment", "neutre"),
            "score": float(result.get("score", 0.0)),
            "confidence": float(result.get("confidence", 0.8)),
            "aspects": result.get("aspects", []),
            "method": f"{AI_PROVIDER}_{AI_MODEL}",
        }

    except Exception as e:
        logger.warning(f"⚠️ Groq sentiment échoué: {e}")
        return None


# ============================================================
# Résumé d'article
# ============================================================

def summarize_groq(text: str, max_sentences: int = 3) -> Optional[str]:
    """Résumé d'article via Groq."""
    client = _get_client()
    if client is None:
        return None

    if not text or len(text.strip()) < 50:
        return None

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": f"Résume ce texte d'actualité de Guadeloupe en {max_sentences} phrases maximum. Sois factuel et concis."},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0.2,
            max_tokens=300,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"⚠️ Groq résumé échoué: {e}")
        return None


# ============================================================
# Fonction combinée (Groq + fallback tags_index)
# ============================================================

def smart_enrich_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrichissement intelligent :
    1. Essaie Groq d'abord (meilleure qualité)
    2. Fallback sur tags_index (règles locales)
    3. Fusionne les résultats si les deux sont disponibles
    """
    groq_result = enrich_article_with_groq(article)

    if groq_result is not None:
        # Groq a fonctionné — on complète avec les règles locales
        # (pour attraper des entités spécifiques que l'IA aurait pu manquer)
        try:
            from backend.tags_index import detect_entities, detect_theme

            title = article.get("title", "")
            content = article.get("content", "") or article.get("text", "")
            full_text = f"{title} {content}"

            # Entités supplémentaires détectées par regex
            rule_personalities, rule_institutions = detect_entities(full_text)

            # Fusionner (union des deux sources)
            existing_elected = set(groq_result.get("elected", []))
            existing_institutions = set(groq_result.get("institutions", []))

            for p in rule_personalities:
                existing_elected.add(p)
            for i in rule_institutions:
                existing_institutions.add(i)

            groq_result["elected"] = sorted(existing_elected)
            groq_result["institutions"] = sorted(existing_institutions)
            groq_result["entities"] = sorted(existing_elected | existing_institutions)
            groq_result["_analysis_method"] = f"groq_{GROQ_MODEL}+rules"

        except Exception:
            pass  # Si tags_index n'est pas dispo, on garde juste Groq

        return groq_result

    # Fallback complet sur tags_index
    try:
        from backend.tags_index import infer_tags_and_theme
        return infer_tags_and_theme(article)
    except Exception:
        try:
            from tags_index import infer_tags_and_theme
            return infer_tags_and_theme(article)
        except Exception as e:
            logger.error(f"❌ Aucun enrichissement disponible: {e}")
            return article
