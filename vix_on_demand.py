"""On-demand A-share stock fear index V1.0 (not CBOE VIX)."""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import akshare as ak
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "results"
WINDOW = 252
MIN_HISTORY = 120
WEIGHTS = {"volatility": 0.35, "downside": 0.30, "volume": 0.20, "relative": 0.15}


def percentile(series):
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)
    for i, value in enumerate(values):
        history = values[max(0, i - WINDOW):i]
        history = history[np.isfinite(history)]
        if np.isfinite(value) and len(history) >= MIN_HISTORY:
            result[i] = 100 * ((history < value).sum() + 0.5 * (history == value).sum()) / len(history)
    return pd.Series(result, index=series.index)


def prepare(df, label):
    if df is None or df.empty:
        raise ValueError(f"{label}: empty data")
    required = {"日期", "收盘", "成交量"}
    if not required.issubset(df.columns):
        raise ValueError(f"{label}: missing columns {required - set(df.columns)}")
    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"])
    df["收盘"] = pd.to_numeric(df["收盘"], errors="raise")
    df["成交量"] = pd.to_numeric(df["成交量"], errors="raise")
    if df["日期"].duplicated().any() or df[["日期", "收盘", "成交量"]].isna().any().any():
        raise ValueError(f"{label}: duplicate dates or missing data")
    if (df["收盘"] <= 0).any() or (df["成交量"] < 0).any():
        raise ValueError(f"{label}: invalid price or volume")
    return df.sort_values("日期").set_index("日期")


def main(code):
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("Stock code must contain six digits")
    end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y%m%d")
    print(f"Downloading stock {code} ...", flush=True)
    stock = prepare(ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20211101", end_date=end, adjust="qfq"), code)
    print("Downloading CSI 300 from Sina ...", flush=True)
    # Independent index feed; avoids the Eastmoney push2 index-lookup endpoint.
    market_raw = ak.stock_zh_index_daily(symbol="sh000300")
    market_raw = market_raw.rename(columns={"date": "日期", "close": "收盘", "volume": "成交量"})
    market = prepare(market_raw, "000300")
    df = pd.DataFrame(index=stock.index)
    df["close"] = stock["收盘"]
    df["volume"] = stock["成交量"]
    df["ret"] = df["close"].pct_change(fill_method=None)
    market_returns = market["收盘"].pct_change(fill_method=None)
    df["market_ret"] = market_returns.reindex(df.index)
    if df["market_ret"].iloc[1:].isna().any():
        raise ValueError("Stock and CSI 300 trading calendars are not aligned")
    df["volatility"] = df["ret"].rolling(20).std()
    df["downside"] = -df["close"].pct_change(5)
    past_volume = df["volume"].shift(1).rolling(20).mean()
    df["volume_factor"] = np.log((df["volume"] / past_volume).clip(lower=0.01))
    df["relative"] = df["market_ret"] - df["ret"]
    for key, factor in {"volatility": "volatility", "downside": "downside", "volume": "volume_factor", "relative": "relative"}.items():
        df[f"p_{key}"] = percentile(df[factor])
    df["VIX"] = sum(df[f"p_{key}"] * weight for key, weight in WEIGHTS.items())
    valid = df.dropna(subset=["VIX"])
    if valid.empty:
        raise ValueError("Insufficient history to calculate VIX")
    last = valid.iloc[-1]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "stock_code": code,
        "model": "Stock Fear Index V1.0",
        "date": valid.index[-1].strftime("%Y-%m-%d"),
        "close": round(float(last["close"]), 4),
        "vix": round(float(last["VIX"]), 2),
        "factors": {k: round(float(last[f"p_{k}"]), 2) for k in WEIGHTS},
        "weights": WEIGHTS,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "AKShare (stock: Eastmoney, CSI 300: Sina)",
        "adjustment": "qfq",
        "status": "ok"
    }
    path = OUTPUT / f"{code}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("code", help="Six-digit A-share stock code")
    main(parser.parse_args().code)
