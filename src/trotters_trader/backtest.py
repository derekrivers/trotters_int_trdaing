from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from trotters_trader.allocator import build_rebalance_orders
from trotters_trader.benchmark import build_benchmarks, equal_weight_lookback_return
from trotters_trader.calendar import TradingCalendar
from trotters_trader.config import AppConfig
from trotters_trader.data import load_daily_bars, load_instruments, trading_calendar
from trotters_trader.domain import DailyBar, PortfolioSnapshot
from trotters_trader.execution import simulate_fill
from trotters_trader.features import ensure_feature_set, feature_store_matches_config, load_feature_store
from trotters_trader.metrics import build_analytics, summarize, write_run_artifacts
from trotters_trader.portfolio import PortfolioState
from trotters_trader.run_metadata import run_metadata
from trotters_trader.strategy import build_strategy, build_target_weights
from trotters_trader.universe import eligible_instruments
from trotters_trader.validation import validate_market_data


@dataclass(frozen=True)
class BacktestResult:
    summary: dict[str, float]
    analytics: dict[str, object]
    results_path: str


def run_backtest(config: AppConfig) -> BacktestResult:
    all_bars_by_instrument = load_daily_bars(config.data.canonical_dir / "daily_bars.csv")
    instruments = load_instruments(config.data.canonical_dir / "instruments.csv")
    validate_market_data(all_bars_by_instrument, instruments, {})
    feature_artifacts = ensure_feature_set(config)
    feature_store = load_feature_store(config) if config.features.enabled and config.features.use_precomputed else None
    if feature_store is not None and not feature_store_matches_config(feature_store, config):
        feature_store = None

    eligibility_bars = _eligibility_bars(all_bars_by_instrument, config.period.start_date)
    allowed = eligible_instruments(
        eligibility_bars,
        instruments,
        config.universe,
        start_date=config.period.start_date,
        end_date=config.period.end_date,
    )
    bars_by_instrument = {
        instrument: bars
        for instrument, bars in all_bars_by_instrument.items()
        if instrument in allowed
    }

    bars_by_instrument = _bars_to_end_date(bars_by_instrument, config.period.end_date)
    calendar = TradingCalendar(tuple(trading_calendar(bars_by_instrument)))
    trading_dates = tuple(_dates_in_period(calendar.dates, config.period.start_date, config.period.end_date))
    strategy = build_strategy(config.strategy)
    portfolio = PortfolioState(cash=config.run.initial_cash)
    fills = []
    performance: list[PortfolioSnapshot] = []
    basket_snapshots: list[dict[str, object]] = []
    benchmark_performance = build_benchmarks(
        _bars_in_period(bars_by_instrument, config.period.start_date, config.period.end_date),
        config.run.initial_cash,
        config.benchmark,
    )

    bars_lookup = _bars_lookup_by_date(bars_by_instrument)
    peak_nav = config.run.initial_cash
    prior_drawdown = 0.0
    prior_benchmark_regime_active = False

    for day_index, trade_date in enumerate(trading_dates):
        portfolio.advance_holding_days()
        next_trade_date = calendar.next_date(trade_date)
        if next_trade_date is None or (
            config.period.end_date is not None and next_trade_date > config.period.end_date
        ):
            performance.append(_snapshot(trade_date, portfolio, bars_lookup))
            break

        visible_history = _history_to_date(bars_by_instrument, trade_date)
        current_nav = _portfolio_nav(portfolio, bars_lookup.get(trade_date, {}))
        peak_nav = max(peak_nav, current_nav)
        current_drawdown = _current_drawdown(current_nav, peak_nav)
        effective_portfolio_config = _apply_drawdown_overlay(
            config.portfolio,
            current_drawdown,
        )
        benchmark_regime_active = _benchmark_regime_active(
            visible_history,
            effective_portfolio_config,
        )
        effective_portfolio_config = _apply_benchmark_regime_overlay(
            effective_portfolio_config,
            benchmark_regime_active,
        )
        feature_snapshot = None
        if feature_store is not None:
            feature_snapshot = feature_store.snapshot(trade_date.isoformat())
        scores = strategy.score(visible_history, feature_snapshot=feature_snapshot)
        target_weights = build_target_weights(
            scores,
            visible_history,
            config.strategy,
            instruments=instruments,
            current_holdings=set(portfolio.positions),
            holding_days=portfolio.holding_days,
            selection_buffer_slots=config.portfolio.selection_buffer_slots,
            max_positions_per_sector=config.portfolio.max_positions_per_sector,
            max_positions_per_industry=config.portfolio.max_positions_per_industry,
            max_positions_per_benchmark_bucket=config.portfolio.max_positions_per_benchmark_bucket,
            min_holding_days=config.portfolio.min_holding_days,
        )
        next_day_bars = bars_lookup[next_trade_date]

        orders = []
        should_rebalance = day_index % max(config.portfolio.rebalance_frequency_days, 1) == 0
        drawdown_breach = (
            effective_portfolio_config.drawdown_force_rebalance
            and effective_portfolio_config.drawdown_reduce_threshold > 0
            and prior_drawdown < effective_portfolio_config.drawdown_reduce_threshold <= current_drawdown
        )
        if drawdown_breach:
            should_rebalance = True
        if (
            effective_portfolio_config.benchmark_regime_force_rebalance
            and benchmark_regime_active
            and not prior_benchmark_regime_active
        ):
            should_rebalance = True

        if should_rebalance:
            orders = build_rebalance_orders(
                portfolio=portfolio,
                target_weights=target_weights,
                prices=next_day_bars,
                history_by_instrument=visible_history,
                config=effective_portfolio_config,
            )

        for order in orders:
            next_bar = next_day_bars[order.instrument]
            fill = simulate_fill(order, next_bar, config.execution)
            if fill is None:
                continue
            portfolio.apply_fill(fill)
            fills.append(fill)

        performance.append(_snapshot(trade_date, portfolio, bars_lookup))
        basket_snapshots.append(_basket_snapshot(trade_date, portfolio, bars_lookup.get(trade_date, {}), instruments))
        prior_drawdown = current_drawdown
        prior_benchmark_regime_active = benchmark_regime_active

    summary = summarize(performance, fills, portfolio.closed_trades)
    analytics = build_analytics(
        performance,
        fills,
        portfolio.closed_trades,
        benchmark_performance,
        config.benchmark.primary,
        config.evaluation,
        instruments=instruments,
        basket_snapshots=basket_snapshots,
    )
    analytics["run_metadata"] = run_metadata(
        config.run.name,
        default_strategy_family=config.strategy.name,
        research_tranche=config.research.research_tranche,
        research_slice_name=config.research.research_slice_name,
        ranking_mode=config.strategy.ranking_mode,
        score_transform=config.strategy.score_transform,
        control_profile=config.research.control_profile,
        promotion_candidate=config.research.promotion_candidate,
    )
    analytics["period"] = {
        "label": config.period.label,
        "start_date": None if config.period.start_date is None else config.period.start_date.isoformat(),
        "end_date": None if config.period.end_date is None else config.period.end_date.isoformat(),
        "trading_days": len(trading_dates),
    }
    analytics["research"] = {
        "profile_name": config.research.profile_name,
        "profile_version": config.research.profile_version,
        "frozen_on": None if config.research.frozen_on is None else config.research.frozen_on.isoformat(),
        "promoted": config.research.promoted,
        "research_tranche": config.research.research_tranche,
        "research_slice_name": config.research.research_slice_name,
        "control_profile": config.research.control_profile,
        "promotion_candidate": config.research.promotion_candidate,
    }
    analytics["data_policy"] = {
        "source_name": config.data.source_name,
        "adjustment_policy": config.data.adjustment_policy,
        "signal_price_field": "adjusted_close",
        "execution_price_field": "raw_ohlc_next_open",
    }
    analytics["features"] = {
        "enabled": config.features.enabled,
        "set_name": config.features.set_name,
        "used_precomputed": feature_store is not None,
        "feature_artifacts": feature_artifacts or {},
    }
    analytics["universe_lifecycle"] = _universe_lifecycle_summary(allowed)
    results_path = write_run_artifacts(
        output_dir=config.run.output_dir,
        run_name=config.run.name,
        summary=summary,
        analytics=analytics,
        fills=fills,
        performance=performance,
    )
    return BacktestResult(summary=summary, analytics=analytics, results_path=str(results_path))


