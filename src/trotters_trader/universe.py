from __future__ import annotations

from trotters_trader.config import UniverseConfig
from trotters_trader.domain import DailyBar, Instrument


def eligible_instruments(
    bars_by_instrument: dict[str, list[DailyBar]],
    instruments: dict[str, Instrument],
    config: UniverseConfig,
    start_date=None,
    end_date=None,
) -> dict[str, Instrument]:
    eligible: dict[str, Instrument] = {}

    for instrument, metadata in instruments.items():
        if config.active_only and not _active_during_period(metadata, start_date, end_date):
            continue
        if metadata.exchange_mic not in config.allowed_exchange_mic:
            continue
        if metadata.currency != config.allowed_currency:
            continue
        if config.allowed_benchmark_buckets and metadata.benchmark_bucket not in config.allowed_benchmark_buckets:
            continue
        if config.allowed_tradability_statuses:
            tradability_status = metadata.tradability_status or "TRADABLE"
            if tradability_status not in config.allowed_tradability_statuses:
                continue
        if config.allowed_universe_buckets and metadata.universe_bucket not in config.allowed_universe_buckets:
            continue
        if config.excluded_liquidity_buckets and metadata.liquidity_bucket in config.excluded_liquidity_buckets:
            continue

        bars = bars_by_instrument.get(instrument, [])
        if len(bars) < config.min_history_days:
            continue

        average_volume = sum(bar.volume for bar in bars) / len(bars) if bars else 0.0
        if average_volume < config.min_average_volume:
            continue

        eligible[instrument] = metadata

    return eligible


def _active_during_period(
    instrument: Instrument,
    start_date,
    end_date,
) -> bool:
    if instrument.status == "INACTIVE":
        return False
    if instrument.listing_date is not None and end_date is not None and instrument.listing_date > end_date:
        return False
    if instrument.delisting_date is not None:
        if start_date is not None and instrument.delisting_date < start_date:
            return False
        if start_date is None and instrument.status == "DELISTED":
            return False
    return True
