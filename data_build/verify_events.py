"""
verify_events.py — events_verified.csv 자동 검증

이벤트마다 자동으로 확인:
  [시각]  SEC 8-K/6-K 접수 시각 -> 정보가 늦어도 언제 공개됐는지 -> 기록된 반응일과 비교
  [시총]  t-1 당시 실제 주가(분할 되돌림) x XBRL 발행주식수 -> small/mid/large
  [태그]  openFDA 신청 유형 -> novelty(NME/non-NME/novel_biologic), center(CDER/CBER)
  [오염]  반응 구간(t-1~t+1)의 다른 공시: 실적(2.02), 계약/차입(1.01/2.03), 증자(424B*, S-3 등)
  [해외]  20-F/6-K 제출사 -> 해외 기업 플래그 (본주 상장지는 사람이 최종 판단)

결과:
  verification_report.csv  이벤트별 자동 검증 결과 + 플래그
  events_enriched.csv      events_verified + 자동 태그 (원본은 건드리지 않음)

USAGE:
  1) sec_utils.py 맨 위 SEC_USER_AGENT에 이메일 입력
  2) python3 verify_events.py
  상장폐지 종목 CIK를 못 찾으면 아래 CIK_OVERRIDES에 적고 다시 실행 (캐시 덕분에 빠름)
"""

import os
import re
import statistics
from datetime import datetime, timedelta

import pandas as pd

import sec_utils as su

VERIFIED = "events_verified.csv"
APPROVAL_RAW = "approval_candidates_raw.csv"
CRL_RAW = "crl_candidates_raw.csv"

CIK_OVERRIDES = {
    # "VRNA": 1657312,   # 예시 형식. 자동으로 못 찾은 것만 채우면 됨
}

# 미승인 CRL 약은 openFDA에 기록이 없어 자동 판정 불가 -> 수동 (근거: 공시/라벨)
MANUAL_NOVELTY = {
    ("NERV", "CRL"): "NME",             # roluperidone
    ("ABEO", "CRL"): "novel_biologic",  # pz-cel (gene therapy)
    ("RCKT", "CRL"): "novel_biologic",  # Kresladi (gene therapy)
    ("ZEAL", "CRL"): "non-NME",         # dasiglucagon, 2021년 Zegalogue로 이미 승인 (새 적응증)
    ("APLT", "CRL"): "NME",             # govorestat
    ("LXRX", "CRL"): "non-NME",         # sotagliflozin, 2023년 Inpefa로 이미 승인
    ("ATRA", "CRL"): "novel_biologic",  # tab-cel (cell therapy)
    ("MIST", "CRL"): "NME",             # etripamil
    ("ALDX", "CRL"): "non-NME",         # ADX-2191 methotrexate (2023 CRL로 교체)
    ("UNCY", "CRL"): "non-NME",         # oxylanthanum carbonate, lanthanum 기존 성분
    ("RARE", "CRL"): "novel_biologic",  # UX111 (gene therapy)
    ("CAPR", "CRL"): "novel_biologic",  # deramiocel (cell therapy)
    ("REPL", "CRL"): "novel_biologic",  # RP1 (oncolytic virus)
    ("PTCT", "CRL"): "NME",             # vatiquinone
    ("OTLK", "CRL"): "non-NME",         # bevacizumab 안과 제형
    ("SRRK", "CRL"): "novel_biologic",  # apitegromab
    ("BHVN", "CRL"): "NME",             # troriluzole
    # --- 2024-26 CRL (EDGAR 전문검색)
    ("CORT", "CRL"): "NME",
    ("AQST", "CRL"): "NME",
    ("RGNX", "CRL"): "novel_biologic",
    ("IRON", "CRL"): "NME",
    ("GRCE", "CRL"): "non-NME",
    ("CING", "CRL"): "non-NME",
    ("ACHV", "CRL"): "NME",
    # --- 2022-23 CRL (EDGAR 전문검색)
    ("AKBA", "CRL"): "NME",
    ("CHRS", "CRL"): "novel_biologic",
    ("AXSM", "CRL"): "non-NME",
    ("VRCA", "CRL"): "non-NME",
    ("SPRO", "CRL"): "NME",
    ("SUPN", "CRL"): "non-NME",
    ("CYTK", "CRL"): "NME",
    ("ASND", "CRL"): "NME",
    ("IBRX", "CRL"): "novel_biologic",
    ("CTXR", "CRL"): "non-NME",
    ("SPRY", "CRL"): "non-NME",
}

