"""
Observatoire social — phase 1 : snapshots historiques des comptes RS.

Le scraping (Apify) met à jour les stats *courantes* dans `campaign_posts`, mais
écrase les valeurs sans garder de trace datée. Ce service ajoute une couche
« snapshot » par-dessus : il fige chaque jour les agrégats d'engagement par
plateforme dans la collection `account_snapshots`, ce qui permet de tracer une
courbe d'évolution dans le temps.

Stratégie de capture (cf. décision produit) :
  - engagement (vues/likes/commentaires/partages, nb de posts) → capture QUOTIDIENNE
  - followers/abonnés → capture HEBDOMADAIRE (le profile-scraping coûte plus cher
    et la valeur bouge lentement). Les followers sont lus *gratuitement* depuis
    les items déjà renvoyés par les actors quand ils sont présents, sinon laissés
    à null sans bloquer le snapshot d'engagement.

Aucune donnée existante n'est modifiée : lecture seule sur `campaign_posts`,
écriture uniquement dans `account_snapshots` (upsert idempotent par jour).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger("veille.social_snapshot")

PLATFORMS = ("instagram", "facebook", "tiktok")

# Champs d'engagement agrégés que l'on suit dans le temps.
_METRICS = ("views", "likes", "comments", "shares")


def _get_db():
    from backend.db import get_db
    return get_db()


def _today_str() -> str:
    """Date du jour (UTC) au format YYYY-MM-DD — clé d'idempotence du snapshot."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_int(val) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _aggregate_engagement(db) -> Dict[str, Dict[str, int]]:
    """Somme les métriques d'engagement de tous les posts, groupées par plateforme.

    Lit `campaign_posts.stats` (valeurs courantes maintenues par le scraper Apify
    et la sync Buffer). Renvoie {platform: {views, likes, comments, shares, posts}}.
    """
    agg: Dict[str, Dict[str, int]] = {
        p: {m: 0 for m in _METRICS} | {"posts": 0} for p in PLATFORMS
    }

    cursor = db["campaign_posts"].find(
        {"platform": {"$in": list(PLATFORMS)}},
        {"platform": 1, "stats": 1},
    )
    for post in cursor:
        platform = post.get("platform")
        if platform not in agg:
            continue
        stats = post.get("stats") or {}
        agg[platform]["posts"] += 1
        for m in _METRICS:
            agg[platform][m] += _safe_int(stats.get(m))

    return agg


def _engagement_total(metrics: Dict[str, int]) -> int:
    """Engagement = somme des interactions (likes + commentaires + partages)."""
    return metrics.get("likes", 0) + metrics.get("comments", 0) + metrics.get("shares", 0)


def _read_followers(db, platform: str) -> Optional[int]:
    """Lit le nombre d'abonnés *si* déjà capturé (gratuitement) par le scraper.

    Les actors Apify renvoient parfois la taille d'audience dans les items
    (ex. `authorMeta.fans` pour TikTok). Le scraper la stocke, le cas échéant,
    sous `campaign_posts.author_followers`. On prend la valeur la plus récente.
    Renvoie None si l'info n'est pas disponible (capture hebdo dédiée plus tard).
    """
    doc = db["campaign_posts"].find_one(
        {"platform": platform, "author_followers": {"$gt": 0}},
        {"author_followers": 1},
        sort=[("created_at", -1)],
    )
    if doc and doc.get("author_followers"):
        return _safe_int(doc["author_followers"])
    return None


