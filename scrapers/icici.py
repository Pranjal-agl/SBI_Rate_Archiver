"""
ICICI Bank – USD Buying/Selling Rate Scraper
Source: https://www.icicibank.com/personal-banking/forex/forex-rates
Method: requests + BeautifulSoup (server-rendered table)
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from models import RateRecord

logger = logging.getLogger(__name__)

ICICI_URL = "https://www.icicibank.com/personal-banking/forex/forex-rates"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
}


def _parse_icici_html(html: str) -> list[RateRecord]:
    """
    Parse ICICI's forex rates page for USD buy/sell rates.
    ICICI renders a table with columns: Currency | TT Buying | TT Selling | ...
    """
    records: list[RateRecord] = []
    soup = BeautifulSoup(html, "html.parser")

    # Find tables on the page
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        header_row = rows[0] if rows else None
        if not header_row:
            continue

        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]
        # Look for a table that has buying/selling columns
        if not any("buy" in h for h in headers):
            continue

        # Find column indices
        buy_idx = next((i for i, h in enumerate(headers) if "buy" in h), None)
        sell_idx = next((i for i, h in enumerate(headers) if "sell" in h), None)

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts:
                continue

            # Check if this row is for USD
            row_text = " ".join(texts).upper()
            if "USD" not in row_text and "US DOLLAR" not in row_text and "UNITED STATES" not in row_text:
                continue

            try:
                if buy_idx is not None and buy_idx < len(texts):
                    buy_rate = float(re.sub(r"[^\d.]", "", texts[buy_idx]))
                    if 70 < buy_rate < 120:
                        records.append(RateRecord(bank="ICICI", label="TT Buying", rate=buy_rate))

                if sell_idx is not None and sell_idx < len(texts):
                    sell_rate = float(re.sub(r"[^\d.]", "", texts[sell_idx]))
                    if 70 < sell_rate < 120:
                        records.append(RateRecord(bank="ICICI", label="TT Selling", rate=sell_rate))

                if records:
                    return records
            except (ValueError, IndexError) as exc:
                logger.debug("ICICI: row parse error: %s | row: %s", exc, texts)

    # Fallback: regex scan raw HTML for USD rates
    # Matches patterns like "83.25" near "USD" text
    usd_blocks = re.findall(
        r"(?:USD|US Dollar|United States Dollar).{0,200}?(\d{2,3}\.\d{2,4})",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    for match in usd_blocks[:2]:  # take at most 2 hits
        try:
            rate = float(match)
            if 70 < rate < 120:
                records.append(RateRecord(bank="ICICI", label="Rate", rate=rate))
        except ValueError:
            pass

    return records


def fetch_icici_rates() -> list[RateRecord]:
    """
    Fetch USD→INR TT Buying and TT Selling rates from ICICI Bank.

    Returns:
        List of RateRecord entries; empty list on complete failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("ICICI fetch attempt %d/%d …", attempt, MAX_RETRIES)
            resp = requests.get(ICICI_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            records = _parse_icici_html(resp.text)
            if records:
                logger.info("ICICI: fetched %d record(s).", len(records))
                return records
            else:
                logger.warning("ICICI attempt %d: no USD records found in response.", attempt)

        except requests.HTTPError as exc:
            logger.error("ICICI attempt %d HTTP %s", attempt, exc.response.status_code)
        except Exception as exc:
            logger.error("ICICI attempt %d failed: %s", attempt, exc)

        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            logger.info("Retrying ICICI in %ds …", backoff)
            time.sleep(backoff)

    logger.error("ICICI: all %d attempts exhausted.", MAX_RETRIES)
    return []
