from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class RunConfig:
    name: str
    initial_cash: float
    output_dir: Path


@dataclass(frozen=True)
class PeriodConfig:
    label: str
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True)
class DataConfig:
    source_name: str
    source_bars_csv: Path
    source_instruments_csv: Path
    download_instruments_csv: Path | None
    source_corporate_actions_csv: Path
    staging_dir: Path
    canonical_dir: Path
    raw_dir: Path
    download_exchange_code: str = ""
    adjustment_policy: str = "raw_close"


@dataclass(frozen=True)
class SmaCrossConfig:
    short_window: int
    long_window: int
    signal_threshold: float


@dataclass(frozen=True)
class LookbackStrategyConfig:
    lookback_window: int
    min_score: float
    max_trailing_drawdown: float = 1.0
    drawdown_lookback_window: int = 0


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    top_n: int
    weighting: str
    ranking_mode: str
    score_transform: str
    min_candidates_per_group: int
    sma_cross: SmaCrossConfig
    cross_sectional_momentum: LookbackStrategyConfig
    mean_reversion: LookbackStrategyConfig


@dataclass(frozen=True)
class PortfolioConfig:
    cash_buffer_pct: float
    target_gross_exposure: float
    max_position_weight: float
    rebalance_threshold_bps: float
    rebalance_frequency_days: int
    max_rebalance_turnover_pct: float
    initial_deployment_turnover_pct: float
    selection_buffer_slots: int
    max_positions_per_sector: int
    min_holding_days: int
    adv_window_days: int
    max_target_adv_participation: float
    volatility_target: float = 0.0
    volatility_lookback_days: int = 20
    drawdown_reduce_threshold: float = 0.0
    drawdown_reduced_gross_exposure: float = 0.0
    drawdown_force_rebalance: bool = False
    benchmark_regime_window_days: int = 0
    benchmark_regime_min_return: float = 0.0
    benchmark_regime_reduced_gross_exposure: float = 0.0
    benchmark_regime_force_rebalance: bool = False
    max_positions_per_industry: int = 0
    max_positions_per_benchmark_bucket: int = 0


@dataclass(frozen=True)
class ExecutionConfig:
    fill_model: str
    commission_bps: float
    slippage_bps: float
    spread_bps: float
    stamp_duty_bps: float
    max_participation_rate: float
    allow_partial_fills: bool


@dataclass(frozen=True)
class BenchmarkConfig:
    models: tuple[str, ...]
    primary: str


@dataclass(frozen=True)
class UniverseConfig:
    allowed_exchange_mic: tuple[str, ...]
    allowed_currency: str
    active_only: bool
    min_history_days: int
    min_average_volume: float
    allowed_benchmark_buckets: tuple[str, ...] = ()
    allowed_tradability_statuses: tuple[str, ...] = ()
    allowed_universe_buckets: tuple[str, ...] = ()
    excluded_liquidity_buckets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchConfig:
    profile_name: str
    profile_version: str
    frozen_on: date | None
    promoted: bool
    research_tranche: str = ""
    research_slice_name: str = "all"
    control_profile: str = ""
    promotion_candidate: bool = False


@dataclass(frozen=True)
class FeaturesConfig:
    enabled: bool
    feature_dir: Path
    set_name: str
    use_precomputed: bool
    materialize_on_backtest: bool


@dataclass(frozen=True)
class WalkForwardConfig:
    enabled: bool
    train_days: int
    test_days: int
    step_days: int
    anchored: bool


@dataclass(frozen=True)
class PromotionPolicyConfig:
    min_pass_windows: int
    min_windows: int
    max_oos_drawdown: float
    max_oos_turnover: float
    min_oos_excess_return: float
    require_frozen_profile: bool = True
    require_validation_pass: bool = True
    require_holdout_pass: bool = True
    min_validation_excess_return: float = 0.0
    min_holdout_excess_return: float = 0.0


