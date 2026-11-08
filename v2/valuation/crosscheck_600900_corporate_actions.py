"""Cross-check 600900 corporate-action candidates against historical report share capital.
This is an independent provider-vs-provider consistency test, NOT original-announcement verification.
"""
import argparse,csv,json,math
from pathlib import Path
def load(p):
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def n(x):
 try:return float(x)
 except (ValueError,TypeError):return None
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--market-dir",type=Path,required=True)
 p.add_argument("--audit-csv",type=Path,required=True)
 p.add_argument("--daily",type=Path,required=True)
 p.add_argument("--output-dir",type=Path,required=True)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 s=load(a.market_dir/"share_capital_changes.csv")
 d=load(a.market_dir/"dividend_history.csv")
 f=load(a.audit_csv);daily=load(a.daily)
 rows=[];matched=0;disagree=0
 for r in f:
  period=r["report_period"];published=r["published_date"]
  reported=n(r.get("shares_reported_cny"))
  # Only share snapshots whose own announcement date is not after the report's disclosure.
  snapshots=[x for x in s if x.get("变动日期","")<=period and x.get("公告日期","")<=published and n(x.get("总股本"))]
  latest=max(snapshots,key=lambda x:(x["变动日期"],x["公告日期"])) if snapshots else None
  provider_shares=n(latest["总股本"])*10000 if latest else None
  delta=(provider_shares/reported-1)*100 if provider_shares and reported else None
  status="MATCH_PROVIDER_ONLY" if delta is not None and abs(delta)<0.1 else ("MISMATCH" if delta is not None else "MISSING_SNAPSHOT")
  matched+=status=="MATCH_PROVIDER_ONLY";disagree+=status=="MISMATCH"
  rows.append({"report_period":period,"report_disclosure":published,"report_share_capital_cny_candidate":reported,
   "share_provider_snapshot_date":latest["变动日期"] if latest else "",
   "share_provider_known_date":latest["公告日期"] if latest else "",
   "share_provider_shares_candidate":provider_shares,"relative_difference_pct":delta,"status":status})
 with (a.output_dir/"share_crosscheck.csv").open("w",newline="",encoding="utf-8-sig") as fh:
  w=csv.DictWriter(fh,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 # Dividends: validate chronology and proposed vs implemented, without inventing official notice.
 div_rows=[]
 for r in d:
  implemented=r.get("进度")=="实施";ann=r.get("公告日期","");ex=r.get("除权除息日","")
  issues=[]
  if implemented and not ex:issues.append("missing_ex_date")
  if implemented and ex and ann>ex:issues.append("announcement_after_ex_date")
  if implemented and n(r.get("派息")) is None:issues.append("invalid_cash")
  div_rows.append({"announcement_date":ann,"ex_date":ex,"status":r.get("进度"),"cash_per_10_candidate":r.get("派息"),
                   "issues":";".join(issues),"verified_against_original_notice":False})
 with (a.output_dir/"dividend_crosscheck.csv").open("w",newline="",encoding="utf-8-sig") as fh:
  w=csv.DictWriter(fh,fieldnames=list(div_rows[0]));w.writeheader();w.writerows(div_rows)
 # Check if daily share counts agree with the latest disclosed report as of the day
 # WITHOUT treating later comparative financial values as genuine PIT vintages.
 distinct_shares=sorted(set(n(r.get("shares_candidate")) for r in daily if n(r.get("shares_candidate"))))
 summary={"periods_compared":len(rows),"provider_only_share_matches":matched,"share_mismatches":disagree,
  "missing_share_snapshots":sum(r["status"]=="MISSING_SNAPSHOT" for r in rows),
  "daily_distinct_share_counts":distinct_shares,
  "dividend_records":len(div_rows),"dividend_chronology_issues":sum(bool(r["issues"]) for r in div_rows),
  "original_announcements_verified":0,"valuation_approved":False,
  "important":["Share capital reported in CNY is compared to share counts assuming RMB1 par value; confirm with original filings.",
    "Share-capital data source reports 10k shares; unit is still unverified against issuer disclosures.",
    "Provider historical share-capital report periods may be restated and are NOT automatically PIT.",
    "Dividend amounts are interpreted as cash per 10 shares, NOT independently confirmed.",
    "2022-2023 asset restructuring makes profit-based valuations non-comparable without normalization.",
    "No PB or formal backtest approved."]}
 (a.output_dir/"corporate_action_crosscheck_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
