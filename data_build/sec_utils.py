"""
sec_utils.py — 검증 자동화 공용 함수 (SEC EDGAR / openFDA / yfinance)

- 모든 요청은 .cache/ 에 저장 -> 두 번째 실행부터 빠르고, SEC 요청 제한도 안전
- SEC 규칙: User-Agent에 이름+이메일 필수, 초당 10회 이하
"""

import json
import os
import re
import time
import hashlib
from datetime import datetime, timedelta, date

import pandas as pd
import requests

# ↓↓↓ 여기 이메일만 네 걸로 바꿔 ↓↓↓
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "Minki Kim your_email@example.com")
# ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑

CACHE_DIR = ".cache"
SMALL_MAX = 2_000_000_000     # map_tickers.py와 동일: < $2B small
MID_MAX = 10_000_000_000      # < $10B mid, 이상 large
OPEN_T = (9, 30)
CLOSE_T = (16, 0)

os.makedirs(CACHE_DIR, exist_ok=True)
_last_call = {"sec": 0.0, "fda": 0.0}


# ---------------------------------------------------------------- HTTP + cache
def _cache_path(url):
    return os.path.join(CACHE_DIR, hashlib.md5(url.encode()).hexdigest() + ".json")


def get_json(url, kind="sec", retries=4):
    """kind: 'sec' (0.12s 간격, UA 필수) | 'fda' (0.3s 간격). 404면 None."""
    p = _cache_path(url)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    gap = 0.12 if kind == "sec" else 0.3
    headers = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"} if kind == "sec" else {}
    for attempt in range(retries):
        wait = gap - (time.time() - _last_call[kind])
        if wait > 0:
            time.sleep(wait)
        _last_call[kind] = time.time()
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 404:
            with open(p, "w") as f:
                json.dump(None, f)
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 403 and kind == "sec":
            raise SystemExit("SEC 403: sec_utils.py의 SEC_USER_AGENT에 이메일을 넣었는지 확인")
        r.raise_for_status()
        data = r.json()
        with open(p, "w") as f:
            json.dump(data, f)
        return data
    raise RuntimeError(f"요청 실패: {url}")


def get_text(url, retries=4):
    """SEC 문서 원문(html/txt) -> 태그 제거한 텍스트. 캐시."""
    p = _cache_path(url).replace(".json", ".txt")
    if os.path.exists(p):
        with open(p) as f:
            return f.read()
    for attempt in range(retries):
        wait = 0.12 - (time.time() - _last_call["sec"])
        if wait > 0:
            time.sleep(wait)
        _last_call["sec"] = time.time()
        r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
        if r.status_code == 404:
            return ""
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 * (attempt + 1))
            continue
        r.raise_for_status()
        txt = re.sub(r"<[^>]+>", " ", r.text)
        txt = re.sub(r"&nbsp;|&#160;", " ", txt)
        txt = re.sub(r"\s+", " ", txt)
        with open(p, "w") as f:
            f.write(txt)
        return txt
    return ""


# ---------------------------------------------------------------- names / CIK
SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "llc",
            "plc", "sa", "ag", "nv", "na", "lp", "holdings", "holding", "group", "the",
            "pharmaceuticals", "pharmaceutical", "pharma", "pharms", "pharm", "therapeutics",
            "theraps", "therap", "biosciences", "bioscience", "biopharma", "biopharmaceuticals",
            "biotherapeutics", "biotech", "biotechnology", "sciences", "science", "usa", "us",
            "international", "intl", "labs", "laboratories", "medicines", "medical", "health"}


def norm_name(s):
    s = re.sub(r"[^a-z0-9 ]", " ", str(s).lower())
    toks = [t for t in s.split() if t not in SUFFIXES]
    return " ".join(toks)


_ticker_map = None


def ticker_map():
    """{TICKER: (cik, title)} — SEC 현재 상장 목록(상장폐지 종목은 없음)."""
    global _ticker_map
    if _ticker_map is None:
        d = get_json("https://www.sec.gov/files/company_tickers.json")
        _ticker_map = {v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in d.values()}
    return _ticker_map


