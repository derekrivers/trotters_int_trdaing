from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from trotters_trader.config import DataConfig
from trotters_trader.validation import DataValidationError


def stage_source_data(config: DataConfig) -> dict[str, str]:
    config.staging_dir.mkdir(parents=True, exist_ok=True)

    adapter = _adapter(config.source_name)
    return adapter(config)


def _adapter(source_name: str):
    adapters = {
        "bulk_csv": _stage_bulk_csv,
        "alpha_vantage_json": _stage_alpha_vantage_json,
        "eodhd_json": _stage_eodhd_json,
        "sample_csv": _stage_sample_csv,
    }
    if source_name not in adapters:
        raise DataValidationError(
            f"unsupported data source adapter '{source_name}'. Supported adapters: {', '.join(sorted(adapters))}"
        )
    return adapters[source_name]


def _stage_sample_csv(config: DataConfig) -> dict[str, str]:
    _validate_csv_adjustment_policy(config.source_bars_csv, config.adjustment_policy)
    working_raw_dir = _working_raw_dir(config)
    raw_targets = {
        "raw_bars": _copy(config.source_bars_csv, working_raw_dir / "source_daily_bars.csv"),
        "raw_instruments": _copy(config.source_instruments_csv, working_raw_dir / "source_instruments.csv"),
        "raw_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            working_raw_dir / "source_corporate_actions.csv",
        ),
    }

    staging_targets = {
        "staged_bars": _copy(config.source_bars_csv, config.staging_dir / "daily_bars.csv"),
        "staged_instruments": _copy(config.source_instruments_csv, config.staging_dir / "instruments.csv"),
        "staged_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            config.staging_dir / "corporate_actions.csv",
        ),
    }

    return {**raw_targets, **staging_targets}


def _stage_bulk_csv(config: DataConfig) -> dict[str, str]:
    _validate_csv_adjustment_policy(config.source_bars_csv, config.adjustment_policy)
    working_raw_dir = _working_raw_dir(config)
    raw_targets = {
        "raw_bars": _copy(config.source_bars_csv, working_raw_dir / "bulk_daily_bars.csv"),
        "raw_instruments": _copy(config.source_instruments_csv, working_raw_dir / "bulk_instruments.csv"),
        "raw_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            working_raw_dir / "bulk_corporate_actions.csv",
        ),
    }

    staged_bars_path = config.staging_dir / "daily_bars.csv"
    staged_instruments_path = config.staging_dir / "instruments.csv"
    staged_actions_path = config.staging_dir / "corporate_actions.csv"

    _stage_bulk_bars(config.source_bars_csv, staged_bars_path, config.adjustment_policy)
    _stage_bulk_instruments(config.source_instruments_csv, staged_instruments_path)
    _stage_bulk_corporate_actions(config.source_corporate_actions_csv, staged_actions_path)

    return {
        **raw_targets,
        "staged_bars": str(staged_bars_path),
        "staged_instruments": str(staged_instruments_path),
        "staged_corporate_actions": str(staged_actions_path),
    }


def _stage_alpha_vantage_json(config: DataConfig) -> dict[str, str]:
    source_dir = config.source_bars_csv
    if not source_dir.exists() or not source_dir.is_dir():
        raise DataValidationError(
            f"alpha_vantage_json source_bars_csv must point to a directory of raw JSON files: {source_dir}"
        )

    working_raw_dir = _working_raw_dir(config)
    raw_bars_dir = working_raw_dir / "alpha_vantage_json"
    raw_bars_dir.mkdir(parents=True, exist_ok=True)

    allowed_instruments = _instrument_names_from_csv(config.source_instruments_csv)
    json_files = sorted(
        source_file
        for source_file in source_dir.glob("*.json")
        if source_file.stem in allowed_instruments
    )
    if not json_files:
        raise DataValidationError(f"no Alpha Vantage JSON files found in {source_dir}")

    for source_file in json_files:
        _copy(source_file, raw_bars_dir / source_file.name)

    staged_bars_path = config.staging_dir / "daily_bars.csv"
    _write_alpha_vantage_bars(json_files, staged_bars_path, config.adjustment_policy)

    return {
        "raw_bars": str(raw_bars_dir),
        "raw_instruments": _copy(config.source_instruments_csv, working_raw_dir / "source_instruments.csv"),
        "raw_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            working_raw_dir / "source_corporate_actions.csv",
        ),
        "staged_bars": str(staged_bars_path),
        "staged_instruments": _copy(config.source_instruments_csv, config.staging_dir / "instruments.csv"),
        "staged_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            config.staging_dir / "corporate_actions.csv",
        ),
    }


