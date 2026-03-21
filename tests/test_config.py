from pathlib import Path
import unittest

from trotters_trader.config import RuntimeOverrides, apply_period, apply_runtime_overrides, load_config, scope_app_config


class ConfigTests(unittest.TestCase):
    def test_load_config(self) -> None:
        config = load_config(Path("configs/backtest.toml"))
        self.assertEqual(config.data.source_name, "sample_csv")
        self.assertEqual(config.data.staging_dir, Path("data/staging"))
        self.assertEqual(config.data.adjustment_policy, "dividends_from_actions")
        self.assertEqual(config.strategy.name, "sma_cross")
        self.assertEqual(config.strategy.sma_cross.short_window, 3)
        self.assertEqual(config.strategy.sma_cross.signal_threshold, 0.001)
        self.assertEqual(config.strategy.ranking_mode, "global")
        self.assertEqual(config.strategy.score_transform, "raw")
        self.assertEqual(config.strategy.min_candidates_per_group, 1)
        self.assertEqual(config.strategy.cross_sectional_momentum.lookback_window, 5)
        self.assertEqual(config.strategy.cross_sectional_momentum.min_score, 0.0)
        self.assertEqual(config.strategy.mean_reversion.lookback_window, 3)
        self.assertEqual(config.strategy.mean_reversion.min_score, 0.0)
        self.assertEqual(config.execution.fill_model, "next_open")
        self.assertEqual(config.universe.allowed_currency, "GBP")
        self.assertEqual(config.universe.min_history_days, 5)
        self.assertEqual(config.universe.allowed_tradability_statuses, ())
        self.assertEqual(config.portfolio.target_gross_exposure, 0.98)
        self.assertEqual(config.portfolio.max_position_weight, 0.25)
        self.assertEqual(config.portfolio.rebalance_frequency_days, 1)
        self.assertEqual(config.portfolio.max_rebalance_turnover_pct, 1.0)
        self.assertEqual(config.portfolio.initial_deployment_turnover_pct, 1.0)
        self.assertEqual(config.portfolio.selection_buffer_slots, 0)
        self.assertEqual(config.portfolio.max_positions_per_sector, 0)
        self.assertEqual(config.portfolio.max_positions_per_industry, 0)
        self.assertEqual(config.portfolio.max_positions_per_benchmark_bucket, 0)
        self.assertEqual(config.portfolio.min_holding_days, 0)
        self.assertEqual(config.execution.spread_bps, 8.0)
        self.assertEqual(config.benchmark.models, ("equal_weight", "price_weighted"))
        self.assertEqual(config.benchmark.primary, "equal_weight")
        self.assertEqual(config.evaluation.warn_turnover, 2.0)
        self.assertEqual(config.evaluation.fail_turnover, 3.0)
        self.assertEqual(config.evaluation.warn_min_trade_count, 3)
        self.assertEqual(config.evaluation.fail_min_trade_count, 1)
        self.assertEqual(config.evaluation.warn_max_drawdown, 0.10)
        self.assertEqual(config.evaluation.fail_max_drawdown, 0.20)
        self.assertEqual(config.evaluation.warn_min_excess_return, 0.0)
        self.assertEqual(config.evaluation.fail_min_excess_return, -0.05)
        self.assertTrue(config.evaluation.flag_underperform_benchmark)
        self.assertTrue(config.evaluation.fail_on_zero_trade_run)
        self.assertEqual(config.evaluation.profile_name, "default")
        self.assertEqual(config.research.profile_name, "sample_sma")
        self.assertEqual(config.research.research_slice_name, "all")
        self.assertEqual(config.research.control_profile, "")
        self.assertFalse(config.research.promotion_candidate)
        self.assertFalse(config.features.enabled)
        self.assertEqual(config.features.set_name, "sample_sma")
        self.assertFalse(config.walkforward.enabled)
        self.assertEqual(config.promotion.min_windows, 3)

    def test_load_named_evaluation_profile(self) -> None:
        config = load_config(Path("configs/backtest.toml"), evaluation_profile="strict")

        self.assertEqual(config.evaluation.profile_name, "strict")
        self.assertEqual(config.evaluation.warn_turnover, 1.5)
        self.assertEqual(config.evaluation.fail_turnover, 2.5)
        self.assertEqual(config.evaluation.warn_min_trade_count, 5)
        self.assertEqual(config.evaluation.fail_min_trade_count, 2)
        self.assertEqual(config.evaluation.warn_min_excess_return, 0.01)

    def test_unknown_evaluation_profile_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_config(Path("configs/backtest.toml"), evaluation_profile="missing")

    def test_load_bulk_historical_config(self) -> None:
        config = load_config(Path("configs/bulk_historical.toml"))

        self.assertEqual(config.data.source_name, "bulk_csv")
        self.assertEqual(config.data.source_bars_csv, Path("data/bulk/daily_bars.csv"))
        self.assertEqual(config.data.adjustment_policy, "dividends_from_actions")
        self.assertEqual(config.universe.min_history_days, 252)
        self.assertEqual(config.strategy.top_n, 10)
        self.assertEqual(config.portfolio.target_gross_exposure, 0.97)
        self.assertEqual(config.portfolio.rebalance_frequency_days, 5)
        self.assertEqual(config.portfolio.max_rebalance_turnover_pct, 0.20)
        self.assertEqual(config.portfolio.initial_deployment_turnover_pct, 0.20)
        self.assertEqual(config.portfolio.selection_buffer_slots, 3)
        self.assertEqual(config.portfolio.max_positions_per_sector, 0)
        self.assertEqual(config.universe.allowed_tradability_statuses, ())
        self.assertEqual(config.portfolio.min_holding_days, 20)

    def test_load_eodhd_config(self) -> None:
        config = load_config(Path("configs/eodhd.toml"))

        self.assertEqual(config.data.source_name, "eodhd_json")
        self.assertEqual(config.data.source_bars_csv, Path("data/raw/eodhd_json"))
        self.assertEqual(config.data.source_instruments_csv, Path("data/universes/uk_starter_instrument_master.csv"))
        self.assertEqual(config.data.download_instruments_csv, Path("data/universes/uk_starter_watchlist.csv"))
        self.assertEqual(config.data.adjustment_policy, "vendor_adjusted_close")
        self.assertEqual(config.universe.min_history_days, 252)
        self.assertEqual(config.universe.allowed_tradability_statuses, ("TRADABLE",))
        self.assertEqual(config.strategy.top_n, 10)
        self.assertEqual(config.portfolio.target_gross_exposure, 0.97)
        self.assertEqual(config.portfolio.rebalance_frequency_days, 5)
        self.assertEqual(config.portfolio.max_rebalance_turnover_pct, 0.20)
        self.assertEqual(config.portfolio.initial_deployment_turnover_pct, 0.20)
        self.assertEqual(config.portfolio.selection_buffer_slots, 3)
        self.assertEqual(config.portfolio.max_positions_per_sector, 0)
        self.assertEqual(config.portfolio.max_positions_per_industry, 0)
        self.assertEqual(config.portfolio.max_positions_per_benchmark_bucket, 0)
        self.assertEqual(config.portfolio.min_holding_days, 20)

    def test_load_eodhd_momentum_config(self) -> None:
        config = load_config(Path("configs/eodhd_momentum.toml"))

        self.assertEqual(config.strategy.name, "cross_sectional_momentum")
        self.assertEqual(config.strategy.top_n, 8)
        self.assertEqual(config.strategy.weighting, "vol_inverse")
        self.assertEqual(config.strategy.ranking_mode, "global")
        self.assertEqual(config.strategy.score_transform, "raw")
        self.assertEqual(config.strategy.min_candidates_per_group, 1)
        self.assertEqual(config.strategy.cross_sectional_momentum.lookback_window, 126)
        self.assertEqual(config.strategy.cross_sectional_momentum.min_score, 0.03)
        self.assertEqual(config.strategy.cross_sectional_momentum.max_trailing_drawdown, 1.0)
        self.assertEqual(config.strategy.cross_sectional_momentum.drawdown_lookback_window, 0)
        self.assertEqual(config.portfolio.target_gross_exposure, 0.60)
        self.assertEqual(config.portfolio.rebalance_frequency_days, 63)
        self.assertEqual(config.portfolio.max_rebalance_turnover_pct, 0.06)
        self.assertEqual(config.portfolio.initial_deployment_turnover_pct, 0.20)
        self.assertEqual(config.portfolio.volatility_target, 0.0)
        self.assertEqual(config.portfolio.volatility_lookback_days, 20)
        self.assertEqual(config.portfolio.drawdown_reduce_threshold, 0.0)
        self.assertEqual(config.portfolio.drawdown_reduced_gross_exposure, 0.0)
        self.assertFalse(config.portfolio.drawdown_force_rebalance)
        self.assertEqual(config.portfolio.benchmark_regime_window_days, 0)
        self.assertEqual(config.portfolio.benchmark_regime_min_return, 0.0)
        self.assertEqual(config.portfolio.benchmark_regime_reduced_gross_exposure, 0.0)
        self.assertFalse(config.portfolio.benchmark_regime_force_rebalance)
        self.assertEqual(config.portfolio.max_positions_per_sector, 0)
        self.assertEqual(config.portfolio.max_positions_per_industry, 0)
        self.assertEqual(config.portfolio.max_positions_per_benchmark_bucket, 0)
        self.assertEqual(config.portfolio.min_holding_days, 84)
        self.assertEqual(config.research.profile_name, "momentum_balanced")
        self.assertEqual(config.research.profile_version, "2026-03-20.1")
        self.assertEqual(config.research.frozen_on.isoformat(), "2026-03-20")
        self.assertFalse(config.research.promoted)
        self.assertEqual(config.research.research_tranche, "")
        self.assertEqual(config.research.research_slice_name, "all")
        self.assertEqual(config.research.control_profile, "")
        self.assertFalse(config.research.promotion_candidate)
        self.assertTrue(config.features.enabled)
        self.assertTrue(config.features.use_precomputed)
        self.assertEqual(config.features.set_name, "momentum_balanced")
        self.assertTrue(config.walkforward.enabled)
        self.assertEqual(config.walkforward.train_days, 756)
        self.assertEqual(config.walkforward.test_days, 252)
        self.assertEqual(config.promotion.min_pass_windows, 2)
        self.assertEqual(config.promotion.max_oos_turnover, 2.5)
        self.assertTrue(config.promotion.require_frozen_profile)
        self.assertTrue(config.promotion.require_validation_pass)
        self.assertTrue(config.promotion.require_holdout_pass)
        self.assertEqual(config.promotion.min_validation_excess_return, 0.0)
        self.assertEqual(config.promotion.min_holdout_excess_return, 0.0)
        self.assertEqual(len(config.validation), 3)
        self.assertEqual(config.validation[0].label, "train")
        self.assertEqual(config.validation[1].label, "validation")
        self.assertEqual(config.validation[1].start_date.isoformat(), "2023-01-03")
        self.assertEqual(config.validation[1].end_date.isoformat(), "2024-12-31")
        self.assertEqual(config.validation[0].start_date.isoformat(), "2019-01-02")
        self.assertEqual(config.validation[2].label, "holdout")
        self.assertEqual(config.validation[2].start_date.isoformat(), "2025-01-01")
        self.assertEqual(config.validation[2].end_date.isoformat(), "2026-03-19")

    def test_load_eodhd_momentum_profile_configs(self) -> None:
        aggressive = load_config(Path("configs/eodhd_momentum_aggressive.toml"))
        defensive = load_config(Path("configs/eodhd_momentum_defensive.toml"))
        core = load_config(Path("configs/eodhd_momentum_core.toml"))
        broad = load_config(Path("configs/eodhd_momentum_broad.toml"))
        candidate = load_config(Path("configs/eodhd_momentum_candidate.toml"))

        self.assertEqual(aggressive.strategy.name, "cross_sectional_momentum")
        self.assertEqual(aggressive.portfolio.rebalance_frequency_days, 42)
        self.assertEqual(aggressive.portfolio.target_gross_exposure, 0.92)
        self.assertEqual(aggressive.portfolio.max_rebalance_turnover_pct, 0.08)
        self.assertEqual(aggressive.portfolio.initial_deployment_turnover_pct, 0.08)
        self.assertEqual(aggressive.research.profile_name, "momentum_aggressive")
        self.assertEqual(aggressive.data.adjustment_policy, "vendor_adjusted_close")
        self.assertEqual(aggressive.features.set_name, "momentum_aggressive")
        self.assertTrue(aggressive.walkforward.enabled)

        self.assertEqual(defensive.strategy.name, "cross_sectional_momentum")
        self.assertEqual(defensive.strategy.top_n, 2)
        self.assertEqual(defensive.portfolio.target_gross_exposure, 0.88)
        self.assertEqual(defensive.portfolio.rebalance_frequency_days, 84)
        self.assertEqual(defensive.portfolio.min_holding_days, 105)
        self.assertEqual(defensive.portfolio.initial_deployment_turnover_pct, 0.04)
        self.assertEqual(defensive.research.profile_name, "momentum_defensive")
        self.assertEqual(defensive.features.set_name, "momentum_defensive")

        self.assertEqual(core.data.download_instruments_csv, Path("data/universes/uk_core_watchlist.csv"))
        self.assertEqual(core.universe.allowed_universe_buckets, ("core",))
        self.assertEqual(core.research.profile_name, "momentum_core")
        self.assertEqual(core.features.set_name, "momentum_core")
        self.assertEqual(core.validation[1].label, "validation")

        self.assertEqual(broad.data.download_instruments_csv, Path("data/universes/uk_broad_watchlist.csv"))
        self.assertEqual(broad.data.source_instruments_csv, Path("data/universes/uk_broad_instrument_master.csv"))
        self.assertEqual(broad.run.name, "eodhd_momentum_broad_backtest")
        self.assertEqual(broad.research.profile_name, "momentum_broad")
        self.assertFalse(broad.research.promoted)
        self.assertEqual(broad.features.set_name, "momentum_broad")
        self.assertEqual(broad.research.research_slice_name, "all")

        self.assertEqual(candidate.run.name, "eodhd_momentum_candidate_backtest")
        self.assertEqual(candidate.research.profile_name, "momentum_candidate_refine_n4_ms002_rf63")
        self.assertEqual(candidate.research.research_tranche, "refine_seed")
        self.assertEqual(candidate.research.control_profile, "momentum_balanced")
        self.assertTrue(candidate.research.promotion_candidate)

    def test_scope_app_config_isolates_intermediate_paths(self) -> None:
        config = load_config(Path("configs/backtest.toml"))
        scoped = scope_app_config(config, "backtest:run")

        self.assertEqual(scoped.data.staging_dir, Path("data/staging/backtest_run"))
        self.assertEqual(scoped.data.canonical_dir, Path("data/canonical/backtest_run"))
        self.assertEqual(scoped.data.raw_dir, Path("data/raw"))

    def test_apply_period_replaces_active_period(self) -> None:
        config = load_config(Path("configs/eodhd_momentum.toml"))
        holdout = config.validation[2]
        applied = apply_period(config, holdout, run_name="holdout_run")

        self.assertEqual(applied.run.name, "holdout_run")
        self.assertEqual(applied.period.label, "holdout")
        self.assertEqual(applied.period.start_date.isoformat(), "2025-01-01")

    def test_apply_runtime_overrides_retargets_paths_and_features(self) -> None:
        config = load_config(Path("configs/eodhd_momentum.toml"))
        applied = apply_runtime_overrides(
            config,
            RuntimeOverrides(
                output_dir=Path("runtime/job-01"),
                staging_dir=Path("runtime/job-01/staging"),
                canonical_dir=Path("data/shared/canonical"),
                raw_dir=Path("runtime/job-01/raw"),
                feature_set_ref=Path("data/features/shared_set"),
                control_profile="runtime_control",
                disable_feature_materialization=True,
                force_precomputed_features=True,
            ),
        )

        self.assertEqual(applied.run.output_dir, Path("runtime/job-01"))
        self.assertEqual(applied.data.staging_dir, Path("runtime/job-01/staging"))
        self.assertEqual(applied.data.canonical_dir, Path("data/shared/canonical"))
        self.assertEqual(applied.data.raw_dir, Path("runtime/job-01/raw"))
        self.assertEqual(applied.features.feature_dir, Path("data/features"))
        self.assertEqual(applied.features.set_name, "shared_set")
        self.assertTrue(applied.features.use_precomputed)
        self.assertFalse(applied.features.materialize_on_backtest)
        self.assertEqual(applied.research.control_profile, "runtime_control")


if __name__ == "__main__":
    unittest.main()
