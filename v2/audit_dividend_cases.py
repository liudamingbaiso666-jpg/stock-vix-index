"""Audit AKShare dividend raw data without guessing fiscal year or per-share units."""
import argparse
import datetime as dt
import json
from pathlib import Path

FIELDS = ("公告日期", "派息", "进度", "除权除息日", "股权登记日")
EXPECTED = {"601899", "600519", "600900"}


def audit(doc):
    results = []
    for item in doc["records"]:
        code = item["code"]
        rows = item["rows"]
        columns = set(item["columns"])
        missing = sorted(set(FIELDS) - columns)
        duplicate_keys = set()
        seen = set()
        invalid_dates = []
        statuses = {}
        cash_values = []
        for i, row in enumerate(rows):
            status = str(row.get("进度") or "")
            statuses[status] = statuses.get(status, 0) + 1
            key = (row.get("公告日期"), row.get("除权除息日"), row.get("派息"))
            if key in seen:
                duplicate_keys.add(str(key))
            seen.add(key)
            for field in ("公告日期", "除权除息日", "股权登记日"):
                value = row.get(field)
                if value:
                    try:
                        dt.date.fromisoformat(str(value)[:10])
                    except ValueError:
                        invalid_dates.append({"row": i, "field": field, "value": value})
            cash = row.get("派息")
            if cash is not None:
                try:
                    cash_values.append(float(cash))
                except (ValueError, TypeError):
                    pass
        results.append({"code": code, "row_count": len(rows), "missing_columns": missing,
                        "status_counts": statuses, "duplicate_key_count": len(duplicate_keys),
                        "duplicate_keys": sorted(duplicate_keys),
                        "invalid_dates": invalid_dates,
                        "cash_min_raw": min(cash_values) if cash_values else None,
                        "cash_max_raw": max(cash_values) if cash_values else None,
                        "unit": "UNVERIFIED: raw 派息 is not per-share dividend",
                        "fiscal_year": "UNVERIFIED: do not infer from announcement/ex-date",
                        "eligible_for_annual_metrics": False})
    return {"model_version": "dividend_audit_v2_2", "source_version": doc.get("model_version"),
            "total_records": sum(x["row_count"] for x in results),
            "all_expected_cases_present": {x["code"] for x in results} == EXPECTED,
            "cases": results, "next_required": [
                "Verify raw 派息 unit against exchange or issuer dividend implementation notice",
                "Link each implementation to fiscal-year distribution resolution",
                "Reconcile interim and final payments, share capital adjustments",
                "Only then calculate payout ratio, cash coverage and trailing yield"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    doc = json.loads(args.input.read_text(encoding="utf-8"))
    result = audit(doc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total_records": result["total_records"],
                      "cases": [{"code": x["code"], "count": x["row_count"],
                                 "statuses": x["status_counts"]} for x in result["cases"]]},
                     ensure_ascii=False))
    if not result["all_expected_cases_present"] or any(x["missing_columns"] for x in result["cases"]):
        raise RuntimeError("Raw source missing expected companies or columns")


if __name__ == "__main__":
    main()
