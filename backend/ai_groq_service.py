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
# Configuration — auto-détection Groq vs xAI + fallback OpenAI
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
_user_model = os.environ.get("GROQ_MODEL", "").strip()

# --- Provider primaire (xAI / Groq) ---
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

# --- Fallback OpenAI (GPT-4o-mini, ~1€/mois) ---
FALLBACK_PROVIDER = "openai"
FALLBACK_BASE_URL = "https://api.openai.com/v1"
FALLBACK_MODEL = "gpt-4o-mini"

# Compat
GROQ_MODEL = AI_MODEL

# ============================================================
# Clients IA (primaire + fallback)
# ============================================================

_client = None
_fallback_client = None


def _get_client():
    """Initialise le client IA primaire (lazy loading)."""
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
        logger.info(f"✅ Client IA primaire — provider: {AI_PROVIDER}, modèle: {AI_MODEL}")
        return _client
    except Exception as e:
        logger.error(f"❌ Impossible d'initialiser le client IA primaire: {e}")
        return None


def _get_fallback_client():
    """Initialise le client OpenAI fallback (lazy loading)."""
    global _fallback_client
    if _fallback_client is not None:
        return _fallback_client
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        _fallback_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=FALLBACK_BASE_URL,
        )
        logger.info(f"✅ Client IA fallback — {FALLBACK_PROVIDER}/{FALLBACK_MODEL}")
        return _fallback_client
    except Exception as e:
        logger.warning(f"⚠️ Fallback OpenAI non disponible: {e}")
        return None


def _call_ai(messages: List[Dict], temperature: float = 0.1,
             max_tokens: int = 800, json_mode: bool = True) -> Optional[str]:
    """
    Appel IA avec fallback automatique : xAI/Grok → OpenAI GPT-4o-mini.
    Retourne le contenu brut de la réponse ou None.
    """
    kwargs = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # 1. Essayer le provider primaire
    client = _get_client()
    if client:
        try:
            resp = client.chat.completions.create(model=GROQ_MODEL, **kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"⚠️ {AI_PROVIDER} échoué: {e} — fallback OpenAI")

    # 2. Fallback OpenAI
    fb = _get_fallback_client()
    if fb:
        try:
            resp = fb.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            content = resp.choices[0].message.content.strip()
            logger.info(f"✅ Fallback {FALLBACK_PROVIDER}/{FALLBACK_MODEL} OK")
            return content
        except Exception as e:
            logger.error(f"❌ Fallback OpenAI aussi échoué: {e}")

    return None


def is_available() -> bool:
    """Vérifie si au moins un service IA est disponible."""
    return bool(GROQ_API_KEY and _get_client()) or bool(OPENAI_API_KEY and _get_fallback_client())


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
    Enrichit un article via IA (xAI → fallback OpenAI → fallback tags_index).
    Retourne None si échec (pour permettre le fallback sur tags_index).
    """
    if not is_available():
        return None

    title = article.get("title", "")
    content = article.get("content", "") or article.get("text", "")

    if not title and not content:
        return None

    # Limiter le contenu pour rester dans les limites
    text_input = f"Titre: {title}\n\nContenu: {content[:3000]}"

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text_input},
            ],
            temperature=0.1,
            max_tokens=800,
            json_mode=True,
        )
        if raw is None:
            return None
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
    """Analyse de sentiment via IA (xAI → fallback OpenAI)."""
    if not text or len(text.strip()) < 20:
        return None

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": SENTIMENT_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
            temperature=0.1,
            max_tokens=300,
            json_mode=True,
        )
        if raw is None:
            return None
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
    """Résumé d'article via IA (xAI → fallback OpenAI)."""
    if not text or len(text.strip()) < 50:
        return None

    try:
        result = _call_ai(
            messages=[
                {"role": "system", "content": f"Résume ce texte d'actualité de Guadeloupe en {max_sentences} phrases maximum. Sois factuel et concis."},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0.2,
            max_tokens=300,
            json_mode=False,
        )
        return result

    except Exception as e:
        logger.warning(f"⚠️ Groq résumé échoué: {e}")
        return None


# ============================================================
# Clustering IA — regrouper des articles par événement
# ============================================================

CLUSTERING_PROMPT = """Tu es un analyste média spécialisé Guadeloupe/Antilles.

Voici une liste d'articles récents numérotés. Regroupe-les par ÉVÉNEMENT RÉEL :
- Deux articles parlent du MÊME événement s'ils couvrent le même fait concret
  (même accident, même décision politique, même grève, même incident).
- Deux articles sur des accidents DIFFÉRENTS ne font PAS partie du même groupe,
  même s'ils parlent tous les deux d'"accident".
- Un article culturel et un article politique ne vont JAMAIS ensemble.

Réponds UNIQUEMENT en JSON :
{
  "groups": [
    {
      "label": "description courte de l'événement (max 10 mots)",
      "articles": [1, 4, 7],
      "gravity": 0.0 à 1.0
    }
  ],
  "isolates": [2, 5]
}

"isolates" = articles qui ne correspondent à aucun groupe (événement unique).
Ne crée un groupe QUE si au moins 2 articles parlent du même événement."""


def cluster_articles_with_ai(
    articles: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Envoie un batch d'articles à l'IA pour regroupement sémantique.
    Utilise xAI en priorité, fallback OpenAI GPT-4o-mini.
    Retourne {"groups": [...], "isolates": [...]} ou None si échec.
    """
    if not is_available():
        return None

    if not articles or len(articles) < 2:
        return None

    # Construire la liste numérotée
    lines = []
    for i, art in enumerate(articles, 1):
        title = art.get("title", "Sans titre")[:120]
        summary = art.get("ai_summary") or art.get("summary") or ""
        date = art.get("date") or art.get("scraped_at") or ""
        if isinstance(date, str):
            date = date[:10]  # Juste YYYY-MM-DD
        else:
            try:
                date = date.strftime("%Y-%m-%d")
            except Exception:
                date = ""

        line = f"{i}. [{date}] {title}"
        if summary:
            line += f" — {summary[:150]}"
        lines.append(line)

    user_content = "\n".join(lines)

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": CLUSTERING_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.05,
            max_tokens=1500,
            json_mode=True,
        )
        if raw is None:
            return None
        result = json.loads(raw)

        groups = result.get("groups", [])
        isolates = result.get("isolates", [])

        # Valider les indices
        valid_range = set(range(1, len(articles) + 1))
        for group in groups:
            group["articles"] = [a for a in group.get("articles", []) if a in valid_range]
        isolates = [a for a in isolates if a in valid_range]

        # Filtrer les groupes vides ou avec 1 seul article
        groups = [g for g in groups if len(g.get("articles", [])) >= 2]

        logger.info(
            f"🤖 Clustering IA: {len(articles)} articles → "
            f"{len(groups)} groupes, {len(isolates)} isolés"
        )
        return {"groups": groups, "isolates": isolates}

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Clustering IA: JSON invalide: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Clustering IA échoué: {e}")
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
