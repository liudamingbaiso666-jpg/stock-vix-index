"""V2.6 geometric table-row audit of original 600900 report PDFs.

A match is only a row/column evidence candidate; it never automatically
approves a point-in-time valuation. Uses PyMuPDF word geometry rather than
concatenating adjacent text lines.
"""
import argparse,json,re
from pathlib import Path
import fitz,pandas as pd

FIELDS={
 "cfo_ytd_cny":["经营活动产生的现金流量净额"],
 "capex_ytd_cny":["购建固定资产、无形资产和其他长期资产支付的现金","购建固定资产、无形资产和其他长期资产所支付的现金"],
 "net_profit_ytd_cny":["归属于母公司股东的净利润","归属于母公司所有者的净利润"],
 "cash_cny":["货币资金"],
 "shares_reported_cny":["实收资本(或股本)","实收资本（或股本）","股本"]
}
NUM=re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")
def normalize(s):
 return re.sub(r"\s+","",s).replace("（","(").replace("）",")")
def row_candidates(page,labels):
 words=page.get_text("words",sort=True)
 rows={}
 for w in words:
  x0,y0,x1,y1,t,block,line,word=w
  key=(block,line)
  rows.setdefault(key,[]).append((x0,t,y0,y1))
 out=[]
 for (block,line),items in rows.items():
  items.sort()
  text="".join(t for _,t,_,_ in items)
  match=next((v for v in labels if normalize(v) in normalize(text)),None)
  if match:
   numeric=[{"x":round(x,1),"value":t} for x,t,_,_ in items if NUM.fullmatch(t.replace("−","-"))]
   out.append({"page":page.number+1,"block":block,"line":line,
               "row_text":text[:350],"numeric_cells":numeric,
               "candidate_label":match})
 return out
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--pdf-dir",type=Path,required=True)
 ap.add_argument("--audit-file",type=Path,required=True)
 ap.add_argument("--output-dir",type=Path,required=True)
 a=ap.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 df=pd.read_csv(a.audit_file,dtype={"code":str},encoding="utf-8-sig").fillna("")
 results=[]
 for row in df.to_dict("records"):
  path=a.pdf_dir/(row["report_period"]+"_"+row["announcement_id"]+".pdf")
  item={"report_period":row["report_period"],"pdf_found":path.exists(),"fields":{},"status":"missing"}
  if path.exists():
   try:
    with fitz.open(path) as doc:
     item["status"]="geometry_extracted"
     for key,labels in FIELDS.items():
      ev=[]
      for page in doc:
       ev.extend(row_candidates(page,labels))
      provider=float(row[key]) if str(row[key]).strip() else None
      hits=[]
      if provider is not None:
       for e in ev:
        for cell in e["numeric_cells"]:
         val=float(cell["value"].replace(",","").replace("−","-"))
         if abs(val-provider)<=max(0.02,abs(provider)*1e-9):
          hits.append({"page":e["page"],"block":e["block"],"line":e["line"],"x":cell["x"],"value":cell["value"]})
      item["fields"][key]={"provider_value_cny":provider,"matching_row_cells":hits[:30],
        "row_evidence":ev[:60],
        "status":"row_match_unverified" if hits else "no_row_match_or_wrapped_label",
        "pdf_column_verified":False,"consolidated_statement_verified":False}
   except Exception as e:
    item["status"]="error";item["error"]=str(e)
  results.append(item)
  print(row["report_period"],item["status"],flush=True)
 (a.output_dir/"geometric_row_evidence.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
 summary={"periods":len(results),"pdfs_processed":sum(x["status"]=="geometry_extracted" for x in results),
  "same_row_numeric_candidates":sum(bool(f["matching_row_cells"]) for x in results for f in x["fields"].values()),
  "total_fields":len(results)*len(FIELDS),"approved_for_historical_valuation":0,
  "limitations":["PDF row grouping may split wrapped labels or merged numeric columns.",
                 "Matching same row is not proof of current-period consolidated figures.",
                 "Need source table title, units, reporting column and corporate-action validation."]}
 (a.output_dir/"geometric_row_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
 if summary["pdfs_processed"]==0:raise RuntimeError("No PDFs processed")
if __name__=="__main__":main()
