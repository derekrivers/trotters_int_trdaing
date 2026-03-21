from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
import math

from trotters_trader.config import StrategyConfig
from trotters_trader.domain import DailyBar, Instrument


class Strategy(ABC):
    @abstractmethod
    def score(
        self,
        history_by_instrument: dict[str, list[DailyBar]],
        feature_snapshot: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float]:
        raise NotImplementedError


class SmaCrossStrategy(Strategy):
    def __init__(self, short_window: int, long_window: int, signal_threshold: float) -> None:
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.signal_threshold = signal_threshold

    def score(
        self,
        history_by_instrument: dict[str, list[DailyBar]],
        feature_snapshot: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for instrument, bars in history_by_instrument.items():
            if len(bars) < self.long_window:
                continue
            short_avg = _average_close(bars[-self.short_window :])
            long_avg = _average_close(bars[-self.long_window :])
            if long_avg <= 0:
                continue
            score = (short_avg / long_avg) - 1.0
            if score >= self.signal_threshold:
                scores[instrument] = score
        return scores


class CrossSectionalMomentumStrategy(Strategy):
    def __init__(
        self,
        lookback_window: int,
        min_score: float,
        max_trailing_drawdown: float,
        drawdown_lookback_window: int,
        score_transform: str,
    ) -> None:
        if lookback_window < 2:
            raise ValueError("lookback_window must be at least 2")
        self.lookback_window = lookback_window
        self.min_score = min_score
        self.max_trailing_drawdown = max_trailing_drawdown
        self.drawdown_lookback_window = drawdown_lookback_window
        self.score_transform = score_transform

    def score(
        self,
        history_by_instrument: dict[str, list[DailyBar]],
        feature_snapshot: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for instrument, bars in history_by_instrument.items():
            feature_row = (feature_snapshot or {}).get(instrument, {})
            if feature_row:
                raw_score = float(feature_row.get("momentum_return", 0.0) or 0.0)
                realized_volatility = float(feature_row.get("realized_volatility", 0.0) or 0.0)
                trailing_drawdown = float(feature_row.get("trailing_drawdown", 0.0) or 0.0)
            else:
                if len(bars) < self.lookback_window:
                    continue
                window = bars[-self.lookback_window :]
                start_price = window[0].adjusted_close
                end_price = window[-1].adjusted_close
                if start_price <= 0:
                    continue
                raw_score = (end_price / start_price) - 1.0
                effective_drawdown_window = self._effective_drawdown_window()
                trailing_drawdown = _trailing_drawdown(
                    bars[-effective_drawdown_window:] if effective_drawdown_window > 0 else bars
                )
                realized_volatility = _realized_volatility(window)
            score = _transform_cross_sectional_score(
                raw_score,
                trailing_drawdown,
                realized_volatility,
                self.score_transform,
            )
            if score < self.min_score:
                continue
            if self.score_transform != "drawdown_penalized" and trailing_drawdown > self.max_trailing_drawdown:
                continue
            if score >= self.min_score:
                scores[instrument] = score
        return scores

    def _effective_drawdown_window(self) -> int:
        return self.drawdown_lookback_window or self.lookback_window


class MeanReversionStrategy(Strategy):
    def __init__(self, lookback_window: int, min_score: float) -> None:
        if lookback_window < 2:
            raise ValueError("lookback_window must be at least 2")
        self.lookback_window = lookback_window
        self.min_score = min_score

    def score(
        self,
        history_by_instrument: dict[str, list[DailyBar]],
        feature_snapshot: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for instrument, bars in history_by_instrument.items():
            if len(bars) < self.lookback_window:
                continue
            window = bars[-self.lookback_window :]
            start_price = window[0].adjusted_close
            end_price = window[-1].adjusted_close
            if start_price <= 0:
                continue
            cumulative_return = (end_price / start_price) - 1.0
            score = -cumulative_return
            if score >= self.min_score:
                scores[instrument] = score
        return scores


def build_strategy(config: StrategyConfig) -> Strategy:
    if config.name == "sma_cross":
        return SmaCrossStrategy(
            short_window=config.sma_cross.short_window,
            long_window=config.sma_cross.long_window,
            signal_threshold=config.sma_cross.signal_threshold,
        )
    if config.name == "cross_sectional_momentum":
        return CrossSectionalMomentumStrategy(
            lookback_window=config.cross_sectional_momentum.lookback_window,
            min_score=config.cross_sectional_momentum.min_score,
            max_trailing_drawdown=config.cross_sectional_momentum.max_trailing_drawdown,
            drawdown_lookback_window=config.cross_sectional_momentum.drawdown_lookback_window,
            score_transform=config.score_transform,
        )
    if config.name == "mean_reversion":
        return MeanReversionStrategy(
            lookback_window=config.mean_reversion.lookback_window,
            min_score=config.mean_reversion.min_score,
        )
    raise ValueError(f"Unsupported strategy: {config.name}")


def _average_close(bars: list[DailyBar]) -> float:
    return sum(bar.adjusted_close for bar in bars) / len(bars)


def build_target_weights(
    scores: dict[str, float],
    history_by_instrument: dict[str, list[DailyBar]],
    config: StrategyConfig,
    instruments: dict[str, Instrument] | None = None,
    current_holdings: set[str] | None = None,
    holding_days: dict[str, int] | None = None,
    selection_buffer_slots: int = 0,
    max_positions_per_sector: int = 0,
    max_positions_per_industry: int = 0,
    max_positions_per_benchmark_bucket: int = 0,
    min_holding_days: int = 0,
) -> dict[str, float]:
    current_holdings = current_holdings or set()
    holding_days = holding_days or {}
    positive_scores = [
        (instrument, score)
        for instrument, score in scores.items()
        if score > 0
    ]
    ranked_all = _ranked_scores(
        positive_scores,
        config,
        instruments or {},
    )
    selected = _select_ranked_instruments(
        ranked_all,
        config.top_n,
        instruments or {},
        current_holdings,
        holding_days,
        selection_buffer_slots,
        max_positions_per_sector,
        max_positions_per_industry,
        max_positions_per_benchmark_bucket,
        min_holding_days,
    )
    if not selected:
        return {}

    if config.weighting == "equal":
        weight = 1.0 / len(selected)
        return {instrument: weight for instrument, _ in selected}

    if config.weighting == "vol_inverse":
        raw_weights: dict[str, float] = {}
        volatility_window = _volatility_window(config)
        for instrument, _ in selected:
            volatility = _realized_volatility(history_by_instrument[instrument][-volatility_window:])
            if volatility <= 0:
                continue
            raw_weights[instrument] = 1.0 / volatility
        total = sum(raw_weights.values())
        if total <= 0:
            return {}
        return {instrument: value / total for instrument, value in raw_weights.items()}

    if config.weighting == "beta_vol_inverse":
        raw_weights: dict[str, float] = {}
        volatility_window = _volatility_window(config)
        benchmark_returns = _equal_weight_benchmark_returns(history_by_instrument, volatility_window)
        if benchmark_returns is None:
            return {}
        for instrument, _ in selected:
            volatility = _realized_volatility(history_by_instrument[instrument][-volatility_window:])
            instrument_returns = _simple_returns(history_by_instrument[instrument][-volatility_window:])
            if volatility <= 0 or not instrument_returns:
                continue
            beta = _beta_to_benchmark(instrument_returns, benchmark_returns)
            raw_weights[instrument] = 1.0 / (max(abs(beta), 0.25) * volatility)
        total = sum(raw_weights.values())
        if total <= 0:
            return {}
        return {instrument: value / total for instrument, value in raw_weights.items()}

    raise ValueError(f"Unsupported weighting mode: {config.weighting}")


def _realized_volatility(bars: list[DailyBar]) -> float:
    if len(bars) < 2:
        return 0.0
    returns = []
    previous = bars[0].adjusted_close
    for bar in bars[1:]:
        if previous <= 0:
            return 0.0
        returns.append(math.log(bar.adjusted_close / previous))
        previous = bar.adjusted_close
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def _trailing_drawdown(bars: list[DailyBar]) -> float:
    if not bars:
        return 0.0
    peak = bars[0].adjusted_close
    max_drawdown = 0.0
    for bar in bars:
        peak = max(peak, bar.adjusted_close)
        if peak <= 0:
            continue
        drawdown = (peak - bar.adjusted_close) / peak
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _simple_returns(bars: list[DailyBar]) -> list[float]:
    if len(bars) < 2:
        return []
    returns = []
    previous = bars[0].adjusted_close
    for bar in bars[1:]:
        if previous <= 0:
            return []
        returns.append((bar.adjusted_close / previous) - 1.0)
        previous = bar.adjusted_close
    return returns


def _equal_weight_benchmark_returns(
    history_by_instrument: dict[str, list[DailyBar]],
    lookback_window: int,
) -> list[float] | None:
    if lookback_window < 2:
        return None
    instrument_returns = []
    for bars in history_by_instrument.values():
        returns = _simple_returns(bars[-lookback_window:])
        if len(returns) == lookback_window - 1:
            instrument_returns.append(returns)
    if not instrument_returns:
        return None

    benchmark_returns = []
    for index in range(lookback_window - 1):
        benchmark_returns.append(sum(returns[index] for returns in instrument_returns) / len(instrument_returns))
    return benchmark_returns


def _beta_to_benchmark(
    instrument_returns: list[float],
    benchmark_returns: list[float],
) -> float:
    aligned = min(len(instrument_returns), len(benchmark_returns))
    if aligned <= 1:
        return 0.0
    instrument_window = instrument_returns[-aligned:]
    benchmark_window = benchmark_returns[-aligned:]
    benchmark_mean = sum(benchmark_window) / aligned
    instrument_mean = sum(instrument_window) / aligned
    covariance = sum(
        (inst - instrument_mean) * (bench - benchmark_mean)
        for inst, bench in zip(instrument_window, benchmark_window)
    ) / aligned
    benchmark_variance = sum((bench - benchmark_mean) ** 2 for bench in benchmark_window) / aligned
    if benchmark_variance <= 0:
        return 0.0
    return covariance / benchmark_variance


def _volatility_window(config: StrategyConfig) -> int:
    if config.name == "sma_cross":
        return config.sma_cross.long_window
    if config.name == "cross_sectional_momentum":
        return config.cross_sectional_momentum.lookback_window
    if config.name == "mean_reversion":
        return config.mean_reversion.lookback_window
    raise ValueError(f"Unsupported strategy for volatility window: {config.name}")


def _transform_cross_sectional_score(
    raw_score: float,
    trailing_drawdown: float,
    realized_volatility: float,
    score_transform: str,
) -> float:
    if score_transform == "raw":
        return raw_score
    if score_transform == "vol_adjusted":
        volatility_floor = max(realized_volatility, 1e-6)
        return raw_score / volatility_floor
    if score_transform == "drawdown_penalized":
        penalty = max(0.0, 1.0 - max(trailing_drawdown, 0.0))
        return raw_score * penalty
    raise ValueError(f"Unsupported score transform: {score_transform}")


def _ranked_scores(
    positive_scores: list[tuple[str, float]],
    config: StrategyConfig,
    instruments: dict[str, Instrument],
) -> list[tuple[str, float]]:
    ranked_all = sorted(positive_scores, key=lambda item: (-item[1], item[0]))
    if config.ranking_mode == "global":
        return ranked_all

    if config.ranking_mode == "sector_relative":
        return _group_relative_ranking(ranked_all, instruments, "sector", config.min_candidates_per_group)

    if config.ranking_mode == "benchmark_bucket_relative":
        return _group_relative_ranking(
            ranked_all,
            instruments,
            "benchmark_bucket",
            config.min_candidates_per_group,
        )

    raise ValueError(f"Unsupported ranking mode: {config.ranking_mode}")


def _group_relative_ranking(
    ranked_all: list[tuple[str, float]],
    instruments: dict[str, Instrument],
    attribute: str,
    min_candidates_per_group: int,
) -> list[tuple[str, float]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for instrument, score in ranked_all:
        value = _metadata_value(instrument, instruments, attribute) or "UNSPECIFIED"
        grouped.setdefault(value, []).append((instrument, score))

    eligible_groups = [
        sorted(entries, key=lambda item: (-item[1], item[0]))
        for entries in grouped.values()
        if len(entries) >= max(min_candidates_per_group, 1)
    ]
    if not eligible_groups:
        return ranked_all

    eligible_groups.sort(key=lambda group: (-group[0][1], group[0][0]))
    ranked: list[tuple[str, float]] = []
    depth = 0
    while True:
        added = False
        for group in eligible_groups:
            if depth < len(group):
                ranked.append(group[depth])
                added = True
        if not added:
            break
        depth += 1
    return ranked


def _select_ranked_instruments(
    ranked_all: list[tuple[str, float]],
    top_n: int,
    instruments: dict[str, Instrument],
    current_holdings: set[str],
    holding_days: dict[str, int],
    selection_buffer_slots: int,
    max_positions_per_sector: int,
    max_positions_per_industry: int,
    max_positions_per_benchmark_bucket: int,
    min_holding_days: int,
) -> list[tuple[str, float]]:
    if not ranked_all:
        return []

    selected: list[tuple[str, float]] = []
    selected_names: set[str] = set()
    sector_counts: Counter[str] = Counter()
    industry_counts: Counter[str] = Counter()
    benchmark_bucket_counts: Counter[str] = Counter()
    protected_names = _protected_holdings(
        ranked_all,
        top_n,
        current_holdings,
        holding_days,
        selection_buffer_slots,
        min_holding_days,
    )
    selection_limit = max(top_n + selection_buffer_slots, len(protected_names))

    for instrument, score in ranked_all:
        if instrument not in protected_names:
            continue
        if _metadata_capped(
            instrument,
            instruments,
            "sector",
            sector_counts,
            max_positions_per_sector,
        ) or _metadata_capped(
            instrument,
            instruments,
            "industry",
            industry_counts,
            max_positions_per_industry,
        ) or _metadata_capped(
            instrument,
            instruments,
            "benchmark_bucket",
            benchmark_bucket_counts,
            max_positions_per_benchmark_bucket,
        ):
            continue
        selected.append((instrument, score))
        selected_names.add(instrument)
        _increment_metadata_count(instrument, instruments, "sector", sector_counts)
        _increment_metadata_count(instrument, instruments, "industry", industry_counts)
        _increment_metadata_count(instrument, instruments, "benchmark_bucket", benchmark_bucket_counts)

    for instrument, score in ranked_all:
        if len(selected) >= selection_limit:
            break
        if instrument in selected_names:
            continue
        if _metadata_capped(
            instrument,
            instruments,
            "sector",
            sector_counts,
            max_positions_per_sector,
        ) or _metadata_capped(
            instrument,
            instruments,
            "industry",
            industry_counts,
            max_positions_per_industry,
        ) or _metadata_capped(
            instrument,
            instruments,
            "benchmark_bucket",
            benchmark_bucket_counts,
            max_positions_per_benchmark_bucket,
        ):
            continue
        selected.append((instrument, score))
        selected_names.add(instrument)
        _increment_metadata_count(instrument, instruments, "sector", sector_counts)
        _increment_metadata_count(instrument, instruments, "industry", industry_counts)
        _increment_metadata_count(instrument, instruments, "benchmark_bucket", benchmark_bucket_counts)

    return selected


def _protected_holdings(
    ranked_all: list[tuple[str, float]],
    top_n: int,
    current_holdings: set[str],
    holding_days: dict[str, int],
    selection_buffer_slots: int,
    min_holding_days: int,
) -> set[str]:
    protected: set[str] = set()
    if selection_buffer_slots > 0:
        buffered_names = {
            instrument
            for instrument, _ in ranked_all[: top_n + selection_buffer_slots]
            if instrument in current_holdings
        }
        protected.update(buffered_names)

    if min_holding_days > 0:
        recent_holdings = {
            instrument
            for instrument, _ in ranked_all
            if instrument in current_holdings and holding_days.get(instrument, 0) < min_holding_days
        }
        protected.update(recent_holdings)

    return protected


def _metadata_capped(
    instrument: str,
    instruments: dict[str, Instrument],
    attribute: str,
    counts: Counter[str],
    max_positions: int,
) -> bool:
    if max_positions <= 0:
        return False
    value = _metadata_value(instrument, instruments, attribute)
    if not value:
        return False
    return counts[value] >= max_positions


def _increment_metadata_count(
    instrument: str,
    instruments: dict[str, Instrument],
    attribute: str,
    counts: Counter[str],
) -> None:
    value = _metadata_value(instrument, instruments, attribute)
    if value:
        counts[value] += 1


def _metadata_value(
    instrument: str,
    instruments: dict[str, Instrument],
    attribute: str,
) -> str:
    metadata = instruments.get(instrument)
    if metadata is None:
        return ""
    return str(getattr(metadata, attribute, "") or "")
