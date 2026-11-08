import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dividend_screen import evaluate, ratio


class DividendScreenTests(unittest.TestCase):
    def row(self, year, dividend=0.5, eps=1.0, fcf=0.8, price=10.0):
        return {"code": "600900", "fiscal_year": year,
                "cash_dividend_per_share_cny": dividend, "eps_cny": eps,
                "free_cash_flow_per_share_cny": fcf, "price_cny": price,
                "price_date": "2026-11-06", "source": "test", "source_date": "2026-11-06"}

    def test_five_years_and_ratios(self):
        result = evaluate([self.row(y) for y in range(2021, 2026)])
        self.assertTrue(result["five_years_complete"])
        self.assertEqual(result["paid_years_of_five"], 5)
        self.assertEqual(result["trailing_dividend_yield"], 0.05)
        self.assertEqual(result["payout_ratio"], 0.5)
        self.assertEqual(result["fcf_dividend_coverage"], 1.6)

    def test_missing_year_is_not_zero_dividend(self):
        result = evaluate([self.row(y) for y in [2021, 2022, 2024, 2025]])
        self.assertFalse(result["five_years_complete"])
        self.assertIsNone(result["paid_years_of_five"])

    def test_no_price_no_yield(self):
        rows = [self.row(y, price=None) for y in range(2021, 2026)]
        self.assertIsNone(evaluate(rows)["trailing_dividend_yield"])

    def test_no_fcf_no_coverage(self):
        rows = [self.row(y, fcf=None) for y in range(2021, 2026)]
        self.assertIsNone(evaluate(rows)["fcf_dividend_coverage"])

    def test_zero_dividend_no_coverage(self):
        rows = [self.row(y, dividend=0) for y in range(2021, 2026)]
        self.assertIsNone(evaluate(rows)["fcf_dividend_coverage"])
        self.assertEqual(evaluate(rows)["paid_years_of_five"], 0)

    def test_no_divide_by_zero(self):
        self.assertIsNone(ratio(1, 0))


if __name__ == "__main__":
    unittest.main()
