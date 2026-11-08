"""Point-in-time-safe forward-return evaluator for archived daily pressure snapshots.
Requires independently archived daily score files and future daily close files.
Never reconstruct historical scores from today's universe.
"""
import argparse,json
from pathlib import Path
import pandas as pd
HORIZONS=(1,3,5,10,20)
def evaluate(scores_dir,prices_csv,out_csv):
    scores=[]
    for f in sorted(Path(scores_dir).glob("pressure_*.csv")):
        d=pd.read_csv(f,dtype={"code":str})
        if {"code","date","pressure_score"}<=set(d):
            scores.append(d[["code","date","pressure_score"]])
    if not scores: raise ValueError("No archived dated pressure snapshots; cannot backtest")
    s=pd.concat(scores,ignore_index=True).drop_duplicates(["code","date"])
    p=pd.read_csv(prices_csv,dtype={"code":str})
    if not {"code","date","close"}<=set(p):raise ValueError("Need code,date,close")
    p["date"]=pd.to_datetime(p.date)
    p["close"]=pd.to_numeric(p.close,errors="coerce")
    p=p.dropna(subset=["date","close"]).sort_values(["code","date"])
    p["index"]=p.groupby("code").cumcount()
    base=p[["code","date","index","close"]].rename(columns={"close":"signal_close"})
    s["date"]=pd.to_datetime(s.date)
    out=s.merge(base,on=["code","date"],how="inner",validate="one_to_one")
    for h in HORIZONS:
        future=p[["code","index","close"]].copy()
        future["index"]=future["index"]-h
        future=future.rename(columns={"close":f"close_{h}d"})
        out=out.merge(future,on=["code","index"],how="left",validate="many_to_one")
        out[f"return_{h}d_pct"]=(out[f"close_{h}d"]/out.signal_close-1)*100
    out["score_bucket"]=pd.cut(out.pressure_score,[0,70,80,90,100],
                                labels=["0-70","70-80","80-90","90-100"],include_lowest=True)
    out=out.drop(columns=["index"])
    out.to_csv(out_csv,index=False,encoding="utf-8-sig")
    stats=[]
    for bucket,g in out.groupby("score_bucket",observed=True):
        for h in HORIZONS:
            v=g[f"return_{h}d_pct"].dropna()
            if len(v)<30:continue
            stats.append({"bucket":str(bucket),"horizon":h,"n":len(v),"up_pct":round(100*(v>0).mean(),2),
                          **{f"p{q}":round(float(v.quantile(q/100)),2) for q in (10,25,50,75,90)}})
    summary={"snapshots":int(s.date.nunique()),"matched_signals":len(out),"stats":stats,
             "limitations":["Point-in-time index constituents must be archived separately",
                            "No benchmark excess returns until benchmark file provided",
                            "No historical claims when there are insufficient snapshots"]}
    Path(out_csv).with_suffix(".json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"snapshots":summary["snapshots"],"matched_signals":len(out),"valid_groups":len(stats)}))
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--scores-dir",required=True)
    a.add_argument("--prices",required=True)
    a.add_argument("--output",required=True)
    x=a.parse_args()
    evaluate(x.scores_dir,x.prices,x.output)
