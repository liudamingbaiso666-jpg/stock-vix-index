"""V2.6 point-in-time margin-of-safety research.

Valuation inputs must be sourced separately and contain publication/availability dates.
Never infer fair value from historical price or fabricate missing values.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

HORIZONS=(5,10,20,60)
PCTS=(10,25,50,75,90)
REQUIRED={"code","asof_date","available_date","conservative_value","method","source"}
COLUMNS=["code","asof_date","available_date","conservative_value","method","source"]
def describe(a):
    a=np.asarray(a,dtype=float)
    a=a[np.isfinite(a)]
    return {"n":len(a),"p":{str(p):round(float(np.percentile(a,p)),3) for p in PCTS}} if len(a) else {"n":0}

def study(df,values):
    df=df.sort_index().copy()
    values=values.sort_values("available_date")
    # At every event, merge only valuations published on or before that date.
    left=df.reset_index().rename(columns={"日期":"event_date"})
    left["event_date"]=pd.to_datetime(left["event_date"])
    joined=pd.merge_asof(left.sort_values("event_date"),values.sort_values("available_date"),
                         left_on="event_date",right_on="available_date",direction="backward")
    joined["age_days"]=(joined["event_date"]-joined["asof_date"]).dt.days
    # Avoid stale estimates, future-dated financial periods, zero or negative fair values.
    valid=(joined["conservative_value"]>0)&joined["asof_date"].le(joined["event_date"])&joined["age_days"].between(0,550)
    joined["margin"]=np.where(valid,1-joined["close"]/joined["conservative_value"],np.nan)
    # Only independent first-crossing events, with a 20-session cooldown per threshold.
    joined["event_threshold"]=np.nan
    for threshold in (70,80,90):
        flag=joined["panic_score"].ge(threshold).fillna(False)
        crossings=np.flatnonzero((flag & ~flag.shift(1,fill_value=False)).to_numpy())
        last=-10**9
        for i in crossings:
            if i-last>20:
                joined.loc[i,"event_threshold"]=threshold if pd.isna(joined.loc[i,"event_threshold"]) else max(threshold,joined.loc[i,"event_threshold"])
                last=i
    joined["margin_bucket"]=pd.cut(joined["margin"],bins=[-np.inf,0,.15,.30,np.inf],
                    labels=["negative","0_to_15","15_to_30","above_30"],right=False)
    joined["panic_bucket"]=pd.cut(joined["panic_score"],bins=[0,70,80,90,101],
                    labels=["below_70","70_to_80","80_to_90","90_plus"],right=False)
    # Forward maximum adverse excursion from the day AFTER the signal to each horizon.
    prices=df["close"].to_numpy(dtype=float)
    for h in HORIZONS:
        mae=np.full(len(prices),np.nan)
        for i in range(len(prices)-h):
            future=prices[i+1:i+h+1]
            if np.isfinite(prices[i]) and prices[i]>0 and np.isfinite(future).all():
                mae[i]=100*(np.min(future)/prices[i]-1)
        joined[f"mae_{h}d"]=mae
    output={"coverage":{"trading_days":len(joined),"days_with_valid_valuation":int(joined["margin"].notna().sum()),"independent_event_days_with_valuation":int((joined["margin"].notna() & joined["event_threshold"].notna()).sum())},
            "groups":{}}
    for (panic,margin),g in joined.dropna(subset=["event_threshold","margin_bucket"]).groupby(["event_threshold","margin_bucket"],observed=True):
        group={}
        for h in HORIZONS:
            excess=g[f"excess_{h}d"]
            returns=g[f"future_{h}d"]
            mae=g[f"mae_{h}d"]
            group[str(h)]={"return":describe(returns),"excess":describe(excess),
                           "max_adverse_excursion":describe(mae),
                           "beat_benchmark_ratio":round(float((excess.dropna()>0).mean()),4) if excess.notna().any() else None}
        output["groups"][f"{panic}|{margin}"]={"observations":len(g),"horizons":group}
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",type=Path,required=True)
    p.add_argument("--valuations",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    output={"version":"v2_6_point_in_time_margin","status":"not_calibrated","stocks":{},"errors":{},
            "limitations":["No valid historical valuations means NO investment inference.",
              "A single as-of valuation must not be carried past 550 days.",
              "Conservative value assumptions, financial statement release date and data vintage require audit.",
              "Events have a 20-session cooldown per threshold, but 60-session outcome windows may overlap.",
              "Maximum adverse excursion is close-to-close, not intraday drawdown.",
              "Stock-specific valuation methods are not comparable until standardized.",
              "Historical adjusted prices can be revised and must match valuation adjustment basis."]}
    if not a.valuations.exists():
        output["status"]="awaiting_historical_valuations"
    else:
        v=pd.read_csv(a.valuations,dtype={"code":str},encoding="utf-8-sig")
        missing=REQUIRED-set(v.columns)
        if missing:
            raise ValueError(f"Missing valuation fields: {missing}")
        if len(v):
            v["asof_date"]=pd.to_datetime(v["asof_date"],errors="raise")
            v["available_date"]=pd.to_datetime(v["available_date"],errors="raise")
            v["conservative_value"]=pd.to_numeric(v["conservative_value"],errors="raise")
            if (v["available_date"]<v["asof_date"]).any() or (v["conservative_value"]<=0).any():
                raise ValueError("Invalid valuation dates or values")
            if v[COLUMNS].isna().any().any() or (v["source"].astype(str).str.strip()=="").any():
                raise ValueError("Valuation sources and all fields required")
            for path in sorted(a.input_dir.glob("*_panic.csv")):
                code=path.name.split("_")[0]
                if not (v.code==code).any():
                    continue
                try:
                    df=pd.read_csv(path,encoding="utf-8-sig",parse_dates=["日期"]).set_index("日期")
                    output["stocks"][code]=study(df,v[v.code==code].copy())
                except Exception as exc:
                    output["errors"][code]=f"{type(exc).__name__}: {exc}"
            output["status"]="research_ready" if output["stocks"] and not output["errors"] and any(x["coverage"]["independent_event_days_with_valuation"]>0 for x in output["stocks"].values()) else "incomplete"
        else:
            output["status"]="awaiting_historical_valuations"
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":output["status"],"stocks":list(output["stocks"]),"errors":output["errors"]},ensure_ascii=False))
    if output["errors"]:
        raise RuntimeError("Valuation research incomplete")

if __name__=="__main__":
    main()
