# backend/services/publication_social_check_service.py
"""
Rapprochement « publications validées » ↔ « posts scrapés des comptes du Département ».

La publication sur les réseaux se fait à la main : rien ne dit au système qu'une publication
validée est effectivement sortie. Ce service compare le texte des publications validées
(statut Validée ou Publiée) aux posts récents collectés par le scraping RS
(collection `social_media_posts`, comptes du Département uniquement) :

  - titre normalisé contenu dans le post                      → score 0.95
  - recouvrement des mots de la publication par le post       → score = part des mots retrouvés
  - ressemblance de chaînes (difflib) sur le début du texte   → score = ratio

Si le meilleur score dépasse le seuil, la publication est marquée « vue sur <plateforme> » avec
le lien du post ; une publication seulement « Validée » passe alors en « Publiée » (publication
manuelle constatée), le statut est écrit dans la feuille et une notification est envoyée.

Configuration :
  PUBLICATION_OWN_ACCOUNTS     — identifiants des comptes à considérer, séparés par des virgules
                                 (défaut : departementguadeloupe, departaborguadeloupe,
                                 departement de la guadeloupe, conseil departemental) ; "*" = tous les posts
  PUBLICATION_MATCH_THRESHOLD  — seuil de rapprochement (défaut 0.6)
  PUBLICATION_MATCH_DAYS       — fenêtre de posts examinés (défaut 21 jours)
"""

import os
import re
import logging
import difflib
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.services import crypto_service as crypto
from backend.services import publication_validation_service as pv
from backend.services.google_sheets_service import strip_accents

logger = logging.getLogger("veille.publications.social_check")

SOCIAL_COLLECTION = "social_media_posts"
DEFAULT_OWN_ACCOUNTS = ["departementguadeloupe", "departaborguadeloupe", "departement de la guadeloupe",
                        "departementdelaguadeloupe", "conseil departemental", "cd971", "cg971"]
STOPWORDS = {"les", "des", "une", "dans", "pour", "avec", "sur", "par", "est", "aux", "the", "and", "que", "qui",
             "pas", "plus", "sont", "ont", "ses", "son", "nos", "vos", "leur", "leurs", "cette", "ces", "mais",
             "donc", "ainsi", "comme", "tout", "tous", "toute", "toutes", "ici", "lui", "elle", "ils", "elles",
             "votre", "notre", "etre", "avoir", "fait", "faire", "vous", "nous", "deux", "trois"}
_URL = re.compile(r"https?://\S+")
_HASH = re.compile(r"[#@](\w+)")


# ── Normalisation ──────────────────────────────────────────

def norm_text(s: str) -> str:
    s = _URL.sub(" ", s or "")
    s = _HASH.sub(r"\1", s)
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def tokens(s: str) -> set:
    return {w for w in norm_text(s).split() if len(w) >= 3 and w not in STOPWORDS}


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_accents(s or "").lower())


def own_accounts() -> List[str]:
    raw = os.getenv("PUBLICATION_OWN_ACCOUNTS", "").strip()
    if raw == "*":
        return ["*"]
    lst = [_compact(x) for x in raw.split(",") if x.strip()]
    return lst or [_compact(x) for x in DEFAULT_OWN_ACCOUNTS]


def threshold() -> float:
    try:
        return float(os.getenv("PUBLICATION_MATCH_THRESHOLD", "0.6"))
    except ValueError:
        return 0.6


def window_days() -> int:
    try:
        return max(1, int(os.getenv("PUBLICATION_MATCH_DAYS", "21")))
    except ValueError:
        return 21


def is_own_post(post: Dict[str, Any], accounts: List[str]) -> bool:
    if accounts == ["*"]:
        return True
    hay = _compact(" ".join(str(post.get(k) or "") for k in ("author", "pageName", "username", "ownerUsername", "url")))
    return any(a and a in hay for a in accounts)


def _post_date(post: Dict[str, Any]) -> Optional[datetime]:
    for k in ("posted_at", "scraped_at"):
        v = post.get(k)
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)) and v > 0:
            try:
                return datetime.fromtimestamp(v if v < 1e11 else v / 1000, tz=timezone.utc)
            except Exception:
                continue
        if isinstance(v, str) and v.strip():
            try:
                from dateutil import parser as dp
                d = dp.parse(v)
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


# ── Score ──────────────────────────────────────────────────

def similarity(pub_title: str, pub_text: str, post_text: str) -> Tuple[float, str, int]:
    """Renvoie (score 0..1, méthode, nombre de mots communs). Le nombre de mots communs sert à
    départager deux publications à égalité de score sur un même post : la plus précise gagne."""
    npost = norm_text(post_text)
    if not npost:
        return 0.0, "vide", 0
    best, how = 0.0, "aucune"
    ntitle = norm_text(pub_title)
    if len(ntitle) >= 12 and ntitle in npost:
        best, how = 0.95, "titre contenu"
    ptok = tokens(f"{pub_title} {pub_text}")
    common = len(ptok & tokens(post_text))
    if len(ptok) >= 4:
        cov = common / len(ptok)
        if cov > best:
            best, how = cov, f"mots retrouvés {int(cov * 100)}%"
    a, b = norm_text(f"{pub_title} {pub_text}")[:400], npost[:400]
    if a and b:
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        if ratio > best:
            best, how = ratio, f"ressemblance {int(ratio * 100)}%"
    return round(best, 3), how, common


