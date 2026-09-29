"""
3_market_model.py

Question
    1_event_returns.py assumes every stock moves 1:1 with XBI (beta = 1). Many small
    biotechs don't. Do the results change if I estimate each stock's own alpha and beta?

Why I did it this way
    This is the standard market model from event-study papers (MacKinlay 1997):

        R_stock = alpha + beta * R_XBI + e

    I estimate it by OLS on a "normal" period before the event, then treat the
    prediction on event days as the expected return:

        AR  = R_stock - (alpha_hat + beta_hat * R_XBI)      on days t and t+1
        CAR = AR_t + AR_t+1                                  (same window as before)

What it does
    1. Estimation window: trading days t-250 to t-31 (at least 120 days).
       It stops at t-31 so a pre-event run-up does not leak into beta.
    2. OLS in matrix form:  X = [1, R_XBI],  theta_hat = (X'X)^-1 X'y,
       residual variance  s^2 = SSR / (n - 2).
    3. Standardize each CAR by its prediction-error variance, which includes the
       error from estimating alpha and beta, not just s^2:
           Var(CAR) = s^2 * ( L + 1' Xe (X'X)^-1 Xe' 1 ),   L = 2 event days
           SCAR = CAR / sqrt(Var(CAR))
    4. Tests on top of t-test and Wilcoxon:
           Patell Z = sum(SCAR) / sqrt( sum( (n-2)/(n-4) ) )
           BMP t    = mean(SCAR) / ( sd(SCAR) / sqrt(N) )   (Boehmer, Musumeci & Poulsen 1991)
       Patell assumes volatility on event day is the same as normal days, which is
       clearly false for FDA news, so it overstates significance. BMP uses the actual
       spread of SCARs across events, so it is my main test here.
    5. Same thing with SPY as the benchmark, and the same sensitivity subsets as
       2_significance_tests.py.

Input / Output
    results/event_returns.csv, data/events_verified.csv
      ->  results/market_model_results.csv (alpha, beta, CAR, SCAR per event)
          results/market_model_results.txt (tests)

Result
    Median beta vs XBI is about 1.0, so beta = 1 was a reasonable assumption.
    Approvals +7.4% (BMP p = 0.006), CRLs -24.5% (BMP p = 0.0007).
    Rank correlation with the simple method is 0.996, so the conclusions do not change.
    Novel-drug-only approvals stay borderline (BMP p = 0.058).

Run
    python3 3_market_model.py        (downloads ~1.5 years of prices per event, a few minutes)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

EST_START, EST_END = 250, 31
MIN_EST = 120
EVENT_DAYS = 2
OUT_CSV, OUT_TXT = "results/market_model_results.csv", "results/market_model_results.txt"

lines = []
def out(s=""):
    print(s)
    lines.append(s)


def close_series(ticker, start, end):
    s = yf.Ticker(ticker).history(start=start, end=end)["Close"]
    if s.empty:
        return s
    s.index = s.index.tz_localize(None).normalize()
    return s


def market_model_car(stock, market, event_day):
    px = pd.DataFrame({"s": stock, "m": market}).dropna()
    r = px.pct_change().dropna() * 100
    if event_day not in r.index:
        return None
    t = r.index.get_loc(event_day)
    if t + EVENT_DAYS > len(r):
        return None

    est = r.iloc[max(0, t - EST_START): t - EST_END + 1]
    evt = r.iloc[t: t + EVENT_DAYS]
    n = len(est)
    if n < MIN_EST:
        return dict(est_n=n)

    X = np.column_stack([np.ones(n), est["m"].values])
    y = est["s"].values
    theta, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = theta
    resid = y - X @ theta
    s2 = resid @ resid / (n - 2)

    Xe = np.column_stack([np.ones(EVENT_DAYS), evt["m"].values])
    ar = evt["s"].values - Xe @ theta
    car = ar.sum()

    one = np.ones(EVENT_DAYS)
    XtX_inv = np.linalg.inv(X.T @ X)
    var_car = s2 * (EVENT_DAYS + one @ Xe @ XtX_inv @ Xe.T @ one)
    scar = car / np.sqrt(var_car)

    return dict(alpha=alpha, beta=beta, s2=s2, est_n=n, car=car, var_car=var_car, scar=scar)


def summarize(d, col_car, col_scar, label):
    d = d.dropna(subset=[col_car, col_scar])
    x, z = d[col_car].values, d[col_scar].values
    N = len(x)
    if N < 3:
        out(f"  {label:<28} n={N} (too few events)")
        return
    _, p_t = stats.ttest_1samp(x, 0.0)
    try:
        _, p_w = stats.wilcoxon(x)
    except ValueError:
        p_w = np.nan
    ni = d["est_n_" + col_car.split("_")[-1]].values
    patell = z.sum() / np.sqrt(((ni - 2) / (ni - 4)).sum())
    p_pat = 2 * (1 - stats.norm.cdf(abs(patell)))
    bmp = z.mean() / (z.std(ddof=1) / np.sqrt(N))
    p_bmp = 2 * (1 - stats.t.cdf(abs(bmp), N - 1))
    out(f"  {label:<28} n={N:>2} | mean CAR {x.mean():+7.2f}% | median {np.median(x):+7.2f}% "
        f"| t p={p_t:.4f} | Wilcoxon p={p_w:.4f} | Patell Z={patell:+.2f} (p={p_pat:.4f}) "
        f"| BMP t={bmp:+.2f} (p={p_bmp:.4f})")


def main():
    ev = pd.read_csv("results/event_returns.csv")
    tags = pd.read_csv("data/events_verified.csv")
    keep = [c for c in ["ticker", "decision_type", "confounded", "novelty", "center"] if c in tags]
    ev = ev.merge(tags[keep], on=["ticker", "decision_type"], how="left")
    ev["event_trading_day"] = pd.to_datetime(ev["event_trading_day"])

    lo = (ev.event_trading_day.min() - pd.Timedelta(days=420)).date()
    hi = (ev.event_trading_day.max() + pd.Timedelta(days=10)).date()
    bench = {b: close_series(b, lo, hi) for b in ["XBI", "SPY"]}

    rows = []
    for _, e in ev.iterrows():
        t0 = e.event_trading_day
        stock = close_series(e.ticker, (t0 - pd.Timedelta(days=420)).date(), (t0 + pd.Timedelta(days=10)).date())
        rec = dict(ticker=e.ticker, decision_type=e.decision_type, event_trading_day=t0.date(),
                   simple_abn_xbi=e.announcement_abn_return_xbi,
                   confounded=e.get("confounded", ""), novelty=e.get("novelty", ""))
        for b in ["XBI", "SPY"]:
            res = market_model_car(stock, bench[b], t0) if not stock.empty else None
            for k in ["alpha", "beta", "est_n", "car", "scar"]:
                rec[f"{k}_{b.lower()}"] = (res or {}).get(k, np.nan)
        rows.append(rec)
        print(f"{e.ticker:<6} {e.decision_type:<8} beta_XBI={rec['beta_xbi']:+.2f}  est_n={rec['est_n_xbi']:.0f}  "
              f"CAR={rec['car_xbi']:+7.2f}%  (simple method {rec['simple_abn_xbi']:+7.2f}%)")

    r = pd.DataFrame(rows)
    r.to_csv(OUT_CSV, index=False)
    ok = r[r.est_n_xbi >= MIN_EST]
    thin = r[~r.index.isin(ok.index)]

    out("\n" + "=" * 100)
    out("Market model (OLS, estimation window t-250 to t-31, event window t to t+1)")
    out(f"Estimated {len(ok)} / {len(r)}  (not enough history: {', '.join(thin.ticker) or 'none'})")
    out("=" * 100)

    out("\n[1] Beta vs XBI")
    for dt, g in ok.groupby("decision_type"):
        out(f"  {dt:<9} median beta {g.beta_xbi.median():.2f} | mean {g.beta_xbi.mean():.2f} "
            f"| range {g.beta_xbi.min():.2f} to {g.beta_xbi.max():.2f}")

    out("\n[2] Market model CAR (XBI, main)")
    for dt in ["APPROVAL", "CRL"]:
        summarize(ok[ok.decision_type == dt], "car_xbi", "scar_xbi", dt)

    out("\n[2b] Market model CAR (SPY, robustness)")
    for dt in ["APPROVAL", "CRL"]:
        summarize(ok[ok.decision_type == dt], "car_spy", "scar_spy", dt + " (SPY)")

    out("\n[3] Asymmetry (approval vs CRL, market model CAR)")
    a, c = ok[ok.decision_type == "APPROVAL"].car_xbi.dropna(), ok[ok.decision_type == "CRL"].car_xbi.dropna()
    _, p_w = stats.ttest_ind(a, c, equal_var=False)
    _, p_u = stats.mannwhitneyu(a, c, alternative="two-sided")
    out(f"  APPROVAL {a.mean():+.2f}% vs CRL {c.mean():+.2f}% | diff {a.mean()-c.mean():+.2f}pp "
        f"| Welch p={p_w:.4f} | Mann-Whitney p={p_u:.4f} | |CRL| / approval = {abs(c.mean()/a.mean()):.1f}x")

    out("\n[4] Sensitivity: clean events only / novel drugs only")
    clean = ok[~ok.confounded.fillna("").astype(str).str.len().gt(0)]
    nme = ok[ok.novelty.isin(["NME", "novel_biologic"])]
    for dt in ["APPROVAL", "CRL"]:
        summarize(clean[clean.decision_type == dt], "car_xbi", "scar_xbi", dt + " - clean only")
    for dt in ["APPROVAL", "CRL"]:
        summarize(nme[nme.decision_type == dt], "car_xbi", "scar_xbi", dt + " - novel drugs only")

    out("\n[5] Simple method (beta = 1) vs market model")
    diff = ok.car_xbi - ok.simple_abn_xbi
    out(f"  Mean difference per event {diff.mean():+.2f}pp | median absolute difference {diff.abs().median():.2f}pp "
        f"| sign flipped for {int((np.sign(ok.car_xbi) != np.sign(ok.simple_abn_xbi)).sum())} events")
    rho, p = stats.spearmanr(ok.car_xbi, ok.simple_abn_xbi, nan_policy="omit")
    out(f"  Rank correlation between the two methods: Spearman rho={rho:.3f} (p={p:.4g})")

    out("\nNote: Patell ignores the higher volatility on event days and overstates significance -> read BMP first.")
    open(OUT_TXT, "w").write("\n".join(lines) + "\n")
    print(f"\n-> {OUT_CSV}, {OUT_TXT}")


if __name__ == "__main__":
    main()
