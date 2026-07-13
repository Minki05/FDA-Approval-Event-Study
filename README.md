# FDA Decision Event Study (Approvals + CRLs)

## Project Overview

This project analyzes stock price reactions around FDA decision announcements for publicly traded biotechnology companies. The goal is to measure whether FDA decisions are associated with abnormal returns relative to a biotechnology sector benchmark, and — as of v1.2 — whether the market reacts **asymmetrically** to good news (approvals) versus bad news (Complete Response Letters, "CRLs").

This version uses two manually verified samples:

- **Approvals** — a pilot sample of FDA novel drug approvals (positive events).
- **CRLs** — a contrast group of Complete Response Letters (negative events), where the FDA declines to approve a drug in its current form.

Because both samples are small, the project reports both mean and median for every window and explicitly checks how sensitive each average is to a single outlier.

## Data

The event dataset was constructed from FDA decision records and manually verified using company press releases, newswire announcements, and SEC 8-K filings.

Each event includes:

- Ticker
- Company name
- Drug name (approvals)
- FDA decision date
- Announcement timing (pre-market / market-hours / after-hours)
- Market reaction date
- Market cap group
- Source URL / verification notes

The verified input file is `events_verified.csv` (approvals and CRLs combined). CRL candidates were first collected as `crl_candidates_raw.csv`, hand-verified, and cleaned into `events_crl_clean.csv` via `clean_crl.py` before being merged in.

Events without available historical price data from yfinance were recorded separately in `skipped_events.csv`. This exclusion matters and is discussed under Limitations.

### CRL verification notes

CRL announcement dates are harder to pin down than approvals: the FDA does not publicly release CRLs, so the market-moving event is the company's own disclosure (usually an 8-K or press release), which can lag the letter by days. Each CRL's disclosure timestamp was verified by hand, and after-hours / weekend disclosures were rolled forward to the next trading day. Two verification patterns are worth noting:

- **Duplicate CRLs.** Some companies received more than one CRL for the same drug (e.g., Outlook, Zealand). Only the **first** CRL per company was kept, since repeat CRLs are less of a surprise to the market and their event windows can overlap.
- **Priced-in decisions.** At least one CRL (LXRX) followed a negative advisory-committee vote months earlier, so the market had largely priced in the outcome before the letter. This shows up in the data as a muted or even positive reaction and is discussed under Interpretation.

## Methodology

Historical price data was collected using yfinance. Each stock was compared against two benchmarks:

- SPY: broad market benchmark
- XBI: biotechnology sector benchmark

The main abnormal return measure uses XBI as the benchmark:

```
Abnormal Return = Stock Return - XBI Return
```

Note: this benchmark-subtraction measure implicitly assumes a beta of 1 against XBI. A beta-adjusted market model is planned for a future version (see Next Steps).

### Event Window Definition

The analysis uses trading-day windows around the market reaction date. The market reaction date may differ from the FDA decision date if the announcement occurred after market close; for after-hours announcements, the next trading day is used as the market reaction date.

The event windows are:

- Pre-event window: [-30, -1]
- Announcement window: [0, +1]
- Post-event window: [+2, +30]

## Results

The verified sample contained 10 approvals and 17 CRLs. Historical price data was available for **8 approvals and 15 CRLs** (23 of 27 events); the rest were excluded for missing yfinance data.

### Headline: approval vs CRL asymmetry (announcement window)

| Decision | Mean    | Median  | n |
| -------- | ------- | ------- | --- |
| Approval | +9.12%  | +6.95%  | 8 |
| CRL      | -35.17% | -40.01% | 15 |

The market's reaction to a CRL is far larger in magnitude than its reaction to an approval. In this sample the average bad-news move (-35%) is roughly four times the size of the average good-news move (+9%). This is the central finding of v1.2. See `charts/approval_vs_crl_asymmetry.png`.

### Abnormal returns by window — approvals (n=8)

| Window               | Mean   | Median  | Mean (drop top outlier) | Dominant outlier |
| -------------------- | ------ | ------- | ----------------------- | ---------------- |
| Pre-event [-30, -1]  | +6.32% | +4.39%  | +1.88%                  | XFOR (+37.4%)    |
| Announcement [0, +1] | +9.12% | +6.95%  | +6.08%                  | GERN (+30.5%)    |
| Post-event [+2, +30] | -7.30% | -13.34% | -5.34%                  | MDGL (-21.0%)    |

### Abnormal returns by window — CRLs (n=15)

| Window               | Mean    | Median  |
| -------------------- | ------- | ------- |
| Pre-event [-30, -1]  | -3.66%  | -5.17%  |
| Announcement [0, +1] | -35.17% | -40.01% |
| Post-event [+2, +30] | +9.62%  | +7.01%  |

For CRLs, the reaction is heavily concentrated in the announcement window. The small negative pre-event mean (-3.66%) suggests only mild anticipation, and the positive post-event figures (+9.62% mean, +7.01% median) indicate a partial bounce-back after the initial drop, consistent with an oversold reaction being partly retraced.

### CRL reaction by market cap (announcement window)

| Group     | Mean    | Median  | n |
| --------- | ------- | ------- | --- |
| Small-cap | -49.51% | -57.20% | 9 |
| Mid-cap   | -13.67% | -4.74%  | 6 |

Small-cap biotechs are punished far more severely by a CRL than mid-caps — the small-cap median announcement reaction is roughly -57%. This is consistent with small single-asset companies being more existentially exposed to a single FDA decision.

