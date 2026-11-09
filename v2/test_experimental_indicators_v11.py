"""Smoke tests for experimental indicators; run: python -m unittest v2/test_experimental_indicators_v11.py"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from experimental_indicators_v11 import experimental_indicators

class IndicatorTests(unittest.TestCase):
    def test_flat_price_has_zero_cmf_and_obv(self):
        d = pd.DataFrame([{"date": pd.Timestamp("2026-01-01")+pd.Timedelta(days=i),
                           "high": 11, "low": 9, "close": 10, "volume": 100} for i in range(25)])
        result = experimental_indicators(d)
        self.assertAlmostEqual(result["natr_20"], 20.0)
        self.assertAlmostEqual(result["cmf_20"], 0.0)
        self.assertAlmostEqual(result["obv_5d_change"], 0.0)

    def test_short_history_returns_missing(self):
        d = pd.DataFrame([{"date": pd.Timestamp("2026-01-01"),
                           "high": 11, "low": 9, "close": 10, "volume": 100}])
        self.assertTrue(all(v is None for v in experimental_indicators(d).values()))

    def test_close_at_high_gives_positive_cmf(self):
        d = pd.DataFrame([{"date": pd.Timestamp("2026-01-01")+pd.Timedelta(days=i),
                           "high": 10+i*.1, "low": 9+i*.1,
                           "close": 10+i*.1, "volume": 100} for i in range(25)])
        result = experimental_indicators(d)
        self.assertAlmostEqual(result["cmf_20"], 1.0)
        self.assertGreater(result["obv_5d_change"], 0)

if __name__ == "__main__":
    unittest.main()
