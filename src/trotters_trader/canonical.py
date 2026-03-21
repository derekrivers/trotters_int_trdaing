from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path

from trotters_trader.config import DataConfig
from trotters_trader.data import load_corporate_actions, load_daily_bars, load_instruments
from trotters_trader.domain import CorporateAction, DailyBar, Instrument
from trotters_trader.staging import stage_source_data
from trotters_trader.validation import validate_market_data


def materialize_canonical_data(config: DataConfig) -> dict[str, str]:
    stage_targets = stage_source_data(config)
    config.canonical_dir.mkdir(parents=True, exist_ok=True)

    bars = load_daily_bars(config.staging_dir / "daily_bars.csv")
    instruments = load_instruments(config.staging_dir / "instruments.csv")
    corporate_actions = load_corporate_actions(config.staging_dir / "corporate_actions.csv")
    bars = _apply_adjustment_policy(bars, corporate_actions, config.adjustment_policy)
    validate_market_data(bars, instruments, corporate_actions)

    canonical_targets = {
        "bars": _write_daily_bars(config.canonical_dir / "daily_bars.csv", bars),
        "instruments": _write_instruments(config.canonical_dir / "instruments.csv", instruments),
        "corporate_actions": _write_corporate_actions(
            config.canonical_dir / "corporate_actions.csv",
            corporate_actions,
        ),
        "manifest": _write_manifest(config.canonical_dir / "dataset_manifest.json", config),
    }

    return {**stage_targets, **canonical_targets}


def _write_daily_bars(path: Path, bars_by_instrument: dict[str, list[DailyBar]]) -> str:
    fieldnames = ["trade_date", "instrument", "open", "high", "low", "close", "adjusted_close", "volume"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for instrument in sorted(bars_by_instrument):
            for bar in bars_by_instrument[instrument]:
                writer.writerow(asdict(bar))
    return str(path)


def _apply_adjustment_policy(
    bars_by_instrument: dict[str, list[DailyBar]],
    actions_by_instrument: dict[str, list[CorporateAction]],
    adjustment_policy: str,
) -> dict[str, list[DailyBar]]:
    if adjustment_policy == "vendor_adjusted_close":
        return bars_by_instrument
    if adjustment_policy == "raw_close":
        return {
            instrument: [
                DailyBar(
                    trade_date=bar.trade_date,
                    instrument=bar.instrument,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    adjusted_close=bar.close,
                    volume=bar.volume,
                )
                for bar in bars
            ]
            for instrument, bars in bars_by_instrument.items()
        }
    if adjustment_policy == "dividends_from_actions":
        return _apply_corporate_action_adjustments(
            bars_by_instrument,
            actions_by_instrument,
            include_splits=False,
        )
    if adjustment_policy == "splits_and_dividends_from_actions":
        return _apply_corporate_action_adjustments(
            bars_by_instrument,
            actions_by_instrument,
            include_splits=True,
        )
    raise ValueError(f"unsupported adjustment_policy '{adjustment_policy}'")


def _apply_corporate_action_adjustments(
    bars_by_instrument: dict[str, list[DailyBar]],
    actions_by_instrument: dict[str, list[CorporateAction]],
    include_splits: bool,
) -> dict[str, list[DailyBar]]:
    adjusted: dict[str, list[DailyBar]] = {}

    for instrument, bars in bars_by_instrument.items():
        actions_by_date: dict[object, list[CorporateAction]] = {}
        for action in actions_by_instrument.get(instrument, []):
            actions_by_date.setdefault(action.ex_date, []).append(action)
        cumulative_factor = 1.0
        adjusted_reversed: list[DailyBar] = []

        for bar in reversed(bars):
            for action in actions_by_date.get(bar.trade_date, []):
                if action.action_type == "DIVIDEND" and bar.close > 0:
                    ratio = max((bar.close - action.ratio_or_amount) / bar.close, 0.0)
                    cumulative_factor *= ratio
                elif include_splits and action.action_type == "SPLIT" and action.ratio_or_amount > 0:
                    cumulative_factor /= action.ratio_or_amount

            adjusted_reversed.append(
                DailyBar(
                    trade_date=bar.trade_date,
                    instrument=bar.instrument,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    adjusted_close=bar.close * cumulative_factor,
                    volume=bar.volume,
                )
            )

        adjusted[instrument] = list(reversed(adjusted_reversed))

    return adjusted


def _write_instruments(path: Path, instruments: dict[str, Instrument]) -> str:
    fieldnames = [
        "instrument",
        "exchange_mic",
        "currency",
        "isin",
        "sedol",
        "company_number",
        "status",
        "listing_date",
        "delisting_date",
        "sector",
        "industry",
        "benchmark_bucket",
        "liquidity_bucket",
        "tradability_status",
        "universe_bucket",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for instrument in sorted(instruments):
            writer.writerow(asdict(instruments[instrument]))
    return str(path)


def _write_corporate_actions(
    path: Path,
    actions_by_instrument: dict[str, list[CorporateAction]],
) -> str:
    fieldnames = [
        "instrument",
        "action_type",
        "ex_date",
        "record_date",
        "payable_date",
        "ratio_or_amount",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for instrument in sorted(actions_by_instrument):
            for action in actions_by_instrument[instrument]:
                writer.writerow(asdict(action))
    return str(path)


def _write_manifest(path: Path, config: DataConfig) -> str:
    manifest = {
        "source_name": config.source_name,
        "adjustment_policy": config.adjustment_policy,
        "field_semantics": {
            "open": "raw",
            "high": "raw",
            "low": "raw",
            "close": "raw",
            "adjusted_close": _adjusted_close_semantics(config.adjustment_policy),
            "volume": "raw",
        },
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return str(path)


def _adjusted_close_semantics(adjustment_policy: str) -> str:
    if adjustment_policy == "vendor_adjusted_close":
        return "vendor_adjusted_close"
    if adjustment_policy == "raw_close":
        return "raw_close"
    if adjustment_policy == "dividends_from_actions":
        return "reconstructed_dividend_adjusted_close"
    if adjustment_policy == "splits_and_dividends_from_actions":
        return "reconstructed_split_and_dividend_adjusted_close"
    return "unknown"
