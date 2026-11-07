from pathlib import Path
from datetime import datetime, timedelta
import akshare as ak
import pandas as pd

BASE = Path(__file__).resolve().parent / "stock_data"
BASE.mkdir(parents=True, exist_ok=True)

STOCKS = {
    "601899": "紫金矿业",
    "601991": "大唐发电",
    "603993": "洛阳钼业"
}

START_DATE = "20211101"
END_DATE = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")

for code, name in STOCKS.items():
    print(f"正在下载：{name}（{code}）")

    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=START_DATE,
        end_date=END_DATE,
        adjust="qfq"
    )

    if df.empty:
        raise RuntimeError(f"{name}历史行情为空")

    df.to_csv(
        BASE / f"{code}_history.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"下载成功：{len(df)}条记录")

print("正在下载沪深300指数")

market = ak.index_zh_a_hist(
    symbol="000300",
    period="daily",
    start_date=START_DATE,
    end_date=END_DATE
)

if market.empty:
    raise RuntimeError("沪深300历史行情为空")

market.to_csv(
    BASE / "000300_history.csv",
    index=False,
    encoding="utf-8-sig"
)

print("全部历史行情下载完成")
