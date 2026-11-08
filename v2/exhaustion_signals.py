"""Post-selloff exhaustion research flags, not entry orders.
Reads historical OHLCV per symbol and uses only data through signal day.
"""
import pandas as pd

def exhaustion_features(frame):
    d=frame.copy().sort_values("date")
    required={"date","open","high","low","close","volume"}
    if not required.issubset(d): raise ValueError(f"Missing {required-set(d)}")
    if len(d)<25: raise ValueError("Need at least 25 sessions")
    for col in ("open","high","low","close","volume"):
        d[col]=pd.to_numeric(d[col],errors="coerce")
    d=d.dropna(subset=list(required-{"date"}))
    if len(d)<25: raise ValueError("Not enough clean sessions")
    x=d.iloc[-1]
    prior=d.iloc[-6:-1]
    recent=d.iloc[-5:]
    prev_low=float(prior.low.min())
    low_tolerance=0.01
    no_material_new_low=bool(float(x.low)>=prev_low*(1-low_tolerance))
    close_location=float((x.close-x.low)/(x.high-x.low)) if x.high>x.low else None
    strong_close=close_location is not None and close_location>=.65
    vol5=float(recent.volume.mean())
    prevvol=float(d.iloc[-10:-5].volume.mean())
    fading_volume=prevvol>0 and vol5<prevvol*.85
    ret5=float(x.close/d.iloc[-6].close-1)
    recent_selloff=ret5<=-.06
    prior_shock=bool((d.close.pct_change().iloc[-11:-1]<=-.05).any())
    # Signal components intentionally separate from initial panic and quality screening.
    flags={"recent_selloff_or_shock":bool(recent_selloff or prior_shock),
           "no_material_new_low":no_material_new_low,
           "strong_close_location":bool(strong_close),
           "fading_recent_volume":bool(fading_volume)}
    evidence=sum(flags[k] for k in ("no_material_new_low","strong_close_location","fading_recent_volume"))
    return {"date":str(x.date),"flags":flags,"evidence_count":evidence,
            "exhaustion_watch":bool(flags["recent_selloff_or_shock"] and evidence>=2),
            "warning":"Preliminary daily-bar exhaustion watch only; not proof sellers exhausted or a buy signal."}
