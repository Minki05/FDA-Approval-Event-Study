import yfinance as yf
import pandas as pd

# FDA 데이터에 나온 회사들 티커 매핑
company_ticker = {
    "THROMBOGENICS, INC": "THR.BR",
    "OMEROS CORP": "OMER",
    "SEATTLE GENETICS": "SGEN",
    "GENENTECH": None,  # 로슈 자회사, 비상장
    "MACROGENICS INC": "MGNX",
    "SANOFI AVENTIS US": "SNY",
    "UCB INC": "UCB.BR",
    "BIOGEN IDEC": "BIIB",
    "PFIZER INC": "PFE",
    "NOVO NORDISK INC": "NVO",
    "GENZYME": None,  # 사노피 인수, 비상장
    "SAMSUNG BIOEPIS CO LTD": None,  # 비상장
}

# 상장된 회사만 필터링하고 주가 확인
print("Checking tickers...\n")
valid = {}
for company, ticker in company_ticker.items():
    if ticker is None:
        print(f"{company}: not listed")
        continue
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get("shortName", "N/A")
        print(f"{company}: {ticker} -> {name}")
        valid[company] = ticker
    except:
        print(f"{company}: {ticker} -> failed")

print(f"\nValid tickers: {len(valid)}")
