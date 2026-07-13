import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================================================
# make_charts.py  (v1.1)
#
# v1.0 -> v1.1 changes (reporting layer only; no change to
# how returns are computed in calculate_event_returns.py):
#   - report MEDIAN alongside MEAN for every event window
#   - flag the single biggest-magnitude outlier per window
#   - show a "drop-top-outlier" mean so the small-sample
#     sensitivity is visible instead of hidden
#
# Rationale: with n~8 events, one stock is ~1/8 of every
# average, so a single extreme name can swing the mean.
# median + outlier flag exposes that instead of burying it.
# =========================================================

INPUT_FILE = "event_returns.csv"
OUTPUT_DIR = "charts"

WINDOWS = [
    ("pre",          "pre_abn_return_xbi",          "Pre-event [-30, -1]"),
    ("announcement", "announcement_abn_return_xbi", "Announcement [0, +1]"),
    ("post",         "post_abn_return_xbi",         "Post-event [+2, +30]"),
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(INPUT_FILE)
print(f"Loaded {len(df)} events from {INPUT_FILE}")


# -----------------------------
# Basic column check
# -----------------------------

required_columns = ["ticker", "market_cap_group"] + [c for _, c, _ in WINDOWS]
missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    raise ValueError(f"Missing required columns: {missing_columns}")


# -----------------------------
# Per-window stats with outlier awareness
# -----------------------------

def window_stats(series, tickers):
    """Return mean, median, and the mean after dropping the single
    largest-magnitude value (the dominant outlier in a small sample)."""
    s = series.reset_index(drop=True)
    t = tickers.reset_index(drop=True)

    outlier_pos = s.abs().idxmax()
    outlier_ticker = t.iloc[outlier_pos]
    outlier_value = s.iloc[outlier_pos]

    mean_all = s.mean()
    median_all = s.median()
    mean_drop = s.drop(index=outlier_pos).mean()

    return {
        "mean": mean_all,
        "median": median_all,
        "mean_drop_outlier": mean_drop,
        "outlier_ticker": outlier_ticker,
        "outlier_value": outlier_value,
    }


stats = {}
for key, col, label in WINDOWS:
    stats[key] = window_stats(df[col], df["ticker"])
    stats[key]["label"] = label


# -----------------------------
# Chart 1: Announcement abnormal return by ticker (unchanged)
# -----------------------------

chart_df = df.sort_values("announcement_abn_return_xbi")

plt.figure(figsize=(10, 8))
plt.barh(chart_df["ticker"], chart_df["announcement_abn_return_xbi"])
plt.axvline(x=0, linewidth=0.8)
plt.title("Announcement Window Abnormal Return by Ticker vs XBI")
plt.xlabel("Announcement Abnormal Return vs XBI (%)")
plt.ylabel("Ticker")
plt.tight_layout()
path1 = os.path.join(OUTPUT_DIR, "announcement_abnormal_return_by_ticker.png")
plt.savefig(path1, dpi=300)
plt.close()
print(f"Saved: {path1}")


# -----------------------------
# Chart 2 (v1.1): Mean vs Median by window, grouped bars
# This is the key v1.1 chart — the mean/median gap is the story.
# -----------------------------

labels = [stats[k]["label"] for k, _, _ in WINDOWS]
means = [stats[k]["mean"] for k, _, _ in WINDOWS]
medians = [stats[k]["median"] for k, _, _ in WINDOWS]

x = np.arange(len(labels))
w = 0.38

plt.figure(figsize=(9, 6))
plt.bar(x - w / 2, means, w, label="Mean")
plt.bar(x + w / 2, medians, w, label="Median")
plt.axhline(y=0, linewidth=0.8)
plt.title(f"Abnormal Return by Event Window vs XBI  (n={len(df)})")
plt.xlabel("Event Window")
plt.ylabel("Abnormal Return vs XBI (%)")
plt.xticks(x, labels, rotation=15, ha="right")
plt.legend()

# annotate each window with the outlier that moves the mean
for i, (k, _, _) in enumerate(WINDOWS):
    ot = stats[k]["outlier_ticker"]
    ov = stats[k]["outlier_value"]
    plt.annotate(f"outlier: {ot} ({ov:+.0f}%)",
                 xy=(x[i], max(means[i], medians[i])),
                 xytext=(0, 8), textcoords="offset points",
                 ha="center", fontsize=8, color="gray")

plt.tight_layout()
path2 = os.path.join(OUTPUT_DIR, "mean_median_by_window.png")
plt.savefig(path2, dpi=300)
plt.close()
print(f"Saved: {path2}")


# -----------------------------
# Chart 3 (v1.1): Full sample vs top-outlier-dropped mean
# Makes the small-sample sensitivity explicit.
# -----------------------------

mean_full = [stats[k]["mean"] for k, _, _ in WINDOWS]
mean_drop = [stats[k]["mean_drop_outlier"] for k, _, _ in WINDOWS]

plt.figure(figsize=(9, 6))
plt.bar(x - w / 2, mean_full, w, label="Mean (all events)")
plt.bar(x + w / 2, mean_drop, w, label="Mean (drop top outlier)")
plt.axhline(y=0, linewidth=0.8)
plt.title("Sensitivity of Window Mean to the Single Largest Outlier")
plt.xlabel("Event Window")
plt.ylabel("Mean Abnormal Return vs XBI (%)")
plt.xticks(x, labels, rotation=15, ha="right")
plt.legend()
plt.tight_layout()
path3 = os.path.join(OUTPUT_DIR, "outlier_sensitivity_by_window.png")
plt.savefig(path3, dpi=300)
plt.close()
print(f"Saved: {path3}")


# -----------------------------
# Chart 4: Small vs mid announcement reaction (mean + median)
# -----------------------------

grp = (
    df.groupby("market_cap_group")["announcement_abn_return_xbi"]
    .agg(["mean", "median", "count"])
    .reset_index()
)
grp["label"] = grp["market_cap_group"] + " (n=" + grp["count"].astype(str) + ")"

gx = np.arange(len(grp))
plt.figure(figsize=(7, 6))
plt.bar(gx - w / 2, grp["mean"], w, label="Mean")
plt.bar(gx + w / 2, grp["median"], w, label="Median")
plt.axhline(y=0, linewidth=0.8)
plt.title("Announcement Abnormal Return by Market Cap Group")
plt.xlabel("Market Cap Group")
plt.ylabel("Announcement Abnormal Return vs XBI (%)")
plt.xticks(gx, grp["label"])
plt.legend()
plt.tight_layout()
path4 = os.path.join(OUTPUT_DIR, "market_cap_group_announcement_return.png")
plt.savefig(path4, dpi=300)
plt.close()
print(f"Saved: {path4}")

def chart_asymmetry(df, out_dir, w=0.38):
    appr = df[df["decision_type"] == "APPROVAL"]["announcement_abn_return_xbi"]
    crl  = df[df["decision_type"] == "CRL"]["announcement_abn_return_xbi"]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    bp = ax.boxplot([appr.values, crl.values],
                    tick_labels=[f"APPROVAL (n={len(appr)})", f"CRL (n={len(crl)})"],
                    widths=0.5, patch_artist=True, showmeans=True)
    for patch, c in zip(bp["boxes"], ["#2E7D5B", "#C0392B"]):
        patch.set_facecolor(c); patch.set_alpha(0.35)
    rng = np.random.default_rng(0)
    for i, (vals, c) in enumerate(zip([appr.values, crl.values],
                                      ["#2E7D5B", "#C0392B"]), start=1):
        ax.scatter(rng.normal(i, 0.06, len(vals)), vals,
                   color=c, s=45, alpha=0.8, zorder=3, edgecolor="white")
    ax.axhline(0, color="gray", linewidth=1, linestyle="--")
    ax.set_ylabel("Announcement abnormal return vs XBI (%)")
    ax.set_title("APPROVAL vs CRL asymmetry")
    plt.tight_layout()
    p = os.path.join(out_dir, "approval_vs_crl_asymmetry.png")
    plt.savefig(p, dpi=300); plt.close()
    print(f"Saved: {p}")

chart_asymmetry(df, OUTPUT_DIR)

# -----------------------------
# Summary table
# -----------------------------

print("\n=== Window Summary (v1.1) ===")
print(f"{'window':<22}{'mean':>8}{'median':>9}{'drop-outlier':>14}   outlier")
for k, _, _ in WINDOWS:
    st = stats[k]
    print(f"{st['label']:<22}"
          f"{st['mean']:>+8.2f}"
          f"{st['median']:>+9.2f}"
          f"{st['mean_drop_outlier']:>+14.2f}"
          f"   {st['outlier_ticker']} ({st['outlier_value']:+.1f}%)")

print("\n=== Market Cap Group (announcement) ===")
print(grp[["label", "mean", "median"]].to_string(index=False))

print("\nAll charts saved in the charts/ folder.")
