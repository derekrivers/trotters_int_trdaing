from __future__ import annotations

from trotters_trader.config import BenchmarkConfig
from trotters_trader.domain import DailyBar, PortfolioSnapshot


def build_equal_weight_benchmark(
    bars_by_instrument: dict[str, list[DailyBar]],
    initial_cash: float,
) -> list[PortfolioSnapshot]:
    if not bars_by_instrument:
        return []

    instruments = sorted(bars_by_instrument)
    if not instruments:
        return []

    shared_dates = sorted(
        set.intersection(*[{bar.trade_date for bar in bars} for bars in bars_by_instrument.values()])
    )
    if not shared_dates:
        return []

    first_date = shared_dates[0]
    bar_lookup = {
        instrument: {bar.trade_date: bar for bar in bars}
        for instrument, bars in bars_by_instrument.items()
    }
    allocation_per_instrument = initial_cash / len(instruments)
    quantities: dict[str, int] = {}
    cash = initial_cash

    for instrument in instruments:
        entry_bar = bar_lookup[instrument][first_date]
        quantity = int(allocation_per_instrument // entry_bar.close)
        quantities[instrument] = quantity
        cash -= quantity * entry_bar.close

    performance: list[PortfolioSnapshot] = []
    for trade_date in shared_dates:
        gross_market_value = 0.0
        for instrument, quantity in quantities.items():
            gross_market_value += quantity * bar_lookup[instrument][trade_date].close
        nav = cash + gross_market_value
        performance.append(
            PortfolioSnapshot(
                trade_date=trade_date,
                cash=cash,
                gross_market_value=gross_market_value,
                gross_exposure_ratio=0.0 if nav == 0 else gross_market_value / nav,
                net_asset_value=nav,
            )
        )

    return performance


def build_price_weighted_benchmark(
    bars_by_instrument: dict[str, list[DailyBar]],
    initial_cash: float,
) -> list[PortfolioSnapshot]:
    if not bars_by_instrument:
        return []

    instruments = sorted(bars_by_instrument)
    if not instruments:
        return []

    shared_dates = _shared_dates(bars_by_instrument)
    if not shared_dates:
        return []

    first_date = shared_dates[0]
    bar_lookup = _bar_lookup(bars_by_instrument)
    total_price = sum(bar_lookup[instrument][first_date].close for instrument in instruments)
    if total_price == 0:
        return []

    quantities: dict[str, int] = {}
    cash = initial_cash
    for instrument in instruments:
        weight = bar_lookup[instrument][first_date].close / total_price
        allocation = initial_cash * weight
        quantity = int(allocation // bar_lookup[instrument][first_date].close)
        quantities[instrument] = quantity
        cash -= quantity * bar_lookup[instrument][first_date].close

    return _benchmark_performance(shared_dates, bar_lookup, quantities, cash)


def build_benchmarks(
    bars_by_instrument: dict[str, list[DailyBar]],
    initial_cash: float,
    config: BenchmarkConfig,
) -> dict[str, list[PortfolioSnapshot]]:
    builders = {
        "equal_weight": build_equal_weight_benchmark,
        "price_weighted": build_price_weighted_benchmark,
    }
    return {
        model: builders[model](bars_by_instrument, initial_cash)
        for model in config.models
        if model in builders
    }


def equal_weight_lookback_return(
    bars_by_instrument: dict[str, list[DailyBar]],
    lookback_days: int,
) -> float | None:
    if lookback_days <= 0:
        return None

    returns: list[float] = []
    for bars in bars_by_instrument.values():
        if len(bars) < lookback_days + 1:
            continue
        window = bars[-(lookback_days + 1) :]
        start_price = window[0].adjusted_close
        end_price = window[-1].adjusted_close
        if start_price <= 0:
            continue
        returns.append((end_price / start_price) - 1.0)

    if not returns:
        return None
    return sum(returns) / len(returns)


def _shared_dates(bars_by_instrument: dict[str, list[DailyBar]]) -> list:
    return sorted(
        set.intersection(*[{bar.trade_date for bar in bars} for bars in bars_by_instrument.values()])
    )


def _bar_lookup(bars_by_instrument: dict[str, list[DailyBar]]) -> dict[str, dict]:
    return {
        instrument: {bar.trade_date: bar for bar in bars}
        for instrument, bars in bars_by_instrument.items()
    }


def _benchmark_performance(
    shared_dates: list,
    bar_lookup: dict[str, dict],
    quantities: dict[str, int],
    cash: float,
) -> list[PortfolioSnapshot]:
    performance: list[PortfolioSnapshot] = []
    for trade_date in shared_dates:
        gross_market_value = 0.0
        for instrument, quantity in quantities.items():
            gross_market_value += quantity * bar_lookup[instrument][trade_date].close
        nav = cash + gross_market_value
        performance.append(
            PortfolioSnapshot(
                trade_date=trade_date,
                cash=cash,
                gross_market_value=gross_market_value,
                gross_exposure_ratio=0.0 if nav == 0 else gross_market_value / nav,
                net_asset_value=nav,
            )
        )
    return performance
