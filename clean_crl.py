import pandas as pd

# 1. 검증 초안 읽기
df = pd.read_csv("crl_draft.csv")

# 2. 제외 처리한 행 버리기 (keep_for_v2 == 'no': 비상장/상폐/8-K 없음/대형자회사)
df = df[df["keep_for_v2"].str.strip() != "no"].copy()

# 3. 회사당 CRL 1개만 남김 (통계 독립성 + estimation window 겹침 방지)
#    규칙: 같은 ticker면 letter_date가 가장 이른 것 = '첫 CRL(진짜 서프라이즈)' 유지
df["_ld"] = pd.to_datetime(df["letter_date"], format="%m/%d/%Y")
df = df.sort_values("_ld").drop_duplicates(subset="ticker", keep="first")

# 4. 스크립트가 읽는 컬럼명으로 맞추기
df = df.rename(columns={"company_name": "company", "letter_date": "event_date"})

# 5. event_date를 YYYY-MM-DD로 통일 + 없는 컬럼(drug_name) 채우기
df["event_date"] = df["_ld"].dt.strftime("%Y-%m-%d")
df["drug_name"] = ""

# 6. 스크립트가 쓰는 컬럼만, 순서대로
cols = ["company", "ticker", "drug_name", "event_date", "announcement_time",
        "decision_type", "event_direction", "market_reaction_date", "market_cap_group"]
out = df[cols].sort_values("event_date").reset_index(drop=True)

out.to_csv("events_crl_clean.csv", index=False)

# 리포트
print(f"최종 CRL 이벤트: {len(out)}개\n")
print(out[["company", "ticker", "event_date", "market_reaction_date",
           "announcement_time", "market_cap_group"]].to_string(index=False))
ah = out[out["announcement_time"] == "after_hours"]
print(f"\n날짜 재확인 대상 (after_hours {len(ah)}개) — output에서 갭이 announcement 창에 잡혔는지 확인:")
print("  " + ", ".join(ah["ticker"].tolist()))