def capture_snapshots(include_followers: bool = False) -> Dict[str, Any]:
    """Fige l'état d'engagement du jour pour chaque plateforme.

    Idempotent : ré-exécuté le même jour, met à jour le snapshot existant
    (upsert sur la clé unique platform + snapshot_date).

    Args:
        include_followers: si True, tente aussi de renseigner le champ followers
            (utilisé par le job hebdomadaire). Sinon le champ n'est pas touché,
            ce qui préserve une éventuelle valeur déjà capturée cette semaine.

    Returns:
        {ok, snapshot_date, platforms: {platform: {...metrics}}, captured}
    """
    db = _get_db()
    date_str = _today_str()
    now_iso = datetime.now(timezone.utc).isoformat()

    agg = _aggregate_engagement(db)
    out_platforms: Dict[str, Any] = {}
    captured = 0

    for platform in PLATFORMS:
        metrics = agg[platform]
        doc = {
            "platform": platform,
            "snapshot_date": date_str,
            "captured_at": now_iso,
            "posts_count": metrics["posts"],
            "views": metrics["views"],
            "likes": metrics["likes"],
            "comments": metrics["comments"],
            "shares": metrics["shares"],
            "engagement": _engagement_total(metrics),
        }

        if include_followers:
            followers = _read_followers(db, platform)
            if followers is not None:
                doc["followers"] = followers
                doc["followers_captured_at"] = now_iso

        # Upsert idempotent : un snapshot par plateforme par jour.
        db["account_snapshots"].update_one(
            {"platform": platform, "snapshot_date": date_str},
            {"$set": doc},
            upsert=True,
        )
        out_platforms[platform] = {k: doc[k] for k in
                                   ("posts_count", "views", "likes", "comments", "shares", "engagement")}
        captured += 1

    logger.info("📸 Snapshots sociaux capturés (%s) : %d plateformes", date_str, captured)
    return {"ok": True, "snapshot_date": date_str, "platforms": out_platforms, "captured": captured}


def capture_followers_weekly() -> Dict[str, Any]:
    """Job hebdomadaire : renseigne les followers sur le snapshot du jour.

    Délègue à capture_snapshots(include_followers=True) pour garantir qu'un
    snapshot du jour existe, puis y attache les followers disponibles.
    """
    return capture_snapshots(include_followers=True)


def get_history(platform: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
    """Renvoie la série temporelle des snapshots sur `days` jours.

    Args:
        platform: filtre une plateforme, ou None pour toutes.
        days: profondeur d'historique (défaut 30).

    Returns:
        {ok, days, series: {platform: [{snapshot_date, engagement, followers, ...}]}}
    """
    db = _get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    query: Dict[str, Any] = {"snapshot_date": {"$gte": since}}
    if platform:
        query["platform"] = platform

    series: Dict[str, List[Dict[str, Any]]] = {}
    cursor = db["account_snapshots"].find(
        query, {"_id": 0}
    ).sort("snapshot_date", 1)
    for snap in cursor:
        series.setdefault(snap["platform"], []).append(snap)

    return {"ok": True, "days": days, "series": series}


def get_evolution() -> Dict[str, Any]:
    """Résumé d'évolution par plateforme : valeur actuelle + deltas J-7 / J-30.

    Pour chaque plateforme, compare le dernier snapshot aux snapshots ~7j et ~30j
    plus tôt, afin d'afficher une tendance (hausse/baisse) en tête de la vue.
    """
    db = _get_db()
    out: Dict[str, Any] = {}

    for platform in PLATFORMS:
        snaps = list(
            db["account_snapshots"].find({"platform": platform}, {"_id": 0})
            .sort("snapshot_date", -1).limit(40)
        )
        if not snaps:
            out[platform] = {"available": False}
            continue

        latest = snaps[0]

        def _delta(metric: str, ref_index: int) -> Optional[int]:
            if len(snaps) > ref_index:
                return _safe_int(latest.get(metric)) - _safe_int(snaps[ref_index].get(metric))
            return None

        out[platform] = {
            "available": True,
            "snapshot_date": latest.get("snapshot_date"),
            "engagement": latest.get("engagement", 0),
            "followers": latest.get("followers"),
            "posts_count": latest.get("posts_count", 0),
            "delta_engagement_7d": _delta("engagement", 7),
            "delta_engagement_30d": _delta("engagement", 30),
            "delta_followers_7d": _delta("followers", 7) if latest.get("followers") is not None else None,
        }

    return {"ok": True, "platforms": out}
