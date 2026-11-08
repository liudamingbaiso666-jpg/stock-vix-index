"""V2.5 diagnostic: historical panic events vs same-stock nearest-neighbor controls.

Matching uses ONLY information observable at event date. This is not a valuation model.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

HORIZONS=(5,10,20,60)
THRESHOLDS=(70,80,90)
PCTS=(10,25,50,75,90)
FEATURES=("ret5","market20","vol20")
NAMES={"601899":"紫金矿业","600519":"贵州茅台","600900":"长江电力"}


def events(df, threshold, cooldown=20):
    flag=df.panic_score.ge(threshold)&df.panic_score.notna()
    starts=np.flatnonzero((flag & ~flag.shift(1,fill_value=False)).to_numpy())
    selected=[]
    for i in starts:
        if not selected or i-selected[-1]>cooldown:
            selected.append(int(i))
    return selected


def prepare(df):
    df=df.copy()
    df["ret5"]=df["close"].pct_change(5,fill_method=None)
    df["market20"]=df["market_close"].pct_change(20,fill_method=None)
    df["vol20"]=df["ret"].rolling(20).std()
    return df


def summarize(arr):
    arr=np.asarray(arr,dtype=float)
    arr=arr[np.isfinite(arr)]
    if not len(arr):
        return {"n":0}
    return {"n":len(arr),"positive_ratio":round(float(np.mean(arr>0)),4),
            "p":{str(p):round(float(np.percentile(arr,p)),3) for p in PCTS}}


def match(df, indices, horizon):
    # Exclude event-adjacent sessions from control pool, and avoid controls
    # whose forward returns are unavailable.
    valid=df[list(FEATURES)+[f"excess_{horizon}d",f"future_{horizon}d"]].notna().all(axis=1).to_numpy(copy=True)
    for i in indices:
        valid[max(0,i-20):min(len(df),i+21)]=False
    pool=np.flatnonzero(valid)
    used=set()
    pairs=[]
    unmatched=[]
    for i in indices:
        row=df.iloc[i]
        if not np.isfinite(row[list(FEATURES)].to_numpy(dtype=float)).all() or not np.isfinite(row[f"excess_{horizon}d"]):
            continue
        # Same calendar year +/- 1, and same market 20-day direction.
        possible=[j for j in pool if j not in used and abs(df.index[j].year-df.index[i].year)<=1
                  and np.sign(df.iloc[j]["market20"])==np.sign(row["market20"])]
        if not possible:
            unmatched.append(str(df.index[i].date()))
            continue
        controls=df.iloc[possible]
        # Scale using pre-event historical data only. No future outcomes used for matching.
        history=df.iloc[max(0,i-252):i]
        scale=history[list(FEATURES)].std().replace(0,np.nan).fillna(1.0)
        distance=((controls[list(FEATURES)]-row[list(FEATURES)])/scale).pow(2).sum(axis=1)
        j=int(possible[int(np.argmin(distance.to_numpy()))])
        used.add(j)
        pairs.append({"event_date":str(df.index[i].date()),"control_date":str(df.index[j].date()),
                      "distance":round(float(distance.loc[df.index[j]]),3),
                      "event_excess":float(row[f"excess_{horizon}d"]),
                      "control_excess":float(df.iloc[j][f"excess_{horizon}d"]),
                      "event_return":float(row[f"future_{horizon}d"]),
                      "control_return":float(df.iloc[j][f"future_{horizon}d"])})
    return pairs,unmatched


def evaluate(df):
    output={}
    for threshold in THRESHOLDS:
        idx=events(df,threshold)
        horizons={}
        for h in HORIZONS:
            pairs,unmatched=match(df,idx,h)
            event=np.array([p["event_excess"] for p in pairs])
            control=np.array([p["control_excess"] for p in pairs])
            difference=event-control
            horizons[str(h)]={"matched_pairs":len(pairs),"unmatched_dates":unmatched,
                "event_excess":summarize(event),"matched_control_excess":summarize(control),
                "paired_excess_difference":summarize(difference),
                "median_excess_difference":round(float(np.median(difference)),3) if len(difference) else None,
                "pairs":pairs}
        output[str(threshold)]={"event_count":len(idx),"horizons":horizons}
    return output


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result={"version":"v2_5_matched_exploratory","stocks":{},"errors":{},
            "matching":"Same stock, within +/-1 calendar year, same trailing 20-session market direction; nearest neighbor in 5-day stock return, 20-day market return and 20-day stock volatility; controls outside +/-20 sessions of selected threshold events; no replacement within horizon.",
            "limitations":["Nearest-neighbor matching is descriptive, not causal; feature balance and match distances must be reviewed.",
            "20-session exclusion can leave few eligible controls; no forced matches across market directions.",
            "Matching pools depend on threshold and horizon; comparisons across thresholds are not paired experiments.",
            "Adjusted historical prices may be revised; not point-in-time reproducible.",
            "No contemporaneously available fundamental valuations or safety-margin estimate.",
            "No transaction costs, limit-down execution, delisting or universe survivorship corrections."]}
    for path in sorted(a.input_dir.glob("*_panic.csv")):
        code=path.name.split("_")[0]
        try:
            df=pd.read_csv(path,parse_dates=["日期"],encoding="utf-8-sig").set_index("日期").sort_index()
            required={"close","market_close","ret","panic_score"}|{f"{prefix}_{h}d" for h in HORIZONS for prefix in ("future","excess")}
            if not required.issubset(df.columns):
                raise ValueError(f"Missing fields {required-set(df.columns)}")
            result["stocks"][code]={"name":NAMES.get(code,code),"results":evaluate(prepare(df))}
        except Exception as exc:
            result["errors"][code]=f"{type(exc).__name__}: {exc}"
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"completed":list(result["stocks"]),"errors":result["errors"]},ensure_ascii=False))
    if len(result["stocks"])!=3 or result["errors"]:
        raise RuntimeError("Incomplete V2.5 validation")


if __name__=="__main__":
    main()
