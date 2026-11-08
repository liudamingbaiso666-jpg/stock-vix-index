"""Build a validated A-share candidate universe from CSI index constituents."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import pandas as pd
import akshare as ak

INDEXES = {"CSI300": "000300", "CSIA50": "930050", "CSI500": "000905"}
EXPECTED = {"000300": 300, "930050": 50, "000905": 500}
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data"


def normalize_code(value: object) -> str:
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    if "." in value:
        value = value.split(".")[0]
    if not value.isdigit() or len(value) > 6:
        raise ValueError(f"Invalid stock code: {value!r}")
    return value.zfill(6)


def fetch_constituents(index_code: str) -> tuple[pd.DataFrame, str]:
    # CSI official constituent snapshot via AkShare; never use duplicate-prone Sina endpoint.
    raw = ak.index_stock_cons_csindex(symbol=index_code)
    if raw is None or raw.empty:
        raise RuntimeError(f"Empty CSI constituent data for {index_code}")
    required = {"成分券代码", "成分券名称", "日期"}
    if not required.issubset(raw.columns):
        raise RuntimeError(f"Unexpected CSI columns for {index_code}: {list(raw.columns)}")
    dates = pd.to_datetime(raw["日期"], errors="coerce")
    if dates.isna().any() or dates.dt.date.nunique() != 1:
        raise RuntimeError(f"Missing/inconsistent snapshot dates for {index_code}")
    snapshot_date = dates.iloc[0].date()
    today_cn = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    age = (today_cn - snapshot_date).days
    if age < 0 or age > 45:
        raise RuntimeError(f"CSI snapshot for {index_code} is future/stale: "
                           f"{snapshot_date}, age {age} days")
    out = pd.DataFrame({
        "code": raw["成分券代码"].map(normalize_code),
        "name": raw["成分券名称"].astype(str).str.strip(),
    })
    expected = EXPECTED[index_code]
    if len(out) != expected or out.code.nunique() != expected:
        raise RuntimeError(f"{index_code}: expected {expected} distinct constituents, "
                           f"got {len(out)} rows, {out.code.nunique()} distinct")
    if out["name"].eq("").any() or out["name"].eq("nan").any():
        raise RuntimeError(f"Missing stock names for {index_code}")
    print(f"[CSI] {index_code}: {expected} unique stocks, snapshot {snapshot_date}", flush=True)
    return out, snapshot_date.isoformat()


def main() -> None:
    rows: dict[str, dict] = {}
    counts: dict[str, int] = {}
    dates: dict[str, str] = {}
    for name, code in INDEXES.items():
        frame, snapshot_date = fetch_constituents(code)
        counts[name] = len(frame)
        dates[name] = snapshot_date
        for record in frame.to_dict("records"):
            stock_code = record["code"]
            if stock_code not in rows:
                rows[stock_code] = {"code": stock_code, "name": record["name"], "indexes": []}
            elif rows[stock_code]["name"] != record["name"]:
                raise RuntimeError(f"Conflicting stock names across indexes: {stock_code}")
            rows[stock_code]["indexes"].append(name)
    if not 800 <= len(rows) <= 850:
        raise RuntimeError(f"Unexpected union count {len(rows)}; no output written")
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    records = [
        {"code": row["code"], "name": row["name"],
         "indexes": "|".join(sorted(row["indexes"])),
         "quality_status": "pending", "valuation_status": "pending"}
        for row in sorted(rows.values(), key=lambda x: x["code"])
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT / f"universe_{date}.csv"
    json_path = OUTPUT / f"universe_{date}.json"
    # Immutable per-day archives: never silently overwrite an earlier snapshot.
    if csv_path.exists() or json_path.exists():
        if csv_path.exists() and json_path.exists():
            print(f"Snapshot for {date} already archived; preserving original files.", flush=True)
            return
        raise RuntimeError(f"Incomplete existing snapshot for {date}; manual review required")
    pd.DataFrame(records).to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps({
        "as_of": date, "fetched_at_utc": fetched_at,
        "source": "AKShare index_stock_cons_csindex",
        "index_codes": INDEXES, "counts": counts,
        "snapshot_dates": dates, "unique_count": len(rows),
        "records": records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} validated candidate stocks to {csv_path}")


if __name__ == "__main__":
    main()
