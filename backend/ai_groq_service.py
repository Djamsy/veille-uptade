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
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ai_groq_service")

# ============================================================
# Configuration — OpenAI GPT-4o-mini uniquement
# ============================================================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

AI_PROVIDER = "openai"
AI_BASE_URL = "https://api.openai.com/v1"
AI_MODEL = "gpt-4o-mini"

# Compat (ancien code peut référencer GROQ_MODEL)
GROQ_MODEL = AI_MODEL

# ============================================================
# Client IA (OpenAI uniquement)
# ============================================================

_client = None


def _get_client():
    """Initialise le client OpenAI GPT-4o-mini (lazy loading)."""
    global _client
    if _client is not None:
        return _client
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=AI_BASE_URL,
        )
        logger.info(f"✅ Client IA — {AI_PROVIDER}/{AI_MODEL}")
        return _client
    except Exception as e:
        logger.error(f"❌ Impossible d'initialiser OpenAI: {e}")
        return None


def _call_ai(messages: List[Dict], temperature: float = 0.1,
             max_tokens: int = 800, json_mode: bool = True) -> Optional[str]:
    """
    Appel OpenAI GPT-4o-mini avec retry et exponential backoff.
    Retourne le contenu brut ou None.

    Retry logic:
    - Max 3 tentatives
    - Backoff: 1s, 2s, 4s
    - Retry only on rate limit (429) and server errors (500+)
    """
    kwargs = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    client = _get_client()
    if not client:
        logger.warning("⚠️ Client OpenAI non disponible (OPENAI_API_KEY manquant ?)")
        return None

    max_retries = 3
    backoff_times = [1, 2, 4]  # exponential backoff: 1s, 2s, 4s

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(model=AI_MODEL, **kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            # Check if it's a rate limit (429) or server error (500+)
            is_retryable = False
            error_str = str(e)

            # Try to detect rate limit errors
            if "429" in error_str or "rate" in error_str.lower():
                is_retryable = True
            # Try to detect server errors (500+)
            elif any(code in error_str for code in ["500", "501", "502", "503", "504"]):
                is_retryable = True

            # If not retryable or last attempt, fail now
            if not is_retryable or attempt >= max_retries - 1:
                logger.error(f"❌ {AI_PROVIDER}/{AI_MODEL} échoué: {e}")
                return None

            # Sleep before retry
            sleep_time = backoff_times[attempt]
            logger.warning(
                f"⚠️ {AI_PROVIDER}/{AI_MODEL} tentative {attempt + 1}/{max_retries} échouée "
                f"(retryable error). Attente {sleep_time}s avant retry..."
            )
            time.sleep(sleep_time)


def is_available() -> bool:
    """Vérifie si OpenAI est disponible."""
    return bool(OPENAI_API_KEY and _get_client())


def _normalize_entity_name(name: str) -> str:
    """
    Normalise un nom d'entité:
    - Strip leading/trailing whitespace and quotes
    - Capitalize first letter of each word (title case)
    - Remove prefixes: M., Mme, Monsieur, Madame
    """
    if not isinstance(name, str):
        return ""

    # Strip whitespace and quotes
    name = name.strip().strip("'\"")

    if not name:
        return ""

    # Remove prefixes (case-insensitive)
    prefixes = ["M.", "Mme", "Monsieur", "Madame", "Dr.", "Pr.", "Prof."]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
            break

    # Title case: capitalize first letter of each word
    name = " ".join(word.capitalize() for word in name.split())

    return name


def _clean_entity_list(entities: list) -> list:
    """
    Cleans and normalizes a list of entities:
    - Filter out None, empty strings, strings < 2 chars
    - Normalize each name
    - Remove duplicates (case-insensitive)
    - Return sorted list
    """
    if not isinstance(entities, list):
        return []

    cleaned = []
    seen = set()

    for ent in entities:
        if ent is None or not isinstance(ent, str):
            continue

        ent = ent.strip()
        if len(ent) < 2:  # Skip strings shorter than 2 chars
            continue

        normalized = _normalize_entity_name(ent)
        if not normalized:
            continue

        # Case-insensitive dedup
        normalized_lower = normalized.lower()
        if normalized_lower not in seen:
            cleaned.append(normalized)
            seen.add(normalized_lower)

    return sorted(cleaned)


# ============================================================
# Validation — Valid values
# ============================================================

VALID_THEMES = {"eau_env", "energie_transports", "sante_social", "education",
                "economie_emploi", "culture_patrimoine", "securite_justice", "politique",
                "sport", "general"}
VALID_SENTIMENTS = {"positif", "négatif", "negatif", "neutre", "mixte"}
VALID_EVENT_TYPES = {"declaration", "decision", "incident", "mobilisation", "bilan",
                     "nomination", "judiciaire", "catastrophe", "routine"}
VALID_AFFAIR_TYPES = {"routine", "incident_mineur", "affaire_importante",
                      "affaire_grave", "crise_majeure"}


# ============================================================
# Prompt système pour l'analyse médiatique Guadeloupe
# ============================================================

SYSTEM_PROMPT = """Tu es un analyste média spécialisé dans l'actualité de la Guadeloupe et des Antilles françaises.

Analyse l'article fourni et retourne un JSON avec EXACTEMENT ces champs :

{
  "theme": "un parmi: eau_env, energie_transports, sante_social, education, economie_emploi, culture_patrimoine, securite_justice, politique, sport, general",
  "elected": ["liste des personnalités politiques/publiques mentionnées (nom complet)"],
  "institutions": ["liste des institutions mentionnées (CHU, SMGEAG, EDF, Préfecture, etc.)"],
  "event": {
    "subject": "qui fait l'action (personne, institution, groupe)",
    "action": "verbe/action principale (annonce, dénonce, grève, inaugure, arrête...)",
    "object": "sur quoi/qui porte l'action (plan eau, budget, suspect...)",
    "event_type": "un parmi: declaration, decision, incident, mobilisation, bilan, nomination, judiciaire, catastrophe, routine",
    "location": "lieu précis si mentionné (commune, quartier) ou vide"
  },
  "sentiment": "positif, negatif ou neutre",
  "gravity_score": 0.0 à 1.0,
  "is_affair": true/false,
  "affair_type": "routine, incident_mineur, affaire_importante, affaire_grave ou crise_majeure",
  "summary": "résumé en 1-2 phrases de l'article",
  "keywords": ["mots-clés principaux de l'article"]
}

=== CALIBRATION GRAVITY_SCORE (TRÈS IMPORTANT — sois STRICT) ===

La MAJORITÉ des articles doivent avoir une gravity basse. Distribution attendue :
- 60% des articles → gravity 0.05 à 0.25 (routine, info générale)
- 25% des articles → gravity 0.25 à 0.50 (événement notable mais pas grave)
- 10% des articles → gravity 0.50 à 0.70 (affaire significative)
- 4% des articles → gravity 0.70 à 0.85 (affaire grave, crise locale)
- 1% des articles → gravity 0.85+ (crise majeure exceptionnelle)

Exemples concrets pour la Guadeloupe :
- gravity 0.05-0.15 : météo, résultats sportifs locaux, programme culturel, événement associatif, ouverture de commerce, agenda
- gravity 0.15-0.25 : travaux routiers, coupure d'eau programmée, annonce institutionnelle, bilan d'activité, inauguration
- gravity 0.25-0.40 : grève limitée (1 entreprise), accident de la route, interpellation de délinquants, fermeture d'entreprise
- gravity 0.40-0.55 : grève touchant un service public, pénurie temporaire, polémique politique locale, incendie important
- gravity 0.55-0.70 : scandale financier public, grève générale d'un secteur, contamination eau potable, mort suspecte
- gravity 0.70-0.85 : meurtre, corruption d'élu avérée, cyclone imminent, crise sanitaire, émeute
- gravity 0.85-1.0 : catastrophe naturelle majeure, crise sociale généralisée (blocages île entière), multiple victimes

RÈGLE CLEF : si l'article est informatif, factuel et sans conséquence directe sur la population → gravity <= 0.20.
Un article n'est PAS une "affaire" s'il rapporte simplement un fait divers ou un événement ordinaire.

is_affair : true UNIQUEMENT si gravity_score >= 0.55 ET l'article implique des personnalités publiques ou des institutions dans un contexte problématique.

EXTRACTION D'ÉVÉNEMENT (champ "event") :
- subject : qui est l'acteur principal ? (nom complet de la personne ou institution)
- action : quel est le verbe/action ? (annonce, dénonce, lance une grève, inaugure, est arrêté, conteste, etc.)
- object : sur quoi porte l'action ? (plan de rénovation, budget 2025, un suspect, etc.)
- event_type : catégorise l'événement (declaration, decision, incident, mobilisation, bilan, nomination, judiciaire, catastrophe, routine)
- location : lieu précis si mentionné (Pointe-à-Pitre, Baie-Mahault, Les Abymes, etc.)
- Ceci permet de distinguer "Losbar annonce un plan" de "Losbar critiqué pour un plan" : même personne, événements différents.

Autres règles :
- Sois précis sur les noms : utilise le prénom ET le nom pour les personnalités
- Les institutions locales de Guadeloupe sont importantes : CHU, SMGEAG, EDF Guadeloupe, ARS, Préfecture, Région, Département, CAF
- Réponds UNIQUEMENT en JSON valide, pas de texte autour."""


# ============================================================
# Fonction d'enrichissement par IA
# ============================================================

def enrich_article_with_groq(article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Enrichit un article via IA avec validation stricte.
    Retourne None si échec (pour permettre le fallback sur tags_index).

    Validation stricte:
    - gravity_score: float [0.0-1.0], clamped if outside
    - theme: one of VALID_THEMES, defaults to "general"
    - sentiment: one of VALID_SENTIMENTS, defaults to "neutre"
    - elected/institutions: cleaned lists, no empty strings, no None, no short strings
    - event_type: one of VALID_EVENT_TYPES, defaults to "routine"
    - affair_type: one of VALID_AFFAIR_TYPES, defaults based on gravity
    - summary: non-empty string, max 500 chars
    Entity normalization applied after validation.
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

        # === STRICT VALIDATION ===

        # 1. gravity_score: float [0.0-1.0]
        try:
            gravity_score = float(result.get("gravity_score", 0.15))
        except (ValueError, TypeError):
            gravity_score = 0.15
            logger.warning("⚠️ gravity_score invalid, defaulting to 0.15")

        original_gravity = gravity_score
        if gravity_score < 0.0 or gravity_score > 1.0:
            gravity_score = max(0.0, min(1.0, gravity_score))
            logger.warning(f"⚠️ gravity_score {original_gravity} clamped to {gravity_score}")

        # 2. theme: validate against VALID_THEMES
        theme = result.get("theme", "general")
        if theme not in VALID_THEMES:
            logger.warning(f"⚠️ theme '{theme}' invalid, defaulting to 'general'")
            theme = "general"

        # 3. sentiment: validate against VALID_SENTIMENTS
        sentiment = result.get("sentiment", "neutre")
        if sentiment not in VALID_SENTIMENTS:
            logger.warning(f"⚠️ sentiment '{sentiment}' invalid, defaulting to 'neutre'")
            sentiment = "neutre"

        # 4. elected & institutions: clean lists
        elected_raw = result.get("elected", [])
        institutions_raw = result.get("institutions", [])

        if isinstance(elected_raw, str):
            elected_raw = [elected_raw] if elected_raw else []
        if isinstance(institutions_raw, str):
            institutions_raw = [institutions_raw] if institutions_raw else []

        # Clean and normalize
        elected = _clean_entity_list(elected_raw)
        institutions = _clean_entity_list(institutions_raw)

        # 5. event_type: validate within event object
        event_raw = result.get("event", {})
        event_type = event_raw.get("event_type", "routine") if event_raw else "routine"
        if event_type not in VALID_EVENT_TYPES:
            logger.warning(f"⚠️ event_type '{event_type}' invalid, defaulting to 'routine'")
            event_type = "routine"

        event_structured = {
            "subject": str(event_raw.get("subject", "")).strip() if event_raw else "",
            "action": str(event_raw.get("action", "")).strip() if event_raw else "",
            "object": str(event_raw.get("object", "")).strip() if event_raw else "",
            "event_type": event_type,
            "location": str(event_raw.get("location", "")).strip() if event_raw else "",
        } if event_raw else {}

        # 6. affair_type: validate against VALID_AFFAIR_TYPES
        affair_type = result.get("affair_type", "routine")
        if affair_type not in VALID_AFFAIR_TYPES:
            # Default based on gravity
            if gravity_score >= 0.7:
                affair_type = "affaire_grave"
            elif gravity_score >= 0.55:
                affair_type = "affaire_importante"
            elif gravity_score >= 0.3:
                affair_type = "incident_mineur"
            else:
                affair_type = "routine"
            logger.warning(f"⚠️ affair_type invalid, defaulted to '{affair_type}' based on gravity")

        # 7. is_affair: computed from gravity
        is_affair = gravity_score >= 0.55

        # 8. summary: non-empty string, max 500 chars
        summary = result.get("summary", "")
        if not isinstance(summary, str):
            summary = ""
        summary = summary.strip()
        if len(summary) > 500:
            summary = summary[:500].strip()
            logger.warning("⚠️ summary truncated to 500 chars")
        if not summary:
            logger.warning("⚠️ summary empty, using default")
            summary = f"Article analysé - {theme}"

        # 9. keywords: clean list
        keywords_raw = result.get("keywords", [])
        if isinstance(keywords_raw, str):
            keywords_raw = [keywords_raw] if keywords_raw else []
        keywords = [k for k in keywords_raw if isinstance(k, str) and k.strip()]

        # Construire entities combinées
        all_entities = list(set(elected + institutions))

        # Résoudre les alias d'entités
        try:
            from backend.entity_aliases import resolve_entities
            elected = resolve_entities(elected)
            institutions = resolve_entities(institutions)
            all_entities = list(set(elected + institutions))
        except ImportError:
            pass

        # Mise à jour de l'article (même format que tags_index)
        article.update({
            "theme": theme,
            "elected": elected,
            "institutions": institutions,
            "entities": all_entities,
            "event_structured": event_structured,
            "sentiment": sentiment,
            "is_affair": is_affair,
            "affair_type": affair_type,
            "gravity_score": round(gravity_score, 3),
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


AFFAIRS_MANAGEMENT_PROMPT = """Tu es le gestionnaire d'affaires média pour la Guadeloupe/Antilles.

Tu reçois :
1. La liste des AFFAIRES ACTIVES (max 20) avec leur ID, titre, score de gravité
2. La liste des NOUVEAUX CONTENUS (articles presse + sujets radio) non encore assignés
3. (Optionnel) Les affaires de la semaine passée pour continuité

Ta mission :
- ASSIGNER un contenu à une affaire existante s'il parle du MÊME événement ou sujet
- CRÉER une nouvelle affaire pour tout contenu notable qui ne correspond à rien
- METTRE À JOUR le score de gravité
- N'IGNORER que les contenus vraiment anodins (météo banale, programme TV, résultats sportifs mineurs)

RÈGLES D'ASSIGNATION :
- Pour assigner à une affaire existante, le contenu doit parler du même sujet concret
- Le thème seul ne suffit PAS : "campagne sucrière" et "carnaval" = PAS la même affaire
- Deux faits différents dans le même domaine = AFFAIRES SÉPARÉES
- En cas de doute → CRÉER une nouvelle affaire (mieux vaut trop d'affaires que trop d'ignorés)

RÈGLES DE GRAVITÉ :
- 0.1-0.2 = anodin (météo banale, programme TV, petites annonces)
- 0.3-0.4 = suivi (événement culturel, annonce routine, info service)
- 0.5-0.6 = notable (décision politique, événement économique, mobilisation citoyenne)
- 0.7-0.8 = grave (décès, agression, grève, crise eau/énergie, catastrophe naturelle)
- 0.9-1.0 = crise majeure (émeute, scandale politique majeur, épidémie)

CONTEXTE GUADELOUPE — sujets récurrents et IMPORTANTS (ne pas ignorer) :
- Eau potable / coupures d'eau / SMGEAG = toujours >= 0.5
- Sargasses / chlordécone / pollution = toujours >= 0.5
- Grèves / blocages / mouvements sociaux = toujours >= 0.6
- Vie chère / pouvoir d'achat = toujours >= 0.5
- Campagne sucrière / agriculture = toujours >= 0.3 (créer une affaire)
- Insécurité / fusillades / trafic = toujours >= 0.6
- Carnaval / patrimoine / fêtes = créer si récurrence, >= 0.3

IMPORTANT : Préfère CRÉER ou ASSIGNER plutôt qu'IGNORER. Un article ignoré est perdu.
N'ignore que les contenus sans aucune valeur informative.

Réponds UNIQUEMENT en JSON :
{
  "assignments": [
    {"article_index": 1, "affair_id": "abc123", "reason": "même sujet: [explication]"},
    {"article_index": 3, "affair_id": null, "new_affair_title": "Titre court", "gravity": 0.5, "reason": "nouveau: [explication]"}
  ],
  "gravity_updates": [
    {"affair_id": "abc123", "new_gravity": 0.7, "reason": "confirmé par 2e source"}
  ],
  "ignored_articles": [5],
  "expired_affairs": ["def456"]
}

Notes :
- "article_index" est 1-based
- "affair_id": null = créer une nouvelle affaire
- "expired_affairs" : IDs d'affaires > 7 jours sans activité
- [RADIO] = sujets extraits de journaux radio (traiter comme articles normaux)"""


def manage_affairs_with_ai(
    active_affairs: List[Dict[str, Any]],
    new_articles: List[Dict[str, Any]],
    last_week_affairs: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Gestion IA des affaires : reçoit la liste des affaires actives + nouveaux articles,
    retourne les assignations, nouvelles affaires et mises à jour de gravité.
    """
    if not is_available():
        return None

    if not new_articles:
        return None

    # --- Construire le contexte ---
    parts = []

    # 1. Affaires actives
    if active_affairs:
        parts.append("=== AFFAIRES ACTIVES ===")
        for aff in active_affairs:
            aff_id = aff.get("_id", aff.get("id", "?"))
            title = aff.get("title", "Sans titre")[:100]
            gravity = aff.get("gravity_score", 0)
            items = aff.get("item_count", 0)
            last_act = aff.get("last_activity", "")
            if hasattr(last_act, "strftime"):
                last_act = last_act.strftime("%Y-%m-%d")
            elif isinstance(last_act, str):
                last_act = last_act[:10]
            parts.append(
                f"[{aff_id}] (gravity={gravity:.1f}, {items} items, dernier={last_act}) {title}"
            )
    else:
        parts.append("=== AUCUNE AFFAIRE ACTIVE ===")

    # 2. Contexte semaine passée (si dispo)
    if last_week_affairs:
        parts.append("\n=== CONTEXTE SEMAINE PASSÉE (pour continuité) ===")
        for aff in last_week_affairs[:10]:
            title = aff.get("title", "Sans titre")[:80]
            gravity = aff.get("gravity_score", 0)
            parts.append(f"- (gravity={gravity:.1f}) {title}")

    # 3. Nouveaux contenus (articles + sujets radio)
    parts.append("\n=== NOUVEAUX CONTENUS ===")
    for i, art in enumerate(new_articles, 1):
        title = art.get("title", "Sans titre")[:120]
        summary = art.get("ai_summary") or art.get("summary") or ""
        source = art.get("source") or art.get("source_name") or ""
        theme = art.get("theme", "")
        date = art.get("date") or art.get("scraped_at") or ""
        if isinstance(date, str):
            date = date[:10]
        elif hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")

        # Marquer les sujets radio distinctement
        is_radio = art.get("_is_radio_topic", False) or art.get("source_type") == "transcription"
        tag = "[RADIO]" if is_radio else "[PRESSE]"

        line = f"{i}. {tag} [{date}] [{source}] {title}"
        if theme:
            line += f" (thème: {theme})"
        if summary:
            line += f" — {summary[:150]}"
        parts.append(line)

    user_content = "\n".join(parts)

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": AFFAIRS_MANAGEMENT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.05,
            max_tokens=2000,
            json_mode=True,
        )
        if raw is None:
            return None

        result = json.loads(raw)

        # Valider la structure
        assignments = result.get("assignments", [])
        gravity_updates = result.get("gravity_updates", [])
        ignored = result.get("ignored_articles", [])
        expired = result.get("expired_affairs", [])

        # Valider les indices d'articles (list comprehension, pas remove pendant itération)
        valid_range = set(range(1, len(new_articles) + 1))
        assignments = [a for a in assignments if a.get("article_index") in valid_range]

        logger.info(
            f"🤖 Gestion IA affaires: {len(new_articles)} articles → "
            f"{len(assignments)} assignés, {len(ignored)} ignorés, "
            f"{len(gravity_updates)} MAJ gravité, {len(expired)} expirées"
        )

        return {
            "assignments": assignments,
            "gravity_updates": gravity_updates,
            "ignored_articles": ignored,
            "expired_affairs": expired,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Gestion IA affaires: JSON invalide: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Gestion IA affaires échoué: {e}")
        return None


RADIO_SPLIT_PROMPT = """Tu es un analyste média spécialisé Guadeloupe/Antilles.

On te donne une transcription radio (journal d'infos, flash, émission).
Une transcription contient PLUSIEURS sujets/nouvelles différents.

Découpe cette transcription en sujets distincts. Pour chaque sujet :
- Donne un titre court (max 15 mots)
- Résume le contenu en 1-2 phrases
- Estime la gravité (0.0 à 1.0)
- Liste les entités (personnalités, institutions) mentionnées
- Donne le thème (eau_env, energie_transports, sante_social, education, economie_emploi, culture_patrimoine, securite_justice, politique, sport, general)

Réponds UNIQUEMENT en JSON :
{
  "topics": [
    {
      "title": "Titre court du sujet",
      "summary": "Résumé en 1-2 phrases",
      "gravity": 0.7,
      "entities": ["Nom Prénom", "Institution"],
      "theme": "securite_justice",
      "event": {
        "subject": "qui fait l'action",
        "action": "verbe/action principale",
        "object": "sur quoi porte l'action",
        "event_type": "declaration/decision/incident/mobilisation/bilan/nomination/judiciaire/catastrophe/routine",
        "location": "lieu si mentionné"
      },
      "text_excerpt": "passage clé de la transcription (50 mots max)"
    }
  ]
}

Règles :
- Ignore les pubs, jingles, présentations de l'émission
- Un sujet = un événement/fait concret
- Un décès, accident grave, grève = gravity >= 0.7
- Météo banale, résultats sportifs mineurs = gravity < 0.3
- Minimum 1 sujet, pas de limite haute"""


def _segment_transcription(text: str, segment_seconds: int = 45, words_per_second: float = 2.5) -> List[str]:
    """
    Segmente une transcription en blocs de ~30-60 secondes.
    Estime ~2.5 mots/seconde pour la parole radio française.
    Retourne des segments de texte numérotés.
    """
    words = text.split()
    words_per_segment = int(segment_seconds * words_per_second)  # ~112 mots par segment

    if len(words) <= words_per_segment * 1.5:
        # Transcription courte, pas besoin de segmenter
        return [text]

    segments = []
    for i in range(0, len(words), words_per_segment):
        segment = " ".join(words[i:i + words_per_segment])
        if len(segment) > 30:  # Ignorer les segments trop courts
            segments.append(segment)

    return segments


def split_radio_transcription(
    transcription_text: str,
    radio_name: str = "",
    max_chars: int = 4000,
) -> Optional[List[Dict[str, Any]]]:
    """
    Découpe une transcription radio en sujets individuels via IA.
    Segmente d'abord en blocs de ~45s pour aider l'IA à identifier
    les changements de sujet, puis envoie à l'IA pour extraction.
    Retourne une liste de topics ou None si échec.
    """
    if not is_available():
        return None

    if not transcription_text or len(transcription_text.strip()) < 50:
        return None

    # Segmenter en blocs pour aider l'IA
    segments = _segment_transcription(transcription_text)

    header = f"Radio: {radio_name}\n" if radio_name else ""
    if len(segments) > 1:
        # Envoyer les segments numérotés pour aider l'IA à repérer les transitions
        seg_text = "\n\n".join(f"[Bloc {i+1}/{len(segments)}]\n{seg}" for i, seg in enumerate(segments))
        user_content = f"{header}Transcription segmentée en {len(segments)} blocs de ~45 secondes:\n\n{seg_text[:max_chars]}"
    else:
        user_content = f"{header}Transcription:\n{transcription_text[:max_chars]}"

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": RADIO_SPLIT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=1500,
            json_mode=True,
        )
        if raw is None:
            return None

        result = json.loads(raw)
        topics = result.get("topics", [])

        if not topics:
            return None

        # Résolution d'alias pour radio
        try:
            from backend.entity_aliases import resolve_entities
        except ImportError:
            try:
                from entity_aliases import resolve_entities
            except ImportError:
                resolve_entities = None

        # Valider chaque topic
        valid_topics = []
        for t in topics:
            if t.get("title") and t.get("summary"):
                t["gravity"] = float(t.get("gravity", 0.3))
                entities = t.get("entities", [])
                if resolve_entities:
                    entities = resolve_entities(entities)
                t["entities"] = entities
                t["theme"] = t.get("theme", "general")
                # Événement structuré
                event_raw = t.get("event", {})
                if event_raw:
                    t["event_structured"] = {
                        "subject": event_raw.get("subject", ""),
                        "action": event_raw.get("action", ""),
                        "object": event_raw.get("object", ""),
                        "event_type": event_raw.get("event_type", "routine"),
                        "location": event_raw.get("location", ""),
                    }
                valid_topics.append(t)

        logger.info(
            f"📻 Transcription {radio_name}: {len(valid_topics)} sujets extraits"
        )
        return valid_topics

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Split radio: JSON invalide: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Split radio échoué: {e}")
        return None


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
# Enrichissement des posts sociaux (Facebook/Instagram/Twitter)
# ============================================================

SOCIAL_POST_PROMPT = """Tu es un analyste média spécialisé dans l'actualité de la Guadeloupe et des Antilles françaises.

On te donne un lot de posts de réseaux sociaux. Analyse CHAQUE post et retourne un JSON.
Les posts sont souvent courts, informels, parfois en créole guadeloupéen.

Pour CHAQUE post, détermine :
1. S'il concerne l'actualité/la vie publique de la Guadeloupe (pertinent = true) ou non (pub, perso, hors-sujet)
2. Les entités nommées (élus, institutions, lieux spécifiques)
3. Le thème
4. La gravité (impact sur la population)

Réponds UNIQUEMENT en JSON :
{
  "posts": [
    {
      "index": 1,
      "relevant": true,
      "elected": ["Guy Losbar"],
      "institutions": ["SMGEAG"],
      "theme": "eau_env",
      "gravity": 0.45,
      "summary": "Coupure d'eau à Petit-Pérou, habitants mécontents",
      "keywords": ["eau", "coupure", "Petit-Pérou"],
      "event": {"subject": "SMGEAG", "action": "coupe l'eau", "object": "habitants de Petit-Pérou", "event_type": "incident", "location": "Petit-Pérou"}
    }
  ]
}

Thèmes possibles : eau_env, energie_transports, sante_social, education, economie_emploi, culture_patrimoine, securite_justice, politique, sport, general

RÈGLES :
- Un post sur un match de foot local → relevant=true, theme=sport, gravity=0.05
- Un post personnel (selfie, anniversaire, pub) → relevant=false
- Un post en créole sur une grève → relevant=true, traduis en français pour le summary
- Même calibration gravity que pour les articles (60% < 0.25, 10% > 0.50)
- Sois précis sur les noms : utilise prénom + nom pour les personnalités
- Les institutions : CHU, SMGEAG, EDF, ARS, Préfecture, Région, Département, SDIS, CAF, IEDOM"""


def enrich_social_posts_batch(posts: List[Dict[str, Any]], batch_size: int = 15) -> List[Dict[str, Any]]:
    """
    Enrichit un lot de posts sociaux via IA en un seul appel.
    Retourne la liste des posts enrichis (seuls les pertinents sont marqués).
    Batch de 15 max pour rester dans les limites de tokens.
    """
    if not is_available():
        return []

    if not posts:
        return []

    # Construire le texte des posts
    lines = []
    for i, post in enumerate(posts[:batch_size], 1):
        platform = post.get("platform", "?")
        author = post.get("author", "?")
        text = (post.get("text") or "")[:300]
        if not text.strip():
            continue
        lines.append(f"{i}. [{platform}] @{author}: {text}")

    if not lines:
        return []

    user_content = "\n".join(lines)

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": SOCIAL_POST_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=1500,
            json_mode=True,
        )
        if raw is None:
            return []

        result = json.loads(raw)
        ai_posts = result.get("posts", [])

        # Résolution d'alias
        try:
            from backend.entity_aliases import resolve_entities
        except ImportError:
            try:
                from entity_aliases import resolve_entities
            except ImportError:
                resolve_entities = None

        enriched = []
        for ai_post in ai_posts:
            idx = ai_post.get("index", 0) - 1
            if 0 <= idx < len(posts):
                original = posts[idx]
                elected = ai_post.get("elected", [])
                institutions = ai_post.get("institutions", [])
                if resolve_entities:
                    elected = resolve_entities(elected)
                    institutions = resolve_entities(institutions)
                original["ai_enriched"] = True
                original["ai_relevant"] = ai_post.get("relevant", False)
                original["elected"] = elected
                original["institutions"] = institutions
                original["entities"] = list(set(elected + institutions))
                original["theme"] = ai_post.get("theme", "general")
                original["gravity_score"] = float(ai_post.get("gravity", 0.1))
                original["ai_summary"] = ai_post.get("summary", "")
                original["keywords_found"] = ai_post.get("keywords", [])
                # Événement structuré
                event_raw = ai_post.get("event", {})
                if event_raw:
                    original["event_structured"] = {
                        "subject": event_raw.get("subject", ""),
                        "action": event_raw.get("action", ""),
                        "object": event_raw.get("object", ""),
                        "event_type": event_raw.get("event_type", "routine"),
                        "location": event_raw.get("location", ""),
                    }
                original["_analysis_method"] = f"{AI_PROVIDER}_{AI_MODEL}_social"
                enriched.append(original)

        logger.info(f"📱 Enrichissement social: {len(enriched)}/{len(posts)} posts enrichis par IA")
        return enriched

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Social enrichissement: JSON invalide: {e}")
        return []
    except Exception as e:
        logger.warning(f"⚠️ Social enrichissement échoué: {e}")
        return []


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


# ============================================================
# Déduplication IA des affaires — GPT compare les affaires actives
# ============================================================

DEDUP_PROMPT = """Tu es un analyste média spécialisé Guadeloupe/Antilles.

On te donne une liste d'AFFAIRES ACTIVES. Certaines parlent du MÊME événement ou sujet
mais ont été créées séparément (titres légèrement différents, sources différentes, etc.).

Identifie les GROUPES D'AFFAIRES QUI SONT DES DOUBLONS (même événement réel).

CRITÈRES POUR CONSIDÉRER COMME DOUBLON :
- Même événement concret (même incident, même décision, même personne impliquée dans la même action)
- Même sujet traité sous des angles différents (ex: "Pénurie d'eau à Petit-Pérou" et "Résidents sans eau aux Abymes")
- Même institution/personne + même action (ex: "Ary Chalus convoqué" et "Arichalus devant le parquet")
- Même lieu + même type d'incident (ex: "Plongeur décédé à Sainte-Anne" et "Mort d'un touriste à Sainte-Anne")

CE QUI N'EST PAS UN DOUBLON :
- Même thème mais événements différents (ex: deux accidents différents, deux grèves différentes)
- Même personne mais actions différentes (ex: "Chalus annonce" vs "Chalus critiqué pour corruption")
- Même institution mais sujets différents

Réponds UNIQUEMENT en JSON :
{
  "duplicates": [
    {
      "keep_id": "ID de l'affaire à garder (la plus complète/haute gravité)",
      "merge_ids": ["ID1", "ID2"],
      "reason": "explication courte du doublon"
    }
  ]
}

Si aucun doublon → {"duplicates": []}
Sois CONSERVATEUR : en cas de doute, ne fusionne PAS."""


def detect_duplicate_affairs(affairs: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """
    Utilise GPT pour identifier les affaires actives qui sont des doublons.
    Envoie seulement titre + entités + action (léger en tokens).

    Retourne une liste de groupes à fusionner :
    [{"keep_id": "...", "merge_ids": ["...", "..."], "reason": "..."}]

    Retourne None si échec ou IA non disponible.
    """
    if not is_available():
        return None

    if len(affairs) < 2:
        return []

    # Limiter à 40 affaires pour rester dans les limites de tokens
    affairs_to_check = affairs[:40]

    # Construire la liste compacte
    lines = ["=== AFFAIRES ACTIVES ==="]
    for aff in affairs_to_check:
        aff_id = str(aff.get("_id", "?"))
        title = (aff.get("title", "") or "")[:120]
        gravity = aff.get("gravity_score", 0)
        elected = ", ".join((aff.get("elected", []) or [])[:5])
        institutions = ", ".join((aff.get("institutions", []) or [])[:5])
        items = aff.get("item_count", 0)

        # Événement structuré si disponible
        event = aff.get("event_structured", {}) or {}
        action_str = ""
        if event.get("subject") and event.get("action"):
            action_str = f" | Action: {event['subject']} → {event['action']}"
            if event.get("object"):
                action_str += f" ({event['object']})"

        line = f"[{aff_id}] gravity={gravity:.2f} items={items} | {title}"
        if elected:
            line += f" | Élus: {elected}"
        if institutions:
            line += f" | Instit: {institutions}"
        if action_str:
            line += action_str
        lines.append(line)

    user_content = "\n".join(lines)

    try:
        raw = _call_ai(
            messages=[
                {"role": "system", "content": DEDUP_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.05,
            max_tokens=1000,
            json_mode=True,
        )
        if raw is None:
            return None

        result = json.loads(raw)
        duplicates = result.get("duplicates", [])

        if not duplicates:
            logger.info("🔍 Dédup IA: aucun doublon détecté")
            return []

        # Valider que les IDs existent dans la liste
        valid_ids = {str(a.get("_id", "")) for a in affairs_to_check}
        validated = []
        for dup in duplicates:
            keep_id = str(dup.get("keep_id", ""))
            merge_ids = [str(mid) for mid in dup.get("merge_ids", [])]

            if keep_id not in valid_ids:
                logger.warning(f"⚠️ Dédup IA: keep_id '{keep_id}' non trouvé, ignoré")
                continue

            valid_merges = [mid for mid in merge_ids if mid in valid_ids and mid != keep_id]
            if not valid_merges:
                continue

            validated.append({
                "keep_id": keep_id,
                "merge_ids": valid_merges,
                "reason": dup.get("reason", "doublon IA"),
            })

        if validated:
            logger.info(
                f"🤖 Dédup IA: {len(validated)} groupes de doublons détectés "
                f"({sum(len(d['merge_ids']) for d in validated)} affaires à fusionner)"
            )
        return validated

    except json.JSONDecodeError as e:
        logger.warning(f"⚠️ Dédup IA: JSON invalide: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Dédup IA échoué: {e}")
        return None
