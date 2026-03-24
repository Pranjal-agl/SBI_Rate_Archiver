"""
Forex Rate Archiver — Main Orchestrator
========================================
Fetches USD→INR exchange rates from SBI, HDFC, and ICICI in parallel,
persists results, and exits with a non-zero code if all sources failed
(so GitHub Actions can surface the failure).

Usage:
    python main.py                    # normal daily run
    python main.py --no-excel         # skip daily Excel (CSV only)
    python main.py --banks sbi hdfc   # fetch specific banks only
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Callable

from models import RateRecord
from scrapers import fetch_hdfc_rates, fetch_icici_rates, fetch_sbi_rates
from storage import append_to_master_csv, save_daily_excel

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("archiver.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── Bank registry ─────────────────────────────────────────────────────────────

BANK_FETCHERS: dict[str, Callable[[], list[RateRecord]]] = {
    "sbi":   fetch_sbi_rates,
    "hdfc":  fetch_hdfc_rates,
    "icici": fetch_icici_rates,
}


# ── Core logic ────────────────────────────────────────────────────────────────

def run_fetchers(banks: list[str]) -> tuple[list[RateRecord], list[str]]:
    """
    Run selected bank fetchers concurrently.

    Returns:
        (all_records, failed_banks)
    """
    all_records: list[RateRecord] = []
    failed: list[str] = []

    fetchers = {bank: BANK_FETCHERS[bank] for bank in banks if bank in BANK_FETCHERS}
    unknown = [b for b in banks if b not in BANK_FETCHERS]
    if unknown:
        logger.warning("Unknown bank(s) requested and skipped: %s", unknown)

    with ThreadPoolExecutor(max_workers=len(fetchers)) as pool:
        futures = {pool.submit(fn): name for name, fn in fetchers.items()}
        for future in as_completed(futures):
            bank_name = futures[future]
            try:
                records = future.result()
                if records:
                    all_records.extend(records)
                    logger.info("✓ %-6s → %d record(s)", bank_name.upper(), len(records))
                else:
                    logger.warning("✗ %-6s → 0 records (scraper returned empty)", bank_name.upper())
                    failed.append(bank_name)
            except Exception as exc:
                logger.error("✗ %-6s → unhandled exception: %s", bank_name.upper(), exc)
                failed.append(bank_name)

    return all_records, failed


def print_summary(records: list[RateRecord]) -> None:
    logger.info("\n%s", "─" * 55)
    logger.info("  %-8s %-22s %s", "BANK", "SLAB / TYPE", "USD → INR")
    logger.info("%s", "─" * 55)
    for r in sorted(records, key=lambda x: (x.bank, x.label)):
        logger.info("  %-8s %-22s ₹ %.4f", r.bank, r.label, r.rate)
    logger.info("%s", "─" * 55)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forex Rate Archiver")
    parser.add_argument(
        "--banks",
        nargs="+",
        default=list(BANK_FETCHERS.keys()),
        help="Banks to fetch (default: all). Choices: sbi hdfc icici",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Skip writing the daily Excel file (CSV only).",
    )
    return parser.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    today = date.today()

    logger.info("=" * 55)
    logger.info("  Forex Rate Archiver  |  %s", today.isoformat())
    logger.info("  Banks: %s", ", ".join(args.banks).upper())
    logger.info("=" * 55)

    records, failed = run_fetchers(args.banks)

    if not records:
        logger.error("❌ No data fetched from any source. Aborting save.")
        return 1  # fail the GitHub Action

    print_summary(records)

    # Persist
    if not args.no_excel:
        save_daily_excel(records, for_date=today)
    append_to_master_csv(records)

    # Partial failure warning (doesn't fail the run, but visible in logs)
    if failed:
        logger.warning("⚠️  Partial failure — these banks returned no data: %s", ", ".join(failed).upper())
        return 2  # non-zero but distinct from "total failure"

    logger.info("✅ All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
