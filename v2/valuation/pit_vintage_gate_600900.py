"""Conservative PIT data-vintage eligibility gate for 600900.

Never reinterpret later-provider disclosure dates as original disclosure dates.
This is a data-quality gate, not a historical valuation.
"""
import argparse
import json
from pathlib import Path
import pandas as pd

TABLES=("cash_flow","balance_sheet","income_statement")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--audit-file",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(a.audit_file,dtype={"code":str},encoding="utf-8-sig")
    for table in TABLES:
        df[table+"_provider_date"]=pd.to_datetime(df[table+"_provider_date"],errors="coerce")
    df["published_date"]=pd.to_datetime(df["published_date"],errors="coerce")
    df["latest_provider_date"]=df[[x+"_provider_date" for x in TABLES]].max(axis=1)
    df["vintage_lag_days"]=(df["latest_provider_date"]-df["published_date"]).dt.days
    df["all_dates_match"]=df[[x+"_date_agrees" for x in TABLES]].fillna(False).all(axis=1)
    df["all_dates_present"]=df[[x+"_provider_date" for x in TABLES]].notna().all(axis=1)
    df["pit_eligible"]=df["all_dates_match"] & df["all_dates_present"]
    df["reason"]=df["pit_eligible"].map({True:"provider_dates_agree_requires_original_pdf_audit",
                                           False:"provider_dates_differ_or_missing_block_pit"})
    df["original_pdf_audited"]=False
    df["valuation_input_approved"]=False
    cols=["code","report_period","published_date","latest_provider_date",
          "vintage_lag_days","pit_eligible","original_pdf_audited",
          "valuation_input_approved","reason","report_url"]
    df[cols].to_csv(a.output_dir/"pit_vintage_gate.csv",index=False,encoding="utf-8-sig")
    result={
        "report_periods":len(df),
        "provider_date_agreement_candidates":int(df["pit_eligible"].sum()),
        "blocked_for_provider_date_disagreement":int((~df["pit_eligible"]).sum()),
        "approved_for_historical_valuation":0,
        "reason":"Provider-date agreement is insufficient to verify historical statement vintages. Original published PDFs must be checked.",
        "notes":["Never backdate financial figures sourced from later provider vintages.",
                 "Do not treat provider's 公告日期 as a definitive publication timestamp for every historical number.",
                 "No intrinsic value or margin-of-safety series is produced."]
    }
    (a.output_dir/"pit_vintage_gate_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":
    main()
