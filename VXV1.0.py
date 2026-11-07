
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent / "stock_data"
OUT = BASE / "vix_results"
OUT.mkdir(parents=True, exist_ok=True)

STOCKS = {
    "601899": "紫金矿业",
    "601991": "大唐发电"
}

WEIGHTS = {
    "volatility": 0.35,
    "downside": 0.30,
    "volume": 0.20,
    "relative": 0.15
}

# 过去252个交易日作为参考窗口
WINDOW = 252
MIN_HISTORY = 120


def load_data(filename):
    df = pd.read_csv(BASE / filename, encoding="utf-8-sig")
    df["日期"] = pd.to_datetime(df["日期"])

    required = ["日期", "收盘", "成交量"]
    if df[required].isna().any().any():
        raise ValueError(f"{filename}存在关键字段缺失")

    if df["日期"].duplicated().any():
        raise ValueError(f"{filename}存在重复日期")

    df = df.sort_values("日期").set_index("日期")

    for col in ["收盘", "成交量"]:
        df[col] = pd.to_numeric(df[col], errors="raise")

    if (df["收盘"] <= 0).any():
        raise ValueError(f"{filename}存在无效价格")

    if (df["成交量"] < 0).any():
        raise ValueError(f"{filename}存在负成交量")

    return df


def rolling_percentile(series):
    """只用当前日期之前的历史值计算百分位。"""
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)

    for i in range(len(values)):
        history = values[max(0, i-WINDOW):i]
        history = history[np.isfinite(history)]

        if len(history) >= MIN_HISTORY and np.isfinite(values[i]):
            less = np.sum(history < values[i])
            equal = np.sum(history == values[i])
            result[i] = 100 * (less + 0.5 * equal) / len(history)

    return pd.Series(result, index=series.index)


market = load_data("000300_history.csv")
market_returns = market["收盘"].pct_change(fill_method=None)


def calculate_vix(code, name):
    stock = load_data(f"{code}_history.csv")

    df = pd.DataFrame(index=stock.index)
    df["close"] = stock["收盘"]
    df["volume"] = stock["成交量"]
    df["ret"] = df["close"].pct_change(fill_method=None)
    df["market_ret"] = market_returns.reindex(df.index)

    if df["market_ret"].isna().iloc[1:].any():
        raise ValueError(f"{name}与沪深300交易日不匹配")

    # 因子1：20日收益率标准差
    df["volatility"] = df["ret"].rolling(20).std()

    # 因子2：5日累计跌幅，越跌越高
    df["downside"] = -df["close"].pct_change(5)

    # 因子3：成交量相对过去20日均量
    past_volume = df["volume"].shift(1).rolling(20).mean()
    df["volume_ratio"] = df["volume"] / past_volume
    df["volume_factor"] = np.log(
        df["volume_ratio"].clip(lower=0.01)
    )

    # 因子4：当日相对沪深300跌幅
    df["relative"] = df["market_ret"] - df["ret"]

    factors = {
        "volatility": "volatility",
        "downside": "downside",
        "volume": "volume_factor",
        "relative": "relative"
    }

    for key, column in factors.items():
        df[f"p_{key}"] = rolling_percentile(df[column])

    # 初步版本：四因子加权
    df["VIX"] = sum(
        df[f"p_{key}"] * weight
        for key, weight in WEIGHTS.items()
    )

    # 未来收益，仅用于回测，不参与VIX计算
    for days in [5, 10, 20]:
        df[f"future_{days}d"] = (
            df["close"].shift(-days) / df["close"] - 1
        ) * 100

    df.to_csv(
        OUT / f"{code}_vix_v1.csv",
        encoding="utf-8-sig",
        index_label="日期"
    )

    valid = df.dropna(subset=["VIX"])
    latest = valid.iloc[-1]

    print(f"\n{'='*45}")
    print(f"{name}（{code}）")
    print(f"最新日期：{valid.index[-1].date()}")
    print(f"最新收盘价：{latest['close']:.2f}")
    print(f"VIX V1.0：{latest['VIX']:.2f}")

    print("\n历史高恐慌事件回测：")
    for threshold in [70, 80, 90]:
        # 同一轮恐慌连续多天只计首次触发
        signal = valid["VIX"] >= threshold
        starts = signal & ~signal.shift(1, fill_value=False)
        events = valid.loc[starts]

        print(f"\nVIX首次达到{threshold}：{len(events)}次")

        for days in [5, 10, 20]:
            returns = events[f"future_{days}d"].dropna()

            if len(returns) == 0:
                print(f"  {days}日：暂无完整样本")
                continue

            print(
                f"  {days}日："
                f"样本{len(returns)}，"
                f"上涨比例{(returns > 0).mean():.1%}，"
                f"中位收益{returns.median():.2f}%"
            )

    return df


results = {}
for code, name in STOCKS.items():
    results[code] = calculate_vix(code, name)

print("\n计算完成！")
print("结果保存位置：", OUT)

