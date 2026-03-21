from datetime import date
import unittest

from trotters_trader.config import ExecutionConfig
from trotters_trader.domain import DailyBar, Order
from trotters_trader.execution import simulate_fill


class ExecutionTests(unittest.TestCase):
    def test_partial_fill_respects_participation_cap(self) -> None:
        order = Order(
            trade_date=date(2024, 1, 3),
            instrument="TSCO.L",
            quantity=1000,
            side="BUY",
        )
        bar = DailyBar(
            trade_date=date(2024, 1, 3),
            instrument="TSCO.L",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            adjusted_close=100.0,
            volume=10000.0,
        )
        execution = ExecutionConfig(
            fill_model="next_open",
            commission_bps=10.0,
            slippage_bps=5.0,
            spread_bps=8.0,
            stamp_duty_bps=50.0,
            max_participation_rate=0.05,
            allow_partial_fills=True,
        )

        fill = simulate_fill(order, bar, execution)

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill.quantity, 500)
        self.assertEqual(fill.requested_quantity, 1000)
        self.assertAlmostEqual(fill.participation_rate, 0.05)


if __name__ == "__main__":
    unittest.main()