def cik_for_ticker(ticker, overrides=None):
    t = str(ticker).upper().strip()
    if overrides and t in overrides:
        return overrides[t]
    m = ticker_map()
    return m[t][0] if t in m else None


def fuzzy_cik(name, min_ratio=0.86):
    """회사명 -> (cik, ticker, title, score). 현재 상장사만."""
    from difflib import SequenceMatcher
    target = norm_name(name)
    if not target:
        return None
    best = None
    for tk, (cik, title) in ticker_map().items():
        n = norm_name(title)
        if not n:
            continue
        if n == target:
            return cik, tk, title, 1.0
        sc = SequenceMatcher(None, target, n).ratio()
        if best is None or sc > best[3]:
            best = (cik, tk, title, sc)
    return best if best and best[3] >= min_ratio else None


# ---------------------------------------------------------------- submissions
def submissions(cik):
    """회사 전체 공시 목록 DataFrame (recent + 과거 페이지 합침)."""
    base = get_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if base is None:
        return None, pd.DataFrame()
    frames = [pd.DataFrame(base["filings"]["recent"])]
    for f in base["filings"].get("files", []):
        d = get_json(f"https://data.sec.gov/submissions/{f['name']}")
        if d:
            frames.append(pd.DataFrame(d))
    df = pd.concat(frames, ignore_index=True)
    df["filingDate"] = pd.to_datetime(df["filingDate"])
    return base, df


def is_foreign_filer(sub_df, base):
    forms = set(sub_df["form"].astype(str)) if len(sub_df) else set()
    fpi = bool({"20-F", "6-K", "40-F"} & forms) and "10-K" not in forms
    country = ""
    try:
        country = base["addresses"]["business"].get("stateOrCountryDescription", "") or ""
    except Exception:
        pass
    return fpi, country


# ---------------------------------------------------------------- time zone
# EDGAR acceptanceDateTime 끝에 'Z'가 붙어 있지만 실제로는 동부시간(ET)인 경우가 많음.
# verify_events.py가 보도자료 시각이 적힌 이벤트들로 자동 보정해서 "ET" 또는 "UTC"로 정함.
ACCEPT_TZ = "ET"


def parse_acceptance(s):
    """EDGAR acceptanceDateTime -> naive ET datetime."""
    if not isinstance(s, str) or not s:
        return None
    dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    if ACCEPT_TZ == "UTC":
        from zoneinfo import ZoneInfo
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------- EDGAR full-text search
def fts_search(query, startdt, enddt, forms="8-K", max_hits=2000):
    """EDGAR 전문검색(2001~). -> list of dict(_id, _source). 100개씩 페이지."""
    from urllib.parse import quote
    out, frm = [], 0
    while frm < max_hits:
        url = (f"https://efts.sec.gov/LATEST/search-index?q={quote(query)}"
               f"&dateRange=custom&startdt={startdt}&enddt={enddt}&forms={forms}&from={frm}")
        try:
            d = get_json(url)
        except Exception as e:
            print(f"  [전문검색 실패] {e} -> 이 검색은 건너뜀")
            break
        hits = (d or {}).get("hits", {}).get("hits", [])
        if not hits:
            break
        out.extend(hits)
        total = d["hits"].get("total", {}).get("value", 0)
        frm += len(hits)
        if frm >= total:
            break
    return out


def parse_display_name(dn):
    """'RIGEL PHARMACEUTICALS INC  (RIGL)  (CIK 0001034842)' -> (name, ticker, cik)"""
    cik = re.search(r"CIK\s*0*(\d+)", dn)
    tks = re.findall(r"\(([A-Z.\-, ]{1,20})\)", dn)
    tk = tks[0].split(",")[0].strip() if tks else ""
    name = re.split(r"\s{2,}\(", dn)[0].strip()
    return name, tk, int(cik.group(1)) if cik else None