def _bars_lookup_by_date(
    bars_by_instrument: dict[str, list[DailyBar]],
) -> dict[date, dict[str, DailyBar]]:
    lookup: dict[date, dict[str, DailyBar]] = {}
    for instrument, bars in bars_by_instrument.items():
        for bar in bars:
            lookup.setdefault(bar.trade_date, {})[instrument] = bar
    return lookup


def _history_to_date(
    bars_by_instrument: dict[str, list[DailyBar]],
    trade_date: date,
) -> dict[str, list[DailyBar]]:
    history: dict[str, list[DailyBar]] = {}
    for instrument, bars in bars_by_instrument.items():
        history[instrument] = [bar for bar in bars if bar.trade_date <= trade_date]
    return history


def _bars_to_end_date(
    bars_by_instrument: dict[str, list[DailyBar]],
    end_date: date | None,
) -> dict[str, list[DailyBar]]:
    if end_date is None:
        return bars_by_instrument
    return {
        instrument: [bar for bar in bars if bar.trade_date <= end_date]
        for instrument, bars in bars_by_instrument.items()
    }


def _bars_in_period(
    bars_by_instrument: dict[str, list[DailyBar]],
    start_date: date | None,
    end_date: date | None,
) -> dict[str, list[DailyBar]]:
    return {
        instrument: [
            bar
            for bar in bars
            if (start_date is None or bar.trade_date >= start_date)
            and (end_date is None or bar.trade_date <= end_date)
        ]
        for instrument, bars in bars_by_instrument.items()
    }


