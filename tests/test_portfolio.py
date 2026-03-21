from datetime import date
import unittest

from trotters_trader.domain import Fill
from trotters_trader.portfolio import PortfolioState


class PortfolioTests(unittest.TestCase):
    def test_holding_days_start_on_entry_and_increment(self) -> None:
        portfolio = PortfolioState(cash=10000.0)
        fill = Fill(
            trade_date=date(2024, 1, 2),
            instrument="TSCO.L",
            quantity=10,
            side="BUY",
            requested_quantity=10,
            price=100.0,
            gross_notional=1000.0,
            commission=1.0,
            slippage=0.0,
            spread_cost=0.0,
            stamp_duty=0.0,
            participation_rate=0.01,
        )

        portfolio.apply_fill(fill)
        self.assertEqual(portfolio.holding_days["TSCO.L"], 0)

        portfolio.advance_holding_days()
        self.assertEqual(portfolio.holding_days["TSCO.L"], 1)


if __name__ == "__main__":
    unittest.main()
