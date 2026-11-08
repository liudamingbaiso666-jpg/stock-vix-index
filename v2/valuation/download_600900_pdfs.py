"""Archive original periodic-report PDF candidates, without pretending to verify numbers.

Resolves Eastmoney announcement IDs through its notice-detail API. A successful
HTTP download is not proof of PDF authenticity; provenance remains explicit.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import requests

API="https://np-anotice-stock.eastmoney.com/api/content/ann"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mapping",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    rows=pd.read_csv(a.mapping,dtype=str,encoding="utf-8-sig").fillna("")
    session=requests.Session()
    session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; VIX-research/2.6)"})
    results=[]
    for row in rows.to_dict("records"):
        entry={k:row[k] for k in ("report_period","published_date","announcement_id","report_url")}
        entry.update(status="unresolved",pdf_url="",sha256="",bytes=0,error="",source="eastmoney_notice_detail")
        try:
            response=session.get(API,params={"art_code":row["announcement_id"],"client_source":"web","page_index":1},timeout=25)
            response.raise_for_status()
            payload=response.json()
            data=payload.get("data") or {}
            # Eastmoney detail commonly returns attach_url; no URL is guessed.
            pdf=data.get("attach_url") or data.get("attachUrl") or ""
            if pdf.startswith("/"):
                pdf="https://pdf.dfcfw.com"+pdf
            if pdf.startswith("http://") or pdf.startswith("https://"):
                host=urlparse(pdf).hostname or ""
                if not (host=="dfcfw.com" or host.endswith(".dfcfw.com") or host=="eastmoney.com" or host.endswith(".eastmoney.com")):
                    raise ValueError("Unexpected PDF host: "+host)
                resp=session.get(pdf,timeout=45)
                resp.raise_for_status()
                blob=resp.content
                if not blob.startswith(b"%PDF-"):
                    raise ValueError("Attachment does not have PDF signature")
                filename=row["report_period"]+"_"+row["announcement_id"]+".pdf"
                (a.output_dir/filename).write_bytes(blob)
                entry.update(status="downloaded_unverified",pdf_url=pdf,
                             sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob))
            else:
                entry["error"]="No attachment URL in detail response; keys="+str(list(data.keys())[:20])
        except Exception as exc:
            entry.update(status="failed",error=f"{type(exc).__name__}: {exc}")
        results.append(entry)
        print(entry["report_period"],entry["status"],entry["error"][:160],flush=True)
    pd.DataFrame(results).to_csv(a.output_dir/"pdf_provenance.csv",index=False,encoding="utf-8-sig")
    summary={"total":len(results),"downloaded_unverified":sum(x["status"]=="downloaded_unverified" for x in results),
             "unresolved_or_failed":sum(x["status"]!="downloaded_unverified" for x in results),
             "verified_financial_periods":0,
             "note":"PDFs are candidates from announcement detail links. Financial fields have NOT been checked against PDFs; no historical valuation is authorized."}
    (a.output_dir/"pdf_collection_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
    if summary["downloaded_unverified"]==0:
        raise RuntimeError("No PDF retrieved. Review pdf_provenance.csv; do not mark historical values verified.")
if __name__=="__main__":
    main()
