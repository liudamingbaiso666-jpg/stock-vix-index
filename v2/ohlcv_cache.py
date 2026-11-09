"""Conservative per-symbol OHLCV cache. Never score a stale cached bar as today's bar."""
from pathlib import Path
import pandas as pd

COLUMNS=("date","open","high","low","close","volume","turnover_pct")
def cache_path(root,code):
    return Path(root)/f"{code}.csv"

def load_cache(root,code):
    path=cache_path(root,code)
    if not path.is_file():
        return None
    try:
        d=pd.read_csv(path,dtype={"code":str})
        if not set(COLUMNS).issubset(d.columns):
            return None
        d["date"]=pd.to_datetime(d["date"],errors="coerce")
        for col in COLUMNS[1:]:
            d[col]=pd.to_numeric(d[col],errors="coerce")
        d=d.dropna(subset=COLUMNS[:6]).sort_values("date").drop_duplicates("date")
        if len(d)<253 or (d[["open","high","low","close"]]<=0).any().any():
            return None
        return d.iloc[-253:].copy()
    except (OSError,ValueError,pd.errors.ParserError):
        return None

def store_cache(root,code,d):
    path=cache_path(root,code)
    path.parent.mkdir(parents=True,exist_ok=True)
    clean=d.sort_values("date").drop_duplicates("date").iloc[-253:].copy()
    clean.to_csv(path,index=False)

def combine_cached_and_new(cached,new):
    """Merge same-provider bars only; caller must ensure adjustment consistency."""
    return pd.concat([cached,new],ignore_index=True).sort_values("date").drop_duplicates("date",keep="last").iloc[-253:].copy()
