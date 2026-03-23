from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from trotters_trader.config import DataConfig
from trotters_trader.validation import DataValidationError


EOD_BASE_URL = "https://eodhd.com/api/eod"
EXCHANGE_SYMBOL_LIST_URL = "https://eodhd.com/api/exchange-symbol-list"
DIVIDENDS_URL = "https://eodhd.com/api/div"
SPLITS_URL = "https://eodhd.com/api/splits"

INSTRUMENT_FIELDNAMES = [
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
CORPORATE_ACTION_FIELDNAMES = [
    "instrument",
    "action_type",
    "ex_date",
    "record_date",
    "payable_date",
    "ratio_or_amount",
]

EXCHANGE_SUFFIX_MAP = {
    "LSE": ".L",
}

EXCHANGE_MIC_MAP = {
    "LSE": "XLON",
}

@dataclass(frozen=True)
class DownloadResult:
    instrument: str
    api_symbol: str
    output_path: str
    status: str


@dataclass(frozen=True)
class CorporateActionsDownloadResult:
    instrument: str
    api_symbol: str
    dividends_path: str
    splits_path: str
    status: str


def load_api_key(env_path: str | Path = ".env") -> str:
    direct = os.environ.get("EODHD_API_KEY", "").strip()
    if direct:
        return direct

    path = Path(env_path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("EODHD_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key

    raise DataValidationError("EODHD_API_KEY is not set in the environment or .env file")


def default_api_symbol(instrument: str) -> str:
    if instrument.endswith(".L"):
        return f"{instrument[:-2]}.LSE"
    return instrument


def instruments_for_download(instruments_csv: str | Path, limit: int | None = None) -> list[tuple[str, str]]:
    csv_path = Path(instruments_csv)
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    if not rows:
        return []

    instruments: list[tuple[str, str]] = []
    header = [part.strip() for part in rows[0].split(",")]
    instrument_index = header.index("instrument") if "instrument" in header else 0

    for row in rows[1:]:
        parts = row.split(",")
        if len(parts) <= instrument_index:
            continue
        instrument = parts[instrument_index].strip()
        if not instrument:
            continue
        instruments.append((instrument, default_api_symbol(instrument)))

    return instruments if limit is None else instruments[:limit]


def filter_instruments(
    instruments: list[tuple[str, str]],
    requested_instruments: list[str] | None = None,
) -> list[tuple[str, str]]:
    if not requested_instruments:
        return instruments

    requested = {instrument.strip() for instrument in requested_instruments if instrument.strip()}
    return [item for item in instruments if item[0] in requested]


def download_daily_series(
    data_config: DataConfig,
    env_path: str | Path = ".env",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = None,
    requested_instruments: list[str] | None = None,
    force: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    api_key = load_api_key(env_path)
    instrument_source = data_config.download_instruments_csv or data_config.source_instruments_csv
    targets = instruments_for_download(instrument_source)
    targets = filter_instruments(targets, requested_instruments)
    if limit is not None:
        targets = targets[:limit]

    raw_dir = data_config.raw_dir / "eodhd_json"
    raw_dir.mkdir(parents=True, exist_ok=True)

    results: list[DownloadResult] = []
    errors: list[dict[str, str]] = []

    for instrument, api_symbol in targets:
        output_path = raw_dir / f"{instrument}.json"
        if output_path.exists() and not force:
            results.append(
                DownloadResult(
                    instrument=instrument,
                    api_symbol=api_symbol,
                    output_path=str(output_path),
                    status="skipped_existing",
                )
            )
            continue
        try:
            payload = _fetch_eod_payload(
                api_symbol=api_symbol,
                api_key=api_key,
                date_from=date_from,
                date_to=date_to,
                timeout_seconds=timeout_seconds,
            )
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            results.append(
                DownloadResult(
                    instrument=instrument,
                    api_symbol=api_symbol,
                    output_path=str(output_path),
                    status="downloaded",
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "instrument": instrument,
                    "api_symbol": api_symbol,
                    "error": str(exc),
                }
            )

    return {
        "provider": "eodhd",
        "period": "d",
        "from": date_from,
        "to": date_to,
        "downloaded": [result.__dict__ for result in results],
        "errors": errors,
        "raw_dir": str(raw_dir),
        "requested_instruments": requested_instruments or [],
        "force": force,
    }


def download_exchange_symbols(
    data_config: DataConfig,
    env_path: str | Path = ".env",
    exchange_code: str | None = None,
    requested_instruments: list[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    api_key = load_api_key(env_path)
    resolved_exchange_code = _resolve_exchange_code(data_config, exchange_code)
    raw_dir = data_config.raw_dir / "eodhd_reference"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{resolved_exchange_code}.json"

    if raw_path.exists() and not force:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_status = "skipped_existing"
    else:
        payload = _fetch_exchange_symbol_list(
            exchange_code=resolved_exchange_code,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        raw_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        raw_status = "downloaded"

    expected_targets = instruments_for_download(
        data_config.download_instruments_csv or data_config.source_instruments_csv
    )
    expected_targets = filter_instruments(expected_targets, requested_instruments)
    if limit is not None:
        expected_targets = expected_targets[:limit]
    expected_instruments = [instrument for instrument, _ in expected_targets]

    existing_rows = _load_existing_instrument_rows(data_config.source_instruments_csv)
    normalized_rows, missing_instruments = _normalize_exchange_symbol_rows(
        payload=payload,
        exchange_code=resolved_exchange_code,
        exchange_mic=_resolve_exchange_mic(data_config, resolved_exchange_code),
        expected_instruments=expected_instruments,
        existing_rows=existing_rows,
    )
    _write_csv(data_config.source_instruments_csv, INSTRUMENT_FIELDNAMES, normalized_rows)

    return {
        "provider": "eodhd",
        "exchange_code": resolved_exchange_code,
        "raw_reference_path": str(raw_path),
        "raw_reference_status": raw_status,
        "instrument_master_path": str(data_config.source_instruments_csv),
        "instrument_count": len(normalized_rows),
        "missing_instruments": missing_instruments,
        "requested_instruments": expected_instruments,
        "force": force,
    }


def download_corporate_actions(
    data_config: DataConfig,
    env_path: str | Path = ".env",
    limit: int | None = None,
    requested_instruments: list[str] | None = None,
    force: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    api_key = load_api_key(env_path)
    instrument_source = data_config.download_instruments_csv or data_config.source_instruments_csv
    targets = instruments_for_download(instrument_source)
    targets = filter_instruments(targets, requested_instruments)
    if limit is not None:
        targets = targets[:limit]

    dividends_dir = data_config.raw_dir / "eodhd_dividends"
    splits_dir = data_config.raw_dir / "eodhd_splits"
    dividends_dir.mkdir(parents=True, exist_ok=True)
    splits_dir.mkdir(parents=True, exist_ok=True)

    existing_actions = _load_existing_corporate_actions(data_config.source_corporate_actions_csv)
    instrument_rows = _load_existing_instrument_rows(data_config.source_instruments_csv)
    refreshed_instruments: set[str] = set()
    results: list[CorporateActionsDownloadResult] = []
    errors: list[dict[str, str]] = []

    for instrument, api_symbol in targets:
        dividends_path = dividends_dir / f"{instrument}.json"
        splits_path = splits_dir / f"{instrument}.json"
        try:
            dividends_payload, dividends_status = _load_or_fetch_list_payload(
                path=dividends_path,
                force=force,
                fetcher=lambda: _fetch_list_endpoint(
                    base_url=DIVIDENDS_URL,
                    api_symbol=api_symbol,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                ),
            )
            splits_payload, splits_status = _load_or_fetch_list_payload(
                path=splits_path,
                force=force,
                fetcher=lambda: _fetch_list_endpoint(
                    base_url=SPLITS_URL,
                    api_symbol=api_symbol,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                ),
            )
            existing_actions[instrument] = _normalize_corporate_actions(
                instrument=instrument,
                dividends_payload=dividends_payload,
                splits_payload=splits_payload,
                instrument_row=instrument_rows.get(instrument, {}),
            )
            refreshed_instruments.add(instrument)
            combined_status = "downloaded"
            if dividends_status == "skipped_existing" and splits_status == "skipped_existing":
                combined_status = "skipped_existing"
            results.append(
                CorporateActionsDownloadResult(
                    instrument=instrument,
                    api_symbol=api_symbol,
                    dividends_path=str(dividends_path),
                    splits_path=str(splits_path),
                    status=combined_status,
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "instrument": instrument,
                    "api_symbol": api_symbol,
                    "error": str(exc),
                }
            )

    _write_corporate_actions_csv(data_config.source_corporate_actions_csv, existing_actions)

    return {
        "provider": "eodhd",
        "corporate_actions_path": str(data_config.source_corporate_actions_csv),
        "downloaded": [result.__dict__ for result in results],
        "errors": errors,
        "refreshed_instruments": sorted(refreshed_instruments),
        "requested_instruments": [instrument for instrument, _ in targets],
        "dividends_dir": str(dividends_dir),
        "splits_dir": str(splits_dir),
        "force": force,
    }


def _fetch_eod_payload(
    api_symbol: str,
    api_key: str,
    date_from: str | None,
    date_to: str | None,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    query_params = {
        "api_token": api_key,
        "fmt": "json",
        "period": "d",
    }
    if date_from:
        query_params["from"] = date_from
    if date_to:
        query_params["to"] = date_to

    payload = _request_json(
        url=f"{EOD_BASE_URL}/{api_symbol}",
        query_params=query_params,
        timeout_seconds=timeout_seconds,
    )

    if isinstance(payload, dict):
        _raise_payload_error(payload)
        raise DataValidationError(f"EODHD returned an unexpected object payload: {payload}")
    if not isinstance(payload, list):
        raise DataValidationError("EODHD returned a non-list payload")
    if not payload:
        raise DataValidationError(f"EODHD returned no data for {api_symbol}")

    required_keys = {"date", "open", "high", "low", "close", "volume"}
    for row in payload:
        if not isinstance(row, dict):
            raise DataValidationError(f"EODHD returned a malformed row for {api_symbol}")
        missing = sorted(required_keys - set(row.keys()))
        if missing:
            raise DataValidationError(
                f"EODHD row missing required fields for {api_symbol}: {', '.join(missing)}"
            )

    return payload


def _fetch_exchange_symbol_list(
    exchange_code: str,
    api_key: str,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    payload = _request_json(
        url=f"{EXCHANGE_SYMBOL_LIST_URL}/{exchange_code}",
        query_params={"api_token": api_key, "fmt": "json"},
        timeout_seconds=timeout_seconds,
    )
    if isinstance(payload, dict):
        _raise_payload_error(payload)
        raise DataValidationError(f"EODHD returned an unexpected symbol-list payload: {payload}")
    if not isinstance(payload, list):
        raise DataValidationError("EODHD exchange-symbol-list returned a non-list payload")
    return payload


def _fetch_list_endpoint(
    base_url: str,
    api_symbol: str,
    api_key: str,
    timeout_seconds: int,
) -> list[dict[str, object]]:
    payload = _request_json(
        url=f"{base_url}/{api_symbol}",
        query_params={"api_token": api_key, "fmt": "json"},
        timeout_seconds=timeout_seconds,
    )
    if isinstance(payload, dict):
        _raise_payload_error(payload)
        raise DataValidationError(f"EODHD returned an unexpected corporate-action payload: {payload}")
    if not isinstance(payload, list):
        raise DataValidationError("EODHD corporate-action endpoint returned a non-list payload")
    return payload


def _request_json(url: str, query_params: dict[str, object], timeout_seconds: int) -> object:
    query = urlencode(query_params)
    with urlopen(f"{url}?{query}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload


def _raise_payload_error(payload: dict[str, object]) -> None:
    if "error" in payload:
        raise DataValidationError(str(payload["error"]))
    if "message" in payload:
        raise DataValidationError(str(payload["message"]))


def _load_or_fetch_list_payload(
    path: Path,
    force: bool,
    fetcher,
) -> tuple[list[dict[str, object]], str]:
    if path.exists() and not force:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise DataValidationError(f"cached EODHD payload must be a list in {path}")
        return payload, "skipped_existing"

    payload = fetcher()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload, "downloaded"


def _resolve_exchange_code(data_config: DataConfig, exchange_code: str | None) -> str:
    resolved = (exchange_code or data_config.download_exchange_code).strip().upper()
    if not resolved:
        raise DataValidationError("download_exchange_code is not configured; provide --exchange-code or set it in the config")
    return resolved


def _resolve_exchange_mic(data_config: DataConfig, exchange_code: str) -> str:
    if data_config.source_instruments_csv.exists():
        rows = _load_existing_instrument_rows(data_config.source_instruments_csv)
        mics = sorted({row.get("exchange_mic", "") for row in rows.values() if row.get("exchange_mic", "")})
        if len(mics) == 1:
            return mics[0]
    return EXCHANGE_MIC_MAP.get(exchange_code, exchange_code)


def _normalize_exchange_symbol_rows(
    payload: list[dict[str, object]],
    exchange_code: str,
    exchange_mic: str,
    expected_instruments: list[str],
    existing_rows: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    expected_set = set(expected_instruments)
    use_expected_filter = bool(expected_instruments)
    normalized_by_instrument: dict[str, dict[str, str]] = {}

    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Code", "") or "").strip()
        if not code:
            continue
        instrument = _instrument_from_exchange_code(code, exchange_code)
        if use_expected_filter and instrument not in expected_set:
            continue
        existing = existing_rows.get(instrument, {})
        status = str(existing.get("status", "") or "").strip() or "ACTIVE"
        delisting_date = str(existing.get("delisting_date", "") or "").strip()
        tradability_status = str(existing.get("tradability_status", "") or "").strip()
        if status == "DELISTED":
            tradability_status = tradability_status or "HALTED"
        else:
            tradability_status = tradability_status or "TRADABLE"
        normalized_by_instrument[instrument] = {
            "instrument": instrument,
            "exchange_mic": str(existing.get("exchange_mic", "") or exchange_mic).strip() or exchange_mic,
            "currency": str(item.get("Currency", "") or existing.get("currency", "") or "").strip(),
            "isin": str(item.get("Isin", "") or existing.get("isin", "") or "").strip(),
            "sedol": str(existing.get("sedol", "") or "").strip(),
            "company_number": str(existing.get("company_number", "") or "").strip(),
            "status": status,
            "listing_date": str(existing.get("listing_date", "") or "").strip(),
            "delisting_date": delisting_date,
            "sector": str(existing.get("sector", "") or "").strip(),
            "industry": str(existing.get("industry", "") or "").strip(),
            "benchmark_bucket": str(existing.get("benchmark_bucket", "") or "").strip(),
            "liquidity_bucket": str(existing.get("liquidity_bucket", "") or "").strip(),
            "tradability_status": tradability_status,
            "universe_bucket": str(existing.get("universe_bucket", "") or "").strip(),
        }

    missing_instruments = sorted(expected_set - set(normalized_by_instrument)) if use_expected_filter else []
    for instrument in missing_instruments:
        if instrument in existing_rows:
            normalized_by_instrument[instrument] = dict(existing_rows[instrument])

    normalized_rows = [
        {field: normalized_by_instrument[instrument].get(field, "") for field in INSTRUMENT_FIELDNAMES}
        for instrument in sorted(normalized_by_instrument)
    ]
    return normalized_rows, [instrument for instrument in missing_instruments if instrument not in existing_rows]


def _load_existing_instrument_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "instrument" not in (reader.fieldnames or []):
            return {}
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            instrument = (row.get("instrument") or "").strip()
            if not instrument:
                continue
            rows[instrument] = {field: (row.get(field) or "").strip() for field in INSTRUMENT_FIELDNAMES}
        return rows


def _load_existing_corporate_actions(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows_by_instrument: dict[str, list[dict[str, str]]] = {}
        for row in reader:
            instrument = (row.get("instrument") or "").strip()
            if not instrument:
                continue
            rows_by_instrument.setdefault(instrument, []).append(
                {field: (row.get(field) or "").strip() for field in CORPORATE_ACTION_FIELDNAMES}
            )
    for instrument, rows in rows_by_instrument.items():
        rows.sort(key=lambda row: (row["ex_date"], row["action_type"], row["ratio_or_amount"]))
    return rows_by_instrument


def _normalize_corporate_actions(
    instrument: str,
    dividends_payload: list[dict[str, object]],
    splits_payload: list[dict[str, object]],
    instrument_row: dict[str, str],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    cash_scale = _dividend_cash_scale(instrument, instrument_row)

    for item in dividends_payload:
        if not isinstance(item, dict):
            continue
        ex_date = str(item.get("date", "") or "").strip()
        if not ex_date:
            continue
        amount = item.get("unadjustedValue")
        if amount in (None, ""):
            amount = item.get("value")
        if amount in (None, ""):
            continue
        actions.append(
            {
                "instrument": instrument,
                "action_type": "DIVIDEND",
                "ex_date": ex_date,
                "record_date": str(item.get("recordDate", "") or ex_date),
                "payable_date": str(item.get("paymentDate", "") or ex_date),
                "ratio_or_amount": str(float(amount) * cash_scale),
            }
        )

    for item in splits_payload:
        if not isinstance(item, dict):
            continue
        ex_date = str(item.get("date", "") or "").strip()
        split_value = str(item.get("split", "") or "").strip()
        if not ex_date or not split_value:
            continue
        ratio = _parse_split_ratio(split_value)
        actions.append(
            {
                "instrument": instrument,
                "action_type": "SPLIT",
                "ex_date": ex_date,
                "record_date": ex_date,
                "payable_date": ex_date,
                "ratio_or_amount": str(ratio),
            }
        )

    actions.sort(key=lambda row: (row["ex_date"], row["action_type"], row["ratio_or_amount"]))
    return actions


def _parse_split_ratio(value: str) -> float:
    parts = value.split("/", 1)
    if len(parts) != 2:
        raise DataValidationError(f"unsupported split ratio format: {value}")
    numerator = float(parts[0])
    denominator = float(parts[1])
    if denominator == 0:
        raise DataValidationError(f"split ratio denominator must be non-zero: {value}")
    return numerator / denominator


def _write_corporate_actions_csv(path: Path, rows_by_instrument: dict[str, list[dict[str, str]]]) -> None:
    flattened_rows: list[dict[str, str]] = []
    for instrument in sorted(rows_by_instrument):
        flattened_rows.extend(rows_by_instrument[instrument])
    _write_csv(path, CORPORATE_ACTION_FIELDNAMES, flattened_rows)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _instrument_from_exchange_code(code: str, exchange_code: str) -> str:
    normalized_code = code.strip()
    if not normalized_code:
        return normalized_code
    suffix = EXCHANGE_SUFFIX_MAP.get(exchange_code, "")
    if suffix:
        return normalized_code if normalized_code.endswith(suffix) else f"{normalized_code}{suffix}"
    if "." in normalized_code:
        return normalized_code
    return f"{normalized_code}.{exchange_code}"


def _dividend_cash_scale(instrument: str, instrument_row: dict[str, str]) -> float:
    currency = str(instrument_row.get("currency", "") or "").strip().upper()
    if instrument.endswith(".L") and currency == "GBP":
        return 100.0
    return 1.0
