"""
5_backtest_crl_rebound.py

Question
    2_significance_tests.py showed that the harder a stock falls on a CRL, the more it
    tends to recover over the next 30 days (overreaction). Could someone have made
    money from that, and does it survive the obvious objections?

The rule (uses only information known at the time of the trade)
    If a stock's abnormal return vs XBI from t-1 close to t+1 close is -30% or worse,
    buy at the t+1 close and sell at the t+30 close, while shorting the same dollar
    amount of XBI so only the stock-specific move counts.
        trade return = post_abn_return_xbi (t+1 -> t+30 vs XBI) - 1% round-trip cost

What it checks
    [0] the signal itself: Spearman correlation between the drop and the next 30 days
    [1] thresholds -20 / -30 / -40% x costs 0.5 / 1 / 2%, plus the trade list
        -> is the result just one lucky parameter choice?
    [2] out-of-sample: pick the threshold on 2022-24 only, apply it unchanged to 2025-26
        -> overfitting check
    [3] survivorship stress: 7 CRL companies have no price data (acquired or delisted,
        listed in data/survivorship.csv). Add them as -100% and -50% trades.
        -100% is an extreme worst case: they did trade during the 30-day window,
        and not all of them would have hit the -30% signal.
    [4] placebo: same stocks, 2-day drops of -30% or worse at least 60 trading days
        away from the CRL. If these rebound just as much, the effect is "small biotechs
        bounce after crashes", not something special about CRLs.
    [5] without the XBI hedge, for reference

Input / Output
    results/event_returns.csv, data/survivorship.csv
      ->  results/backtest_results.txt, results/backtest_trades.csv

Result
    In-sample it looks strong: 14 trades, mean +16.4%, median +11.7%, 11 of 14 winners
    (p = 0.02), and it barely changes with 2% costs.
    But I don't call it a tradable strategy:
      - out-of-sample 2025-26 mean +15.8%, but only 8 trades, p = 0.18
      - with the missing CRLs at -100% the mean turns negative (-22.7%)
      - non-CRL crashes rebound +4.7%; the CRL rebound is larger but the difference
        is not significant (Mann-Whitney p = 0.11)
    Conclusion: the overreaction pattern is real in this sample, but n is too small and
    survivorship is too important to claim an exploitable anomaly.

Run
    python3 5_backtest_crl_rebound.py      ([4] downloads prices, a few minutes)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

THRESHOLDS = [20, 30, 40]
COSTS = [0.5, 1.0, 2.0]
MAIN_X, MAIN_COST = 30, 1.0
HOLD = 29
rng = np.random.default_rng(42)

lines = []
def out(s=""):
    print(s)
    lines.append(s)


def stats_line(r, label):
    r = pd.Series(r).dropna().values
    if len(r) < 3:
        out(f"  {label:<36} n={len(r)} (too few trades)")
        return
    _, p_t = stats.ttest_1samp(r, 0)
    try:
        _, p_w = stats.wilcoxon(r)
    except ValueError:
        p_w = np.nan
    boot = rng.choice(r, size=(10000, len(r)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    out(f"  {label:<36} n={len(r):>2} | mean {r.mean():+6.1f}% | median {np.median(r):+6.1f}% | win {(r > 0).mean()*100:3.0f}% "
        f"| worst {r.min():+6.1f}% | best {r.max():+6.1f}% | t p={p_t:.3f} | Wilcoxon p={p_w:.3f} | 95% CI [{lo:+.1f}, {hi:+.1f}]")


ev = pd.read_csv("results/event_returns.csv")
crl = ev[ev.decision_type == "CRL"].copy()
crl["year"] = pd.to_datetime(crl.event_date).dt.year
crl["ann"] = crl.announcement_abn_return_xbi
crl["post"] = crl.post_abn_return_xbi
crl["post_raw"] = crl.post_raw_return

out("=" * 110)
out("CRL rebound backtest  (buy t+1 close -> sell t+30 close, hedged with XBI)")
out(f"{len(crl)} CRL events with prices")
out("=" * 110)

rho, p = stats.spearmanr(crl.ann, crl.post)
out(f"\n[0] Signal: announcement reaction vs next 30 days, Spearman rho={rho:.2f} (p={p:.4f})")

out("\n[1] Threshold x cost (return per trade vs XBI, after costs)")
for x in THRESHOLDS:
    sel = crl[crl.ann <= -x]
    for c in COSTS:
        stats_line(sel.post - c, f"buy if <= -{x}%, cost {c}%")
    out("")
stats_line(crl[crl.ann > -MAIN_X].post - MAIN_COST, f"(compare) CRLs that fell less than {MAIN_X}%")

main = crl[crl.ann <= -MAIN_X].copy()
main["net"] = main.post - MAIN_COST
main.sort_values("event_date")[["ticker", "event_date", "ann", "post", "net", "post_raw"]].to_csv(
    "results/backtest_trades.csv", index=False)
out(f"\n  Trades under the main rule (-{MAIN_X}%, cost {MAIN_COST}%) -> results/backtest_trades.csv")
for _, t in main.sort_values("event_date").iterrows():
    out(f"    {t.ticker:<6} {t.event_date}  reaction {t.ann:+6.1f}%  ->  next 30 days {t.post:+6.1f}%")

out("\n[2] Out-of-sample: choose the threshold on 2022-24, apply it to 2025-26")
train, test = crl[crl.year <= 2024], crl[crl.year >= 2025]
cands = [x for x in THRESHOLDS if (train.ann <= -x).sum() >= 3]
best = max(cands, key=lambda x: (train[train.ann <= -x].post - MAIN_COST).mean()) if cands else MAIN_X
if not cands:
    out(f"  (fewer than 3 trades per threshold in 2022-24 -> use main threshold -{MAIN_X}%)")
out(f"  Threshold chosen on 2022-24: -{best}%")
stats_line(train[train.ann <= -best].post - MAIN_COST, f"train 2022-24 (-{best}%)")
stats_line(test[test.ann <= -best].post - MAIN_COST, f"test 2025-26 (-{best}%)")

out("\n[3] Survivorship stress: assume every missing CRL was traded")
try:
    sv = pd.read_csv("data/survivorship.csv")
    miss = sv[sv.decision_type.astype(str).str.startswith("CRL")]
    out(f"  {len(miss)} missing CRLs: {', '.join(miss.ticker)}")
    for loss in [-100, -50]:
        r = np.concatenate([main.net.values, np.full(len(miss), loss - MAIN_COST)])
        stats_line(r, f"missing CRLs added at {loss}%")
    out("  Note: some of these ended in acquisitions at a premium, so -100% is the worst case; the truth is in between.")
except FileNotFoundError:
    out("  data/survivorship.csv not found -> skipped")

out(f"\n[4] Placebo: same stocks, non-CRL 2-day drops of -{MAIN_X}% or worse, next {HOLD} days vs XBI")
try:
    lo = (pd.to_datetime(crl.event_date).min() - pd.Timedelta(days=400)).date()
    hi = (pd.to_datetime(crl.event_date).max() + pd.Timedelta(days=60)).date()
    xbi = yf.Ticker("XBI").history(start=lo, end=hi)["Close"]
    xbi.index = xbi.index.tz_localize(None).normalize()
    plac = []
    for _, e in crl.iterrows():
        s = yf.Ticker(e.ticker).history(start=lo, end=hi)["Close"]
        if s.empty:
            continue
        s.index = s.index.tz_localize(None).normalize()
        px = pd.DataFrame({"s": s, "m": xbi}).dropna()
        ed = pd.Timestamp(e.event_trading_day)
        if ed not in px.index:
            continue
        k = px.index.get_loc(ed)
        two = (px.s / px.s.shift(2) - px.m / px.m.shift(2)) * 100
        fwd = (px.s.shift(-HOLD) / px.s - px.m.shift(-HOLD) / px.m) * 100
        pos = np.arange(len(px))
        ok = (two <= -MAIN_X).values & (np.abs(pos - k) > 60) & fwd.notna().values
        last = -10**9
        for j in np.where(ok)[0]:
            if j - last > HOLD:
                plac.append(fwd.iloc[j] - MAIN_COST)
                last = j
    stats_line(plac, "placebo (non-CRL crashes)")
    stats_line(main.net, "CRL crashes (main rule)")
    if len(plac) >= 3 and len(main) >= 3:
        _, p = stats.mannwhitneyu(main.net, plac, alternative="two-sided")
        out(f"  CRL vs non-CRL rebound: Mann-Whitney p={p:.3f}  (large = can't call it a CRL-specific effect)")
except Exception as err:
    out(f"  placebo failed ({err}) -> skipped")

out("\n[5] Reference: stock only, no XBI hedge")
stats_line(main.post_raw - MAIN_COST, f"<= -{MAIN_X}%, unhedged")

out("\nNote: fewer than 20 trades, so p-values are only indicative. The question is whether the result")
out("      survives costs, survivorship and the placebo, not whether one p-value is below 0.05.")
open("results/backtest_results.txt", "w").write("\n".join(lines) + "\n")
print("\n-> results/backtest_results.txt, results/backtest_trades.csv")
