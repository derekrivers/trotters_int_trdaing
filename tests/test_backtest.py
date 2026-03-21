from dataclasses import replace
from datetime import date
from pathlib import Path
import unittest

from trotters_trader.backtest import run_backtest
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import PeriodConfig, load_config
from tests.support import IsolatedWorkspaceTestCase


class BacktestTests(IsolatedWorkspaceTestCase):
    def test_backtest_runs_and_writes_results(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        result = run_backtest(config)

        self.assertIn("ending_nav", result.summary)
        self.assertIn("benchmark", result.analytics)
        self.assertIn("benchmarks", result.analytics)
        self.assertIn("risk_diagnostics", result.analytics)
        self.assertIn("basket_diagnostics", result.analytics)
        self.assertIn("research", result.analytics)
        self.assertIn("data_policy", result.analytics)
        self.assertIn("features", result.analytics)
        self.assertIn("universe_lifecycle", result.analytics)
        self.assertEqual(result.analytics["primary_benchmark"], "equal_weight")
        self.assertTrue(Path(result.results_path).exists())

    def test_backtest_can_materialize_and_use_precomputed_features(self) -> None:
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        momentum_template = load_config(Path("configs/eodhd_momentum.toml"))
        config = replace(
            base_config,
            strategy=momentum_template.strategy,
            portfolio=momentum_template.portfolio,
            execution=momentum_template.execution,
            benchmark=momentum_template.benchmark,
            evaluation=momentum_template.evaluation,
            research=momentum_template.research,
            features=replace(momentum_template.features, feature_dir=base_config.features.feature_dir),
        )
        materialize_canonical_data(config.data)

        result = run_backtest(config)

        self.assertTrue(result.analytics["features"]["enabled"])
        self.assertTrue(result.analytics["features"]["used_precomputed"])
        self.assertTrue(Path(result.analytics["features"]["feature_artifacts"]["feature_csv"]).exists())

    def test_backtest_respects_period_window_but_keeps_history_for_warmup(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        config = replace(
            config,
            period=PeriodConfig(
                label="holdout",
                start_date=date.fromisoformat("2024-01-10"),
                end_date=date.fromisoformat("2024-01-19"),
            ),
        )
        materialize_canonical_data(config.data)
        result = run_backtest(config)

        performance_path = Path(result.results_path).parent / "performance.csv"
        performance_dates = performance_path.read_text(encoding="utf-8")

        self.assertEqual(result.analytics["period"]["label"], "holdout")
        self.assertEqual(result.analytics["period"]["start_date"], "2024-01-10")
        self.assertEqual(result.analytics["period"]["end_date"], "2024-01-19")
        self.assertNotIn("2024-01-09", performance_dates)
        self.assertIn("2024-01-10", performance_dates)

    def test_backtest_can_reduce_target_exposure_after_drawdown_threshold(self) -> None:
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        base_config = replace(
            base_config,
            portfolio=replace(
                base_config.portfolio,
                target_gross_exposure=1.0,
                max_position_weight=1.0,
                rebalance_threshold_bps=0.0,
            ),
        )
        throttled_config = replace(
            base_config,
            portfolio=replace(
                base_config.portfolio,
                drawdown_reduce_threshold=0.000001,
                drawdown_reduced_gross_exposure=0.25,
            ),
        )
        materialize_canonical_data(base_config.data)

        base_result = run_backtest(base_config)
        throttled_result = run_backtest(throttled_config)

        self.assertLess(
            throttled_result.summary["average_gross_exposure"],
            base_result.summary["average_gross_exposure"],
        )


if __name__ == "__main__":
    unittest.main()
