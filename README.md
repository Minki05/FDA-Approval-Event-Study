# How Do Biotech Stocks React to FDA Decisions?

An event study of small- and mid-cap US biotech stocks around FDA approvals and Complete Response Letters (CRLs), 2022–2026.

**Main result.** On the two trading days around the announcement, and measured against the biotech sector (XBI):

- stocks rose **+7.9%** on average after an approval (n = 52, p = 0.013)
- stocks fell **−23.6%** on average after a CRL (n = 33, p = 0.0002)

The market punishes bad news about **3 times more** than it rewards good news. The result holds with SPY as the benchmark, with a market model, without events contaminated by other news, and under a different reaction-day definition.

![Approval vs CRL](charts/approval_vs_crl.png)

---

## Question

A small biotech often depends on a single drug, so an FDA decision can decide whether the company has a business. I wanted to measure:

1. How large is the average reaction to an approval and to a rejection (CRL)?
2. Is the reaction symmetric, or does bad news matter more?
3. Does the price move before the news (leakage) or keep moving after it (drift / reversal)?

## Data

**Sample:** 93 hand-verified FDA decisions from January 2022 to September 2026. Price data is available for **85 of them: 52 approvals and 33 CRLs**.

**Sample rules**

- US-listed small- and mid-cap companies (market cap below $10B the day before the event)
- one event per company per decision type (the first one), so the same company does not dominate the sample
- all application types are included (new molecular entities, new formulations, biologics reviewed by CDER and gene/cell therapies reviewed by CBER), and each event is tagged so subsets can be tested separately

**Where the events come from**

| Source | Used for |
|---|---|
| openFDA drugsfda | approval candidates (NDA + BLA, original approvals) |
| openFDA CRL database | CRLs from 2024 onward |
| SEC EDGAR full-text search of 8-K filings | CRLs from 2022–2023 |

The FDA's CRL database is biased before 2024: it mostly contains drugs that were **later approved**. Using it for 2022–23 would be look-ahead bias, because I would only see CRLs with a good ending. So for those years I searched what companies themselves disclosed in 8-Ks at the time.

**Verification**

- **Reaction day.** The FDA decision date is often not the day the market reacted. I read the press release time for each event. Anything announced after 4:00 pm ET was assigned to the next trading day.
- **Automatic cross-check.** `data_build/verify_events.py` checks every event against SEC filing timestamps, recomputes market cap at t−1, tags novelty and review center from openFDA, and flags other price-moving filings on the same days. This caught several reaction dates I had entered incorrectly.
- **Contamination.** 11 events had other news in the window, such as earnings, stock offerings or financing deals. They stay in the sample and are dropped in a sensitivity test.
- **Exclusions.** Excluded events are kept with their reason in `data/events_excluded.csv`, for example a company above the market-cap cap or one whose primary listing is outside the US.

## Method

**Abnormal return** = stock return − XBI return over the same days (SPY as a robustness check).

**Windows**, in trading days around the reaction day *t*, all close-to-close:

| Window | Days | What it answers |
|---|---|---|
| Pre | t−30 → t−1 | Did the price move before the news? |
| **Announcement** | **t−1 → t+1** | **The reaction (main result)** |
| Post | t+1 → t+30 | Does the move continue or reverse? |

The announcement window is two days long, so it still catches the reaction if the reaction day is off by one.

**Tests.** Event returns are small-sample and heavy-tailed, so every result is reported with three things: a t-test, a Wilcoxon signed-rank test and a bootstrap 95% confidence interval. The approval vs CRL comparison uses Welch's t-test and Mann-Whitney U.

## Results

### Main result

| | n | Mean | Median | t-test p | Wilcoxon p | 95% CI (bootstrap) |
|---|---|---|---|---|---|---|
| Approval | 52 | **+7.94%** | +1.53% | 0.013 | 0.040 | [+2.1, +14.0] |
| CRL | 33 | **−23.60%** | −14.12% | 0.0002 | 0.0002 | [−34.6, −12.9] |

Difference: 31.5 percentage points (Welch p < 0.001, Mann-Whitney p < 0.001). The CRL reaction is 3.0x the size of the approval reaction.

The approval median (+1.5%) is much lower than the mean. Most approvals are largely expected and move the stock little, while a few surprises move it a lot.

### Robustness

| Check | Approval | CRL |
|---|---|---|
| Main (vs XBI) | +7.9% (p = 0.013) | −23.6% (p = 0.0002) |
| vs SPY instead of XBI | +7.9% (p = 0.015) | −23.5% (p = 0.0003) |
| Market model (OLS beta), BMP test | +7.4% (p = 0.006) | −24.5% (p = 0.0007) |
| Without contaminated events | +8.7% (p = 0.019) | −25.1% (p = 0.0002) |
| Drop largest and smallest event | +7.3% (p = 0.011) | −23.7% (p = 0.0001) |
| Novel drugs only (NME / new biologics) | +5.7% (p = 0.054) | −24.7% (p = 0.001) |
| All approvals with reaction day = FDA date | +6.6% (p = 0.030) | – |

- **Market model** (`3_market_model.py`). Subtracting XBI assumes beta = 1. I estimated each stock's alpha and beta by OLS on days t−250 to t−31, then standardized each event's abnormal return by its prediction-error variance, which includes the estimation error in alpha and beta. I use the BMP test (Boehmer, Musumeci & Poulsen, 1991) because volatility on FDA days is far higher than normal. The median beta turned out to be about 1.0, and the ranking of events is almost identical to the simple method (Spearman ρ = 0.996).
- **Reaction-day definition** (`4_anchor_check.py`). Recomputing every approval with a single mechanical rule (reaction day = FDA date) gives a similar result (ρ = 0.97 between the two versions, and no systematic difference, Wilcoxon p = 0.21).
- The one weak spot is **novel-drug approvals only**, which are borderline (p ≈ 0.05). The CRL result is strong in every version.

