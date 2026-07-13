import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta


# 이벤트 윈도우의 raw return에서 SPY/XBI return을 빼서 abnormal return을 계산
def get_abnormal_return(ticker, event_date):
    start = event_date - timedelta(days=15)
    end = event_date + timedelta(days=15)

    stock = yf.Ticker(ticker).history(start=start, end=end)['Close']
    spy = yf.Ticker("SPY").history(start=start, end=end)['Close']
    xbi = yf.Ticker("XBI").history(start=start, end=end)['Close']

    if stock.empty or spy.empty or xbi.empty:
        return None

    # 타임존 제거해서 날짜 비교 가능하게 맞춤
    stock.index = stock.index.tz_localize(None)
    spy.index = spy.index.tz_localize(None)
    xbi.index = xbi.index.tz_localize(None)

    # 이벤트일 직전 거래일과 직후 거래일을 기준점으로 잡음
    pre_dates = stock[stock.index < pd.Timestamp(event_date)].index
    post_dates = stock[stock.index >= pd.Timestamp(event_date)].index
    if len(pre_dates) == 0 or len(post_dates) == 0:
        return None
    pre, post = pre_dates[-1], post_dates[0]

    # 같은 구간의 종목/벤치마크 수익률 계산
    def ret(series):
        if pre not in series.index or post not in series.index:
            return None
        return (series[post] - series[pre]) / series[pre] * 100

    r_stock, r_spy, r_xbi = ret(stock), ret(spy), ret(xbi)
    if r_stock is None or r_spy is None or r_xbi is None:
        return None

    return {
        "raw_return": r_stock,
        "abn_return_spy": r_stock - r_spy,
        "abn_return_xbi": r_stock - r_xbi,
    }


company_ticker = {
    "OMEROS CORP": "OMER",
    "MACROGENICS INC": "MGNX",
    "SANOFI AVENTIS US": "SNY",
    "UCB INC": "UCB",
    "BIOGEN IDEC": "BIIB",
    "PFIZER INC": "PFE",
    "NOVO NORDISK INC": "NVO",
    "AMGEN": "AMGN",
    "ELI LILLY AND CO": "LLY",
    "ASTRAZENECA UK LTD": "AZN",
    "ALEXION PHARM": "ALXN",
}

events = [
    {"sponsor": "OMEROS CORP", "approval_date": "20251223"},
    {"sponsor": "MACROGENICS INC", "approval_date": "20201216"},
    {"sponsor": "BIOGEN IDEC", "approval_date": "20041123"},
    {"sponsor": "PFIZER INC", "approval_date": "20190627"},
    {"sponsor": "AMGEN", "approval_date": "20100601"},
    {"sponsor": "ELI LILLY AND CO", "approval_date": "20200615"},
    {"sponsor": "ASTRAZENECA UK LTD", "approval_date": "20170501"},
    {"sponsor": "ALEXION PHARM", "approval_date": "20181221"},
]

results = []

for event in events:
    sponsor = event["sponsor"]
    ticker = company_ticker.get(sponsor)
    if not ticker:
        continue

    date = datetime.strptime(event["approval_date"], "%Y%m%d")

    abn = get_abnormal_return(ticker, date)
    if abn is None:
        print(f"{sponsor} ({ticker}): no data")
        continue

    results.append({
        "sponsor": sponsor,
        "ticker": ticker,
        "approval_date": date,
        "raw_return": abn["raw_return"],
        "abn_return_spy": abn["abn_return_spy"],
        "abn_return_xbi": abn["abn_return_xbi"],
    })

    print(f"{sponsor} ({ticker}): raw {abn['raw_return']:+.2f}% | "
          f"vs SPY {abn['abn_return_spy']:+.2f}% | vs XBI {abn['abn_return_xbi']:+.2f}%")

# 결과 요약
df = pd.DataFrame(results)
print(f"\nAverage abnormal return (vs XBI): {df['abn_return_xbi'].mean():+.2f}%")
print(f"Positive events (vs XBI): {(df['abn_return_xbi'] > 0).sum()}/{len(df)}")

# abnormal return 막대 차트 (XBI 기준)
plt.figure(figsize=(10, 6))
colors = ['green' if x > 0 else 'red' for x in df['abn_return_xbi']]
plt.bar(df['ticker'], df['abn_return_xbi'], color=colors)
plt.axhline(y=0, color='black', linewidth=0.8)
plt.title('Abnormal Return on FDA Approval Day (vs XBI)')
plt.xlabel('Ticker')
plt.ylabel('Abnormal Return (%)')
plt.tight_layout()
plt.savefig('fda_abnormal_returns.png')
plt.show()
print("\nChart saved as fda_abnormal_returns.png")


# 소형주 30일 가격 흐름 차트
small_cap_events = [
    {"ticker": "ACAD", "approval_date": "20120601", "name": "Acadia Pharmaceuticals"},
    {"ticker": "SRPT", "approval_date": "20160919", "name": "Sarepta Therapeutics"},
    {"ticker": "BMRN", "approval_date": "20140212", "name": "BioMarin Pharmaceutical"},
    {"ticker": "ALNY", "approval_date": "20180810", "name": "Alnylam Pharmaceuticals"},
]

plt.figure(figsize=(12, 8))

for event in small_cap_events:
    ticker = event["ticker"]
    date = datetime.strptime(event["approval_date"], "%Y%m%d")
    start = date - timedelta(days=40)
    end = date + timedelta(days=40)

    hist = yf.Ticker(ticker).history(start=start, end=end)
    if hist.empty:
        continue

    # 승인일 기준 -30 ~ +30일로 정규화
    hist = hist.reset_index()
    hist['days'] = (hist['Date'].dt.tz_localize(None) - date).dt.days
    hist = hist[(hist['days'] >= -30) & (hist['days'] <= 30)]

    # 승인 전날 종가를 기준으로 수익률 정규화
    baseline = hist[hist['days'] < 0]['Close'].iloc[-1]
    hist['normalized'] = ((hist['Close'] - baseline) / baseline) * 100

    plt.plot(hist['days'], hist['normalized'], label=event['name'])

plt.axvline(x=0, color='black', linewidth=1, linestyle='--', label='FDA Approval')
plt.axhline(y=0, color='gray', linewidth=0.5)
plt.title('Stock Price Movement Around FDA Approval (-30 to +30 days)')
plt.xlabel('Days relative to FDA Approval')
plt.ylabel('Return (%)')
plt.legend()
plt.tight_layout()
plt.savefig('fda_30day_movement.png')
plt.show()
print("Chart saved as fda_30day_movement.png")