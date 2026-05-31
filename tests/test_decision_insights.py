"""Test fonctionnel de get_decision_insights (campaign_service) avec faux DB."""
import sys
from datetime import datetime, timezone
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
        return FakeCursor([d for d in self.docs if self._match(d, query)])
    def find_one(self, query=None, projection=None, sort=None):
        items = list(self.find(query))
        if sort:
            k, dirn = sort[0]
            items = sorted(items, key=lambda d: d.get(k) or "", reverse=(dirn == -1))
        return items[0] if items else None
    def _match(self, d, query):
        for k, v in query.items():
            if isinstance(v, dict):
                if "$gte" in v and not (d.get(k) and d.get(k) >= v["$gte"]): return False
                if "$ne" in v and d.get(k) == v["$ne"]: return False
            elif d.get(k) != v:
                return False
        return True


class FakeDB:
    def __init__(self):
        self.cols = {}
    def __getitem__(self, name):
        return self.cols.setdefault(name, FakeCollection())


import backend.services.campaign_service as cs
fake = FakeDB()
now = datetime.now(timezone.utc).isoformat()

fake.cols["campaign_posts"] = FakeCollection([
    {"_id": "p1", "title": "Plage de Sainte-Anne", "published_at": now, "media_type": "video",
     "campaign_name": "Tourisme", "stats": {"views": 9000, "likes": 800, "comments": 120, "shares": 40},
     "platform_stats": {"instagram": {"views": 6000}, "tiktok": {"views": 3000}},
     "sentiment": {"global": "positif", "score": 0.82},
     "comments_scraped": [{"author": "ml", "text": "Superbe !", "likes": 5}]},
    {"_id": "p2", "title": "Conseil municipal", "published_at": now, "media_type": "photo",
     "campaign_name": "Institutionnel", "stats": {"views": 1200, "likes": 30, "comments": 5, "shares": 1},
     "platform_stats": {"facebook": {"views": 1200}}},
    {"_id": "p3", "title": "Festival", "published_at": now, "media_type": "carousel",
     "campaign_name": "Culture", "stats": {"views": 4500, "likes": 300, "comments": 60, "shares": 20},
     "platform_stats": {"instagram": {"views": 4500}}},
])
fake.cols["campaigns"] = FakeCollection([
    {"_id": "c1", "name": "Tourisme", "analyzed_at": now, "ai_analysis": {
        "sentiment": {"global": "positif", "score": 0.8},
        "performance": {"best_format": "video", "best_platform": "instagram", "best_time": "18:00", "best_day": "samedi", "engagement_rate": 0.06},
        "recommendations": ["Publier plus de vidéos", "Poster le samedi soir", "Miser sur Instagram", "(4e ignorée)"],
        "summary": "Bonne dynamique portée par la vidéo.",
    }},
])
cs._get_db = lambda: fake

print("=== get_decision_insights() ===")
r = cs.get_decision_insights(days=7, db=fake)
assert r["ok"], r

# top_post = le plus vu (p1, 9000 vues)
assert r["top_post"]["_id"] == "p1", r["top_post"]
assert r["top_post"]["platform"] == "instagram", r["top_post"]  # plateforme la plus vue
assert r["top_post"]["engagement"] == 800 + 120 + 40, r["top_post"]
assert r["top_post"]["top_comments"][0]["text"] == "Superbe !"
print("  top_post:", r["top_post"]["title"], "-", r["top_post"]["stats"]["views"], "vues, plateforme", r["top_post"]["platform"])

# top_posts = 3 triés par vues : p1, p3, p2
assert [p["_id"] for p in r["top_posts"]] == ["p1", "p3", "p2"], r["top_posts"]
print("  top_posts:", [p["title"] for p in r["top_posts"]])

# totaux
assert r["totals"]["posts"] == 3 and r["totals"]["views"] == 14700, r["totals"]
print("  totals:", r["totals"])

# what_works depuis l'IA
assert r["what_works"]["best_format"] == "video", r["what_works"]
assert r["what_works"]["best_platform"] == "instagram"
print("  what_works:", r["what_works"]["best_format"], "/", r["what_works"]["best_platform"], "/", r["what_works"]["best_day"])

# sentiment + reco (max 3)
assert r["sentiment"]["global"] == "positif"
assert len(r["recommendations"]) == 3, r["recommendations"]
print("  sentiment:", r["sentiment"], "| reco:", len(r["recommendations"]))

print("\n✅ TOUS LES TESTS PASSENT")