def _stage_eodhd_json(config: DataConfig) -> dict[str, str]:
    source_dir = config.source_bars_csv
    if not source_dir.exists() or not source_dir.is_dir():
        raise DataValidationError(
            f"eodhd_json source_bars_csv must point to a directory of raw JSON files: {source_dir}"
        )

    working_raw_dir = _working_raw_dir(config)
    raw_bars_dir = working_raw_dir / "eodhd_json"
    raw_bars_dir.mkdir(parents=True, exist_ok=True)

    allowed_instruments = _instrument_names_from_csv(config.source_instruments_csv)
    json_files = sorted(
        source_file
        for source_file in source_dir.glob("*.json")
        if source_file.stem in allowed_instruments
    )
    if not json_files:
        raise DataValidationError(f"no EODHD JSON files found in {source_dir}")

    for source_file in json_files:
        _copy(source_file, raw_bars_dir / source_file.name)

    staged_bars_path = config.staging_dir / "daily_bars.csv"
    _write_eodhd_bars(json_files, staged_bars_path, config.adjustment_policy)

    return {
        "raw_bars": str(raw_bars_dir),
        "raw_instruments": _copy(config.source_instruments_csv, working_raw_dir / "source_instruments.csv"),
        "raw_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            working_raw_dir / "source_corporate_actions.csv",
        ),
        "staged_bars": str(staged_bars_path),
        "staged_instruments": _copy(config.source_instruments_csv, config.staging_dir / "instruments.csv"),
        "staged_corporate_actions": _copy(
            config.source_corporate_actions_csv,
            config.staging_dir / "corporate_actions.csv",
        ),
    }


def _copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return str(target)
    shutil.copyfile(source, target)
    return str(target)


