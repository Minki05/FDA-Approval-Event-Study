"""
significance_tests.py  (v2: event_returns.csv -> 통계 검정)

발표 구간 = t-1 종가 -> t+1 종가 (2일), XBI 대비 초과수익률이 메인 지표.
SPY 대비는 robustness로 같이 보고.

검정:
  1) 그룹별 평균 != 0 : one-sample t-test + Wilcoxon signed-rank (소표본/두꺼운 꼬리 대비)
     + bootstrap 95% CI (평균)
  2) 승인 vs CRL 차이 : Welch t-test + Mann-Whitney U
  3) 서브기간 : 승인 2022-23 vs 2024-26 (레짐 차이 robustness)
  4) 민감도 : 오염 플래그 이벤트(VRCA, CRMD) / 시각 미확인(TVTX) 제외
  5) 시총 : small vs mid (그룹 내)

USAGE:  python3 significance_tests.py   ->  significance_results.txt
"""

import numpy as np
import pandas as pd
from scipy import stats

INPUT = "event_returns.csv"
OUTPUT = "significance_results.txt"
MAIN = "announcement_abn_return_xbi"
ROBUST = "announcement_abn_return_spy"
VERIFIED = "events_verified.csv"     # confounded / novelty / center 태그 출처
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
        out(f"  {label:<28} n={len(x)}  (표본 부족)")
        return
    t, p_t = stats.ttest_1samp(x, 0.0)
    try:
        _, p_w = stats.wilcoxon(x)
    except ValueError:
        p_w = np.nan
    lo, hi = boot_ci(x)
    pos = (x > 0).mean() * 100
    out(f"  {label:<28} n={len(x):>2} | mean {x.mean():+7.2f}% | median {np.median(x):+7.2f}% "
        f"| t={t:+.2f} p={p_t:.4f} | Wilcoxon p={p_w:.4f} | 95% CI [{lo:+.2f}, {hi:+.2f}] | 양수 {pos:.0f}%")


def two_sample(a, b, la, lb):
    a, b = pd.Series(a).dropna().values, pd.Series(b).dropna().values
    if len(a) < 3 or len(b) < 3:
        out(f"  {la} vs {lb}: 표본 부족")
        return
    t, p_t = stats.ttest_ind(a, b, equal_var=False)
    _, p_u = stats.mannwhitneyu(a, b, alternative="two-sided")
    out(f"  {la} (n={len(a)}, {a.mean():+.2f}%) vs {lb} (n={len(b)}, {b.mean():+.2f}%) "
        f"| diff {a.mean() - b.mean():+.2f}%p | Welch p={p_t:.4f} | Mann-Whitney p={p_u:.4f}")


df = pd.read_csv(INPUT)
df["year"] = pd.to_datetime(df["event_date"]).dt.year
tags = pd.read_csv(VERIFIED)
for col in ["confounded", "novelty", "center"]:
    if col not in tags:
        tags[col] = ""
df = df.drop(columns=[c for c in ["confounded", "novelty", "center", "market_cap_group"] if c in df]).merge(
    tags[["ticker", "decision_type", "confounded", "novelty", "center", "market_cap_group"]],
    on=["ticker", "decision_type"], how="left")
df["confounded"] = df["confounded"].fillna("").astype(str).str.len() > 0
A = df[df.decision_type == "APPROVAL"]
C = df[df.decision_type == "CRL"]

out("=" * 100)
out("FDA 이벤트 스터디 v2 — 유의성 검정 (발표구간 t-1 -> t+1)")
out(f"표본: 승인 {len(A)} + CRL {len(C)} = {len(df)}")
out("=" * 100)

out("\n[1] 그룹별 평균 초과수익률 (XBI 대비, 메인)")
one_sample(A[MAIN], "APPROVAL")
one_sample(C[MAIN], "CRL")

out("\n[1b] Robustness: SPY 대비")
one_sample(A[ROBUST], "APPROVAL (vs SPY)")
one_sample(C[ROBUST], "CRL (vs SPY)")

out("\n[2] 비대칭: 승인 vs CRL")
two_sample(A[MAIN], C[MAIN], "APPROVAL", "CRL")
out(f"  |CRL 평균| / 승인 평균 = {abs(C[MAIN].mean()) / A[MAIN].mean():.1f}배"
    if A[MAIN].mean() > 0 else "  (승인 평균 <= 0, 배율 계산 생략)")

out("\n[3] 서브기간 (승인만): 2022-23 vs 2024-26")
early, late = A[A.year <= 2023], A[A.year >= 2024]
one_sample(early[MAIN], "APPROVAL 2022-23")
one_sample(late[MAIN], "APPROVAL 2024-26")
two_sample(early[MAIN], late[MAIN], "2022-23", "2024-26")

out("\n[4] 민감도")
out(f"  오염 플래그: {', '.join(df[df.confounded].ticker + '(' + df[df.confounded].decision_type.str[0] + ')') or '없음'}")
one_sample(A[~A.confounded][MAIN], "APPROVAL - 오염 제외")
one_sample(C[~C.confounded][MAIN], "CRL - 오염 제외")
one_sample(A[A.novelty.isin(["NME", "novel_biologic"])][MAIN], "APPROVAL NME/신규 바이오만")
one_sample(C[C.novelty.isin(["NME", "novel_biologic"])][MAIN], "CRL NME/신규 바이오만")
one_sample(C[C.center == "CDER"][MAIN], "CRL CDER만 (CBER 제외)")
two_sample(C[C.center == "CDER"][MAIN], C[C.center == "CBER"][MAIN], "CRL CDER", "CBER")
two_sample(A[A.novelty.isin(["NME", "novel_biologic"])][MAIN],
           C[C.novelty.isin(["NME", "novel_biologic"])][MAIN], "APPROVAL NME", "CRL NME")
# 극단값 영향: 최대/최소 1개씩 제거
a_sorted = A[MAIN].sort_values()
one_sample(a_sorted.iloc[1:-1], "APPROVAL trim(최대·최소 1)")
c_sorted = C[MAIN].sort_values()
one_sample(c_sorted.iloc[1:-1], "CRL trim(최대·최소 1)")

out("\n[5] 시총 그룹")
for name, g in [("APPROVAL", A), ("CRL", C)]:
    s, m = g[g.market_cap_group == "small"][MAIN], g[g.market_cap_group == "mid"][MAIN]
    one_sample(s, f"{name} small")
    one_sample(m, f"{name} mid")
    two_sample(s, m, f"{name} small", "mid")

out("\n[6] 사전 구간 (t-30 -> t-1): 정보 선반영 확인")
one_sample(A["pre_abn_return_xbi"], "APPROVAL pre")
one_sample(C["pre_abn_return_xbi"], "CRL pre")

out("\n[7] 사후 구간 (t+1 -> t+30): drift / 과잉반응 확인")
one_sample(A["post_abn_return_xbi"], "APPROVAL post")
one_sample(C["post_abn_return_xbi"], "CRL post")
r, p = stats.spearmanr(C[MAIN], C["post_abn_return_xbi"])
out(f"  CRL 발표 반응 vs 사후 반응 Spearman rho={r:+.2f} p={p:.4f}  (음수면 반전 경향)")

out("\n주의: 소표본(n<30) + 이벤트별 분산 이질성 -> t-검정은 참고용, Wilcoxon/부트스트랩과 함께 해석.")
out("      다중 비교(구간·서브그룹 여러 개)라 개별 p<0.05를 과대해석하지 말 것.")

with open(OUTPUT, "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"\n-> {OUTPUT}")
