"""Uncalibrated V1 research watchlist. Never treat score as VIX or buy signal."""
import json,sys
from pathlib import Path
import pandas as pd

def build(path):
    d=pd.read_csv(path,dtype={"code":str})
    required={"code","name","date","distance_pct","ret_5d_pct","ret_20d_pct","volume_ratio_20d","quality_status"}
    if d.empty or required-set(d.columns): raise ValueError("Missing rows/columns")
    date=d.date.mode().iloc[0]
    same=d[d.date==date].copy()
    if len(same)/len(d)<.95: raise ValueError("Mixed trading dates")
    for c in ["distance_pct","ret_5d_pct","ret_20d_pct","volume_ratio_20d"]:
        same[c]=pd.to_numeric(same[c],errors="coerce")
    same["near_low"]=same.distance_pct.le(10)
    same["selloff"]=(same.ret_5d_pct.le(-6)|same.ret_20d_pct.le(-15))&same.volume_ratio_20d.ge(1.3)
    same["repair"]=same.ret_20d_pct.lt(0)&same.ret_5d_pct.gt(0)&same.distance_pct.le(20)
    same["exhaustion_watch"]=same.get("exhaustion_watch",pd.Series(False,index=same.index)).astype(str).str.lower().eq("true")
    same["research_score"]=2*(same.near_low.astype(int)+same.selloff.astype(int)+same.repair.astype(int)+same.exhaustion_watch.astype(int))+same.quality_status.eq("priority_review").astype(int)
    watch=same[same.near_low|same.selloff|same.repair|same.exhaustion_watch].sort_values(["research_score","distance_pct"],ascending=[False,True]).head(20).copy()
    watch["reason"]=watch.apply(lambda x:"疑似抛压衰竭" if x.exhaustion_watch else ("异常下跌" if x.selloff else ("低位反弹" if x.repair else "接近52周低点")),axis=1)
    cols=["code","name","date","close","distance_pct","ret_5d_pct","ret_20d_pct","volume_ratio_20d","quality_status","exhaustion_watch","reason","research_score"]
    output=Path(path).parent
    watch[cols].to_csv(output/f"watchlist_{date}.csv",index=False,encoding="utf-8-sig")
    payload={"session":date,"total":len(d),"aligned":len(same),"stale":len(d)-len(same),"near_low":int(same.near_low.sum()),"selloff":int(same.selloff.sum()),"repair":int(same.repair.sum()),"model":"heuristic_watchlist_v1_uncalibrated","warning":"Research triage only: not a VIX, valuation, quality approval or buy signal.","watchlist":json.loads(watch[cols].to_json(orient="records",force_ascii=False))}
    (output/f"watchlist_{date}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in payload.items() if k!="watchlist"},ensure_ascii=False),flush=True)
if __name__=="__main__": build(sys.argv[1])