# 2022-23 CRL은 FDA CRL DB(2024~)에 없어 신청번호가 없음 -> center 수동 지정
MANUAL_CENTER = {(t, "CRL"): "CDER" for t in ['AKBA', 'CHRS', 'AXSM', 'VRCA', 'SPRO', 'SUPN', 'CYTK', 'ASND', 'IBRX', 'ALDX', 'CTXR', 'OTLK', 'SPRY']}
MANUAL_CENTER.update({("CORT", "CRL"): "CDER", ("AQST", "CRL"): "CDER", ("RGNX", "CRL"): "CBER", ("IRON", "CRL"): "CDER", ("GRCE", "CRL"): "CDER", ("CING", "CRL"): "CDER", ("ACHV", "CRL"): "CDER"})

EVENT_FORMS = {"8-K", "6-K"}
EVENT_ITEMS = ("7.01", "8.01")        # 보도자료성 8-K만 (주총 결과 5.07 같은 무관 공시 제외)
OFFERING_FORMS = ("424B", "S-3", "S-1", "F-3", "F-1", "SC TO")
CONFOUND_ITEMS = {"2.02": "EARNINGS", "1.01": "AGREEMENT", "2.03": "DEBT",
                  "3.02": "EQUITY_SALE", "5.02": "EXEC_CHANGE", "2.01": "ACQUISITION"}


def first_token(s):
    t = su.norm_name(s).split()
    return t[0] if t else ""


# ------------------------------------------------------------- application no.
def load_raw():
    a = pd.read_csv(APPROVAL_RAW) if os.path.exists(APPROVAL_RAW) else pd.DataFrame()
    c = pd.read_csv(CRL_RAW) if os.path.exists(CRL_RAW) else pd.DataFrame()
    if len(a):
        a["d"] = pd.to_datetime(a["approval_date"].astype(str), format="mixed", errors="coerce")
        a["brand_tok"] = a["brand_name"].astype(str).str.upper().str.extract(r"([A-Z0-9]+)")[0]
    if len(c):
        c["d"] = pd.to_datetime(c["letter_date"], format="mixed", errors="coerce")
        c["tok"] = c["company_name"].apply(first_token)
    return a, c


def find_appno(row, a, c):
    if "application_number" in row and isinstance(row.get("application_number"), str) and row["application_number"]:
        return row["application_number"], "events_verified"
    ed = pd.Timestamp(row["event_date"])
    if row["decision_type"] == "APPROVAL" and len(a):
        bt = re.match(r"[A-Za-z0-9]+", str(row["drug_name"]))
        if bt:
            m = a[(a.brand_tok == bt.group(0).upper()) & ((a.d - ed).abs() <= pd.Timedelta(days=10))]
            if len(m):
                return list(m["application_number"].unique()), "approval_raw"
    if row["decision_type"] == "CRL" and len(c):
        m = c[(c.tok == first_token(row["company"])) & ((c.d - ed).abs() <= pd.Timedelta(days=30))]
        if len(m):
            m = m.assign(gap=(m.d - ed).abs()).sort_values("gap")
            return m.iloc[0]["application_number"], "crl_raw"
    return "", ""


# ------------------------------------------------------------- timezone calib
PR_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.I)
PR_DATE_RE = re.compile(r"(20\d\d-\d\d-\d\d)")


def pr_datetime_from_note(row):
    note = str(row.get("market_reaction_note", ""))
    m = PR_TIME_RE.search(note)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    h = h % 12 + (12 if ap == "PM" else 0)
    dm = PR_DATE_RE.search(note)
    d = pd.Timestamp(dm.group(1)) if dm else pd.Timestamp(row["event_date"])
    return datetime(d.year, d.month, d.day, h, mi)


def calibrate_tz(rows):
    """보도자료 시각이 적힌 이벤트: (8-K 접수시각 원값 - 보도자료 시각). 중앙값 3~6시간이면 UTC."""
    diffs = []
    for pr_dt, raw_acc in rows:
        if pr_dt and raw_acc:
            dh = (raw_acc - pr_dt).total_seconds() / 3600
            if -2 <= dh <= 12:
                diffs.append(dh)
    if len(diffs) < 3:
        print(f"[시간대 보정] 비교 가능한 이벤트 {len(diffs)}개 -> 기본값 ET 사용")
        return "ET"
    med = statistics.median(diffs)
    mode = "UTC" if 3.0 <= med <= 6.5 else "ET"
    print(f"[시간대 보정] 8-K 접수 - 보도자료 시각 중앙값 {med:+.2f}h (n={len(diffs)}) -> EDGAR 시각을 {mode}로 해석")
    return mode