## Charts

- `charts/approval_vs_crl_asymmetry.png` — box + individual points, approval vs CRL announcement returns (the v1.2 headline)
- `charts/announcement_abnormal_return_by_ticker.png` — per-event announcement reaction, all events
- `charts/mean_median_by_window.png` — mean vs median per window, with the dominant outlier annotated
- `charts/outlier_sensitivity_by_window.png` — window mean with and without the single largest outlier
- `charts/market_cap_group_announcement_return.png` — small-cap vs mid-cap, mean and median

Note: `mean_median_by_window.png`, `outlier_sensitivity_by_window.png`, and `market_cap_group_announcement_return.png` currently **pool approvals and CRLs**, so their pooled means (e.g., an announcement average around -20%) mix a positive and a negative event type and should be read as full-sample diagnostics of *where* the reaction concentrates, not as an interpretable effect size. The approval-only and CRL-only tables above are the correct basis for magnitude. Splitting these charts by decision type is a v1.3 item.

## Interpretation

Read with the small samples in mind:

1. **Asymmetry is the main result.** Approvals produce a positive announcement reaction (mean +9.12%, robust under the median and after dropping the largest name); CRLs produce a much larger negative one (mean -35.17%, median -40.01%). The market reacts more violently to bad news than to good news in this sample.

2. **Approval pre-event window — no clear anticipation.** The positive pre-event mean (+6.32%) is driven almost entirely by a single stock, XFOR (+37.4%). Inspecting XFOR's daily prices shows this run-up came from a large single-day move about six weeks before the approval, unrelated to the FDA decision, not a gradual pre-approval drift. With XFOR removed, the pre-event mean falls to +1.88%. This window is better described as showing no systematic pre-announcement signal than as "market anticipation."

3. **Approval post-event window — reversal.** Post-approval abnormal returns are negative (mean -7.30%, median -13.34%), consistent with a profit-taking / "sell the news" pattern following the approval pop.

4. **CRL reaction concentrates at announcement, then partly retraces.** CRLs show only mild pre-event drift (-3.66%), a large announcement drop (-35.17%), and a positive post-event window (+9.62%). The partial bounce is consistent with an initial overreaction to bad news being partly corrected over the following month.

5. **Not every CRL is a surprise.** LXRX reacted positively to its CRL because a negative advisory-committee vote months earlier had already priced in the bad outcome. This is a useful reminder that event studies measure reactions to *new information*, and a CRL is only "news" if the market had not already expected it.

## Limitations

This is a pilot analysis with several limitations:

- **Small samples** (8 approvals, 15 CRLs), so individual events strongly influence the averages.
- **Survivorship bias in the CRL sample.** Two verified CRL events (ZEAL, APLT) were dropped because their tickers no longer return price data on yfinance — and delisting is correlated with the *worst* CRL outcomes. APLT in particular was an ~-80% event. Because the most catastrophic CRL reactions are the ones most likely to be missing, the reported CRL drop (-35%) is likely an **underestimate** of the true average. The excluded events are listed in `skipped_events.csv`.
- Abnormal return uses simple benchmark subtraction (implicit beta = 1), not a beta-adjusted market model.
- Events without yfinance price data were excluded.
- Statistical significance is not yet tested; the samples are still small, and the asymmetry result should be treated as descriptive until a test is added.
- Market cap groups are simplified.
- Pooled charts mix decision types (see Charts note).

## Next Steps

- Add statistical significance testing (bootstrap / permutation) for the approval-vs-CRL asymmetry.
- Expand the approval sample (n=8 toward ~20) to balance the two groups and improve power.
- Recover skipped events where event-window prices exist despite later delisting, to reduce survivorship bias.
- Beta-adjusted abnormal returns via a market model estimated on a pre-event window.
- Split the window and market-cap charts by decision type.
- A simple event-driven trading strategy backtest.

## Changelog

Newest entries on top.

### v1.2

- Added a **CRL contrast group** (15 events with price data) alongside the approval sample.
- New headline result: **approval vs CRL announcement asymmetry** (+9.12% vs -35.17%).
- Added CRL-only window table and CRL-only market-cap breakdown (small-cap -49.51% vs mid-cap -13.67%).
- New chart `approval_vs_crl_asymmetry.png`.
- CRL data pipeline: `crl_candidates_raw.csv` -> hand verification -> `clean_crl.py` -> `events_crl_clean.csv` -> merged into `events_verified.csv`.
- Documented **survivorship bias** in the CRL sample (ZEAL, APLT dropped; reported CRL drop is a likely underestimate).
- Kept one CRL per company (first CRL only) to preserve independence and avoid overlapping windows.

### v1.1

- Reporting layer only — no change to how returns are computed.
- Added median alongside mean for every event window.
- Added per-window outlier flagging and a "drop top outlier" mean to expose small-sample sensitivity.
- New chart `outlier_sensitivity_by_window.png`; window chart replaced by `mean_median_by_window.png`.
- Corrected the pre-event interpretation: the positive pre-event mean is an XFOR-driven artifact, not market anticipation.

### v1.0

- Initial event study on a manually verified pilot sample of approvals.
- XBI-adjusted abnormal returns over pre / announcement / post trading-day windows.
- Trading-day anchoring with after-hours announcements mapped to the next trading day.
- Mean abnormal return by window and by market cap group; three summary charts.
