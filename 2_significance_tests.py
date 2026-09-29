"""
2_significance_tests.py

Question
    Are the average reactions to approvals and CRLs real, or could they be noise from
    a small sample? And is the CRL drop really bigger than the approval gain?

Why these tests
    Biotech event returns are small-sample and heavy-tailed (one stock can move +80%),
    so I don't rely on the t-test alone. Every result is reported with three things:
        - one-sample t-test          classic test that the mean is 0
        - Wilcoxon signed-rank       rank-based, not driven by a few extreme values
        - bootstrap 95% CI of mean   resample events 10,000 times, no normality needed
    To compare approvals with CRLs I use Welch's t-test (the two groups have very
    different variances) and Mann-Whitney U (rank-based version).

What it tests (announcement window t-1 -> t+1, abnormal return vs XBI)
    [1]  approvals and CRLs separately, and again vs SPY
    [2]  asymmetry: approval mean vs CRL mean
    [3]  approvals split into 2022-23 and 2024-26 (is it stable over time?)
    [4]  sensitivity:
           - drop events contaminated by other news on the same days
             (earnings, stock offerings, financing) that I flagged by hand from 8-Ks
           - novel drugs only (NME / new biologics)
           - CRLs from CDER only (drugs) vs CBER (gene/cell therapies)
           - drop the single largest and smallest value
    [5]  small-cap vs mid-cap
    [6]  pre window  t-30 -> t-1   did the price move before the news?
    [7]  post window t+1 -> t+30   does the reaction continue or reverse?

Input / Output
    results/event_returns.csv, data/events_verified.csv (tags)  ->  results/significance_results.txt

Result
    Approvals +7.9% (p = 0.013), CRLs -23.6% (p = 0.0002), difference p < 0.001.
    Holds vs SPY and without contaminated events. Novel-drug-only approvals are
    borderline (p = 0.054). After large CRL drops, prices tend to partly recover
    (Spearman rho = -0.52 between the drop and the next 30 days), which is what
    5_backtest_crl_rebound.py tests as a strategy.

    I run many subgroup tests here, so a single p < 0.05 in a subgroup should not be
    over-read (multiple comparisons).

Run
    python3 2_significance_tests.py
"""

import numpy as np
import pandas as pd
from scipy import stats

INPUT = "results/event_returns.csv"
TAGS = "data/events_verified.csv"
OUTPUT = "results/significance_results.txt"
MAIN = "announcement_abn_return_xbi"
ROBUST = "announcement_abn_return_spy"
N_BOOT = 10000
rng = np.random.default_rng(42)

lines = []
def out(s=""):
    print(s)
    lines.append(s)


def boot_ci(x, n=N_BOOT):
    x = np.asarray(x)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return np.percentile(means, [2.5, 97.5])


def one_sample(x, label):
    x = pd.Series(x).dropna().values
    if len(x) < 3:
        out(f"  {label:<30} n={len(x)}  (too few events)")
        return
    t, p_t = stats.ttest_1samp(x, 0.0)
    try:
        _, p_w = stats.wilcoxon(x)
    except ValueError:
        p_w = np.nan
    lo, hi = boot_ci(x)
    pos = (x > 0).mean() * 100
    out(f"  {label:<30} n={len(x):>2} | mean {x.mean():+7.2f}% | median {np.median(x):+7.2f}% "
        f"| t={t:+.2f} p={p_t:.4f} | Wilcoxon p={p_w:.4f} | 95% CI [{lo:+.2f}, {hi:+.2f}] | positive {pos:.0f}%")


def two_sample(a, b, la, lb):
    a, b = pd.Series(a).dropna().values, pd.Series(b).dropna().values
    if len(a) < 3 or len(b) < 3:
        out(f"  {la} vs {lb}: too few events")
        return
    _, p_t = stats.ttest_ind(a, b, equal_var=False)
    _, p_u = stats.mannwhitneyu(a, b, alternative="two-sided")
    out(f"  {la} (n={len(a)}, {a.mean():+.2f}%) vs {lb} (n={len(b)}, {b.mean():+.2f}%) "
        f"| diff {a.mean() - b.mean():+.2f}pp | Welch p={p_t:.4f} | Mann-Whitney p={p_u:.4f}")


