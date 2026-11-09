"""Simple P/R out-of-sample diagnostic using archived daily signal snapshots.
No threshold optimization. Quartiles are descriptive, not trading rules.
Requires independent adjusted close history with code,date,close.
"""
import argparse
import json
from pathlib import Path
import pandas as pd

HORIZONS=(1,3,5,10,20)

def evaluate(snapshot_dir, prices_csv, output, calendar_csv=None):
    snapshots=[]
    for f in sorted(Path(snapshot_dir).glob("low52_*.csv")):
        d=pd.read_csv(f,dtype={"code":str})
        need={"code","date","repair_score","repair_stage"}
        if not need.issubset(d):continue
        pf=f.with_name(f.name.replace("low52_","pressure_"))
        if not pf.exists():continue
        p=pd.read_csv(pf,dtype={"code":str})
        if not {"code","date","pressure_score"}.issubset(p):continue
        d=d.merge(p[["code","date","pressure_score"]],on=["code","date"],validate="one_to_one")
        optional=["selloff_context","natr_20","cmf_20","obv_5d_change"]
        for col in optional:
            if col not in d.columns: d[col]=pd.NA
        snapshots.append(d[["code","date","repair_score","repair_stage","pressure_score",*optional]])
    if not snapshots:raise ValueError("No archived matching P/R daily snapshots")
    s=pd.concat(snapshots,ignore_index=True)
    if s.duplicated(["code","date"]).any():
        raise ValueError("Duplicate stock/date snapshots: resolve before backtest")
    p=pd.read_csv(prices_csv,dtype={"code":str})
    if not {"code","date","close"}.issubset(p):raise ValueError("Need code,date,close")
    p["date"]=pd.to_datetime(p.date)
    p["close"]=pd.to_numeric(p.close,errors="coerce")
    p=p.dropna(subset=["date","close"]).sort_values(["code","date"])
    if p.duplicated(["code","date"]).any():raise ValueError("Duplicate stock/date prices")
    # A sparse archive must not silently turn row offsets into trading-day horizons.
    # Require an independent trading-session calendar for forward-return interpretation.
    if calendar_csv is None:
        raise ValueError("Trading-session calendar required (--calendar). Sparse snapshots are not sufficient.")
    calendar = pd.read_csv(calendar_csv)
    if "date" not in calendar:
        raise ValueError("Calendar requires date column")
    sessions = pd.DatetimeIndex(pd.to_datetime(calendar["date"], errors="raise").drop_duplicates().sort_values())
    if len(sessions) < max(HORIZONS) + 1:
        raise ValueError("Calendar too short for 20-session horizon")
    if not p["date"].isin(sessions).all():
        raise ValueError("Price observations outside trading calendar")
    p["ix"]=p["date"].map(pd.Series(range(len(sessions)), index=sessions))
    s["date"]=pd.to_datetime(s.date)
    out=s.merge(p[["code","date","ix","close"]].rename(columns={"close":"entry_close"}),
                on=["code","date"],validate="one_to_one")
    for h in HORIZONS:
        future=p[["code","ix","close"]].copy()
        future["ix"]-=h
        future=future.rename(columns={"close":f"future_{h}"})
        out=out.merge(future,on=["code","ix"],how="left",validate="many_to_one")
        out[f"ret_{h}d_pct"]=(out[f"future_{h}"]/out.entry_close-1)*100
    # Within-date quartiles avoid tuning arbitrary score cutoffs; tied scores can collapse bins.
    for key in ("pressure_score","repair_score"):
        out[key]=pd.to_numeric(out[key],errors="coerce")
        out[key+"_quartile"]=out.groupby("date")[key].transform(
            lambda x: pd.qcut(x.rank(method="first"),4,labels=False)+1 if len(x)>=4 else pd.Series(pd.NA,index=x.index))
    out["group"]=out.pressure_score_quartile.astype("Int64").astype(str)+"P/"+out.repair_score_quartile.astype("Int64").astype(str)+"R"
    rows=[]
    for (group,h),g in (( (group,h),v) for group,v in out.groupby("group") for h in HORIZONS):
        v=g[f"ret_{h}d_pct"].dropna()
        if len(v)<30:continue
        rows.append({"group":group,"horizon":h,"n":int(len(v)),
                     "up_pct":round(float((v>0).mean()*100),2),
                     **{f"p{q}":round(float(v.quantile(q/100)),2) for q in (10,25,50,75,90)}})
    target=Path(output)
    target.parent.mkdir(parents=True,exist_ok=True)
    out.drop(columns=["ix"]).to_csv(target,index=False,encoding="utf-8-sig")
    summary={"snapshot_days":int(s.date.nunique()),"matched_rows":int(len(out)),
             "stats":rows,"warning":"Descriptive only; overlapping horizons, survivor bias, adjusted-price consistency and missing benchmarks must be audited. No calibrated predictive claim."}
    target.with_suffix(".json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"snapshot_days":summary["snapshot_days"],"matched_rows":len(out),"groups":len(rows)}))
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--snapshots",required=True)
    a.add_argument("--prices",required=True)
    a.add_argument("--output",required=True)
    a.add_argument("--calendar",required=True,help="Independent CSV with date column of actual A-share sessions")
    x=a.parse_args()
    evaluate(x.snapshots,x.prices,x.output,x.calendar)
