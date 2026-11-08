"""V2.6 quality gates for 600900 daily valuation candidate series.
Produces diagnostics, not valuation approval. No future data or fabricated values.
"""
import argparse,csv,json,math,statistics
from collections import Counter
from pathlib import Path
def read(p):
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def num(x):
 try:
  v=float(x)
  return v if math.isfinite(v) else None
 except (TypeError,ValueError):return None
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--daily",type=Path,required=True)
 p.add_argument("--market-dir",type=Path,required=True)
 p.add_argument("--output-dir",type=Path,required=True)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 rows=read(a.daily);shares=read(a.market_dir/"share_capital_changes.csv");divs=read(a.market_dir/"dividend_history.csv")
 events=[];problems=[];last=None
 for r in rows:
  date=r["date"];price=num(r["close_unadjusted_cny_candidate"])
  shares_count=num(r["shares_candidate"]);cap=num(r["market_cap_cny_candidate"])
  pe=num(r["pe_ttm_candidate"]);yield_=num(r["trailing_paid_dividend_yield_candidate"])
  issues=[]
  if price is None or price<=0:issues.append("invalid_close")
  if shares_count is None or shares_count<=0:issues.append("invalid_shares")
  if cap is not None and price and shares_count and abs(cap-price*shares_count)>max(1,cap*1e-8):issues.append("market_cap_arithmetic")
  if pe is not None and (pe<=0 or pe>150):issues.append("pe_outlier")
  if yield_ is not None and (yield_<0 or yield_>0.15):issues.append("dividend_yield_outlier")
  if r.get("share_event_known_date") and r["share_event_known_date"]>date:issues.append("future_share_announcement")
  if r.get("share_event_effective_date") and r["share_event_effective_date"]>date:issues.append("future_share_effective_date")
  if r.get("financial_report_published_date_candidate") and r["financial_report_published_date_candidate"]>=date:issues.append("financial_report_not_prior")
  if last:
   last_shares=num(last["shares_candidate"])
   if shares_count and last_shares and abs(shares_count/last_shares-1)>0.01:
    events.append({"date":date,"type":"share_count_change","old_shares":last_shares,"new_shares":shares_count,"pct_change":(shares_count/last_shares-1)*100})
   last_pe=num(last["pe_ttm_candidate"])
   if pe and last_pe and abs(pe/last_pe-1)>0.5:
    events.append({"date":date,"type":"pe_change_gt_50pct","old_pe":last_pe,"new_pe":pe,"pct_change":(pe/last_pe-1)*100})
  if issues:problems.append({"date":date,"issues":";".join(issues),"close":price,"shares":shares_count,"pe":pe,"yield":yield_})
  last=r
 # Source-unit triangulation: compare provider historical share values to
 # statement reported share capital (CNY); never assume the same unit.
 share_values=[num(r.get("总股本")) for r in shares if num(r.get("总股本"))]
 div_values=[num(r.get("派息")) for r in divs if r.get("进度")=="实施" and num(r.get("派息")) is not None]
 source_checks={"share_capital_provider_value_examples":share_values[-8:],
   "candidate_share_unit_multiplier":10000,
   "share_unit_verified_against_original_filings":False,
   "implemented_dividend_cash_per_10_shares_examples":div_values[:8],
   "dividend_unit_verified_against_original_notices":False,
   "dividend_event_rows_with_missing_ex_date":sum(r.get("进度")=="实施" and not r.get("除权除息日") for r in divs),
   "dividend_duplicate_ex_dates":{d:n for d,n in Counter(r.get("除权除息日") for r in divs if r.get("进度")=="实施" and r.get("除权除息日")).items() if n>1}}
 with (a.output_dir/"valuation_anomalies.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["date","issues","close","shares","pe","yield"]);w.writeheader();w.writerows(problems)
 with (a.output_dir/"valuation_jump_events.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=["date","type","old_shares","new_shares","old_pe","new_pe","pct_change"],extrasaction="ignore");w.writeheader();w.writerows(events)
 summary={"total_days":len(rows),"anomaly_days":len(problems),
  "anomaly_types":dict(Counter(z for r in problems for z in r["issues"].split(";"))),
  "jump_events":len(events),"jump_event_types":dict(Counter(x["type"] for x in events)),
  "source_checks":source_checks,
  "verified_days":0,"valuation_ready":False,
  "next_steps":["Verify share units against original capital-change announcements.",
    "Verify cash dividend per-ten-share units and ex-dates against official notices.",
    "Audit point-in-time financial vintages and restructuring before PE backtesting.",
    "Get attributable equity for PB; do not invent missing data."]}
 (a.output_dir/"valuation_quality_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
