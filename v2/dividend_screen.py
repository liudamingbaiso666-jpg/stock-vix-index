"""V2.2 shareholder-return evidence layer (no fabricated yields or payouts).

Input: normalized, verified annual dividends CSV (see documentation).
Use: python v2/dividend_screen.py --input v2/dividends_input.csv
     python -m unittest discover -s v2/tests -p 'test_*.py'
No price data => no dividend yield. No FCF data => no FCF coverage.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
VERSION = "dividend_v2_2"
FIELDS = ("code", "fiscal_year", "cash_dividend_per_share_cny",
          "eps_cny", "free_cash_flow_per_share_cny", "price_cny",
          "price_date", "source", "source_date")
MIN_YEAR = 2015


def finite_nonnegative(value: str, name: str) -> float | None:
    if not value.strip():
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError(f"CSV must contain {FIELDS}")
        rows = []
        seen = set()
        for line, row in enumerate(reader, 2):
            code = row["code"].strip().zfill(6)
            year = int(row["fiscal_year"])
            if not (code.isdigit() and len(code) == 6 and MIN_YEAR <= year <= dt.date.today().year):
                raise ValueError(f"Invalid code/year on line {line}")
            if (code, year) in seen:
                raise ValueError(f"Duplicate code/year on line {line}; aggregate interim and final payouts first")
            seen.add((code, year))
            source = row["source"].strip()
            source_date = row["source_date"].strip()
            if not source or not source_date:
                raise ValueError(f"Source and source_date required on line {line}")
            dt.date.fromisoformat(source_date)
            price_date = row["price_date"].strip()
            if price_date:
                dt.date.fromisoformat(price_date)
            nums = {k: finite_nonnegative(row[k], k) for k in
                    ("cash_dividend_per_share_cny", "eps_cny",
                     "free_cash_flow_per_share_cny", "price_cny")}
            if nums["price_cny"] is not None and (nums["price_cny"] == 0 or not price_date):
                raise ValueError(f"Positive price and price_date required on line {line}")
            if price_date and nums["price_cny"] is None:
                raise ValueError(f"Price date without price on line {line}")
            rows.append({"code": code, "fiscal_year": year, **nums,
                         "price_date": price_date or None,
                         "source": source, "source_date": source_date})
    return rows


def ratio(num: float | None, den: float | None) -> float | None:
    return round(num / den, 6) if num is not None and den is not None and den > 0 else None


def evaluate(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda x: x["fiscal_year"])
    years = [r["fiscal_year"] for r in rows]
    latest = rows[-1]
    # Require five consecutive years for continuity; never infer missing years as zero.
    five = rows[-5:]
    contiguous = len(five) == 5 and [r["fiscal_year"] for r in five] == list(range(five[0]["fiscal_year"], five[0]["fiscal_year"] + 5))
    known = contiguous and all(r["cash_dividend_per_share_cny"] is not None for r in five)
    paid_years = sum(r["cash_dividend_per_share_cny"] > 0 for r in five) if known else None
    d = latest["cash_dividend_per_share_cny"]
    payout = ratio(d, latest["eps_cny"])
    fcf_coverage = ratio(latest["free_cash_flow_per_share_cny"], d) if d and d > 0 else None
    # Current price may be quoted on different date than annual payout: explicitly label trailing.
    trailing_yield = ratio(d, latest["price_cny"])
    growth = None
    if known and five[0]["cash_dividend_per_share_cny"] > 0 and five[-1]["cash_dividend_per_share_cny"] is not None:
        growth = round((five[-1]["cash_dividend_per_share_cny"] / five[0]["cash_dividend_per_share_cny"]) ** (1 / 4) - 1, 6)
    flags = []
    if payout is not None and payout > 1:
        flags.append("Cash dividend exceeds reported EPS; inspect earnings and balance sheet")
    if fcf_coverage is not None and fcf_coverage < 1:
        flags.append("Reported FCF/share does not fully cover dividend; inspect capex cycle")
    if not known:
        flags.append("Five-year continuity unknown due to missing fiscal years or payouts")
    if d is None:
        flags.append("Latest annual cash dividend unknown")
    return {"code": latest["code"], "model_version": VERSION,
            "latest_fiscal_year": latest["fiscal_year"], "five_years_complete": known,
            "paid_years_of_five": paid_years,
            "latest_cash_dividend_per_share_cny": d,
            "payout_ratio": payout, "fcf_dividend_coverage": fcf_coverage,
            "trailing_dividend_yield": trailing_yield, "price_date": latest["price_date"],
            "dividend_cagr_4y": growth, "review_flags": flags,
            "classification": "manual_review_required",
            "evidence": [{"fiscal_year": r["fiscal_year"], "source": r["source"],
                          "source_date": r["source_date"]} for r in rows]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    rows = read_rows(args.input)
    groups = defaultdict(list)
    for row in rows:
        groups[row["code"]].append(row)
    result = {"model_version": VERSION,
              "limitations": ["Verified input CSV required; no live price inferred",
                              "Fiscal-year payouts must be aggregated and adjusted for share changes",
                              "FCF depends on accounting definition; compare like-for-like",
                              "High yield is not a buy signal; no dividend double-counting in valuation"],
              "count": len(groups),
              "records": [evaluate(group) for _, group in sorted(groups.items())]}
    out = args.output or BASE / "dividends" / f"dividend_screen_{dt.date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"Archive already exists: {out}")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Archived {len(groups)} company dividend reviews to {out}")


if __name__ == "__main__":
    main()
