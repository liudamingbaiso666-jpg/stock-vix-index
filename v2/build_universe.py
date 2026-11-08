"""Build a versioned A-share index-union candidate universe.

Run: python v2/build_universe.py
Requires: akshare, pandas (already in repository requirements.txt).
Fails closed: never publishes a partial universe when any source fails.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import pandas as pd
import akshare as ak

INDEXES = {
    "CSI300": "000300",
    "CSIA50": "930050",
    "CSI500": "000905",
}
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data"


def normalize_code(value: object) -> str:
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    elif "." in s:
        s = s.split(".")[0]
    if not s.isdigit() or len(s) > 6:
        raise ValueError(f"Invalid stock code: {value!r}")
    return s.zfill(6)


def fetch_constituents(index_code: str) -> pd.DataFrame:
    # AkShare's index_stock_cons endpoint uses index codes; upstream schema
    # may change, so validate explicitly instead of silently writing bad data.
    raw = ak.index_stock_cons(symbol=index_code)
    if raw is None or raw.empty:
        raise RuntimeError(f"Empty constituent data for {index_code}")
    code_candidates = ["品种代码", "成分券代码", "证券代码", "股票代码", "代码"]
    name_candidates = ["品种名称", "成分券名称", "证券简称", "股票简称", "名称"]
    code_col = next((c for c in code_candidates if c in raw.columns), None)
    name_col = next((c for c in name_candidates if c in raw.columns), None)
    if code_col is None:
        raise RuntimeError(f"Unexpected columns for {index_code}: {list(raw.columns)}")
    out = pd.DataFrame({
        "code": raw[code_col].map(normalize_code),
        "name": raw[name_col].astype(str).str.strip() if name_col else "",
    })
    duplicate_rows = out.loc[out.code.duplicated(keep=False)].sort_values("code")
    if not duplicate_rows.empty:
        print(f"[DIAGNOSTIC] {index_code}: {len(out)} raw rows, "
              f"{out.code.nunique()} unique codes, "
              f"{len(duplicate_rows)} rows involving duplicate codes", flush=True)
        print(duplicate_rows.head(30).to_string(index=False), flush=True)
        conflicts = duplicate_rows.groupby("code")["name"].nunique(dropna=False)
        if (conflicts > 1).any():
            raise RuntimeError(
                f"Conflicting names for duplicate codes in {index_code}: "
                f"{conflicts[conflicts > 1].index.tolist()[:20]}"
            )
        out = out.drop_duplicates(subset=["code"], keep="first").copy()
        print(f"[DIAGNOSTIC] {index_code}: removed duplicate rows; "
              f"{len(out)} unique codes remain", flush=True)
    if not 40 <= len(out) <= 600:
        raise RuntimeError(f"Implausible constituent count for {index_code}: {len(out)}")
    return out


def main() -> None:
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    snapshots = {}
    rows = {}
    for index_name, index_code in INDEXES.items():
        frame = fetch_constituents(index_code)
        snapshots[index_name] = len(frame)
        for record in frame.to_dict("records"):
            code = record["code"]
            if code not in rows:
                rows[code] = {"code": code, "name": record["name"], "indexes": []}
            rows[code]["indexes"].append(index_name)
            if not rows[code]["name"] and record["name"]:
                rows[code]["name"] = record["name"]
    if not 500 <= len(rows) <= 900:
        raise RuntimeError(f"Unexpected union size: {len(rows)}; no files written")
    date = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_csv = OUTPUT / f"universe_{date}.csv"
    output_json = OUTPUT / f"universe_{date}.json"
    frame = pd.DataFrame([
        {"code": v["code"], "name": v["name"],
         "indexes": "|".join(sorted(v["indexes"])),
         "quality_status": "pending", "valuation_status": "pending"}
        for v in sorted(rows.values(), key=lambda x: x["code"])
    ])
    # Avoid publishing partial data: validation above must finish first.
    frame.to_csv(output_csv, index=False, encoding="utf-8-sig")
    output_json.write_text(json.dumps({
        "as_of": date, "fetched_at_utc": fetched_at,
        "source": "AkShare index_stock_cons",
        "index_codes": INDEXES, "counts": snapshots,
        "unique_count": len(rows), "records": frame.to_dict("records")
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} unique stocks to {output_csv}")


if __name__ == "__main__":
    main()
