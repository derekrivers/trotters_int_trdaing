from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
from pathlib import Path
import sys

from trotters_trader.domain import CorporateAction, DailyBar, Instrument


csv.field_size_limit(sys.maxsize)


def load_daily_bars(path: str | Path) -> dict[str, list[DailyBar]]:
    bars_by_instrument: dict[str, list[DailyBar]] = defaultdict(list)
    csv_path = Path(path)

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            bar = DailyBar(
                trade_date=date.fromisoformat(row["trade_date"]),
                instrument=row["instrument"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                adjusted_close=float(row.get("adjusted_close") or row["close"]),
                volume=float(row["volume"]),
            )
            bars_by_instrument[bar.instrument].append(bar)

    for instrument in bars_by_instrument:
        bars_by_instrument[instrument].sort(key=lambda item: item.trade_date)

    return dict(bars_by_instrument)


def load_instruments(path: str | Path) -> dict[str, Instrument]:
    csv_path = Path(path)
    instruments: dict[str, Instrument] = {}

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            instrument = Instrument(
                instrument=row["instrument"],
                exchange_mic=row["exchange_mic"],
                currency=row["currency"],
                isin=row["isin"],
                sedol=row["sedol"],
                company_number=row["company_number"],
                status=row["status"],
                listing_date=_optional_date(row.get("listing_date")),
                delisting_date=_optional_date(row.get("delisting_date")),
                sector=(row.get("sector") or "").strip(),
                industry=(row.get("industry") or "").strip(),
                benchmark_bucket=(row.get("benchmark_bucket") or "").strip(),
                liquidity_bucket=(row.get("liquidity_bucket") or "").strip(),
                tradability_status=(row.get("tradability_status") or "").strip(),
                universe_bucket=(row.get("universe_bucket") or "").strip(),
            )
            instruments[instrument.instrument] = instrument

    return instruments


def load_corporate_actions(path: str | Path) -> dict[str, list[CorporateAction]]:
    csv_path = Path(path)
    actions_by_instrument: dict[str, list[CorporateAction]] = defaultdict(list)

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            action = CorporateAction(
                instrument=row["instrument"],
                action_type=row["action_type"],
                ex_date=date.fromisoformat(row["ex_date"]),
                record_date=date.fromisoformat(row["record_date"]),
                payable_date=date.fromisoformat(row["payable_date"]),
                ratio_or_amount=float(row["ratio_or_amount"]),
            )
            actions_by_instrument[action.instrument].append(action)

    for instrument in actions_by_instrument:
        actions_by_instrument[instrument].sort(key=lambda item: item.ex_date)

    return dict(actions_by_instrument)


def trading_calendar(bars_by_instrument: dict[str, list[DailyBar]]) -> list[date]:
    dates = {
        bar.trade_date
        for bars in bars_by_instrument.values()
        for bar in bars
    }
    return sorted(dates)


def _optional_date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(value)