# ── Rapprochement ──────────────────────────────────────────

def _candidates(db, days: int, accounts: List[str]) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    cur = db[SOCIAL_COLLECTION].find(
        {"text": {"$exists": True, "$ne": ""}},
        {"text": 1, "platform": 1, "author": 1, "pageName": 1, "username": 1, "ownerUsername": 1,
         "url": 1, "posted_at": 1, "scraped_at": 1, "likes": 1},
    ).sort("scraped_at", -1).limit(3000)
    for p in cur:
        d = _post_date(p)
        if d and d < cutoff:
            continue
        if not is_own_post(p, accounts):
            continue
        p["_date"] = d
        out.append(p)
    return out


def post_key(post: Dict[str, Any]) -> str:
    """Identifiant stable d'un post : plateforme + URL (ou post_hash du scraping à défaut).
    Stocké en clair (`seen_post_key`, index unique) : un post ne peut être attribué qu'à UNE publication."""
    import hashlib
    base = f"{post.get('platform', '')}|{post.get('url') or post.get('post_hash') or norm_text(post.get('text', ''))[:200]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _ensure_indexes(db) -> None:
    try:
        db[pv.COLLECTION].create_index("seen_post_key", unique=True, sparse=True)
    except Exception as e:
        logger.debug("index seen_post_key : %s", e)


