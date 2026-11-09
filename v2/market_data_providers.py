"""Independent daily OHLCV provider fallback; no silent data mixing."""
import pandas as pd
import akshare as ak

REQUIRED = ("date", "open", "high", "low", "close", "volume")

def _validate(raw, provider, min_sessions=253):
    if raw is None or raw.empty:
        raise ValueError(f"{provider}: empty history")
    if provider == "eastmoney":
        d = raw.rename(columns={"日期":"date","开盘":"open","最高":"high",
             "最低":"low","收盘":"close","成交量":"volume","换手率":"turnover_pct"})
    else:
        d = raw.copy()
        if "turnover_pct" not in d:
            d["turnover_pct"] = float("nan")
    if "turnover_pct" not in d.columns:
        d["turnover_pct"] = float("nan")
    if any(k not in d.columns for k in REQUIRED):
        raise ValueError(f"{provider}: missing OHLCV columns")
    d["date"] = pd.to_datetime(d["date"],errors="coerce")
    for k in (*REQUIRED[1:],"turnover_pct"):
        d[k] = pd.to_numeric(d[k],errors="coerce")
    d = d.dropna(subset=REQUIRED).sort_values("date").drop_duplicates("date")
    if len(d)<min_sessions:
        raise ValueError(f"{provider}: insufficient sessions {len(d)}")
    if (d[["open","high","low","close"]] <= 0).any().any():
        raise ValueError(f"{provider}: nonpositive OHLC prices")
    if (d["high"]<d[["open","close","low"]].max(axis=1)).any() or (d["low"]>d[["open","close","high"]].min(axis=1)).any():
        raise ValueError(f"{provider}: inconsistent OHLC")
    if (d["volume"]<0).any():
        raise ValueError(f"{provider}: negative volume")
    return d.iloc[-253:].copy()

def fetch_daily(code, start_date, end_date, preferred="sina", min_sessions=253, allow_fallback=True):
    """Prefer independent Sina history; use Eastmoney only if needed.
    Both use qfq but adjustments may differ; do not combine bars across providers.
    """
    if preferred not in ("sina","eastmoney"):
        raise ValueError("Unknown provider")
    providers = (preferred, "eastmoney" if preferred=="sina" else "sina") if allow_fallback else (preferred,)
    errors = []
    for provider in providers:
        try:
            if provider=="sina":
                prefix = "sh" if str(code).startswith(("6","9")) else "bj" if str(code).startswith(("4","8")) else "sz"
                if prefix=="bj":
                    raise ValueError("Sina fallback not supported for Beijing tickers")
                raw=ak.stock_zh_a_daily(symbol=prefix+str(code),
                      start_date=start_date,end_date=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y%m%d"),adjust="qfq")
            else:
                raw=ak.stock_zh_a_hist(symbol=str(code),period="daily",
                      start_date=start_date,end_date=end_date,adjust="qfq")
            return _validate(raw,provider,min_sessions=min_sessions),provider
        except Exception as exc:
            errors.append(f"{provider}: {str(exc)[:120]}")
    raise RuntimeError("; ".join(errors))
