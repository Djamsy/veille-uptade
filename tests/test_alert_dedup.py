"""Test : anti-doublon des alertes (titre normalisé par regex, stockage en base).

Nécessite mongomock. Usage : python tests/test_alert_dedup.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import mongomock  # noqa: E402

import backend.services.alert_dedup as dd  # noqa: E402


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


def main():
    print("Normalisation")
    check(dd.normalize("Guadeloupe. Feux dans la nuit !") == "feux dans la nuit", "préfixe « Guadeloupe. » et ponctuation retirés")
    check(dd.normalize("FEUX  DANS la nuit") == "feux dans la nuit", "casse et espaces")
    check(dd.normalize("Grève à l’hôpital : réquisitions") == dd.normalize("Greve a l'hopital - requisitions"),
          "accents, apostrophes et ponctuation neutralisés")
    check(dd.normalize("Guadeloupe 1ère : la grève continue") != "la greve continue",
          "« Guadeloupe 1ère » n'est pas pris pour un préfixe de lieu")

    print("Envoi unique")
    db = mongomock.MongoClient()["v"]
    dd._collection = lambda: db["sent_alerts"]
    check(dd.claim("telegram_article", "Guadeloupe. Feux dans la nuit") is True, "1re fois : envoyée")
    check(dd.claim("telegram_article", "Feux dans la nuit") is False, "même annonce reprise par un autre média : bloquée")
    check(dd.claim("email_article", "Feux dans la nuit") is True, "canal différent (e-mail) : envoyée une fois aussi")
    dd._local.clear()  # redémarrage / autre instance : seule la base fait foi
    check(dd.claim("telegram_article", "FEUX DANS LA NUIT") is False, "après redémarrage ou sur une 2e instance : bloquée")
    check(dd.claim("telegram_article", "Faits divers", "https://rci.fm/a") is True
          and dd.claim("telegram_article", "Faits divers", "https://rci.fm/b") is True,
          "titres courts génériques : distingués par leur lien")

    print("Base injoignable")
    def broken():
        raise RuntimeError("base injoignable")
    dd._collection = broken
    dd._local.clear()
    check(dd.claim("telegram_radio", "rci_0700 2026-10-27 07:00") is True
          and dd.claim("telegram_radio", "rci_0700 2026-10-27 07:00") is False,
          "repli sur la mémoire locale, sans bloquer les alertes")
    print("\n✅ TOUS LES TESTS PASSENT")


if __name__ == "__main__":
    main()
