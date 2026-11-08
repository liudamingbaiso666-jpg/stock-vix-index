"""Build minimal PIT *candidate* fundamental dataset; no valuation approval.

Only pre-existing report-index dates are used as provisional availability.
Numbers may come from later provider vintages and are NEVER treated as verified.
"""
import argparse,csv,json
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path

CORE=["net_profit_ytd_cny","cfo_ytd_cny","capex_ytd_cny","cash_cny",
      "gross_debt_components_cny","shares_reported_cny"]
DEBT=["debt_短期借款","debt_长期借款","debt_应付债券","debt_一年内到期的非流动负债"]
def val(row,key):
 try:return float(row[key]) if row.get(key,"").strip() else None
 except (ValueError,TypeError):return None
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--audit-file",type=Path,required=True)
 p.add_argument("--output-dir",type=Path,required=True)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 with a.audit_file.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
 rows.sort(key=lambda r:r["report_period"])
 by_period={r["report_period"]:r for r in rows}
 output=[]
 for r in rows:
  period=r["report_period"];year=int(period[:4]);month=int(period[5:7])
  previous=by_period.get(f"{year-1}-12-31")
  # TTM = current YTD + prior full year - prior same YTD (if all exist).
  prior_same=by_period.get(f"{year-1}-{period[5:]}")
  def ttm(field):
   current=val(r,field)
   if month==12:return current
   if not previous or not prior_same:return None
   pfull=val(previous,field);psame=val(prior_same,field)
   return current+pfull-psame if None not in (current,pfull,psame) else None
  cfo=ttm("cfo_ytd_cny");capex=ttm("capex_ytd_cny");profit=ttm("net_profit_ytd_cny")
  gross=sum(val(r,k) or 0 for k in DEBT) if all(val(r,k) is not None for k in DEBT) else None
  cash=val(r,"cash_cny")
  # Corporate restructuring may invalidate naive TTM across 2022-2023.
  structural_break=(period>="2022-12-31" and period<="2023-12-31")
  flags=[]
  if structural_break:flags.append("2022_2023_restructuring_normalization_required")
  if not all(r.get(k,"").strip() for k in CORE):flags.append("missing_core_provider_fields")
  if r.get("provider_date_all_agree","").lower()!="true":flags.append("provider_vintage_disagreement")
  flags.append("original_pdf_current_column_unverified")
  flags.append("historical_dividend_revenue_equity_generation_pending")
  output.append({
   "code":"600900","report_period":period,"published_date_candidate":r["published_date"],
   "first_eligible_trade_date_rule":"first_trading_session_strictly_after_published_date",
   "report_type":r["report_type"],"source_announcement_id":r["announcement_id"],
   "net_profit_ytd_cny_candidate":val(r,"net_profit_ytd_cny"),
   "cfo_ytd_cny_candidate":val(r,"cfo_ytd_cny"),
   "capex_ytd_cny_candidate":val(r,"capex_ytd_cny"),
   "profit_ttm_cny_candidate":profit,"cfo_ttm_cny_candidate":cfo,
   "capex_ttm_cny_candidate":capex,
   "fcf_ttm_proxy_cny_candidate":cfo-capex if cfo is not None and capex is not None else None,
   "cash_cny_candidate":cash,"gross_debt_cny_candidate":gross,
   "net_debt_proxy_cny_candidate":gross-cash if gross is not None and cash is not None else None,
   "shares_reported_cny_candidate":val(r,"shares_reported_cny"),
   "restructuring_break_flag":structural_break,
   "pit_valuation_approved":False,"verification_status":"CANDIDATE_ONLY_NOT_PDF_VERIFIED",
   "flags":";".join(flags)
  })
 path=a.output_dir/"minimal_pit_candidates.csv"
 with path.open("w",encoding="utf-8-sig",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=list(output[0]));writer.writeheader();writer.writerows(output)
 summary={"stock":"600900","report_periods":len(output),
          "annual_periods":sum(x["report_type"]=="annual" for x in output),
          "quarterly_or_semiannual_periods":sum(x["report_type"]!="annual" for x in output),
          "ttm_profit_candidate_periods":sum(x["profit_ttm_cny_candidate"] is not None for x in output),
          "ttm_fcf_candidate_periods":sum(x["fcf_ttm_proxy_cny_candidate"] is not None for x in output),
          "approved_valuations":0,
          "missing_inputs":["revenue","attributable_equity","dividends","generation","unadjusted_daily_close","verified_actual_shares"],
          "important":["These are provider figures, NOT verified historical vintages.",
                       "Report-index dates are provisional, use next trading session to avoid intraday lookahead.",
                       "TTM across 2022-2023 restructuring is NOT comparable without normalization.",
                       "Capital expenditure is a cashflow proxy; it includes growth investments.",
                       "No fair values or backtest returns are produced."]}
 (a.output_dir/"minimal_pit_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
