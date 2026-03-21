from __future__ import annotations

import csv
import json
from pathlib import Path

from trotters_trader.config import DataConfig
from trotters_trader.validation import DataValidationError


def summarize_data_coverage(config: DataConfig) -> dict[str, object]:
    expected_source = config.download_instruments_csv or config.source_instruments_csv
    expected_instruments = _load_expected_instruments(expected_source)
    metadata = _load_instrument_metadata(config.source_instruments_csv)

    if config.source_name == "eodhd_json":
        return _summarize_eodhd_raw(config, expected_instruments, metadata)
    if config.source_name == "alpha_vantage_json":
        return _summarize_alpha_vantage_raw(config, expected_instruments, metadata)

    canonical_bars = config.canonical_dir / "daily_bars.csv"
    if canonical_bars.exists():
        return _summarize_bar_csv(canonical_bars, expected_instruments, metadata, source_label="canonical")

    staging_bars = config.staging_dir / "daily_bars.csv"
    if staging_bars.exists():
        return _summarize_bar_csv(staging_bars, expected_instruments, metadata, source_label="staging")

    raise DataValidationError(
        "no coverage source available; generate raw, staging, or canonical bars before auditing coverage"
    )


def write_coverage_artifacts(
    summary: dict[str, object],
    output_dir: str | Path = "data/coverage",
    report_name: str = "coverage",
) -> dict[str, str]:
    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    json_path = base_dir / f"{report_name}_summary.json"
    csv_path = base_dir / f"{report_name}_missing.csv"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_missing_instruments(csv_path, summary.get("missing_instruments", []))

    return {
        "summary_json": str(json_path),
        "missing_csv": str(csv_path),
    }


def _load_expected_instruments(instruments_csv: Path) -> list[str]:
    with instruments_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row["instrument"] for row in reader if row.get("instrument")]


def _load_instrument_metadata(instruments_csv: Path) -> dict[str, dict[str, str]]:
    if not instruments_csv.exists():
        return {}
    with instruments_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        metadata: dict[str, dict[str, str]] = {}
        for row in reader:
            instrument = row.get("instrument")
            if not instrument:
                continue
            metadata[instrument] = {
                "status": row.get("status", "") or "",
                "listing_date": row.get("listing_date", "") or "",
                "delisting_date": row.get("delisting_date", "") or "",
                "sector": row.get("sector", "") or "",
                "industry": row.get("industry", "") or "",
                "benchmark_bucket": row.get("benchmark_bucket", "") or "",
                "liquidity_bucket": row.get("liquidity_bucket", "") or "",
                "tradability_status": row.get("tradability_status", "") or "",
                "universe_bucket": row.get("universe_bucket", "") or "",
            }
        return metadata


def _summarize_eodhd_raw(
    config: DataConfig,
    expected_instruments: list[str],
    metadata: dict[str, dict[str, str]],
) -> dict[str, object]:
    raw_dir = config.raw_dir / "eodhd_json"
    per_instrument: dict[str, dict[str, object]] = {}
    for instrument in expected_instruments:
        json_path = raw_dir / f"{instrument}.json"
        if not json_path.exists():
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue
        dates = sorted(str(row["date"]) for row in payload if isinstance(row, dict) and row.get("date"))
        if not dates:
            continue
        per_instrument[instrument] = {
            "rows": len(dates),
            "start_date": dates[0],
            "end_date": dates[-1],
        }

    return _coverage_payload("raw_eodhd_json", raw_dir, expected_instruments, per_instrument, metadata)


def _summarize_alpha_vantage_raw(
    config: DataConfig,
    expected_instruments: list[str],
    metadata: dict[str, dict[str, str]],
) -> dict[str, object]:
    raw_dir = config.raw_dir / "alpha_vantage_json"
    per_instrument: dict[str, dict[str, object]] = {}
    for instrument in expected_instruments:
        json_path = raw_dir / f"{instrument}.json"
        if not json_path.exists():
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        series = payload.get("Time Series (Daily)") or payload.get("Time Series (Daily) Adjusted")
        if not isinstance(series, dict):
            continue
        dates = sorted(str(key) for key in series.keys())
        if not dates:
            continue
        per_instrument[instrument] = {
            "rows": len(dates),
            "start_date": dates[0],
            "end_date": dates[-1],
        }

    return _coverage_payload("raw_alpha_vantage_json", raw_dir, expected_instruments, per_instrument, metadata)


