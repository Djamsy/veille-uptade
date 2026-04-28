# backend/campaign_service.py
"""
Service de gestion des campagnes RS et publications.

Gère :
- CRUD des campagnes (événements)
- Stockage des posts publiés
- Récupération des stats via Buffer API
- Analyse IA des performances (Mistral)

Configuration requise (variables d'environnement) :
  BUFFER_ACCESS_TOKEN   — token d'accès Buffer API
  CLOUDINARY_CLOUD_NAME — nom du cloud Cloudinary
  CLOUDINARY_API_KEY    — clé API Cloudinary
  CLOUDINARY_API_SECRET — secret API Cloudinary
  MISTRAL_API_KEY       — clé API Mistral pour l'analyse IA
"""

import os
import logging
import json
import urllib.request
import urllib.parse
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger("veille.campaigns")

# ── Configuration ──────────────────────────────────────────
BUFFER_ACCESS_TOKEN = os.getenv("BUFFER_ACCESS_TOKEN", "")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Collections MongoDB ──────────────────────────────────
def _get_db():
    from backend.db import get_db
    return get_db()


# ============================================================
# CAMPAGNES
# ============================================================

def create_campaign(name: str, description: str = "", keywords: List[str] = None,
                    start_date: str = None, end_date: str = None, db=None) -> Dict:
    """Crée une nouvelle campagne."""
    if db is None:
        db = _get_db()

    campaign = {
        "name": name,
        "slug": re.sub(r'[^a-z0-9]+', '-', name.lower().strip()).strip('-'),
        "description": description,
        "keywords": keywords or [name.lower()],
        "start_date": start_date or datetime.now(timezone.utc).isoformat(),
        "end_date": end_date,
        "status": "active",  # active, ended, draft
        "created_at": datetime.now(timezone.utc).isoformat(),
        "post_count": 0,
        "total_views": 0,
        "total_likes": 0,
        "total_comments": 0,
        "total_clicks": 0,
        "total_reach": 0,
    }

    result = db["campaigns"].insert_one(campaign)
    campaign["_id"] = str(result.inserted_id)
    logger.info(f"📢 Campagne créée: {name} (keywords: {campaign['keywords']})")
    return campaign


def get_campaigns(status: str = None, db=None) -> List[Dict]:
    """Liste les campagnes."""
    if db is None:
        db = _get_db()
    query = {}
    if status:
        query["status"] = status
    campaigns = list(db["campaigns"].find(query).sort("created_at", -1))
    for c in campaigns:
        c["_id"] = str(c["_id"])
    return campaigns


def get_campaign(campaign_id: str, db=None) -> Optional[Dict]:
    """Récupère une campagne par ID."""
    if db is None:
        db = _get_db()
    from bson import ObjectId
    try:
        campaign = db["campaigns"].find_one({"_id": ObjectId(campaign_id)})
        if campaign:
            campaign["_id"] = str(campaign["_id"])
        return campaign
    except Exception:
        return None


def detect_campaign(text: str, db=None) -> Optional[Dict]:
    """Détecte automatiquement la campagne à partir du texte d'un post.

    Cherche les mots-clés de chaque campagne active dans le texte.
    Si aucun match → retourne la campagne "Institutionnel" (ou la crée).
    """
    if db is None:
        db = _get_db()

    text_lower = text.lower()
    campaigns = list(db["campaigns"].find({"status": "active"}))

    for campaign in campaigns:
        keywords = campaign.get("keywords", [])
        for kw in keywords:
            if kw.lower() in text_lower:
                campaign["_id"] = str(campaign["_id"])
                return campaign

    # Fallback : campagne "Institutionnel"
    instit = db["campaigns"].find_one({"slug": "institutionnel"})
    if not instit:
        instit = create_campaign("Institutionnel", "Posts généraux sans campagne spécifique", db=db)
    else:
        instit["_id"] = str(instit["_id"])
    return instit


def update_campaign(campaign_id: str, updates: Dict, db=None) -> bool:
    """Met à jour une campagne."""
    if db is None:
        db = _get_db()
    from bson import ObjectId
    try:
        result = db["campaigns"].update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": updates}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Erreur update campaign: {e}")
        return False


# ============================================================
# POSTS
# ============================================================

