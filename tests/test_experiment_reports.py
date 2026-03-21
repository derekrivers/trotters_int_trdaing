from pathlib import Path
import unittest

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import load_config
from trotters_trader.experiments import run_sma_grid, write_experiment_comparison
from trotters_trader.reports import _excluded_rows, _filter_comparison_rows, _render_comparison_markdown, _rank_comparison_rows
from tests.support import IsolatedWorkspaceTestCase


class ExperimentReportTests(IsolatedWorkspaceTestCase):
    def test_experiment_comparison_report_is_written(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_sma_grid(config)
        outputs = write_experiment_comparison(
            results=results,
            output_dir=config.run.output_dir,
            report_name="test_experiment_report",
        )

        self.assertTrue(Path(outputs["summary_md"]).exists())
        self.assertTrue(Path(outputs["rankings_csv"]).exists())

    def test_comparison_ranking_prioritizes_status_before_return(self) -> None:
        rows = [
            {
                "run_name": "warn_best_return",
                "strategy_family": "sma_cross",
                "parameter_name": "windows",
                "parameter_value": "3_l5",
                "total_return": 0.20,
                "excess_return": 0.10,
                "max_drawdown": 0.05,
                "turnover": 1.0,
                "trade_count": 5.0,
                "zero_trade": False,
                "return_per_turnover": 0.20,
                "return_per_drawdown": 4.0,
                "evaluation_status": "warn",
                "evaluation_warn_flags": "high_turnover",
                "evaluation_fail_flags": "",
                "evaluation_warn_count": 1,
                "evaluation_fail_count": 0,
            },
            {
                "run_name": "pass_lower_return",
                "strategy_family": "sma_cross",
                "parameter_name": "windows",
                "parameter_value": "4_l8",
                "total_return": 0.05,
                "excess_return": 0.02,
                "max_drawdown": 0.03,
                "turnover": 0.8,
                "trade_count": 6.0,
                "zero_trade": False,
                "return_per_turnover": 0.0625,
                "return_per_drawdown": 1.6667,
                "evaluation_status": "pass",
                "evaluation_warn_flags": "",
                "evaluation_fail_flags": "",
                "evaluation_warn_count": 0,
                "evaluation_fail_count": 0,
            },
        ]

        ranked = _rank_comparison_rows(rows)

        self.assertEqual(ranked[0]["run_name"], "pass_lower_return")

    def test_comparison_markdown_shows_fail_reasons(self) -> None:
        report = _render_comparison_markdown(
            "test_report",
            _rank_comparison_rows(
                [
                    {
                        "run_name": "failed_run",
                        "strategy_family": "mean_reversion",
                        "parameter_name": "threshold",
                        "parameter_value": "010",
                        "total_return": -0.10,
                        "excess_return": -0.12,
                        "max_drawdown": 0.25,
                        "turnover": 3.5,
                        "trade_count": 2.0,
                        "zero_trade": False,
                        "return_per_turnover": -0.0286,
                        "return_per_drawdown": -0.4,
                        "evaluation_status": "fail",
                        "evaluation_warn_flags": "",
                        "evaluation_fail_flags": "excessive_drawdown,material_benchmark_underperformance",
                        "evaluation_warn_count": 0,
                        "evaluation_fail_count": 2,
                    }
                ]
            ),
        )

        self.assertIn("Fail runs: 1", report)
        self.assertIn("fail_flags=excessive_drawdown,material_benchmark_underperformance", report)
        self.assertIn("profile=default", report)

    def test_quality_gate_filters_fail_runs_from_comparison(self) -> None:
        rows = [
            {
                "run_name": "pass_run",
                "strategy_family": "sma_cross",
                "parameter_name": "windows",
                "parameter_value": "3_l5",
                "total_return": 0.04,
                "excess_return": 0.02,
                "max_drawdown": 0.02,
                "turnover": 0.8,
                "trade_count": 6.0,
                "zero_trade": False,
                "return_per_turnover": 0.05,
                "return_per_drawdown": 2.0,
                "evaluation_status": "pass",
                "evaluation_warn_flags": "",
                "evaluation_fail_flags": "",
                "evaluation_warn_count": 0,
                "evaluation_fail_count": 0,
            },
            {
                "run_name": "fail_run",
                "strategy_family": "mean_reversion",
                "parameter_name": "threshold",
                "parameter_value": "010",
                "total_return": -0.10,
                "excess_return": -0.12,
                "max_drawdown": 0.25,
                "turnover": 3.5,
                "trade_count": 2.0,
                "zero_trade": False,
                "return_per_turnover": -0.0286,
                "return_per_drawdown": -0.4,
                "evaluation_status": "fail",
                "evaluation_warn_flags": "",
                "evaluation_fail_flags": "excessive_drawdown",
                "evaluation_warn_count": 0,
                "evaluation_fail_count": 1,
            },
        ]

        filtered = _filter_comparison_rows(rows, "pass_warn")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["run_name"], "pass_run")

    def test_comparison_markdown_summarizes_excluded_runs(self) -> None:
        rows = [
            {
                "run_name": "pass_run",
                "strategy_family": "sma_cross",
                "parameter_name": "windows",
                "parameter_value": "3_l5",
                "total_return": 0.04,
                "excess_return": 0.02,
                "max_drawdown": 0.02,
                "turnover": 0.8,
                "trade_count": 6.0,
                "zero_trade": False,
                "return_per_turnover": 0.05,
                "return_per_drawdown": 2.0,
                "evaluation_status": "pass",
                "evaluation_warn_flags": "",
                "evaluation_fail_flags": "",
                "evaluation_warn_count": 0,
                "evaluation_fail_count": 0,
            },
            {
                "run_name": "fail_run",
                "strategy_family": "mean_reversion",
                "parameter_name": "threshold",
                "parameter_value": "010",
                "total_return": -0.10,
                "excess_return": -0.12,
                "max_drawdown": 0.25,
                "turnover": 3.5,
                "trade_count": 2.0,
                "zero_trade": False,
                "return_per_turnover": -0.0286,
                "return_per_drawdown": -0.4,
                "evaluation_status": "fail",
                "evaluation_warn_flags": "",
                "evaluation_fail_flags": "excessive_drawdown",
                "evaluation_warn_count": 0,
                "evaluation_fail_count": 1,
            },
        ]
        filtered = _filter_comparison_rows(rows, "pass_warn")
        report = _render_comparison_markdown(
            "test_report",
            _rank_comparison_rows(filtered),
            "pass_warn",
            _excluded_rows(rows, filtered),
        )

        self.assertIn("## Excluded Runs", report)
        self.assertIn("Excluded by quality gate: 1", report)
        self.assertIn("Exclusion reason excessive_drawdown: 1", report)

    def test_comparison_markdown_summarizes_profiles(self) -> None:
        report = _render_comparison_markdown(
            "profile_report",
            _rank_comparison_rows(
                [
                    {
                        "run_name": "lenient_a",
                        "strategy_family": "sma_cross",
                        "evaluation_profile": "lenient",
                        "parameter_name": "profile",
                        "parameter_value": "lenient",
                        "total_return": 0.02,
                        "excess_return": 0.01,
                        "max_drawdown": 0.02,
                        "turnover": 1.0,
                        "trade_count": 5.0,
                        "zero_trade": False,
                        "return_per_turnover": 0.02,
                        "return_per_drawdown": 1.0,
                        "evaluation_status": "pass",
                        "evaluation_warn_flags": "",
                        "evaluation_fail_flags": "",
                        "evaluation_warn_count": 0,
                        "evaluation_fail_count": 0,
                    },
                    {
                        "run_name": "strict_a",
                        "strategy_family": "sma_cross",
                        "evaluation_profile": "strict",
                        "parameter_name": "profile",
                        "parameter_value": "strict",
                        "total_return": -0.01,
                        "excess_return": -0.02,
                        "max_drawdown": 0.03,
                        "turnover": 1.2,
                        "trade_count": 5.0,
                        "zero_trade": False,
                        "return_per_turnover": -0.0083,
                        "return_per_drawdown": -0.3333,
                        "evaluation_status": "warn",
                        "evaluation_warn_flags": "benchmark_underperformance",
                        "evaluation_fail_flags": "",
                        "evaluation_warn_count": 1,
                        "evaluation_fail_count": 0,
                    },
                ]
            ),
        )

        self.assertIn("## Profile Summary", report)
        self.assertIn("- lenient: pass=1.0, warn=0.0, fail=0.0", report)
        self.assertIn("- strict: pass=0.0, warn=1.0, fail=0.0", report)

    def test_comparison_markdown_shows_benchmark_specific_columns(self) -> None:
        report = _render_comparison_markdown(
            "benchmark_report",
            _rank_comparison_rows(
                [
                    {
                        "run_name": "bench_equal_weight",
                        "strategy_family": "sma_cross",
                        "evaluation_profile": "default",
                        "primary_benchmark": "equal_weight",
                        "parameter_name": "benchmark",
                        "parameter_value": "equal_weight",
                        "total_return": 0.02,
                        "excess_return": 0.01,
                        "excess_vs_equal_weight": 0.01,
                        "excess_vs_price_weighted": 0.005,
                        "max_drawdown": 0.02,
                        "turnover": 1.0,
                        "trade_count": 5.0,
                        "zero_trade": False,
                        "return_per_turnover": 0.02,
                        "return_per_drawdown": 1.0,
                        "evaluation_status": "pass",
                        "evaluation_warn_flags": "",
                        "evaluation_fail_flags": "",
                        "evaluation_warn_count": 0,
                        "evaluation_fail_count": 0,
                    }
                ]
            ),
        )

        self.assertIn("benchmark=equal_weight", report)
        self.assertIn("excess_vs_equal_weight=1.0000%", report)
        self.assertIn("excess_vs_price_weighted=0.5000%", report)


if __name__ == "__main__":
    unittest.main()
