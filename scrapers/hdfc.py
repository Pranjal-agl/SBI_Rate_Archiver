"""
HDFC Bank – USD Cash Buying Rate Scraper
Source: https://www.hdfcbank.com/personal/resources/rates-and-fees/forex-rates
Method: Selenium (requests/PDF approach blocked by Cloudflare on GitHub Actions IPs)
"""

import logging
import re
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from models import RateRecord
from scrapers._driver import build_driver

logger = logging.getLogger(__name__)

HDFC_URL = "https://www.hdfcbank.com/personal/resources/rates-and-fees/forex-rates"
PAGE_LOAD_WAIT = 12
TABLE_POLL_TIMEOUT = 25
MAX_RETRIES = 3


def _parse_rates(driver) -> list[RateRecord]:
    records: list[RateRecord] = []

    try:
        WebDriverWait(driver, TABLE_POLL_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(PAGE_LOAD_WAIT)
    except Exception:
        logger.warning("HDFC: timed out waiting for table.")

    tables = driver.find_elements(By.TAG_NAME, "table")
    for table in tables:
        rows = table.find_elements(By.TAG_NAME, "tr")
        headers = []
        for row in rows[:3]:
            ths = row.find_elements(By.TAG_NAME, "th")
            tds = row.find_elements(By.TAG_NAME, "td")
            header_cells = ths or tds
            if header_cells:
                headers = [c.text.strip().lower() for c in header_cells]
                break

        cash_buy_idx = next(
            (i for i, h in enumerate(headers) if "cash" in h and "buy" in h), None
        )
        if cash_buy_idx is None:
            cash_buy_idx = next((i for i, h in enumerate(headers) if "buy" in h), None)

        if cash_buy_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            texts = [c.text.strip() for c in cells]
            if not texts:
                continue

            row_text = " ".join(texts).upper()
            if "USD" not in row_text and "US DOLLAR" not in row_text and "UNITED STATES" not in row_text:
                continue

            try:
                val = re.sub(r"[^\d.]", "", texts[cash_buy_idx])
                if val:
                    rate = float(val)
                    if 70 < rate < 120:
                        records.append(RateRecord(bank="HDFC", label="Cash Buying", rate=rate))
                        return records
            except (ValueError, IndexError) as exc:
                logger.debug("HDFC: row parse error: %s | row: %s", exc, texts)

    # Fallback: regex on page source
    page_src = driver.page_source
    usd_blocks = re.findall(
        r"(?:USD|US Dollar|United States Dollar).{0,300}?(\d{2,3}\.\d{2,4})",
        page_src,
        re.IGNORECASE | re.DOTALL,
    )
    for match in usd_blocks[:3]:
        try:
            rate = float(match)
            if 70 < rate < 120:
                records.append(RateRecord(bank="HDFC", label="Cash Buying", rate=rate))
                return records
        except ValueError:
            pass

    return records


def fetch_hdfc_rates() -> list[RateRecord]:
    for attempt in range(1, MAX_RETRIES + 1):
        driver = None
        try:
            logger.info("HDFC fetch attempt %d/%d …", attempt, MAX_RETRIES)
            driver = build_driver(stealth=True)
            driver.get(HDFC_URL)
            records = _parse_rates(driver)

            if records:
                logger.info("HDFC: USD Cash Buying = %.4f", records[0].rate)
                return records
            else:
                logger.warning("HDFC attempt %d: 0 records found.", attempt)

        except Exception as exc:
            logger.error("HDFC attempt %d failed: %s", attempt, exc)
        finally:
            if driver:
                driver.quit()

        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            logger.info("Retrying HDFC in %ds …", backoff)
            time.sleep(backoff)

    logger.error("HDFC: all %d attempts exhausted.", MAX_RETRIES)
    return []
