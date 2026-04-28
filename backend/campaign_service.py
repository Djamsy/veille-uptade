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
# BUFFER API (GraphQL — nouvelle API officielle)
# Docs: https://developers.buffer.com/guides/getting-started.html
# Endpoint unique: https://api.buffer.com
# Auth: Bearer token
# ============================================================

BUFFER_GRAPHQL_URL = "https://api.buffer.com"
BUFFER_ORG_ID = os.getenv("BUFFER_ORG_ID", "")


def _buffer_graphql(query: str, variables: Dict = None) -> Optional[Dict]:
    """Appel GraphQL à Buffer (endpoint officiel api.buffer.com).

    Retourne le dict "data" en cas de succès.
    En cas d'erreur GraphQL, retourne {"_errors": [...]} pour que l'appelant
    puisse voir le message d'erreur exact.
    """
    if not BUFFER_ACCESS_TOKEN:
        logger.warning("Buffer non configuré (BUFFER_ACCESS_TOKEN manquant)")
        return None

    payload = json.dumps({
        "query": query,
        "variables": variables or {},
    }).encode()

    try:
        req = urllib.request.Request(BUFFER_GRAPHQL_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BUFFER_ACCESS_TOKEN}",
            "User-Agent": "VeilleMedia/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            result = json.loads(raw)
            logger.info(f"📡 Buffer GraphQL response: {str(raw[:800])}")
            if result.get("errors"):
                err_msgs = [e.get("message", str(e)) for e in result["errors"]]
                logger.error(f"Buffer GraphQL errors: {err_msgs}")
                # Retourner les erreurs au lieu de None pour debug
                return {"_errors": result["errors"], "_data": result.get("data")}
            return result.get("data")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else ""
        logger.error(f"Buffer GraphQL HTTP {e.code}: {body[:500]}")
        return None
    except Exception as e:
        logger.error(f"Buffer GraphQL error: {e}")
        return None


def _get_org_id() -> str:
    """Récupère l'organization ID Buffer via account query."""
    if BUFFER_ORG_ID:
        return BUFFER_ORG_ID

    query = """query { account { organizations { id name } } }"""
    data = _buffer_graphql(query)
    if data and data.get("account"):
        orgs = data["account"].get("organizations") or []
        if orgs:
            oid = orgs[0].get("id", "")
            logger.info(f"📡 Buffer org: {orgs[0].get('name', '?')} ({oid})")
            return oid
    logger.warning("Buffer: impossible de récupérer l'org ID")
    return ""


def get_buffer_channels() -> List[Dict]:
    """Liste les channels Buffer connectés via channels(organizationId)."""
    org_id = _get_org_id()
    if not org_id:
        logger.warning("Buffer: pas d'org ID → impossible de lister les channels")
        return []

    query = """
    query GetChannels($input: ChannelsInput!) {
      channels(input: $input) {
        id
        name
        service
        organizationId
      }
    }
    """
    variables = {"input": {"organizationId": org_id}}
    data = _buffer_graphql(query, variables)

    if not data or not data.get("channels"):
        logger.warning("Buffer: aucun channel trouvé")
        return []

    channels = data["channels"]
    logger.info(f"📡 Buffer: {len(channels)} channels trouvés")
    for ch in channels:
        logger.info(f"   → {ch.get('name', '?')} ({ch.get('service', '?')}) id={ch.get('id', '?')}")
    return channels