def save_post(post_data: Dict, db=None) -> Dict:
    """Sauvegarde un post publié."""
    if db is None:
        db = _get_db()

    post = {
        "title": post_data.get("title", ""),
        "body": post_data.get("body", ""),
        "hashtags": post_data.get("hashtags", []),
        "media_url": post_data.get("media_url", ""),
        "media_type": post_data.get("media_type", "photo"),  # photo, video, carousel
        "campaign_id": post_data.get("campaign_id", ""),
        "campaign_name": post_data.get("campaign_name", ""),
        "platforms": post_data.get("platforms", {}),  # {instagram: {id, status}, facebook: {...}}
        "buffer_ids": post_data.get("buffer_ids", []),
        "published_at": post_data.get("published_at", datetime.now(timezone.utc).isoformat()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Stats (mises à jour par le scheduler)
        "stats": {
            "views": 0,
            "likes": 0,
            "comments": 0,
            "clicks": 0,
            "reach": 0,
        },
        "platform_stats": {},  # {instagram: {views, likes...}, facebook: {...}}
        "comments_scraped": [],  # commentaires récupérés par Apify
        "sentiment": None,  # analyse sentiment IA
        "ai_analysis": None,  # analyse IA complète
    }

    result = db["campaign_posts"].insert_one(post)
    post["_id"] = str(result.inserted_id)

    # Incrémenter le compteur de la campagne
    if post["campaign_id"]:
        from bson import ObjectId
        try:
            db["campaigns"].update_one(
                {"_id": ObjectId(post["campaign_id"])},
                {"$inc": {"post_count": 1}}
            )
        except Exception:
            pass

    logger.info(f"📝 Post sauvegardé: '{post['title'][:50]}' → campagne {post['campaign_name']}")
    return post


def get_campaign_posts(campaign_id: str = None, limit: int = 50, db=None) -> List[Dict]:
    """Récupère les posts d'une campagne."""
    if db is None:
        db = _get_db()
    query = {}
    if campaign_id:
        query["campaign_id"] = campaign_id
    posts = list(db["campaign_posts"].find(query).sort("published_at", -1).limit(limit))
    for p in posts:
        p["_id"] = str(p["_id"])
    return posts


# ============================================================
# BUFFER API (GraphQL — nouvelle API)
# ============================================================

BUFFER_GRAPHQL_URL = "https://graph.buffer.com/graphql"


def _buffer_graphql(query: str, variables: Dict = None) -> Optional[Dict]:
    """Appel GraphQL à Buffer."""
    if not BUFFER_ACCESS_TOKEN:
        logger.warning("Buffer non configuré")
        return None

    payload = json.dumps({
        "query": query,
        "variables": variables or {},
    }).encode()

    try:
        req = urllib.request.Request(BUFFER_GRAPHQL_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BUFFER_ACCESS_TOKEN}",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            if result.get("errors"):
                logger.error(f"Buffer GraphQL errors: {result['errors']}")
                return None
            return result.get("data")
    except Exception as e:
        logger.error(f"Buffer GraphQL error: {e}")
        return None


def get_buffer_channels() -> List[Dict]:
    """Liste les channels (profils) Buffer connectés."""
    query = """
    query GetChannels {
      organizations {
        id
        channels {
          id
          name
          service
          serverUrl
        }
      }
    }
    """
    data = _buffer_graphql(query)
    if not data:
        return []

    channels = []
    for org in data.get("organizations", []):
        for ch in org.get("channels", []):
            ch["organization_id"] = org["id"]
            channels.append(ch)

    logger.info(f"📡 Buffer: {len(channels)} channels trouvés")
    return channels


def publish_to_buffer(text: str, media_urls: List[str] = None,
                      channel_ids: List[str] = None) -> Dict:
    """Publie un post via Buffer sur toutes les plateformes (GraphQL API).

    Args:
        text: Texte du post
        media_urls: URLs des médias (Cloudinary)
        channel_ids: IDs des channels Buffer (tous si None)

    Returns:
        Dict avec les résultats
    """
    if not BUFFER_ACCESS_TOKEN:
        return {"ok": False, "error": "Buffer non configuré (BUFFER_ACCESS_TOKEN)"}

    # Récupérer les channels si pas spécifiés
    if not channel_ids:
        channels = get_buffer_channels()
        channel_ids = [ch["id"] for ch in channels]

    if not channel_ids:
        return {"ok": False, "error": "Aucun channel Buffer trouvé. Connectez vos RS sur buffer.com."}

    # Construire le contenu
    content = {"text": text}
    if media_urls:
        content["media"] = [{"url": url} for url in media_urls[:4]]

    # Mutation GraphQL pour créer un post
    query = """
    mutation CreateIdea($input: CreateIdeaInput!) {
      createIdea(input: $input) {
        ... on Idea {
          id
          content {
            text
          }
        }
        ... on CoreError {
          message
        }
      }
    }
    """

    # D'abord, récupérer l'organization ID
    channels = get_buffer_channels()
    if not channels:
        return {"ok": False, "error": "Aucun channel Buffer trouvé"}

    org_id = channels[0].get("organization_id", "")

    variables = {
        "input": {
            "organizationId": org_id,
            "content": {
                "title": text[:100],
                "text": text,
            },
        }
    }

    # Créer l'idée (brouillon)
    idea_data = _buffer_graphql(query, variables)

    if not idea_data:
        # Fallback: essayer la publication directe via createPost
        return _publish_direct(text, media_urls, channel_ids, org_id)

    idea = idea_data.get("createIdea", {})
    if idea.get("message"):
        logger.error(f"Buffer createIdea error: {idea['message']}")
        return _publish_direct(text, media_urls, channel_ids, org_id)

    idea_id = idea.get("id", "")
    logger.info(f"📝 Buffer idea créée: {idea_id}")

    # Publier immédiatement sur tous les channels
    publish_query = """
    mutation ShareIdeaNow($input: ShareIdeaNowInput!) {
      shareIdeaNow(input: $input) {
        ... on ShareIdeaNowSuccess {
          posts {
            id
            channelId
          }
        }
        ... on CoreError {
          message
        }
      }
    }
    """

    publish_vars = {
        "input": {
            "ideaId": idea_id,
            "channelIds": channel_ids,
        }
    }

    if media_urls:
        publish_vars["input"]["content"] = {
            "text": text,
            "media": [{"url": url} for url in media_urls[:4]],
        }

    pub_data = _buffer_graphql(publish_query, publish_vars)

    if pub_data:
        share_result = pub_data.get("shareIdeaNow", {})
        if share_result.get("posts"):
            post_ids = [p.get("id", "") for p in share_result["posts"]]
            logger.info(f"✅ Buffer: publié sur {len(post_ids)} channels")
            return {
                "ok": True,
                "buffer_ids": post_ids,
                "profiles_count": len(post_ids),
            }
        if share_result.get("message"):
            logger.error(f"Buffer share error: {share_result['message']}")
            return {"ok": False, "error": share_result["message"]}

    return {"ok": False, "error": "Buffer publication échouée (pas de réponse)"}


def _publish_direct(text: str, media_urls: List[str], channel_ids: List[str], org_id: str) -> Dict:
    """Fallback: publier directement via createPost mutation."""
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on Post {
          id
          channelId
        }
        ... on CoreError {
          message
        }
      }
    }
    """

    published = []
    errors = []

    for ch_id in channel_ids:
        content = {"text": text}
        if media_urls:
            content["media"] = [{"url": url} for url in media_urls[:4]]

        variables = {
            "input": {
                "channelId": ch_id,
                "content": content,
                "publishNow": True,
            }
        }

        result = _buffer_graphql(query, variables)
        if result:
            post = result.get("createPost", {})
            if post.get("id"):
                published.append(post["id"])
                logger.info(f"✅ Buffer post créé: {post['id']} → channel {ch_id}")
            elif post.get("message"):
                errors.append(post["message"])
                logger.error(f"Buffer createPost error ({ch_id}): {post['message']}")

    if published:
        return {
            "ok": True,
            "buffer_ids": published,
            "profiles_count": len(published),
        }
    return {"ok": False, "error": "; ".join(errors) if errors else "Aucun post créé"}


def fetch_buffer_stats(post_id: str) -> Optional[Dict]:
    """Récupère les stats d'un post Buffer via GraphQL."""
    query = """
    query GetPostStats($id: ID!) {
      post(id: $id) {
        statistics {
          impressions
          reach
          clicks
          likes
          comments
          shares
        }
      }
    }
    """
    data = _buffer_graphql(query, {"id": post_id})
    if not data or not data.get("post"):
        return None

    stats = data["post"].get("statistics", {})
    return {
        "views": stats.get("impressions", 0),
        "likes": stats.get("likes", 0),
        "comments": stats.get("comments", 0),
        "clicks": stats.get("clicks", 0),
        "reach": stats.get("reach", 0),
        "shares": stats.get("shares", 0),
    }