# ------------------------------------------------------------- main
def main():
    v = pd.read_csv(VERIFIED)
    a_raw, c_raw = load_raw()

    # 1차: CIK + 공시 목록
    info = {}
    for i, r in v.iterrows():
        tk = str(r["ticker"]).upper()
        cik = su.cik_for_ticker(tk, CIK_OVERRIDES)
        how = "ticker_map" if cik else ""
        if not cik:
            hit = su.find_cik_by_name(r["company"], r["event_date"])
            if hit:
                cik, how = hit[0], f"fts_name({hit[3]}, {hit[2]:.2f})"
        base, subs = (su.submissions(cik) if cik else (None, pd.DataFrame()))
        info[i] = dict(cik=cik, cik_how=how, base=base, subs=subs)

    # 시간대 보정용: 원값(보정 전) 접수 시각
    calib = []
    for i, r in v.iterrows():
        subs = info[i]["subs"]
        if subs.empty:
            continue
        ed = pd.Timestamp(r["event_date"])
        w = subs[subs.form.isin(EVENT_FORMS) & (subs.filingDate >= ed) &
                 (subs.filingDate <= ed + timedelta(days=10))]
        w = w[(w.form == "6-K") | w["items"].astype(str).str.contains(r"7\.01|8\.01")]
        if len(w):
            raw = min(datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") for s in w.acceptanceDateTime if isinstance(s, str))
            calib.append((pr_datetime_from_note(r), raw))
    su.ACCEPT_TZ = calibrate_tz(calib)

    out = []
    for i, r in v.iterrows():
        tk, dt_type = str(r["ticker"]).upper(), r["decision_type"]
        cik, subs, base = info[i]["cik"], info[i]["subs"], info[i]["base"]
        ed = pd.Timestamp(r["event_date"])
        rec_react = su.next_trading_day_on_or_after(r["market_reaction_date"])
        flags, rep = [], dict(ticker=tk, decision_type=dt_type, event_date=r["event_date"],
                              recorded_reaction=r["market_reaction_date"],
                              recorded_time=r.get("announcement_time", ""), cik=cik or "", cik_source=info[i]["cik_how"])
        if not cik:
            flags.append("NO_CIK")

        # ---- 시각
        if not subs.empty:
            w = subs[subs.form.isin(EVENT_FORMS) & (subs.filingDate >= ed) &
                     (subs.filingDate <= ed + timedelta(days=10))].copy()
            w = w[(w.form == "6-K") | w["items"].astype(str).str.contains("|".join(EVENT_ITEMS).replace(".", r"\."))]
            w["acc"] = w.acceptanceDateTime.apply(su.parse_acceptance)
            w = w.dropna(subset=["acc"]).sort_values("acc")
            if len(w):
                f0 = w.iloc[0]
                implied = su.reaction_day_from_time(f0.acc)
                rep.update(first_filing=f0.form, first_filing_time_et=f0.acc.strftime("%Y-%m-%d %H:%M"),
                           first_filing_items=f0.get("items", ""), first_filing_session=su.session_label(f0.acc),
                           implied_latest_reaction=implied.date() if implied is not None else "")
                if implied is not None and rec_react is not None:
                    if rec_react > implied:
                        flags.append("TIMING_LATE")      # 기록된 반응일이 공시보다 늦음 -> 날짜 오류 가능성 큼
                        rep["timing_check"] = f"ERROR: 늦어도 {implied.date()}에 공개됨"
                    elif rec_react == implied:
                        rep["timing_check"] = "OK"
                        if su.session_label(f0.acc) != str(r.get("announcement_time", "")) and \
                                su.session_label(f0.acc) in ("pre_market", "after_hours"):
                            rep["timing_check"] = f"OK (세션 표기 {r.get('announcement_time')} vs 공시 {su.session_label(f0.acc)})"
                    else:
                        rep["timing_check"] = "INFO: 8-K가 반응일 이후 접수 (보도자료가 먼저) — 메모의 PR 시각으로 확인"
            else:
                flags.append("NO_EVENT_FILING")
                rep["timing_check"] = "8-K/6-K 없음 — 보도자료로 수동 확인"

            # ---- 오염: 반응 구간 [t-1, t+1]
            if rec_react is not None:
                lo, hi = su.shift_tday(rec_react, -1), su.shift_tday(rec_react, 1)
                ww = subs[(subs.filingDate >= lo) & (subs.filingDate <= hi)]
                hits = []
                for _, f in ww.iterrows():
                    form = str(f.form)
                    if form.startswith(OFFERING_FORMS):
                        hits.append(f"OFFERING:{form}@{f.filingDate.date()}")
                    for it in str(f.get("items", "")).split(","):
                        it = it.strip()
                        if it in CONFOUND_ITEMS:
                            hits.append(f"{CONFOUND_ITEMS[it]}:{it}@{f.filingDate.date()}")
                n8k = (ww.form.isin(EVENT_FORMS)).sum()
                if n8k >= 2:
                    hits.append(f"MULTI_8K:{n8k}")
                rep["confound_filings"] = "; ".join(dict.fromkeys(hits))
                if hits:
                    flags.append("CONFOUND?")

            # ---- 해외
            fpi, country = su.is_foreign_filer(subs, base)
            rep.update(foreign_filer=fpi, business_country=country)
            if fpi:
                flags.append("FOREIGN_FILER")

        # ---- 시총 (t-1)
        if rec_react is not None and cik:
            t1 = su.shift_tday(rec_react, -1)
            px = su.raw_close(tk, t1)
            sh, sh_end, sh_tag = su.shares_outstanding_asof(cik, t1)
            mcap = px * sh if (px and sh) else None
            grp = su.cap_group(mcap)
            rep.update(t_minus_1=t1.date(), price_raw_t1=round(px, 4) if px else "",
                       shares=int(sh) if sh else "", shares_asof=sh_end or "", shares_tag=sh_tag or "",
                       mcap_t1_musd=round(mcap / 1e6, 1) if mcap else "", cap_group_calc=grp,
                       cap_group_recorded=r.get("market_cap_group", ""))
            if not mcap:
                flags.append("NO_MCAP")
            elif grp != r.get("market_cap_group", ""):
                flags.append(f"CAP_{str(r.get('market_cap_group','')).upper()}->{grp.upper()}")
            if grp == "large":
                flags.append("LARGE_CAP_EXCLUDE?")

        # ---- 신청번호 / novelty / center
        appno, src = find_appno(r, a_raw, c_raw)
        recs = []
        for ap in (appno if isinstance(appno, list) else ([appno] if appno else [])):
            rr = su.drugsfda_app(ap)
            if rr:
                recs.append(rr)
        if not recs and dt_type == "APPROVAL":            # raw에서 못 찾으면 브랜드로 openFDA 직접 검색
            bt = re.match(r"[A-Za-z0-9]+", str(r["drug_name"]))
            recs = su.drugsfda_by_brand(bt.group(0)) if bt else []
            src = "openfda_brand" if recs else src
        # 같은 브랜드 여러 신청(정제/현탁액 등) -> 가장 먼저 승인된 원 신청
        recs.sort(key=lambda x: (su.orig_approval_date(x) or "99999999",
                                 0 if su.novelty_from_drugsfda(x)[0] in ("NME", "novel_biologic") else 1))
        rec = recs[0] if recs else None
        if rec is not None:
            appno = rec.get("application_number", appno)
        if isinstance(appno, list):
            appno = appno[0] if appno else ""
        nov, desc = su.novelty_from_drugsfda(rec)
        if nov == "novel_biologic" and rec is not None and su.ingredient_previously_approved(rec):
            nov, desc = "non-NME", "biologic: same molecule approved earlier"
        if (tk, dt_type) in MANUAL_NOVELTY and (nov == "unknown" or dt_type == "CRL"):
            nov, desc = MANUAL_NOVELTY[(tk, dt_type)], "manual"
        rep.update(application_number=appno, appno_source=src, in_drugsfda=rec is not None,
                   novelty=nov, class_desc=desc, center=su.center_guess(appno, rec is not None) if appno else "")
        if not rep["center"] and (tk, dt_type) in MANUAL_CENTER:
            rep["center"] = MANUAL_CENTER[(tk, dt_type)]
        if not appno:
            flags.append("NO_APPNO")
        if nov == "non-NME":
            flags.append("NON_NME")
        if rep.get("center") == "CBER?":
            flags.append("CBER?")

        rep["flags"] = " ".join(flags)
        out.append(rep)
        print(f"{tk:<5} {dt_type:<8} {rep.get('timing_check','-')[:45]:<45} "
              f"cap={rep.get('mcap_t1_musd','?')}M {rep.get('cap_group_calc','')} | {nov} {rep.get('center','')} | {rep['flags']}")

    rep_df = pd.DataFrame(out)
    rep_df.to_csv("verification_report.csv", index=False)

    enr = v.copy()
    keep = ["cik", "application_number", "novelty", "center", "mcap_t1_musd", "cap_group_calc",
            "foreign_filer", "confound_filings", "timing_check", "flags"]
    for k in keep:
        enr[k] = rep_df[k].values if k in rep_df else ""
    enr.to_csv("events_enriched.csv", index=False)

    print("\n=== 플래그 요약 ===")
    from collections import Counter
    cnt = Counter(f for fl in rep_df["flags"] for f in str(fl).split())
    for f, n in cnt.most_common():
        tks = rep_df[rep_df["flags"].str.contains(re.escape(f), na=False)]
        print(f"  {f:<22} {n:>2}  {', '.join(tks.ticker + '(' + tks.decision_type.str[0] + ')')}")
    print("\n-> verification_report.csv, events_enriched.csv")
    print("   플래그 뜬 것만 사람이 확인하면 됨. 원본 events_verified.csv는 안 바뀜.")


if __name__ == "__main__":
    main()