def _clean_social_text(text: str) -> str:
    """Nettoie le texte pour les réseaux sociaux.

    Supprime le markdown qui n'est pas interprété par les plateformes :
    - *gras* → gras (supprime les astérisques)
    - __texte__ → texte
    - [texte](url) → texte (url)
    - Caractères Unicode bold (𝐀-𝐳) → caractères normaux
    """
    import unicodedata

    # 1. Liens markdown [texte](url) → texte (url)
    cleaned = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)

    # 2. __texte__ → texte
    cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)

    # 3. *texte* → texte (mais pas ** ou les emojis)
    cleaned = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'\1', cleaned)

    # 4. Caractères Unicode bold → ASCII normal
    # Les Mathematical Bold (U+1D400-1D433) et autres séries Unicode fancy
    result = []
    for ch in cleaned:
        cp = ord(ch)
        # Mathematical Bold Capital A-Z: U+1D400-1D419
        if 0x1D400 <= cp <= 0x1D419:
            result.append(chr(cp - 0x1D400 + ord('A')))
        # Mathematical Bold Small a-z: U+1D41A-1D433
        elif 0x1D41A <= cp <= 0x1D433:
            result.append(chr(cp - 0x1D41A + ord('a')))
        # Bold digits: U+1D7CE-1D7D7
        elif 0x1D7CE <= cp <= 0x1D7D7:
            result.append(chr(cp - 0x1D7CE + ord('0')))
        else:
            result.append(ch)

    return ''.join(result)


def _build_create_post_mutation(text: str, channel_id: str, service: str,
                                media_urls: List[str] = None) -> str:
    """Construit la mutation createPost avec assets + metadata par plateforme.

    Schema Buffer (introspection) :
    - assets: { images: [{ url }], videos: [{ url }] }
    - metadata.facebook:  { type: post|story|reel }  (NON_NULL)
    - metadata.instagram: { type: post|story|reel, shouldShareToFeed: true } (NON_NULL)
    - metadata.youtube:   { title: "...", categoryId: "22" }
    - metadata.tiktok:    { title: "..." }
    """
    # Nettoyer le markdown / Unicode bold
    clean_text = _clean_social_text(text)
    escaped_text = clean_text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

    # ── Assets (images / videos) ──
    has_video = False
    has_image = False
    assets_part = ""
    if media_urls:
        images = []
        videos = []
        for url in media_urls[:4]:
            if '/video/' in url or url.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                videos.append(url)
            else:
                images.append(url)

        has_video = bool(videos)
        has_image = bool(images)
        asset_items = []
        if images:
            img_entries = ", ".join([f'{{ url: "{u}" }}' for u in images])
            asset_items.append(f"images: [{img_entries}]")
        if videos:
            vid_entries = ", ".join([f'{{ url: "{u}" }}' for u in videos])
            asset_items.append(f"videos: [{vid_entries}]")

        if asset_items:
            assets_part = f'assets: {{ {", ".join(asset_items)} }},'

    # ── Metadata par plateforme ──
    metadata_part = ""
    has_media = has_video or has_image

    if service == "facebook":
        # Toujours "post" — reel limité à 1m30
        metadata_part = 'metadata: { facebook: { type: post } },'

    elif service == "instagram":
        # type + shouldShareToFeed sont NON_NULL
        if not has_media:
            return ""  # skip — Instagram sans média impossible
        ig_type = "reel" if has_video else "post"
        metadata_part = f'metadata: {{ instagram: {{ type: {ig_type}, shouldShareToFeed: true }} }},'

    elif service == "youtube":
        # YouTube exige une vidéo
        if not has_video:
            return ""  # skip — YouTube sans vidéo impossible
        # Extraire un titre nettoyé (première ligne, max 90 chars)
        raw_title = clean_text.split('\\n')[0].split('\n')[0].strip()
        # Enlever emojis de début et ponctuation
        raw_title = re.sub(r'^[^\w]*', '', raw_title).strip()[:90]
        escaped_title = raw_title.replace('\\', '\\\\').replace('"', '\\"')
        if not escaped_title:
            escaped_title = "Publication Conseil Departemental Guadeloupe"
        metadata_part = f'metadata: {{ youtube: {{ title: "{escaped_title}", categoryId: "25" }} }},'

    elif service == "tiktok":
        # TikTok exige un média
        if not has_media:
            return ""  # skip — TikTok sans média impossible

    elif service == "twitter":
        # Twitter : pas de metadata requise, mais limite 280 chars
        # On tronque le texte nettoyé et on ajoute un lien si possible
        if len(clean_text) > 275:
            # Couper au dernier espace avant 275 chars + "..."
            cut = clean_text[:272].rsplit(' ', 1)[0]
            escaped_text = cut.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + "..."

    # Pour les services inconnus, on envoie tel quel (pas de metadata)

    mutation = f'''
    mutation {{
      createPost(input: {{
        text: "{escaped_text}",
        channelId: "{channel_id}",
        schedulingType: now,
        {assets_part}
        {metadata_part}
      }}) {{
        ... on PostActionSuccess {{
          post {{
            id
            text
            dueAt
          }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    '''
    return mutation


