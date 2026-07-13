import pandas as pd
a = pd.read_csv("events_verified.csv")
c = pd.read_csv("events_crl_clean.csv")
pd.concat([a, c]).to_csv("events_verified.csv", index=False)
print(f"합침 완료: approval {len(a)} + CRL {len(c)} = {len(a)+len(c)}행")