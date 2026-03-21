from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from trotters_trader.domain import ClosedTrade, Fill


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    average_costs: dict[str, float] = field(default_factory=dict)
    holding_days: dict[str, int] = field(default_factory=dict)
    closed_trades: list[ClosedTrade] = field(default_factory=list)

    def advance_holding_days(self) -> None:
        for instrument in list(self.positions):
            self.holding_days[instrument] = self.holding_days.get(instrument, 0) + 1

    def apply_fill(self, fill: Fill) -> None:
        signed_quantity = fill.quantity if fill.side == "BUY" else -fill.quantity
        current_quantity = self.positions.get(fill.instrument, 0)
        new_quantity = current_quantity + signed_quantity

        if fill.side == "BUY":
            self._apply_buy(fill, current_quantity, new_quantity)
        else:
            self._apply_sell(fill, current_quantity, new_quantity)

        if new_quantity == 0:
            self.positions.pop(fill.instrument, None)
            self.average_costs.pop(fill.instrument, None)
            self.holding_days.pop(fill.instrument, None)
        else:
            self.positions[fill.instrument] = new_quantity
            if current_quantity == 0 and fill.side == "BUY":
                self.holding_days[fill.instrument] = 0

        gross_cash_flow = fill.gross_notional
        total_costs = fill.commission + fill.stamp_duty

        if fill.side == "BUY":
            self.cash -= gross_cash_flow + total_costs
        else:
            self.cash += gross_cash_flow - total_costs

    def _apply_buy(self, fill: Fill, current_quantity: int, new_quantity: int) -> None:
        existing_cost = self.average_costs.get(fill.instrument, 0.0)
        existing_notional = existing_cost * current_quantity
        incoming_cost = fill.gross_notional + fill.commission + fill.stamp_duty
        if new_quantity > 0:
            self.average_costs[fill.instrument] = (existing_notional + incoming_cost) / new_quantity

    def _apply_sell(self, fill: Fill, current_quantity: int, new_quantity: int) -> None:
        average_cost = self.average_costs.get(fill.instrument, 0.0)
        realized_value = fill.gross_notional - fill.commission - fill.stamp_duty
        realized_cost = average_cost * fill.quantity
        realized_pnl = realized_value - realized_cost
        return_pct = 0.0 if realized_cost == 0 else realized_pnl / realized_cost
        self.closed_trades.append(
            ClosedTrade(
                trade_date=fill.trade_date,
                instrument=fill.instrument,
                quantity=fill.quantity,
                realized_pnl=realized_pnl,
                return_pct=return_pct,
            )
        )
        if new_quantity > 0:
            self.average_costs[fill.instrument] = average_cost
