from __future__ import annotations

import math

from trotters_trader.config import PortfolioConfig
from trotters_trader.domain import DailyBar, Order
from trotters_trader.portfolio import PortfolioState


def build_rebalance_orders(
    portfolio: PortfolioState,
    target_weights: dict[str, float],
    prices: dict[str, DailyBar],
    history_by_instrument: dict[str, list[DailyBar]],
    config: PortfolioConfig,
) -> list[Order]:
    instruments = sorted(set(target_weights) | set(portfolio.positions))
    nav = _portfolio_nav(portfolio, prices)
    if nav <= 0:
        return []

    capped_weights = _redistribute_capped_weights(target_weights, config.max_position_weight)
    target_gross_exposure_ratio = _target_gross_exposure_ratio(
        target_weights,
        history_by_instrument,
        config,
    )
    investable_nav = nav * target_gross_exposure_ratio
    candidates: list[tuple[float, Order, float]] = []

    for instrument in instruments:
        bar = prices.get(instrument)
        if bar is None or bar.open <= 0:
            continue

        capped_weight = capped_weights.get(instrument, 0.0)
        current_quantity = portfolio.positions.get(instrument, 0)
        current_value = current_quantity * bar.close
        current_weight = current_value / nav if nav > 0 else 0.0

        if abs(capped_weight - current_weight) * 10_000.0 < config.rebalance_threshold_bps:
            continue

        target_value = investable_nav * capped_weight
        uncapped_target_quantity = int(target_value // bar.open)
        adv_cap_quantity = _adv_cap_quantity(history_by_instrument.get(instrument, []), config)
        target_quantity = min(uncapped_target_quantity, adv_cap_quantity)
        delta = target_quantity - current_quantity
        if delta == 0:
            continue

        side = "BUY" if delta > 0 else "SELL"
        quantity = abs(delta)
        notional = quantity * bar.open
        candidates.append(
            (
                abs(capped_weight - current_weight),
                Order(
                    trade_date=bar.trade_date,
                    instrument=instrument,
                    quantity=quantity,
                    side=side,
                ),
                notional,
            )
        )

    return _apply_turnover_budget(
        candidates,
        config,
        nav,
        prices,
        _gross_exposure_ratio(portfolio, prices, nav),
        min(sum(capped_weights.values()) * target_gross_exposure_ratio, 1.0),
    )


def _adv_cap_quantity(bars: list[DailyBar], config: PortfolioConfig) -> int:
    if not bars:
        return 0
    recent = bars[-config.adv_window_days :]
    average_volume = sum(bar.volume for bar in recent) / len(recent)
    return int(average_volume * config.max_target_adv_participation)


def _portfolio_nav(portfolio: PortfolioState, prices: dict[str, DailyBar]) -> float:
    gross_market_value = 0.0
    for instrument, quantity in portfolio.positions.items():
        bar = prices.get(instrument)
        if bar is None:
            continue
        gross_market_value += quantity * bar.close
    return portfolio.cash + gross_market_value


def _gross_exposure_ratio(
    portfolio: PortfolioState,
    prices: dict[str, DailyBar],
    nav: float,
) -> float:
    if nav <= 0:
        return 0.0
    gross_market_value = 0.0
    for instrument, quantity in portfolio.positions.items():
        bar = prices.get(instrument)
        if bar is None:
            continue
        gross_market_value += quantity * bar.close
    return gross_market_value / nav


def _apply_turnover_budget(
    candidates: list[tuple[float, Order, float]],
    config: PortfolioConfig,
    nav: float,
    prices: dict[str, DailyBar],
    current_gross_exposure_ratio: float,
    target_gross_exposure_ratio: float,
) -> list[Order]:
    if not candidates:
        return []

    turnover_budget_pct = config.max_rebalance_turnover_pct
    if current_gross_exposure_ratio < target_gross_exposure_ratio * 0.8:
        turnover_budget_pct = max(config.initial_deployment_turnover_pct, turnover_budget_pct)

    budget = nav * turnover_budget_pct
    if budget <= 0:
        return []

    approved: list[Order] = []
    sell_candidates = [
        (priority, order, notional)
        for priority, order, notional in candidates
        if order.side == "SELL"
    ]
    buy_candidates = [
        (priority, order, notional)
        for priority, order, notional in candidates
        if order.side == "BUY"
    ]

    for _, order, _ in sorted(sell_candidates, key=lambda item: item[0], reverse=True):
        approved.append(order)

    spent = 0.0

    for _, order, notional in sorted(buy_candidates, key=lambda item: item[0], reverse=True):
        if spent >= budget:
            break
        if spent + notional <= budget:
            approved.append(order)
            spent += notional
            continue

        bar = prices.get(order.instrument)
        if bar is None or bar.open <= 0:
            continue
        remaining_budget = budget - spent
        partial_quantity = int(remaining_budget // bar.open)
        if partial_quantity <= 0:
            continue
        approved.append(
            Order(
                trade_date=order.trade_date,
                instrument=order.instrument,
                quantity=partial_quantity,
                side=order.side,
            )
        )
        spent += partial_quantity * bar.open
        break

    return approved


def _effective_target_gross_exposure(config: PortfolioConfig) -> float:
    cash_limited_exposure = max(0.0, 1.0 - config.cash_buffer_pct)
    return max(0.0, min(config.target_gross_exposure, cash_limited_exposure, 1.0))


def _target_gross_exposure_ratio(
    target_weights: dict[str, float],
    history_by_instrument: dict[str, list[DailyBar]],
    config: PortfolioConfig,
) -> float:
    base_exposure = _effective_target_gross_exposure(config)
    if base_exposure <= 0 or config.volatility_target <= 0:
        return base_exposure

    basket_volatility = _portfolio_realized_volatility(
        target_weights,
        history_by_instrument,
        config.volatility_lookback_days,
    )
    if basket_volatility <= 0:
        return base_exposure

    scale = min(1.0, config.volatility_target / basket_volatility)
    return base_exposure * scale


def _portfolio_realized_volatility(
    target_weights: dict[str, float],
    history_by_instrument: dict[str, list[DailyBar]],
    lookback_days: int,
) -> float:
    positive_weights = {
        instrument: weight
        for instrument, weight in target_weights.items()
        if weight > 0 and len(history_by_instrument.get(instrument, [])) >= lookback_days + 1
    }
    if not positive_weights:
        return 0.0

    total_weight = sum(positive_weights.values())
    if total_weight <= 0:
        return 0.0

    normalized_weights = {
        instrument: weight / total_weight
        for instrument, weight in positive_weights.items()
    }
    returns_by_instrument: dict[str, list[float]] = {}
    for instrument in normalized_weights:
        bars = history_by_instrument[instrument][-(lookback_days + 1) :]
        returns: list[float] = []
        for previous, current in zip(bars, bars[1:]):
            if previous.adjusted_close <= 0:
                return 0.0
            returns.append((current.adjusted_close / previous.adjusted_close) - 1.0)
        if len(returns) != lookback_days:
            return 0.0
        returns_by_instrument[instrument] = returns

    portfolio_returns = []
    for day_index in range(lookback_days):
        portfolio_returns.append(
            sum(
                normalized_weights[instrument] * returns_by_instrument[instrument][day_index]
                for instrument in normalized_weights
            )
        )

    if not portfolio_returns:
        return 0.0
    mean_return = sum(portfolio_returns) / len(portfolio_returns)
    variance = sum((value - mean_return) ** 2 for value in portfolio_returns) / len(portfolio_returns)
    return math.sqrt(variance)


def _redistribute_capped_weights(
    target_weights: dict[str, float],
    max_position_weight: float,
) -> dict[str, float]:
    positive_weights = {
        instrument: max(weight, 0.0)
        for instrument, weight in target_weights.items()
        if weight > 0.0
    }
    if not positive_weights:
        return {}

    total_target = min(sum(positive_weights.values()), max_position_weight * len(positive_weights))
    allocated: dict[str, float] = {}
    remaining = dict(positive_weights)

    while remaining:
        remaining_target = total_target - sum(allocated.values())
        if remaining_target <= 1e-12:
            break

        total_remaining_weight = sum(remaining.values())
        if total_remaining_weight <= 0:
            break

        scale = remaining_target / total_remaining_weight
        newly_capped: list[str] = []
        for instrument, raw_weight in remaining.items():
            scaled_weight = raw_weight * scale
            if scaled_weight >= max_position_weight - 1e-12:
                allocated[instrument] = max_position_weight
                newly_capped.append(instrument)

        if not newly_capped:
            for instrument, raw_weight in remaining.items():
                allocated[instrument] = raw_weight * scale
            break

        for instrument in newly_capped:
            remaining.pop(instrument, None)

    return {instrument: weight for instrument, weight in allocated.items() if weight > 0.0}
