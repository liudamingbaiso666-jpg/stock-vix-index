"""V2 financial-quality screening: evidence-first, never equate index membership with quality.

Usage: python v2/quality_screen.py --mode cases
       python v2/quality_screen.py --mode full --batch 0 --batch-size 50
Each batch archives raw metrics and classifications, including failures.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import time
from pathlib import Path

import akshare as ak
import pandas as pd

BASE = Path(__file__).resolve().parent
CASES = {"601899": "紫金矿业", "600519": "贵州茅台", "600900": "长江电力"}
METRICS = {
    "roe": ["净资产收益率", "加权净资产收益率"],
    "gross_margin": ["销售毛利率", "毛利率"],
    "net_margin": ["销售净利率", "净利率"],
    "debt_ratio": ["资产负债率"],
    "operating_cashflow": ["经营活动产生的现金流量净额", "每股经营性现金流", "每股经营现金流"],
}
# Explicitly exploratory thresholds; no investment recommendations.
THRESHOLDS = {"roe": 10, "debt_ratio": 70}


def latest_universe() -> Path:
    paths = sorted((BASE / "data").glob("universe_*.json"))
    if not paths:
        raise RuntimeError("No archived universe in v2/data. Run V2 Stock Universe first.")
    return paths[-1]


def select_universe(mode: str, batch: int, batch_size: int) -> tuple[list[dict], str]:
    path = latest_universe()
    doc = json.loads(path.read_text(encoding="utf-8"))
    records = doc["records"]
    if len(records) < 800 or len({r["code"] for r in records}) != len(records):
        raise RuntimeError("Candidate universe count or uniqueness failed")
    by_code = {r["code"]: r for r in records}
    if mode == "cases":
        missing = set(CASES) - set(by_code)
        if missing:
            raise RuntimeError(f"Test cases missing from universe: {sorted(missing)}")
        selected = [by_code[c] for c in CASES]
    else:
        if batch < 0 or batch_size < 1 or batch_size > 100:
            raise ValueError("Invalid batch or batch-size")
        selected = sorted(records, key=lambda r: r["code"])[batch * batch_size:(batch + 1) * batch_size]
        if not selected:
            raise ValueError("Batch outside universe")
    return selected, doc["as_of"]


def metric_column(columns: list[str], terms: list[str]) -> str | None:
    for term in terms:
        for col in columns:
            if term in str(col):
                return str(col)
    return None


def number(value: object) -> float | None:
    if pd.isna(value):
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if s in {"", "-", "--", "nan", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_indicators(code: str) -> dict:
    # AkShare financial analysis endpoint may change its column labels.
    # Retain explicit source/columns and fail to "unrated" rather than invent metrics.
    raw = ak.stock_financial_analysis_indicator(symbol=code, start_year="2021")
    if raw is None or raw.empty:
        raise RuntimeError("Financial analysis endpoint returned no rows")
    date_col = metric_column(list(raw.columns), ["日期", "报告期", "报告日期"])
    if date_col is None:
        raise RuntimeError(f"No report date column: {list(raw.columns)[:15]}")
    frame = raw.copy()
    frame["_date"] = pd.to_datetime(frame[date_col], errors="coerce")
    frame = frame.dropna(subset=["_date"]).sort_values("_date")
    # Use only completed annual reports: avoid comparing Q1 and FY profitability.
    annual = frame[frame["_date"].dt.strftime("%m-%d") == "12-31"].tail(5)
    if annual.empty:
        raise RuntimeError("No dated annual reports available")
    result = {"source": "akshare.stock_financial_analysis_indicator",
              "report_dates": annual["_date"].dt.strftime("%Y-%m-%d").tolist(),
              "metrics": {}, "source_columns": {}}
    for key, terms in METRICS.items():
        col = metric_column(list(annual.columns), terms)
        result["source_columns"][key] = col
        result["metrics"][key] = [number(v) for v in annual[col]] if col else []
    return result


def classify(data: dict) -> tuple[str, list[str]]:
    m = data["metrics"]
    roe = [v for v in m["roe"] if v is not None]
    debt = [v for v in m["debt_ratio"] if v is not None]
    reasons = []
    if len(roe) < 3 or len(debt) < 3:
        return "unrated", ["Insufficient comparable annual ROE/debt observations"]
    if any(v < 0 for v in roe[-3:]):
        reasons.append("Negative ROE in one of last three annual observations")
    if debt[-1] > THRESHOLDS["debt_ratio"]:
        reasons.append("Latest annual debt ratio above exploratory threshold")
    if reasons:
        return "C_review", reasons
    if all(v >= THRESHOLDS["roe"] for v in roe[-3:]):
        return "A_candidate", ["Three annual ROE observations >= 10%; qualitative review required"]
    return "B_review", ["Profitability below exploratory A threshold or uneven"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cases", "full"], default="cases")
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    selected, universe_date = select_universe(args.mode, args.batch, args.batch_size)
    rows = []
    for i, item in enumerate(selected, 1):
        code = item["code"]
        entry = {"code": code, "name": item["name"], "indexes": item["indexes"],
                 "universe_date": universe_date, "status": "unrated", "reasons": [],
                 "financials": None, "error": None}
        try:
            entry["financials"] = fetch_indicators(code)
            entry["status"], entry["reasons"] = classify(entry["financials"])
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
            entry["reasons"] = ["Data unavailable; never treat as poor quality"]
        rows.append(entry)
        print(f"[{i}/{len(selected)}] {code} {entry['status']} {entry['error'] or ''}", flush=True)
        time.sleep(0.3)
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    folder = BASE / "quality" / today
    folder.mkdir(parents=True, exist_ok=True)
    suffix = "cases" if args.mode == "cases" else f"batch_{args.batch:02d}"
    path = folder / f"{suffix}.json"
    # Re-running the same date does not overwrite historical evidence.
    if path.exists():
        print(f"Preserving existing {path}")
        return
    payload = {"date": today, "universe_date": universe_date, "mode": args.mode,
               "batch": args.batch if args.mode == "full" else None,
               "count": len(rows), "records": rows}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} observations to {path}")
    if args.mode == "cases" and any(row["error"] for row in rows):
        raise RuntimeError("Case validation incomplete: saved diagnostics; review source compatibility")


if __name__ == "__main__":
    main()
