"""Test : notification radio = résumé IA uniquement, jamais la transcription brute.

Usage : python tests/test_radio_resume.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import backend.services.telegram_service as tg  # noqa: E402
import backend.services.ai_groq_service as ai  # noqa: E402


def check(cond, msg):
    assert cond, msg
    print("  ✓", msg)


RAW = "Bonjour à tous, il est sept heures. " + "Long texte brut de la transcription du journal. " * 200


def main():
    sent = []
    tg.send_message = lambda text, **k: sent.append(text) or True
    tg.BOT_TOKEN, tg.CHAT_ID = "t", "c"

    print("Telegram")
    ok = tg.notify_radio_summary({"_id": "r1", "stream_name": "RCI Journal 7h00", "text": RAW,
                                  "captured_at": "2026-10-27T11:00:00+00:00"})
    check(ok is False and not sent, "sans résumé IA : rien n'est envoyé (plus de transcription brute)")

    tg.notify_radio_summary({
        "_id": "r2", "stream_name": "RCI Journal 7h00", "text": RAW,
        "ai_summary": "• Grève au port & blocages <ce matin>.\n• Coupure d'eau à Goyave.",
        "captured_at": "2026-10-27T11:00:00+00:00", "captured_at_local": "2026-10-27T07:00:00-04:00",
    })
    t = sent[-1]
    check("Grève au port &amp; blocages &lt;ce matin&gt;" in t and "Coupure d'eau" in t, "le résumé IA est envoyé, échappé")
    check("Long texte brut" not in t, "la transcription brute n'est pas dans le message")
    check("⏰ 07:00" in t, "heure locale de Guadeloupe, pas UTC")

    print("Résumé IA")
    seen = {}
    def fake_call_ai(messages, **k):
        seen["user"] = messages[-1]["content"]
        return "• Sujet 1.\n• Sujet 2."
    ai._call_ai = fake_call_ai
    check(ai.summarize_radio_transcription(RAW, "RCI Journal 7h00") == "• Sujet 1.\n• Sujet 2.", "résumé renvoyé")
    check(len(seen["user"]) > 4000, "tout le journal est résumé, pas seulement les 4 000 premiers caractères")
    check(ai.summarize_radio_transcription("[Erreur transcription: quota]") is None,
          "pas de résumé d'une transcription en erreur")
    print("\n✅ TOUS LES TESTS PASSENT")


if __name__ == "__main__":
    main()
