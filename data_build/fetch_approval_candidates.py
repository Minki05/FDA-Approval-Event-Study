"""
fetch_approval_candidates.py  (v1.3, approval sourcing step)

WHY THIS EXISTS:
  기존 fda_events.py는 BLA 승인만, limit 100, 페이지네이션 없이
  긁어서 승인 후보가 ~25개뿐이었다. CRL 후보(128개)와 균형을
  맞추려면 승인 풀 자체를 키워야 한다. 그래서:
    - BLA + NDA 둘 다 (NDA 신약 승인이 빠져 있었음)
    - 페이지네이션으로 전체 훑기
    - ORIG/AP(원 신청의 승인)만, 2024-2025로 연도 필터
  해서 후보 풀을 넓힌 뒤, 수동 검증 단계로 넘긴다.

WHAT THIS DOES (automated part only):
  openFDA drugsfda에서 승인(ORIG + AP) 레코드를 긁어
  approval_candidates_raw.csv로 저장. 티커/시총/검증은 안 함.

WHAT THIS DOES NOT DO (manual, on purpose):
  - sponsor_name -> stock ticker 매핑
  - 상장 여부 / 소형·중형 시총 분류
  - announcement_time (pre/market/after) 확인
  - press release로 market_reaction_date 확정
  이건 CRL 때와 똑같이 사람이 손으로 채운다. 승인일(FDA
  기록)은 시장 반응일과 다를 수 있으므로 그대로 쓰면 안 된다.

USAGE:
  python fetch_approval_candidates.py            # writes approval_candidates_raw.csv
  python fetch_approval_candidates.py --counts   # 연도 분포만 출력
"""

import sys
import time
import csv
import requests
from collections import Counter

ENDPOINT = "https://api.fda.gov/drug/drugsfda.json"
# 2026 추가: v2 만든 이후 새로 쌓인 결정들을 채움.
# 2022-2023 추가 (v2 확장): 승인 표본 보강용. drugsfda는 FDA 전수 기록이라
# CRL DB 같은 look-ahead 선택 문제는 없음. 단 2021(버블 정점)은 레짐 차이로 제외,
# 결과는 2022-23 vs 2024-26 서브기간으로 따로 비교해 robustness 확인.
# ※ CRL 쪽은 확장 금지: 2024 이전 CRL DB는 '나중에 승인된 약'만 공개돼 편향.
TARGET_YEARS = {"2022", "2023", "2024", "2025", "2026"}
APP_PREFIXES = ("BLA", "NDA")   # 기존엔 BLA만; NDA 추가가 이 버전의 핵심
PAGE = 100                      # drugsfda 권장 페이지 크기
MAX_PAGES = 60                  # 방어적 상한
OUTPUT = "approval_candidates_raw.csv"

# 사람이 손으로 채울 칸 (CRL 스크립트와 동일한 분리 원칙)
MANUAL_COLS = [
    "ticker",                 # sponsor_name -> ticker (manual)
    "market_reaction_date",   # press release 기준 (manual)
    "announcement_time",      # pre_market / market_hours / after_hours (manual)
    "market_cap_group",       # small / mid (manual)
    "alive_ticker",           # yes / no (yfinance에 있나)
    "keep_for_v2",            # yes / no
    "exclude_reason",         # delisted / big-pharma / no-clear-disclosure 등
    "verification_notes",
]

# openFDA에서 바로 오는 칸 (자동)
FDA_COLS = [
    "sponsor_name",
    "approval_date",
    "application_number",
    "brand_name",
    "generic_name",
]


def is_target_app(app_num):
    return app_num.startswith(APP_PREFIXES)


def extract_approvals(result):
    """한 drugsfda 레코드에서 ORIG 원신청의 승인(AP) 이벤트를 뽑는다."""
    app_num = result.get("application_number", "")
    if not is_target_app(app_num):
        return []

    sponsor = result.get("sponsor_name", "")
    # 제품명(브랜드/제네릭)은 첫 product 기준으로만 참고용으로 채운다
    products = result.get("products", [])
    brand = products[0].get("brand_name", "") if products else ""
    generic = products[0].get("generic_name", "") if products else ""

    rows = []
    for sub in result.get("submissions", []):
        if sub.get("submission_type") != "ORIG":
            continue
        if sub.get("submission_status") != "AP":
            continue
        date = sub.get("submission_status_date", "")   # YYYYMMDD
        year = date[:4] if len(date) >= 4 else ""
        if year not in TARGET_YEARS:
            continue
        rows.append({
            "sponsor_name": sponsor,
            "approval_date": date,
            "application_number": app_num,
            "brand_name": brand,
            "generic_name": generic,
        })
    return rows


def fetch_all():
    rows = []
    skip = 0
    for _ in range(MAX_PAGES):
        params = {"search": "application_number:BLA* OR application_number:NDA*",
                  "limit": PAGE, "skip": skip}
        r = requests.get(ENDPOINT, params=params, timeout=30)
        if r.status_code != 200:
            print(f"stopped at skip={skip}, status={r.status_code}")
            break
        results = r.json().get("results", [])
        if not results:
            break
        for res in results:
            rows.extend(extract_approvals(res))
        skip += PAGE
        time.sleep(0.3)   # rate-limit 예의
        if len(results) < PAGE:
            break
    return rows


def main():
    counts_only = "--counts" in sys.argv
    rows = fetch_all()

    years = Counter(r["approval_date"][:4] for r in rows)
    print("승인 후보 연도 분포:")
    for y in sorted(years):
        print(f"  {y}: {years[y]}")
    yr_lo, yr_hi = min(TARGET_YEARS), max(TARGET_YEARS)
    print(f"총 승인 후보({yr_lo}-{yr_hi}, BLA+NDA, ORIG/AP): {len(rows)}")

    if counts_only:
        return

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FDA_COLS + MANUAL_COLS)
        writer.writeheader()
        for row in rows:
            for col in MANUAL_COLS:
                row.setdefault(col, "")
            writer.writerow(row)
    print(f"-> {OUTPUT} ({len(rows)} rows, 수동 검증 대기)")


if __name__ == "__main__":
    main()
