from datetime import date
import unittest

from trotters_trader.config import LookbackStrategyConfig, SmaCrossConfig, StrategyConfig
from trotters_trader.domain import DailyBar, Instrument
from trotters_trader.strategy import (
    CrossSectionalMomentumStrategy,
    MeanReversionStrategy,
    SmaCrossStrategy,
    build_target_weights,
)


class StrategyTests(unittest.TestCase):
    def test_top_n_equal_weight_selection(self) -> None:
        strategy = SmaCrossStrategy(short_window=2, long_window=3, signal_threshold=0.0)
        history = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "A", 1, 1, 1, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "A", 1, 1, 1, 12, 12, 1000),
            ],
            "B": [
                DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "B", 1, 1, 1, 10.5, 10.5, 1000),
                DailyBar(date(2024, 1, 3), "B", 1, 1, 1, 11, 11, 1000),
            ],
            "C": [
                DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "C", 1, 1, 1, 9.5, 9.5, 1000),
                DailyBar(date(2024, 1, 3), "C", 1, 1, 1, 9, 9, 1000),
            ],
        }
        config = StrategyConfig(
            name="sma_cross",
            top_n=1,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        scores = strategy.score(history)
        weights = build_target_weights(scores, history, config)

        self.assertEqual(weights, {"A": 1.0})

    def test_cross_sectional_momentum_scores_relative_performance(self) -> None:
        strategy = CrossSectionalMomentumStrategy(
            lookback_window=3,
            min_score=-1.0,
            max_trailing_drawdown=1.0,
            drawdown_lookback_window=0,
            score_transform="raw",
        )
        history = {
            "WINNER": [
                DailyBar(date(2024, 1, 1), "WINNER", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "WINNER", 1, 1, 1, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "WINNER", 1, 1, 1, 12, 12, 1000),
            ],
            "LOSER": [
                DailyBar(date(2024, 1, 1), "LOSER", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "LOSER", 1, 1, 1, 9, 9, 1000),
                DailyBar(date(2024, 1, 3), "LOSER", 1, 1, 1, 8, 8, 1000),
            ],
        }

        scores = strategy.score(history)

        self.assertGreater(scores["WINNER"], scores["LOSER"])

    def test_mean_reversion_prefers_recent_losers(self) -> None:
        strategy = MeanReversionStrategy(lookback_window=3, min_score=-1.0)
        history = {
            "WINNER": [
                DailyBar(date(2024, 1, 1), "WINNER", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "WINNER", 1, 1, 1, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "WINNER", 1, 1, 1, 12, 12, 1000),
            ],
            "LOSER": [
                DailyBar(date(2024, 1, 1), "LOSER", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "LOSER", 1, 1, 1, 9, 9, 1000),
                DailyBar(date(2024, 1, 3), "LOSER", 1, 1, 1, 8, 8, 1000),
            ],
        }

        scores = strategy.score(history)

        self.assertGreater(scores["LOSER"], scores["WINNER"])

    def test_vol_inverse_weighting_prefers_lower_volatility(self) -> None:
        history = {
            "LOWVOL": [
                DailyBar(date(2024, 1, 1), "LOWVOL", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "LOWVOL", 1, 1, 1, 10.1, 10.1, 1000),
                DailyBar(date(2024, 1, 3), "LOWVOL", 1, 1, 1, 10.2, 10.2, 1000),
            ],
            "HIGHVOL": [
                DailyBar(date(2024, 1, 1), "HIGHVOL", 1, 1, 1, 10, 10, 1000),
                DailyBar(date(2024, 1, 2), "HIGHVOL", 1, 1, 1, 11, 11, 1000),
                DailyBar(date(2024, 1, 3), "HIGHVOL", 1, 1, 1, 12, 12, 1000),
            ],
        }
        scores = {"LOWVOL": 0.02, "HIGHVOL": 0.03}
        config = StrategyConfig(
            name="sma_cross",
            top_n=2,
            weighting="vol_inverse",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        weights = build_target_weights(scores, history, config)

        self.assertGreater(weights["LOWVOL"], weights["HIGHVOL"])

    def test_beta_vol_inverse_weighting_prefers_lower_beta_name(self) -> None:
        history = {
            "LOWBETA": [
                DailyBar(date(2024, 1, 1), "LOWBETA", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "LOWBETA", 1, 1, 1, 10.2, 10.2, 1000),
                DailyBar(date(2024, 1, 3), "LOWBETA", 1, 1, 1, 10.3, 10.3, 1000),
                DailyBar(date(2024, 1, 4), "LOWBETA", 1, 1, 1, 10.4, 10.4, 1000),
            ],
            "HIGHBETA": [
                DailyBar(date(2024, 1, 1), "HIGHBETA", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "HIGHBETA", 1, 1, 1, 10.5, 10.5, 1000),
                DailyBar(date(2024, 1, 3), "HIGHBETA", 1, 1, 1, 10.8, 10.8, 1000),
                DailyBar(date(2024, 1, 4), "HIGHBETA", 1, 1, 1, 11.2, 11.2, 1000),
            ],
            "MARKET": [
                DailyBar(date(2024, 1, 1), "MARKET", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "MARKET", 1, 1, 1, 10.35, 10.35, 1000),
                DailyBar(date(2024, 1, 3), "MARKET", 1, 1, 1, 10.55, 10.55, 1000),
                DailyBar(date(2024, 1, 4), "MARKET", 1, 1, 1, 10.8, 10.8, 1000),
            ],
        }
        scores = {"LOWBETA": 0.03, "HIGHBETA": 0.04}
        config = StrategyConfig(
            name="cross_sectional_momentum",
            top_n=2,
            weighting="beta_vol_inverse",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=4, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        weights = build_target_weights(scores, history, config)

        self.assertGreater(weights["LOWBETA"], weights["HIGHBETA"])

    def test_sma_threshold_filters_small_crossovers(self) -> None:
        strategy = SmaCrossStrategy(short_window=2, long_window=3, signal_threshold=0.02)
        history = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "A", 1, 1, 1, 10.1, 10.1, 1000),
                DailyBar(date(2024, 1, 3), "A", 1, 1, 1, 10.2, 10.2, 1000),
            ]
        }

        scores = strategy.score(history)

        self.assertEqual(scores, {})

    def test_momentum_threshold_filters_weak_winners(self) -> None:
        strategy = CrossSectionalMomentumStrategy(
            lookback_window=3,
            min_score=0.15,
            max_trailing_drawdown=1.0,
            drawdown_lookback_window=0,
            score_transform="raw",
        )
        history = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "A", 1, 1, 1, 10.5, 10.5, 1000),
                DailyBar(date(2024, 1, 3), "A", 1, 1, 1, 11.0, 11.0, 1000),
            ]
        }

        scores = strategy.score(history)

        self.assertEqual(scores, {})

    def test_momentum_drawdown_filter_excludes_high_drawdown_name(self) -> None:
        strategy = CrossSectionalMomentumStrategy(
            lookback_window=5,
            min_score=0.0,
            max_trailing_drawdown=0.20,
            drawdown_lookback_window=5,
            score_transform="raw",
        )
        history = {
            "STABLE": [
                DailyBar(date(2024, 1, 1), "STABLE", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "STABLE", 1, 1, 1, 11.0, 11.0, 1000),
                DailyBar(date(2024, 1, 3), "STABLE", 1, 1, 1, 10.8, 10.8, 1000),
                DailyBar(date(2024, 1, 4), "STABLE", 1, 1, 1, 11.2, 11.2, 1000),
                DailyBar(date(2024, 1, 5), "STABLE", 1, 1, 1, 11.4, 11.4, 1000),
            ],
            "WHIPSAW": [
                DailyBar(date(2024, 1, 1), "WHIPSAW", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "WHIPSAW", 1, 1, 1, 13.0, 13.0, 1000),
                DailyBar(date(2024, 1, 3), "WHIPSAW", 1, 1, 1, 9.0, 9.0, 1000),
                DailyBar(date(2024, 1, 4), "WHIPSAW", 1, 1, 1, 10.5, 10.5, 1000),
                DailyBar(date(2024, 1, 5), "WHIPSAW", 1, 1, 1, 11.0, 11.0, 1000),
            ],
        }

        scores = strategy.score(history)

        self.assertIn("STABLE", scores)
        self.assertNotIn("WHIPSAW", scores)

    def test_mean_reversion_threshold_filters_small_reversals(self) -> None:
        strategy = MeanReversionStrategy(lookback_window=3, min_score=0.25)
        history = {
            "A": [
                DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10.0, 10.0, 1000),
                DailyBar(date(2024, 1, 2), "A", 1, 1, 1, 9.5, 9.5, 1000),
                DailyBar(date(2024, 1, 3), "A", 1, 1, 1, 9.0, 9.0, 1000),
            ]
        }

        scores = strategy.score(history)

        self.assertEqual(scores, {})

    def test_vol_adjusted_momentum_prefers_lower_volatility_name(self) -> None:
        strategy = CrossSectionalMomentumStrategy(
            lookback_window=3,
            min_score=0.0,
            max_trailing_drawdown=1.0,
            drawdown_lookback_window=3,
            score_transform="vol_adjusted",
        )
        feature_snapshot = {
            "LOWVOL": {"momentum_return": 0.10, "realized_volatility": 0.02, "trailing_drawdown": 0.05},
            "HIGHVOL": {"momentum_return": 0.10, "realized_volatility": 0.08, "trailing_drawdown": 0.05},
        }

        scores = strategy.score({"LOWVOL": [], "HIGHVOL": []}, feature_snapshot=feature_snapshot)

        self.assertGreater(scores["LOWVOL"], scores["HIGHVOL"])

    def test_drawdown_penalized_momentum_keeps_name_but_reduces_score(self) -> None:
        strategy = CrossSectionalMomentumStrategy(
            lookback_window=3,
            min_score=0.0,
            max_trailing_drawdown=0.10,
            drawdown_lookback_window=3,
            score_transform="drawdown_penalized",
        )
        feature_snapshot = {
            "SHALLOW": {"momentum_return": 0.10, "realized_volatility": 0.02, "trailing_drawdown": 0.05},
            "DEEP": {"momentum_return": 0.10, "realized_volatility": 0.02, "trailing_drawdown": 0.40},
        }

        scores = strategy.score({"SHALLOW": [], "DEEP": []}, feature_snapshot=feature_snapshot)

        self.assertIn("DEEP", scores)
        self.assertLess(scores["DEEP"], scores["SHALLOW"])

    def test_selection_buffer_keeps_near_cutoff_existing_holding(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.3, "B": 0.2, "C": 0.1}
        config = StrategyConfig(
            name="sma_cross",
            top_n=2,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        weights = build_target_weights(
            scores,
            history,
            config,
            current_holdings={"C"},
            holding_days={"C": 30},
            selection_buffer_slots=1,
            min_holding_days=0,
        )

        self.assertEqual(set(weights), {"A", "B", "C"})

    def test_min_holding_days_keeps_recent_position(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.3, "B": 0.2, "C": 0.05}
        config = StrategyConfig(
            name="sma_cross",
            top_n=2,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        weights = build_target_weights(
            scores,
            history,
            config,
            current_holdings={"C"},
            holding_days={"C": 5},
            selection_buffer_slots=0,
            min_holding_days=20,
        )

        self.assertEqual(set(weights), {"A", "C"})

    def test_protected_holdings_do_not_expand_basket_without_limit(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
            "D": [DailyBar(date(2024, 1, 1), "D", 1, 1, 1, 10, 10, 1000)] * 3,
            "E": [DailyBar(date(2024, 1, 1), "E", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.5, "B": 0.4, "C": 0.3, "D": 0.2, "E": 0.1}
        config = StrategyConfig(
            name="sma_cross",
            top_n=2,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )

        weights = build_target_weights(
            scores,
            history,
            config,
            current_holdings={"C", "D", "E"},
            holding_days={"C": 5, "D": 5, "E": 100},
            selection_buffer_slots=1,
            min_holding_days=20,
        )

        self.assertLessEqual(len(weights), 3)
        self.assertIn("C", weights)
        self.assertIn("D", weights)

    def test_sector_cap_limits_same_sector_selection(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.3, "B": 0.2, "C": 0.1}
        config = StrategyConfig(
            name="sma_cross",
            top_n=2,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )
        instruments = {
            "A": Instrument("A", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials"),
            "B": Instrument("B", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials"),
            "C": Instrument("C", "XLON", "GBP", "", "", "", "ACTIVE", sector="Consumer Staples"),
        }

        weights = build_target_weights(
            scores,
            history,
            config,
            instruments=instruments,
            max_positions_per_sector=1,
        )

        self.assertEqual(set(weights), {"A", "C"})

    def test_sector_relative_ranking_distributes_across_groups(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
            "D": [DailyBar(date(2024, 1, 1), "D", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10}
        config = StrategyConfig(
            name="cross_sectional_momentum",
            top_n=2,
            weighting="equal",
            ranking_mode="sector_relative",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )
        instruments = {
            "A": Instrument("A", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials"),
            "B": Instrument("B", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials"),
            "C": Instrument("C", "XLON", "GBP", "", "", "", "ACTIVE", sector="Energy"),
            "D": Instrument("D", "XLON", "GBP", "", "", "", "ACTIVE", sector="Energy"),
        }

        weights = build_target_weights(scores, history, config, instruments=instruments)

        self.assertEqual(set(weights), {"A", "C"})

    def test_industry_and_benchmark_bucket_caps_limit_selection(self) -> None:
        history = {
            "A": [DailyBar(date(2024, 1, 1), "A", 1, 1, 1, 10, 10, 1000)] * 3,
            "B": [DailyBar(date(2024, 1, 1), "B", 1, 1, 1, 10, 10, 1000)] * 3,
            "C": [DailyBar(date(2024, 1, 1), "C", 1, 1, 1, 10, 10, 1000)] * 3,
        }
        scores = {"A": 0.3, "B": 0.2, "C": 0.1}
        config = StrategyConfig(
            name="sma_cross",
            top_n=3,
            weighting="equal",
            ranking_mode="global",
            score_transform="raw",
            min_candidates_per_group=1,
            sma_cross=SmaCrossConfig(short_window=2, long_window=3, signal_threshold=0.0),
            cross_sectional_momentum=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
            mean_reversion=LookbackStrategyConfig(lookback_window=3, min_score=0.0),
        )
        instruments = {
            "A": Instrument("A", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials", industry="Banks", benchmark_bucket="FTSE100"),
            "B": Instrument("B", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials", industry="Banks", benchmark_bucket="FTSE100"),
            "C": Instrument("C", "XLON", "GBP", "", "", "", "ACTIVE", sector="Financials", industry="Insurance", benchmark_bucket="FTSE250"),
        }

        weights = build_target_weights(
            scores,
            history,
            config,
            instruments=instruments,
            max_positions_per_industry=1,
            max_positions_per_benchmark_bucket=1,
        )

        self.assertEqual(set(weights), {"A", "C"})


if __name__ == "__main__":
    unittest.main()
