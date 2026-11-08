"""V2.4 empirical signal validation against unconditional and downside-matched controls.

Exploratory diagnostics, NOT investment advice or a verified trading strategy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20, 60)
THRESHOLDS = (70, 80, 90)
PERCENTILES = (10, 25, 50, 75, 90)


def choose_events(df, threshold, cooldown=60):
    signal = df["panic_score"].ge(threshold) & df["panic_score"].notna()
    starts = np.flatnonzero((signal & ~signal.shift(1, fill_value=False)).to_numpy())
    chosen = []
    for i in starts:
        if not chosen or i - chosen[-1] > cooldown:
            chosen.append(i)
    return np.asarray(chosen, dtype=int)


def metrics(frame, horizon):
    r = frame[f"future_{horizon}d"].dropna().to_numpy(dtype=float)
    excess = frame.loc[frame[f"future_{horizon}d"].notna(), f"excess_{horizon}d"].to_numpy(dtype=float)
    good = np.isfinite(r) & np.isfinite(excess)
    r, excess = r[good], excess[good]
    if not len(r):
        return {"n": 0}
    return {"n": int(len(r)), "up_ratio": round(float(np.mean(r > 0)), 4),
            "beat_ratio": round(float(np.mean(excess > 0)), 4),
            "return_percentiles": {str(p): round(float(np.percentile(r, p)), 3) for p in PERCENTILES},
            "excess_percentiles": {str(p): round(float(np.percentile(excess, p)), 3) for p in PERCENTILES}}


def evaluate(df):
    results = {}
    for threshold in THRESHOLDS:
        idx = choose_events(df, threshold)
        events = df.iloc[idx]
        result = {"event_count": len(idx), "dates": df.index[idx].strftime("%Y-%m-%d").tolist(), "horizons": {}}
        for h in HORIZONS:
            # Control pool: same-stock historical observations with fully observed future,
            # exclude +/-60 trading days around every event to reduce event contamination.
            valid = df[f"future_{h}d"].notna() & df[f"excess_{h}d"].notna() & df["panic_score"].notna()
            mask = valid.to_numpy()
            for i in idx:
                mask[max(0, i-60):min(len(df), i+61)] = False
            pool = df.iloc[np.flatnonzero(mask)]
            event_rows = events.loc[events[f"future_{h}d"].notna() & events[f"excess_{h}d"].notna()]
            # Downside matched: control day with negative 5-day price return;
            # never use future outcomes in matching.
            down_pool = pool[pool["downside"] > 0]
            event_stats = metrics(event_rows, h)
            base_stats = metrics(pool, h)
            down_stats = metrics(down_pool, h)
            result["horizons"][str(h)] = {
                "events": event_stats, "non_event_controls": base_stats,
                "downside_controls": down_stats,
                "excess_median_lift_vs_downside": round(
                    event_stats["excess_percentiles"]["50"]-down_stats["excess_percentiles"]["50"], 3
                ) if event_stats["n"] and down_stats["n"] else None}
        results[str(threshold)] = result
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = {"version": "panic_v2_4_controls", "method": "Event first crossing; 60-day event cooldown; same-stock controls outside +/-60 trading days of events; downside controls require negative trailing 5-day return", "stocks": {}, "errors": {},
              "limitations": ["Exploratory descriptive comparison, not statistical significance or causal proof",
                              "Control sample may be sparse when event windows cover most dates",
                              "No point-in-time financial quality or valuation safety margin yet",
                              "Adjusted historical prices can be revised",
                              "No execution constraints, transaction costs or survivorship adjustment"]}
    for path in sorted(args.input_dir.glob("*_panic.csv")):
        code = path.name.split("_")[0]
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["日期"]).set_index("日期").sort_index()
            required = {"panic_score", "downside"} | {f"{x}_{h}d" for h in HORIZONS for x in ("future", "excess")}
            if not required.issubset(df.columns):
                raise ValueError(f"Missing {required-set(df.columns)}")
            output["stocks"][code] = evaluate(df)
        except Exception as exc:
            output["errors"][code] = f"{type(exc).__name__}: {exc}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stocks": list(output["stocks"]), "errors": output["errors"]}, ensure_ascii=False))
    if len(output["stocks"]) != 3 or output["errors"]:
        raise RuntimeError("V2.4 validation incomplete")


if __name__ == "__main__":
    main()
