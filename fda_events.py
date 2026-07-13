import requests
import pandas as pd

# FDA BLA 승인 데이터 가져오기
url = "https://api.fda.gov/drug/drugsfda.json"
params = {
    "search": "application_number:BLA*",
    "limit": 100
}

response = requests.get(url, params=params)
data = response.json()

# 데이터 정리
events = []
for result in data["results"]:
    app_num = result.get("application_number", "N/A")
    sponsor = result.get("sponsor_name", "N/A")
    
    # 승인 날짜 가져오기
    submissions = result.get("submissions", [])
    for sub in submissions:
        if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP":
            approval_date = sub.get("submission_status_date", "N/A")
            events.append({
                "app_number": app_num,
                "sponsor": sponsor,
                "approval_date": approval_date
            })

# DataFrame으로 변환
df = pd.DataFrame(events)
print(df.head(20))
print(f"\nTotal events: {len(df)}")