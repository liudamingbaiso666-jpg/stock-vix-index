"""Aggregate 16 independent V2 quality-screen batches; never imply missing = weak."""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path


def aggregate(root: Path):
    files = sorted(root.rglob("batch_*_quality_v2_1.json"))
    by_batch = {}
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        b = doc.get("batch")
        if b not in range(16):
            continue
        if b in by_batch:
            raise ValueError(f"Duplicate batch {b}: {p}")
        by_batch[b] = doc
    records = [r for b in sorted(by_batch) for r in by_batch[b]["records"]]
    codes = [r["code"] for r in records]
    if len(codes) != len(set(codes)):
        raise ValueError("Duplicate stock codes across batches")
    counts = dict(collections.Counter(r["status"] for r in records))
    errors = [{"code": r["code"], "error": r["error"]} for r in records if r.get("error")]
    dates = sorted(set(doc.get("universe_date") for doc in by_batch.values()))
    expected_counts = {b: 50 for b in range(16)}
    complete = (len(by_batch) == 16 and len(records) == 800 and
                all(by_batch[b].get("count") == expected_counts[b] for b in range(16))
                and len(dates) == 1)
    return {"model_version": "quality_v2_1_aggregate", "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "complete_universe_coverage": complete, "batches_found": sorted(by_batch),
            "missing_batches": sorted(set(range(16)) - set(by_batch)),
            "universe_dates": dates, "observations": len(records),
            "status_counts": counts, "api_error_count": len(errors),
            "api_errors": errors, "records": records,
            "limitations": ["Quality statuses are preliminary triage, not verified quality classifications",
                            "Missing financial data is unrated, never interpreted as low quality",
                            "Financial observations are not point-in-time validated for backtesting",
                            "Dividend module is supplementary and not included in these quality scores"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = aggregate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("complete_universe_coverage", "observations", "status_counts", "api_error_count", "missing_batches")}, ensure_ascii=False))
    if not result["complete_universe_coverage"]:
        raise RuntimeError("Incomplete 800-stock coverage; diagnostic summary archived")


if __name__ == "__main__":
    main()