def _eligibility_bars(
    bars_by_instrument: dict[str, list[DailyBar]],
    start_date: date | None,
) -> dict[str, list[DailyBar]]:
    if start_date is None:
        return bars_by_instrument
    return {
        instrument: [bar for bar in bars if bar.trade_date < start_date]
        for instrument, bars in bars_by_instrument.items()
    }


def _dates_in_period(
    dates: tuple[date, ...],
    start_date: date | None,
    end_date: date | None,
) -> list[date]:
    return [
        trade_date
        for trade_date in dates
        if (start_date is None or trade_date >= start_date)
        and (end_date is None or trade_date <= end_date)
    ]


def _portfolio_nav(portfolio: PortfolioState, prices: dict[str, DailyBar]) -> float:
    gross_market_value = 0.0
    for instrument, quantity in portfolio.positions.items():
        bar = prices.get(instrument)
        if bar is None:
            continue
        gross_market_value += quantity * bar.close
    return portfolio.cash + gross_market_value


def _snapshot(
    trade_date: date,
    portfolio: PortfolioState,
    bars_lookup: dict[date, dict[str, DailyBar]],
) -> PortfolioSnapshot:
    prices = bars_lookup.get(trade_date, {})
    gross_market_value = 0.0
    for instrument, quantity in portfolio.positions.items():
        bar = prices.get(instrument)
        if bar is None:
            continue
        gross_market_value += quantity * bar.close

    return PortfolioSnapshot(
        trade_date=trade_date,
        cash=portfolio.cash,
        gross_market_value=gross_market_value,
        gross_exposure_ratio=0.0 if (portfolio.cash + gross_market_value) == 0 else gross_market_value / (portfolio.cash + gross_market_value),
        net_asset_value=portfolio.cash + gross_market_value,
    )


def _basket_snapshot(
    trade_date: date,
    portfolio: PortfolioState,
    prices: dict[str, DailyBar],
    instruments: dict[str, object],
) -> dict[str, object]:
    nav = _portfolio_nav(portfolio, prices)
    if nav <= 0:
        return {
            "trade_date": trade_date,
            "portfolio_names": 0,
            "unique_sectors": 0,
            "unique_industries": 0,
            "sector_concentration": 0.0,
            "industry_concentration": 0.0,
            "benchmark_bucket_concentration": 0.0,
            "active_sector_deviation": 0.0,
            "active_benchmark_bucket_deviation": 0.0,
        }

    portfolio_weights = _portfolio_metadata_weights(portfolio, prices, instruments, nav)
    benchmark_weights = _equal_weight_metadata_weights(prices, instruments)
    return {
        "trade_date": trade_date,
        "portfolio_names": len([instrument for instrument, quantity in portfolio.positions.items() if quantity > 0]),
        "unique_sectors": len(portfolio_weights["sector"]),
        "unique_industries": len(portfolio_weights["industry"]),
        "sector_concentration": _max_weight(portfolio_weights["sector"]),
        "industry_concentration": _max_weight(portfolio_weights["industry"]),
        "benchmark_bucket_concentration": _max_weight(portfolio_weights["benchmark_bucket"]),
        "active_sector_deviation": _active_deviation(portfolio_weights["sector"], benchmark_weights["sector"]),
        "active_benchmark_bucket_deviation": _active_deviation(
            portfolio_weights["benchmark_bucket"],
            benchmark_weights["benchmark_bucket"],
        ),
    }


