"""
1_event_returns.py

Question
    How much did each biotech stock move around its FDA decision, compared with the
    biotech sector (XBI) and the whole market (SPY)?

Why I did it this way
    A small biotech can jump 20% on a day when the whole sector is up 3%. If I only
    looked at the raw return I would be counting the sector move as a reaction to the
    FDA news. So I subtract the benchmark return over the same days:

        abnormal return = stock return - XBI return      (main)
        abnormal return = stock return - SPY return      (robustness check)

    This assumes the stock moves 1:1 with XBI (beta = 1). 3_market_model.py relaxes
    that assumption and gets the same conclusion.

What it does
    For every event in data/events_verified.csv:
    1. Download daily closes for the stock, SPY and XBI (about 90 days either side).
    2. Find t = the first trading day on or after the market reaction date.
       The reaction date is not always the FDA date: if the company announced after
       the close, the market could only react the next trading day. I checked the
       press release time for these by hand.
    3. Compute three windows (all close-to-close, in trading days):
           pre            t-30 -> t-1    was the news leaking / expected?
           announcement   t-1  -> t+1    the reaction itself (main result)
           post           t+1  -> t+30   does the move continue or reverse?
       The announcement window is two days long so it still catches the reaction if
       my reaction date is off by one day.
    4. Events with no price data (mostly delisted or acquired companies) are written
       to results/skipped_events.csv instead of being silently dropped. This matters
       for survivorship bias (see README).

Input / Output
    data/events_verified.csv  ->  results/event_returns.csv, results/skipped_events.csv

Result
    85 of 93 events have prices. Announcement window vs XBI:
    approvals +7.9% (n=52), CRLs -23.6% (n=33).

Run
    python3 1_event_returns.py
"""

import os
from datetime import timedelta

import pandas as pd
import yfinance as yf

EVENTS = "data/events_verified.csv"
OUT = "results/event_returns.csv"
SKIPPED = "results/skipped_events.csv"
os.makedirs("results", exist_ok=True)


def closes(ticker, start, end):
    s = yf.Ticker(ticker).history(start=start, end=end)["Close"]
    if not s.empty:
        s.index = s.index.tz_localize(None)
    return s


def compute_row(ticker, reaction_date):
    start = reaction_date - timedelta(days=90)
    end = reaction_date + timedelta(days=90)

    stock = closes(ticker, start, end)
    if stock.empty:
        return None
    spy, xbi = closes("SPY", start, end), closes("XBI", start, end)
    if spy.empty or xbi.empty:
        return None

    data = pd.DataFrame({"stock": stock, "spy": spy, "xbi": xbi}).dropna()
    after = data[data.index >= pd.Timestamp(reaction_date)]
    if after.empty:
        return None

    t_day = after.index[0]
    t = data.index.get_loc(t_day)
    if t - 30 < 0 or t + 30 >= len(data):
        return None

    def window(i, j):
        r = (data.iloc[j] - data.iloc[i]) / data.iloc[i] * 100
        return {"raw": r["stock"], "spy": r["stock"] - r["spy"], "xbi": r["stock"] - r["xbi"]}

    row = {"event_trading_day": t_day.date()}
    for name, (i, j) in {"pre": (t - 30, t - 1), "announcement": (t - 1, t + 1), "post": (t + 1, t + 30)}.items():
        w = window(i, j)
        row[f"{name}_raw_return"] = round(w["raw"], 2)
        row[f"{name}_abn_return_spy"] = round(w["spy"], 2)
        row[f"{name}_abn_return_xbi"] = round(w["xbi"], 2)
    return row


events = pd.read_csv(EVENTS)
results, skipped = [], []

for _, e in events.iterrows():
    ticker = str(e["ticker"]).strip()
    info = {"ticker": ticker, "company": e.get("company", ""), "event_date": e.get("event_date", ""),
            "market_reaction_date": e.get("market_reaction_date", "")}
    try:
        reaction = pd.to_datetime(str(e["market_reaction_date"]).strip(), format="%Y-%m-%d")
    except ValueError:
        print(f"{ticker}: bad market_reaction_date '{info['market_reaction_date']}' - skipped")
        skipped.append({**info, "reason": "bad market_reaction_date"})
        continue

    out = compute_row(ticker, reaction)
    if out is None:
        print(f"{ticker} ({e['event_date']} / reaction {e['market_reaction_date']}): no data")
        skipped.append({**info, "reason": "no price data from yfinance"})
        continue

    results.append({
        "ticker": ticker,
        "company": e["company"],
        "drug_name": e.get("drug_name", ""),
        "event_date": e["event_date"],
        "announcement_time": e.get("announcement_time", ""),
        "decision_type": e.get("decision_type", ""),
        "event_direction": e.get("event_direction", ""),
        "market_reaction_date": e["market_reaction_date"],
        "market_cap_group": e["market_cap_group"],
        **out,
    })
    print(f"{ticker} ({e['event_date']} / reaction {e['market_reaction_date']}): "
          f"pre {out['pre_abn_return_xbi']:+.2f}% | announcement {out['announcement_abn_return_xbi']:+.2f}% | "
          f"post {out['post_abn_return_xbi']:+.2f}% vs XBI")

cols = ["ticker", "company", "drug_name", "event_date", "announcement_time", "decision_type", "event_direction",
        "market_reaction_date", "event_trading_day", "market_cap_group"] + \
       [f"{w}_{k}" for w in ["pre", "announcement", "post"] for k in ["raw_return", "abn_return_spy", "abn_return_xbi"]]
df = pd.DataFrame(results, columns=cols)
df.to_csv(OUT, index=False)
pd.DataFrame(skipped).to_csv(SKIPPED, index=False)

print("\n=== Summary ===")
print(f"Events with data: {len(df)} / {len(events)}")
print(f"Avg abnormal return vs XBI | pre {df.pre_abn_return_xbi.mean():+.2f}% | "
      f"announcement {df.announcement_abn_return_xbi.mean():+.2f}% | post {df.post_abn_return_xbi.mean():+.2f}%")
print("\n=== Announcement window vs XBI, by decision type ===")
for dtype, g in df.groupby("decision_type"):
    print(f"  {dtype:<9} mean {g.announcement_abn_return_xbi.mean():+.2f}% | "
          f"median {g.announcement_abn_return_xbi.median():+.2f}% (n={len(g)})")
print(f"\n-> {OUT}, {SKIPPED}")
