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

def similarity(pub_title: str, pub_text: str, post_text: str) -> Tuple[float, str]:
    """Renvoie (score 0..1, méthode)."""
    npost = norm_text(post_text)
    if not npost:
        return 0.0, "vide"
    best, how = 0.0, "aucune"
    ntitle = norm_text(pub_title)
    if len(ntitle) >= 12 and ntitle in npost:
        best, how = 0.95, "titre contenu"
    ptok = tokens(f"{pub_title} {pub_text}")
    if len(ptok) >= 4:
        cov = len(ptok & tokens(post_text)) / len(ptok)
        if cov > best:
            best, how = cov, f"mots retrouvés {int(cov * 100)}%"
    a, b = norm_text(f"{pub_title} {pub_text}")[:400], npost[:400]
    if a and b:
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        if ratio > best:
            best, how = ratio, f"ressemblance {int(ratio * 100)}%"
    return round(best, 3), how


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


def check_publications(days: Optional[int] = None, db=None, notify: bool = True) -> Dict[str, Any]:
    """Compare les publications Validée / Publiée aux posts récents des comptes. Marque les
    correspondances ; une publication seulement Validée trouvée en ligne passe en Publiée."""
    db = db if db is not None else pv._db()
    days = days or window_days()
    thr = threshold()
    accounts = own_accounts()
    posts = _candidates(db, days, accounts)
    now = datetime.now(timezone.utc)
    result = {"ok": True, "posts_examined": len(posts), "accounts": accounts, "threshold": thr, "days": days,
              "checked": 0, "newly_detected": [], "confirmed": [], "not_found": [], "errors": []}
    if not posts:
        result["warning"] = "Aucun post récent des comptes dans social_media_posts (scraping RS non lancé, ou comptes non reconnus)"

    query = {"status_idx": {"$in": [crypto.blind_index(pv.APPROVED), crypto.blind_index(pv.PUBLISHED)]}}
    for doc in db[pv.COLLECTION].find(query).sort("updated_at", -1).limit(300):
        try:
            aad = pv._aad(doc["_id"])
            status = crypto.decrypt_str(doc.get("status_enc"), aad)
            payload = crypto.decrypt_json(doc.get("payload_enc"), aad, default={}) or {}
            prev = crypto.decrypt_json(doc.get("seen_enc"), aad, default=None)
            if prev and prev.get("matched"):
                continue  # déjà constatée
            result["checked"] += 1
            title, text = payload.get("title", ""), payload.get("text", "")
            decided_at = (crypto.decrypt_json(doc.get("decision_enc"), aad, default={}) or {}).get("at")
            best: Optional[Dict[str, Any]] = None
            cands = []
            for p in posts:
                if decided_at and p.get("_date"):
                    try:  # un post antérieur à la validation de plus de 2 jours n'est pas celui-ci
                        dd = datetime.fromisoformat(decided_at)
                        if p["_date"] < dd - timedelta(days=2):
                            continue
                    except Exception:
                        pass
                score, how = similarity(title, text, p.get("text", ""))
                if score <= 0.2:
                    continue
                c = {"score": score, "how": how, "platform": p.get("platform"), "url": p.get("url", ""),
                     "author": p.get("author", ""), "posted_at": p["_date"].isoformat() if p.get("_date") else None,
                     "excerpt": (p.get("text") or "")[:160]}
                cands.append(c)
                if best is None or score > best["score"]:
                    best = c
            cands.sort(key=lambda c: -c["score"])
            seen = {"checked_at": now.isoformat(), "matched": bool(best and best["score"] >= thr),
                    "best": best, "candidates": cands[:3], "threshold": thr}
            update = {"seen_enc": crypto.encrypt_json(seen, aad), "seen_checked_at": now}
            if seen["matched"]:
                update["seen_at"] = now
            db[pv.COLLECTION].update_one({"_id": doc["_id"]}, {"$set": update})
            doc.update(update)
            entry = {"id": str(doc["_id"]), "title": title[:80], "status": status,
                     "score": best["score"] if best else 0, "platform": best["platform"] if best else None,
                     "url": best["url"] if best else None}
            if seen["matched"]:
                if status == pv.APPROVED:
                    record = {"ok": True, "published_at": best.get("posted_at") or now.isoformat(),
                              "platforms": 1, "error": None, "via": "detected_on_social",
                              "platform": best["platform"], "url": best["url"], "score": best["score"], "how": best["how"]}
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
                if decided_at:
                    try:
                        entry["days_since_decision"] = (now - datetime.fromisoformat(decided_at)).days
                    except Exception:
                        pass
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
