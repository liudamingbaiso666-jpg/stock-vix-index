import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ohlcv_cache import store_cache,load_cache,combine_cached_and_new

class CacheTests(unittest.TestCase):
    def data(self):
        return pd.DataFrame({"date":pd.bdate_range("2025-01-01",periods=260),
            "open":10.,"high":11.,"low":9.,"close":10.,
            "volume":1000.,"turnover_pct":1.})
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            store_cache(folder,"000001",self.data())
            got=load_cache(folder,"000001")
            self.assertEqual(len(got),253)
            self.assertEqual(str(got.iloc[-1]["date"].date()),str(self.data().iloc[-1]["date"].date()))
    def test_short_cache_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            store_cache(folder,"000001",self.data().iloc[:10])
            self.assertIsNone(load_cache(folder,"000001"))
    def test_new_bar_replaces_duplicate(self):
        d=self.data().iloc[-253:].copy()
        new=d.tail(1).copy()
        new.loc[:,"close"]=10.5
        got=combine_cached_and_new(d,new)
        self.assertEqual(len(got),253)
        self.assertEqual(float(got.iloc[-1]["close"]),10.5)
if __name__=="__main__":
    unittest.main()
