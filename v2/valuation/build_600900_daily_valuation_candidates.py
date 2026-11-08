"""Construct explicitly provisional daily market-cap, PE and dividend-yield candidates.

Safeguards: stock-share source reports in 10k shares (unit inferred, NOT verified);
only events known by observation date; first eligible financial session is after
announcement date; proposed dividends never count as paid; no PB without equity.
"""
import argparse,csv,json,datetime as dt
from pathlib import Path
def read(path):
 with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def num(v):
 try:return float(v) if str(v).strip() else None
 except (ValueError,TypeError):return None
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--market-dir",type=Path,required=True)
 p.add_argument("--fundamentals",type=Path,required=True)
 p.add_argument("--output-dir",type=Path,required=True)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 prices=sorted(read(a.market_dir/"daily_unadjusted.csv"),key=lambda x:x["日期"])
 dividends=read(a.market_dir/"dividend_history.csv")
 shares=read(a.market_dir/"share_capital_changes.csv")
 funds=read(a.fundamentals)
 # Keep only explicit corporate-action changes; report-period snapshots have
 # ambiguous availability and may encode subsequently restated share figures.
 events=[]
 for r in shares:
  reason=r.get("变动原因","")
  if reason=="定期报告":continue
  event=r.get("变动日期","");published=r.get("公告日期","")
  v=num(r.get("总股本"))
  if not event or not published or v is None:continue
  events.append({"effective_date":event,"known_date":published,
                 "shares_10k_candidate":v,"reason":reason})
 events.sort(key=lambda x:(x["effective_date"],x["known_date"]))
 # Annual and interim reports are candidate-vintage only, not validated.
 funds.sort(key=lambda x:x["published_date_candidate"])
 paid=[]
 for r in dividends:
  if r.get("进度")!="实施" or not r.get("除权除息日") or not r.get("公告日期"):continue
  v=num(r.get("派息"))
  if v is not None:
   paid.append({"known_date":r["公告日期"],"ex_date":r["除权除息日"],
                "cash_per_10_shares_candidate":v})
 out=[]
 for r in prices:
  day=r["日期"];close=num(r["收盘"])
  # For a daily close, only events effective and disclosed no later than day.
  available=[e for e in events if e["effective_date"]<=day and e["known_date"]<=day]
  event=available[-1] if available else None
  share_count=event["shares_10k_candidate"]*10000 if event else None
  available_fin=[f for f in funds if f["published_date_candidate"]<day]
  f=available_fin[-1] if available_fin else None
  # Sum paid cash dividends over trailing 365 calendar days, excluding events
  # that were not yet announced by the observation date.
  since=(dt.date.fromisoformat(day)-dt.timedelta(days=365)).isoformat()
  recent=[d for d in paid if since<d["ex_date"]<=day and d["known_date"]<=day]
  div10=sum(d["cash_per_10_shares_candidate"] for d in recent)
  div_ps=div10/10 if recent else None
  market_cap=close*share_count if close is not None and share_count else None
  profit=num(f.get("profit_ttm_cny_candidate")) if f else None
  pe=market_cap/profit if market_cap is not None and profit and profit>0 else None
  out.append({"date":day,"close_unadjusted_cny_candidate":close,
    "shares_candidate":share_count,"share_event_effective_date":event["effective_date"] if event else "",
    "share_event_known_date":event["known_date"] if event else "",
    "market_cap_cny_candidate":market_cap,
    "financial_report_period_candidate":f["report_period"] if f else "",
    "financial_report_published_date_candidate":f["published_date_candidate"] if f else "",
    "profit_ttm_cny_candidate":profit,"pe_ttm_candidate":pe,
    "trailing_paid_cash_dividend_per_share_candidate":div_ps,
    "trailing_paid_dividend_yield_candidate":div_ps/close if div_ps is not None and close else None,
    "pb_candidate":"","approved_for_historical_valuation":False,
    "status":"CANDIDATE_UNVERIFIED_SHARE_UNITS_VINTAGES_AND_CORPORATE_ACTIONS"})
 with (a.output_dir/"daily_market_valuation_candidates.csv").open("w",encoding="utf-8-sig",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 summary={"days":len(out),"capital_change_events":len(events),
  "implemented_dividend_events":len(paid),
  "days_with_market_cap_candidate":sum(x["market_cap_cny_candidate"] is not None for x in out),
  "days_with_pe_candidate":sum(x["pe_ttm_candidate"] is not None for x in out),
  "days_with_trailing_dividend_candidate":sum(x["trailing_paid_dividend_yield_candidate"] is not None for x in out),
  "approved_days":0,
  "critical":["Total-share provider unit 10k shares is inferred, not verified.",
    "Using only disclosed non-periodic share change events may omit historical baseline and later events.",
    "Cash dividend provider '派息' interpreted per ten shares, requires original notice validation.",
    "Trailing paid dividend is not a forecast or declared-dividend yield.",
    "Provider PIT financial vintages remain unverified; restructuring period not normalized.",
    "PB unavailable without historical attributable equity; no backtest authorized."]}
 (a.output_dir/"daily_market_valuation_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