def check_publications(days: Optional[int] = None, db=None, notify: bool = True) -> Dict[str, Any]:
    """Compare les publications Validée / Publiée aux posts récents des comptes.

    Attribution UN POUR UN : un post déjà attribué (seen_post_key en base) est exclu ; dans un même
    passage, toutes les paires (publication, post) sont triées par score décroissant et attribuées
    tant que ni la publication ni le post ne sont déjà pris. Une publication seulement Validée
    trouvée en ligne passe en Publiée."""
    db = db if db is not None else pv._db()
    _ensure_indexes(db)
    days = days or window_days()
    thr = threshold()
    accounts = own_accounts()
    now = datetime.now(timezone.utc)

    taken = {d["seen_post_key"] for d in db[pv.COLLECTION].find({"seen_post_key": {"$exists": True, "$ne": None}},
                                                                 {"seen_post_key": 1})}
    posts = [p for p in _candidates(db, days, accounts) if post_key(p) not in taken]
    result = {"ok": True, "posts_examined": len(posts), "posts_already_assigned": len(taken), "accounts": accounts,
              "threshold": thr, "days": days, "checked": 0, "newly_detected": [], "confirmed": [], "not_found": [],
              "errors": []}
    if not posts and not taken:
        result["warning"] = "Aucun post récent des comptes dans social_media_posts (scraping RS non lancé, ou comptes non reconnus)"

    # Passe 1 : candidats par publication
    query = {"status_idx": {"$in": [crypto.blind_index(pv.APPROVED), crypto.blind_index(pv.PUBLISHED)]}}
    pubs: List[Dict[str, Any]] = []
    for doc in db[pv.COLLECTION].find(query).sort("updated_at", -1).limit(300):
        try:
            aad = pv._aad(doc["_id"])
            prev = crypto.decrypt_json(doc.get("seen_enc"), aad, default=None)
            if (prev and prev.get("matched")) or doc.get("seen_post_key"):
                continue  # déjà constatée : on ne réattribue jamais
            payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
            decided_at = (crypto.decrypt_json(doc.get("decision_enc"), aad, default={}) or {}).get("at")
            dd = None
            if decided_at:
                try:
                    dd = datetime.fromisoformat(decided_at)
                except Exception:
                    dd = None
            title, text = payload.get("title", ""), payload.get("text", "")
            cands = []
            for p in posts:
                if dd and p.get("_date") and p["_date"] < dd - timedelta(days=2):
                    continue  # post antérieur de plus de 2 jours à la validation : pas celui-ci
                score, how, common = similarity(title, text, p.get("text", ""))
                if score <= 0.2:
                    continue
                cands.append({"score": score, "how": how, "common": common, "platform": p.get("platform"),
                              "url": p.get("url", ""), "author": p.get("author", ""), "key": post_key(p),
                              "posted_at": p["_date"].isoformat() if p.get("_date") else None,
                              "excerpt": (p.get("text") or "")[:160]})
            cands.sort(key=lambda c: -c["score"])
            pubs.append({"doc": doc, "aad": aad, "payload": payload, "decided_at": dd,
                         "status": crypto.decrypt_str(doc.get("status_enc"), aad), "cands": cands, "best": None})
            result["checked"] += 1
        except Exception as e:
            logger.warning("social-check %s : %s", doc.get("_id"), e)
            result["errors"].append({"id": str(doc.get("_id")), "error": str(e)[:200]})

    # Passe 2 : attribution un pour un, meilleures paires d'abord
    pairs = [(c["score"], c.get("common", 0), i, c) for i, pb in enumerate(pubs) for c in pb["cands"] if c["score"] >= thr]
    pairs.sort(key=lambda t: (-t[0], -t[1]))  # meilleur score, puis publication la plus précise
    used_posts: set = set()
    for score, _common, i, c in pairs:
        if pubs[i]["best"] is not None or c["key"] in used_posts:
            continue
        pubs[i]["best"] = c
        used_posts.add(c["key"])

    # Passe 3 : enregistrement
    for pb in pubs:
        doc, aad, payload, status, best = pb["doc"], pb["aad"], pb["payload"], pb["status"], pb["best"]
        try:
            top = [{k: v for k, v in c.items() if k not in ("key", "common")} for c in pb["cands"][:3]]
            best_pub = {k: v for k, v in best.items() if k not in ("key", "common")} if best else None
            seen = {"checked_at": now.isoformat(), "matched": best is not None, "best": best_pub or (top[0] if top else None),
                    "candidates": top, "threshold": thr}
            update: Dict[str, Any] = {"seen_enc": crypto.encrypt_json(seen, aad), "seen_checked_at": now}
            if best:
                update["seen_at"] = now
                update["seen_post_key"] = best["key"]
            try:
                db[pv.COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update})
            except Exception as e:  # clé déjà prise (course entre deux passages) : on n'attribue pas
                logger.warning("post déjà attribué (%s) : %s", doc["_id"], e)
                seen["matched"], best = False, None
                update = {"seen_enc": crypto.encrypt_json(seen, aad), "seen_checked_at": now}
                db[pv.COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update})
            doc.update(update)
            title = payload.get("title", "")
            entry = {"id": str(doc["_id"]), "title": title[:80], "status": status,
                     "score": (best or (top[0] if top else {})).get("score", 0),
                     "platform": (best or (top[0] if top else {})).get("platform"),
                     "url": (best or (top[0] if top else {})).get("url")}
            if best:
                if status == pv.APPROVED:
                    record = {"ok": True, "published_at": best.get("posted_at") or now.isoformat(), "platforms": 1,
                              "error": None, "via": "detected_on_social", "platform": best["platform"],
                              "url": best["url"], "score": best["score"], "how": best["how"]}
                    pv._set_status(db, doc, pv.PUBLISHED, {"publish_enc": crypto.encrypt_json(record, aad)})
                    pv._append_audit(db, doc, "detected_published", "social-check",
                                     detail=f"{best['platform']} {best['how']} ({best['score']})")
                    pv._write_sheet_status(doc, pv.PUBLISHED, f"constatée sur {best['platform']}")
                    if notify:
                        _notify_detected(payload, best)
                    result["newly_detected"].append(entry)
                else:
                    pv._append_audit(db, doc, "seen_on_social", "social-check",
                                     detail=f"{best['platform']} {best['how']} ({best['score']})")
                    result["confirmed"].append(entry)
            else:
                if pb["decided_at"]:
                    entry["days_since_decision"] = (now - pb["decided_at"]).days
                result["not_found"].append(entry)
        except Exception as e:
            logger.warning("social-check %s : %s", doc.get("_id"), e)
            result["errors"].append({"id": str(doc.get("_id")), "error": str(e)[:200]})

    db["service_state"].update_one({"_id": "publication_social_check"},
                                   {"$set": {"last_run": now, "posts_examined": len(posts),
                                             "newly_detected": len(result["newly_detected"]),
                                             "not_found": len(result["not_found"])}}, upsert=True)
    logger.info("🔎 Rapprochement RS : %d posts, %d publications vérifiées, %d constatées, %d non trouvées",
                len(posts), result["checked"], len(result["newly_detected"]), len(result["not_found"]))
    return result


def last_run(db=None) -> Optional[Dict[str, Any]]:
    db = db if db is not None else pv._db()
    st = db["service_state"].find_one({"_id": "publication_social_check"})
    if not st:
        return None
    lr = st.get("last_run")
    return {"last_run": lr.isoformat() if isinstance(lr, datetime) else lr,
            "posts_examined": st.get("posts_examined", 0), "newly_detected": st.get("newly_detected", 0),
            "not_found": st.get("not_found", 0)}


def _notify_detected(payload: Dict[str, Any], best: Dict[str, Any]) -> None:
    try:
        if os.getenv("PUBLICATION_VALIDATION_NOTIFY_TELEGRAM", "1").strip() in ("0", "false", "no", "off"):
            return
        from backend.services.telegram_service import send_message
        import html
        title = payload.get("title") or payload.get("text", "")[:60]
        send_message(f"📡 <b>Publication constatée sur {html.escape(str(best.get('platform')))}</b> — {html.escape(title)}\n"
                     f"{html.escape(best.get('how', ''))} · {html.escape(best.get('url') or '')}")
    except Exception as e:
        logger.debug("telegram détection : %s", e)
