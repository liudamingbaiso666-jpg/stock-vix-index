"""V2.6 600900 historical fundamental audit: NO inferred intrinsic values.

Cross-check notice-index dates with provider statement dates, extract transparent
cash-flow / debt / share features, and flag corporate-action discontinuities.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

CFO="经营活动产生的现金流量净额"
CAPEX="购建固定资产、无形资产和其他长期资产所支付的现金"
CASH="货币资金"
DEBT=("短期借款","长期借款","应付债券","一年内到期的非流动负债")
SHARES="实收资本(或股本)"
NET_PROFIT="归属于母公司所有者的净利润"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--raw-dir",type=Path,required=True)
    ap.add_argument("--matched-dir",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    tables={}
    for name in ("cash_flow","balance_sheet","income_statement"):
        df=pd.read_csv(a.raw_dir/f"{name}.csv",dtype={"报告日":str},encoding="utf-8-sig")
        df["report_period"]=pd.to_datetime(df["报告日"],format="%Y%m%d").dt.strftime("%Y-%m-%d")
        if df["report_period"].duplicated().any():
            raise ValueError(f"Duplicate reporting periods in {name}")
        tables[name]=df.set_index("report_period")
    mapping=pd.read_csv(a.matched_dir/"report_availability_candidates.csv",dtype=str,encoding="utf-8-sig")
    if mapping["report_period"].duplicated().any():
        raise ValueError("Duplicate notice matches")
    out=mapping.copy().set_index("report_period")
    for name,df in tables.items():
        if set(out.index)!=set(df.index):
            raise ValueError(f"Reporting period mismatch: {name}")
        provider=pd.to_datetime(df["公告日期"],format="%Y%m%d",errors="coerce")
        index_date=pd.to_datetime(out["published_date"],errors="coerce")
        out[f"{name}_provider_date"]=provider.dt.strftime("%Y-%m-%d")
        out[f"{name}_date_agrees"]=provider.eq(index_date)
        out[f"{name}_source_audit"]=df["是否审计"].astype(str)
    cf=tables["cash_flow"]
    bs=tables["balance_sheet"]
    inc=tables["income_statement"]
    for label,source,column in (
        ("cfo_ytd_cny",cf,CFO),("capex_ytd_cny",cf,CAPEX),
        ("cash_cny",bs,CASH),("shares_reported_cny",bs,SHARES),
        ("net_profit_ytd_cny",inc,NET_PROFIT)):
        if column not in source:
            raise ValueError(f"Required column missing: {column}")
        out[label]=pd.to_numeric(source[column],errors="coerce")
    for col in DEBT:
        if col not in bs:
            raise ValueError(f"Required debt field missing: {col}")
        out["debt_"+col]=pd.to_numeric(bs[col],errors="coerce")
    debt_cols=["debt_"+c for c in DEBT]
    # A blank debt component is NOT treated as a confirmed zero.
    out["gross_debt_components_cny"]=out[debt_cols].sum(axis=1,min_count=1)
    out["debt_components_present"]=out[debt_cols].notna().sum(axis=1)
    out["net_debt_proxy_cny"]=out["gross_debt_components_cny"]-out["cash_cny"]
    out["fcf_ytd_proxy_cny"]=out["cfo_ytd_cny"]-out["capex_ytd_cny"]
    out=out.sort_index()
    out["shares_yoy_change_pct"]=100*(out["shares_reported_cny"]/out["shares_reported_cny"].shift(4)-1)
    out["large_share_change_flag"]=out["shares_yoy_change_pct"].abs()>5
    out["provider_date_all_agree"]=out[[f"{x}_date_agrees" for x in tables]].all(axis=1)
    out["complete_key_cashflows"]=out[["cfo_ytd_cny","capex_ytd_cny"]].notna().all(axis=1)
    out["complete_debt_components"]=out["debt_components_present"].eq(len(DEBT))
    out["cashflow_period_type"]="year_to_date_cumulative_not_quarterly"
    out["valuation_status"]="NOT_VALUED_requires_pdf_audit_and_model"
    out.reset_index().to_csv(a.output_dir/"historical_fundamental_audit.csv",index=False,encoding="utf-8-sig")
    result={
        "version":"v2_6_600900_fundamental_audit_v1",
        "periods":len(out),
        "provider_dates_agree_all_tables":int(out["provider_date_all_agree"].sum()),
        "provider_dates_disagree_or_missing":out.index[~out["provider_date_all_agree"]].tolist(),
        "complete_cashflow_periods":int(out["complete_key_cashflows"].sum()),
        "complete_debt_component_periods":int(out["complete_debt_components"].sum()),
        "share_change_flags":out.index[out["large_share_change_flag"].fillna(False)].tolist(),
        "valuation_ready":False,
        "limitations":[
            "All financial amounts are original CNY, not millions.",
            "Cash flows are cumulative year-to-date, not individual quarterly cash flows.",
            "Net debt is a proxy; debt fields may omit leases or other liabilities.",
            "Share capital in CNY must be verified as share count and adjusted for corporate actions.",
            "2023 asset consolidation/major restructuring requires explicit normalization before cross-year valuation.",
            "Provider and notice-index date agreement does not replace original PDF verification.",
            "No fair value, margin of safety, or backtest has been calculated."
        ]}
    (a.output_dir/"audit_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
