import unittest

from trotters_trader.run_metadata import classify_run_name, run_metadata


class ExperimentMetadataTests(unittest.TestCase):
    def test_classifies_threshold_run_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("sample_sma_backtest_thr_mom_002")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "threshold")
        self.assertEqual(parameter, "min_score")
        self.assertEqual(value, "002")

    def test_classifies_strategy_comparison_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("sample_sma_backtest_mean_reversion")
        self.assertEqual(family, "mean_reversion")
        self.assertEqual(sweep, "strategy_compare")
        self.assertEqual(parameter, "strategy")
        self.assertEqual(value, "mean_reversion")

    def test_classifies_profile_comparison_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("sample_sma_backtest_profile-strict_sma_cross")
        self.assertEqual(family, "sma_cross")
        self.assertEqual(sweep, "evaluation_profile")
        self.assertEqual(parameter, "profile")
        self.assertEqual(value, "strict")

    def test_classifies_momentum_sweep_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_mom_n-3_ms-003_rf-63")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "momentum_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "n-3_ms-003_rf-63")

    def test_classifies_momentum_profile_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_momprof_balanced")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "momentum_profile")
        self.assertEqual(parameter, "profile")
        self.assertEqual(value, "balanced")

    def test_classifies_momentum_refinement_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_momref_n-3_ms-003_rf-63")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "momentum_refine")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "n-3_ms-003_rf-63")

    def test_classifies_validation_split_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_split-holdout")
        self.assertEqual(family, "unknown")
        self.assertEqual(sweep, "validation_split")
        self.assertEqual(parameter, "period")
        self.assertEqual(value, "holdout")

    def test_classifies_risk_sweep_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_risk_gross70_deploy20_n8_w10_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "risk_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "gross70_deploy20_n8_w10")

    def test_classifies_regime_sweep_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_regime_bw252_re45_force_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "regime_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "bw252_re45_force")

    def test_classifies_sector_sweep_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_sector_sec2_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "sector_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "sec2")

    def test_classifies_walkforward_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_wf_01_walkforward_01")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "walk_forward")
        self.assertEqual(parameter, "window")
        self.assertEqual(value, "01_walkforward_01")

    def test_classifies_universe_slice_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_slice_core_only_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "universe_slice")
        self.assertEqual(parameter, "slice")
        self.assertEqual(value, "core_only")

    def test_classifies_ranking_and_construction_names(self) -> None:
        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_ranking_sector_relative_raw_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "ranking_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "sector_relative_raw")

        family, sweep, parameter, value = classify_run_name("eodhd_momentum_backtest_construct_n8_g60_r63_h84_b3_split-holdout")
        self.assertEqual(family, "cross_sectional_momentum")
        self.assertEqual(sweep, "construction_sweep")
        self.assertEqual(parameter, "scenario")
        self.assertEqual(value, "n8_g60_r63_h84_b3")

    def test_run_metadata_uses_shared_classification(self) -> None:
        metadata = run_metadata(
            "sample_sma_backtest_profile-lenient_cross_sectional_momentum",
            research_tranche="ranking",
            research_slice_name="core",
            ranking_mode="sector_relative",
            score_transform="vol_adjusted",
            control_profile="momentum_balanced",
            promotion_candidate=True,
        )
        self.assertEqual(metadata["strategy_family"], "cross_sectional_momentum")
        self.assertEqual(metadata["sweep_type"], "evaluation_profile")
        self.assertEqual(metadata["parameter_name"], "profile")
        self.assertEqual(metadata["parameter_value"], "lenient")
        self.assertEqual(metadata["research_tranche"], "ranking")
        self.assertEqual(metadata["research_slice_name"], "core")
        self.assertEqual(metadata["ranking_mode"], "sector_relative")
        self.assertEqual(metadata["score_transform"], "vol_adjusted")
        self.assertEqual(metadata["control_profile"], "momentum_balanced")
        self.assertTrue(metadata["promotion_candidate"])


if __name__ == "__main__":
    unittest.main()
