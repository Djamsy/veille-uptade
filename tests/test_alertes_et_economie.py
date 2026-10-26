"""Tests : alertes Telegram par article + mode économie OpenAI.

Usage : python tests/test_alertes_et_economie.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ["TELEGRAM_SEND_INTERVAL_S"] = "0.01"
os.environ["TELEGRAM_BOT_TOKEN"] = "test"
os.environ["TELEGRAM_CHAT_ID"] = "-100"

from pymongo.errors import BulkWriteError  # noqa: E402

import backend.services.telegram_service as tg  # noqa: E402


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


sent = []
tg.send_message = lambda text, **k: sent.append(text) or True
tg.BOT_TOKEN, tg.CHAT_ID = "test", "-100"


def wait_sent(n, timeout=3):
    deadline = time.time() + timeout
    while len(sent) < n and time.time() < deadline:
        time.sleep(0.01)


def test_message_html():
    print("Message Telegram")
    sent.clear()
    tg.notify_new_article({
        "_id": "a1", "title": "Routes & ponts : <urgent>", "source": "RCI",
        "url": "https://x.fr/a?b=1&c=2", "gravity_score": None, "elected": ["A & B"],
        "ai_summary": "é" * 199 + "&",
    })
    t = sent[-1]
    check("Routes &amp; ponts : &lt;urgent&gt;" in t, "le titre est échappé pour le mode HTML")
    check("🔗 https://x.fr/a?b=1&amp;c=2" in t and "href" not in t, "le lien de l'article est affiché en clair")
    check("A &amp; B" in t, "les entités sont échappées")
    check("&amp;</i>" in t, "le résumé est coupé avant d'être échappé (pas d'entité tronquée)")
    check("Gravité : 0%" in t, "une gravité absente ne fait pas planter le message")
    check(tg.notify_new_article({"_id": "a1", "title": "x"}) is False, "le même article n'est pas alerté deux fois")


def test_queue():
    print("File d'envoi à débit limité")
    sent.clear()
    for i in range(5):
        tg.enqueue_message(f"m{i}")
    wait_sent(5)
    check(sent == [f"m{i}" for i in range(5)], "les messages partent tous, dans l'ordre")


def test_modes():
    print("Modes d'alerte")
    for value, expected in [(None, "all"), ("relevant", "relevant"), ("off", "off"), ("n'importe quoi", "all")]:
        if value is None:
            os.environ.pop("TELEGRAM_ARTICLE_ALERTS", None)
        else:
            os.environ["TELEGRAM_ARTICLE_ALERTS"] = value
        check(tg.article_alerts_mode() == expected, f"TELEGRAM_ARTICLE_ALERTS={value!r} -> {expected}")
    os.environ.pop("TELEGRAM_ARTICLE_ALERTS", None)


def test_scraper_inserted_only():
    print("Scraper : alerte uniquement pour les articles réellement insérés")
    from backend.services.scraper_service import GuadeloupeScraper

    class FakeCollection:
        def insert_many(self, docs, ordered=False):
            for i, d in enumerate(docs):
                d["_id"] = f"id{i}"
            # Le 1er et le 3e sont des doublons (index unique)
            raise BulkWriteError({"writeErrors": [{"index": 0}, {"index": 2}], "nInserted": 2})

    scraper = GuadeloupeScraper.__new__(GuadeloupeScraper)
    scraper.articles_collection = FakeCollection()
    scraper.db = None
    scraper.sites_config = {"rci": {"name": "RCI"}}
    scraper.scrape_site = lambda k, c: [{"title": f"T{i}", "source": "RCI", "url": f"u{i}"} for i in range(4)]

    import backend.services.scraper_service as ss
    ss.time.sleep = lambda s: None
    sent.clear()
    tg._sent_cache.clear()
    res = scraper.scrape_all_sites()
    wait_sent(2)
    titles = sorted(t.split("<b>")[2].split("</b>")[0] for t in sent)
    check(res["articles_saved"] == 2, "2 articles comptés comme sauvegardés")
    check(titles == ["T1", "T3"], "alertes pour T1 et T3, pas pour les doublons T0 et T2")

    os.environ["TELEGRAM_ARTICLE_ALERTS"] = "relevant"
    sent.clear()
    tg._sent_cache.clear()
    scraper.scrape_all_sites()
    time.sleep(0.2)
    check(sent == [], "en mode relevant, pas d'alerte à l'enregistrement")
    os.environ.pop("TELEGRAM_ARTICLE_ALERTS", None)


def test_predictive_switch():
    print("Analyse prédictive")
    from backend.services import ai_groq_service as ai
    os.environ.pop("PREDICTIVE_ANALYSIS_ENABLED", None)
    check(ai.predictive_enabled() is False, "désactivée par défaut")
    check(ai.analyze_trends_predictive([{"title": "x", "gravity_score": 1}]) is None,
          "aucun appel IA quand elle est désactivée")
    os.environ["PREDICTIVE_ANALYSIS_ENABLED"] = "true"
    check(ai.predictive_enabled() is True, "réactivable avec PREDICTIVE_ANALYSIS_ENABLED=true")
    os.environ.pop("PREDICTIVE_ANALYSIS_ENABLED", None)

    import asyncio
    from backend.services.scheduler_service import job_predictive_analysis
    res = asyncio.run(job_predictive_analysis())
    check(res == {"status": "skip", "reason": "disabled"}, "la tâche planifiée est ignorée")


def test_radio_allowlist():
    print("Radio : liste de flux")
    from backend.services.radio_service import RadioTranscriptionService
    svc = RadioTranscriptionService.__new__(RadioTranscriptionService)
    svc.streams = {
        "rci_0700": {"enabled": True, "duration_minutes": 20},
        "rci_1300": {"enabled": True, "duration_minutes": 30},
        "gp_radio_1200": {"enabled": True, "duration_minutes": 20},
    }
    os.environ.pop("RADIO_STREAMS", None)
    svc._apply_stream_allowlist()
    check(all(c["enabled"] for c in svc.streams.values()), "sans RADIO_STREAMS : tous les flux restent actifs")
    os.environ["RADIO_STREAMS"] = "rci_0700, gp_radio_1200, inconnu"
    svc._apply_stream_allowlist()
    active = sorted(k for k, c in svc.streams.items() if c["enabled"])
    check(active == ["gp_radio_1200", "rci_0700"], "seuls les flux listés restent actifs")
    os.environ.pop("RADIO_STREAMS", None)


if __name__ == "__main__":
    test_message_html()
    test_queue()
    test_modes()
    test_scraper_inserted_only()
    test_predictive_switch()
    test_radio_allowlist()
    print("\n✅ TOUS LES TESTS PASSENT")
