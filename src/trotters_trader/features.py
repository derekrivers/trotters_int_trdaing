from __future__ import annotations

import csv
import json
from json import JSONDecodeError
from dataclasses import dataclass
from pathlib import Path

from trotters_trader.config import AppConfig
from trotters_trader.data import load_daily_bars
from trotters_trader.domain import DailyBar


@dataclass(frozen=True)
class FeatureStore:
    set_name: str
    feature_path: Path
    manifest_path: Path
    momentum_lookback_window: int
    volatility_window: int
    drawdown_window: int
    rows_by_date: dict[str, dict[str, dict[str, float]]]

    def snapshot(self, trade_date: str) -> dict[str, dict[str, float]]:
        return self.rows_by_date.get(trade_date, {})


def materialize_feature_set(config: AppConfig) -> dict[str, str]:
    bars_by_instrument = load_daily_bars(config.data.canonical_dir / "daily_bars.csv")
    feature_dir = config.features.feature_dir / _safe_name(config.features.set_name)
    feature_dir.mkdir(parents=True, exist_ok=True)
    feature_path = feature_dir / "features.csv"
    manifest_path = feature_dir / "manifest.json"

    lookback_window = config.strategy.cross_sectional_momentum.lookback_window
    drawdown_window = config.strategy.cross_sectional_momentum.drawdown_lookback_window or lookback_window
    volatility_window = max(config.portfolio.volatility_lookback_days, 2)

    fieldnames = [
        "trade_date",
        "instrument",
        "momentum_return",
        "realized_volatility",
        "trailing_drawdown",
    ]
    rows: list[dict[str, object]] = []
    for instrument, bars in sorted(bars_by_instrument.items()):
        for index, bar in enumerate(bars):
            if index + 1 < max(lookback_window, volatility_window, drawdown_window):
                continue
            momentum_window = bars[index + 1 - lookback_window : index + 1]
            volatility_window_bars = bars[index + 1 - volatility_window : index + 1]
            drawdown_window_bars = bars[index + 1 - drawdown_window : index + 1]
            rows.append(
                {
                    "trade_date": bar.trade_date.isoformat(),
                    "instrument": instrument,
                    "momentum_return": _window_return(momentum_window),
                    "realized_volatility": _realized_volatility(volatility_window_bars),
                    "trailing_drawdown": _trailing_drawdown(drawdown_window_bars),
                }
            )

    temp_feature_path = feature_path.with_suffix(".csv.tmp")
    with temp_feature_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "set_name": config.features.set_name,
        "strategy_family": config.strategy.name,
        "feature_path": str(feature_path),
        "momentum_lookback_window": lookback_window,
        "volatility_window": volatility_window,
        "drawdown_window": drawdown_window,
        "source_canonical_dir": str(config.data.canonical_dir),
    }
    temp_manifest_path = manifest_path.with_suffix(".json.tmp")
    temp_manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temp_feature_path.replace(feature_path)
    temp_manifest_path.replace(manifest_path)
    return {
        "feature_csv": str(feature_path),
        "manifest_json": str(manifest_path),
        "set_name": config.features.set_name,
    }


def load_feature_store(config: AppConfig) -> FeatureStore | None:
    feature_dir = config.features.feature_dir / _safe_name(config.features.set_name)
    feature_path = feature_dir / "features.csv"
    manifest_path = feature_dir / "manifest.json"
    if not feature_path.exists() or not manifest_path.exists():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return None
    rows_by_date: dict[str, dict[str, dict[str, float]]] = {}
    try:
        with feature_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                trade_date = row["trade_date"]
                instrument = row["instrument"]
                rows_by_date.setdefault(trade_date, {})[instrument] = {
                    "momentum_return": float(row["momentum_return"]),
                    "realized_volatility": float(row["realized_volatility"]),
                    "trailing_drawdown": float(row["trailing_drawdown"]),
                }
    except (OSError, KeyError, ValueError, csv.Error):
        return None

    return FeatureStore(
        set_name=str(manifest.get("set_name", config.features.set_name)),
        feature_path=feature_path,
        manifest_path=manifest_path,
        momentum_lookback_window=int(manifest.get("momentum_lookback_window", 0)),
        volatility_window=int(manifest.get("volatility_window", 0)),
        drawdown_window=int(manifest.get("drawdown_window", 0)),
        rows_by_date=rows_by_date,
    )


def ensure_feature_set(config: AppConfig) -> dict[str, str] | None:
    if not config.features.enabled or not config.features.materialize_on_backtest:
        return None
    return materialize_feature_set(config)


def feature_store_matches_config(store: FeatureStore, config: AppConfig) -> bool:
    return (
        store.momentum_lookback_window == config.strategy.cross_sectional_momentum.lookback_window
        and store.drawdown_window
        == (config.strategy.cross_sectional_momentum.drawdown_lookback_window or config.strategy.cross_sectional_momentum.lookback_window)
    )


def _window_return(bars: list[DailyBar]) -> float:
    if len(bars) < 2:
        return 0.0
    start = bars[0].adjusted_close
    end = bars[-1].adjusted_close
    if start <= 0:
        return 0.0
    return (end / start) - 1.0


def _realized_volatility(bars: list[DailyBar]) -> float:
    if len(bars) < 2:
        return 0.0
    returns: list[float] = []
    previous = bars[0].adjusted_close
    for bar in bars[1:]:
        if previous <= 0:
            return 0.0
        returns.append((bar.adjusted_close / previous) - 1.0)
        previous = bar.adjusted_close
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    return variance ** 0.5


def _trailing_drawdown(bars: list[DailyBar]) -> float:
    if not bars:
        return 0.0
    peak = bars[0].adjusted_close
    max_drawdown = 0.0
    for bar in bars:
        peak = max(peak, bar.adjusted_close)
        if peak <= 0:
            continue
        max_drawdown = max(max_drawdown, (peak - bar.adjusted_close) / peak)
    return max_drawdown


def _safe_name(name: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in name)
    return safe or "default"
