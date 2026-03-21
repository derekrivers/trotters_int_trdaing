from pathlib import Path
from dataclasses import replace
import unittest

from trotters_trader.backtest import run_backtest
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import load_config
from trotters_trader.experiments import run_promotion_check, run_universe_slice_sweep
from trotters_trader.reports import write_operability_program_report, write_promotion_artifacts
from tests.support import IsolatedWorkspaceTestCase


class ReportTests(IsolatedWorkspaceTestCase):
    def test_backtest_writes_report_files(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        result = run_backtest(config)
        run_dir = Path(result.results_path).parent

        self.assertTrue((run_dir / "summary.md").exists())
        self.assertTrue((run_dir / "performance.csv").exists())
        self.assertTrue((run_dir / "fills.csv").exists())
        self.assertTrue((run_dir / "closed_trades.csv").exists())
        self.assertTrue((run_dir / "benchmark_performance.csv").exists())

    def test_summary_includes_run_metadata_and_evaluation(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        result = run_backtest(config)
        summary_text = Path(result.results_path).parent.joinpath("summary.md").read_text(encoding="utf-8")

        self.assertIn("## Run Metadata", summary_text)
        self.assertIn("## Research Profile", summary_text)
        self.assertIn("## Data Policy", summary_text)
        self.assertIn("## Feature Set", summary_text)
        self.assertIn("## Universe Lifecycle", summary_text)
        self.assertIn("## Period", summary_text)
        self.assertIn("## Evaluation", summary_text)
        self.assertIn("## Risk Diagnostics", summary_text)
        self.assertIn("## Basket Diagnostics", summary_text)
        self.assertIn("Strategy family:", summary_text)
        self.assertIn("Profile version:", summary_text)
        self.assertIn("Adjustment policy:", summary_text)
        self.assertIn("Used precomputed features:", summary_text)
        self.assertIn("Start date:", summary_text)
        self.assertIn("Status:", summary_text)
        self.assertIn("Policy:", summary_text)
        self.assertIn("profile_name=", summary_text)
        self.assertIn("## Additional Benchmarks", summary_text)

    def test_promotion_artifacts_are_written(self) -> None:
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        promotion_template = load_config(Path("configs/eodhd_momentum.toml"))
        config = replace(
            base_config,
            run=replace(base_config.run, name=promotion_template.run.name),
            strategy=promotion_template.strategy,
            portfolio=promotion_template.portfolio,
            execution=promotion_template.execution,
            benchmark=promotion_template.benchmark,
            evaluation=promotion_template.evaluation,
            validation=promotion_template.validation,
            research=promotion_template.research,
            walkforward=promotion_template.walkforward,
            promotion=promotion_template.promotion,
        )
        materialize_canonical_data(config.data)
        promotion = run_promotion_check(config)

        artifacts = write_promotion_artifacts(
            output_dir=config.run.output_dir,
            report_name="promotion_test_report",
            promotion_decision=promotion["promotion_decision"],
            config_path="configs/eodhd_momentum.toml",
        )

        self.assertTrue(Path(artifacts["promotion_json"]).exists())
        self.assertTrue(Path(artifacts["promotion_md"]).exists())
        self.assertTrue(Path(artifacts["history_jsonl"]).exists())
        summary_text = Path(artifacts["promotion_md"]).read_text(encoding="utf-8")
        self.assertIn("## Profile", summary_text)
        self.assertIn("## Walk-Forward", summary_text)
        self.assertIn("## Split Summary", summary_text)
        self.assertIn("## Decision", summary_text)

    def test_tranche_report_is_written(self) -> None:
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        template = load_config(Path("configs/eodhd_momentum.toml"))
        config = replace(
            base_config,
            run=replace(base_config.run, name=template.run.name),
            data=replace(base_config.data, source_instruments_csv=Path("data/universes/uk_starter_instrument_master.csv")),
            strategy=template.strategy,
            portfolio=template.portfolio,
            execution=template.execution,
            benchmark=template.benchmark,
            evaluation=template.evaluation,
            validation=template.validation,
            research=template.research,
            walkforward=template.walkforward,
            promotion=template.promotion,
        )
        materialize_canonical_data(config.data)

        tranche = run_universe_slice_sweep(config)

        summary_text = Path(tranche["artifacts"]["summary_md"]).read_text(encoding="utf-8")
        self.assertIn("## Control", summary_text)
        self.assertIn("## Candidates", summary_text)
        self.assertIn("## Decision", summary_text)

    def test_operability_program_report_is_written(self) -> None:
        artifacts = write_operability_program_report(
            output_dir=self.temp_root / "runs",
            report_name="operability_program_test",
            control_row={
                "run_name": "control_run",
                "profile_name": "control_profile",
                "strategy_family": "cross_sectional_momentum",
                "validation_excess_return": 0.01,
                "holdout_excess_return": -0.02,
                "walkforward_pass_windows": 0,
            },
            focused_result={
                "decision": {
                    "selected_run_name": "focused_run",
                    "candidate_count": 10,
                    "viable_candidate_count": 2,
                    "focused_success": False,
                    "reason": "no_candidate_restored_walkforward_without_giving_back_holdout",
                }
            },
            pivot_result={
                "decision": {
                    "selected_run_name": "pivot_run",
                    "candidate_count": 6,
                    "viable_candidate_count": 1,
                    "focused_success": True,
                    "reason": "candidate_improves_walkforward_and_preserves_holdout_edge",
                }
            },
            shortlisted=[
                {
                    "run_name": "pivot_run",
                    "profile_name": "pivot_profile",
                    "eligible": True,
                    "validation_excess_return": 0.03,
                    "holdout_excess_return": 0.02,
                    "walkforward_pass_windows": 2,
                    "rebalance_frequency_days": 84,
                    "max_rebalance_turnover_pct": 0.08,
                }
            ],
            stress_results=[
                {
                    "candidate_run_name": "pivot_run",
                    "candidate_profile_name": "pivot_profile",
                    "scenario_count": 2,
                    "non_broken_count": 2,
                    "stress_ok": True,
                    "scenarios": [
                        {
                            "scenario_name": "cost_step_up",
                            "validation_status": "warn",
                            "holdout_status": "warn",
                            "holdout_excess_return": 0.01,
                            "walkforward_pass_windows": 1,
                            "non_broken": True,
                        }
                    ],
                }
            ],
            final_decision={
                "recommended_action": "freeze_candidate",
                "reason": "candidate_passed_promotion_and_stress_pack",
                "selected_run_name": "pivot_run",
                "selected_profile_name": "pivot_profile",
                "selected_candidate_eligible": True,
                "selected_stress_ok": True,
                "pivot_used": True,
            },
        )

        self.assertTrue(Path(artifacts["summary_md"]).exists())
        self.assertTrue(Path(artifacts["decision_json"]).exists())
        self.assertTrue(Path(artifacts["shortlist_csv"]).exists())
        self.assertTrue(Path(artifacts["stress_csv"]).exists())
        summary_text = Path(artifacts["summary_md"]).read_text(encoding="utf-8")
        self.assertIn("## Control", summary_text)
        self.assertIn("## Focused Tranche", summary_text)
        self.assertIn("## Pivot Tranche", summary_text)
        self.assertIn("## Stress Pack", summary_text)
        self.assertIn("## Final Recommendation", summary_text)


if __name__ == "__main__":
    unittest.main()
