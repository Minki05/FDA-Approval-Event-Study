import yfinance as yf
import pandas as pd
import requests

# --- Stock Data ---
tickers = ["MRNA", "BNTX", "NVAX", "BIIB", "REGN"]

stock_data = {}
for ticker in tickers:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="2y")
    stock_data[ticker] = hist
    print(f"\n{ticker} last 5 days:")
    print(hist.tail())

# --- FDA BLA Data (Biologics only) ---
print("\n\n--- FDA BLA Applications ---")

url = "https://api.fda.gov/drug/drugsfda.json"
params = {
    "search": "application_number:BLA*",
    "limit": 10
}

response = requests.get(url, params=params)
data = response.json()

for result in data["results"]:
    app_num = result.get("application_number", "N/A")
    sponsor = result.get("sponsor_name", "N/A")
    print(f"{app_num} | {sponsor}")