def find_cik_by_name(company, around_date, days=400):
    """상장폐지 종목용: 전문검색으로 회사명 -> CIK."""
    from difflib import SequenceMatcher
    core = norm_name(company)
    if not core:
        return None
    d = pd.Timestamp(around_date)
    hits = fts_search(f'"{core}"', (d - timedelta(days=days)).date().isoformat(),
                      (d + timedelta(days=60)).date().isoformat(), forms="8-K,10-K,20-F,6-K", max_hits=200)
    best = None
    for h in hits:
        for dn in h["_source"].get("display_names", []):
            name, tk, cik = parse_display_name(dn)
            sc = SequenceMatcher(None, core, norm_name(name)).ratio()
            if cik and (best is None or sc > best[2]):
                best = (cik, tk, sc, name)
    return best if best and best[2] >= 0.8 else None


# ---------------------------------------------------------------- trading days
_tdays = None


def trading_days():
    global _tdays
    if _tdays is None:
        import yfinance as yf
        h = yf.Ticker("XBI").history(start="2021-06-01", end=(date.today() + timedelta(days=5)).isoformat())
        _tdays = pd.DatetimeIndex(h.index.tz_localize(None).normalize()).unique().sort_values()
    return _tdays


def next_trading_day_on_or_after(d):
    td = trading_days()
    d = pd.Timestamp(d).normalize()
    i = td.searchsorted(d)
    return td[i] if i < len(td) else None


def reaction_day_from_time(dt):
    """공시 시각(ET) -> 시장이 처음 반응할 수 있는 거래일."""
    if dt is None:
        return None
    d = pd.Timestamp(dt.date())
    td = trading_days()
    is_tday = d in td
    if is_tday and (dt.hour, dt.minute) < CLOSE_T:
        return d                       # 장 전 또는 장중 -> 당일
    return next_trading_day_on_or_after(d + timedelta(days=1))


def session_label(dt):
    if dt is None:
        return ""
    if pd.Timestamp(dt.date()) not in trading_days():
        return "non_trading_day"
    hm = (dt.hour, dt.minute)
    if hm < OPEN_T:
        return "pre_market"
    if hm < CLOSE_T:
        return "market_hours"
    return "after_hours"


def shift_tday(d, n):
    td = trading_days()
    i = td.searchsorted(pd.Timestamp(d).normalize())
    j = i + n
    return td[j] if 0 <= j < len(td) else None