def publish_to_buffer(text: str, media_urls: List[str] = None,
                      channel_ids: List[str] = None) -> Dict:
    """Publie un post via Buffer GraphQL createPost sur tous les channels.

    Adapte automatiquement le post aux exigences de chaque plateforme
    (Facebook, Instagram, YouTube, TikTok).
    """
    if not BUFFER_ACCESS_TOKEN:
        return {"ok": False, "error": "Buffer non configuré (BUFFER_ACCESS_TOKEN)"}

    # 1. Récupérer les channels avec leur service
    channels = get_buffer_channels()
    if not channels:
        return {"ok": False, "error": "Aucun channel Buffer trouvé. Vérifiez BUFFER_ORG_ID et vos profils connectés."}

    # Filtrer par channel_ids si fournis
    if channel_ids:
        channels = [ch for ch in channels if ch["id"] in channel_ids]

    if not channels:
        return {"ok": False, "error": "Aucun channel Buffer trouvé avec les IDs fournis."}

    # 2. Publier sur chaque channel avec la mutation adaptée
    published = []
    errors = []
    skipped = []

    for ch in channels:
        ch_id = ch["id"]
        service = ch.get("service", "unknown")
        ch_name = ch.get("name", ch_id)

        mutation = _build_create_post_mutation(text, ch_id, service, media_urls)

        if not mutation:
            reason = f"{ch_name} ({service}): média requis mais non fourni"
            skipped.append(reason)
            logger.info(f"⏭️ Buffer skip {reason}")
            continue

        result = _buffer_graphql(mutation)

        if not result:
            errors.append(f"channel {ch_id}: pas de réponse (HTTP error)")
            continue

        # Si erreurs GraphQL remontées
        if "_errors" in result:
            gql_errs = [e.get("message", str(e)) for e in result["_errors"]]
            errors.append(f"channel {ch_id}: GraphQL errors: {'; '.join(gql_errs)}")
            logger.error(f"Buffer createPost GQL errors ({ch_id}): {gql_errs}")
            # Vérifier s'il y a quand même des data partielles
            result = result.get("_data") or {}

        create_result = result.get("createPost", {})

        # Succès → PostActionSuccess
        post_data = create_result.get("post")
        if post_data:
            pid = post_data.get("id", "")
            due = post_data.get("dueAt", "")
            published.append(pid)
            logger.info(f"✅ Buffer post créé: {pid} → channel {ch_id} (dueAt: {due})")
            continue

        # Erreur → MutationError
        err_msg = create_result.get("message", "")
        if err_msg:
            errors.append(f"channel {ch_id}: {err_msg}")
            logger.error(f"Buffer createPost error ({ch_id}): {err_msg}")
        else:
            errors.append(f"channel {ch_id}: réponse inattendue: {str(create_result)[:200]}")
            logger.error(f"Buffer createPost réponse inattendue ({ch_id}): {create_result}")

    total = len(channels)
    if published:
        logger.info(f"✅ Buffer: publié sur {len(published)}/{total} channels ({len(skipped)} skippés)")
        return {
            "ok": True,
            "buffer_ids": published,
            "profiles_count": len(published),
            "skipped": skipped if skipped else None,
            "errors": errors if errors else None,
        }

    all_issues = errors + [f"⏭️ {s}" for s in skipped]
    return {"ok": False, "error": "; ".join(all_issues) if all_issues else "Aucun post créé sur Buffer"}


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
        "views": stats.get("impressions", 0) or 0,
        "likes": stats.get("likes", 0) or 0,
        "comments": stats.get("comments", 0) or 0,
        "clicks": stats.get("clicks", 0) or 0,
        "reach": stats.get("reach", 0) or 0,
        "shares": stats.get("shares", 0) or 0,
    }


