"""
SBI New York – Exchange Rate Scraper
Source: https://sbinewyork.statebank/exchange-rate
Method: Selenium (JS-rendered page)
"""

import logging
import time
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from models import RateRecord

logger = logging.getLogger(__name__)

SBI_URL = "https://sbinewyork.statebank/exchange-rate"
PAGE_LOAD_WAIT = 12       # seconds to wait for JS tables to render
TABLE_POLL_TIMEOUT = 20   # WebDriverWait timeout
MAX_RETRIES = 3


def _build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def _parse_tables(driver: webdriver.Chrome) -> list[RateRecord]:
    """Extract all slab → rate rows from the SBI exchange rate table."""
    records: list[RateRecord] = []

    try:
        # Wait until at least one <table> is present in the DOM
        WebDriverWait(driver, TABLE_POLL_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        # Extra buffer for JS to populate all rows
        time.sleep(PAGE_LOAD_WAIT)
    except Exception:
        logger.warning("Timed out waiting for SBI table to appear in DOM.")
        return records

    tables = driver.find_elements(By.TAG_NAME, "table")
    target_table = None

    for table in tables:
        headers = table.find_elements(By.TAG_NAME, "th")
        if any("Remittance Amount" in h.text for h in headers):
            target_table = table
            break

    if target_table is None:
        logger.warning("SBI: target table with 'Remittance Amount' header not found.")
        return records

    rows = target_table.find_elements(By.TAG_NAME, "tr")
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 2:
            continue
        slab = cells[0].text.strip()
        raw_rate = cells[1].text.strip().replace(",", "")
        try:
            rate = float(raw_rate)
            records.append(RateRecord(bank="SBI", label=slab, rate=rate))
        except ValueError:
            logger.debug("SBI: skipping non-numeric cell: %r", raw_rate)

    return records


def fetch_sbi_rates() -> list[RateRecord]:
    """
    Fetch all USD→INR slab rates from SBI New York.
    Retries up to MAX_RETRIES times on failure.

    Returns:
        List of RateRecord(bank="SBI", label=<slab>, rate=<float>)
        Empty list if all attempts fail.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        driver: Optional[webdriver.Chrome] = None
        try:
            logger.info("SBI fetch attempt %d/%d …", attempt, MAX_RETRIES)
            driver = _build_driver()
            driver.get(SBI_URL)
            records = _parse_tables(driver)

            if records:
                logger.info("SBI: fetched %d slab(s).", len(records))
                return records
            else:
                logger.warning("SBI attempt %d: 0 records parsed.", attempt)

        except Exception as exc:
            logger.error("SBI attempt %d failed: %s", attempt, exc)
        finally:
            if driver:
                driver.quit()

        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            logger.info("Retrying SBI in %ds …", backoff)
            time.sleep(backoff)

    logger.error("SBI: all %d attempts exhausted. Returning empty.", MAX_RETRIES)
    return []
