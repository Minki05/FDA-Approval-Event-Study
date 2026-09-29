"""
data_build/find_crl_edgar.py

Step 1c: find CRLs from what companies disclosed at the time, using SEC EDGAR.

Why
    The FDA CRL database is biased before 2024 (see fetch_crl_candidates.py). A company
    that receives a CRL usually has to disclose it in an 8-K, whether or not the drug
    is approved later. Searching 8-Ks gives a list without look-ahead bias.

What it does
    1. EDGAR full-text search for 8-Ks containing "complete response letter".
    2. Download each document and keep it only if it has a sentence saying the company
       received a CRL (regex), dropping boilerplate like risk-factor text and mentions
       of old CRLs.
    3. Keep the earliest filing per company and estimate the reaction day from the
       filing time.
    4. Add ticker, market cap at t-1 and foreign-filer status, and sort into buckets.
       Only rows marked CANDIDATE were reviewed by hand.

Run (originally from the repo root)
    python3 data_build/find_crl_edgar.py 2022 2023   -> crl_candidates_edgar_2022_2023.csv
    python3 data_build/find_crl_edgar.py 2024 2026   (used to cross-check recent CRLs)
    First run takes 5-15 minutes; responses are cached in .cache/.
"""

import re
from datetime import timedelta

import pandas as pd

import sec_utils as su

import sys
Y0, Y1 = (sys.argv[1], sys.argv[2]) if len(sys.argv) == 3 else ("2022", "2023")
START, END = f"{Y0}-01-01", f"{Y1}-12-31"
QUERY = '"complete response letter"'
OUT = f"crl_candidates_edgar_{Y0}_{Y1}.csv"

STRONG = re.compile(
    r"(?:ha[sd]|have)?\s*(?:received|issued|issuance of)\s+(?:a|an|the)\s+"
    r"complete\s+response\s+letter|complete\s+response\s+letter\s*\(\s*[\"“]?crl[\"”]?\s*\)\s+"
    r"(?:from|was issued|has been issued)", re.I)
HISTORIC = re.compile(r"previously|in 20(?:1\d|2[01])|prior complete response|second complete|resubmi", re.I)
APPNO = re.compile(r"\b(NDA|BLA)\)?\s*(?:No\.?|#|number)?\s*(\d{6})\b", re.I)


def doc_url(cik, hit_id):
    adsh, fname = hit_id.split(":", 1)
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{fname}"


def main():
    hits = su.fts_search(QUERY, START, END, forms="8-K,6-K", max_hits=3000)
    print(f"Full-text search: {len(hits)} documents")

    rows = []
    for n, h in enumerate(hits, 1):
        s = h["_source"]
        dns = s.get("display_names", [])
        if not dns:
            continue
        name, tk, cik = su.parse_display_name(dns[0])
        if not cik:
            continue
        txt = su.get_text(doc_url(cik, h["_id"]))
        m = STRONG.search(txt)
        if not m:
            continue
        a, b = max(0, m.start() - 250), min(len(txt), m.end() + 250)
        snip = txt[a:b]
        hist = bool(HISTORIC.search(txt[max(0, m.start() - 120):m.end() + 40]))
        app = APPNO.search(txt)
        rows.append(dict(company=name, ticker=tk, cik=cik, file_date=s.get("file_date"), form=s.get("form"),
                         adsh=h["_id"].split(":")[0], url=doc_url(cik, h["_id"]),
                         application_number=f"{app.group(1).upper()} {app.group(2)}" if app else "",
                         historic_mention=hist, snippet=snip))
        if n % 100 == 0:
            print(f"  ...checked {n}/{len(hits)} documents, real CRL sentences {len(rows)}")

    df = pd.DataFrame(rows)
    if df.empty:
        print("No candidates")
        return
    df["file_date"] = pd.to_datetime(df["file_date"])
    df = df.sort_values(["cik", "historic_mention", "file_date"])
    first = df.groupby("cik", as_index=False).first()
    print(f"Companies with a real CRL sentence: {len(first)}")

    out = []
    for _, r in first.iterrows():
        base, subs = su.submissions(r.cik)
        acc = None
        if not subs.empty:
            m = subs[subs.accessionNumber == r.adsh]
            if len(m):
                acc = su.parse_acceptance(m.iloc[0].acceptanceDateTime)
        react = su.reaction_day_from_time(acc) if acc else su.next_trading_day_on_or_after(r.file_date)
        fpi, country = su.is_foreign_filer(subs, base) if base else (False, "")
        tk = r.ticker or ""
        mcap = grp = None
        if tk and react is not None:
            t1 = su.shift_tday(react, -1)
            px = su.raw_close(tk, t1)
            sh, _, _ = su.shares_outstanding_asof(r.cik, t1)
            mcap = px * sh if (px and sh) else None
            grp = su.cap_group(mcap)
        if not tk:
            bucket = "NO_TICKER"
        elif fpi:
            bucket = "FOREIGN?"
        elif mcap is None:
            bucket = "NO_PRICE(delisted?)"
        elif grp == "large":
            bucket = "LARGE"
        else:
            bucket = "CANDIDATE"
        out.append(dict(bucket=bucket, company=r.company, ticker=tk, cik=r.cik,
                        filing_time_et=acc.strftime("%Y-%m-%d %H:%M") if acc else "",
                        session=su.session_label(acc) if acc else "",
                        implied_reaction=react.date() if react is not None else "",
                        mcap_t1_musd=round(mcap / 1e6, 1) if mcap else "", cap_group=grp or "",
                        foreign_filer=fpi, country=country, application_number=r.application_number,
                        historic_mention=r.historic_mention, url=r.url, snippet=r.snippet))
        print(f"{bucket:<20} {tk:<6} {str(out[-1]['implied_reaction']):<11} {out[-1]['mcap_t1_musd']}M  {r.company[:40]}")

    res = pd.DataFrame(out).sort_values(["bucket", "implied_reaction"])
    res.to_csv(OUT, index=False)
    print(f"\n{res.bucket.value_counts().to_dict()}")
    print(f"-> {OUT}")
    print("   Check CANDIDATE rows by hand: is it a new CRL, which drug, NME or not, other news on the same day")


if __name__ == "__main__":
    main()
