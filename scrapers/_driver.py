"""
Shared Selenium Chrome driver factory.

Uses the system chromedriver (installed by browser-actions/setup-chrome in CI,
or whatever is on PATH locally). Avoids ChromeDriverManager entirely so
concurrent scraper threads don't race on the same cache directory.
"""

import logging
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def build_driver(*, stealth: bool = False) -> webdriver.Chrome:
    """
    Build a headless Chrome driver.

    Args:
        stealth: suppress automation flags (helps with basic bot detection).

    Returns:
        webdriver.Chrome instance. Caller must call .quit() when done.

    Raises:
        RuntimeError: if chromedriver is not found on PATH.
    """
    chromedriver_path = shutil.which("chromedriver")
    if chromedriver_path is None:
        raise RuntimeError(
            "chromedriver not found on PATH. "
            "Install it or run the GitHub Actions workflow which sets it up via setup-chrome."
        )

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"user-agent={_UA}")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    if stealth:
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=opts)

    if stealth:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )

    return driver
