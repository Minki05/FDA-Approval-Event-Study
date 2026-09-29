"""
anchor_check.py — 반응일 기준 통일 점검 (결과 파일은 안 바꿈, 비교만)

문제: 승인 이벤트의 반응일 기준이 두 가지 섞여 있음
  - 수동 행 (처음 22건 + 2022-23 수동 + 2026 추가분): 보도자료 시각을 보고 반응일 결정
  - 자동 행 (build_new_approval_rows.py 로 만든 30여 건): "FDA 승인일 = 반응일" 규칙 (verification_notes 에 'auto-built')
점검: 모든 승인 행에 FDA 승인일 규칙을 적용했을 때 (반응일 = event_date 이후 첫 거래일)
      발표구간 [t-1 종가 -> t+1 종가] XBI 대비 초과수익과 검정 결과가 달라지는지 비교

USAGE:  python3 anchor_check.py   ->  anchor_check.txt
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
    """반응일 react 기준 [t-1 종가 -> t+1 종가] 주식 수익률 - XBI 수익률 (%)"""
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
    t, p = stats.ttest_1samp(x, 0)
    _, pw = stats.wilcoxon(x)
    out(f"  {label:<34} n={len(x)} | mean {x.mean():+6.2f}% | median {np.median(x):+6.2f}% | t p={p:.4f} | Wilcoxon p={pw:.4f}")


v = pd.read_csv("events_verified.csv")
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
    rec = ann_abn(s, xbi, e.react_rec)            # 지금 쓰는 반응일
    fda = ann_abn(s, xbi, e.event_date)           # FDA 승인일 규칙
    rows.append(dict(ticker=e.ticker, auto=e.auto, event_date=e.event_date.date(), react_recorded=e.react_rec.date(),
                     same_day=e.react_rec.normalize() == e.event_date.normalize(), abn_recorded=rec, abn_fda_anchor=fda))
r = pd.DataFrame(rows).dropna(subset=["abn_recorded", "abn_fda_anchor"])
r.to_csv("anchor_check.csv", index=False)

manual = r[~r.auto]
moved = manual[~manual.same_day]
out("=" * 100)
out("반응일 기준 점검: 기록된 반응일 vs FDA 승인일 규칙 (승인 이벤트, XBI 대비, t-1 -> t+1)")
out("=" * 100)
out(f"승인 {len(r)}건 중 수동 행 {len(manual)}건, 그중 반응일이 FDA 승인일과 다른 것 {len(moved)}건")
for _, x in moved.iterrows():
    out(f"  {x.ticker:<6} FDA {x.event_date} -> 기록 {x.react_recorded} | 기록 기준 {x.abn_recorded:+7.2f}% | "
        f"FDA 기준 {x.abn_fda_anchor:+7.2f}% | 차이 {x.abn_fda_anchor - x.abn_recorded:+6.2f}%p")

out("\n[전체 승인] 기준별 결과")
test(r.abn_recorded, "현재 (수동+자동 혼합)")
test(r.abn_fda_anchor, "전부 FDA 승인일 규칙")
rho, p = stats.spearmanr(r.abn_recorded, r.abn_fda_anchor)
out(f"  두 기준 이벤트별 순위상관 Spearman rho={rho:.3f} (p={p:.3g})")
_, pp = stats.wilcoxon(r.abn_recorded - r.abn_fda_anchor) if (r.abn_recorded != r.abn_fda_anchor).any() else (0, 1.0)
out(f"  이벤트별 차이 Wilcoxon p={pp:.4f}  (크면 두 기준 차이가 체계적이지 않음)")

out("\n해석: FDA 승인일 규칙은 구간이 [승인일-1, 승인일+1] 이라 장후 발표(다음날 반응)도 포함함.")
out("      두 기준 결과가 비슷하면 README에 '반응일 정의에 강건함'으로 기록.")
open("anchor_check.txt", "w").write("\n".join(lines) + "\n")
print("\n-> anchor_check.txt, anchor_check.csv")
