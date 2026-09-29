"""
data_build/verify_events.py

Step 2: automatically check every hand-entered event in events_verified.csv.

Why
    I entered dates, times and tags by hand from press releases. Hand entry makes
    mistakes, so I wanted an independent automatic check against SEC filings instead
    of trusting myself. This script actually caught real errors (for example reaction
    days that were later than the company's filing).

What it checks for each event
    timing    8-K / 6-K acceptance time -> the latest possible time the news was public.
              If my recorded reaction day is after that, flag TIMING_LATE.
              EDGAR timestamps are calibrated against known press-release times first.
    size      market cap at t-1 (split-adjusted price x XBRL shares) -> small/mid/large
    tags      openFDA application -> novelty (NME / non-NME / novel_biologic) and
              review center (CDER / CBER). CRL drugs that were never approved are not in
              openFDA, so those are tagged by hand in MANUAL_NOVELTY / MANUAL_CENTER
              (with the drug name next to each one as the reason).
    contamination   other price-moving filings in the window t-1 to t+1: earnings
              (8-K 2.02), financing (1.01 / 2.03), stock offerings (424B*, S-3)
    foreign   20-F / 6-K filers -> flag, final call made by hand

Output
    verification_report.csv   one row per event with the checks and flags
    events_enriched.csv       events + automatic tags (events_verified.csv is not changed)
    Only flagged events needed a manual look.

Run (originally from the repo root, after setting SEC_USER_AGENT in sec_utils.py)
    python3 data_build/verify_events.py
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
}

MANUAL_NOVELTY = {
    ("NERV", "CRL"): "NME",             # roluperidone
    ("ABEO", "CRL"): "novel_biologic",  # pz-cel (gene therapy)
    ("RCKT", "CRL"): "novel_biologic",  # Kresladi (gene therapy)
    ("ZEAL", "CRL"): "non-NME",         # dasiglucagon, already approved in 2021 as Zegalogue (new indication)
    ("APLT", "CRL"): "NME",             # govorestat
    ("LXRX", "CRL"): "non-NME",         # sotagliflozin, already approved in 2023 as Inpefa
    ("ATRA", "CRL"): "novel_biologic",  # tab-cel (cell therapy)
    ("MIST", "CRL"): "NME",             # etripamil
    ("ALDX", "CRL"): "non-NME",         # ADX-2191 methotrexate (replaced by the 2023 CRL)
    ("UNCY", "CRL"): "non-NME",         # oxylanthanum carbonate, lanthanum already approved
    ("RARE", "CRL"): "novel_biologic",  # UX111 (gene therapy)
    ("CAPR", "CRL"): "novel_biologic",  # deramiocel (cell therapy)
    ("REPL", "CRL"): "novel_biologic",  # RP1 (oncolytic virus)
    ("PTCT", "CRL"): "NME",             # vatiquinone
    ("OTLK", "CRL"): "non-NME",         # bevacizumab, ophthalmic formulation
    ("SRRK", "CRL"): "novel_biologic",  # apitegromab
    ("BHVN", "CRL"): "NME",             # troriluzole
    ("CORT", "CRL"): "NME",
    ("AQST", "CRL"): "NME",
    ("RGNX", "CRL"): "novel_biologic",
    ("IRON", "CRL"): "NME",
    ("GRCE", "CRL"): "non-NME",
    ("CING", "CRL"): "non-NME",
    ("ACHV", "CRL"): "NME",
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

MANUAL_CENTER = {(t, "CRL"): "CDER" for t in ['AKBA', 'CHRS', 'AXSM', 'VRCA', 'SPRO', 'SUPN', 'CYTK', 'ASND', 'IBRX', 'ALDX', 'CTXR', 'OTLK', 'SPRY']}
MANUAL_CENTER.update({("CORT", "CRL"): "CDER", ("AQST", "CRL"): "CDER", ("RGNX", "CRL"): "CBER", ("IRON", "CRL"): "CDER", ("GRCE", "CRL"): "CDER", ("CING", "CRL"): "CDER", ("ACHV", "CRL"): "CDER"})

EVENT_FORMS = {"8-K", "6-K"}
EVENT_ITEMS = ("7.01", "8.01")
OFFERING_FORMS = ("424B", "S-3", "S-1", "F-3", "F-1", "SC TO")
CONFOUND_ITEMS = {"2.02": "EARNINGS", "1.01": "AGREEMENT", "2.03": "DEBT",
                  "3.02": "EQUITY_SALE", "5.02": "EXEC_CHANGE", "2.01": "ACQUISITION"}


def first_token(s):
    t = su.norm_name(s).split()
    return t[0] if t else ""


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
    diffs = []
    for pr_dt, raw_acc in rows:
        if pr_dt and raw_acc:
            dh = (raw_acc - pr_dt).total_seconds() / 3600
            if -2 <= dh <= 12:
                diffs.append(dh)
    if len(diffs) < 3:
        print(f"[timezone calibration] only {len(diffs)} comparable events -> default to ET")
        return "ET"
    med = statistics.median(diffs)
    mode = "UTC" if 3.0 <= med <= 6.5 else "ET"
    print(f"[timezone calibration] median 8-K acceptance minus press release time {med:+.2f}h (n={len(diffs)}) -> read EDGAR times as {mode}")
    return mode


def main():
    v = pd.read_csv(VERIFIED)
    a_raw, c_raw = load_raw()

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
                        flags.append("TIMING_LATE")
                        rep["timing_check"] = f"ERROR: public by {implied.date()} at the latest"
                    elif rec_react == implied:
                        rep["timing_check"] = "OK"
                        if su.session_label(f0.acc) != str(r.get("announcement_time", "")) and \
                                su.session_label(f0.acc) in ("pre_market", "after_hours"):
                            rep["timing_check"] = f"OK (recorded session {r.get('announcement_time')} vs filing {su.session_label(f0.acc)})"
                    else:
                        rep["timing_check"] = "INFO: 8-K filed after the reaction day (press release came first) - checked with PR time in notes"
            else:
                flags.append("NO_EVENT_FILING")
                rep["timing_check"] = "no 8-K/6-K - checked manually from press release"

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

            fpi, country = su.is_foreign_filer(subs, base)
            rep.update(foreign_filer=fpi, business_country=country)
            if fpi:
                flags.append("FOREIGN_FILER")

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

        appno, src = find_appno(r, a_raw, c_raw)
        recs = []
        for ap in (appno if isinstance(appno, list) else ([appno] if appno else [])):
            rr = su.drugsfda_app(ap)
            if rr:
                recs.append(rr)
        if not recs and dt_type == "APPROVAL":
            bt = re.match(r"[A-Za-z0-9]+", str(r["drug_name"]))
            recs = su.drugsfda_by_brand(bt.group(0)) if bt else []
            src = "openfda_brand" if recs else src
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

    print("\n=== Flag summary ===")
    from collections import Counter
    cnt = Counter(f for fl in rep_df["flags"] for f in str(fl).split())
    for f, n in cnt.most_common():
        tks = rep_df[rep_df["flags"].str.contains(re.escape(f), na=False)]
        print(f"  {f:<22} {n:>2}  {', '.join(tks.ticker + '(' + tks.decision_type.str[0] + ')')}")
    print("\n-> verification_report.csv, events_enriched.csv")
    print("   Only flagged events need a manual check. events_verified.csv is not modified.")


if __name__ == "__main__":
    main()
