import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 검증 완료된 이벤트만 읽어옴
events = pd.read_csv("events_verified.csv")

# 벤치마크는 한 번만 받아서 재사용 (SPY = 시장, XBI = 바이오텍 섹터)
def get_benchmarks(start, end):
    spy = yf.Ticker("SPY").history(start=start, end=end)["Close"]
    xbi = yf.Ticker("XBI").history(start=start, end=end)["Close"]

    spy.index = spy.index.tz_localize(None)
    xbi.index = xbi.index.tz_localize(None)

    return spy, xbi


# 거래일 기준으로 이벤트일 직전/직후를 잡아 abnormal return을 계산
def compute_row(ticker, market_reaction_date):
    start = market_reaction_date - timedelta(days=90)
    end = market_reaction_date + timedelta(days=90)

    stock = yf.Ticker(ticker).history(start=start, end=end)["Close"]
    if stock.empty:
        return None

    spy, xbi = get_benchmarks(start, end)
    if spy.empty or xbi.empty:
        return None

    stock.index = stock.index.tz_localize(None)
    spy.index = spy.index.tz_localize(None)
    xbi.index = xbi.index.tz_localize(None)

    # stock, SPY, XBI를 같은 날짜 기준으로 합침
    data = pd.DataFrame({
        "stock": stock,
        "spy": spy,
        "xbi": xbi
    }).dropna()

    if data.empty:
        return None

    # market_reaction_date 이후 첫 번째 거래일을 event trading day로 잡음
    event_candidates = data[data.index >= pd.Timestamp(market_reaction_date)]
    if event_candidates.empty:
        return None

    event_trading_day = event_candidates.index[0]
    event_idx = data.index.get_loc(event_trading_day)

    # 필요한 trading-day index
    idx_minus_30 = event_idx - 30
    idx_minus_1 = event_idx - 1
    idx_plus_1 = event_idx + 1
    idx_plus_30 = event_idx + 30

    # 데이터가 부족하면 skip
    if idx_minus_30 < 0 or idx_minus_1 < 0 or idx_plus_30 >= len(data):
        return None

    def window_return(start_idx, end_idx):
        start_price = data.iloc[start_idx]
        end_price = data.iloc[end_idx]

        stock_return = (end_price["stock"] - start_price["stock"]) / start_price["stock"] * 100
        spy_return = (end_price["spy"] - start_price["spy"]) / start_price["spy"] * 100
        xbi_return = (end_price["xbi"] - start_price["xbi"]) / start_price["xbi"] * 100

        return {
            "stock_return": stock_return,
            "spy_return": spy_return,
            "xbi_return": xbi_return,
            "abn_return_spy": stock_return - spy_return,
            "abn_return_xbi": stock_return - xbi_return
        }

    # Window convention:
    # pre: t-30 close to t-1 close
    # announcement: t-1 close to t+1 close
    # post: t+1 close to t+30 close
    pre = window_return(idx_minus_30, idx_minus_1)
    announcement = window_return(idx_minus_1, idx_plus_1)
    post = window_return(idx_plus_1, idx_plus_30)

    return {
        "event_trading_day": event_trading_day.date(),

        "pre_raw_return": round(pre["stock_return"], 2),
        "pre_spy_return": round(pre["spy_return"], 2),
        "pre_xbi_return": round(pre["xbi_return"], 2),
        "pre_abn_return_spy": round(pre["abn_return_spy"], 2),
        "pre_abn_return_xbi": round(pre["abn_return_xbi"], 2),

        "announcement_raw_return": round(announcement["stock_return"], 2),
        "announcement_spy_return": round(announcement["spy_return"], 2),
        "announcement_xbi_return": round(announcement["xbi_return"], 2),
        "announcement_abn_return_spy": round(announcement["abn_return_spy"], 2),
        "announcement_abn_return_xbi": round(announcement["abn_return_xbi"], 2),

        "post_raw_return": round(post["stock_return"], 2),
        "post_spy_return": round(post["spy_return"], 2),
        "post_xbi_return": round(post["xbi_return"], 2),
        "post_abn_return_spy": round(post["abn_return_spy"], 2),
        "post_abn_return_xbi": round(post["abn_return_xbi"], 2),
    }


results = []
skipped = []

