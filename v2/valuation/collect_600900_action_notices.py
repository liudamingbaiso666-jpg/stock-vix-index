"""Discover and archive targeted original issuer notices for share changes and cash dividends.
Candidate evidence only: PDFs and titles are not independently authenticated or audited.
"""
import argparse,datetime as dt,hashlib,json,re,time
from pathlib import Path
import requests
INDEX="https://np-anotice-stock.eastmoney.com/api/security/ann"
DETAIL="https://np-cnotice-stock.eastmoney.com/api/content/ann"
def category(title):
 if re.search("权益分派实施公告|利润分配实施公告|分红派息实施公告|权益分派实施",title):return "dividend"
 if re.search("股份发行结果|发行结果暨股本变动|股本变动公告|股份变动公告|新增股份上市|发行股份购买资产实施",title):return "shares"
 return None
def main():
 p=argparse.ArgumentParser();p.add_argument("--output-dir",required=True,type=Path)
 a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
 s=requests.Session();s.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://data.eastmoney.com/"})
 found=[];errors=[];seen=set()
 for year in range(2020,2027):
  for page in range(1,16):
   try:
    resp=s.get(INDEX,params={"sr":"-1","page_size":"100","page_index":page,"ann_type":"A","stock_list":"600900","client_source":"web","f_node":"0","s_node":"0","begin_time":f"{year}-01-01","end_time":f"{year}-12-31"},timeout=30)
    resp.raise_for_status();items=(resp.json().get("data") or {}).get("list") or []
    for item in items:
     title=str(item.get("title",""));kind=category(title);art=str(item.get("art_code",""))
     date=str(item.get("notice_date",""))[:10]
     if not kind or not art or art in seen:continue
     seen.add(art);found.append({"date":date,"title":title,"kind":kind,"art_code":art})
    if len(items)<100:break
    time.sleep(.12)
   except Exception as e:
    errors.append({"year":year,"page":page,"error":str(e)});break
 # Limit PDFs to key corporate-action years and recent dividend notices;
 # retain full discovered index for independent future review.
 targets=[r for r in found if (r["kind"]=="shares" and r["date"][:4] in ("2020","2023")) or
          (r["kind"]=="dividend" and r["date"][:4] in ("2023","2024","2025","2026"))]
 targets=sorted(targets,key=lambda r:(r["date"],r["art_code"]))[:40]
 for r in targets:
  r.update(status="unresolved",pdf_url="",sha256="",bytes=0,error="")
  try:
   resp=s.get(DETAIL,params={"art_code":r["art_code"],"client_source":"web","page_index":1},timeout=25)
   resp.raise_for_status();data=resp.json().get("data") or {}
   url=data.get("attach_url") or data.get("attachUrl") or ""
   if not url:url="https://pdf.dfcfw.com/pdf/H2_"+r["art_code"]+"_1.pdf"
   if url.startswith("/"):url="https://pdf.dfcfw.com"+url
   if not url.startswith("https://") or not any(x in url.split("/")[2] for x in ("eastmoney.com","dfcfw.com")):raise ValueError("Unexpected PDF host")
   pdf=s.get(url,timeout=45);pdf.raise_for_status()
   if not pdf.content.startswith(b"%PDF-"):raise ValueError("Not PDF content")
   name=r["date"]+"_"+r["art_code"]+".pdf"
   (a.output_dir/name).write_bytes(pdf.content)
   r.update(status="downloaded_unverified",pdf_url=url,sha256=hashlib.sha256(pdf.content).hexdigest(),bytes=len(pdf.content))
  except Exception as e:r.update(status="failed",error=str(e))
  print(r["date"],r["kind"],r["status"],r["title"][:40],flush=True)
 (a.output_dir/"notice_index.json").write_text(json.dumps(found,ensure_ascii=False,indent=2),encoding="utf-8")
 (a.output_dir/"pdf_evidence_manifest.json").write_text(json.dumps(targets,ensure_ascii=False,indent=2),encoding="utf-8")
 summary={"indexed_targeted_notices":len(found),"selected_pdfs":len(targets),
 "downloaded_pdf_candidates":sum(r["status"]=="downloaded_unverified" for r in targets),
 "failed_pdfs":sum(r["status"]=="failed" for r in targets),"index_errors":errors,
 "original_notice_values_verified":0,"approved_for_valuation":False,
 "warning":"Titles/PDFs are archival candidates only; no share amount, dividend unit or effective date has been verified against their text."}
 (a.output_dir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False))
 if not found:raise RuntimeError("No targeted notices found; inspect index errors")
if __name__=="__main__":main()