# ---------------------------------------------------------------- market cap
def shares_outstanding_asof(cik, asof, max_age_days=400):
    """XBRL 공시 발행주식수 중 asof 이전 가장 최근 값. (shares, end_date, tag)"""
    facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    if not facts:
        return None, None, None
    asof = pd.Timestamp(asof)
    cands = []
    for ns, tag in [("dei", "EntityCommonStockSharesOutstanding"),
                    ("us-gaap", "CommonStockSharesOutstanding"),
                    ("ifrs-full", "NumberOfSharesOutstanding"),
                    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic")]:
        try:
            units = facts["facts"][ns][tag]["units"]
        except KeyError:
            continue
        for unit, rows in units.items():
            if "share" not in unit.lower():
                continue
            for r in rows:
                end = pd.Timestamp(r["end"])
                if end <= asof and (asof - end).days <= max_age_days:
                    cands.append((end, r["val"], f"{ns}:{tag}"))
        if cands:
            break   # 우선순위 높은 태그에서 찾았으면 거기서 끝
    if not cands:
        return None, None, None
    end, val, tag = max(cands, key=lambda x: x[0])
    return float(val), end.date(), tag


def raw_close(ticker, d):
    """d 거래일 종가를 '당시 실제 가격'으로 (yfinance는 분할 조정돼 있어서 되돌림)."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    d = pd.Timestamp(d)
    try:
        h = t.history(start=(d - timedelta(days=7)).date().isoformat(),
                      end=(d + timedelta(days=1)).date().isoformat(), auto_adjust=False)
    except Exception:
        return None
    if h.empty:
        return None
    h.index = h.index.tz_localize(None).normalize()
    h = h[h.index <= d]
    if h.empty:
        return None
    px = float(h["Close"].iloc[-1])
    try:
        sp = t.splits
        sp.index = sp.index.tz_localize(None)
        for when, ratio in sp.items():
            if when > d and ratio > 0:
                px *= float(ratio)
    except Exception:
        pass
    return px


def cap_group(mcap):
    if mcap is None or pd.isna(mcap):
        return ""
    return "small" if mcap < SMALL_MAX else ("mid" if mcap < MID_MAX else "large")


# ---------------------------------------------------------------- openFDA
def drugsfda_app(appno):
    """'NDA 218038' / 'NDA218038' -> openFDA 레코드 (없으면 None: 미승인 또는 CBER)."""
    a = re.sub(r"\s+", "", str(appno)).upper()
    if not a or a == "NAN":
        return None
    a = re.sub(r"^BL(?=\d)", "BLA", a)          # CRL DB의 'BL 125807'(CBER 표기) -> BLA125807
    d = get_json(f'https://api.fda.gov/drug/drugsfda.json?search=application_number:"{a}"&limit=1', kind="fda")
    if not d or not d.get("results"):
        return None
    return d["results"][0]


def novelty_from_drugsfda(rec):
    """-> (novelty, class_code_desc). novelty: NME / novel_biologic / non-NME / unknown"""
    if rec is None:
        return "unknown", ""
    subs = rec.get("submissions", [])
    orig = [s for s in subs if s.get("submission_type") == "ORIG"] or subs
    desc = ""
    for s in orig:
        desc = s.get("submission_class_code_description") or s.get("submission_class_code") or ""
        if desc:
            break
    app = rec.get("application_number", "")
    if app.startswith("BLA"):
        return "novel_biologic", desc or "BLA (CDER)"
    if re.search(r"type\s*1\b|new molecular entity", desc, re.I):
        return "NME", desc
    if desc:
        return "non-NME", desc
    return "unknown", ""


def center_guess(appno, in_drugsfda):
    a = re.sub(r"\s+", "", str(appno)).upper()
    if re.match(r"^BL\d", a):
        return "CBER"                                # FDA CRL DB는 CBER 제품을 'BL'로 표기
    if a.startswith("NDA"):
        return "CDER"
    if a.startswith("BLA"):
        if in_drugsfda:
            return "CDER"
        num = re.sub(r"\D", "", a)
        return "CDER" if num.startswith("761") else "CBER?"
    return ""


# ---------------------------------------------------------------- v2 추가: 브랜드 검색 / 기존 성분 확인
def drugsfda_by_brand(brand):
    """브랜드명 -> openFDA 레코드 목록 (신청번호를 raw에서 못 찾을 때)."""
    b = re.sub(r"[^A-Za-z0-9 ]", "", str(brand)).upper().strip()
    if not b:
        return []
    d = get_json(f'https://api.fda.gov/drug/drugsfda.json?search=openfda.brand_name:"{b}"&limit=10', kind="fda")
    return (d or {}).get("results", [])


def orig_approval_date(rec):
    for s in rec.get("submissions", []):
        if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP":
            return s.get("submission_status_date", "")
    return ""


def ingredient_previously_approved(rec):
    """같은 성분(바이오 접미사 -xxxx 제거)이 더 먼저 승인된 다른 신청이 있으면 True.
    예: bevacizumab-vikg(OTLK) -> Avastin 존재 -> 기존 성분."""
    names = (rec.get("openfda") or {}).get("generic_name", [])
    if not names:
        return None
    base = re.sub(r"-[a-z]{4}$", "", names[0].lower().strip())
    base = base.split(" and ")[0].split(",")[0].strip()
    me, my_date = rec.get("application_number"), orig_approval_date(rec)
    d = get_json(f'https://api.fda.gov/drug/drugsfda.json?search=openfda.generic_name:"{base}"&limit=50', kind="fda")
    for r in (d or {}).get("results", []):
        if r.get("application_number") == me:
            continue
        od = orig_approval_date(r)
        if od and my_date and od < my_date:
            return True
    return False
