"""Fetch RAW A-share dividend history for three calibration cases.

This is a source-adapter/provenance step, NOT normalized fiscal-year dividends.
Never infer fiscal year from ex-dividend date or count proposals as paid.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import inspect
import time
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parent
CASES = {"601899": "紫金矿业", "600519": "贵州茅台", "600900": "长江电力"}
MODEL = "dividend_raw_v2_2_1"


def normalize_cell(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (dt.date, dt.datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def collect(code: str, name: str) -> dict:
    entry = {"code": code, "name": name, "source": "akshare.stock_history_dividend_detail",
             "source_parameters": {"symbol": code, "indicator": "分红"},
             "status": "error", "columns": [], "rows": [], "error": None}
    try:
        signature = inspect.signature(ak.stock_history_dividend_detail)
        if "symbol" not in signature.parameters or "indicator" not in signature.parameters:
            raise RuntimeError(f"Unexpected dividend API signature: {signature}")
        frame = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if frame is None or frame.empty:
            entry["status"] = "empty"
            return entry
        entry["columns"] = [str(c) for c in frame.columns]
        if "公告日期" not in entry["columns"]:
            raise RuntimeError(f"Unexpected dividend response columns: {entry['columns\']}")
        entry["rows"] = [{str(k): normalize_cell(v) for k, v in row.items()}
                         for row in frame.to_dict(orient="records")]
        entry["status"] = "raw_collected"
    except Exception as exc:
        entry["error"] = f"{type(exc).__name__}: {exc}"[:600]
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    result = {"model_version": MODEL, "retrieved_at_utc": now.isoformat(),
              "normalization_status": "not_normalized",
              "warnings": [
                  "Rows may include proposed/unimplemented dividends",
                  "Distribution fiscal year and payment/ex-dividend dates are different",
                  "Cash dividend unit and share adjustment must be verified against disclosures",
                  "Raw dividend records alone do not establish EPS, FCF or dividend yield"
              ], "records": []}
    for code, name in CASES.items():
        entry = collect(code, name)
        result["records"].append(entry)
        print(code, entry["status"], len(entry["rows"]), entry["error"] or "", flush=True)
        time.sleep(0.5)
    run_id = os.environ.get("GITHUB_RUN_ID", now.strftime("%H%M%S%f"))
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    out = args.output or ROOT / "dividends" / now.date().isoformat() / f"cases_{MODEL}_run_{run_id}_attempt_{attempt}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"Existing archive preserved: {out}")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Saved raw source evidence: {out}")
    if any(r["status"] != "raw_collected" for r in result["records"]):
        raise RuntimeError("Raw source acquisition incomplete; diagnostics archived")


if __name__ == "__main__":
    main()
