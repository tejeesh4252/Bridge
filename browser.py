# =============================================================================
# BROWSER LIFECYCLE MANAGER
# =============================================================================

import logging
from playwright.sync_api import sync_playwright, Browser, Page

logger = logging.getLogger("BridgeBMO.Browser")


class BrowserManager:
    """
    Manages Playwright browser instance.
    Always runs HEADED - required for RSA token entry.
    """

    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._page: Page       = None

    def launch(self) -> Page:
        """Launch headed Chromium and return page."""
        logger.info("Launching browser...")
        self._playwright = sync_playwright().start()
        self._browser    = self._playwright.chromium.launch(
            headless=False,
            slow_mo=50,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = self._browser.new_context(
            viewport=None,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        self._page = context.new_page()
        logger.info("Browser launched ✅")
        return self._page

    def get_page(self) -> Page:
        return self._page

    def close(self):
        """Clean shutdown."""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
            logger.info("Browser closed")
        except Exception:
            pass

    def is_alive(self) -> bool:
        try:
            self._page.title()
            return True
        except Exception:
            return False
