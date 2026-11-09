"""Build point-in-time daily close panel from archived low52 snapshots.
Usage: python v2/build_prices_from_snapshots.py --snapshots v2/history --output v2/reports/archive_prices.csv
NOTE: only observed dates are present. Do NOT use this panel for 1/3/5/10/20
trading-day forward returns unless session coverage is independently verified.
"""
import argparse
from pathlib import Path
import pandas as pd

def build(folder, output):
    frames = []
    for f in sorted(Path(folder).glob("low52_*.csv")):
        d = pd.read_csv(f, dtype={"code": str})
        if not {"code","date","close"}.issubset(d):
            raise ValueError(f"{f}: missing code/date/close")
        frames.append(d[["code","date","close"]])
    if not frames:
        raise ValueError("No archived low52 CSV snapshots")
    prices = pd.concat(frames, ignore_index=True)
    prices["date"] = pd.to_datetime(prices.date, errors="raise")
    prices["close"] = pd.to_numeric(prices.close, errors="coerce")
    prices = prices.dropna(subset=["close"])
    if prices.duplicated(["code","date"]).any():
        raise ValueError("Duplicate code/date; inspect snapshots")
    prices = prices.sort_values(["code","date"])
    # Diagnostics: date coverage alone is not sufficient to certify market-session completeness.
    sessions = prices.date.nunique()
    coverage = prices.groupby("code").date.nunique()
    target = Path(output)
    target.parent.mkdir(parents=True,exist_ok=True)
    prices.to_csv(target,index=False,encoding="utf-8-sig")
    print(f"snapshot dates={sessions}, stocks={coverage.size}, min dates/stock={coverage.min()}, max={coverage.max()}")
    print("WARNING: archive-only closes are not verified continuous trading sessions. "
          "Do not interpret row offsets as trading-day horizons without an exchange calendar.")

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--snapshots",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    build(a.snapshots,a.output)
