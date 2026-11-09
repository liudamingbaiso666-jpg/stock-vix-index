"""V1.1 observational comparison on backtest_pr.py output.
Usage: python v2/compare_v11.py --backtest v2/reports/pr_backtest.csv --output v2/reports/v11_comparison.csv
The backtest must contain natr_20 and cmf_20 columns from V1.1 snapshots.
Quartiles are per-date; this is descriptive, not a trading strategy or a causal test.
"""
import argparse
from pathlib import Path
import pandas as pd

HORIZONS = (1, 3, 5, 10, 20)
FIELDS = ("natr_20", "cmf_20")

def compare(input_csv, output_csv):
    d = pd.read_csv(input_csv, dtype={"code": str})
    required = {"code", "date", "pressure_score", "repair_score", *FIELDS}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}. Regenerate backtest with V1.1 snapshots.")
    if d.duplicated(["code", "date"]).any():
        raise ValueError("Duplicate code/date rows")
    for col in FIELDS + ("pressure_score", "repair_score"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    # Only compare within selloff contexts, to avoid rewarding ordinary uptrends.
    if "selloff_context" not in d.columns:
        raise ValueError("Missing selloff_context: update backtest snapshot column selection")
    d = d[d.selloff_context.astype(str).str.lower().isin(("true", "1"))].copy()
    if d.empty:
        raise ValueError("No selloff-context observations")
    for col in FIELDS:
        d[col + "_quartile"] = d.groupby("date")[col].transform(
            lambda x: pd.qcut(x.rank(method="average"), 4, labels=False, duplicates="drop") + 1
            if x.notna().sum() >= 4 else pd.Series(float("nan"), index=x.index))
    rows = []
    for factor in FIELDS:
        for q, g in d.groupby(factor + "_quartile", dropna=True):
            for h in HORIZONS:
                ret_col = f"ret_{h}d_pct"
                if ret_col not in g.columns:
                    raise ValueError(f"Missing future-return column: {ret_col}")
                v = pd.to_numeric(g[ret_col], errors="coerce").dropna()
                if len(v) < 30:
                    continue
                rows.append({"factor": factor, "quartile": int(q), "horizon": h,
                             "n": len(v), "negative_pct": round(100 * (v < 0).mean(), 2),
                             **{f"p{p}": round(float(v.quantile(p/100)), 2)
                                for p in (10,25,50,75,90)}})
    out = Path(output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["factor","quartile","horizon","n","negative_pct","p10","p25","p50","p75","p90"]).to_csv(
        out, index=False, encoding="utf-8-sig")
    print(f"V1.1 descriptive groups: {len(rows)}; selloff observations: {len(d)}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--backtest", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    compare(a.backtest, a.output)
