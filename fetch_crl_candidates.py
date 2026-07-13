"""
fetch_crl_candidates.py  (v1.2, CRL sourcing step)

WHAT THIS DOES (automated part only):
  Pulls Complete Response Letter (CRL) records from the openFDA
  transparency endpoint and writes a candidate list for the
  2024-2025 window, to time-match the existing approval sample
  (same XBI regime -> clean approval-vs-CRL comparison).

WHAT THIS DOES NOT DO (manual, on purpose):
  - company_name -> stock ticker mapping
  - market_reaction_date verification via 8-K / press release
  - alive-vs-delisted check
  These are left as BLANK columns for you to fill by hand. CRLs are
  frequently disclosed late / vaguely by companies, so letter_date
  is NOT the market reaction date and must not be treated as one.

USAGE:
  python fetch_crl_candidates.py            # writes crl_candidates_raw.csv
  python fetch_crl_candidates.py --counts   # just print year distribution

NOTE ON DATES:
  letter_date comes back as an MM/DD/YYYY string. We do NOT rely on
  the API to range-filter dates (its date indexing on this field is
  unreliable). Instead we page through records and filter by year in
  Python. Slower but correct.
"""

import sys
import time
import csv
import requests
from collections import Counter

ENDPOINT = "https://api.fda.gov/transparency/crl.json"
TARGET_YEARS = {"2024", "2025"}
PAGE = 1000            # max allowed per call
OUTPUT = "crl_candidates_raw.csv"

# columns you will fill in by hand during manual verification
MANUAL_COLS = [
    "ticker",                 # company_name -> ticker (manual)
    "market_reaction_date",   # from 8-K / press release (manual)
    "announcement_time",      # pre_market / market_hours / after_hours (manual)
    "market_cap_group",       # small / mid (manual)
    "alive_ticker",           # yes / no  (does yfinance have it?)
    "keep_for_v2",            # yes / no
    "exclude_reason",         # e.g. delisted, acquired, no-clear-disclosure
    "verification_notes",
]

# columns coming straight from openFDA (the automated part)
FDA_COLS = [
    "company_name",
    "letter_date",
    "application_number",
    "product_type",     # NDA vs BLA if present
    "file_name",
]


def parse_year(letter_date):
    # "10/05/2018" -> "2018"; be defensive about odd formats
    s = str(letter_date).strip()
    if "/" in s and len(s.split("/")) == 3:
        return s.split("/")[-1]
    if "-" in s and len(s.split("-")[0]) == 4:  # ISO fallback
        return s.split("-")[0]
    return ""


def fetch_all():
    """Page through the entire CRL dataset. It's small enough
    (a few hundred records) that pulling all of it is fine."""
    records = []
    skip = 0
    while True:
        params = {"limit": PAGE, "skip": skip}
        r = requests.get(ENDPOINT, params=params, timeout=30)
        if r.status_code == 404:
            break  # openFDA returns 404 when skip runs past the end
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            break
        records.extend(results)
        print(f"  fetched {len(records)} records...")
        if len(results) < PAGE:
            break
        skip += PAGE
        time.sleep(0.3)  # be polite
    return records


def print_counts(records):
    years = Counter(parse_year(rec.get("letter_date", "")) for rec in records)
    print("\n=== CRL count by letter_date year ===")
    for yr in sorted(years, reverse=True):
        marker = "  <-- target" if yr in TARGET_YEARS else ""
        print(f"  {yr or '(unparsed)'}: {years[yr]}{marker}")
    print(f"  TOTAL: {len(records)}")


def get_first(rec, *keys):
    """openFDA sometimes nests fields or returns lists; grab a scalar."""
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

    # filter to target years
    target = [r for r in records if parse_year(r.get("letter_date", "")) in TARGET_YEARS]
    print(f"\n{len(target)} records in {sorted(TARGET_YEARS)}")

    # write candidate CSV: FDA fields populated, manual fields blank
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