def _summarize_bar_csv(
    bars_path: Path,
    expected_instruments: list[str],
    metadata: dict[str, dict[str, str]],
    source_label: str,
) -> dict[str, object]:
    per_instrument: dict[str, dict[str, object]] = {}
    with bars_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            instrument = row["instrument"]
            trade_date = row["trade_date"]
            summary = per_instrument.setdefault(
                instrument,
                {"rows": 0, "start_date": trade_date, "end_date": trade_date},
            )
            summary["rows"] = int(summary["rows"]) + 1
            if trade_date < str(summary["start_date"]):
                summary["start_date"] = trade_date
            if trade_date > str(summary["end_date"]):
                summary["end_date"] = trade_date

    return _coverage_payload(source_label, bars_path, expected_instruments, per_instrument, metadata)


def _coverage_payload(
    source_label: str,
    source_path: Path,
    expected_instruments: list[str],
    per_instrument: dict[str, dict[str, object]],
    metadata: dict[str, dict[str, str]],
) -> dict[str, object]:
    expected_set = set(expected_instruments)
    covered = sorted(per_instrument.keys())
    covered_set = set(covered)
    missing = sorted(expected_set - covered_set)
    row_count = sum(int(item["rows"]) for item in per_instrument.values())

    earliest = min((str(item["start_date"]) for item in per_instrument.values()), default=None)
    latest = max((str(item["end_date"]) for item in per_instrument.values()), default=None)

    return {
        "source": source_label,
        "path": str(source_path),
        "expected_instruments": len(expected_instruments),
        "covered_instruments": len(covered),
        "missing_instruments": missing,
        "coverage_ratio": (len(covered) / len(expected_instruments)) if expected_instruments else 0.0,
        "total_rows": row_count,
        "earliest_date": earliest,
        "latest_date": latest,
        "per_instrument": {instrument: per_instrument[instrument] for instrument in covered},
        "metadata_counts": _metadata_counts(expected_instruments, metadata),
        "metadata_gaps": _metadata_gaps(expected_instruments, metadata),
    }


def _metadata_counts(
    expected_instruments: list[str],
    metadata: dict[str, dict[str, str]],
) -> dict[str, dict[str, int]]:
    counts = {
        "status": {},
        "sector": {},
        "industry": {},
        "benchmark_bucket": {},
        "liquidity_bucket": {},
        "tradability_status": {},
        "universe_bucket": {},
    }
    for instrument in expected_instruments:
        instrument_metadata = metadata.get(instrument, {})
        for key in counts:
            value = str(instrument_metadata.get(key, "") or "UNSPECIFIED")
            counts[key][value] = counts[key].get(value, 0) + 1
    return counts


def _metadata_gaps(
    expected_instruments: list[str],
    metadata: dict[str, dict[str, str]],
) -> dict[str, object]:
    fields = [
        "benchmark_bucket",
        "liquidity_bucket",
        "tradability_status",
        "universe_bucket",
        "listing_date",
    ]
    missing_by_field: dict[str, list[str]] = {}
    for field in fields:
        missing = [
            instrument
            for instrument in expected_instruments
            if not str(metadata.get(instrument, {}).get(field, "") or "").strip()
        ]
        missing_by_field[field] = missing
    delisted_missing_date = [
        instrument
        for instrument in expected_instruments
        if str(metadata.get(instrument, {}).get("status", "") or "") == "DELISTED"
        and not str(metadata.get(instrument, {}).get("delisting_date", "") or "").strip()
    ]
    return {
        "missing_counts": {field: len(values) for field, values in missing_by_field.items()},
        "missing_examples": {field: values[:10] for field, values in missing_by_field.items() if values},
        "delisted_missing_delisting_date": delisted_missing_date,
    }


def _write_missing_instruments(path: Path, missing_instruments: object) -> None:
    instruments = missing_instruments if isinstance(missing_instruments, list) else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["instrument"])
        writer.writeheader()
        for instrument in instruments:
            writer.writerow({"instrument": instrument})