# ============================================================
# CLOUDINARY
# ============================================================

def upload_to_cloudinary(file_source: str, resource_type: str = "image") -> Optional[str]:
    """Upload un fichier sur Cloudinary depuis une URL ou un chemin local.

    Args:
        file_source: URL distante (https://...) ou chemin local (file:///path)
        resource_type: "image" ou "video"

    Returns:
        URL publique Cloudinary ou None si échec.
    """
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logger.warning("Cloudinary non configuré")
        return None

    import time
    timestamp = str(int(time.time()))
    is_local = file_source.startswith("file://")

    # Signature Cloudinary
    params = f"timestamp={timestamp}{CLOUDINARY_API_SECRET}"
    signature = hashlib.sha1(params.encode()).hexdigest()

    url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/{resource_type}/upload"
    timeout = 60 if resource_type == "video" else 30

    try:
        if is_local:
            # Upload fichier local en multipart
            local_path = file_source.replace("file://", "")
            import mimetypes
            content_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"

            boundary = f"----CloudinaryBoundary{int(time.time())}"
            fields = {
                "api_key": CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
            }

            body = b""
            for key, val in fields.items():
                body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode()

            with open(local_path, "rb") as f:
                file_data = f.read()

            fname = os.path.basename(local_path)
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
            body += file_data
            body += f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
        else:
            # Upload depuis URL distante
            data = urllib.parse.urlencode({
                "file": file_source,
                "api_key": CLOUDINARY_API_KEY,
                "timestamp": timestamp,
                "signature": signature,
            }).encode()
            req = urllib.request.Request(url, data=data, method="POST")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            public_url = result.get("secure_url", "")
            size_kb = result.get("bytes", 0) // 1024
            logger.info(f"☁️ Upload Cloudinary OK ({size_kb}KB): {public_url[:60]}")
            return public_url
    except Exception as e:
        logger.error(f"Cloudinary upload error: {e}")
        return None


