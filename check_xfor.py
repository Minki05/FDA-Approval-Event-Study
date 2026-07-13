import yfinance as yf

x = yf.Ticker("XFOR").history(start="2024-03-01", end="2024-05-06")["Close"]
x.index = x.index.tz_localize(None)

pct = x.pct_change().mul(100).round(2)
print(pct.tail(35).to_string())          # 승인 전후 일별 % 변화
print()
print("4/26 종가:", round(x.loc[:"2024-04-26"].iloc[-1], 3))
print("4/29 종가:", round(x.loc["2024-04-29"], 3))