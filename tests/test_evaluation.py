from datetime import date
import unittest

from trotters_trader.config import EvaluationConfig
from trotters_trader.domain import Fill, PortfolioSnapshot
from trotters_trader.metrics import build_analytics


class EvaluationTests(unittest.TestCase):
    def test_zero_trade_run_is_flagged(self) -> None:
        performance = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 100000.0, 0.0, 0.0, 100000.0),
        ]
        benchmark = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 100000.0, 1.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 101000.0, 0.0, 1.0, 101000.0),
        ]

        analytics = build_analytics(performance, [], [], {"equal_weight": benchmark}, "equal_weight")

        self.assertEqual(analytics["evaluation"]["status"], "fail")
        self.assertIn("zero_trade_run", analytics["evaluation"]["flags"])
        self.assertIn("zero_trade_run", analytics["evaluation"]["fail_flags"])

    def test_excessive_turnover_is_fail(self) -> None:
        performance = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 98000.0, 0.0, 0.0, 98000.0),
        ]
        fills = [
            Fill(date(2024, 1, 2), "A", 1000, "BUY", 1000, 101.0, 101000.0, 10.0, 5.0, 2.0, 0.0, 0.1),
            Fill(date(2024, 1, 2), "A", 1000, "SELL", 1000, 99.0, 99000.0, 10.0, 5.0, 2.0, 0.0, 0.1),
            Fill(date(2024, 1, 2), "A", 1000, "BUY", 1000, 100.0, 100000.0, 10.0, 5.0, 2.0, 0.0, 0.1),
        ]
        benchmark = performance

        analytics = build_analytics(performance, fills, [], {"equal_weight": benchmark}, "equal_weight")

        self.assertIn("excessive_turnover", analytics["evaluation"]["flags"])
        self.assertIn("excessive_turnover", analytics["evaluation"]["fail_flags"])
        self.assertEqual(analytics["evaluation"]["status"], "fail")

    def test_underperformance_flag_can_be_disabled(self) -> None:
        performance = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 100500.0, 0.0, 0.0, 100500.0),
        ]
        benchmark = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 101000.0, 0.0, 0.0, 101000.0),
        ]

        analytics = build_analytics(
            performance,
            [],
            [],
            {"equal_weight": benchmark},
            "equal_weight",
            EvaluationConfig(
                profile_name="test",
                warn_turnover=2.0,
                fail_turnover=3.0,
                warn_min_trade_count=3,
                fail_min_trade_count=1,
                warn_max_drawdown=0.10,
                fail_max_drawdown=0.20,
                warn_min_excess_return=0.0,
                fail_min_excess_return=-0.05,
                flag_underperform_benchmark=False,
                fail_on_zero_trade_run=True,
            ),
        )

        self.assertNotIn("underperformed_benchmark", analytics["evaluation"]["flags"])

    def test_excessive_drawdown_is_fail(self) -> None:
        performance = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 70000.0, 0.0, 0.0, 70000.0),
        ]

        analytics = build_analytics(
            performance,
            [
                Fill(date(2024, 1, 2), "A", 10, "BUY", 10, 100.0, 1000.0, 1.0, 0.5, 0.5, 0.0, 0.01),
                Fill(date(2024, 1, 2), "A", 10, "SELL", 10, 70.0, 700.0, 1.0, 0.5, 0.5, 0.0, 0.01),
            ],
            [],
            {"equal_weight": performance},
            "equal_weight",
        )

        self.assertEqual(analytics["evaluation"]["status"], "fail")
        self.assertIn("excessive_drawdown", analytics["evaluation"]["fail_flags"])

    def test_fail_on_zero_trade_run_can_be_downgraded_to_warn(self) -> None:
        performance = [
            PortfolioSnapshot(date(2024, 1, 1), 100000.0, 0.0, 0.0, 100000.0),
            PortfolioSnapshot(date(2024, 1, 2), 100000.0, 0.0, 0.0, 100000.0),
        ]

        analytics = build_analytics(
            performance,
            [],
            [],
            {"equal_weight": performance},
            "equal_weight",
            EvaluationConfig(
                profile_name="test",
                warn_turnover=2.0,
                fail_turnover=3.0,
                warn_min_trade_count=3,
                fail_min_trade_count=1,
                warn_max_drawdown=0.10,
                fail_max_drawdown=0.20,
                warn_min_excess_return=0.0,
                fail_min_excess_return=-0.05,
                flag_underperform_benchmark=False,
                fail_on_zero_trade_run=False,
            ),
        )

        self.assertEqual(analytics["evaluation"]["status"], "warn")
        self.assertIn("zero_trade_run", analytics["evaluation"]["warn_flags"])


if __name__ == "__main__":
    unittest.main()
