"""V2.3 stock panic prototype: causal factors, independent valuation gate.

Panic is an empirical selling-pressure proxy, NOT options-implied VIX and NOT a buy signal.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np
import pandas as pd
import akshare as ak

WEIGHTS = {"downside": .35, "relative": .25, "selling_volume": .25, "downside_vol": .15}
CODES = {"601899": "紫金矿业", "600519": "贵州茅台", "600900": "长江电力"}
HORIZONS = (5, 10, 20, 60)


def pct_history(series, window=252, minimum=120):
    """Rank current value using only preceding observations (no lookahead)."""
    a = series.to_numpy(dtype=float)
    out = np.full(len(a), np.nan)
    for i, x in enumerate(a):
        prior = a[max(0, i-window):i]
        prior = prior[np.isfinite(prior)]
        if np.isfinite(x) and len(prior) >= minimum:
            out[i] = 100 * ((prior < x).sum() + .5 * (prior == x).sum()) / len(prior)
    return pd.Series(out, index=series.index)


def clean(df, name):
    needed = {"日期", "收盘", "成交量"}
    if not needed.issubset(df.columns):
        raise ValueError(f"{name} missing {needed-set(df.columns)}")
    d = df.copy()
    d["日期"] = pd.to_datetime(d["日期"], errors="raise")
    if d["日期"].duplicated().any():
        raise ValueError(f"{name} duplicate dates")
    d = d.sort_values("日期").set_index("日期")
    for c in ("收盘", "成交量"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d[["收盘", "成交量"]].isna().any().any() or (d["收盘"] <= 0).any() or (d["成交量"] < 0).any():
        raise ValueError(f"{name} invalid prices or volumes")
    return d


def score(stock, market):
    aligned = stock.join(market[["收盘"]].rename(columns={"收盘": "market_close"}), how="left")
    if aligned["market_close"].isna().any():
        raise ValueError("Stock and benchmark dates not fully aligned")
    close = aligned["收盘"]
    volume = aligned["成交量"]
    r = close.pct_change(fill_method=None)
    mr = aligned["market_close"].pct_change(fill_method=None)
    downside = (-close.pct_change(5, fill_method=None)).clip(lower=0)
    relative = (mr.rolling(5).apply(lambda a: np.prod(1+a)-1, raw=True) -
                r.rolling(5).apply(lambda a: np.prod(1+a)-1, raw=True)).clip(lower=0)
    past_vol = volume.shift(1).rolling(20).mean().replace(0, np.nan)
    # Rising prices on heavy volume must not be scored as panic.
    selling_volume = np.where(r < 0, np.log1p((volume / past_vol).clip(lower=0)), 0.)
    selling_volume = pd.Series(selling_volume, index=close.index)
    # Only downside volatility; high upward volatility should not create panic.
    downside_vol = r.clip(upper=0).rolling(20).std()
    factors = {"downside": downside, "relative": relative,
               "selling_volume": selling_volume, "downside_vol": downside_vol}
    result = pd.DataFrame({"close": close, "market_close": aligned["market_close"], "ret": r}, index=close.index)
    for key, series in factors.items():
        result[key] = series
        result["p_" + key] = pct_history(series)
    pcols = ["p_" + k for k in WEIGHTS]
    result["panic_score"] = sum(result["p_" + k] * w for k, w in WEIGHTS.items())
    result.loc[result[pcols].isna().any(axis=1), "panic_score"] = np.nan
    for h in HORIZONS:
        result[f"future_{h}d"] = (close.shift(-h) / close - 1) * 100
        result[f"benchmark_{h}d"] = (aligned["market_close"].shift(-h) / aligned["market_close"] - 1) * 100
        result[f"excess_{h}d"] = result[f"future_{h}d"] - result[f"benchmark_{h}d"]
    return result


def backtest(df, thresholds=(70, 80, 90), cooldown=20):
    """First crossing, minimum separation, no overlapping event counting within cooldown."""
    output = {}
    for threshold in thresholds:
        above = df["panic_score"].ge(threshold) & df["panic_score"].notna()
        crossing = above & ~above.shift(1, fill_value=False)
        candidates = np.flatnonzero(crossing.to_numpy())
        selected = []
        last = -10**9
        for i in candidates:
            if i-last > cooldown:
                selected.append(i)
                last = i
        events = df.iloc[selected]
        horizons = {}
        for h in HORIZONS:
            eligible = events.dropna(subset=[f"future_{h}d", f"benchmark_{h}d"])
            returns = eligible[f"future_{h}d"]
            excess = eligible[f"excess_{h}d"]
            horizons[str(h)] = {"n": len(eligible),
                "up_ratio": float((returns > 0).mean()) if len(eligible) else None,
                "beat_benchmark_ratio": float((excess > 0).mean()) if len(eligible) else None,
                "return_percentiles": {str(p): float(np.percentile(returns, p)) for p in (10,25,50,75,90)} if len(eligible) else None,
                "excess_percentiles": {str(p): float(np.percentile(excess, p)) for p in (10,25,50,75,90)} if len(eligible) else None}
        output[str(threshold)] = {"crossings_after_cooldown": len(selected),
                                  "event_dates": [str(x.date()) for x in events.index], "horizons": horizons}
    return output


def fetch(code, start, end):
    raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
    if raw is None or raw.empty:
        raise RuntimeError(f"{code} no price history")
    return clean(raw, code)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="20200101")
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    end = (dt.date.today()+dt.timedelta(days=1)).strftime("%Y%m%d")
    # Benchmark from same trading calendar; prices must be checked for adjustment consistency.
    benchmark = ak.index_zh_a_hist(symbol="000300", period="daily", start_date=args.start, end_date=end)
    market = clean(benchmark, "CSI300")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"model": "panic_v2_3_prototype", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "benchmark": "000300", "codes": {}, "errors": {},
               "limitations": ["Panic score is historical price/volume proxy, not option-implied VIX",
                               "Historical qfq adjusted prices may be revised; no point-in-time guarantee",
                               "Quality classifications are preliminary and not point-in-time validated",
                               "No valuation, intrinsic value or buy decision is inferred",
                               "No transaction costs, suspension, limit-down execution or survivorship correction"]}
    for code, name in CODES.items():
        try:
            s = score(fetch(code, args.start, end), market)
            s.to_csv(args.output_dir / f"{code}_panic.csv", encoding="utf-8-sig", index_label="日期")
            valid = s.dropna(subset=["panic_score"])
            summary["codes"][code] = {"name": name, "observations": len(s),
                "latest_date": str(valid.index[-1].date()) if len(valid) else None,
                "latest_panic": round(float(valid["panic_score"].iloc[-1]), 2) if len(valid) else None,
                "backtest": backtest(s)}
        except Exception as e:
            summary["errors"][code] = f"{type(e).__name__}: {e}"
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scores": {k: v["latest_panic"] for k,v in summary["codes"].items()}, "errors": summary["errors"]}, ensure_ascii=False))
    if summary["errors"] or len(summary["codes"]) != len(CODES):
        raise RuntimeError("Incomplete three-stock panic calibration; diagnostics saved")


if __name__ == "__main__":
    main()
