"""V1.1 research-only NATR/CMF/OBV indicators. No changes to P or R scores.
Input: adjusted daily OHLCV sorted by date. All rolling windows are backward-looking.
CMF is a daily-bar money-flow proxy, NOT actual institutional fund flows.
"""
import pandas as pd
import numpy as np

def experimental_indicators(frame, period=20):
    d = frame.sort_values("date").copy()
    for c in ("high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["high", "low", "close", "volume"])
    if len(d) < period + 1:
        return {"natr_20": None, "cmf_20": None, "obv_5d_change": None}
    high, low, close, volume = (d[k] for k in ("high", "low", "close", "volume"))
    prev = close.shift(1)
    true_range = pd.concat([(high-low).abs(), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
    atr = true_range.iloc[-period:].mean()
    natr = 100 * atr / close.iloc[-1] if close.iloc[-1] > 0 else np.nan
    spread = high - low
    multiplier = ((2*close-high-low) / spread.where(spread > 0)).fillna(0)
    recent_vol = volume.iloc[-period:].sum()
    cmf = (multiplier*volume).iloc[-period:].sum() / recent_vol if recent_vol > 0 else np.nan
    signed_volume = np.sign(close.diff()).fillna(0) * volume
    obv_change = signed_volume.iloc[-5:].sum()
    def clean(x):
        return round(float(x), 5) if pd.notna(x) and np.isfinite(x) else None
    return {"natr_20": clean(natr), "cmf_20": clean(cmf),
            "obv_5d_change": clean(obv_change)}
