from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from trotters_trader.config import DataConfig
from trotters_trader.validation import DataValidationError


BASE_URL = "https://eodhd.com/api/eod"


@dataclass(frozen=True)
class DownloadResult:
    instrument: str
    api_symbol: str
    output_path: str
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
            payload = _fetch_payload(
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


def _fetch_payload(
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

    query = urlencode(query_params)
    with urlopen(f"{BASE_URL}/{api_symbol}?{query}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if isinstance(payload, dict):
        if "error" in payload:
            raise DataValidationError(str(payload["error"]))
        if "message" in payload:
            raise DataValidationError(str(payload["message"]))
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
