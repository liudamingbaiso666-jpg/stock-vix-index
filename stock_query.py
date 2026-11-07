
import sys
from pathlib import Path
from datetime import datetime, timedelta

import akshare as ak

BASE = Path(__file__).resolve().parent / "stock_data"
BASE.mkdir(parents=True, exist_ok=True)


def download_stock(code):
    end_date = (
        datetime.now() + timedelta(days=1)
    ).strftime("%Y%m%d")

    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date="20211101",
        end_date=end_date,
        adjust="qfq"
    )

    if df.empty:
        raise ValueError(f"股票 {code} 没有获取到数据")

    df.to_csv(
        BASE / f"{code}_history.csv",
        index=False,
        encoding="utf-8-sig"
    )

    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("请输入6位A股股票代码")
        sys.exit(1)

    code = sys.argv[1].strip()
    if not (len(code) == 6 and code.isdigit()):
        raise ValueError("股票代码必须为6位数字")

    data = download_stock(code)

    print(f"股票代码：{code}")
    print(f"最新日期：{data.iloc[-1]['日期']}")
    print(f"最新收盘价：{data.iloc[-1]['收盘']}")
    print("历史行情下载完成")
