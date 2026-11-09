"""Smoke tests for R-score output contract and context gating."""
import unittest
import pandas as pd
from repair_score import repair_features

class RepairScoreTests(unittest.TestCase):
    def data(self,fall):
        dates=pd.bdate_range("2026-08-03",periods=35)
        rows=[]
        for i,day in enumerate(dates):
            c=(80.0 if i>=20 else 100.0) if fall else 100.0
            rows.append({"date":day,"open":c-.5,"high":c+1,"low":c-1,
                         "close":c,"volume":100})
        return pd.DataFrame(rows)
    def test_output_range(self):
        r=repair_features(self.data(True))
        self.assertGreaterEqual(r["repair_score"],0)
        self.assertLessEqual(r["repair_score"],100)
        self.assertTrue(r["selloff_context"])
    def test_no_selloff_not_promoted(self):
        r=repair_features(self.data(False))
        self.assertEqual(r["repair_stage"],"非下跌修复情境")
    def test_rebound_far_from_low_not_early_support(self):
        d=self.data(True)
        d.loc[d.index[-1],"close"]=110.0
        d.loc[d.index[-1],"high"]=111.0
        d.loc[d.index[-1],"low"]=109.0
        r=repair_features(d)
        self.assertFalse(r["early_window"])
        self.assertNotEqual(r["repair_stage"],"初步承接观察")
    def test_short_data(self):
        with self.assertRaises(ValueError): repair_features(self.data(True).iloc[:10])
    def test_missing_column(self):
        with self.assertRaises(ValueError): repair_features(self.data(True).drop(columns=["low"]))
if __name__=="__main__":unittest.main()
