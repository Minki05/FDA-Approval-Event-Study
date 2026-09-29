"""
backtest_crl_rebound.py — CRL 폭락 후 반등 전략 백테스트

전략: CRL 발표 구간(t-1 종가 -> t+1 종가) XBI 대비 초과수익이 -X% 이하면
      t+1 종가에 매수, t+30 종가에 매도.  같은 금액 XBI 공매도로 헤지 (섹터 움직임 제거)
      -> 거래당 수익 = post_abn_return_xbi (t+1 -> t+30 XBI 대비 초과수익) - 왕복 거래비용
      (미래정보 없음: 매수 판단에 쓰는 발표 반응은 t+1 종가에 이미 확정된 값)

점검:
  [1] 임계값 X = 20/30/40%  x  거래비용 0.5/1/2%
  [2] 기간 분리: 2022-24 에서 X 선택 -> 2025-26 에 그대로 적용 (과적합 점검)
  [3] 생존편향 스트레스: 가격 없어 빠진 CRL 종목(survivorship.csv)을 -100% / -50% 거래로 추가
  [4] 플라시보: 같은 종목들이 CRL 과 무관한 날(이벤트 ±60거래일 밖) 이틀에 -X% 이상 빠졌을 때
      그 뒤 29거래일 XBI 대비 수익 -> "소형 바이오는 원래 폭락 후 반등한다" 와 구분
  [5] 헤지 안 한 경우 (주식만 보유) 참고

입력: event_returns.csv, survivorship.csv      출력: backtest_results.txt, backtest_trades.csv
USAGE: python3 backtest_crl_rebound.py         ([4] 플라시보는 가격 다운로드로 몇 분)
"""
import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

THRESHOLDS = [20, 30, 40]          # 발표 반응 -X% 이하일 때 매수
COSTS = [0.5, 1.0, 2.0]            # 왕복 거래비용 (%)
MAIN_X, MAIN_COST = 30, 1.0
HOLD = 29                          # t+1 -> t+30 = 29 거래일
rng = np.random.default_rng(42)

lines = []
def out(s=""):
    print(s)
    lines.append(s)