def fetch_buffer_sent_posts(channel_id: str = None, limit: int = 30) -> List[Dict]:
    """Liste les posts envoyés (publiés) via Buffer avec leurs stats.

    Utilise la query 'sentPosts' du GraphQL Buffer pour chaque channel.
    Beaucoup plus fiable qu'Apify et ne consomme pas de tokens.
    """
    channels = get_buffer_channels()
    if not channels:
        return []

    if channel_id:
        channels = [ch for ch in channels if ch.get("id") == channel_id]

    all_posts = []

    for ch in channels:
        cid = ch.get("id", "")
        service = (ch.get("service", "") or "").lower()

        # Query sentPosts pour ce channel
        query = """
        query GetSentPosts($input: SentPostsInput!) {
          sentPosts(input: $input) {
            id
            text
            createdAt
            scheduledAt
            sentAt
            status
            assets {
              images { url }
              videos { url }
            }
            statistics {
              impressions
              reach
              clicks
              likes
              comments
              shares
              engagements
            }
          }
        }
        """
        variables = {"input": {"channelId": cid, "limit": limit}}
        data = _buffer_graphql(query, variables)

        if not data or not data.get("sentPosts"):
            # Essayer avec la pagination directe
            query2 = """
            query GetSentPosts($channelId: ID!, $limit: Int) {
              channel(id: $channelId) {
                sentPosts(limit: $limit) {
                  id
                  text
                  createdAt
                  scheduledAt
                  sentAt
                  status
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
            }
            """
            data2 = _buffer_graphql(query2, {"channelId": cid, "limit": limit})
            if data2 and data2.get("channel"):
                posts = data2["channel"].get("sentPosts", []) or []
            else:
                logger.warning(f"Buffer: pas de sentPosts pour channel {ch.get('name', cid)}")
                continue
        else:
            posts = data.get("sentPosts", []) or []

        for p in posts:
            stats_raw = p.get("statistics") or {}
            all_posts.append({
                "buffer_id": p.get("id", ""),
                "platform": service,
                "channel_name": ch.get("name", ""),
                "text": p.get("text", ""),
                "published_at": p.get("sentAt") or p.get("scheduledAt") or p.get("createdAt", ""),
                "media_url": "",
                "stats": {
                    "views": stats_raw.get("impressions", 0) or 0,
                    "likes": stats_raw.get("likes", 0) or 0,
                    "comments": stats_raw.get("comments", 0) or 0,
                    "clicks": stats_raw.get("clicks", 0) or 0,
                    "reach": stats_raw.get("reach", 0) or 0,
                    "shares": stats_raw.get("shares", 0) or 0,
                },
            })
            # Extraire l'URL média
            assets = p.get("assets") or {}
            images = assets.get("images") or []
            videos = assets.get("videos") or []
            if videos:
                all_posts[-1]["media_url"] = videos[0].get("url", "")
                all_posts[-1]["media_type"] = "video"
            elif images:
                all_posts[-1]["media_url"] = images[0].get("url", "")
                all_posts[-1]["media_type"] = "photo"

        logger.info(f"📡 Buffer sentPosts: {len(posts)} posts pour {ch.get('name', cid)} ({service})")

    return all_posts


