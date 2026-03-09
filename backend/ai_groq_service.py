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
# Configuration — OpenAI en priorité, fallback Groq/xAI
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
_user_model = os.environ.get("GROQ_MODEL", "").strip()

# --- Provider PRIMAIRE : OpenAI GPT-4o-mini (fiable + pas cher) ---
AI_PROVIDER = "openai"
AI_BASE_URL = "https://api.openai.com/v1"
AI_MODEL = "gpt-4o-mini"

# --- Fallback : xAI/Groq (si OpenAI indisponible) ---
if GROQ_API_KEY.startswith("xai-"):
    FALLBACK_PROVIDER = "xai"
    FALLBACK_BASE_URL = "https://api.x.ai/v1"
    FALLBACK_MODEL = _user_model if _user_model and _user_model != "mixtral-8x7b-32768" else "grok-2-latest"
elif GROQ_API_KEY.startswith("gsk_"):
    FALLBACK_PROVIDER = "groq"
    FALLBACK_BASE_URL = "https://api.groq.com/openai/v1"
    FALLBACK_MODEL = _user_model or "mixtral-8x7b-32768"
else:
    FALLBACK_PROVIDER = "groq"
    FALLBACK_BASE_URL = "https://api.groq.com/openai/v1"
    FALLBACK_MODEL = _user_model or "mixtral-8x7b-32768"

# Compat
GROQ_MODEL = AI_MODEL

# ============================================================
# Clients IA (primaire + fallback)
# ============================================================

_client = None
_fallback_client = None


def _get_client():
    """Initialise le client IA primaire — OpenAI GPT-4o-mini (lazy loading)."""
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
        logger.info(f"✅ Client IA primaire — provider: {AI_PROVIDER}, modèle: {AI_MODEL}")
        return _client
    except Exception as e:
        logger.error(f"❌ Impossible d'initialiser le client IA primaire (OpenAI): {e}")
        return None


def _get_fallback_client():
    """Initialise le client IA fallback — xAI/Groq (lazy loading)."""
    global _fallback_client
    if _fallback_client is not None:
        return _fallback_client
    if not GROQ_API_KEY:
        return None
    try:
        from openai import OpenAI
        _fallback_client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url=FALLBACK_BASE_URL,
        )
        logger.info(f"✅ Client IA fallback — {FALLBACK_PROVIDER}/{FALLBACK_MODEL}")
        return _fallback_client
    except Exception as e:
        logger.warning(f"⚠️ Fallback {FALLBACK_PROVIDER} non disponible: {e}")
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

    # 1. Essayer OpenAI (provider primaire)
    client = _get_client()
    if client:
        try:
            resp = client.chat.completions.create(model=AI_MODEL, **kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"⚠️ {AI_PROVIDER}/{AI_MODEL} échoué: {e} — fallback {FALLBACK_PROVIDER}")

    # 2. Fallback xAI/Groq
    fb = _get_fallback_client()
    if fb:
        try:
            resp = fb.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            content = resp.choices[0].message.content.strip()
            logger.info(f"✅ Fallback {FALLBACK_PROVIDER}/{FALLBACK_MODEL} OK")
            return content
        except Exception as e:
            logger.error(f"❌ Fallback {FALLBACK_PROVIDER} aussi échoué: {e}")

    return None


def is_available() -> bool:
    """Vérifie si au moins un service IA est disponible."""
    return bool(OPENAI_API_KEY and _get_client()) or bool(GROQ_API_KEY and _get_fallback_client())


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

Autres règles :
- Sois précis sur les noms : utilise le prénom ET le nom pour les personnalités
- Les institutions locales de Guadeloupe sont importantes : CHU, SMGEAG, EDF Guadeloupe, ARS, Préfecture, Région, Département, CAF
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
        gravity_score = float(result.get("gravity_score", 0.15))
        is_affair = result.get("is_affair", gravity_score >= 0.55)
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


def split_radio_transcription(
    transcription_text: str,
    radio_name: str = "",
    max_chars: int = 4000,
) -> Optional[List[Dict[str, Any]]]:
    """
    Découpe une transcription radio en sujets individuels via IA.
    Chaque sujet peut ensuite être assigné à une affaire différente.
    Retourne une liste de topics ou None si échec.
    """
    if not is_available():
        return None

    if not transcription_text or len(transcription_text.strip()) < 50:
        return None

    header = f"Radio: {radio_name}\n" if radio_name else ""
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

        # Valider chaque topic
        valid_topics = []
        for t in topics:
            if t.get("title") and t.get("summary"):
                t["gravity"] = float(t.get("gravity", 0.3))
                t["entities"] = t.get("entities", [])
                t["theme"] = t.get("theme", "general")
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
