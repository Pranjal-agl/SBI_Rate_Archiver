"""
HDFC Bank – USD Cash Buying Rate Scraper
Source: https://www.hdfcbank.com/personal/resources/rates-and-fees/forex-rates
Method: Dynamic PDF URL discovery → pdfplumber extraction
"""

import logging
import os
import re
import tempfile
from typing import Optional

import pdfplumber
import requests
from bs4 import BeautifulSoup

from models import RateRecord

logger = logging.getLogger(__name__)

HDFC_RATES_PAGE = "https://www.hdfcbank.com/personal/resources/rates-and-fees/forex-rates"
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Fallback static URL (updated periodically — less reliable)
HDFC_PDF_FALLBACK = (
    "https://www.hdfcbank.com/content/bbp/repositories/723fb80a-2dde-42a3-9793-"
    "7ae1be57c87f/?path=%2FPersonal%2FHome%2Fcontent%2Frates.pdf"
)


def _discover_pdf_url() -> Optional[str]:
    """
    Scrape HDFC's forex rates page to find the current PDF download link.
    Falls back to the hardcoded URL if discovery fails.
    """
    try:
        resp = requests.get(HDFC_RATES_PAGE, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for any anchor tag whose href points to a PDF
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if href.lower().endswith(".pdf") and "rates" in href.lower():
                # Make absolute if relative
                if href.startswith("http"):
                    return href
                return "https://www.hdfcbank.com" + href

        # Fallback: regex scan the raw HTML for PDF URLs
        matches = re.findall(r'https?://[^\s"\']+rates[^\s"\']*\.pdf', resp.text, re.IGNORECASE)
        if matches:
            return matches[0]

    except Exception as exc:
        logger.warning("HDFC: PDF URL discovery failed: %s", exc)

    logger.warning("HDFC: using fallback PDF URL.")
    return HDFC_PDF_FALLBACK


def _extract_usd_rate_from_pdf(pdf_path: str) -> Optional[float]:
    """
    Parse HDFC's forex PDF and return the USD Cash Buying rate.

    HDFC PDF column layout (typical):
      Currency Name | ISO Code | TT Buy | TT Sell | Cash Buy | Cash Sell | ...
    We locate the USD row and pick Cash Buy (index offset from USD code).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Prefer structured table extraction over raw text
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row and any(cell and "USD" in str(cell) for cell in row):
                            # Find USD cell index
                            for i, cell in enumerate(row):
                                if cell and "USD" in str(cell):
                                    # Cash Buy is typically 2 columns after ISO code
                                    # Try offsets 2, 3, 4 in case layout varies
                                    for offset in (2, 3, 4):
                                        try:
                                            candidate = row[i + offset]
                                            if candidate:
                                                rate = float(str(candidate).replace(",", "").strip())
                                                if 70 < rate < 120:  # sanity check: plausible INR range
                                                    return rate
                                        except (ValueError, IndexError):
                                            continue

                # Fallback: raw text parsing
                text = page.extract_text()
                if not text:
                    continue
                for line in text.splitlines():
                    if "United States Dollar" in line and "USD" in line:
                        parts = line.split()
                        usd_idx = next((i for i, p in enumerate(parts) if p == "USD"), None)
                        if usd_idx is None:
                            continue
                        for offset in range(2, 6):
                            try:
                                rate = float(parts[usd_idx + offset].replace(",", ""))
                                if 70 < rate < 120:
                                    return rate
                            except (ValueError, IndexError):
                                continue
    except Exception as exc:
        logger.error("HDFC: PDF parsing error: %s", exc)

    return None


def fetch_hdfc_rates() -> list[RateRecord]:
    """
    Fetch USD→INR Cash Buying rate from HDFC's daily PDF.

    Returns:
        List with a single RateRecord(bank="HDFC", label="Cash Buying", rate=<float>)
        Empty list on failure.
    """
    pdf_url = _discover_pdf_url()
    if not pdf_url:
        return []

    for attempt in range(1, MAX_RETRIES + 1):
        tmp_path: Optional[str] = None
        try:
            logger.info("HDFC fetch attempt %d/%d — URL: %s", attempt, MAX_RETRIES, pdf_url)
            resp = requests.get(pdf_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            # Validate we actually got a PDF
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not resp.content[:4] == b"%PDF":
                logger.warning("HDFC: response doesn't look like a PDF (Content-Type: %s)", content_type)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            rate = _extract_usd_rate_from_pdf(tmp_path)
            if rate is not None:
                logger.info("HDFC: USD Cash Buying = %.4f", rate)
                return [RateRecord(bank="HDFC", label="Cash Buying", rate=rate)]
            else:
                logger.warning("HDFC attempt %d: could not parse rate from PDF.", attempt)

        except requests.HTTPError as exc:
            logger.error("HDFC attempt %d HTTP error: %s", attempt, exc)
        except Exception as exc:
            logger.error("HDFC attempt %d failed: %s", attempt, exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    logger.error("HDFC: all %d attempts exhausted.", MAX_RETRIES)
    return []
