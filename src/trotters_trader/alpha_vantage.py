from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from trotters_trader.config import DataConfig
from trotters_trader.validation import DataValidationError


BASE_URL = "https://www.alphavantage.co/query"


@dataclass(frozen=True)
class DownloadResult:
    instrument: str
    api_symbol: str
    output_path: str
    status: str


def load_api_key(env_path: str | Path = ".env") -> str:
    direct = os.environ.get("AV_KEY", "").strip()
    if direct:
        return direct

    path = Path(env_path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("AV_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key

    raise DataValidationError("AV_KEY is not set in the environment or .env file")


def default_api_symbol(instrument: str) -> str:
    if instrument.endswith(".L"):
        return f"{instrument[:-2]}.LON"
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
    adjusted: bool = True,
    outputsize: str = "full",
    limit: int | None = None,
    requested_instruments: list[str] | None = None,
    force: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, object]:
    api_key = load_api_key(env_path)
    function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
    instrument_source = data_config.download_instruments_csv or data_config.source_instruments_csv
    targets = instruments_for_download(instrument_source)
    targets = filter_instruments(targets, requested_instruments)
    if limit is not None:
        targets = targets[:limit]
    raw_dir = data_config.raw_dir / "alpha_vantage_json"
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
                function=function,
                api_symbol=api_symbol,
                api_key=api_key,
                outputsize=outputsize,
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
        "function": function,
        "outputsize": outputsize,
        "downloaded": [result.__dict__ for result in results],
        "errors": errors,
        "raw_dir": str(raw_dir),
        "requested_instruments": requested_instruments or [],
        "force": force,
    }


def _fetch_payload(
    function: str,
    api_symbol: str,
    api_key: str,
    outputsize: str,
    timeout_seconds: int,
) -> dict[str, object]:
    query = urlencode(
        {
            "function": function,
            "symbol": api_symbol,
            "outputsize": outputsize,
            "apikey": api_key,
        }
    )
    with urlopen(f"{BASE_URL}?{query}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise DataValidationError("Alpha Vantage returned a non-object payload")

    if "Information" in payload:
        raise DataValidationError(str(payload["Information"]))
    if "Error Message" in payload:
        raise DataValidationError(str(payload["Error Message"]))
    if not any(key.startswith("Time Series") for key in payload):
        raise DataValidationError(f"Alpha Vantage payload missing time series keys: {payload}")

    return payload
