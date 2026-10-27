"""Tests : alertes e-mail Brevo + correctifs de la page Articles.

Nécessite mongomock. Usage : python tests/test_brevo_et_articles.py
"""
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.update(BREVO_API_KEY="xkeysib-test", BREVO_SENDER_EMAIL="veille@exemple.fr",
                  EMAIL_ALERT_TO="a@exemple.fr, b@exemple.fr, pas-un-email", EMAIL_DAILY_LIMIT="5")

import backend.services.email_service as mail  # noqa: E402


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, str(body)

    def json(self):
        return self._body


calls = []


def fake_post(url, json=None, timeout=None, headers=None):
    calls.append({"url": url, "json": json, "headers": headers})
    return FakeResp(201, {"messageId": "<id@brevo>"})


mail.requests.post = fake_post


def test_send():
    print("Envoi Brevo")
    calls.clear()
    r = mail.send_email("Sujet", "<p>x</p>", "x")
    c = calls[-1]
    check(r == {"ok": True, "message_id": "<id@brevo>"}, "envoi réussi, messageId renvoyé")
    check(c["url"] == "https://api.brevo.com/v3/smtp/email", "API transactionnelle Brevo v3")
    check(c["headers"]["api-key"] == "xkeysib-test", "clé passée dans l'en-tête api-key")
    check([t["email"] for t in c["json"]["to"]] == ["a@exemple.fr", "b@exemple.fr"],
          "destinataires lus dans EMAIL_ALERT_TO, entrée invalide ignorée")
    check("xkeysib" not in str(mail.status()), "la clé n'apparaît jamais dans le statut")

    print("Plafond quotidien")
    r = mail.send_email("2", "<p>x</p>")   # 2 + 2 = 4 <= 5
    r3 = mail.send_email("3", "<p>x</p>")  # 6 > 5
    check(r["ok"] and not r3["ok"] and r3["error"] == "plafond quotidien atteint",
          "au-delà de EMAIL_DAILY_LIMIT (destinataires compris), plus d'envoi")
    mail._quota.update(day=None, sent=0)

    print("Erreur Brevo")
    mail.requests.post = lambda *a, **k: FakeResp(400, {"message": "sender not valid"})
    r = mail.send_email("x", "<p>x</p>")
    check(not r["ok"] and r["status"] == 400 and "sender not valid" in r["error"], "l'erreur Brevo est remontée")
    mail.requests.post = fake_post
    mail._quota.update(day=None, sent=0)


def test_build_and_modes():
    print("Contenu de l'e-mail")
    arts = [
        {"title": "Routes & ponts <fermés>", "source": "RCI Guadeloupe", "url": "https://rci.fm/a?x=1&y=2",
         "gravity_score": 0.7, "theme": "infrastructures", "content": "Chapô", "content_restricted": True},
        {"title": "Fête", "source": "KaribInfo", "url": "https://karibinfo.com/b", "gravity_score": 0.1},
    ]
    m = mail.build_articles_email(arts)
    check(m["subject"] == "📰 2 nouveaux articles — KaribInfo, RCI Guadeloupe", "sujet : nombre + sources")
    check("Routes &amp; ponts &lt;fermés&gt;" in m["html"], "titres échappés")
    check("https://rci.fm/a?x=1&amp;y=2" in m["html"] and "https://rci.fm/a?x=1&y=2" in m["text"],
          "lien de chaque article, en clair")
    check("Réservé abonnés" in m["html"], "mention « Réservé abonnés »")

    print("Modes")
    calls.clear()
    os.environ["EMAIL_ARTICLE_ALERTS"] = "relevant"
    mail.notify_new_articles(arts)
    time.sleep(0.2)
    check(len(calls) == 1 and len(calls[0]["json"]["htmlContent"].split("<tr>")) == 2,
          "relevant : seul l'article de gravité >= 0.4")
    calls.clear()
    os.environ["EMAIL_ARTICLE_ALERTS"] = "off"
    check(mail.notify_new_articles(arts) is False and not calls, "off : aucun e-mail")
    os.environ.pop("EMAIL_ARTICLE_ALERTS")
    mail._quota.update(day=None, sent=0)


def test_scraper():
    print("Scraper")
    import backend.services.scraper_service as ss
    from backend.services.scraper_service import GuadeloupeScraper

    page = """<html><head><meta property="og:description" content="Le vrai chapô de l'article."></head>
    <body><div class="paywall">Réservé aux abonnés</div>
    <p>Accroche d'un AUTRE article : le Brésil s'est réveillé ce matin avec beaucoup de questions.</p>
    <p>Accroche d'un troisième article sur les experts-comptables réunis à Antigua cette semaine.</p>
    </body></html>"""

    class R:
        content = page.encode()
        def raise_for_status(self): pass

    ss.requests.get = lambda *a, **k: R()
    sc = GuadeloupeScraper.__new__(GuadeloupeScraper)
    sc.headers = {}
    content = sc.extract_article_content("https://x", {"content_selectors": [".article-body"]})
    check(content == "Le vrai chapô de l'article." and sc.last_extraction == "description",
          "article réservé : chapô des métadonnées, pas les accroches d'autres articles")

    body = "<html><body><div class='article-body'><p>" + "Texte éditorial complet de l'article. " * 5 + "</p></div></body></html>"
    R.content = body.encode()
    content = sc.extract_article_content("https://x", {"content_selectors": [".article-body"]})
    check(sc.last_extraction == "body" and content.startswith("Texte éditorial"), "article libre : corps complet")

    print("Un seul e-mail par cycle")
    sent = []
    import backend.services.email_service as em
    em.notify_new_articles = lambda arts: sent.append(len(arts))

    class Col:
        def insert_many(self, docs, ordered=False):
            return None

    sc.articles_collection, sc.db = Col(), None
    sc.sites_config = {"a": {"name": "A"}, "b": {"name": "B"}}
    sc.scrape_site = lambda k, c: [{"title": f"{k}{i}", "source": k, "url": f"u{k}{i}"} for i in range(2)]
    ss.time.sleep = lambda s: None
    sc.scrape_all_sites()
    check(sent == [4], "2 sites × 2 articles -> 1 seul e-mail de 4 articles")


def test_api_total():
    print("API /api/articles")
    import asyncio
    import mongomock
    import backend.server as srv
    col = mongomock.MongoClient()["v"]["articles_guadeloupe"]
    now = datetime.now()
    col.insert_many([{"title": f"r{i}", "scraped_at": now - timedelta(hours=i)} for i in range(35)]
                    + [{"title": "vieux", "scraped_at": now - timedelta(days=10)},
                       {"title": "vieux-str", "scraped_at": (now - timedelta(days=9)).isoformat()},
                       {"title": "recent-str", "scraped_at": (now - timedelta(days=1)).isoformat()}])
    srv.collections["articles_guadeloupe"] = col
    r = asyncio.run(srv.get_articles(limit=30, skip=0, days=7))
    check(r["total"] == 36 and len(r["articles"]) == 30, "total sur 7 jours (36) > 30 : la pagination s'affiche")
    r = asyncio.run(srv.get_articles(limit=30, skip=30, days=7))
    check(len(r["articles"]) == 6, "page 2 : les 6 articles restants")
    r = asyncio.run(srv.get_articles(limit=200, skip=0, days=0))
    check(r["total"] == 38, "days=0 : tout l'historique")


if __name__ == "__main__":
    test_send()
    test_build_and_modes()
    test_scraper()
    test_api_total()
    print("\n✅ TOUS LES TESTS PASSENT")
