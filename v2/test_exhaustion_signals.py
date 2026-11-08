"""Deterministic smoke tests for exhaustion flags and daily ranking."""
import unittest
import pandas as pd
from exhaustion_signals import exhaustion_features

class ExhaustionTests(unittest.TestCase):
    def sample(self,fall=True):
        dates=pd.bdate_range("2026-09-01",periods=35)
        closes=[100.0]*35
        if fall:
            closes[27]=92
            for i in range(28,35): closes[i]=92.0
        rows=[]
        for i,(day,c) in enumerate(zip(dates,closes)):
            rows.append(dict(date=day,open=c,high=c+2,low=c-2,close=c+1,volume=100 if i<30 else 70))
        return pd.DataFrame(rows)
    def test_detects_prior_shock(self):
        result=exhaustion_features(self.sample(True))
        self.assertTrue(result["flags"]["recent_selloff_or_shock"])
        self.assertTrue(result["exhaustion_watch"])
    def test_requires_prior_shock(self):
        result=exhaustion_features(self.sample(False))
        self.assertFalse(result["exhaustion_watch"])
    def test_missing_column_fails(self):
        with self.assertRaises(ValueError):
            exhaustion_features(self.sample().drop(columns=["high"]))
    def test_short_history_fails(self):
        with self.assertRaises(ValueError):
            exhaustion_features(self.sample().iloc[:10])
if __name__=="__main__":unittest.main()
