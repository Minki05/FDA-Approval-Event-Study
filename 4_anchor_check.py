"""
4_anchor_check.py

Question
    Does my result depend on how I chose each event's reaction day?

Why I checked this
    The approval sample was built in two ways:
      - manual rows: I read each press release time and moved after-hours news to the
        next trading day
      - automated rows (marked 'auto-built' in the notes): reaction day = FDA approval date
    Mixing two rules could bias the result. So I recompute every approval with one
    single rule (reaction day = FDA approval date) and compare.

What it does
    1. For every approval, compute the announcement-window return vs XBI
       (t-1 close -> t+1 close) twice: with my recorded reaction day and with the
       FDA date rule.
    2. List the manual rows where the two days differ and how much the return changes.
    3. Test both versions, and check if the per-event differences are systematic
       (Wilcoxon on the differences) and how similar the rankings are (Spearman).
       This file only compares; it does not change any data.

Input / Output
    data/events_verified.csv  ->  results/anchor_check.txt, results/anchor_check.csv

Result
    Recorded rule +7.6% vs FDA-date rule +6.6%, both significant (t-test p = 0.016 / 0.030).
    Rank correlation 0.97, differences not systematic (Wilcoxon p = 0.21).
    So the result is robust to the reaction-day definition. Individual events can still
    move a lot (e.g. MDGL, RIGL) because the two windows cover different days.

Run
    python3 4_anchor_check.py
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

lines = []
def out(s=""):
    print(s)
    lines.append(s)


def closes(tk, start, end):
    s = yf.Ticker(tk).history(start=start, end=end)["Close"]
    if not s.empty:
        s.index = s.index.tz_localize(None).normalize()
    return s


def ann_abn(stock, xbi, react):
    px = pd.DataFrame({"s": stock, "m": xbi}).dropna()
    after = px.index[px.index >= pd.Timestamp(react)]
    if len(after) == 0:
        return np.nan
    t = px.index.get_loc(after[0])
    if t - 1 < 0 or t + 1 >= len(px):
        return np.nan
    r = px.iloc[t + 1] / px.iloc[t - 1] - 1
    return (r["s"] - r["m"]) * 100


def test(x, label):
    x = pd.Series(x).dropna().values
    _, p = stats.ttest_1samp(x, 0)
    _, pw = stats.wilcoxon(x)
    out(f"  {label:<34} n={len(x)} | mean {x.mean():+6.2f}% | median {np.median(x):+6.2f}% | t p={p:.4f} | Wilcoxon p={pw:.4f}")


v = pd.read_csv("data/events_verified.csv")
a = v[v.decision_type == "APPROVAL"].copy()
a["auto"] = a.verification_notes.fillna("").str.contains("auto-built")
a["event_date"] = pd.to_datetime(a.event_date)
a["react_rec"] = pd.to_datetime(a.market_reaction_date)

lo = (a.event_date.min() - pd.Timedelta(days=15)).date()
hi = (a.event_date.max() + pd.Timedelta(days=20)).date()
xbi = closes("XBI", lo, hi)

rows = []
for _, e in a.iterrows():
    s = closes(e.ticker, (e.event_date - pd.Timedelta(days=15)).date(), (e.event_date + pd.Timedelta(days=20)).date())
    if s.empty:
        continue
    rows.append(dict(ticker=e.ticker, auto=e.auto, event_date=e.event_date.date(), react_recorded=e.react_rec.date(),
                     same_day=e.react_rec.normalize() == e.event_date.normalize(),
                     abn_recorded=ann_abn(s, xbi, e.react_rec), abn_fda_anchor=ann_abn(s, xbi, e.event_date)))
r = pd.DataFrame(rows).dropna(subset=["abn_recorded", "abn_fda_anchor"])
r.to_csv("results/anchor_check.csv", index=False)

manual = r[~r.auto]
moved = manual[~manual.same_day]
out("=" * 100)
out("Reaction-day check: recorded reaction day vs FDA-date rule (approvals, vs XBI, t-1 -> t+1)")
out("=" * 100)
out(f"{len(r)} approvals, {len(manual)} manual rows, {len(moved)} of them with reaction day != FDA date")
for _, x in moved.iterrows():
    out(f"  {x.ticker:<6} FDA {x.event_date} -> recorded {x.react_recorded} | recorded {x.abn_recorded:+7.2f}% | "
        f"FDA rule {x.abn_fda_anchor:+7.2f}% | diff {x.abn_fda_anchor - x.abn_recorded:+6.2f}pp")

out("\n[All approvals] result under each rule")
test(r.abn_recorded, "Recorded (manual + auto mixed)")
test(r.abn_fda_anchor, "FDA-date rule for all")
rho, p = stats.spearmanr(r.abn_recorded, r.abn_fda_anchor)
out(f"  Rank correlation between rules: Spearman rho={rho:.3f} (p={p:.3g})")
_, pp = stats.wilcoxon(r.abn_recorded - r.abn_fda_anchor) if (r.abn_recorded != r.abn_fda_anchor).any() else (0, 1.0)
out(f"  Wilcoxon on per-event differences p={pp:.4f}  (large = no systematic difference)")

out("\nNote: the FDA-date window [date-1, date+1] still contains the next-day reaction to after-hours news,")
out("      so if both rules give similar results the finding is robust to the reaction-day definition.")
open("results/anchor_check.txt", "w").write("\n".join(lines) + "\n")
print("\n-> results/anchor_check.txt, results/anchor_check.csv")
