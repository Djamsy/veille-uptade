"""Test fonctionnel du social_snapshot_service avec un faux DB minimal."""
import sys, types
from datetime import datetime, timezone, timedelta
sys.path.insert(0, "/home/user/veille-uptade")


class FakeCursor(list):
    def sort(self, key, direction=1):
        return FakeCursor(sorted(self, key=lambda d: d.get(key) or "", reverse=(direction == -1)))
    def limit(self, n):
        return FakeCursor(self[:n])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []
    def find(self, query=None, projection=None):
        query = query or {}
        out = [d for d in self.docs if self._match(d, query)]
        return FakeCursor(out)
    def find_one(self, query=None, projection=None, sort=None):
        items = self.find(query)
        if sort:
            k, dirn = sort[0]
            items = sorted(items, key=lambda d: d.get(k) or "", reverse=(dirn == -1))
        return items[0] if items else None
    def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if self._match(d, flt):
                d.update(update.get("$set", {}))
                return
        if upsert:
            doc = dict(flt)
            doc.update(update.get("$setOnInsert", {}))
            doc.update(update.get("$set", {}))
            self.docs.append(doc)
    def _match(self, d, query):
        for k, v in query.items():
            if isinstance(v, dict):
                if "$in" in v and d.get(k) not in v["$in"]: return False
                if "$gte" in v and not (d.get(k) and d.get(k) >= v["$gte"]): return False
                if "$gt" in v and not (d.get(k, 0) and d.get(k, 0) > v["$gt"]): return False
            elif d.get(k) != v:
                return False
        return True


class FakeDB:
    def __init__(self):
        self.cols = {}
    def __getitem__(self, name):
        return self.cols.setdefault(name, FakeCollection())


# Monter le faux DB
import backend.services.social_snapshot_service as svc
fake = FakeDB()
# Seed campaign_posts : 2 IG + 1 FB + 1 TikTok
fake.cols["campaign_posts"] = FakeCollection([
    {"platform": "instagram", "stats": {"likes": 100, "comments": 10, "views": 500, "shares": 0}, "created_at": "2026-05-30"},
    {"platform": "instagram", "stats": {"likes": 50, "comments": 5, "views": 200, "shares": 2}, "created_at": "2026-05-29"},
    {"platform": "facebook", "stats": {"likes": 30, "comments": 3, "shares": 7}, "created_at": "2026-05-30"},
    {"platform": "tiktok", "stats": {"likes": 1000, "comments": 50, "views": 9000, "shares": 20}, "author_followers": 4200, "created_at": "2026-05-30"},
])
svc._get_db = lambda: fake

print("=== capture_snapshots() ===")
r = svc.capture_snapshots()
assert r["ok"] and r["captured"] == 3, r
ig = r["platforms"]["instagram"]
assert ig["likes"] == 150 and ig["comments"] == 15 and ig["views"] == 700, ig
assert ig["engagement"] == 150 + 15 + 2, ig  # likes+comments+shares
fb = r["platforms"]["facebook"]
assert fb["engagement"] == 30 + 3 + 7, fb
print("  IG:", ig)
print("  FB:", fb)
print("  TikTok:", r["platforms"]["tiktok"])

print("=== idempotence (re-capture le même jour) ===")
r2 = svc.capture_snapshots()
assert len(fake.cols["account_snapshots"].docs) == 3, "doublon créé !"
print("  OK — toujours 3 snapshots (upsert)")

print("=== capture_followers_weekly() lit author_followers gratuit ===")
rf = svc.capture_followers_weekly()
tk_snap = [d for d in fake.cols["account_snapshots"].docs if d["platform"] == "tiktok"][0]
assert tk_snap.get("followers") == 4200, tk_snap
print("  TikTok followers:", tk_snap["followers"])

print("=== get_history() ===")
h = svc.get_history(days=30)
assert h["ok"] and "instagram" in h["series"], h
print("  séries:", {k: len(v) for k, v in h["series"].items()})

print("=== get_evolution() ===")
e = svc.get_evolution()
assert e["ok"], e
assert e["platforms"]["instagram"]["available"] is True
assert e["platforms"]["instagram"]["delta_engagement_7d"] is None  # 1 seul snapshot
print("  IG evolution:", e["platforms"]["instagram"])

print("=== set_followers() : saisie manuelle, n'écrase pas l'engagement ===")
# Date du jour (= celle utilisée par capture_snapshots) pour viser le même snapshot.
TODAY = svc._today_str()
rfm = svc.set_followers("facebook", 12000, TODAY)
assert rfm["ok"] and rfm["followers"] == 12000, rfm
fb_snap = [d for d in fake.cols["account_snapshots"].docs if d["platform"] == "facebook"][0]
assert fb_snap["followers"] == 12000, fb_snap
assert fb_snap.get("engagement") == 40, "engagement écrasé !"  # préservé
assert fb_snap.get("followers_source") == "manual"
print("  FB snapshot:", {k: fb_snap.get(k) for k in ("engagement", "followers", "followers_source")})

print("=== set_followers() refuse une plateforme inconnue ===")
bad = svc.set_followers("linkedin", 999)
assert bad["ok"] is False, bad
print("  rejet linkedin OK")

print("=== set_web_traffic() : nouvelle source site_web ===")
rweb = svc.set_web_traffic({
    "sessions": 22725, "pageviews": 31992, "users": 17647,
    "new_users": 15804, "avg_session_duration": 26, "bounce_rate": 55.9,
}, TODAY)
assert rweb["ok"] and rweb["metrics"]["sessions"] == 22725, rweb
assert rweb["metrics"]["bounce_rate"] == 55.9, rweb
web_snap = [d for d in fake.cols["account_snapshots"].docs if d["platform"] == "site_web"][0]
assert web_snap["pageviews"] == 31992 and web_snap["source"] == "manual", web_snap
print("  web snapshot:", {k: web_snap.get(k) for k in svc._WEB_METRICS})

print("=== get_web_history() ===")
wh = svc.get_web_history(days=90)
assert wh["ok"] and len(wh["points"]) == 1 and wh["latest"]["sessions"] == 22725, wh
print("  points:", len(wh["points"]), "latest sessions:", wh["latest"]["sessions"])

print("\n✅ TOUS LES TESTS PASSENT")
