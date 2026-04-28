"""
ICICI Bank – USD Buying/Selling Rate Scraper
Source: https://www.icicibank.com/personal-banking/forex/forex-rates
Method: Selenium (site blocks plain requests with 403)
"""

import logging
import re
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

ICICI_URL = "https://www.icicibank.com/personal-banking/forex/forex-rates"
PAGE_LOAD_WAIT = 10
TABLE_POLL_TIMEOUT = 25
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
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # Suppress automation flags that trigger bot detection
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def _parse_rates(driver: webdriver.Chrome) -> list[RateRecord]:
    records: list[RateRecord] = []

    try:
        WebDriverWait(driver, TABLE_POLL_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        time.sleep(PAGE_LOAD_WAIT)
    except Exception:
        logger.warning("ICICI: timed out waiting for table.")
        return records

    tables = driver.find_elements(By.TAG_NAME, "table")
    for table in tables:
        html = table.get_attribute("outerHTML")
        headers_el = table.find_elements(By.TAG_NAME, "th")
        headers = [h.text.strip().lower() for h in headers_el]

        if not any("buy" in h for h in headers):
            continue

        buy_idx = next((i for i, h in enumerate(headers) if "buy" in h), None)
        sell_idx = next((i for i, h in enumerate(headers) if "sell" in h), None)

        rows = table.find_elements(By.TAG_NAME, "tr")
        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            texts = [c.text.strip() for c in cells]
            if not texts:
                continue

            row_text = " ".join(texts).upper()
            if "USD" not in row_text and "US DOLLAR" not in row_text and "UNITED STATES" not in row_text:
                continue

            try:
                if buy_idx is not None and buy_idx < len(texts):
                    buy_val = re.sub(r"[^\d.]", "", texts[buy_idx])
                    if buy_val:
                        buy_rate = float(buy_val)
                        if 70 < buy_rate < 120:
                            records.append(RateRecord(bank="ICICI", label="TT Buying", rate=buy_rate))

                if sell_idx is not None and sell_idx < len(texts):
                    sell_val = re.sub(r"[^\d.]", "", texts[sell_idx])
                    if sell_val:
                        sell_rate = float(sell_val)
                        if 70 < sell_rate < 120:
                            records.append(RateRecord(bank="ICICI", label="TT Selling", rate=sell_rate))

                if records:
                    return records
            except (ValueError, IndexError) as exc:
                logger.debug("ICICI: row parse error: %s | row: %s", exc, texts)

    # Fallback: regex on full page source
    page_src = driver.page_source
    usd_blocks = re.findall(
        r"(?:USD|US Dollar|United States Dollar).{0,200}?(\d{2,3}\.\d{2,4})",
        page_src,
        re.IGNORECASE | re.DOTALL,
    )
    for match in usd_blocks[:2]:
        try:
            rate = float(match)
            if 70 < rate < 120:
                records.append(RateRecord(bank="ICICI", label="Rate", rate=rate))
        except ValueError:
            pass

    return records


def fetch_icici_rates() -> list[RateRecord]:
    for attempt in range(1, MAX_RETRIES + 1):
        driver: Optional[webdriver.Chrome] = None
        try:
            logger.info("ICICI fetch attempt %d/%d …", attempt, MAX_RETRIES)
            driver = _build_driver()
            driver.get(ICICI_URL)
            records = _parse_rates(driver)

            if records:
                logger.info("ICICI: fetched %d record(s).", len(records))
                return records
            else:
                logger.warning("ICICI attempt %d: 0 records found.", attempt)

        except Exception as exc:
            logger.error("ICICI attempt %d failed: %s", attempt, exc)
        finally:
            if driver:
                driver.quit()

        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            logger.info("Retrying ICICI in %ds …", backoff)
            time.sleep(backoff)

    logger.error("ICICI: all %d attempts exhausted.", MAX_RETRIES)
    return []