for _, row in events.iterrows():
    ticker = str(row["ticker"]).strip()

    try:
        event_date = str(row["event_date"]).strip()
        market_reaction_date = datetime.strptime(
            str(row["market_reaction_date"]).strip(),
            "%Y-%m-%d"
        )
    except ValueError:
        print(f"{ticker}: bad market_reaction_date '{row.get('market_reaction_date', '')}' - skipped")
        skipped.append({
            "ticker": ticker,
            "company": row.get("company", ""),
            "event_date": row.get("event_date", ""),
            "market_reaction_date": row.get("market_reaction_date", ""),
            "reason": "bad market_reaction_date"
        })
        continue

    out = compute_row(ticker, market_reaction_date)

    if out is None:
        skipped.append({
            "ticker": ticker,
            "company": row.get("company", ""),
            "event_date": row.get("event_date", ""),
            "market_reaction_date": row.get("market_reaction_date", ""),
            "reason": "no price data from yfinance"
        })
        print(f"{ticker} ({row['event_date']} / reaction {row['market_reaction_date']}): no data")
        continue

    results.append({
        "ticker": ticker,
        "company": row["company"],
        "drug_name": row.get("drug_name", ""),
        "event_date": row["event_date"],
        "announcement_time": row.get("announcement_time", ""),
        "decision_type": row.get("decision_type", ""),
        "event_direction": row.get("event_direction", ""),
        "market_reaction_date": row["market_reaction_date"],
        "event_trading_day": out["event_trading_day"],
        "market_cap_group": row["market_cap_group"],

        "pre_raw_return": out["pre_raw_return"],
        "pre_abn_return_spy": out["pre_abn_return_spy"],
        "pre_abn_return_xbi": out["pre_abn_return_xbi"],

        "announcement_raw_return": out["announcement_raw_return"],
        "announcement_abn_return_spy": out["announcement_abn_return_spy"],
        "announcement_abn_return_xbi": out["announcement_abn_return_xbi"],

        "post_raw_return": out["post_raw_return"],
        "post_abn_return_spy": out["post_abn_return_spy"],
        "post_abn_return_xbi": out["post_abn_return_xbi"],
    })

    print(f"{ticker} ({row['event_date']} / reaction {row['market_reaction_date']}): "
          f"pre {out['pre_abn_return_xbi']:+.2f}% | "
          f"announcement {out['announcement_abn_return_xbi']:+.2f}% | "
          f"post {out['post_abn_return_xbi']:+.2f}% vs XBI")


# 결과 저장
df = pd.DataFrame(results)
df.to_csv("event_returns.csv", index=False)

skipped_df = pd.DataFrame(skipped)
skipped_df.to_csv("skipped_events.csv", index=False)

print("\n=== Summary ===")
print(f"Events with data: {len(df)} / {len(events)}")

if len(df) > 0:
    print(f"Avg pre-event abnormal return (vs XBI): {df['pre_abn_return_xbi'].mean():+.2f}%")
    print(f"Avg announcement abnormal return (vs XBI): {df['announcement_abn_return_xbi'].mean():+.2f}%")
    print(f"Avg post-event abnormal return (vs XBI): {df['post_abn_return_xbi'].mean():+.2f}%")

    print(f"Positive announcement events (vs XBI): "
          f"{(df['announcement_abn_return_xbi'] > 0).sum()}/{len(df)}")

    for grp in ["small", "mid"]:
        sub = df[df["market_cap_group"] == grp]
        if len(sub) > 0:
            print(f"  {grp}: avg announcement vs XBI "
                  f"{sub['announcement_abn_return_xbi'].mean():+.2f}% (n={len(sub)})")

    # split by event type once CRL events are present (harmless with only APPROVAL)
    if "decision_type" in df.columns and df["decision_type"].nunique() > 1:
        print("\n=== By decision_type (announcement window vs XBI) ===")
        for dtype, sub in df.groupby("decision_type"):
            print(f"  {dtype}: mean {sub['announcement_abn_return_xbi'].mean():+.2f}% | "
                  f"median {sub['announcement_abn_return_xbi'].median():+.2f}% (n={len(sub)})")

print("\nSaved to event_returns.csv")
print("Saved to skipped_events.csv")