def sync_buffer_stats() -> Dict[str, Any]:
    """Synchronise les stats Buffer → campaign_posts en base.

    Pour chaque post publié via Buffer (qui a des buffer_ids),
    récupère les stats actuelles et met à jour la base.

    Retourne un résumé des mises à jour.
    """
    from bson import ObjectId
    from difflib import SequenceMatcher

    db = _get_db()
    results = {"ok": True, "updated": 0, "created": 0, "platforms": {}}

    # Récupérer les posts Buffer
    buffer_posts = fetch_buffer_sent_posts(limit=30)
    if not buffer_posts:
        logger.info("📡 Buffer sync: aucun post trouvé")
        return {"ok": True, "updated": 0, "created": 0, "message": "Aucun post Buffer"}

    # Posts récents en base (60 jours)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    db_posts = list(db["campaign_posts"].find(
        {"created_at": {"$gte": cutoff}},
        {"_id": 1, "title": 1, "body": 1, "buffer_ids": 1, "platform_stats": 1,
         "stats": 1, "platform": 1, "url": 1, "created_at": 1}
    ))

    for bp in buffer_posts:
        bid = bp.get("buffer_id", "")
        platform = bp.get("platform", "")
        text = bp.get("text", "")

        # Compteur par plateforme
        if platform not in results["platforms"]:
            results["platforms"][platform] = {"updated": 0, "created": 0, "skipped": 0}

        # 1) Match par buffer_id
        matched = None
        for dbp in db_posts:
            bids = dbp.get("buffer_ids") or []
            if bid and bid in bids:
                matched = dbp
                break

        # 2) Match par texte similaire
        if not matched and text:
            s_text = text.strip()[:200].lower()
            for dbp in db_posts:
                db_text = (dbp.get("title", "") + " " + dbp.get("body", "")).strip()[:200].lower()
                if db_text and SequenceMatcher(None, s_text, db_text).ratio() >= 0.55:
                    matched = dbp
                    break

        if matched:
            # Mettre à jour les stats
            post_id = matched["_id"]
            all_ps = matched.get("platform_stats", {})
            all_ps[platform] = bp["stats"]

            total = {"views": 0, "likes": 0, "comments": 0, "clicks": 0, "reach": 0, "shares": 0}
            for ps in all_ps.values():
                for k in total:
                    total[k] += (ps.get(k, 0) or 0)

            db["campaign_posts"].update_one(
                {"_id": post_id},
                {"$set": {
                    f"platform_stats.{platform}": bp["stats"],
                    "stats": total,
                    "stats_updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            results["updated"] += 1
            results["platforms"][platform]["updated"] += 1
        else:
            # Post non trouvé en base, on le skip (déjà créé par le scraper Facebook)
            results["platforms"][platform]["skipped"] += 1

    # Recalculer totaux campagnes
    from backend.social_stats_scraper import _update_campaign_totals
    _update_campaign_totals(db)

    logger.info(f"📡 Buffer sync terminé: {results['updated']} MAJ, {results['created']} créés")
    return results


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


def _get_previous_analysis(campaign_id: str, db) -> Optional[Dict]:
    """Récupère la dernière analyse stockée pour comparaison."""
    from bson import ObjectId
    doc = db["campaign_analyses"].find_one(
        {"campaign_id": campaign_id},
        sort=[("created_at", -1)]
    )
    return doc


def _store_analysis(campaign_id: str, analysis: Dict, previous: Optional[Dict], db) -> Dict:
    """Stocke l'analyse en historique avec delta vs précédente."""
    from bson import ObjectId
    now = datetime.now(timezone.utc)

    record = {
        "campaign_id": campaign_id,
        "analysis": analysis,
        "created_at": now,
        "expires_at": now + timedelta(days=2),
    }

    # Calculer le delta si on a une analyse précédente
    if previous and previous.get("analysis"):
        prev = previous["analysis"]
        delta = {}

        # Delta sentiment score
        prev_score = (prev.get("sentiment") or {}).get("score", 0)
        new_score = (analysis.get("sentiment") or {}).get("score", 0)
        if prev_score and new_score:
            delta["sentiment_score_change"] = round(new_score - prev_score, 3)
            delta["sentiment_direction"] = "up" if new_score > prev_score else ("down" if new_score < prev_score else "stable")

        # Delta sentiment global
        prev_global = (prev.get("sentiment") or {}).get("global", "")
        new_global = (analysis.get("sentiment") or {}).get("global", "")
        if prev_global and new_global and prev_global != new_global:
            delta["sentiment_shift"] = f"{prev_global} -> {new_global}"

        # Delta recommandations (nouvelles vs anciennes)
        prev_recs = set(prev.get("recommendations") or [])
        new_recs = set(analysis.get("recommendations") or [])
        delta["new_recommendations"] = list(new_recs - prev_recs)
        delta["resolved_recommendations"] = list(prev_recs - new_recs)

        record["delta"] = delta
        record["previous_analysis_id"] = previous.get("_id")

    # Stocker dans l'historique
    result = db["campaign_analyses"].insert_one(record)

    # Mettre à jour la campagne avec la dernière analyse
    db["campaigns"].update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {
            "ai_analysis": analysis,
            "analyzed_at": now.isoformat(),
            "analysis_delta": record.get("delta"),
            "next_analysis_at": (now + timedelta(days=2)).isoformat(),
        }}
    )

    return record


def analyze_campaign(campaign_id: str, db=None) -> Optional[Dict]:
    """Analyse IA complète d'une campagne (Mistral -> OpenAI fallback).
    Stocke l'historique et calcule le delta vs la dernière analyse.
    """
    if not MISTRAL_API_KEY and not OPENAI_API_KEY:
        logger.warning("Aucune cle IA configuree -- analyse impossible")
        return None

    if db is None:
        db = _get_db()

    campaign = get_campaign(campaign_id, db)
    if not campaign:
        return None

    posts = get_campaign_posts(campaign_id, limit=100, db=db)
    if not posts:
        return {"error": "Aucun post dans cette campagne"}

    # Récupérer l'analyse précédente pour contexte
    previous = _get_previous_analysis(campaign_id, db)
    previous_context = ""
    if previous and previous.get("analysis"):
        prev_a = previous["analysis"]
        previous_context = f"""

ANALYSE PRECEDENTE ({previous.get('created_at', '').isoformat() if hasattr(previous.get('created_at', ''), 'isoformat') else str(previous.get('created_at', ''))}):
- Sentiment: {(prev_a.get('sentiment') or {}).get('global', '?')} (score: {(prev_a.get('sentiment') or {}).get('score', '?')})
- Recommandations: {json.dumps(prev_a.get('recommendations', [])[:5], ensure_ascii=False)}

Compare avec l'analyse precedente et indique les progressions/regressions dans le champ "evolution"."""

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
    ) + previous_context

    content = _call_ai(prompt, max_tokens=2000)
    if not content:
        return None

    try:
        analysis = json.loads(content)

        # Stocker avec historique et delta
        _store_analysis(campaign_id, analysis, previous, db)

        logger.info(f"Analyse campagne '{campaign['name']}': {analysis.get('sentiment', {}).get('global', '?')}"
                     + (f" (delta: {analysis.get('evolution', '')})" if previous else " (premiere analyse)"))
        return analysis

    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON analyse: {e}")
        return None


def auto_analyze_campaigns(db=None) -> Dict[str, Any]:
    """Re-analyse automatiquement les campagnes dont l'analyse a expiré (>2 jours).
    Appelé par le scheduler."""
    if db is None:
        db = _get_db()

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=2)).isoformat()

    # Campagnes avec analyse expirée ou jamais analysées
    campaigns = list(db["campaigns"].find({
        "$or": [
            {"analyzed_at": {"$exists": False}},
            {"analyzed_at": {"$lt": cutoff}},
        ],
        "post_count": {"$gt": 0},
    }))

    results = {"analyzed": 0, "skipped": 0, "errors": 0, "campaigns": []}

    for camp in campaigns:
        cid = str(camp["_id"])
        try:
            analysis = analyze_campaign(cid, db=db)
            if analysis and "error" not in analysis:
                results["analyzed"] += 1
                results["campaigns"].append(camp.get("name", cid))
            else:
                results["skipped"] += 1
        except Exception as e:
            logger.error(f"Erreur auto-analyse {camp.get('name', cid)}: {e}")
            results["errors"] += 1

    logger.info(f"Auto-analyse: {results['analyzed']} analysees, {results['skipped']} ignorees, {results['errors']} erreurs")
    return results


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
