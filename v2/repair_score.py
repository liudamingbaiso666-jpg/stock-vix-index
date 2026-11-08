"""Experimental 0-100 buying-support/repair evidence score, not a probability.
Point-in-time OHLCV only; P (selloff severity) and R (support evidence) are independent.
"""
import pandas as pd

def repair_features(frame):
    d=frame.sort_values("date").copy()
    required={"date","open","high","low","close","volume"}
    if not required.issubset(d.columns):
        raise ValueError("Missing repair fields: "+str(required-set(d.columns)))
    if len(d)<26: raise ValueError("Need 26 sessions")
    for c in required-{"date"}:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=list(required-{"date"}))
    if len(d)<26: raise ValueError("Need 26 clean sessions")
    x=d.iloc[-1]
    closes=d.close
    ret5=float(x.close/closes.iloc[-6]-1)
    ret20=float(x.close/closes.iloc[-21]-1)
    # Context gate: meaningful prior drawdown, not simply a rising stock.
    prior_peak=float(d.high.iloc[-26:-1].max())
    drawdown=float(x.close/prior_peak-1) if prior_peak>0 else 0
    selloff_context=(drawdown<=-.08 or ret20<=-.08)
    # Price stabilization: latest 3 lows not materially below previous 5-day low.
    previous_low=float(d.low.iloc[-8:-3].min())
    stable_lows=bool(previous_low>0 and float(d.low.iloc[-3:].min())>=previous_low*.99)
    # Buying support: close above session midpoint for at least 2 of last 3 sessions.
    last3=d.iloc[-3:]
    ranges=(last3.high-last3.low)
    close_positions=((last3.close-last3.low)/ranges.where(ranges>0)).fillna(0)
    strong_closes=bool((close_positions>=.6).sum()>=2)
    # Recent positive close and no new low over latest two sessions.
    improving_close=bool(x.close>closes.iloc[-2] and x.low>=d.low.iloc[-2]*.99)
    # Decline deceleration compares two non-overlapping 5-day returns.
    earlier=float(closes.iloc[-6]/closes.iloc[-11]-1)
    deceleration=bool(ret5>earlier+.02)
    # Volume confirmation is conditional on price improvement; no fake bid inference.
    vol20=float(d.volume.iloc[-21:-1].mean())
    supported_up_day=bool(x.close>x.open and x.close>closes.iloc[-2] and vol20>0 and x.volume>=vol20*1.1)
    flags={"stable_lows":stable_lows,"strong_closes":strong_closes,
           "improving_close":improving_close,"decline_deceleration":deceleration,
           "supported_up_day":supported_up_day}
    weights={"stable_lows":25,"strong_closes":20,"improving_close":20,
             "decline_deceleration":20,"supported_up_day":15}
    raw_score=sum(weights[k] for k,v in flags.items() if v)
    # Outside a selloff context, report evidence but never promote to entry stage.
    score=int(raw_score)
    if not selloff_context:
        stage="非下跌修复情境"
    elif stable_lows and strong_closes and (improving_close or supported_up_day) and score>=65:
        stage="初步承接观察"
    elif score>=40:
        stage="疑似衰竭待确认"
    else:
        stage="抛压未见充分缓解"
    return {"repair_score":score,"repair_stage":stage,"repair_flags":flags,
            "selloff_context":bool(selloff_context),"drawdown_25d_pct":round(drawdown*100,2),
            "warning":"Uncalibrated daily-bar heuristic; not proof of buyer identity, bottom, or buy signal."}
