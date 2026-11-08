"""Match 600900 reporting periods to dated, full periodic-report notices.

This produces a candidate availability map, not audited intrinsic values.
"""
import argparse
import json
import re
from pathlib import Path
import pandas as pd

PERIODS={"annual":"12-31","semiannual":"06-30","quarter1":"03-31","quarter3":"09-30"}
EXCLUDE=("摘要","正文","关于","问答","更正","修订","取消","变更","提示","说明")
PATTERNS={
    "annual":re.compile(r"(20\d{2})年年度报告$"),
    "semiannual":re.compile(r"(20\d{2})年半年度报告$"),
    "quarter1":re.compile(r"(20\d{2})年(?:第)?一季度报告$|(?:20\d{2})年第一季度报告$"),
    "quarter3":re.compile(r"(20\d{2})年(?:第)?三季度报告$|(?:20\d{2})年第三季度报告$"),
}
def parse_notice(title):
    if any(x in title for x in EXCLUDE):
        return None
    for kind,pattern in PATTERNS.items():
        match=pattern.search(title)
        if match:
            year=int(re.search(r"20\d{2}",match.group(0)).group())
            return f"{year}-{PERIODS[kind]}",kind
    return None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--raw-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    notice=pd.read_csv(args.raw_dir/"disclosures.csv",dtype=str).fillna("")
    report=pd.read_csv(args.raw_dir/"balance_sheet.csv",dtype=str)
    periods=set(pd.to_datetime(report["报告日"],errors="coerce").dropna().dt.strftime("%Y-%m-%d"))
    matched=[]
    rejected=[]
    for row in notice.to_dict("records"):
        parsed=parse_notice(row["title"])
        if parsed is None:
            rejected.append({"title":row["title"],"reason":"not_unambiguous_full_periodic_report"})
            continue
        period,kind=parsed
        if period not in periods:
            rejected.append({"title":row["title"],"reason":"financial_period_not_present"})
            continue
        if row["published_date"]<period:
            rejected.append({"title":row["title"],"reason":"date_before_period_end"})
            continue
        matched.append({"code":"600900","report_period":period,
                        "published_date":row["published_date"],"report_type":kind,
                        "report_url":row["report_url"],"announcement_id":row["announcement_id"],
                        "source":row["source"],"verification_status":"candidate_not_pdf_audited"})
    df=pd.DataFrame(matched,columns=["code","report_period","published_date","report_type",
                   "report_url","announcement_id","source","verification_status"])
    if not df.empty:
        df=df.sort_values(["report_period","published_date"]).drop_duplicates("report_period",keep="first")
    df.to_csv(args.output_dir/"report_availability_candidates.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(rejected,columns=["title","reason"]).to_csv(args.output_dir/"rejected_notices.csv",index=False,encoding="utf-8-sig")
    covered=set(df["report_period"])
    result={"status":"candidate_mapping_not_pdf_audited",
            "financial_period_count":len(periods),"matched_period_count":len(covered),
            "unmatched_financial_periods":sorted(periods-covered),
            "rejected_notice_count":len(rejected),
            "notes":["Only full periodic report titles are accepted.",
                     "Availability date comes from notice index and must be audited against the original PDF.",
                     "No intrinsic value is generated; do not use as completed valuation calibration."]}
    (args.output_dir/"mapping_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
    if not covered:
        raise RuntimeError("No candidate period-to-disclosure matches")

if __name__=="__main__":
    main()
