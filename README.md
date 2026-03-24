# 💱 Forex Rate Archiver

> **Automated daily archival of USD → INR exchange rates** from SBI New York, HDFC Bank, and ICICI Bank — with historical analytics dashboard, structured logging, and zero-touch GitHub Actions CI/CD.

[![Daily Forex Scrape](https://github.com/<your-username>/SBI_Rate_Archiver/actions/workflows/daily_scrape.yml/badge.svg)](https://github.com/<your-username>/SBI_Rate_Archiver/actions)
![Python](https://img.shields.io/badge/python-3.11-blue?logo=python)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Overview

This project solves a real-world data problem: Indian banks publish their USD→INR exchange rates daily on their websites, but **none of them expose a historical API**. This archiver bridges that gap by:

1. Scraping three banks using different techniques (Selenium, PDF parsing, HTML parsing)
2. Persisting each day's snapshot to a structured Excel file and an append-only master CSV
3. Automatically running and committing results every day via GitHub Actions
4. Providing a client-side analytics dashboard to visualize trends over time

---

## Features

| Feature | Detail |
|---|---|
| **Multi-bank scraping** | SBI (Selenium/JS), HDFC (dynamic PDF discovery + pdfplumber), ICICI (requests + BeautifulSoup) |
| **Retry logic** | Exponential backoff, up to 3 attempts per bank |
| **Concurrent fetching** | All banks scraped in parallel via `ThreadPoolExecutor` |
| **Deduplication** | Re-runs on the same day never produce duplicate rows |
| **Structured logging** | Console + `archiver.log` with timestamps and severity levels |
| **Graceful partial failure** | Partial failures (exit 2) are distinguished from total failure (exit 1) |
| **GitHub Actions CI** | Daily cron at 04:00 UTC, manual trigger, Chrome setup, artifact upload, auto-commit |
| **Analytics dashboard** | Client-side HTML/JS dashboard — load your CSV, get charts instantly. No server needed. |

---

## Project Structure

```
├── main.py                    # Orchestrator — arg parsing, concurrency, logging
├── models.py                  # RateRecord dataclass (immutable, typed)
├── storage.py                 # Data persistence (Excel + master CSV, deduplication)
├── scrapers/
│   ├── __init__.py
│   ├── sbi.py                 # Selenium scraper for SBI New York
│   ├── hdfc.py                # Dynamic PDF URL discovery + pdfplumber parser
│   └── icici.py              # requests + BeautifulSoup HTML parser
├── dashboard/
│   └── index.html             # Standalone analytics dashboard (no server needed)
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily_scrape.yml   # GitHub Actions CI/CD
├── data/
│   └── <year>/
│       └── forex_rates_YYYY-MM-DD.xlsx   # Daily snapshots
└── all_rates_history.csv      # Master historical record (auto-created)
```

---

## Tech Stack

- **Python 3.11** — core language
- **Selenium 4** + **webdriver-manager** — JS-rendered page scraping (SBI)
- **pdfplumber** — structured PDF table extraction (HDFC)
- **requests** + **BeautifulSoup4** — HTML scraping (ICICI)
- **openpyxl** — formatted Excel output
- **pandas** — CSV management and deduplication
- **GitHub Actions** — daily automation, artifact upload, auto-commit

---

## How It Works

### SBI New York
SBI's exchange rate page renders its table via JavaScript. A headless Chrome instance (via Selenium) loads the page, waits for the DOM to stabilize, then locates the `Remittance Amount` table and extracts all slab → rate pairs.

### HDFC Bank
HDFC publishes rates as a downloadable PDF. Rather than hardcoding the URL (which changes when HDFC updates the file), the scraper **first visits the forex rates page**, scans the HTML for any PDF link containing "rates", and only then downloads and parses it with `pdfplumber`'s table extractor.

### ICICI Bank
ICICI renders its rates as a server-side HTML table. A plain `requests` GET + BeautifulSoup parse is sufficient — no headless browser needed.

---

## Setup

### Local

```bash
git clone https://github.com/<your-username>/SBI_Rate_Archiver.git
cd SBI_Rate_Archiver
pip install -r requirements.txt
python main.py
```

**Options:**
```bash
python main.py --banks sbi hdfc          # fetch specific banks only
python main.py --no-excel                # skip daily Excel, CSV only
```

### GitHub Actions

1. Fork this repo
2. Enable Actions in your fork's Settings → Actions → General
3. The workflow runs automatically every day at **04:00 UTC (9:30 AM IST)**
4. To trigger manually: Actions tab → "Daily Forex Scrape" → "Run workflow"

No secrets or tokens are required — the workflow uses the built-in `GITHUB_TOKEN` to commit data back to the repository.

---

## Output

**Daily Excel** (`data/<year>/forex_rates_YYYY-MM-DD.xlsx`):

| Bank | Slab / Type | USD to INR Rate | Date |
|---|---|---|---|
| SBI | USD 500 - USD 2,500 | 83.2100 | 2025-01-15 |
| HDFC | Cash Buying | 83.1500 | 2025-01-15 |
| ICICI | TT Buying | 83.0900 | 2025-01-15 |

**Master CSV** (`all_rates_history.csv`) — same schema, growing daily, ready for analysis.

---

## Analytics Dashboard

Open `dashboard/index.html` in any browser. Upload your `all_rates_history.csv` to instantly see:

- **KPI cards** — today's average rate per bank, δ vs previous day, days archived
- **Trend chart** — all banks on a single time-series chart
- **Distribution bar chart** — average rate by slab type
- **Bank comparison** — doughnut chart of average rates
- **Recent records table** — filterable by bank, with per-row day-over-day delta

No server, no dependencies, no install — pure client-side HTML/JS.

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | All banks fetched successfully |
| `1` | **Total failure** — no data from any bank (GitHub Action fails) |
| `2` | **Partial failure** — ≥1 bank succeeded, ≥1 failed (Action succeeds with warning) |

---

## License

MIT License. See `LICENSE` for details.
