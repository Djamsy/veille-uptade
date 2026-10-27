"""Test : sélection des liens d'articles (KaribInfo, doublons, menus).

Usage : python tests/test_scraper_liens.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import backend.services.scraper_service as ss  # noqa: E402
from backend.services.scraper_service import GuadeloupeScraper  # noqa: E402

HOME = """<html><body>
<nav><h2><a href="https://www.karibinfo.com/actualite/societe/">Société</a></h2></nav>
<h3><a href="https://www.karibinfo.com/actualite/karib-itw/">Karib' ITW</a></h3>
<article>
  <a href="https://www.karibinfo.com/news/guadeloupe-feux-dans-la-nuit/"><img src="x.jpg"></a>
  <h2><a href="https://www.karibinfo.com/news/guadeloupe-feux-dans-la-nuit/">Guadeloupe. Feux dans la nuit</a></h2>
  <a href="https://www.karibinfo.com/news/guadeloupe-feux-dans-la-nuit/#comments">Lire la suite</a>
</article>
<article>
  <h2><a href="/news/guadeloupe-pas-deau-aujourdhui/">Guadeloupe. Pas d'eau aujourd'hui</a></h2>
</article>
</body></html>"""


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


class R:
    def __init__(self, html):
        self.content = html.encode()
    def raise_for_status(self):
        pass


def main():
    print("KaribInfo : liens d'articles")
    ss.requests.get = lambda url, *a, **k: R(HOME if url.endswith("karibinfo.com/") else
                                            "<html><head><meta property='og:description' content='Chapô KaribInfo.'></head></html>")

    class Col:
        def find_one(self, *a, **k):
            return None

    sc = GuadeloupeScraper.__new__(GuadeloupeScraper)
    sc.headers, sc.articles_collection = {}, Col()
    sc.clean_title = lambda t: t
    import inspect
    src = inspect.getsource(GuadeloupeScraper.__init__)
    check("a[href*='/news/']" in src, "KaribInfo cible les liens /news/")

    config = {"name": "KaribInfo", "url": "https://www.karibinfo.com/",
              "selectors": ["a[href*='/news/']"],
              "content_selectors": [".entry-content", ".post-content", "article"],
              "base_url": "https://www.karibinfo.com"}
    ss.infer_tags_and_theme = lambda a: {"theme": "general", "gravity_score": 0.1}
    arts = sc.scrape_site("karibinfo", config)
    titles = [a["title"] for a in arts]
    check(titles == ["Guadeloupe. Feux dans la nuit", "Guadeloupe. Pas d'eau aujourd'hui"],
          "2 articles, sans menus, rubriques, image ni « Lire la suite »")
    check(arts[1]["url"] == "https://www.karibinfo.com/news/guadeloupe-pas-deau-aujourdhui",
          "lien relatif complété en adresse absolue")
    print("\n✅ TOUS LES TESTS PASSENT")


if __name__ == "__main__":
    main()
