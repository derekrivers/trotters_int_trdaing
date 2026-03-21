from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import load_config
from trotters_trader.experiments import (
    apply_research_variant,
    build_research_batch_jobs,
    run_construction_sweep,
    run_benchmark_comparison,
    run_evaluation_profile_comparison,
    run_momentum_profile_comparison,
    run_momentum_refinement_sweep,
    run_promotion_check,
    run_ranking_sweep,
    run_regime_sweep,
    run_sector_sweep,
    run_operability_program,
    run_starter_tranche,
    run_momentum_sweep,
    run_risk_sweep,
    run_sma_grid,
    run_universe_slice_sweep,
    run_validation_split,
    run_walkforward_validation,
    summarize_promotion_readiness,
)
from tests.support import IsolatedWorkspaceTestCase


class ExperimentTests(IsolatedWorkspaceTestCase):
    def _sample_momentum_config(self):
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        momentum_template = load_config(Path("configs/eodhd_momentum.toml"))
        return replace(
            base_config,
            run=replace(base_config.run, name=momentum_template.run.name),
            strategy=momentum_template.strategy,
            portfolio=momentum_template.portfolio,
            execution=momentum_template.execution,
            benchmark=momentum_template.benchmark,
            evaluation=momentum_template.evaluation,
            research=momentum_template.research,
            walkforward=momentum_template.walkforward,
            promotion=momentum_template.promotion,
        )

    def test_experiment_grid_runs_multiple_backtests(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_sma_grid(config)

        self.assertEqual(len(results), 3)
        self.assertTrue(all("ending_nav" in result.summary for result in results))

    def test_profile_comparison_runs_for_each_profile_and_strategy(self) -> None:
        base_config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(base_config.data)
        configs = [
            self.isolated_config(load_config(Path("configs/backtest.toml"), evaluation_profile="lenient")),
            self.isolated_config(load_config(Path("configs/backtest.toml"), evaluation_profile="research")),
            self.isolated_config(load_config(Path("configs/backtest.toml"), evaluation_profile="strict")),
        ]

        results = run_evaluation_profile_comparison(configs)

        self.assertEqual(len(results), 9)
        self.assertTrue(any("profile-lenient" in result.results_path for result in results))

    def test_benchmark_comparison_runs_for_each_benchmark_and_strategy(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)

        results = run_benchmark_comparison(config)

        self.assertEqual(len(results), 6)
        self.assertTrue(any("bench-equal_weight" in result.results_path for result in results))
        self.assertTrue(any("bench-price_weighted" in result.results_path for result in results))

    def test_momentum_sweep_runs_expected_grid(self) -> None:
        config = self._sample_momentum_config()
        materialize_canonical_data(config.data)
        results = run_momentum_sweep(config)

        self.assertEqual(len(results), 27)
        self.assertTrue(any("_mom_n-4_ms-005_rf-63" in result.results_path for result in results))

    def test_momentum_profile_comparison_runs_named_profiles(self) -> None:
        config = self._sample_momentum_config()
        materialize_canonical_data(config.data)
        results = run_momentum_profile_comparison(config)

        self.assertEqual(len(results), 3)
        self.assertTrue(any("_momprof_aggressive" in result.results_path for result in results))
        self.assertTrue(any("_momprof_balanced" in result.results_path for result in results))
        self.assertTrue(any("_momprof_defensive" in result.results_path for result in results))

    def test_momentum_refinement_sweep_runs_expected_grid(self) -> None:
        config = self._sample_momentum_config()
        materialize_canonical_data(config.data)
        results = run_momentum_refinement_sweep(config)

        self.assertEqual(len(results), 12)
        self.assertTrue(any("_momref_n-3_ms-003_rf-63" in result.results_path for result in results))

    def test_validation_split_runs_train_validation_and_holdout_periods(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        results = run_validation_split(config)

        self.assertEqual(len(results), 3)
        self.assertTrue(any("_split-train" in result.results_path for result in results))
        self.assertTrue(any(result.analytics.get("period", {}).get("label") == "validation" for result in results))
        self.assertTrue(any(result.analytics.get("period", {}).get("label") == "holdout" for result in results))

    def test_risk_sweep_runs_expected_scenarios_across_periods(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        results = run_risk_sweep(config)

        self.assertEqual(len(results), 18)
        self.assertTrue(any("_risk_baseline_split-train" in result.results_path for result in results))
        self.assertTrue(any("_risk_gross70_deploy20_n8_w10_split-holdout" in result.results_path for result in results))

    def test_regime_sweep_runs_expected_scenarios_across_periods(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        results = run_regime_sweep(config)

        self.assertEqual(len(results), 15)
        self.assertTrue(any("_regime_off_split-train" in result.results_path for result in results))
        self.assertTrue(any("_regime_bw252_re45_force_split-holdout" in result.results_path for result in results))

    def test_sector_sweep_runs_expected_scenarios_across_periods(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        results = run_sector_sweep(config)

        self.assertEqual(len(results), 12)
        self.assertTrue(any("_sector_off_split-train" in result.results_path for result in results))
        self.assertTrue(any("_sector_sec1_split-holdout" in result.results_path for result in results))

    def test_walkforward_validation_runs_windows(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        results = run_walkforward_validation(config)

        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(any("_wf_" in result.results_path for result in results))
        self.assertTrue(all("walkforward_window" in result.analytics for result in results))
        self.assertTrue(all(result.analytics.get("period", {}).get("start_date", "").startswith("2023") or result.analytics.get("period", {}).get("start_date", "").startswith("2024") for result in results))

    def test_promotion_readiness_combines_split_and_walkforward_evidence(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)
        validation_results = run_validation_split(config)
        walkforward_results = run_walkforward_validation(config)

        decision = summarize_promotion_readiness(config, validation_results, walkforward_results)

        self.assertIn("eligible", decision)
        self.assertIn("recommended_action", decision)
        self.assertIn("walkforward_summary", decision)
        self.assertIn("split_summary", decision)
        self.assertIn("validation", decision["split_summary"])
        self.assertIn("holdout", decision["split_summary"])

    def test_promotion_check_runs_split_and_walkforward(self) -> None:
        config = self._sample_momentum_config()
        config = replace(config, validation=load_config(Path("configs/eodhd_momentum.toml")).validation)
        materialize_canonical_data(config.data)

        promotion = run_promotion_check(config)

        self.assertEqual(len(promotion["validation_results"]), 3)
        self.assertGreaterEqual(len(promotion["walkforward_results"]), 1)
        self.assertIn("promotion_decision", promotion)

    def test_universe_slice_sweep_writes_tranche_artifacts(self) -> None:
        config = self._sample_momentum_config()
        config = replace(
            config,
            data=replace(config.data, source_instruments_csv=Path("data/universes/uk_starter_instrument_master.csv")),
            validation=load_config(Path("configs/eodhd_momentum.toml")).validation,
        )
        materialize_canonical_data(config.data)

        tranche = run_universe_slice_sweep(config)

        self.assertIn("control", tranche)
        self.assertIn("candidates", tranche)
        self.assertIn("decision", tranche)
        self.assertTrue(Path(tranche["artifacts"]["summary_md"]).exists())
        self.assertTrue(Path(tranche["artifacts"]["decision_json"]).exists())

    def test_ranking_and_construction_sweeps_return_tranche_results(self) -> None:
        config = self._sample_momentum_config()
        config = replace(
            config,
            data=replace(config.data, source_instruments_csv=Path("data/universes/uk_starter_instrument_master.csv")),
            validation=load_config(Path("configs/eodhd_momentum.toml")).validation,
        )
        materialize_canonical_data(config.data)

        ranking = run_ranking_sweep(config)
        construction = run_construction_sweep(config)

        self.assertIn("top_candidate", ranking)
        self.assertIn("top_candidate", construction)
        self.assertTrue(Path(ranking["artifacts"]["rankings_csv"]).exists())
        self.assertTrue(Path(construction["artifacts"]["rankings_csv"]).exists())

    def test_starter_tranche_registers_catalog_entries(self) -> None:
        config = self._sample_momentum_config()
        config = replace(
            config,
            data=replace(config.data, source_instruments_csv=Path("data/universes/uk_starter_instrument_master.csv")),
            validation=load_config(Path("configs/eodhd_momentum.toml")).validation,
        )
        materialize_canonical_data(config.data)

        tranche = run_starter_tranche(config)

        self.assertIn("final_decision", tranche)
        self.assertTrue(Path(tranche["starter_tranche_report"]["summary_md"]).exists())
        catalog_path = config.run.output_dir / "research_catalog" / "experiment_catalog.json"
        self.assertTrue(catalog_path.exists())
        self.assertIn("recommended_action", tranche["final_decision"])

    def test_build_research_batch_jobs_returns_ranking_tournament(self) -> None:
        config = self._sample_momentum_config()

        jobs = build_research_batch_jobs(config, "configs/eodhd_momentum.toml", "ranking")

        self.assertEqual(len(jobs), 7)
        self.assertEqual(jobs[0]["command"], "promotion-check")
        self.assertEqual(jobs[0]["research_variant"]["kind"], "control")
        self.assertEqual(jobs[1]["research_variant"]["scenario_name"], "global_raw")
        self.assertEqual(jobs[-1]["research_variant"]["scenario_name"], "benchmark_bucket_relative_vol_adjusted")

    def test_apply_research_variant_builds_candidate_config(self) -> None:
        config = self._sample_momentum_config()

        candidate = apply_research_variant(
            config,
            {
                "kind": "candidate",
                "tranche_name": "ranking",
                "scenario_name": "sector_relative_vol_adjusted",
                "scenario_label": "ranking",
                "overrides": {
                    "ranking_mode": "sector_relative",
                    "score_transform": "vol_adjusted",
                },
            },
        )
        control = apply_research_variant(
            config,
            {
                "kind": "control",
                "tranche_name": "ranking",
                "scenario_name": "control",
                "scenario_label": "ranking",
            },
        )

        self.assertEqual(candidate.run.name, f"{config.run.name}_ranking_sector_relative_vol_adjusted")
        self.assertEqual(candidate.strategy.ranking_mode, "sector_relative")
        self.assertEqual(candidate.strategy.score_transform, "vol_adjusted")
        self.assertTrue(candidate.research.promotion_candidate)
        self.assertEqual(candidate.research.control_profile, config.research.profile_name)
        self.assertEqual(control.run.name, f"{config.run.name}_ranking_control")
        self.assertEqual(control.research.profile_name, config.research.profile_name)

    def test_build_research_batch_jobs_returns_risk_tournament_without_duplicate_control(self) -> None:
        config = self._sample_momentum_config()

        jobs = build_research_batch_jobs(config, "configs/eodhd_momentum.toml", "risk")

        self.assertEqual(len(jobs), 6)
        self.assertEqual(jobs[0]["research_variant"]["kind"], "control")
        self.assertEqual(jobs[1]["research_variant"]["scenario_name"], "gross70_deploy12_n6_w09")
        self.assertEqual(jobs[-1]["research_variant"]["scenario_name"], "gross65_deploy20_n8_w09_cb12")

    def test_apply_research_variant_applies_risk_portfolio_overrides(self) -> None:
        config = self._sample_momentum_config()

        candidate = apply_research_variant(
            config,
            {
                "kind": "candidate",
                "tranche_name": "risk",
                "scenario_name": "gross65_deploy20_n8_w09_cb12",
                "scenario_label": "risk",
                "overrides": {
                    "top_n": 8,
                    "cash_buffer_pct": 0.12,
                    "target_gross_exposure": 0.65,
                    "max_position_weight": 0.09,
                    "initial_deployment_turnover_pct": 0.20,
                },
            },
        )

        self.assertEqual(candidate.run.name, f"{config.run.name}_risk_gross65_deploy20_n8_w09_cb12")
        self.assertEqual(candidate.strategy.top_n, 8)
        self.assertEqual(candidate.portfolio.cash_buffer_pct, 0.12)
        self.assertEqual(candidate.portfolio.target_gross_exposure, 0.65)
        self.assertEqual(candidate.portfolio.max_position_weight, 0.09)
        self.assertEqual(candidate.portfolio.initial_deployment_turnover_pct, 0.20)

    def test_build_research_batch_jobs_returns_operability_batch(self) -> None:
        config = self._sample_momentum_config()

        jobs = build_research_batch_jobs(config, "configs/eodhd_momentum.toml", "operability")

        self.assertEqual(jobs[0]["research_variant"]["kind"], "control")
        self.assertEqual(jobs[0]["research_variant"]["tranche_name"], "operability")
        self.assertGreater(len(jobs), 700)
        self.assertEqual(jobs[1]["research_variant"]["scenario_label"], "operability")
        self.assertIn("max_rebalance_turnover_pct", jobs[1]["research_variant"]["overrides"])

    def test_apply_research_variant_applies_operability_and_execution_overrides(self) -> None:
        config = self._sample_momentum_config()

        candidate = apply_research_variant(
            config,
            {
                "kind": "candidate",
                "tranche_name": "operability",
                "scenario_name": "rf63_n8_g60_t08_sec3_buf2",
                "scenario_label": "operability",
                "overrides": {
                    "top_n": 8,
                    "target_gross_exposure": 0.60,
                    "rebalance_frequency_days": 63,
                    "max_rebalance_turnover_pct": 0.08,
                    "max_positions_per_sector": 3,
                    "max_positions_per_benchmark_bucket": 2,
                    "selection_buffer_slots": 2,
                    "commission_bps": 12.0,
                    "slippage_bps": 7.0,
                    "spread_bps": 10.0,
                    "stamp_duty_bps": 55.0,
                    "max_participation_rate": 0.02,
                },
            },
        )

        self.assertEqual(candidate.portfolio.max_rebalance_turnover_pct, 0.08)
        self.assertEqual(candidate.portfolio.max_positions_per_benchmark_bucket, 2)
        self.assertEqual(candidate.execution.commission_bps, 12.0)
        self.assertEqual(candidate.execution.slippage_bps, 7.0)
        self.assertEqual(candidate.execution.spread_bps, 10.0)
        self.assertEqual(candidate.execution.stamp_duty_bps, 55.0)
        self.assertEqual(candidate.execution.max_participation_rate, 0.02)

    def test_operability_program_pivots_and_freezes_stress_validated_candidate(self) -> None:
        config = self._sample_momentum_config()
        control_row = {
            "run_name": "control_run",
            "profile_name": "control_profile",
            "strategy_family": "cross_sectional_momentum",
            "validation_excess_return": 0.01,
            "holdout_excess_return": -0.02,
            "walkforward_pass_windows": 0,
        }
        focused_candidate = {
            "run_name": "focused_run",
            "profile_name": "focused_profile",
            "eligible": False,
            "validation_status": "pass",
            "holdout_status": "warn",
            "validation_excess_return": 0.02,
            "holdout_excess_return": 0.01,
            "walkforward_pass_windows": 0,
            "decision_score": (False, True, True, 0.01, 0.02, 0, -0.2, -0.3, 63, -0.08, -2),
        }
        pivot_candidate = {
            "run_name": "pivot_run",
            "profile_name": "pivot_profile",
            "eligible": True,
            "promotion_decision": {"eligible": True},
            "validation_status": "pass",
            "holdout_status": "pass",
            "validation_excess_return": 0.03,
            "holdout_excess_return": 0.02,
            "walkforward_pass_windows": 2,
            "decision_score": (True, True, True, 0.02, 0.03, 2, -0.1, -0.2, 84, -0.08, -2),
        }
        focused_result = {
            "control": control_row,
            "candidates": [focused_candidate],
            "top_candidate": focused_candidate,
            "decision": {
                "selected_run_name": "focused_run",
                "focused_success": False,
                "reason": "no_candidate_restored_walkforward_without_giving_back_holdout",
            },
            "artifacts": {},
        }
        pivot_result = {
            "control": control_row,
            "candidates": [pivot_candidate],
            "top_candidate": pivot_candidate,
            "decision": {
                "selected_run_name": "pivot_run",
                "focused_success": True,
                "reason": "candidate_improves_walkforward_and_preserves_holdout_edge",
            },
            "artifacts": {},
        }

        with (
            patch("trotters_trader.experiments._run_operability_tranche", side_effect=[focused_result, pivot_result]),
            patch("trotters_trader.experiments._candidate_row_config", return_value=config),
            patch("trotters_trader.experiments._operability_shortlist", return_value=[pivot_candidate]),
            patch(
                "trotters_trader.experiments._evaluate_stress_pack",
                return_value={
                    "candidate_run_name": "pivot_run",
                    "candidate_profile_name": "pivot_profile",
                    "scenario_count": 3,
                    "non_broken_count": 3,
                    "stress_ok": True,
                    "scenarios": [],
                },
            ),
            patch(
                "trotters_trader.experiments.write_operability_program_report",
                return_value={"summary_md": "runs/operability/operability_program.md"},
            ) as write_program_report,
            patch(
                "trotters_trader.experiments.write_promotion_artifacts",
                return_value={"promotion_md": "runs/operability/promotion_summary.md"},
            ) as write_promotion_artifacts,
        ):
            result = run_operability_program(config)

        self.assertEqual(result["final_decision"]["recommended_action"], "freeze_candidate")
        self.assertTrue(result["final_decision"]["pivot_used"])
        self.assertEqual(result["final_decision"]["selected_run_name"], "pivot_run")
        write_program_report.assert_called_once()
        write_promotion_artifacts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