@dataclass(frozen=True)
class EvaluationConfig:
    profile_name: str
    warn_turnover: float
    fail_turnover: float
    warn_min_trade_count: int
    fail_min_trade_count: int
    warn_max_drawdown: float
    fail_max_drawdown: float
    warn_min_excess_return: float
    fail_min_excess_return: float
    flag_underperform_benchmark: bool
    fail_on_zero_trade_run: bool


@dataclass(frozen=True)
class AppConfig:
    run: RunConfig
    period: PeriodConfig
    data: DataConfig
    universe: UniverseConfig
    strategy: StrategyConfig
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    benchmark: BenchmarkConfig
    evaluation: EvaluationConfig
    validation: tuple[PeriodConfig, ...]
    research: ResearchConfig
    features: FeaturesConfig
    walkforward: WalkForwardConfig
    promotion: PromotionPolicyConfig


@dataclass(frozen=True)
class RuntimeOverrides:
    output_dir: Path | None = None
    staging_dir: Path | None = None
    canonical_dir: Path | None = None
    raw_dir: Path | None = None
    feature_dir: Path | None = None
    feature_set_name: str | None = None
    input_dataset_ref: Path | None = None
    feature_set_ref: Path | None = None
    control_profile: str | None = None
    disable_feature_materialization: bool = False
    force_precomputed_features: bool = False


def scope_app_config(config: AppConfig, scope_name: str) -> AppConfig:
    safe_scope = _safe_scope_name(scope_name)
    return replace(
        config,
        data=replace(
            config.data,
            staging_dir=config.data.staging_dir / safe_scope,
            canonical_dir=config.data.canonical_dir / safe_scope,
        ),
    )


def apply_runtime_overrides(config: AppConfig, overrides: RuntimeOverrides) -> AppConfig:
    feature_dir = overrides.feature_dir
    feature_set_name = overrides.feature_set_name
    if overrides.feature_set_ref is not None:
        feature_dir = overrides.feature_set_ref.parent
        feature_set_name = overrides.feature_set_ref.name

    data = replace(
        config.data,
        staging_dir=overrides.staging_dir or config.data.staging_dir,
        canonical_dir=overrides.input_dataset_ref or overrides.canonical_dir or config.data.canonical_dir,
        raw_dir=overrides.raw_dir or config.data.raw_dir,
    )
    research = config.research
    if overrides.control_profile is not None:
        research = replace(research, control_profile=overrides.control_profile)
    features = replace(
        config.features,
        feature_dir=feature_dir or config.features.feature_dir,
        set_name=feature_set_name or config.features.set_name,
        use_precomputed=(
            True
            if overrides.force_precomputed_features or overrides.feature_set_ref is not None
            else config.features.use_precomputed
        ),
        materialize_on_backtest=(
            False
            if overrides.disable_feature_materialization or overrides.feature_set_ref is not None
            else config.features.materialize_on_backtest
        ),
    )
    return replace(
        config,
        run=replace(config.run, output_dir=overrides.output_dir or config.run.output_dir),
        data=data,
        research=research,
        features=features,
    )


