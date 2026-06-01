# backend/services/report_render_service.py
"""
Rendu serveur du bilan hebdomadaire en PNG via navigateur headless.

Le bilan est dessiné par du code Canvas (frontend). Pour le produire sans
intervention humaine (job du lundi), on charge la page de rendu hors-écran
`/report/render` dans Chromium (Playwright), on attend le PNG, puis on le
récupère.

Dépendances runtime :
  - `playwright` (pip) + navigateur Chromium installé
    (`python -m playwright install chromium`).
  - FRONTEND_URL — URL publique du front (ex. https://veille.example.com).

Tout est défensif : si Playwright/Chromium ou FRONTEND_URL manquent, la
fonction renvoie None et l'appelant retombe sur le digest texte.
"""

import os
import base64
import logging
from typing import Optional

logger = logging.getLogger("veille.report_render")

FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
RENDER_TIMEOUT_MS = int(os.getenv("REPORT_RENDER_TIMEOUT_MS", "60000"))


async def render_weekly_png(days: int = 7) -> Optional[bytes]:
    """Rend le bilan hebdomadaire en PNG. Renvoie les octets ou None."""
    if not FRONTEND_URL:
        logger.warning("FRONTEND_URL non défini — rendu PNG serveur ignoré")
        return None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright non installé — rendu PNG serveur indisponible")
        return None

    url = f"{FRONTEND_URL}/report/render?days={days}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = await browser.new_page(
                    viewport={"width": 900, "height": 1400},
                    device_scale_factor=2,
                )
                await page.goto(url, wait_until="networkidle", timeout=RENDER_TIMEOUT_MS)
                # Attendre que le canvas ait produit le dataURL (ou une erreur).
                await page.wait_for_function(
                    "() => window.__REPORT_PNG__ || window.__REPORT_ERROR__",
                    timeout=RENDER_TIMEOUT_MS,
                )
                err = await page.evaluate("() => window.__REPORT_ERROR__ || null")
                if err:
                    logger.warning(f"Rendu bilan: erreur côté page: {err}")
                    return None
                data_url = await page.evaluate("() => window.__REPORT_PNG__ || null")
            finally:
                await browser.close()

        if not data_url or "," not in data_url:
            return None
        return base64.b64decode(data_url.split(",", 1)[1])

    except Exception as e:
        logger.warning(f"Rendu PNG serveur échoué: {e}")
        return None
