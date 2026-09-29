"""
market_model.py — 마켓 모델(OLS 베타)로 초과수익률(CAR) 재계산 + 검정

지금까지(calculate_event_returns.py):  AR = R_stock - R_XBI        (alpha=0, beta=1 로 고정한 특수한 경우)
여기서:                               AR = R_stock - (alpha + beta * R_XBI)   (종목마다 alpha, beta 를 OLS 로 추정)

1) 추정 구간  : 이벤트일 t 기준 [t-250, t-31] 거래일의 일간 수익률 (이벤트 전 급등락이 섞이지 않게 t-31 에서 끊음)
               최소 120일 필요 (부족하면 결과에 est_n 이 작게 표시되고 검정에서 제외)
2) OLS        : y = X theta + e,  X = [1, R_m],  theta_hat = (X'X)^-1 X'y   (np.linalg.lstsq)
               s^2 = SSR / (n - 2)
3) 이벤트 구간 : t, t+1 두 거래일 (= t-1 종가 -> t+1 종가, 기존 발표구간과 동일)
               AR_t = R_i,t - (alpha_hat + beta_hat R_m,t),   CAR = AR_t + AR_t+1
4) 표준화     : Var(CAR) = s^2 * ( L + 1' X_e (X'X)^-1 X_e' 1 )     (L=2, X_e = 이벤트 구간의 [1, R_m])
               -> 두 번째 항은 alpha, beta 추정 오차 보정 (예측오차 분산)
               SCAR = CAR / sqrt(Var(CAR))
5) 검정       : 평균 CAR t-test / Wilcoxon (기존과 같은 방식)
               Patell Z = sum(SCAR) / sqrt( sum( (n-2)/(n-4) ) )   (종목별 변동성 차이 보정)
               BMP t    = mean(SCAR) / ( std(SCAR) / sqrt(N) )     (이벤트로 변동성이 커지는 것까지 허용 -> 더 보수적)

벤치마크: XBI (메인), SPY (robustness)
입력 : event_returns.csv (이벤트/이벤트 거래일), events_verified.csv (태그)
출력 : market_model_results.csv (이벤트별 alpha/beta/CAR/SCAR), market_model_results.txt (검정 요약)
USAGE: python3 market_model.py      (종목 가격 다운로드 때문에 처음 몇 분 걸림)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

EST_START, EST_END = 250, 31      # 추정 구간: t-250 ~ t-31 거래일
MIN_EST = 120                     # 최소 추정 관측치
EVENT_DAYS = 2                    # t, t+1
OUT_CSV, OUT_TXT = "market_model_results.csv", "market_model_results.txt"

lines = []
def out(s=""):
    print(s)
    lines.append(s)


# ------------------------------------------------------------------ 가격 받기
def close_series(ticker, start, end):
    s = yf.Ticker(ticker).history(start=start, end=end)["Close"]
    if s.empty:
        return s
    s.index = s.index.tz_localize(None).normalize()
    return s


# ------------------------------------------------------------------ 핵심: OLS + CAR
def market_model_car(stock, market, event_day):
    """stock, market: 종가 Series. event_day: 이벤트 거래일(t).
    반환: dict(alpha, beta, s2, est_n, car, var_car, scar) 또는 None"""
    px = pd.DataFrame({"s": stock, "m": market}).dropna()
    r = px.pct_change().dropna() * 100            # 일간 수익률(%). r.iloc[i] = i-1 종가 -> i 종가
    if event_day not in r.index:
        return None
    t = r.index.get_loc(event_day)
    if t + EVENT_DAYS > len(r):
        return None

    est = r.iloc[max(0, t - EST_START): t - EST_END + 1]     # t-250 ~ t-31
    evt = r.iloc[t: t + EVENT_DAYS]                           # t, t+1
    n = len(est)
    if n < MIN_EST:
        return dict(est_n=n)

    # (1) OLS: theta_hat = (X'X)^-1 X'y
    X = np.column_stack([np.ones(n), est["m"].values])
    y = est["s"].values
    theta, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = theta
    resid = y - X @ theta
    s2 = resid @ resid / (n - 2)                              # 잔차 분산

    # (2) 이벤트 구간 AR, CAR
    Xe = np.column_stack([np.ones(EVENT_DAYS), evt["m"].values])
    ar = evt["s"].values - Xe @ theta
    car = ar.sum()

    # (3) Var(CAR) = s^2 (L + 1' Xe (X'X)^-1 Xe' 1)   -> 추정 오차까지 포함한 예측오차 분산
    one = np.ones(EVENT_DAYS)
    XtX_inv = np.linalg.inv(X.T @ X)
    var_car = s2 * (EVENT_DAYS + one @ Xe @ XtX_inv @ Xe.T @ one)
    scar = car / np.sqrt(var_car)

    return dict(alpha=alpha, beta=beta, s2=s2, est_n=n, car=car, var_car=var_car, scar=scar)


# ------------------------------------------------------------------ 검정
def summarize(d, col_car, col_scar, label):
    d = d.dropna(subset=[col_car, col_scar])
    x, z = d[col_car].values, d[col_scar].values
    N = len(x)
    if N < 3:
        out(f"  {label:<26} n={N} (표본 부족)")
        return
    t, p_t = stats.ttest_1samp(x, 0.0)
    try:
        _, p_w = stats.wilcoxon(x)
    except ValueError:
        p_w = np.nan
    # Patell: SCAR_i ~ t(n_i - 2), 분산 (n_i-2)/(n_i-4)
    ni = d["est_n_" + col_car.split("_")[-1]].values          # car_xbi -> est_n_xbi
    patell = z.sum() / np.sqrt(((ni - 2) / (ni - 4)).sum())
    p_pat = 2 * (1 - stats.norm.cdf(abs(patell)))
    # BMP: SCAR 의 횡단면 표준편차 사용
    bmp = z.mean() / (z.std(ddof=1) / np.sqrt(N))
    p_bmp = 2 * (1 - stats.t.cdf(abs(bmp), N - 1))
    out(f"  {label:<26} n={N:>2} | mean CAR {x.mean():+7.2f}% | median {np.median(x):+7.2f}% "
        f"| t p={p_t:.4f} | Wilcoxon p={p_w:.4f} | Patell Z={patell:+.2f} (p={p_pat:.4f}) "
        f"| BMP t={bmp:+.2f} (p={p_bmp:.4f})")


def main():
    ev = pd.read_csv("event_returns.csv")
    tags = pd.read_csv("events_verified.csv")
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
              f"CAR_mm={rec['car_xbi']:+7.2f}%  (기존 단순차감 {rec['simple_abn_xbi']:+7.2f}%)")

    r = pd.DataFrame(rows)
    r.to_csv(OUT_CSV, index=False)
    ok = r[r.est_n_xbi >= MIN_EST]
    thin = r[~r.index.isin(ok.index)]

    out("\n" + "=" * 100)
    out("마켓 모델 (OLS, 추정구간 t-250~t-31, 이벤트구간 t~t+1)")
    out(f"추정 가능 {len(ok)} / 전체 {len(r)}  (추정일수 부족: {', '.join(thin.ticker) or '없음'})")
    out("=" * 100)

    out("\n[1] 베타 분포 (XBI 대비)")
    for dt, g in ok.groupby("decision_type"):
        out(f"  {dt:<9} 중앙값 beta {g.beta_xbi.median():.2f} | 평균 {g.beta_xbi.mean():.2f} "
            f"| 범위 {g.beta_xbi.min():.2f} ~ {g.beta_xbi.max():.2f}")

    out("\n[2] 마켓 모델 CAR (XBI, 메인)")
    for dt in ["APPROVAL", "CRL"]:
        summarize(ok[ok.decision_type == dt], "car_xbi", "scar_xbi", dt)

    out("\n[2b] 마켓 모델 CAR (SPY, robustness)")
    for dt in ["APPROVAL", "CRL"]:
        summarize(ok[ok.decision_type == dt], "car_spy", "scar_spy", dt + " (SPY)")

    out("\n[3] 비대칭 (승인 vs CRL, 마켓 모델 CAR)")
    a, c = ok[ok.decision_type == "APPROVAL"].car_xbi.dropna(), ok[ok.decision_type == "CRL"].car_xbi.dropna()
    _, p_w = stats.ttest_ind(a, c, equal_var=False)
    _, p_u = stats.mannwhitneyu(a, c, alternative="two-sided")
    out(f"  APPROVAL {a.mean():+.2f}% vs CRL {c.mean():+.2f}% | diff {a.mean()-c.mean():+.2f}%p "
        f"| Welch p={p_w:.4f} | Mann-Whitney p={p_u:.4f} | |CRL|/승인 = {abs(c.mean()/a.mean()):.1f}배")

    out("\n[4] 민감도: 오염 제외 / NME·신규 바이오만")
    clean = ok[~ok.confounded.fillna("").astype(str).str.len().gt(0)]
    nme = ok[ok.novelty.isin(["NME", "novel_biologic"])]
    for dt in ["APPROVAL", "CRL"]:
        summarize(clean[clean.decision_type == dt], "car_xbi", "scar_xbi", dt + " - 오염 제외")
    for dt in ["APPROVAL", "CRL"]:
        summarize(nme[nme.decision_type == dt], "car_xbi", "scar_xbi", dt + " NME/신규 바이오")

    out("\n[5] 방법 비교: 단순 차감(beta=1) vs 마켓 모델")
    diff = ok.car_xbi - ok.simple_abn_xbi
    out(f"  이벤트별 차이 평균 {diff.mean():+.2f}%p | 절대값 중앙값 {diff.abs().median():.2f}%p "
        f"| 부호가 바뀐 이벤트 {int((np.sign(ok.car_xbi) != np.sign(ok.simple_abn_xbi)).sum())}개")
    rho, p = stats.spearmanr(ok.car_xbi, ok.simple_abn_xbi, nan_policy="omit")
    out(f"  두 방법 순위상관 Spearman rho={rho:.3f} (p={p:.4g})")

    out("\n주의: Patell 은 이벤트일 변동성 증가를 무시해서 과대유의 경향 -> BMP 를 우선으로 해석.")
    open(OUT_TXT, "w").write("\n".join(lines) + "\n")
    print(f"\n-> {OUT_CSV}, {OUT_TXT}")


if __name__ == "__main__":
    main()
