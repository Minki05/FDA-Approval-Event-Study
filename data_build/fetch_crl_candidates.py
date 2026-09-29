"""
data_build/fetch_crl_candidates.py

Step 1b: list Complete Response Letters (CRLs) for 2024-2026.

Why
    CRLs are the bad-news contrast group. The FDA started publishing CRLs through
    openFDA, so for recent years I can pull them directly.

What it does
    Pages through the openFDA CRL endpoint, keeps letters dated 2024-2026 (filtered
    by year in Python because the API's date filter on letter_date was unreliable),
    and writes crl_candidates_raw.csv.

Important limitation
    For letters before 2024 this database mostly contains drugs that were approved
    later. Using it for 2022-23 would be look-ahead bias (I would only see CRLs with
    a happy ending). That is why 2022-23 CRLs come from find_crl_edgar.py instead.

What it deliberately does not do
    Ticker mapping and the reaction date. The letter date is not the day the market
    found out; companies often disclose days later. Checked by hand.

Run (originally from the repo root)
    python3 data_build/fetch_crl_candidates.py            -> crl_candidates_raw.csv
    python3 data_build/fetch_crl_candidates.py --counts
"""

import sys
import time
import csv
import requests
from collections import Counter

ENDPOINT = "https://api.fda.gov/transparency/crl.json"
TARGET_YEARS = {"2024", "2025", "2026"}
PAGE = 1000
OUTPUT = "crl_candidates_raw.csv"

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
    "company_name",
    "letter_date",
    "application_number",
    "product_type",
    "file_name",
]


def parse_year(letter_date):
    s = str(letter_date).strip()
    if "/" in s and len(s.split("/")) == 3:
        return s.split("/")[-1]
    if "-" in s and len(s.split("-")[0]) == 4:
        return s.split("-")[0]
    return ""


def fetch_all():
    records = []
    skip = 0
    while True:
        params = {"limit": PAGE, "skip": skip}
        r = requests.get(ENDPOINT, params=params, timeout=30)
        if r.status_code == 404:
            break
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            break
        records.extend(results)
        print(f"  fetched {len(records)} records...")
        if len(results) < PAGE:
            break
        skip += PAGE
        time.sleep(0.3)
    return records


def print_counts(records):
    years = Counter(parse_year(rec.get("letter_date", "")) for rec in records)
    print("\n=== CRL count by letter_date year ===")
    for yr in sorted(years, reverse=True):
        marker = "  <-- target" if yr in TARGET_YEARS else ""
        print(f"  {yr or '(unparsed)'}: {years[yr]}{marker}")
    print(f"  TOTAL: {len(records)}")


def get_first(rec, *keys):
    for k in keys:
        v = rec.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if v:
            return v
    return ""


def main():
    counts_only = "--counts" in sys.argv

    print(f"Fetching CRL records from {ENDPOINT} ...")
    records = fetch_all()
    print(f"Total CRL records pulled: {len(records)}")

    print_counts(records)
    if counts_only:
        return

    target = [r for r in records if parse_year(r.get("letter_date", "")) in TARGET_YEARS]
    print(f"\n{len(target)} records in {sorted(TARGET_YEARS)}")

    header = FDA_COLS + MANUAL_COLS
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for rec in sorted(target, key=lambda r: parse_year(r.get("letter_date", ""))):
            row = {
                "company_name": get_first(rec, "company_name"),
                "letter_date": get_first(rec, "letter_date"),
                "application_number": get_first(rec, "application_number"),
                "product_type": get_first(rec, "product_type", "letter_type"),
                "file_name": get_first(rec, "file_name"),
            }
            for c in MANUAL_COLS:
                row[c] = ""
            w.writerow(row)

    print(f"\nWrote {len(target)} candidates to {OUTPUT}")
    print("Next: fill in ticker / market_reaction_date / alive_ticker by hand.")
    print("Remember: letter_date != market reaction date. Verify each via 8-K / press release.")


if __name__ == "__main__":
    main()
