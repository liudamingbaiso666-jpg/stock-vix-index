"""Simple daily 52-week low and price-repair scanner; candidate universe is NOT quality-approved."""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
from market_data_providers import fetch_daily
from ohlcv_cache import load_cache, store_cache, combine_cached_and_new, cache_path
from exhaustion_signals import exhaustion_features
from repair_score import repair_features
from experimental_indicators_v11 import experimental_indicators

ROOT = Path(__file__).resolve().parent
def scan_one(code, name, end_date):
    start = (pd.Timestamp(end_date) - pd.Timedelta(days=520)).strftime("%Y%m%d")
    cache_dir = ROOT / "cache" / "ohlcv"
    cached = load_cache(cache_dir, code)
    if cached is not None:
        cached = cached.loc[cached["date"] <= pd.Timestamp(end_date)].copy()
        if len(cached) < 253:
            cached = None
    provider_file = cache_path(cache_dir, code).with_suffix(".provider")
    cached_provider = provider_file.read_text().strip() if cached is not None and provider_file.exists() else None
    if cached is not None and cached_provider in ("sina", "eastmoney"):
        last = cached["date"].max()
        if last >= pd.Timestamp(end_date):
            d, provider = cached.copy(), cached_provider
        else:
            # Re-fetch a small overlap to detect historical qfq revisions.
            overlap_start = cached.iloc[-6]["date"].strftime("%Y%m%d")
            try:
                new, source = fetch_daily(code, overlap_start, end_date,
                    preferred=cached_provider, min_sessions=1, allow_fallback=False)
                overlap = cached.merge(new, on="date", suffixes=("_old", "_new"))
                if overlap.empty or any(
                    ((overlap[f"{col}_old"] - overlap[f"{col}_new"]).abs() >
                     0.001 * overlap[f"{col}_old"].abs().clip(lower=1)).any()
                    for col in ("open", "high", "low", "close")
                ):
                    raise ValueError("qfq adjustment revision or missing overlap")
                d = combine_cached_and_new(cached, new)
                provider = source
            except ValueError:
                # Changed adjustments require a complete provider-consistent refresh.
                d, provider = fetch_daily(code, start, end_date)
            except Exception as exc:
                # A transient incremental outage must not trigger 800 full downloads.
                raise RuntimeError(f"incremental update failed for {code}: {exc}") from exc
    else:
        d, provider = fetch_daily(code, start, end_date)
    store_cache(cache_dir, code, d)
    provider_file.write_text(provider, encoding="utf-8")
    d["date"] = pd.to_datetime(d["date"])
    for k in ("open","high","close","low","volume","turnover_pct"):
        d[k] = pd.to_numeric(d[k], errors="coerce")
    d = d.dropna(subset=["date","open","high","close","low","volume"]).sort_values("date").drop_duplicates("date")
    if len(d) < 253:
        raise ValueError(f"insufficient sessions: {len(d)}")
    d = d.iloc[-253:].copy()
    latest = d.iloc[-1]
    # Use prior 252 sessions INCLUDING the current session; no future prices.
    w = d.iloc[-252:]
    low52 = float(w["low"].min())
    low_date = w.loc[w["low"].idxmin(),"date"]
    close = float(latest["close"])
    def ret(n):
        return round((close / float(d.iloc[-(n+1)]["close"]) - 1)*100,2)
    v20 = float(d.iloc[-21:-1]["volume"].mean())
    ratio = float(latest["volume"])/v20 if v20>0 else None
    r5,r20,r60=ret(5),ret(20),ret(60)
    labels=[]
    if r5 < -6 and ratio is not None and ratio >= 1.8:
        labels.append("急跌放量（待核实是否恐慌）")
    elif r5 < 0 and ratio is not None and ratio >= 1.3:
        labels.append("放量下跌")
    elif r20 < 0 and ratio is not None and ratio <= 0.8:
        labels.append("缩量下跌")
    if r5 > 0 and ratio is not None:
        labels.append("放量反弹" if ratio>=1.3 else "反弹")
    if abs(r5) <= 2 and r20 < 0:
        labels.append("低位震荡（需复核）")
    if not labels: labels=["走势待观察"]
    distance=(close/low52-1)*100
    ex=exhaustion_features(d)
    repair=repair_features(d)
    experimental=experimental_indicators(d)
    return {"code":code,"name":name,"date":latest["date"].strftime("%Y-%m-%d"),
            "close":close,"low52":round(low52,3),"distance_pct":round(distance,2),
            "ret_5d_pct":r5,"ret_20d_pct":r20,"ret_60d_pct":r60,
            "volume_ratio_20d":round(ratio,2) if ratio is not None else None,
            "low_date":low_date.strftime("%Y-%m-%d"),
            "rebound_from_low_pct":round(distance,2),
            "sessions_since_low":int((d["date"]>low_date).sum()),
            "price_behavior":"、".join(labels),
            "turnover_pct":round(float(latest["turnover_pct"]),3) if pd.notna(latest["turnover_pct"]) else None,
            "exhaustion_watch":ex["exhaustion_watch"],
            "exhaustion_evidence_count":ex["evidence_count"],
            "exhaustion_flags":json.dumps(ex["flags"],ensure_ascii=False),
            "repair_score":repair["repair_score"],
            "repair_stage":repair["repair_stage"],
            "early_window":repair["early_window"],
            "repair_flags":json.dumps(repair["repair_flags"],ensure_ascii=False),
            "selloff_context":repair["selloff_context"],
            "drawdown_25d_pct":repair["drawdown_25d_pct"],
            "quality_status":"unverified",
            "data_provider":provider,
            **experimental}

