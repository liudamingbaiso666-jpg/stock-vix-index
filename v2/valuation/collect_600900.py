"""Collect 600900 historical financial statements and independently dated disclosures.

No financial value or disclosure date is synthesized. Raw API tables and
provenance are retained. Collection is NOT a point-in-time valuation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import time
from pathlib import Path
import pandas as pd
import requests
import akshare as ak

CODE="600900"
NAME="长江电力"
START="2020-01-01"
END="2026-12-31"
ENDPOINT="https://www.cninfo.com.cn/new/hisAnnouncement/query"
CATEGORIES={"annual":"category_ndbg_szsh","semiannual":"category_bndbg_szsh",
            "quarter1":"category_yjdbg_szsh","quarter3":"category_sjdbg_szsh"}
TABLES={"balance_sheet":"资产负债表","income_statement":"利润表","cash_flow":"现金流量表"}



def collect_eastmoney_disclosures(session):
    """Fallback notice index. Publication dates from the returned notice records only."""
    url="https://np-anotice-stock.eastmoney.com/api/security/ann"
    records=[]
    try:
        for page in range(1,30):
            params={"sr":"-1","page_size":"100","page_index":str(page),
                    "ann_type":"A","stock_list":CODE,"f_node":"0","s_node":"0",
                    "begin_time":START,"end_time":END}
            response=session.get(url,params=params,timeout=35,
                                 headers={"Referer":"https://data.eastmoney.com/"})
            response.raise_for_status()
            payload=response.json()
            data=payload.get("data") or {}
            items=data.get("list") or []
            for item in items:
                title=str(item.get("title",""))
                if "年度报告" in title:
                    kind="annual"
                elif "半年度报告" in title:
                    kind="semiannual"
                elif "第一季度报告" in title or "一季度报告" in title:
                    kind="quarter1"
                elif "第三季度报告" in title or "三季度报告" in title:
                    kind="quarter3"
                else:
                    continue
                published=str(item.get("notice_date",""))[:10]
                if not re.fullmatch(r"20\\d{2}-\\d{2}-\\d{2}",published):
                    continue
                art=str(item.get("art_code",""))
                if not art:
                    continue
                records.append({"code":CODE,"company":NAME,"category":kind,"title":title,
                                "published_date":published,"announcement_id":art,
                                "report_url":"https://data.eastmoney.com/notices/detail/600900/"+art+".html",
                                "source":"eastmoney_notice_index"})
            if len(items)<100:
                break
            time.sleep(.3)
        return records,None
    except Exception as exc:
        return records,f"{type(exc).__name__}: {exc}"

def collect_disclosures(session):
    records=[]
    errors={}
    for kind,category in CATEGORIES.items():
        try:
            for page in range(1,21):
                form={"pageNum":page,"pageSize":30,"column":"sse","tabName":"fulltext",
                      "plate":"","stock":CODE,"searchKey":"","secid":"",
                      "category":category,"trade":"","seDate":f"{START}~{END}",
                      "sortName":"time","sortType":"asc","isHLtitle":"true"}
                response=session.post(ENDPOINT,data=form,timeout=35,
                                      headers={"Referer":"https://www.cninfo.com.cn/","Origin":"https://www.cninfo.com.cn"})
                response.raise_for_status()
                data=response.json()
                rows=data.get("announcements")
                if rows is None:
                    raise ValueError(f"announcements=null (API returned no records); response keys={list(data)[:8]}")
                for item in rows:
                    title=re.sub("<[^>]*>","",str(item.get("announcementTitle","")))
                    if str(item.get("secCode",""))!=CODE:
                        continue
                    if not any(x in title for x in ("年度报告","半年度报告","季度报告","第一季度报告","第三季度报告")):
                        continue
                    # Retain corrections and abstracts, but distinguish from full reports.
                    ts=item.get("announcementTime")
                    if not isinstance(ts,(int,float)):
                        continue
                    published=dt.datetime.fromtimestamp(ts/1000,dt.timezone(dt.timedelta(hours=8))).date().isoformat()
                    path=item.get("adjunctUrl")
                    if not path:
                        continue
                    records.append({"code":CODE,"company":item.get("secName",NAME),
                                    "category":kind,"title":title,"published_date":published,
                                    "announcement_id":str(item.get("announcementId","")),
                                    "report_url":"https://static.cninfo.com.cn/"+path.lstrip("/"),
                                    "source":"cninfo_disclosure_api"})
                if len(rows)<30:
                    break
                time.sleep(.35)
        except Exception as exc:
            errors[kind]=f"{type(exc).__name__}: {exc}"
    if not records:
        fallback, fallback_error = collect_eastmoney_disclosures(session)
        records.extend(fallback)
        if fallback:
            errors["cninfo_primary"]="; ".join(f"{k}: {v}" for k,v in errors.items())
            for k in CATEGORIES:
                errors.pop(k,None)
        elif fallback_error:
            errors["eastmoney_fallback"]=fallback_error
    records=list({(r["announcement_id"],r["report_url"]):r for r in records}.values())
    records.sort(key=lambda r:(r["published_date"],r["category"],r["title"]))
    return records,errors


def collect_financial_tables():
    results={}
    errors={}
    for key,label in TABLES.items():
        try:
            df=ak.stock_financial_report_sina(stock="sh"+CODE,symbol=label)
            if df is None or df.empty:
                raise ValueError("empty financial table")
            # Preserve every original field; report period != public availability date.
            if "报告日" not in df.columns:
                raise ValueError("missing report-period field 报告日")
            dates=pd.to_datetime(df["报告日"],errors="coerce")
            df=df.loc[dates.ge(pd.Timestamp(START)) & dates.le(pd.Timestamp(END))].copy()
            if df.empty:
                raise ValueError("no periods in requested window")
            results[key]=df
        except Exception as exc:
            errors[key]=f"{type(exc).__name__}: {exc}"
    return results,errors


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; financial-disclosure-research/1.0)"})
    disclosures,d_errors=collect_disclosures(session)
    tables,f_errors=collect_financial_tables()
    pd.DataFrame(disclosures,columns=["code","company","category","title","published_date",
                                      "announcement_id","report_url","source"]).to_csv(
                                          args.output_dir/"disclosures.csv",index=False,encoding="utf-8-sig")
    for key,df in tables.items():
        df.to_csv(args.output_dir/f"{key}.csv",index=False,encoding="utf-8-sig")
    annual=[x for x in disclosures if x["category"]=="annual" and "年度报告" in x["title"]
            and "摘要" not in x["title"]]
    status="collected_partial"
    if len(annual)>=5 and len(tables)==3 and not f_errors:
        status="collected_unverified"
    if not disclosures and not tables:
        status="collection_failed"
    manifest={"version":"v2_6_600900_collection_v1","status":status,"stock":CODE,
              "collected_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
              "requested_range":[START,END],
              "sources":{"disclosure_api":ENDPOINT,
                         "financial_api":"AKShare stock_financial_report_sina; source Sina Finance"},
              "disclosure_count":len(disclosures),"full_annual_report_candidates":len(annual),
              "financial_periods":{k:len(v) for k,v in tables.items()},
              "disclosure_errors":d_errors,"financial_errors":f_errors,
              "important":["Financial report periods are NOT publication dates.",
                           "Announcement dates are publication dates for specific documents, not automatically for every numeric row.",
                           "Data not independently audited against original report PDFs.",
                           "No valuation or safety margin generated from unverified data.",
                           "API failures or partial coverage must not be silently filled."]}
    (args.output_dir/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False))
    if status=="collection_failed":
        raise RuntimeError("No financial or disclosure data obtained")


if __name__=="__main__":
    main()