df = pd.read_csv(INPUT)
df["year"] = pd.to_datetime(df["event_date"]).dt.year
tags = pd.read_csv(TAGS)
for col in ["confounded", "novelty", "center"]:
    if col not in tags:
        tags[col] = ""
df = df.drop(columns=[c for c in ["confounded", "novelty", "center", "market_cap_group"] if c in df]).merge(
    tags[["ticker", "decision_type", "confounded", "novelty", "center", "market_cap_group"]],
    on=["ticker", "decision_type"], how="left")
df["confounded"] = df["confounded"].fillna("").astype(str).str.len() > 0
A = df[df.decision_type == "APPROVAL"]
C = df[df.decision_type == "CRL"]
novel = ["NME", "novel_biologic"]

out("=" * 100)
out("FDA event study - significance tests (announcement window t-1 -> t+1)")
out(f"Sample: {len(A)} approvals + {len(C)} CRLs = {len(df)}")
out("=" * 100)

out("\n[1] Mean abnormal return by decision type (vs XBI, main)")
one_sample(A[MAIN], "APPROVAL")
one_sample(C[MAIN], "CRL")

out("\n[1b] Robustness: vs SPY")
one_sample(A[ROBUST], "APPROVAL (vs SPY)")
one_sample(C[ROBUST], "CRL (vs SPY)")

out("\n[2] Asymmetry: approval vs CRL")
two_sample(A[MAIN], C[MAIN], "APPROVAL", "CRL")
out(f"  |CRL mean| / approval mean = {abs(C[MAIN].mean()) / A[MAIN].mean():.1f}x"
    if A[MAIN].mean() > 0 else "  (approval mean <= 0, ratio skipped)")

out("\n[3] Sub-periods (approvals): 2022-23 vs 2024-26")
early, late = A[A.year <= 2023], A[A.year >= 2024]
one_sample(early[MAIN], "APPROVAL 2022-23")
one_sample(late[MAIN], "APPROVAL 2024-26")
two_sample(early[MAIN], late[MAIN], "2022-23", "2024-26")

out("\n[4] Sensitivity")
flagged = df[df.confounded]
out(f"  Contaminated events: {', '.join(flagged.ticker + '(' + flagged.decision_type.str[0] + ')') or 'none'}")
one_sample(A[~A.confounded][MAIN], "APPROVAL - clean only")
one_sample(C[~C.confounded][MAIN], "CRL - clean only")
one_sample(A[A.novelty.isin(novel)][MAIN], "APPROVAL - novel drugs only")
one_sample(C[C.novelty.isin(novel)][MAIN], "CRL - novel drugs only")
one_sample(C[C.center == "CDER"][MAIN], "CRL - CDER only")
two_sample(C[C.center == "CDER"][MAIN], C[C.center == "CBER"][MAIN], "CRL CDER", "CBER")
two_sample(A[A.novelty.isin(novel)][MAIN], C[C.novelty.isin(novel)][MAIN], "APPROVAL novel", "CRL novel")
one_sample(A[MAIN].sort_values().iloc[1:-1], "APPROVAL - trim max & min")
one_sample(C[MAIN].sort_values().iloc[1:-1], "CRL - trim max & min")

out("\n[5] Market cap group")
for name, g in [("APPROVAL", A), ("CRL", C)]:
    s, m = g[g.market_cap_group == "small"][MAIN], g[g.market_cap_group == "mid"][MAIN]
    one_sample(s, f"{name} small")
    one_sample(m, f"{name} mid")
    two_sample(s, m, f"{name} small", "mid")

out("\n[6] Pre window (t-30 -> t-1): moved before the news?")
one_sample(A["pre_abn_return_xbi"], "APPROVAL pre")
one_sample(C["pre_abn_return_xbi"], "CRL pre")

out("\n[7] Post window (t+1 -> t+30): drift or reversal?")
one_sample(A["post_abn_return_xbi"], "APPROVAL post")
one_sample(C["post_abn_return_xbi"], "CRL post")
r, p = stats.spearmanr(C[MAIN], C["post_abn_return_xbi"])
out(f"  CRL announcement vs post reaction: Spearman rho={r:+.2f} p={p:.4f}  (negative = reversal)")

out("\nNote: small samples and very different volatility across events, so read the t-test together")
out("      with Wilcoxon and the bootstrap CI. Many subgroups are tested, so don't over-read one p < 0.05.")

with open(OUTPUT, "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"\n-> {OUTPUT}")
