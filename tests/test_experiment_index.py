from pathlib import Path
import unittest

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import load_config
from trotters_trader.experiments import run_threshold_sweep, write_experiment_comparison
from trotters_trader.reports import _render_experiment_index
from tests.support import IsolatedWorkspaceTestCase


class ExperimentIndexTests(IsolatedWorkspaceTestCase):
    def test_experiment_index_is_written(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_threshold_sweep(config)
        outputs = write_experiment_comparison(
            results=results,
            output_dir=config.run.output_dir,
            report_name="test_threshold_index_report",
        )

        self.assertTrue(Path(outputs["index_md"]).exists())

    def test_experiment_index_includes_quality_gate(self) -> None:
        index_text = _render_experiment_index(
            "test_report",
            [
                {
                    "run_name": "pass_run",
                    "strategy_family": "sma_cross",
                    "sweep_type": "parameter_grid",
                    "parameter_name": "windows",
                    "parameter_value": "3_l5",
                    "evaluation_status": "pass",
                    "zero_trade": False,
                    "excess_return": 0.01,
                }
            ],
            "pass",
        )

        self.assertIn("Quality gate: pass", index_text)

    def test_experiment_index_summarizes_excluded_runs(self) -> None:
        index_text = _render_experiment_index(
            "test_report",
            [
                {
                    "run_name": "pass_run",
                    "strategy_family": "sma_cross",
                    "sweep_type": "parameter_grid",
                    "parameter_name": "windows",
                    "parameter_value": "3_l5",
                    "evaluation_status": "pass",
                    "evaluation_warn_flags": "",
                    "evaluation_fail_flags": "",
                    "zero_trade": False,
                    "excess_return": 0.01,
                }
            ],
            "pass",
            [
                {
                    "run_name": "fail_run",
                    "strategy_family": "mean_reversion",
                    "sweep_type": "threshold",
                    "parameter_name": "threshold",
                    "parameter_value": "010",
                    "evaluation_status": "fail",
                    "evaluation_warn_flags": "",
                    "evaluation_fail_flags": "excessive_drawdown",
                    "zero_trade": False,
                    "excess_return": -0.10,
                }
            ],
        )

        self.assertIn("## Excluded Runs", index_text)
        self.assertIn("Exclusion reason excessive_drawdown: 1", index_text)


if __name__ == "__main__":
    unittest.main()
