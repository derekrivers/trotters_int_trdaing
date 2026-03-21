from __future__ import annotations

from collections import defaultdict

from trotters_trader.domain import CorporateAction, DailyBar, Instrument


class DataValidationError(ValueError):
    pass


def validate_market_data(
    bars_by_instrument: dict[str, list[DailyBar]],
    instruments: dict[str, Instrument],
    corporate_actions: dict[str, list[CorporateAction]],
) -> None:
    _validate_instruments(instruments)
    _validate_instrument_links(bars_by_instrument, instruments, "bars")
    _validate_instrument_links(corporate_actions, instruments, "corporate actions")
    _validate_daily_bars(bars_by_instrument, instruments)
    _validate_corporate_actions(corporate_actions, instruments)


def _validate_instrument_links(
    rows_by_instrument: dict[str, list[object]],
    instruments: dict[str, Instrument],
    label: str,
) -> None:
    missing = sorted(instrument for instrument in rows_by_instrument if instrument not in instruments)
    if missing:
        raise DataValidationError(
            f"{label} reference instruments missing from instrument master: {', '.join(missing)}"
        )


def _validate_instruments(instruments: dict[str, Instrument]) -> None:
    for instrument, metadata in instruments.items():
        if metadata.listing_date and metadata.delisting_date and metadata.listing_date > metadata.delisting_date:
            raise DataValidationError(f"{instrument} has listing_date after delisting_date")
        if metadata.status == "DELISTED" and metadata.delisting_date is None:
            raise DataValidationError(f"{instrument} is DELISTED but missing delisting_date")


def _validate_daily_bars(
    bars_by_instrument: dict[str, list[DailyBar]],
    instruments: dict[str, Instrument],
) -> None:
    duplicates: dict[str, set[str]] = defaultdict(set)

    for instrument, bars in bars_by_instrument.items():
        metadata = instruments[instrument]
        seen_dates: set[str] = set()
        previous_date = None
        for bar in bars:
            date_key = bar.trade_date.isoformat()
            if date_key in seen_dates:
                duplicates[instrument].add(date_key)
            seen_dates.add(date_key)

            if previous_date is not None and bar.trade_date <= previous_date:
                raise DataValidationError(f"bars for {instrument} are not strictly increasing by date")
            previous_date = bar.trade_date

            if metadata.listing_date is not None and bar.trade_date < metadata.listing_date:
                raise DataValidationError(f"bar for {instrument} predates listing_date on {date_key}")
            if metadata.delisting_date is not None and bar.trade_date > metadata.delisting_date:
                raise DataValidationError(f"bar for {instrument} extends beyond delisting_date on {date_key}")

            if min(bar.open, bar.high, bar.low, bar.close, bar.adjusted_close) <= 0:
                raise DataValidationError(f"non-positive price detected for {instrument} on {date_key}")
            if bar.high < max(bar.open, bar.close, bar.low):
                raise DataValidationError(f"high price is inconsistent for {instrument} on {date_key}")
            if bar.low > min(bar.open, bar.close, bar.high):
                raise DataValidationError(f"low price is inconsistent for {instrument} on {date_key}")
            if bar.volume < 0:
                raise DataValidationError(f"negative volume detected for {instrument} on {date_key}")

    if duplicates:
        duplicate_summary = ", ".join(
            f"{instrument}: {sorted(values)}" for instrument, values in sorted(duplicates.items())
        )
        raise DataValidationError(f"duplicate bars detected: {duplicate_summary}")


def _validate_corporate_actions(
    actions_by_instrument: dict[str, list[CorporateAction]],
    instruments: dict[str, Instrument],
) -> None:
    for instrument, actions in actions_by_instrument.items():
        metadata = instruments[instrument]
        for action in actions:
            if metadata.listing_date is not None and action.ex_date < metadata.listing_date:
                raise DataValidationError(
                    f"corporate action for {instrument} predates listing_date on {action.ex_date.isoformat()}"
                )
            if metadata.delisting_date is not None and action.ex_date > metadata.delisting_date:
                raise DataValidationError(
                    f"corporate action for {instrument} extends beyond delisting_date on {action.ex_date.isoformat()}"
                )
