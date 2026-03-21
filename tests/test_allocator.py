from datetime import date
import unittest

from trotters_trader.allocator import build_rebalance_orders
from trotters_trader.config import PortfolioConfig
from trotters_trader.domain import DailyBar
from trotters_trader.portfolio import PortfolioState


class AllocatorTests(unittest.TestCase):
    def test_adv_and_max_weight_cap_target_quantity(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "TSCO.L": DailyBar(
                trade_date=date(2024, 1, 8),
                instrument="TSCO.L",
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                adjusted_close=100.0,
                volume=10000.0,
            )
        }
        history = {
            "TSCO.L": [
                DailyBar(date(2024, 1, 2), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 3), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 4), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 5), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 8), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
            ]
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.02,
            target_gross_exposure=0.98,
            max_position_weight=0.25,
            rebalance_threshold_bps=50.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=1.0,
            initial_deployment_turnover_pct=1.0,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=0.02,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"TSCO.L": 1.0},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].quantity, 200)

    def test_rebalance_threshold_suppresses_small_changes(self) -> None:
        portfolio = PortfolioState(cash=75000.0, positions={"TSCO.L": 250})
        prices = {
            "TSCO.L": DailyBar(
                trade_date=date(2024, 1, 8),
                instrument="TSCO.L",
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                adjusted_close=100.0,
                volume=10000.0,
            )
        }
        history = {
            "TSCO.L": [
                DailyBar(date(2024, 1, 2), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 3), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 4), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 5), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
                DailyBar(date(2024, 1, 8), "TSCO.L", 100, 101, 99, 100, 100, 10_000),
            ]
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.02,
            target_gross_exposure=0.98,
            max_position_weight=0.251,
            rebalance_threshold_bps=20.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=1.0,
            initial_deployment_turnover_pct=1.0,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=0.10,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"TSCO.L": 0.25},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(orders, [])

    def test_turnover_budget_limits_total_trade_notional(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=1.0,
            max_position_weight=1.0,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=0.30,
            initial_deployment_turnover_pct=0.30,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.20, "BBB.L": 0.20},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(sum(order.quantity for order in orders), 300)
        self.assertEqual(len(orders), 2)

    def test_turnover_budget_can_partially_fill_last_order(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=1.0,
            max_position_weight=1.0,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=0.25,
            initial_deployment_turnover_pct=0.25,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.20, "BBB.L": 0.20},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(sum(order.quantity for order in orders), 250)

    def test_sells_are_not_blocked_by_buy_turnover_budget(self) -> None:
        portfolio = PortfolioState(cash=40000.0, positions={"AAA.L": 300, "BBB.L": 300})
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "CCC.L": DailyBar(date(2024, 1, 8), "CCC.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "CCC.L": [DailyBar(date(2024, 1, 2), "CCC.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=0.5,
            max_position_weight=1.0,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=0.10,
            initial_deployment_turnover_pct=0.10,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"CCC.L": 0.5},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        sell_instruments = {order.instrument for order in orders if order.side == "SELL"}
        buy_orders = [order for order in orders if order.side == "BUY"]

        self.assertEqual(sell_instruments, {"AAA.L", "BBB.L"})
        self.assertEqual(len(buy_orders), 1)
        self.assertEqual(buy_orders[0].instrument, "CCC.L")
        self.assertEqual(buy_orders[0].quantity, 100)

    def test_initial_deployment_turnover_budget_applies_when_underinvested(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=1.0,
            max_position_weight=0.6,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=0.06,
            initial_deployment_turnover_pct=0.30,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.8, "BBB.L": 0.2},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(sum(order.quantity for order in orders), 300)

    def test_weight_caps_are_redistributed_across_remaining_names(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "CCC.L": DailyBar(date(2024, 1, 8), "CCC.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "CCC.L": [DailyBar(date(2024, 1, 2), "CCC.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=1.0,
            max_position_weight=0.4,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=1.0,
            initial_deployment_turnover_pct=1.0,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.8, "BBB.L": 0.1, "CCC.L": 0.1},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        quantities = {order.instrument: order.quantity for order in orders}
        self.assertEqual(quantities["AAA.L"], 400)
        self.assertEqual(quantities["BBB.L"], 300)
        self.assertEqual(quantities["CCC.L"], 300)

    def test_target_gross_exposure_scales_position_sizing(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        history = {
            "AAA.L": [DailyBar(date(2024, 1, 2), "AAA.L", 100, 101, 99, 100, 100, 50_000)] * 5,
            "BBB.L": [DailyBar(date(2024, 1, 2), "BBB.L", 100, 101, 99, 100, 100, 50_000)] * 5,
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=0.5,
            max_position_weight=1.0,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=1.0,
            initial_deployment_turnover_pct=1.0,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.5, "BBB.L": 0.5},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertEqual(sum(order.quantity for order in orders), 500)

    def test_volatility_target_scales_down_exposure(self) -> None:
        portfolio = PortfolioState(cash=100000.0)
        prices = {
            "AAA.L": DailyBar(date(2024, 1, 8), "AAA.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
            "BBB.L": DailyBar(date(2024, 1, 8), "BBB.L", 100.0, 101.0, 99.0, 100.0, 100.0, 50_000),
        }
        volatile_path = [100.0, 200.0, 100.0, 200.0, 100.0, 200.0]
        history = {
            "AAA.L": [
                DailyBar(date(2024, 1, 2 + index), "AAA.L", price, price, price, price, price, 50_000)
                for index, price in enumerate(volatile_path)
            ],
            "BBB.L": [
                DailyBar(date(2024, 1, 2 + index), "BBB.L", price, price, price, price, price, 50_000)
                for index, price in enumerate(volatile_path)
            ],
        }
        config = PortfolioConfig(
            cash_buffer_pct=0.0,
            target_gross_exposure=1.0,
            max_position_weight=1.0,
            rebalance_threshold_bps=0.0,
            rebalance_frequency_days=1,
            max_rebalance_turnover_pct=1.0,
            initial_deployment_turnover_pct=1.0,
            selection_buffer_slots=0,
            max_positions_per_sector=0,
            min_holding_days=0,
            adv_window_days=5,
            max_target_adv_participation=1.0,
            volatility_target=0.10,
            volatility_lookback_days=5,
        )

        orders = build_rebalance_orders(
            portfolio=portfolio,
            target_weights={"AAA.L": 0.5, "BBB.L": 0.5},
            prices=prices,
            history_by_instrument=history,
            config=config,
        )

        self.assertLess(sum(order.quantity for order in orders), 200)


if __name__ == "__main__":
    unittest.main()