def _working_raw_dir(config: DataConfig) -> Path:
    path = config.staging_dir / "_raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_alpha_vantage_bars(json_files: list[Path], target: Path, adjustment_policy: str) -> None:
    fieldnames = ["trade_date", "instrument", "open", "high", "low", "close", "adjusted_close", "volume"]
    rows: list[dict[str, object]] = []

    for json_file in json_files:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        series = payload.get("Time Series (Daily)") or payload.get("Time Series (Daily) Adjusted")
        if not isinstance(series, dict):
            raise DataValidationError(f"Alpha Vantage payload missing daily time series in {json_file}")

        instrument = json_file.stem
        for trade_date, values in series.items():
            if not isinstance(values, dict):
                raise DataValidationError(f"Alpha Vantage row is malformed for {instrument} on {trade_date}")
            rows.append(
                {
                    "trade_date": trade_date,
                    "instrument": instrument,
                    "open": values["1. open"],
                    "high": values["2. high"],
                    "low": values["3. low"],
                    "close": values["4. close"],
                    "adjusted_close": _required_adjusted_close(
                        values.get("5. adjusted close"),
                        values["4. close"],
                        adjustment_policy,
                        instrument,
                        trade_date,
                    ),
                    "volume": values.get("6. volume", values.get("5. volume")),
                }
            )

    rows.sort(key=lambda row: (str(row["instrument"]), str(row["trade_date"])))
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_eodhd_bars(json_files: list[Path], target: Path, adjustment_policy: str) -> None:
    fieldnames = ["trade_date", "instrument", "open", "high", "low", "close", "adjusted_close", "volume"]
    rows: list[dict[str, object]] = []

    for json_file in json_files:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise DataValidationError(f"EODHD payload must be a list in {json_file}")

        instrument = json_file.stem
        for values in payload:
            if not isinstance(values, dict):
                raise DataValidationError(f"EODHD row is malformed for {instrument}")
            rows.append(
                {
                    "trade_date": values["date"],
                    "instrument": instrument,
                    "open": values["open"],
                    "high": values["high"],
                    "low": values["low"],
                    "close": values["close"],
                    "adjusted_close": _required_adjusted_close(
                        values.get("adjusted_close"),
                        values["close"],
                        adjustment_policy,
                        instrument,
                        str(values["date"]),
                    ),
                    "volume": values["volume"],
                }
            )

    rows.sort(key=lambda row: (str(row["instrument"]), str(row["trade_date"])))
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _stage_bulk_bars(source: Path, target: Path, adjustment_policy: str) -> None:
    required = {"trade_date", "instrument", "open", "high", "low", "close", "volume"}
    optional = {"adjusted_close"}
    rows = _read_csv_rows(source, required, optional)
    if adjustment_policy == "vendor_adjusted_close" and "adjusted_close" not in _csv_header(source):
        raise DataValidationError(
            f"{source} does not provide adjusted_close but adjustment_policy is vendor_adjusted_close"
        )

    fieldnames = ["trade_date", "instrument", "open", "high", "low", "close", "adjusted_close", "volume"]
    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        normalized_rows.append(
            {
                "trade_date": row["trade_date"],
                "instrument": row["instrument"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "adjusted_close": row.get("adjusted_close") or row["close"],
                "volume": row["volume"],
            }
        )

    _write_csv(target, fieldnames, normalized_rows)


def _stage_bulk_instruments(source: Path, target: Path) -> None:
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
    required_fields = {
        "instrument",
        "exchange_mic",
        "currency",
        "isin",
        "sedol",
        "company_number",
        "status",
    }
    optional_fields = {
        "listing_date",
        "delisting_date",
        "sector",
        "industry",
        "benchmark_bucket",
        "liquidity_bucket",
        "tradability_status",
        "universe_bucket",
    }
    rows = _read_csv_rows(source, required_fields, optional_fields)
    normalized_rows = [{field: row.get(field, "") for field in fieldnames} for row in rows]
    _write_csv(target, fieldnames, normalized_rows)


def _stage_bulk_corporate_actions(source: Path, target: Path) -> None:
    fieldnames = [
        "instrument",
        "action_type",
        "ex_date",
        "record_date",
        "payable_date",
        "ratio_or_amount",
    ]
    rows = _read_csv_rows(source, set(fieldnames))
    normalized_rows = [{field: row[field] for field in fieldnames} for row in rows]
    _write_csv(target, fieldnames, normalized_rows)


def _read_csv_rows(
    source: Path,
    required_fields: set[str],
    optional_fields: set[str] | None = None,
) -> list[dict[str, str]]:
    if not source.exists() or not source.is_file():
        raise DataValidationError(f"expected CSV source file does not exist: {source}")

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = set(reader.fieldnames or [])
        missing = sorted(required_fields - header)
        if missing:
            raise DataValidationError(f"{source} is missing required columns: {', '.join(missing)}")

        allowed_fields = required_fields | (optional_fields or set())
        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=2):
            normalized_row: dict[str, str] = {}
            for field in allowed_fields:
                normalized_row[field] = (row.get(field) or "").strip()
            missing_values = sorted(field for field in required_fields if not normalized_row[field])
            if missing_values:
                raise DataValidationError(
                    f"{source} row {index} has blank required values: {', '.join(missing_values)}"
                )
            rows.append(normalized_row)

    return rows


def _write_csv(target: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _validate_csv_adjustment_policy(source: Path, adjustment_policy: str) -> None:
    if adjustment_policy != "vendor_adjusted_close":
        return
    header = _csv_header(source)
    if "adjusted_close" not in header:
        raise DataValidationError(
            f"{source} does not provide adjusted_close but adjustment_policy is vendor_adjusted_close"
        )


def _csv_header(source: Path) -> set[str]:
    if not source.exists() or not source.is_file():
        raise DataValidationError(f"expected CSV source file does not exist: {source}")
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return set(reader.fieldnames or [])


def _required_adjusted_close(
    adjusted_value: object,
    close_value: object,
    adjustment_policy: str,
    instrument: str,
    trade_date: str,
) -> object:
    if adjusted_value not in (None, ""):
        return adjusted_value
    if adjustment_policy == "vendor_adjusted_close":
        raise DataValidationError(
            f"{instrument} on {trade_date} is missing adjusted_close for adjustment_policy vendor_adjusted_close"
        )
    return close_value


def _instrument_names_from_csv(source: Path) -> set[str]:
    if not source.exists() or not source.is_file():
        raise DataValidationError(f"expected instrument source file does not exist: {source}")

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "instrument" not in (reader.fieldnames or []):
            raise DataValidationError(f"{source} is missing required column: instrument")
        return {
            (row.get("instrument") or "").strip()
            for row in reader
            if (row.get("instrument") or "").strip()
        }
