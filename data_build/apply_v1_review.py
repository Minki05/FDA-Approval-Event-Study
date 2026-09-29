"""
apply_v1_review.py — verify_events.py 결과 + 수동 확인을 events_verified.csv에 반영

  1) 자동: market_cap_group <- 계산된 t-1 시총 그룹 (events_enriched.csv)
  2) 자동: novelty, center, mcap_t1_musd 열 추가
  3) 수동 확인 결과 (아래 EDITS / EXCLUDE / CONFOUNDED, 근거 주석)
  제외 이벤트는 events_excluded.csv로 이동 (삭제 아님, 기록 보존)

USAGE:  python3 verify_events.py && python3 apply_v1_review.py
"""
import shutil
import pandas as pd

V, E = "events_verified.csv", "events_enriched.csv"

EXCLUDE = {
    ("INSM", "APPROVAL"): "LARGE_CAP: t-1 시총 $23.9B > $10B 상한 (RVMD와 같은 기준)",
    ("ZEAL", "CRL"): "FOREIGN_PRIMARY_LISTING: 본주 코펜하겐 (TLX/Shionogi와 같은 기준)",
}

# (ticker, decision_type): {col: value}
EDITS = {
    ("RARE", "CRL"): dict(market_reaction_date="2025-07-14", announcement_time="after_hours",
                         market_reaction_note="PR Fri 7/11 (after close); Benzinga: shares -8% in Mon 7/14 premarket -> reaction 7/14. "
                                              "Note: separate 8-K 7/9 (Orbit/setrusumab interim miss) falls before window."),
    ("DAWN", "APPROVAL"): dict(novelty="NME"),   # tovorafenib = CDER 2024 novel approval (현탁액 NDA가 잘못 매칭됐던 것)
}

# 반응 구간(t-1~t+1)에 다른 주가 재료 -> 표본 유지, 민감도 분석에서 제외해 비교
CONFOUNDED = {
    ("MDGL", "APPROVAL"): "offering: 424B5 filed 2024-03-18 (= t+1)",
    ("PHAT", "APPROVAL"): "financing: 8-K 1.01/2.03 revenue-interest financing 2022-05-04 (= reaction day)",
    ("LXRX", "APPROVAL"): "offering: 424B5 filed 2023-05-31 (= t+1)",
    ("CHRS", "APPROVAL"): "financing: 8-K 1.01/2.03 2023-10-27 (same release as approval)",
    ("CRMD", "APPROVAL"): "earnings: Q3 8-K 2.02 on 2023-11-14 after close (= t-1 evening)",
    ("VRCA", "APPROVAL"): "debt: $125M loan term sheet announced morning of 2023-07-24 (PR only, no 8-K in window)",
    ("AXSM", "CRL"): "earnings: Q1 2022 results released same morning as CRL PR (5/2)",
    ("CYTK", "CRL"): "earnings + offering: 8-K 2.02 and 424B5 both on 2023-03-01 (= reaction day)",
    ("LENZ", "APPROVAL"): "earnings: Q2 8-K 2.02 on 2025-07-30 (= t-1)",
    ("ARDX", "APPROVAL"): "financing: 8-K 1.01/2.03 on 2023-10-18 (= t+1)",
    ("DERM", "APPROVAL"): "earnings: Q3 8-K 2.02 on 2024-11-04 (= t+1, same filing as approval PR)",
    ("ITRM", "APPROVAL"): "offering: 424B5 on 2024-10-28 (= t+1); no price data anyway",
}

v = pd.read_csv(V)
e = pd.read_csv(E)
shutil.copy(V, "events_verified_backup.csv")
key = lambda d: list(zip(d.ticker, d.decision_type))

e_map = {k: row for k, row in zip(key(e), e.to_dict("records"))}
for col in ["novelty", "center", "mcap_t1_musd"]:
    v[col] = [e_map.get(k, {}).get(col, "") for k in key(v)]
changed = []
for i, k in enumerate(key(v)):
    calc = e_map.get(k, {}).get("cap_group_calc")
    if isinstance(calc, str) and calc and calc != v.at[i, "market_cap_group"]:
        changed.append(f"{k[0]}({k[1][0]}) {v.at[i,'market_cap_group']}->{calc}")
        v.at[i, "market_cap_group"] = calc

for k, cols in EDITS.items():
    m = (v.ticker == k[0]) & (v.decision_type == k[1])
    for c, val in cols.items():
        v.loc[m, c] = val

v["confounded"] = [CONFOUNDED.get(k, "") for k in key(v)]

ex_mask = pd.Series([k in EXCLUDE for k in key(v)])
ex = v[ex_mask.values].copy()
ex["exclude_reason"] = [EXCLUDE[k] for k in key(ex)]
try:
    old = pd.read_csv("events_excluded.csv")
    ex = pd.concat([old, ex]).drop_duplicates(["ticker", "decision_type"], keep="last")
except FileNotFoundError:
    pass
ex.to_csv("events_excluded.csv", index=False)
v = v[~ex_mask.values]
v.to_csv(V, index=False)

print("시총 그룹 변경:", ", ".join(changed) or "없음")
print("제외 ->", ", ".join(f"{a}({b[0]})" for a, b in EXCLUDE))
print("수정:", ", ".join(f"{a}({b[0]})" for a, b in EDITS))
print("오염 플래그:", ", ".join(f"{a}({b[0]})" for a, b in CONFOUNDED))
print(v.decision_type.value_counts().to_dict(), "| 총", len(v), "행")
print(pd.crosstab(v.decision_type, [v.center.fillna(""), v.novelty.fillna("")]))
