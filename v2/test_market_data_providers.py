import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from market_data_providers import fetch_daily

class ProviderTests(unittest.TestCase):
    def make_data(self):
        days=pd.bdate_range("2025-01-01",periods=260)
        return pd.DataFrame({"date":days,"open":[10.]*260,"high":[11.]*260,
                             "low":[9.]*260,"close":[10.]*260,"volume":[1000.]*260})

    @patch("market_data_providers.ak.stock_zh_a_hist")
    @patch("market_data_providers.ak.stock_zh_a_daily")
    def test_sina_preferred(self,sina,eastmoney):
        sina.return_value=self.make_data()
        d,source=fetch_daily("000001","20250101","20260101")
        self.assertEqual(source,"sina")
        self.assertEqual(len(d),253)
        eastmoney.assert_not_called()

    @patch("market_data_providers.ak.stock_zh_a_hist")
    @patch("market_data_providers.ak.stock_zh_a_daily")
    def test_fallback_on_sina_failure(self,sina,eastmoney):
        sina.side_effect=ConnectionError("upstream unavailable")
        d=self.make_data().rename(columns={"date":"日期","open":"开盘","high":"最高",
                  "low":"最低","close":"收盘","volume":"成交量"})
        eastmoney.return_value=d
        result,source=fetch_daily("600000","20250101","20260101")
        self.assertEqual(source,"eastmoney")
        self.assertEqual(len(result),253)

    @patch("market_data_providers.ak.stock_zh_a_hist")
    @patch("market_data_providers.ak.stock_zh_a_daily")
    def test_rejects_bad_ohlc(self,sina,eastmoney):
        bad=self.make_data()
        bad["high"]=8
        sina.return_value=bad
        eastmoney.side_effect=ConnectionError("unavailable")
        with self.assertRaisesRegex(RuntimeError,"inconsistent OHLC"):
            fetch_daily("000001","20250101","20260101")

if __name__=="__main__":
    unittest.main()