![Mean reaction by window](charts/windows_by_decision.png)

### Before and after the announcement

- **Pre window.** There is no significant movement before CRLs (−1.9%, p = 0.82). Before approvals there is a small run-up (+6.0%, p = 0.07), which is consistent with some anticipation but not conclusive.
- **Post window.** On average there is no significant drift after either type. But among CRLs, **the bigger the drop, the bigger the rebound** over the next 30 days (Spearman ρ = −0.52, p = 0.002). This suggests the market overreacts to the worst CRLs.
- **Other splits (not significant).** Approval reactions were larger in 2022–23 (+13.0%) than in 2024–26 (+4.0%), but the difference is not significant (p = 0.15). CBER CRLs (gene and cell therapies) fell more (−34.9%, n = 7) than CDER CRLs (−20.6%), also not significant. Small-cap CRLs fell more than mid-cap CRLs (−27.0% vs −13.1%, p = 0.26).

## Backtest: buying after large CRL drops

![CRL overreaction](charts/crl_overreaction.png)

**Rule.** If the XBI-adjusted return from t−1 to t+1 is −30% or worse, buy at the t+1 close and sell at the t+30 close, shorting the same amount of XBI. Round-trip cost is 1%. The rule only uses information known at the time of the trade.

**In-sample (n = 14).** Mean +16.4% per trade, median +11.7%, 11 of 14 trades profitable (t-test p = 0.021, Wilcoxon p = 0.013). The result barely changes with costs of 0.5–2% or thresholds of −20% / −40%. CRLs that fell less than 30% kept falling (mean −6.4%, n = 19).

**Does it survive the obvious objections?**

- **Out-of-sample.** I chose the threshold on 2022–24 only (it picked −20%) and applied it unchanged to 2025–26: +15.8% per trade. That is the same direction, but with only 8 trades it is not significant (p = 0.18).
- **Survivorship.** Seven CRL companies have no price data because they were later acquired or delisted. If all of them had been −100% trades, the mean turns to −22.7%. At −50% it is −6.1%. This bound is extreme: these stocks did trade during the 30 days, and not all of them would have hit the signal. Still, it shows the result depends on the missing firms.
- **Placebo.** Non-CRL crashes of −30% or more in the same stocks rebounded +4.7% (n = 52, not significant). The CRL rebound is larger, but the difference is not significant (Mann-Whitney p = 0.11).
- **No hedge.** The mean is +14.5% but the worst trade is −43.5% (p = 0.095). The XBI hedge mainly reduces risk.

**Conclusion.** The rebound after large CRL drops is large in this sample. Given the small number of trades, the out-of-sample test, survivorship and the placebo comparison, I do **not** claim it is a tradable or CRL-specific anomaly.

## Limitations

- **Small samples.** 52 and 33 events, and the backtest has 14 trades. Many subgroups are tested, so a single p < 0.05 in a subgroup should not be over-read.
- **Survivorship bias.** Companies that were acquired or delisted have no price history in yfinance: 7 events in the sample and 6 further CRLs, all listed in `data/survivorship.csv`. Delisting is more likely after the worst outcomes, so the CRL reaction may be understated.
- **Human judgment.** Reaction days, novelty tags for never-approved drugs, and contamination flags were decided by hand from press releases and filings. The reasons are recorded in the data and in `data_build/`.
- **Mixed reaction-day rules.** About 30 approvals were added with a mechanical rule (reaction day = FDA date). `4_anchor_check.py` shows this does not change the result.
- **Not a new finding.** Earlier event studies have documented large reactions to FDA news. The contribution here is the recent 2022–26 sample, the look-ahead-free CRL collection from 8-K filings, the automated verification, and the robustness checks.

## Next steps

- Recover prices for the acquired and delisted companies from another data source, to remove the survivorship problem.
- Extend the sample back to 2015–2021 for a real out-of-sample test.
- Look at other catalysts with larger samples, such as Phase 3 readouts and advisory committee votes.

## Repository structure

```
1_event_returns.py          abnormal returns for every event (pre / announcement / post)
2_significance_tests.py     t-test, Wilcoxon, bootstrap CI, subgroups
3_market_model.py           OLS market model, Patell and BMP tests
4_anchor_check.py           robustness to the reaction-day definition
5_backtest_crl_rebound.py   CRL rebound backtest with out-of-sample, survivorship and placebo checks
6_make_charts.py            charts/
data/                       events_verified.csv (final sample), events_excluded.csv, survivorship.csv
results/                    all outputs (regenerated by the scripts)
charts/                     figures used in this README
data_build/                 how the dataset was collected and verified (record, not needed to reproduce results)
```

Each script starts with a header explaining the question, the reasoning and the result.

## How to run

```bash
pip install -r requirements.txt
python3 1_event_returns.py
python3 2_significance_tests.py
python3 3_market_model.py
python3 4_anchor_check.py
python3 5_backtest_crl_rebound.py
python3 6_make_charts.py
```

Prices come from yfinance, so the first run takes a few minutes, and numbers can shift slightly if Yahoo revises historical data.

<details>
<summary>All events, sorted by reaction</summary>

![Reaction by event](charts/reaction_by_event.png)

</details>
