"""Fetch independent A-share exchange sessions and adjusted daily closes for V1.1 research.
Usage:
 python v2/fetch_backtest_market_data.py --snapshots v2/history --output-dir v2/reports/backtest_data
Research only. AKShare availability/adjustment consistency must be audited.
"""
import argparse
import time
from pathlib import Path
import akshare as ak
import pandas as pd

def collect(snapshots, output_dir, sleep=0.2):
    files=sorted(Path(snapshots).glob("low52_*.csv"))
    if not files:
        raise ValueError("No archived signal snapshots")
    samples=pd.concat([pd.read_csv(f,dtype={"code":str})[["code","date"]]
                       for f in files],ignore_index=True).drop_duplicates()
    start=pd.to_datetime(samples.date).min()
    # Request 60 calendar days after last signal for up to 20 exchange sessions.
    end=pd.to_datetime(samples.date).max()+pd.Timedelta(days=65)
    today=pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None).normalize()
    end=min(end,today)
    if end<=start:
        raise ValueError("No available forward observation period")
    calendar=ak.tool_trade_date_hist_sina()
    calendar["trade_date"]=pd.to_datetime(calendar["trade_date"])
    calendar=calendar[(calendar.trade_date>=start)&(calendar.trade_date<=end)]
    if calendar.empty:
        raise ValueError("No exchange sessions returned")
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    calendar.rename(columns={"trade_date":"date"})[["date"]].to_csv(out/"calendar.csv",index=False)
    records=[]
    errors=[]
    for i,code in enumerate(sorted(samples.code.unique()),1):
        try:
            raw=ak.stock_zh_a_hist(symbol=code,period="daily",
                start_date=start.strftime("%Y%m%d"),end_date=end.strftime("%Y%m%d"),
                adjust="qfq")
            if raw is None or raw.empty:
                raise ValueError("empty history")
            d=raw.rename(columns={"日期":"date","收盘":"close"})[["date","close"]]
            d["date"]=pd.to_datetime(d.date)
            d["close"]=pd.to_numeric(d.close,errors="coerce")
            d=d.dropna(subset=["close"])
            d["code"]=code
            records.append(d[["code","date","close"]])
        except Exception as exc:
            errors.append({"code":code,"error":str(exc)[:180]})
        if i%50==0:
            print(f"fetched {i}/{samples.code.nunique()} stocks",flush=True)
        time.sleep(sleep)
    if not records:
        raise ValueError(f"No prices fetched; examples: {errors[:3]}")
    prices=pd.concat(records,ignore_index=True).drop_duplicates(["code","date"])
    prices.to_csv(out/"prices.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(errors,columns=["code","error"]).to_csv(out/"errors.csv",index=False)
    print(f"calendar sessions={len(calendar)}, price rows={len(prices)}, errors={len(errors)}")
    print("CAUTION: qfq history can be revised after corporate actions. "
          "Audit point-in-time consistency, suspended sessions, delistings, and sample selection.")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--snapshots",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--sleep",type=float,default=0.2)
    a=p.parse_args()
    collect(a.snapshots,a.output_dir,a.sleep)
