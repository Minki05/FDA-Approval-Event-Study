"""
data_build/fetch_approval_candidates.py

Step 1a of building the dataset: list every FDA approval that could be an event.

Why
    My first approval list came from a script that only pulled BLAs (biologics) and
    the first 100 records, so it had about 25 candidates. To get enough approvals I
    needed the full list: both NDAs (drugs) and BLAs, all pages, 2022-2026.

What it does
    Pages through openFDA drugsfda and keeps original approvals (submission type ORIG,
    status AP) in the target years. Writes approval_candidates_raw.csv.

What it deliberately does not do
    Company -> ticker, listed or not, market cap, and the real reaction date. An FDA
    approval date is not the day the market reacted (the company may announce after
    the close), so those were checked by hand from press releases and 8-Ks.

Run (originally from the repo root)
    python3 data_build/fetch_approval_candidates.py            -> approval_candidates_raw.csv
    python3 data_build/fetch_approval_candidates.py --counts   (year counts only)
"""

import sys
import time
import csv
import requests
from collections import Counter

ENDPOINT = "https://api.fda.gov/drug/drugsfda.json"
TARGET_YEARS = {"2022", "2023", "2024", "2025", "2026"}
APP_PREFIXES = ("BLA", "NDA")
PAGE = 100
MAX_PAGES = 60
OUTPUT = "approval_candidates_raw.csv"

MANUAL_COLS = [
    "ticker",
    "market_reaction_date",
    "announcement_time",
    "market_cap_group",
    "alive_ticker",
    "keep_for_v2",
    "exclude_reason",
    "verification_notes",
]

FDA_COLS = [
    "sponsor_name",
    "approval_date",
    "application_number",
    "brand_name",
    "generic_name",
]


def is_target_app(app_num):
    return app_num.startswith(APP_PREFIXES)


def extract_approvals(result):
    app_num = result.get("application_number", "")
    if not is_target_app(app_num):
        return []

    sponsor = result.get("sponsor_name", "")
    products = result.get("products", [])
    brand = products[0].get("brand_name", "") if products else ""
    generic = products[0].get("generic_name", "") if products else ""

    rows = []
    for sub in result.get("submissions", []):
        if sub.get("submission_type") != "ORIG":
            continue
        if sub.get("submission_status") != "AP":
            continue
        date = sub.get("submission_status_date", "")
        year = date[:4] if len(date) >= 4 else ""
        if year not in TARGET_YEARS:
            continue
        rows.append({
            "sponsor_name": sponsor,
            "approval_date": date,
            "application_number": app_num,
            "brand_name": brand,
            "generic_name": generic,
        })
    return rows


def fetch_all():
    rows = []
    skip = 0
    for _ in range(MAX_PAGES):
        params = {"search": "application_number:BLA* OR application_number:NDA*",
                  "limit": PAGE, "skip": skip}
        r = requests.get(ENDPOINT, params=params, timeout=30)
        if r.status_code != 200:
            print(f"stopped at skip={skip}, status={r.status_code}")
            break
        results = r.json().get("results", [])
        if not results:
            break
        for res in results:
            rows.extend(extract_approvals(res))
        skip += PAGE
        time.sleep(0.3)
        if len(results) < PAGE:
            break
    return rows


def main():
    counts_only = "--counts" in sys.argv
    rows = fetch_all()

    years = Counter(r["approval_date"][:4] for r in rows)
    print("Approval candidates by year:")
    for y in sorted(years):
        print(f"  {y}: {years[y]}")
    yr_lo, yr_hi = min(TARGET_YEARS), max(TARGET_YEARS)
    print(f"Total approval candidates ({yr_lo}-{yr_hi}, BLA+NDA, ORIG/AP): {len(rows)}")

    if counts_only:
        return

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FDA_COLS + MANUAL_COLS)
        writer.writeheader()
        for row in rows:
            for col in MANUAL_COLS:
                row.setdefault(col, "")
            writer.writerow(row)
    print(f"-> {OUTPUT} ({len(rows)} rows, waiting for manual verification)")


if __name__ == "__main__":
    main()