def load_quality_status():
    statuses = {}
    for path in sorted((ROOT / "quality" / "aggregate").glob("batch_*_quality_v2_1.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data.get("records", []):
                statuses[item["code"]] = item.get("status", "unrated")
        except (ValueError, OSError, KeyError) as exc:
            print(f"Quality batch unreadable {path.name}: {exc}", flush=True)
    return statuses

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=None,help="YYYYMMDD; default uses latest available trading session")
    p.add_argument("--limit",type=int,default=800)
    p.add_argument("--sleep",type=float,default=0.15)
    p.add_argument("--min-fresh-coverage",type=float,default=0.90,help="Minimum same-session fraction of attempted candidates for publication")
    p.add_argument("--stop-after-errors",type=int,default=30,help="Stop early when the first N consecutive stock requests fail")
    a=p.parse_args()
    if a.date is None:
        a.date = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
    universe=json.loads((ROOT/"data"/"universe_2026-11-08.json").read_text(encoding="utf-8"))["records"]
    output=ROOT/"reports";output.mkdir(exist_ok=True)
    quality = load_quality_status()
    rows=[];errors=[]
    consecutive_errors=0
    stopped_early=False
    for i,x in enumerate(universe[:a.limit],1):
        try:
            r=scan_one(x["code"],x["name"],a.date)
            if r["date"]>pd.Timestamp(a.date).strftime("%Y-%m-%d"):
                raise ValueError("future trading date returned")
            r['quality_status'] = quality.get(x['code'], 'unrated')
            rows.append(r)
            consecutive_errors=0
        except Exception as e:
            errors.append({"code":x["code"],"error":str(e)[:160]})
            consecutive_errors+=1
        if i%50==0:print(f"{i}/{min(a.limit,len(universe))} scanned, {len(rows)} valid",flush=True)
        if consecutive_errors>=a.stop_after_errors:
            stopped_early=True
            print(f"ABORT: {consecutive_errors} consecutive failures; source may be rate-limited. "
                  f"Stopping at {i} attempts to avoid repeated requests.",flush=True)
            break
        time.sleep(a.sleep)
    rows.sort(key=lambda x:x["distance_pct"])
    observed_dates = [x["date"] for x in rows]
    day = max(observed_dates) if observed_dates else pd.Timestamp(a.date).strftime("%Y-%m-%d")
    stale = sum(x["date"] != day for x in rows)
    fresh_rows = [x for x in rows if x["date"] == day]
    fresh_coverage = len(fresh_rows) / max(1, min(a.limit, len(universe)))
    # Do not publish mixed-session cross-sectional P/R scores.
    rows = fresh_rows
    result={"as_of":day,"universe_total":len(universe),"attempted":min(a.limit,len(universe)),
            "valid":len(rows),"coverage_pct":round(100*len(rows)/len(universe),2),
            "requested_end_date":pd.Timestamp(a.date).strftime("%Y-%m-%d"),
            "latest_observed_session":day,"stale_stock_count":stale,
            "fresh_coverage_pct":round(100*fresh_coverage,2),
            "actual_attempts":len(rows)+len(errors),"stopped_early":stopped_early,
            "notes":["Candidate pool only; quality approval requires separate verification",
                     "Price-based labels are descriptive, not proof of panic or fund flows",
                     "52-week proximity does not establish intrinsic undervaluation"],
            "top20":rows[:20],"errors":errors,
            "quality_note":"Preliminary screening labels only, not confirmed investable quality"}
    (output/f"low52_{day}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    pd.DataFrame(rows).to_csv(output/f"low52_{day}.csv",index=False,encoding="utf-8-sig")
    print(json.dumps({"valid":len(rows),"errors":len(errors),"coverage_pct":result["coverage_pct"],"error_examples":errors[:5]},ensure_ascii=False),flush=True)
    if stale:
        print(f"WARNING: {stale} stocks do not match latest observed session {day}",flush=True)
    if stopped_early or len(rows)<100 or fresh_coverage < a.min_fresh_coverage or day != pd.Timestamp(a.date).strftime("%Y-%m-%d"):
        raise SystemExit(f"FAILED: market data coverage insufficient for reliable cross-sectional scoring "
                         f"(valid={len(rows)}, fresh_coverage={fresh_coverage:.1%}, errors={len(errors)}, early_stop={stopped_early}, session={day}). "
                         "Inspect low52 JSON and data source availability; no P score should be published.")
if __name__=="__main__":main()
