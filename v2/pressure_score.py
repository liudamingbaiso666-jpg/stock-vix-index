"""Experimental cross-sectional stock selloff pressure score (0-100).
Not option-implied VIX; not calibrated predictive probability.
Input: 52-week scanner CSV. Output: aligned daily ranking and audit JSON.
"""
import argparse
import json
from pathlib import Path
import pandas as pd

def compute(path):
    df=pd.read_csv(path,dtype={"code":str})
    cols=["date","code","name","distance_pct","ret_5d_pct","ret_20d_pct","volume_ratio_20d"]
    if df.empty or any(c not in df for c in cols):
        raise ValueError("Missing required market data")
    session=df.date.mode().iloc[0]
    data=df[df.date==session].copy()
    if len(data)<.95*len(df):
        raise ValueError("Too many stale observations")
    for c in cols[3:]:
        data[c]=pd.to_numeric(data[c],errors="coerce")
    data=data.dropna(subset=cols[3:])
    if len(data)<100:
        raise ValueError("Insufficient cross-section for percentile score")
    # Each component is a 0..100 cross-sectional rank, not an implied volatility.
    data["near_low_rank"]=(-data.distance_pct).rank(pct=True)*100
    data["short_drop_rank"]=(-data.ret_5d_pct).rank(pct=True)*100
    data["medium_drop_rank"]=(-data.ret_20d_pct).rank(pct=True)*100
    # Volume confirms selling pressure only if the stock actually fell in 5 days.
    sell_volume=data.volume_ratio_20d.clip(lower=0,upper=5).where(data.ret_5d_pct<0,0)
    data["sell_volume_rank"]=sell_volume.rank(pct=True)*100
    data["pressure_score"]=(.30*data.near_low_rank+.30*data.short_drop_rank+
                            .25*data.medium_drop_rank+.15*data.sell_volume_rank).round(1)
    data["score_version"]="pressure_v1_experimental"
    data=data.sort_values(["pressure_score","code"],ascending=[False,True])
    out=Path(path).parent
    columns=["code","name","date","close","distance_pct","ret_5d_pct","ret_20d_pct",
             "volume_ratio_20d","quality_status","pressure_score","score_version"]
    columns=[c for c in columns if c in data]
    data[columns].to_csv(out/f"pressure_{session}.csv",index=False,encoding="utf-8-sig")
    audit={"session":session,"input_rows":len(df),"valid_aligned":len(data),
           "stale_rows":len(df)-len(df[df.date==session]),
           "formula":{"near_low_rank":0.30,"short_drop_rank":0.30,
                      "medium_drop_rank":0.25,"sell_volume_rank":0.15},
           "method":"Cross-sectional percentile ranks among aligned candidate stocks",
           "limitations":["NOT VIX or implied volatility","NOT historically calibrated",
                          "NOT a valuation or buy recommendation",
                          "Comparability across dates depends on universe stability"],
           "top20":json.loads(data[columns].head(20).to_json(orient="records",force_ascii=False))}
    (out/f"pressure_{session}.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in audit.items() if k!="top20"},ensure_ascii=False),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("csv")
    compute(parser.parse_args().csv)
