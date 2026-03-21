from datetime import date
import unittest

from trotters_trader.benchmark import (
    build_benchmarks,
    build_equal_weight_benchmark,
    build_price_weighted_benchmark,
    equal_weight_lookback_return,
)
from trotters_trader.config import BenchmarkConfig
from trotters_trader.domain import DailyBar


class BenchmarkTests(unittest.TestCase):
    def test_equal_weight_benchmark_builds_series(self) -> None:
        bars = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 10, 10, 10, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "A", 11, 11, 11, 11, 11, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 20, 20, 20, 20, 20, 1000),
                DailyBar(date(2024, 1, 2), "B", 22, 22, 22, 22, 22, 1000),
            ],
        }

        performance = build_equal_weight_benchmark(bars, 1000.0)

        self.assertEqual(len(performance), 2)
        self.assertGreater(performance[-1].net_asset_value, performance[0].net_asset_value)

    def test_price_weighted_benchmark_builds_series(self) -> None:
        bars = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 10, 10, 10, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "A", 11, 11, 11, 11, 11, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 40, 40, 40, 40, 40, 1000),
                DailyBar(date(2024, 1, 2), "B", 44, 44, 44, 44, 44, 1000),
            ],
        }

        performance = build_price_weighted_benchmark(bars, 1000.0)

        self.assertEqual(len(performance), 2)
        self.assertGreater(performance[-1].net_asset_value, performance[0].net_asset_value)

    def test_build_benchmarks_returns_configured_models(self) -> None:
        bars = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 10, 10, 10, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "A", 11, 11, 11, 11, 11, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 20, 20, 20, 20, 20, 1000),
                DailyBar(date(2024, 1, 2), "B", 21, 21, 21, 21, 21, 1000),
            ],
        }

        benchmarks = build_benchmarks(
            bars,
            1000.0,
            BenchmarkConfig(models=("equal_weight", "price_weighted"), primary="equal_weight"),
        )

        self.assertEqual(sorted(benchmarks.keys()), ["equal_weight", "price_weighted"])

    def test_equal_weight_lookback_return_is_positive_for_rising_basket(self) -> None:
        bars = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 10, 10, 10, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "A", 11, 11, 11, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "A", 12, 12, 12, 12, 12, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 20, 20, 20, 20, 20, 1000),
                DailyBar(date(2024, 1, 2), "B", 21, 21, 21, 21, 21, 1000),
                DailyBar(date(2024, 1, 3), "B", 22, 22, 22, 22, 22, 1000),
            ],
        }

        result = equal_weight_lookback_return(bars, 2)

        self.assertIsNotNone(result)
        self.assertGreater(result, 0.0)

    def test_equal_weight_lookback_return_is_negative_for_falling_basket(self) -> None:
        bars = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 12, 12, 12, 12, 12, 1000),
                DailyBar(date(2024, 1, 2), "A", 11, 11, 11, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "A", 10, 10, 10, 10, 10, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 22, 22, 22, 22, 22, 1000),
                DailyBar(date(2024, 1, 2), "B", 21, 21, 21, 21, 21, 1000),
                DailyBar(date(2024, 1, 3), "B", 20, 20, 20, 20, 20, 1000),
            ],
        }

        result = equal_weight_lookback_return(bars, 2)

        self.assertIsNotNone(result)
        self.assertLess(result, 0.0)


if __name__ == "__main__":
    unittest.main()
