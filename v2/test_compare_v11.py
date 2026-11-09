"""Regression checks for V1.1 comparison; no external market data required."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from compare_v11 import compare

class ComparisonTests(unittest.TestCase):
    def test_missing_values_and_ties_do_not_create_fake_quartiles(self):
        with tempfile.TemporaryDirectory() as folder:
            rows=[]
            for i in range(320):
                rows.append({"code":f"{i:06d}","date":"2026-11-06",
                             "pressure_score":float(i),"repair_score":float(i),
                             "selloff_context":True,
                             "natr_20":None if i == 0 else float(i % 8),
                             "cmf_20":float(i % 8)/10,
                             **{f"ret_{h}d_pct":float(i % 5 - 2) for h in (1,3,5,10,20)}})
            source=Path(folder)/"backtest.csv"
            target=Path(folder)/"comparison.csv"
            pd.DataFrame(rows).to_csv(source,index=False)
            compare(source,target)
            result=pd.read_csv(target)
            self.assertFalse(result.empty)
            self.assertTrue(result.quartile.between(1,4).all())
            self.assertTrue(set(result.factor)=={"natr_20","cmf_20"})

    def test_missing_context_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"backtest.csv"
            target=Path(folder)/"comparison.csv"
            pd.DataFrame([{"code":"000001","date":"2026-11-06",
                           "pressure_score":50,"repair_score":50,
                           "natr_20":2,"cmf_20":0.1}]).to_csv(source,index=False)
            with self.assertRaisesRegex(ValueError,"selloff_context"):
                compare(source,target)

if __name__ == "__main__":
    unittest.main()