# ============================================================
# ── Appel IA générique (Mistral → OpenAI fallback) ────────

def _call_ai(prompt: str, max_tokens: int = 2000, temperature: float = 0.3) -> Optional[str]:
    """Appelle Mistral, fallback sur OpenAI si indisponible."""
    providers = []
    if MISTRAL_API_KEY:
        providers.append({
            "name": "Mistral",
            "url": "https://api.mistral.ai/v1/chat/completions",
            "key": MISTRAL_API_KEY,
            "model": "mistral-small-latest",
        })
    if OPENAI_API_KEY:
        providers.append({
            "name": "OpenAI",
            "url": "https://api.openai.com/v1/chat/completions",
            "key": OPENAI_API_KEY,
            "model": "gpt-4o-mini",
        })

    if not providers:
        logger.warning("Aucune clé IA configurée (MISTRAL_API_KEY / OPENAI_API_KEY)")
        return None

    for provider in providers:
        try:
            payload = json.dumps({
                "model": provider["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }).encode()

            req = urllib.request.Request(provider["url"], data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {provider['key']}",
            })

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"]
                logger.info(f"🧠 Analyse IA via {provider['name']}")
                return content

        except Exception as e:
            logger.warning(f"⚠️ {provider['name']} échoué: {e}")
            continue

    logger.error("Tous les providers IA ont échoué")
    return None


# ANALYSE IA (MISTRAL / OPENAI)
# ============================================================

CAMPAIGN_ANALYSIS_PROMPT = """Tu es un expert en marketing digital et communication institutionnelle.
Analyse les performances de cette campagne de communication du Conseil Départemental de Guadeloupe.

Données de la campagne :
{campaign_data}

Posts et leurs stats :
{posts_data}

Commentaires récupérés :
{comments_data}

Produis une analyse structurée en JSON :
{{
  "sentiment": {{
    "global": "positif|négatif|neutre|mitigé",
    "score": 0.0-1.0,
    "themes": ["thème récurrent 1", "thème 2"],
    "positive_highlights": ["ce qui a bien marché"],
    "negative_highlights": ["ce qui a mal marché"]
  }},
  "performance": {{
    "best_format": "photo|video|carrousel",
    "best_platform": "instagram|facebook|linkedin|twitter",
    "best_time": "HH:MM",
    "best_day": "lundi|mardi|...",
    "engagement_rate": 0.0,
    "top_post": "titre du post le plus performant"
  }},
  "recommendations": [
    "recommandation concrète 1",
    "recommandation concrète 2",
    "recommandation concrète 3"
  ],
  "summary": "Résumé en 2-3 phrases de la performance globale"
}}"""


def analyze_campaign(campaign_id: str, db=None) -> Optional[Dict]:
    """Analyse IA complète d'une campagne (Mistral → OpenAI fallback)."""
    if not MISTRAL_API_KEY and not OPENAI_API_KEY:
        logger.warning("Aucune clé IA configurée — analyse impossible")
        return None

    if db is None:
        db = _get_db()

    campaign = get_campaign(campaign_id, db)
    if not campaign:
        return None

    posts = get_campaign_posts(campaign_id, limit=100, db=db)
    if not posts:
        return {"error": "Aucun post dans cette campagne"}

    # Préparer les données pour l'IA
    campaign_data = json.dumps({
        "name": campaign["name"],
        "description": campaign.get("description", ""),
        "start_date": campaign.get("start_date", ""),
        "end_date": campaign.get("end_date", ""),
        "post_count": len(posts),
    }, ensure_ascii=False)

    posts_data = json.dumps([{
        "title": p.get("title", ""),
        "media_type": p.get("media_type", ""),
        "published_at": p.get("published_at", ""),
        "stats": p.get("stats", {}),
        "platform_stats": p.get("platform_stats", {}),
    } for p in posts], ensure_ascii=False)

    all_comments = []
    for p in posts:
        all_comments.extend(p.get("comments_scraped", [])[:10])
    comments_data = json.dumps(all_comments[:50], ensure_ascii=False)

    prompt = CAMPAIGN_ANALYSIS_PROMPT.format(
        campaign_data=campaign_data,
        posts_data=posts_data,
        comments_data=comments_data,
    )

    content = _call_ai(prompt, max_tokens=2000)
    if not content:
        return None

    try:
        analysis = json.loads(content)

        # Sauvegarder l'analyse sur la campagne
        from bson import ObjectId
        db["campaigns"].update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {
                "ai_analysis": analysis,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

        logger.info(f"🧠 Analyse campagne '{campaign['name']}': {analysis.get('sentiment', {}).get('global', '?')}")
        return analysis

    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON analyse: {e}")
        return None


def compare_campaigns(campaign_id_a: str, campaign_id_b: str, db=None) -> Optional[Dict]:
    """Compare deux campagnes côte à côte (Mistral → OpenAI fallback)."""
    if not MISTRAL_API_KEY and not OPENAI_API_KEY:
        return None

    if db is None:
        db = _get_db()

    camp_a = get_campaign(campaign_id_a, db)
    camp_b = get_campaign(campaign_id_b, db)
    if not camp_a or not camp_b:
        return None

    posts_a = get_campaign_posts(campaign_id_a, limit=100, db=db)
    posts_b = get_campaign_posts(campaign_id_b, limit=100, db=db)

    prompt = f"""Compare ces deux campagnes du Conseil Départemental de Guadeloupe :

CAMPAGNE A : {camp_a['name']}
- Posts: {len(posts_a)}
- Stats totales: {json.dumps(camp_a.get('total_views', 0))} vues, {camp_a.get('total_likes', 0)} likes
- Analyse: {json.dumps(camp_a.get('ai_analysis', {}), ensure_ascii=False)[:500]}

CAMPAGNE B : {camp_b['name']}
- Posts: {len(posts_b)}
- Stats totales: {json.dumps(camp_b.get('total_views', 0))} vues, {camp_b.get('total_likes', 0)} likes
- Analyse: {json.dumps(camp_b.get('ai_analysis', {}), ensure_ascii=False)[:500]}

Produis un JSON :
{{"comparison": "résumé comparatif en 3-5 phrases", "winner": "A ou B ou égalité", "improvements": ["ce qui a progressé"], "regressions": ["ce qui a regressé"], "tips": ["conseil pour la prochaine édition"]}}"""

    content = _call_ai(prompt, max_tokens=1000)
    if not content:
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON comparaison: {e}")
        return None
