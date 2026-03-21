from __future__ import annotations

import math

from trotters_trader.config import ExecutionConfig
from trotters_trader.domain import DailyBar, Fill, Order


def simulate_fill(order: Order, bar: DailyBar, execution: ExecutionConfig) -> Fill | None:
    max_fill_quantity = math.floor(bar.volume * execution.max_participation_rate)
    if max_fill_quantity <= 0:
        return None

    if execution.allow_partial_fills:
        filled_quantity = min(order.quantity, max_fill_quantity)
    elif order.quantity <= max_fill_quantity:
        filled_quantity = order.quantity
    else:
        return None

    participation_rate = filled_quantity / bar.volume if bar.volume > 0 else 0.0
    half_spread_bps = execution.spread_bps / 2.0
    slippage_bps = execution.slippage_bps * (
        1.0 + (participation_rate / execution.max_participation_rate if execution.max_participation_rate > 0 else 0.0)
    )
    total_price_bps = half_spread_bps + slippage_bps
    price_adjustment = bar.open * total_price_bps / 10_000.0
    fill_price = bar.open + price_adjustment if order.side == "BUY" else bar.open - price_adjustment

    gross_notional = fill_price * filled_quantity
    commission = gross_notional * execution.commission_bps / 10_000.0
    slippage = gross_notional * slippage_bps / 10_000.0
    spread_cost = gross_notional * half_spread_bps / 10_000.0
    stamp_duty = 0.0
    if order.side == "BUY":
        stamp_duty = gross_notional * execution.stamp_duty_bps / 10_000.0

    return Fill(
        trade_date=order.trade_date,
        instrument=order.instrument,
        quantity=filled_quantity,
        side=order.side,
        requested_quantity=order.quantity,
        price=fill_price,
        gross_notional=gross_notional,
        commission=commission,
        slippage=slippage,
        spread_cost=spread_cost,
        stamp_duty=stamp_duty,
        participation_rate=participation_rate,
    )