def load_config(path: str | Path, evaluation_profile: str | None = None) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)

    evaluation_payload = _resolve_evaluation_payload(payload, evaluation_profile)

    return AppConfig(
        run=RunConfig(
            name=payload["run"]["name"],
            initial_cash=float(payload["run"]["initial_cash"]),
            output_dir=Path(payload["run"]["output_dir"]),
        ),
        period=_load_period(payload.get("period"), default_label="full_sample"),
        data=DataConfig(
            source_name=payload["data"].get("source_name", "sample_csv"),
            source_bars_csv=Path(payload["data"]["source_bars_csv"]),
            source_instruments_csv=Path(payload["data"]["source_instruments_csv"]),
            download_instruments_csv=Path(payload["data"]["download_instruments_csv"])
            if payload["data"].get("download_instruments_csv")
            else None,
            download_exchange_code=str(payload["data"].get("download_exchange_code", "")),
            source_corporate_actions_csv=Path(payload["data"]["source_corporate_actions_csv"]),
            staging_dir=Path(payload["data"]["staging_dir"]),
            canonical_dir=Path(payload["data"]["canonical_dir"]),
            raw_dir=Path(payload["data"]["raw_dir"]),
            adjustment_policy=str(payload["data"].get("adjustment_policy", "raw_close")),
        ),
        universe=UniverseConfig(
            allowed_exchange_mic=tuple(payload["universe"]["allowed_exchange_mic"]),
            allowed_currency=payload["universe"]["allowed_currency"],
            active_only=bool(payload["universe"]["active_only"]),
            min_history_days=int(payload["universe"]["min_history_days"]),
            min_average_volume=float(payload["universe"]["min_average_volume"]),
            allowed_benchmark_buckets=tuple(payload["universe"].get("allowed_benchmark_buckets", [])),
            allowed_tradability_statuses=tuple(payload["universe"].get("allowed_tradability_statuses", [])),
            allowed_universe_buckets=tuple(payload["universe"].get("allowed_universe_buckets", [])),
            excluded_liquidity_buckets=tuple(payload["universe"].get("excluded_liquidity_buckets", [])),
        ),
        strategy=StrategyConfig(
            name=payload["strategy"]["name"],
            top_n=int(payload["strategy"]["top_n"]),
            weighting=payload["strategy"]["weighting"],
            ranking_mode=str(payload["strategy"].get("ranking_mode", "global")),
            score_transform=str(payload["strategy"].get("score_transform", "raw")),
            min_candidates_per_group=int(payload["strategy"].get("min_candidates_per_group", 1)),
            sma_cross=SmaCrossConfig(
                short_window=int(payload["strategy"]["sma_cross"]["short_window"]),
                long_window=int(payload["strategy"]["sma_cross"]["long_window"]),
                signal_threshold=float(payload["strategy"]["sma_cross"]["signal_threshold"]),
            ),
            cross_sectional_momentum=LookbackStrategyConfig(
                lookback_window=int(payload["strategy"]["cross_sectional_momentum"]["lookback_window"]),
                min_score=float(payload["strategy"]["cross_sectional_momentum"]["min_score"]),
                max_trailing_drawdown=float(
                    payload["strategy"]["cross_sectional_momentum"].get("max_trailing_drawdown", 1.0)
                ),
                drawdown_lookback_window=int(
                    payload["strategy"]["cross_sectional_momentum"].get("drawdown_lookback_window", 0)
                ),
            ),
            mean_reversion=LookbackStrategyConfig(
                lookback_window=int(payload["strategy"]["mean_reversion"]["lookback_window"]),
                min_score=float(payload["strategy"]["mean_reversion"]["min_score"]),
                max_trailing_drawdown=float(
                    payload["strategy"]["mean_reversion"].get("max_trailing_drawdown", 1.0)
                ),
                drawdown_lookback_window=int(
                    payload["strategy"]["mean_reversion"].get("drawdown_lookback_window", 0)
                ),
            ),
        ),
        portfolio=PortfolioConfig(
            cash_buffer_pct=float(payload["portfolio"]["cash_buffer_pct"]),
            target_gross_exposure=float(
                payload["portfolio"].get(
                    "target_gross_exposure",
                    1.0 - float(payload["portfolio"]["cash_buffer_pct"]),
                )
            ),
            max_position_weight=float(payload["portfolio"]["max_position_weight"]),
            rebalance_threshold_bps=float(payload["portfolio"]["rebalance_threshold_bps"]),
            rebalance_frequency_days=int(payload["portfolio"].get("rebalance_frequency_days", 1)),
            max_rebalance_turnover_pct=float(payload["portfolio"].get("max_rebalance_turnover_pct", 1.0)),
            initial_deployment_turnover_pct=float(
                payload["portfolio"].get(
                    "initial_deployment_turnover_pct",
                    payload["portfolio"].get("max_rebalance_turnover_pct", 1.0),
                )
            ),
            selection_buffer_slots=int(payload["portfolio"].get("selection_buffer_slots", 0)),
            max_positions_per_sector=int(payload["portfolio"].get("max_positions_per_sector", 0)),
            min_holding_days=int(payload["portfolio"].get("min_holding_days", 0)),
            adv_window_days=int(payload["portfolio"]["adv_window_days"]),
            max_target_adv_participation=float(payload["portfolio"]["max_target_adv_participation"]),
            volatility_target=float(payload["portfolio"].get("volatility_target", 0.0)),
            volatility_lookback_days=int(payload["portfolio"].get("volatility_lookback_days", 20)),
            drawdown_reduce_threshold=float(payload["portfolio"].get("drawdown_reduce_threshold", 0.0)),
            drawdown_reduced_gross_exposure=float(payload["portfolio"].get("drawdown_reduced_gross_exposure", 0.0)),
            drawdown_force_rebalance=bool(payload["portfolio"].get("drawdown_force_rebalance", False)),
            benchmark_regime_window_days=int(payload["portfolio"].get("benchmark_regime_window_days", 0)),
            benchmark_regime_min_return=float(payload["portfolio"].get("benchmark_regime_min_return", 0.0)),
            benchmark_regime_reduced_gross_exposure=float(
                payload["portfolio"].get("benchmark_regime_reduced_gross_exposure", 0.0)
            ),
            benchmark_regime_force_rebalance=bool(payload["portfolio"].get("benchmark_regime_force_rebalance", False)),
            max_positions_per_industry=int(payload["portfolio"].get("max_positions_per_industry", 0)),
            max_positions_per_benchmark_bucket=int(
                payload["portfolio"].get("max_positions_per_benchmark_bucket", 0)
            ),
        ),
        execution=ExecutionConfig(
            fill_model=payload["execution"]["fill_model"],
            commission_bps=float(payload["execution"]["commission_bps"]),
            slippage_bps=float(payload["execution"]["slippage_bps"]),
            spread_bps=float(payload["execution"]["spread_bps"]),
            stamp_duty_bps=float(payload["execution"]["stamp_duty_bps"]),
            max_participation_rate=float(payload["execution"]["max_participation_rate"]),
            allow_partial_fills=bool(payload["execution"]["allow_partial_fills"]),
        ),
        benchmark=BenchmarkConfig(
            models=tuple(payload["benchmark"]["models"]),
            primary=payload["benchmark"]["primary"],
        ),
        evaluation=EvaluationConfig(
            profile_name=evaluation_payload["profile_name"],
            warn_turnover=float(evaluation_payload["warn_turnover"]),
            fail_turnover=float(evaluation_payload["fail_turnover"]),
            warn_min_trade_count=int(evaluation_payload["warn_min_trade_count"]),
            fail_min_trade_count=int(evaluation_payload["fail_min_trade_count"]),
            warn_max_drawdown=float(evaluation_payload["warn_max_drawdown"]),
            fail_max_drawdown=float(evaluation_payload["fail_max_drawdown"]),
            warn_min_excess_return=float(evaluation_payload["warn_min_excess_return"]),
            fail_min_excess_return=float(evaluation_payload["fail_min_excess_return"]),
            flag_underperform_benchmark=bool(evaluation_payload["flag_underperform_benchmark"]),
            fail_on_zero_trade_run=bool(evaluation_payload["fail_on_zero_trade_run"]),
        ),
        validation=_load_validation_periods(payload.get("validation")),
        research=ResearchConfig(
            profile_name=str(payload.get("research", {}).get("profile_name", "default")),
            profile_version=str(payload.get("research", {}).get("profile_version", "unversioned")),
            frozen_on=_parse_optional_date(payload.get("research", {}).get("frozen_on")),
            promoted=bool(payload.get("research", {}).get("promoted", False)),
            research_tranche=str(payload.get("research", {}).get("research_tranche", "")),
            research_slice_name=str(payload.get("research", {}).get("research_slice_name", "all")),
            control_profile=str(payload.get("research", {}).get("control_profile", "")),
            promotion_candidate=bool(payload.get("research", {}).get("promotion_candidate", False)),
        ),
        features=FeaturesConfig(
            enabled=bool(payload.get("features", {}).get("enabled", False)),
            feature_dir=Path(payload.get("features", {}).get("feature_dir", "data/features")),
            set_name=str(
                payload.get("features", {}).get(
                    "set_name",
                    payload.get("research", {}).get("profile_name", payload["run"]["name"]),
                )
            ),
            use_precomputed=bool(payload.get("features", {}).get("use_precomputed", False)),
            materialize_on_backtest=bool(payload.get("features", {}).get("materialize_on_backtest", True)),
        ),
        walkforward=WalkForwardConfig(
            enabled=bool(payload.get("walkforward", {}).get("enabled", False)),
            train_days=int(payload.get("walkforward", {}).get("train_days", 756)),
            test_days=int(payload.get("walkforward", {}).get("test_days", 252)),
            step_days=int(payload.get("walkforward", {}).get("step_days", 252)),
            anchored=bool(payload.get("walkforward", {}).get("anchored", True)),
        ),
        promotion=PromotionPolicyConfig(
            min_pass_windows=int(payload.get("promotion", {}).get("min_pass_windows", 2)),
            min_windows=int(payload.get("promotion", {}).get("min_windows", 3)),
            max_oos_drawdown=float(payload.get("promotion", {}).get("max_oos_drawdown", 0.20)),
            max_oos_turnover=float(payload.get("promotion", {}).get("max_oos_turnover", 3.0)),
            min_oos_excess_return=float(payload.get("promotion", {}).get("min_oos_excess_return", 0.0)),
            require_frozen_profile=bool(payload.get("promotion", {}).get("require_frozen_profile", True)),
            require_validation_pass=bool(payload.get("promotion", {}).get("require_validation_pass", True)),
            require_holdout_pass=bool(payload.get("promotion", {}).get("require_holdout_pass", True)),
            min_validation_excess_return=float(payload.get("promotion", {}).get("min_validation_excess_return", 0.0)),
            min_holdout_excess_return=float(payload.get("promotion", {}).get("min_holdout_excess_return", 0.0)),
        ),
    )