def stats_line(r, label):
    r = pd.Series(r).dropna().values
    if len(r) < 3:
        out(f"  {label:<34} n={len(r)} (표본 부족)")
        return
    _, p_t = stats.ttest_1samp(r, 0)
    try:
        _, p_w = stats.wilcoxon(r)
    except ValueError:
        p_w = np.nan
    boot = rng.choice(r, size=(10000, len(r)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    out(f"  {label:<34} n={len(r):>2} | 평균 {r.mean():+6.1f}% | 중앙값 {np.median(r):+6.1f}% | 승률 {(r > 0).mean()*100:3.0f}% "
        f"| 최악 {r.min():+6.1f}% | 최고 {r.max():+6.1f}% | t p={p_t:.3f} | Wilcoxon p={p_w:.3f} | 95% CI [{lo:+.1f}, {hi:+.1f}]")


# ------------------------------------------------------------------ 데이터
ev = pd.read_csv("event_returns.csv")
crl = ev[ev.decision_type == "CRL"].copy()
crl["year"] = pd.to_datetime(crl.event_date).dt.year
crl["ann"] = crl.announcement_abn_return_xbi
crl["post"] = crl.post_abn_return_xbi
crl["post_raw"] = crl.post_raw_return

out("=" * 110)
out("CRL 폭락 후 반등 전략 백테스트  (매수 t+1 종가 -> 매도 t+30 종가, XBI 헤지)")
out(f"CRL 이벤트 {len(crl)}건 (가격 있는 것)")
out("=" * 110)

# 전체 CRL 에서 신호 확인 (전략 아님, 참고)
rho, p = stats.spearmanr(crl.ann, crl.post)
out(f"\n[0] 신호: 발표 반응 vs 이후 30일 Spearman rho={rho:.2f} (p={p:.4f})")

# ------------------------------------------------------------------ [1] 임계값 x 비용
out("\n[1] 임계값 x 거래비용 (거래당 XBI 대비 수익, 비용 차감 후)")
for x in THRESHOLDS:
    sel = crl[crl.ann <= -x]
    for c in COSTS:
        stats_line(sel.post - c, f"-{x}% 이하 매수, 비용 {c}%")
    out("")
stats_line(crl[crl.ann > -MAIN_X].post - MAIN_COST, f"(비교) -{MAIN_X}% 안 빠진 CRL")

main = crl[crl.ann <= -MAIN_X].copy()
main["net"] = main.post - MAIN_COST
main.sort_values("event_date")[["ticker", "event_date", "ann", "post", "net", "post_raw"]].to_csv(
    "backtest_trades.csv", index=False)
out(f"\n  메인 규칙(-{MAIN_X}%, 비용 {MAIN_COST}%) 거래 목록 -> backtest_trades.csv")
for _, t in main.sort_values("event_date").iterrows():
    out(f"    {t.ticker:<6} {t.event_date}  발표 {t.ann:+6.1f}%  ->  30일 {t.post:+6.1f}%")

# ------------------------------------------------------------------ [2] 기간 분리
out("\n[2] 기간 분리 (과적합 점검): 2022-24 에서 임계값 선택 -> 2025-26 에 적용")
train, test = crl[crl.year <= 2024], crl[crl.year >= 2025]
cands = [x for x in THRESHOLDS if (train.ann <= -x).sum() >= 3]
best = max(cands, key=lambda x: (train[train.ann <= -x].post - MAIN_COST).mean()) if cands else MAIN_X
if not cands:
    out(f"  (2022-24 에 임계값별 거래가 3건 미만 -> 메인 임계값 -{MAIN_X}% 로 고정)")
out(f"  2022-24 에서 고른 임계값: -{best}%")
stats_line(train[train.ann <= -best].post - MAIN_COST, f"학습 2022-24 (-{best}%)")
stats_line(test[test.ann <= -best].post - MAIN_COST, f"검증 2025-26 (-{best}%)")

# ------------------------------------------------------------------ [3] 생존편향
out("\n[3] 생존편향 스트레스: 가격 없어 빠진 CRL 을 모두 매수했다고 가정")
try:
    sv = pd.read_csv("survivorship.csv")
    miss = sv[sv.decision_type.astype(str).str.startswith("CRL")]
    out(f"  빠진 CRL {len(miss)}건: {', '.join(miss.ticker)}")
    for loss in [-100, -50]:
        r = np.concatenate([main.net.values, np.full(len(miss), loss - MAIN_COST)])
        stats_line(r, f"빠진 CRL 을 {loss}% 로 추가")
    out("  주의: 실제로는 일부가 인수(프리미엄)로 끝나서 -100% 는 최악 가정. 진짜 값은 그 사이.")
except FileNotFoundError:
    out("  survivorship.csv 없음 -> 건너뜀")

# ------------------------------------------------------------------ [4] 플라시보
out(f"\n[4] 플라시보: 같은 종목, CRL 과 무관한 날 이틀 -{MAIN_X}% 이상 폭락 후 {HOLD}일 (XBI 대비)")
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
        two = (px.s / px.s.shift(2) - px.m / px.m.shift(2)) * 100            # 이틀 초과수익 (t-1 -> t+1 과 같은 길이)
        fwd = (px.s.shift(-HOLD) / px.s - px.m.shift(-HOLD) / px.m) * 100    # 이후 29일 초과수익
        pos = np.arange(len(px))
        ok = (two <= -MAIN_X).values & (np.abs(pos - k) > 60) & fwd.notna().values
        last = -10**9
        for j in np.where(ok)[0]:                                            # 겹치는 신호 제거
            if j - last > HOLD:
                plac.append(fwd.iloc[j] - MAIN_COST)
                last = j
    stats_line(plac, "플라시보 (CRL 아닌 폭락)")
    stats_line(main.net, f"CRL 폭락 (메인 규칙)")
    if len(plac) >= 3 and len(main) >= 3:
        _, p = stats.mannwhitneyu(main.net, plac, alternative="two-sided")
        out(f"  CRL 폭락 vs 일반 폭락 반등 차이 Mann-Whitney p={p:.3f}  (크면 'CRL 고유 효과' 라고 말하기 어려움)")
except Exception as err:
    out(f"  플라시보 실패 ({err}) -> 건너뜀")

# ------------------------------------------------------------------ [5] 헤지 안 함
out("\n[5] 참고: XBI 헤지 없이 주식만 보유")
stats_line(main.post_raw - MAIN_COST, f"-{MAIN_X}% 이하, 헤지 없음")

out("\n해석 가이드: 거래 수가 적어 (n<20) p값은 참고용. 결론은 '비용·생존편향·플라시보 후에도 남는가' 로 판단.")
open("backtest_results.txt", "w").write("\n".join(lines) + "\n")
print("\n-> backtest_results.txt, backtest_trades.csv")
