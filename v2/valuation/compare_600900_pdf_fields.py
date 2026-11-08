"""Extract PDF evidence candidates for 600900 and compare with provider figures.

This script intentionally DOES NOT approve PIT valuations. PDF text extraction,
units, consolidated-vs-parent tables and comparative columns require review.
"""
import argparse
import json
import re
from pathlib import Path
import pandas as pd
import fitz

FIELDS={
    "cfo_ytd_cny": ["经营活动产生的现金流量净额"],
    "capex_ytd_cny": ["购建固定资产、无形资产和其他长期资产支付的现金","购建固定资产、无形资产和其他长期资产所支付的现金"],
    "net_profit_ytd_cny": ["归属于母公司股东的净利润","归属于母公司所有者的净利润"],
    "cash_cny": ["货币资金"],
    "shares_reported_cny": ["实收资本（或股本）","实收资本(或股本)","股本"],
}
NUMBER=re.compile(r"(?<![\d.])[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.])")
def norm(s):
    return re.sub(r"\s+","",s).replace("，",",").replace("（","(").replace("）",")")
def candidates(doc,labels,limit=15):
    found=[]
    for page_no in range(len(doc)):
        page=doc[page_no]
        lines=page.get_text("text",sort=True).splitlines()
        # Combine nearby lines to accommodate line-wrapped labels and numeric columns.
        for i in range(len(lines)):
            block=norm(" ".join(lines[i:i+4]))
            matched=next((label for label in labels if norm(label) in block),None)
            if not matched:
                continue
            suffix=block.split(norm(matched),1)[-1][:220]
            nums=NUMBER.findall(suffix)
            if nums:
                found.append({"page":page_no+1,"label":matched,
                              "numbers":nums[:7],"context":block[:260]})
            if len(found)>=limit:
                return found
    return found

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pdf-dir",type=Path,required=True)
    ap.add_argument("--audit-file",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(a.audit_file,dtype={"code":str},encoding="utf-8-sig").fillna("")
    results=[]
    for row in df.to_dict("records"):
        period=row["report_period"]
        name=period+"_"+row["announcement_id"]+".pdf"
        path=a.pdf_dir/name
        item={"report_period":period,"announcement_id":row["announcement_id"],
              "pdf_name":name,"pdf_found":path.exists(),"pages":0,
              "extraction_status":"missing_pdf","fields":{},
              "original_pdf_financials_verified":False}
        if path.exists():
            try:
                with fitz.open(path) as doc:
                    item["pages"]=len(doc)
                    item["extraction_status"]="candidates_extracted"
                    for key,labels in FIELDS.items():
                        raw=row.get(key,"")
                        try:
                            provider=float(raw)
                        except (TypeError,ValueError):
                            provider=None
                        evidence=candidates(doc,labels)
                        # Matching anywhere in nearby columns is weak evidence, not a verified value.
                        matches=[]
                        if provider is not None:
                            for e in evidence:
                                for n in e["numbers"]:
                                    try:
                                        val=float(n.replace(",","").replace("−","-"))
                                    except ValueError:
                                        continue
                                    for multiplier in (1,1000,10000,1000000,100000000):
                                        if abs(val*multiplier-provider)<=max(0.02,abs(provider)*1e-8):
                                            matches.append({"page":e["page"],"extracted":n,"unit_multiplier":multiplier})
                        item["fields"][key]={"provider_value_cny":provider,
                                            "candidate_contexts":evidence,
                                            "numeric_matches_unverified":matches[:15],
                                            "status":"candidate_match_requires_table_unit_and_column_review" if matches else "no_numeric_match_requires_review"}
            except Exception as exc:
                item["extraction_status"]="error"
                item["error"]=f"{type(exc).__name__}: {exc}"
        results.append(item)
        print(period,item["extraction_status"],item["pages"],flush=True)
    (a.output_dir/"pdf_field_evidence.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={"periods":len(results),
             "pdfs_found":sum(x["pdf_found"] for x in results),
             "pdfs_extracted":sum(x["extraction_status"]=="candidates_extracted" for x in results),
             "field_numeric_candidate_matches":sum(bool(v["numeric_matches_unverified"]) for x in results for v in x["fields"].values()),
             "total_fields":len(results)*len(FIELDS),
             "original_pdf_financials_verified":0,
             "approved_for_historical_valuation":0,
             "warning":"Numeric matching is a discovery aid, NOT proof: must verify consolidated tables, units, correct period/column, comparative restatements and source provenance."}
    (a.output_dir/"pdf_field_evidence_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["pdfs_extracted"]==0:
        raise RuntimeError("No PDF extracted; inspect evidence files.")
if __name__=="__main__":
    main()
