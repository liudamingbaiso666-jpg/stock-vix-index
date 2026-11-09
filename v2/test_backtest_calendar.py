"""Regression tests: forward returns must respect actual trading sessions."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pandas as pd
from backtest_pr import evaluate

class CalendarSafetyTests(unittest.TestCase):
    def test_missing_calendar_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            snapshots=root/"snapshots"
            snapshots.mkdir()
            pd.DataFrame([{"code":"000001","date":"2026-01-05","repair_score":40,"repair_stage":"观察"}]).to_csv(snapshots/"low52_2026-01-05.csv",index=False)
            pd.DataFrame([{"code":"000001","date":"2026-01-05","pressure_score":50}]).to_csv(snapshots/"pressure_2026-01-05.csv",index=False)
            pd.DataFrame([{"code":"000001","date":"2026-01-05","close":10}]).to_csv(root/"prices.csv",index=False)
            with self.assertRaisesRegex(ValueError,"Trading-session calendar required"):
                evaluate(snapshots,root/"prices.csv",root/"output.csv")

    def test_sparse_prices_do_not_count_as_next_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            snapshots=root/"snapshots"
            snapshots.mkdir()
            pd.DataFrame([{"code":"000001","date":"2026-01-05","repair_score":40,"repair_stage":"观察",
                           "selloff_context":True,"natr_20":2.0,"cmf_20":-0.1}]).to_csv(snapshots/"low52_2026-01-05.csv",index=False)
            pd.DataFrame([{"code":"000001","date":"2026-01-05","pressure_score":50}]).to_csv(snapshots/"pressure_2026-01-05.csv",index=False)
            pd.DataFrame([{"code":"000001","date":"2026-01-05","close":10},
                          {"code":"000001","date":"2026-01-07","close":11}]).to_csv(root/"prices.csv",index=False)
            pd.DataFrame({"date":pd.bdate_range("2026-01-05",periods=30).strftime("%Y-%m-%d")}).to_csv(root/"calendar.csv",index=False)
            evaluate(snapshots,root/"prices.csv",root/"output.csv",root/"calendar.csv")
            output=pd.read_csv(root/"output.csv")
            self.assertTrue(pd.isna(output.loc[0,"ret_1d_pct"]))
            self.assertTrue(pd.isna(output.loc[0,"ret_3d_pct"]))

if __name__=="__main__":
    unittest.main()