def _portfolio_metadata_weights(
    portfolio: PortfolioState,
    prices: dict[str, DailyBar],
    instruments: dict[str, object],
    nav: float,
) -> dict[str, dict[str, float]]:
    grouped = {"sector": {}, "industry": {}, "benchmark_bucket": {}, "liquidity_bucket": {}}
    for instrument, quantity in portfolio.positions.items():
        if quantity <= 0:
            continue
        bar = prices.get(instrument)
        metadata = instruments.get(instrument)
        if bar is None or metadata is None:
            continue
        weight = (quantity * bar.close) / nav if nav > 0 else 0.0
        for attribute in grouped:
            value = str(getattr(metadata, attribute, "") or "UNSPECIFIED")
            grouped[attribute][value] = grouped[attribute].get(value, 0.0) + weight
    return grouped


def _equal_weight_metadata_weights(
    prices: dict[str, DailyBar],
    instruments: dict[str, object],
) -> dict[str, dict[str, float]]:
    grouped = {"sector": {}, "industry": {}, "benchmark_bucket": {}, "liquidity_bucket": {}}
    names = [instrument for instrument in prices if instrument in instruments]
    if not names:
        return grouped
    weight = 1.0 / len(names)
    for instrument in names:
        metadata = instruments[instrument]
        for attribute in grouped:
            value = str(getattr(metadata, attribute, "") or "UNSPECIFIED")
            grouped[attribute][value] = grouped[attribute].get(value, 0.0) + weight
    return grouped


def _max_weight(weights: dict[str, float]) -> float:
    return max(weights.values(), default=0.0)


def _active_deviation(
    portfolio_weights: dict[str, float],
    benchmark_weights: dict[str, float],
) -> float:
    keys = set(portfolio_weights) | set(benchmark_weights)
    return sum(abs(portfolio_weights.get(key, 0.0) - benchmark_weights.get(key, 0.0)) for key in keys) / 2.0


def _current_drawdown(current_nav: float, peak_nav: float) -> float:
    if peak_nav <= 0:
        return 0.0
    return max(0.0, (peak_nav - current_nav) / peak_nav)


def _apply_drawdown_overlay(config: AppConfig | object, current_drawdown: float) -> object:
    portfolio_config = config
    if not hasattr(portfolio_config, "drawdown_reduce_threshold"):
        return portfolio_config
    threshold = float(getattr(portfolio_config, "drawdown_reduce_threshold", 0.0) or 0.0)
    reduced_exposure = float(getattr(portfolio_config, "drawdown_reduced_gross_exposure", 0.0) or 0.0)
    if threshold <= 0 or reduced_exposure <= 0 or current_drawdown < threshold:
        return portfolio_config
    return replace(
        portfolio_config,
        target_gross_exposure=min(float(getattr(portfolio_config, "target_gross_exposure", 0.0)), reduced_exposure),
    )


def _universe_lifecycle_summary(instruments: dict[str, object]) -> dict[str, int]:
    counts = {"ACTIVE": 0, "INACTIVE": 0, "DELISTED": 0, "OTHER": 0}
    for metadata in instruments.values():
        status = str(getattr(metadata, "status", "") or "OTHER")
        if status not in counts:
            counts["OTHER"] += 1
        else:
            counts[status] += 1
    return counts


def _benchmark_regime_active(
    history_by_instrument: dict[str, list[DailyBar]],
    portfolio_config: AppConfig | object,
) -> bool:
    lookback_days = int(getattr(portfolio_config, "benchmark_regime_window_days", 0) or 0)
    reduced_exposure = float(getattr(portfolio_config, "benchmark_regime_reduced_gross_exposure", 0.0) or 0.0)
    if lookback_days <= 0 or reduced_exposure <= 0:
        return False
    lookback_return = equal_weight_lookback_return(history_by_instrument, lookback_days)
    if lookback_return is None:
        return False
    min_return = float(getattr(portfolio_config, "benchmark_regime_min_return", 0.0) or 0.0)
    return lookback_return < min_return


def _apply_benchmark_regime_overlay(config: AppConfig | object, regime_active: bool) -> object:
    portfolio_config = config
    if not regime_active:
        return portfolio_config
    reduced_exposure = float(getattr(portfolio_config, "benchmark_regime_reduced_gross_exposure", 0.0) or 0.0)
    if reduced_exposure <= 0:
        return portfolio_config
    return replace(
        portfolio_config,
        target_gross_exposure=min(float(getattr(portfolio_config, "target_gross_exposure", 0.0)), reduced_exposure),
    )