def _resolve_evaluation_payload(payload: dict[str, object], evaluation_profile: str | None) -> dict[str, object]:
    profiles = payload.get("evaluation_profiles", {})
    if evaluation_profile is not None:
        if not isinstance(profiles, dict) or evaluation_profile not in profiles:
            available = sorted(profiles.keys()) if isinstance(profiles, dict) else []
            raise ValueError(
                f"Unknown evaluation profile '{evaluation_profile}'. Available profiles: {', '.join(available) or 'none'}"
            )
        selected = dict(profiles[evaluation_profile])
        selected["profile_name"] = evaluation_profile
        return selected

    selected = dict(payload["evaluation"])
    selected["profile_name"] = "default"
    return selected


def available_evaluation_profiles(path: str | Path) -> list[str]:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    profiles = payload.get("evaluation_profiles", {})
    if not isinstance(profiles, dict):
        return []
    return sorted(str(name) for name in profiles.keys())


def apply_period(config: AppConfig, period: PeriodConfig, run_name: str | None = None) -> AppConfig:
    return replace(
        config,
        run=replace(config.run, name=run_name or config.run.name),
        period=period,
    )


def _load_period(payload: object, default_label: str) -> PeriodConfig:
    if not isinstance(payload, dict):
        return PeriodConfig(label=default_label, start_date=None, end_date=None)

    return PeriodConfig(
        label=str(payload.get("label", default_label)),
        start_date=_parse_optional_date(payload.get("start_date")),
        end_date=_parse_optional_date(payload.get("end_date")),
    )


def _load_validation_periods(payload: object) -> tuple[PeriodConfig, ...]:
    if not isinstance(payload, dict):
        return ()

    periods: list[PeriodConfig] = []
    for key, period_payload in payload.items():
        if isinstance(period_payload, dict):
            periods.append(_load_period(period_payload, default_label=key))
    return tuple(periods)


def _parse_optional_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value))


def _safe_scope_name(scope_name: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in scope_name)
    return safe or "default"
