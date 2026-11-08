"""Collect 600900 unadjusted daily prices, share-capital and cash-dividend events.

External provider data are unverified candidates. No valuation or backtest
is approved by this collection step. Keep raw responses and provenance.
"""
import argparse,datetime as dt,json,traceback
from pathlib import Path
import pandas as pd
import akshare as ak

def save(df,path):
 if df is None or df.empty:raise ValueError("empty provider result")
 df.to_csv(path,index=False,encoding="utf-8-sig")
 return {"rows":len(df),"columns":list(map(str,df.columns))}
def attempt(name,fn,out,manifest):
 try:
  df=fn()
  manifest["sources"][name]={"status":"collected_unverified",**save(df,out)}
 except Exception as e:
  manifest["sources"][name]={"status":"failed","error":f"{type(e).__name__}: {e}"}
def main():
 p=argparse.ArgumentParser();p.add_argument("--output-dir",required=True,type=Path)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 m={"stock":"600900","collected_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
    "sources":{},"approved_for_valuation":False,
    "warnings":["Daily prices MUST be unadjusted for comparison with contemporaneous per-share fair values.",
    "Historical share counts and dividends must be checked against original announcements and ex-right dates.",
    "Provider historical series may be revised and must not be assumed point-in-time.",
    "No backtest or safety-margin estimate is authorized by collection."]}
 attempt("unadjusted_daily_prices",
         lambda:ak.stock_zh_a_hist(symbol="600900",period="daily",start_date="20200101",end_date="20261108",adjust=""),
         a.output_dir/"daily_unadjusted.csv",m)
 attempt("dividend_financing_detail",
         lambda:ak.stock_history_dividend_detail(symbol="600900",indicator="分红"),
         a.output_dir/"dividend_history.csv",m)
 attempt("dividend_financing_summary",
         lambda:ak.stock_history_dividend(symbol="600900"),
         a.output_dir/"dividend_summary.csv",m)
 attempt("share_capital_changes",
         lambda:ak.stock_share_change_cninfo(symbol="600900"),
         a.output_dir/"share_capital_changes.csv",m)
 (a.output_dir/"collection_manifest.json").write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(m,ensure_ascii=False))
 if m["sources"]["unadjusted_daily_prices"]["status"]!="collected_unverified":
  raise RuntimeError("Unadjusted price collection failed")
if __name__=="__main__":main()
