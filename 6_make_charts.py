"""
6_make_charts.py

Question
    What are the few pictures that tell the story of this project at a glance?

Charts (all abnormal returns vs XBI, saved in charts/)
    1. approval_vs_crl.png
         Every event's announcement-window reaction (t-1 -> t+1), approvals vs CRLs.
         The main result: CRLs fall about 3x more than approvals rise.
    2. windows_by_decision.png
         Mean reaction in the pre / announcement / post windows for each decision
         type, with bootstrap 95% confidence intervals. Shows the reaction is
         concentrated on the announcement days, and CRLs partly recover afterwards.
    3. crl_overreaction.png
         CRLs only: size of the drop vs return over the next 30 days. The dashed line
         is the -30% backtest threshold. Shows the overreaction / rebound pattern.
    4. reaction_by_event.png
         All events sorted by reaction, so the spread and the outliers are visible.

Why these and not more
    Earlier versions pooled approvals and CRLs in the same window chart, which mixes a
    positive and a negative effect into one meaningless average. Every chart here is
    split by decision type. Colors mark the decision type only (blue = approval,
    orange = CRL), not good or bad.

Input / Output
    results/event_returns.csv  ->  charts/*.png

Run
    python3 6_make_charts.py
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

IN = "results/event_returns.csv"
OUT = "charts"
COLOR = {"APPROVAL": "#2a78d6", "CRL": "#eb6834"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
WINDOWS = [("pre_abn_return_xbi", "Pre\n(t-30 to t-1)"),
           ("announcement_abn_return_xbi", "Announcement\n(t-1 to t+1)"),
           ("post_abn_return_xbi", "Post\n(t+1 to t+30)")]
rng = np.random.default_rng(0)

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})

os.makedirs(OUT, exist_ok=True)
for old in ["announcement_abnormal_return_by_ticker.png", "mean_median_by_window.png",
            "outlier_sensitivity_by_window.png", "market_cap_group_announcement_return.png",
            "approval_vs_crl_asymmetry.png"]:
    if os.path.exists(os.path.join(OUT, old)):
        os.remove(os.path.join(OUT, old))

df = pd.read_csv(IN)
groups = {d: df[df.decision_type == d] for d in ["APPROVAL", "CRL"]}


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    print(f"Saved: {path}")


def boot_ci(x, n=10000):
    x = np.asarray(x)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return np.percentile(means, [2.5, 97.5])


fig, ax = plt.subplots(figsize=(6.5, 5.5))
col = "announcement_abn_return_xbi"
for i, (d, g) in enumerate(groups.items(), start=1):
    v = g[col].values
    ax.boxplot(v, positions=[i], widths=0.45, showfliers=False,
               medianprops=dict(color=INK, linewidth=1.5), boxprops=dict(color=MUTED),
               whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED))
    ax.scatter(rng.normal(i, 0.07, len(v)), v, s=36, color=COLOR[d], alpha=0.85,
               edgecolor="white", linewidth=1, zorder=3)
    ax.text(i + 0.3, v.mean(), f"mean {v.mean():+.1f}%\nmedian {np.median(v):+.1f}%",
            va="center", fontsize=9, color=INK)
ax.axhline(0, color=MUTED, linewidth=1)
ax.set_xticks([1, 2], [f"Approval (n={len(groups['APPROVAL'])})", f"CRL (n={len(groups['CRL'])})"])
ax.set_xlim(0.5, 2.9)
ax.set_ylabel("Abnormal return vs XBI, t-1 to t+1 (%)")
ax.set_title("Reaction to FDA decisions: CRLs hurt more than approvals help", loc="left")
save(fig, "approval_vs_crl.png")


fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(WINDOWS))
w = 0.36
for k, (d, g) in enumerate(groups.items()):
    means = [g[c].mean() for c, _ in WINDOWS]
    cis = [boot_ci(g[c].dropna()) for c, _ in WINDOWS]
    err = np.array([[m - lo, hi - m] for m, (lo, hi) in zip(means, cis)]).T
    pos = x + (k - 0.5) * (w + 0.02)
    ax.bar(pos, means, w, color=COLOR[d], label=f"{d.title() if d == 'APPROVAL' else d} (n={len(g)})")
    ax.errorbar(pos, means, yerr=err, fmt="none", ecolor=INK, elinewidth=1, capsize=3)
    for p, m in zip(pos, means):
        ax.text(p + 0.03, m + (0.8 if m >= 0 else -0.8), f"{m:+.1f}%", ha="left",
                va="bottom" if m >= 0 else "top", fontsize=8.5, color=INK)
ax.axhline(0, color=MUTED, linewidth=1)
ax.set_xticks(x, [lbl for _, lbl in WINDOWS])
ax.set_ylabel("Mean abnormal return vs XBI (%)")
ax.set_title("The move happens on the announcement days (bars: mean, lines: 95% CI)", loc="left")
ax.legend(frameon=False, loc="lower left")
save(fig, "windows_by_decision.png")


crl = groups["CRL"]
fig, ax = plt.subplots(figsize=(7.5, 5.5))
ax.scatter(crl.announcement_abn_return_xbi, crl.post_abn_return_xbi, s=48, color=COLOR["CRL"],
           edgecolor="white", linewidth=1, zorder=3)
ax.axvline(-30, color=MUTED, linestyle="--", linewidth=1)
ax.axhline(0, color=MUTED, linewidth=1)
ax.text(-31, ax.get_ylim()[1] * 0.95, "backtest buys here\n(drop of 30% or more)", ha="right", va="top",
        fontsize=8.5, color=MUTED)
for _, r in crl.iterrows():
    if abs(r.post_abn_return_xbi) > 30 or r.announcement_abn_return_xbi < -70:
        ax.annotate(r.ticker, (r.announcement_abn_return_xbi, r.post_abn_return_xbi),
                    xytext=(5, 4), textcoords="offset points", fontsize=8, color=INK)
rho = crl[["announcement_abn_return_xbi", "post_abn_return_xbi"]].corr(method="spearman").iloc[0, 1]
ax.set_xlabel("Reaction to CRL, t-1 to t+1 (%)")
ax.set_ylabel("Next 30 days, t+1 to t+30 (%)")
ax.set_title(f"Bigger CRL drops tend to rebound more (Spearman rho = {rho:.2f}, n = {len(crl)})", loc="left")
save(fig, "crl_overreaction.png")


s = df.sort_values("announcement_abn_return_xbi").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(7, 13))
ax.barh(s.index, s.announcement_abn_return_xbi, color=s.decision_type.map(COLOR), height=0.75)
ax.set_yticks(s.index, s.ticker + np.where(s.decision_type == "CRL", " (CRL)", ""), fontsize=7)
ax.axvline(0, color=MUTED, linewidth=1)
ax.grid(axis="y", visible=False)
ax.set_ylim(-1, len(s))
ax.set_xlabel("Abnormal return vs XBI, t-1 to t+1 (%)")
ax.set_title("Reaction by event", loc="left")
handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR[d]) for d in groups]
ax.legend(handles, ["Approval", "CRL"], frameon=False, loc="lower right")
save(fig, "reaction_by_event.png")

print("\nAll charts saved in charts/")
