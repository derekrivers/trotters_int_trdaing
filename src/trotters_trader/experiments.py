from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from trotters_trader.backtest import BacktestResult, run_backtest
from datetime import timedelta

from trotters_trader.config import AppConfig, PeriodConfig, PromotionPolicyConfig, apply_period
from trotters_trader.data import load_instruments
from trotters_trader.features import ensure_feature_set
from trotters_trader.reports import (
    write_comparison_report,
    write_experiment_index,
    write_operability_program_report,
    write_promotion_artifacts,
    write_tranche_report,
)
from trotters_trader.run_metadata import classify_run_name

BATCH_PRESETS = (
    "universe-slice",
    "ranking",
    "construction",
    "risk",
    "regime",
    "sector",
    "operability",
)


def run_sma_grid(config: AppConfig) -> list[BacktestResult]:
    parameter_sets = [
        (3, 5),
        (4, 8),
        (5, 10),
    ]
    results: list[BacktestResult] = []

    for short_window, long_window in parameter_sets:
        run_name = f"{config.run.name}_s{short_window}_l{long_window}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                sma_cross=replace(
                    config.strategy.sma_cross,
                    short_window=short_window,
                    long_window=long_window,
                ),
            ),
        )
        results.append(run_backtest(experiment_config))

    return results


def run_strategy_comparison(config: AppConfig) -> list[BacktestResult]:
    variants = [
        "sma_cross",
        "cross_sectional_momentum",
        "mean_reversion",
    ]
    results: list[BacktestResult] = []

    for strategy_name in variants:
        run_name = f"{config.run.name}_{strategy_name}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                name=strategy_name,
            ),
        )
        results.append(run_backtest(experiment_config))

    return results


def run_evaluation_profile_comparison(configs: list[AppConfig]) -> list[BacktestResult]:
    results: list[BacktestResult] = []
    variants = [
        "sma_cross",
        "cross_sectional_momentum",
        "mean_reversion",
    ]

    for config in configs:
        for strategy_name in variants:
            run_name = f"{config.run.name}_profile-{config.evaluation.profile_name}_{strategy_name}"
            experiment_config = replace(
                config,
                run=replace(config.run, name=run_name),
                strategy=replace(config.strategy, name=strategy_name),
            )
            results.append(run_backtest(experiment_config))

    return results


def run_benchmark_comparison(config: AppConfig) -> list[BacktestResult]:
    results: list[BacktestResult] = []
    variants = [
        "sma_cross",
        "cross_sectional_momentum",
        "mean_reversion",
    ]

    for benchmark_name in config.benchmark.models:
        benchmark_config = replace(
            config,
            benchmark=replace(config.benchmark, primary=benchmark_name),
        )
        for strategy_name in variants:
            run_name = f"{config.run.name}_bench-{benchmark_name}_{strategy_name}"
            experiment_config = replace(
                benchmark_config,
                run=replace(config.run, name=run_name),
                strategy=replace(config.strategy, name=strategy_name),
            )
            results.append(run_backtest(experiment_config))

    return results


def run_sensitivity_matrix(config: AppConfig) -> list[BacktestResult]:
    weightings = ["equal", "vol_inverse"]
    max_position_weights = [0.20, 0.25]
    cash_buffers = [0.02, 0.05]
    spread_bps_values = [8.0, 15.0]
    slippage_bps_values = [5.0, 10.0]

    results: list[BacktestResult] = []

    for weighting in weightings:
        for max_position_weight in max_position_weights:
            for cash_buffer in cash_buffers:
                for spread_bps in spread_bps_values:
                    for slippage_bps in slippage_bps_values:
                        run_name = (
                            f"{config.run.name}_sens"
                            f"_w-{weighting}"
                            f"_mpw-{str(max_position_weight).replace('.', '')}"
                            f"_cb-{str(cash_buffer).replace('.', '')}"
                            f"_sp-{int(spread_bps)}"
                            f"_sl-{int(slippage_bps)}"
                        )
                        experiment_config = replace(
                            config,
                            run=replace(config.run, name=run_name),
                            strategy=replace(config.strategy, weighting=weighting),
                            portfolio=replace(
                                config.portfolio,
                                max_position_weight=max_position_weight,
                                cash_buffer_pct=cash_buffer,
                            ),
                            execution=replace(
                                config.execution,
                                spread_bps=spread_bps,
                                slippage_bps=slippage_bps,
                            ),
                        )
                        results.append(run_backtest(experiment_config))

    return results


def run_threshold_sweep(config: AppConfig) -> list[BacktestResult]:
    results: list[BacktestResult] = []

    sma_thresholds = [0.0, 0.001, 0.005]
    momentum_thresholds = [0.0, 0.02, 0.05]
    mean_reversion_thresholds = [0.0, 0.05, 0.10]

    for threshold in sma_thresholds:
        run_name = f"{config.run.name}_thr_sma_{str(threshold).replace('.', '')}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                name="sma_cross",
                sma_cross=replace(config.strategy.sma_cross, signal_threshold=threshold),
            ),
        )
        results.append(run_backtest(experiment_config))

    for threshold in momentum_thresholds:
        run_name = f"{config.run.name}_thr_mom_{str(threshold).replace('.', '')}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                name="cross_sectional_momentum",
                cross_sectional_momentum=replace(
                    config.strategy.cross_sectional_momentum,
                    min_score=threshold,
                ),
            ),
        )
        results.append(run_backtest(experiment_config))

    for threshold in mean_reversion_thresholds:
        run_name = f"{config.run.name}_thr_mr_{str(threshold).replace('.', '')}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                name="mean_reversion",
                mean_reversion=replace(config.strategy.mean_reversion, min_score=threshold),
            ),
        )
        results.append(run_backtest(experiment_config))

    return results


def run_momentum_sweep(config: AppConfig) -> list[BacktestResult]:
    results: list[BacktestResult] = []

    top_n_values = [3, 4, 5]
    min_score_values = [0.03, 0.05, 0.07]
    rebalance_frequency_values = [21, 42, 63]

    for top_n in top_n_values:
        for min_score in min_score_values:
            for rebalance_frequency_days in rebalance_frequency_values:
                run_name = (
                    f"{config.run.name}_mom"
                    f"_n-{top_n}"
                    f"_ms-{str(min_score).replace('.', '')}"
                    f"_rf-{rebalance_frequency_days}"
                )
                experiment_config = replace(
                    config,
                    run=replace(config.run, name=run_name),
                    strategy=replace(
                        config.strategy,
                        name="cross_sectional_momentum",
                        top_n=top_n,
                        cross_sectional_momentum=replace(
                            config.strategy.cross_sectional_momentum,
                            min_score=min_score,
                        ),
                    ),
                    portfolio=replace(
                        config.portfolio,
                        rebalance_frequency_days=rebalance_frequency_days,
                    ),
                )
                results.append(run_backtest(experiment_config))

    return results


def run_momentum_refinement_sweep(config: AppConfig) -> list[BacktestResult]:
    results: list[BacktestResult] = []

    top_n_values = [2, 3, 4]
    min_score_values = [0.02, 0.03]
    rebalance_frequency_values = [42, 63]

    for top_n in top_n_values:
        for min_score in min_score_values:
            for rebalance_frequency_days in rebalance_frequency_values:
                run_name = (
                    f"{config.run.name}_momref"
                    f"_n-{top_n}"
                    f"_ms-{str(min_score).replace('.', '')}"
                    f"_rf-{rebalance_frequency_days}"
                )
                experiment_config = replace(
                    config,
                    run=replace(config.run, name=run_name),
                    strategy=replace(
                        config.strategy,
                        name="cross_sectional_momentum",
                        top_n=top_n,
                        cross_sectional_momentum=replace(
                            config.strategy.cross_sectional_momentum,
                            min_score=min_score,
                        ),
                    ),
                    portfolio=replace(
                        config.portfolio,
                        rebalance_frequency_days=rebalance_frequency_days,
                    ),
                )
                results.append(run_backtest(experiment_config))

    return results


def run_momentum_profile_comparison(config: AppConfig) -> list[BacktestResult]:
    profiles = {
        "aggressive": {
            "top_n": 3,
            "min_score": 0.03,
            "rebalance_frequency_days": 42,
            "cash_buffer_pct": 0.08,
            "max_position_weight": 0.08,
            "max_rebalance_turnover_pct": 0.08,
            "selection_buffer_slots": 2,
            "min_holding_days": 63,
        },
        "balanced": {
            "top_n": 4,
            "min_score": 0.03,
            "rebalance_frequency_days": 63,
            "cash_buffer_pct": 0.10,
            "max_position_weight": 0.07,
            "max_rebalance_turnover_pct": 0.06,
            "selection_buffer_slots": 3,
            "min_holding_days": 84,
        },
        "defensive": {
            "top_n": 2,
            "min_score": 0.05,
            "rebalance_frequency_days": 84,
            "cash_buffer_pct": 0.12,
            "max_position_weight": 0.06,
            "max_rebalance_turnover_pct": 0.04,
            "selection_buffer_slots": 3,
            "min_holding_days": 105,
        },
    }

    results: list[BacktestResult] = []
    for profile_name, profile in profiles.items():
        run_name = f"{config.run.name}_momprof_{profile_name}"
        experiment_config = replace(
            config,
            run=replace(config.run, name=run_name),
            strategy=replace(
                config.strategy,
                name="cross_sectional_momentum",
                top_n=int(profile["top_n"]),
                cross_sectional_momentum=replace(
                    config.strategy.cross_sectional_momentum,
                    min_score=float(profile["min_score"]),
                ),
            ),
            portfolio=replace(
                config.portfolio,
                cash_buffer_pct=float(profile["cash_buffer_pct"]),
                max_position_weight=float(profile["max_position_weight"]),
                rebalance_frequency_days=int(profile["rebalance_frequency_days"]),
                max_rebalance_turnover_pct=float(profile["max_rebalance_turnover_pct"]),
                selection_buffer_slots=int(profile["selection_buffer_slots"]),
                min_holding_days=int(profile["min_holding_days"]),
            ),
        )
        results.append(run_backtest(experiment_config))

    return results


def run_validation_split(config: AppConfig) -> list[BacktestResult]:
    if not config.validation:
        raise ValueError("validation split is not configured")

    results: list[BacktestResult] = []
    for period in config.validation:
        run_name = f"{config.run.name}_split-{period.label}"
        experiment_config = apply_period(config, period, run_name=run_name)
        results.append(run_backtest(experiment_config))
    return results


def run_risk_sweep(config: AppConfig) -> list[BacktestResult]:
    if not config.validation:
        raise ValueError("validation split is not configured")

    scenarios = _risk_scenarios(config, include_baseline=True)

    results: list[BacktestResult] = []
    for scenario_name, scenario in scenarios:
        scenario_config = replace(
            config,
            run=replace(config.run, name=f"{config.run.name}_risk_{scenario_name}"),
            strategy=replace(config.strategy, top_n=int(scenario["top_n"])),
            portfolio=replace(
                config.portfolio,
                cash_buffer_pct=float(scenario["cash_buffer_pct"]),
                target_gross_exposure=float(scenario["target_gross_exposure"]),
                max_position_weight=float(scenario["max_position_weight"]),
                initial_deployment_turnover_pct=float(scenario["initial_deployment_turnover_pct"]),
            ),
        )
        for period in config.validation:
            run_name = f"{scenario_config.run.name}_split-{period.label}"
            experiment_config = apply_period(scenario_config, period, run_name=run_name)
            results.append(run_backtest(experiment_config))

    return results


def run_regime_sweep(config: AppConfig) -> list[BacktestResult]:
    if not config.validation:
        raise ValueError("validation split is not configured")

    scenarios = _regime_scenarios(include_off=True)

    results: list[BacktestResult] = []
    for scenario_name, scenario in scenarios:
        scenario_config = replace(
            config,
            run=replace(config.run, name=f"{config.run.name}_regime_{scenario_name}"),
            portfolio=replace(
                config.portfolio,
                benchmark_regime_window_days=int(scenario["benchmark_regime_window_days"]),
                benchmark_regime_min_return=float(scenario["benchmark_regime_min_return"]),
                benchmark_regime_reduced_gross_exposure=float(scenario["benchmark_regime_reduced_gross_exposure"]),
                benchmark_regime_force_rebalance=bool(scenario["benchmark_regime_force_rebalance"]),
            ),
        )
        for period in config.validation:
            run_name = f"{scenario_config.run.name}_split-{period.label}"
            experiment_config = apply_period(scenario_config, period, run_name=run_name)
            results.append(run_backtest(experiment_config))

    return results


def run_sector_sweep(config: AppConfig) -> list[BacktestResult]:
    if not config.validation:
        raise ValueError("validation split is not configured")

    scenarios = _sector_scenarios(include_off=True)

    results: list[BacktestResult] = []
    for scenario_name, max_positions_per_sector in scenarios:
        scenario_config = replace(
            config,
            run=replace(config.run, name=f"{config.run.name}_sector_{scenario_name}"),
            portfolio=replace(
                config.portfolio,
                max_positions_per_sector=max_positions_per_sector,
            ),
        )
        for period in config.validation:
            run_name = f"{scenario_config.run.name}_split-{period.label}"
            experiment_config = apply_period(scenario_config, period, run_name=run_name)
            results.append(run_backtest(experiment_config))

    return results


def run_walkforward_validation(config: AppConfig) -> list[BacktestResult]:
    windows = _walkforward_windows(config)
    results: list[BacktestResult] = []
    for index, window in enumerate(windows, start=1):
        run_name = f"{config.run.name}_wf_{index:02d}_{window.label}"
        experiment_config = apply_period(config, window, run_name=run_name)
        result = run_backtest(experiment_config)
        result.analytics["walkforward_window"] = {
            "index": index,
            "label": window.label,
            "start_date": None if window.start_date is None else window.start_date.isoformat(),
            "end_date": None if window.end_date is None else window.end_date.isoformat(),
        }
        results.append(result)
    return results


def run_promotion_check(config: AppConfig) -> dict[str, object]:
    validation_results = run_validation_split(config) if config.validation else []
    walkforward_results = run_walkforward_validation(config) if config.walkforward.enabled else []
    promotion_decision = summarize_promotion_readiness(
        config,
        validation_results,
        walkforward_results,
    )
    return {
        "validation_results": validation_results,
        "walkforward_results": walkforward_results,
        "promotion_decision": promotion_decision,
    }


def run_universe_slice_sweep(config: AppConfig) -> dict[str, object]:
    scenarios = _universe_slice_scenarios(config)
    return _run_research_tranche(
        config=config,
        tranche_name="universe_slice",
        scenario_label="slice",
        scenarios=scenarios,
        control_label="control",
        output_report_name=f"{config.run.name}_universe_slice_report",
    )


def run_ranking_sweep(config: AppConfig) -> dict[str, object]:
    scenarios = _ranking_scenarios()
    return _run_research_tranche(
        config=config,
        tranche_name="ranking",
        scenario_label="ranking",
        scenarios=scenarios,
        control_label="control",
        output_report_name=f"{config.run.name}_ranking_report",
    )


def run_construction_sweep(config: AppConfig) -> dict[str, object]:
    scenarios = _construction_scenarios()
    return _run_research_tranche(
        config=config,
        tranche_name="construction",
        scenario_label="construct",
        scenarios=scenarios,
        control_label="control",
        output_report_name=f"{config.run.name}_construction_report",
    )


def run_starter_tranche(config: AppConfig) -> dict[str, object]:
    universe_slice = run_universe_slice_sweep(config)
    ranking_seed = _tranche_seed_config(config, universe_slice)
    ranking = run_ranking_sweep(ranking_seed)
    construction_seed = _tranche_seed_config(ranking_seed, ranking)
    construction = run_construction_sweep(construction_seed)

    final_candidate = construction.get("top_candidate") or ranking.get("top_candidate") or universe_slice.get("top_candidate")
    final_decision = {
        "recommended_action": "open_secondary_research_program",
        "reason": "no_promotion_eligible_momentum_candidate",
    }
    promotion_artifacts: dict[str, str] | None = None

    if isinstance(final_candidate, dict) and bool(final_candidate.get("eligible", False)):
        final_decision = {
            "recommended_action": "promote_candidate",
            "reason": "candidate_passed_promotion_check",
            "profile_name": final_candidate.get("profile_name"),
            "profile_version": final_candidate.get("profile_version"),
            "run_name": final_candidate.get("run_name"),
        }
        promotion_payload = dict(final_candidate.get("promotion_decision", {}))
        if promotion_payload:
            promotion_artifacts = write_promotion_artifacts(
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_starter_tranche_promotion_report",
                promotion_decision=promotion_payload,
                config_path=f"generated:{final_candidate.get('profile_name', 'candidate')}",
            )

    tranche_artifacts = write_tranche_report(
        output_dir=config.run.output_dir,
        report_name=f"{config.run.name}_starter_tranche_report",
        tranche_name="starter_tranche",
        control_row=universe_slice["control"],
        candidate_rows=[
            universe_slice["top_candidate"],
            ranking["top_candidate"],
            construction["top_candidate"],
        ],
        decision={
            "recommended_action": final_decision["recommended_action"],
            "reason": final_decision["reason"],
            "selected_run_name": None if not isinstance(final_candidate, dict) else final_candidate.get("run_name"),
            "selected_profile_name": None if not isinstance(final_candidate, dict) else final_candidate.get("profile_name"),
            "top_candidate_eligible": False if not isinstance(final_candidate, dict) else bool(final_candidate.get("eligible", False)),
            "tranche_results": {
                "universe_slice": universe_slice["decision"],
                "ranking": ranking["decision"],
                "construction": construction["decision"],
            },
        },
    )
    return {
        "universe_slice": universe_slice,
        "ranking": ranking,
        "construction": construction,
        "starter_tranche_report": tranche_artifacts,
        "promotion_artifacts": promotion_artifacts or {},
        "final_decision": final_decision,
    }


def run_operability_program(config: AppConfig) -> dict[str, object]:
    focused = _run_operability_tranche(
        config=config,
        tranche_name="operability",
        scenario_label="operability",
        scenarios=_operability_scenarios(config),
        output_report_name=f"{config.run.name}_operability_report",
    )
    control_row = focused["control"]
    pivot_result: dict[str, object] | None = None
    pivot_used = not bool(focused["decision"].get("focused_success", False))
    pivot_seed = _candidate_row_config(config, focused.get("top_candidate")) if focused.get("top_candidate") else config
    if pivot_used:
        pivot_result = _run_operability_tranche(
            config=pivot_seed,
            tranche_name="benchmark_pivot",
            scenario_label="pivot",
            scenarios=_benchmark_pivot_scenarios(pivot_seed),
            output_report_name=f"{config.run.name}_benchmark_pivot_report",
            control_row=control_row,
        )

    candidate_pool = list(focused["candidates"])
    if pivot_result:
        candidate_pool.extend(pivot_result["candidates"])
    shortlisted = _operability_shortlist(control_row, candidate_pool, limit=3)
    stress_results = [
        _evaluate_stress_pack(control_row, _candidate_row_config(config, candidate_row), candidate_row)
        for candidate_row in shortlisted
    ]
    stress_by_run = {
        str(result["candidate_run_name"]): result
        for result in stress_results
    }
    ranked_shortlist = sorted(
        shortlisted,
        key=lambda row: (
            bool(stress_by_run.get(str(row.get("run_name")), {}).get("stress_ok", False)),
            row.get("decision_score", _candidate_decision_score(row)),
        ),
        reverse=True,
    )
    selected_candidate = ranked_shortlist[0] if ranked_shortlist else None
    selected_stress = None if selected_candidate is None else stress_by_run.get(str(selected_candidate.get("run_name")))
    promotion_artifacts: dict[str, str] = {}
    recommended_action = "continue_research"
    reason = "no_stress_validated_candidate"
    if selected_candidate is not None:
        stress_ok = bool(selected_stress and selected_stress.get("stress_ok", False))
        if bool(selected_candidate.get("eligible", False)) and stress_ok:
            recommended_action = "freeze_candidate"
            reason = "candidate_passed_promotion_and_stress_pack"
            promotion_artifacts = write_promotion_artifacts(
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_operability_promotion_report",
                promotion_decision=dict(selected_candidate.get("promotion_decision", {})),
                config_path=f"generated:{selected_candidate.get('profile_name', 'candidate')}",
            )
        elif pivot_used:
            recommended_action = "continue_benchmark_pivot"
            reason = "focused_tranche_failed_stop_rule"
        else:
            recommended_action = "continue_focused_research"
            reason = "candidate_not_yet_promotion_eligible_or_stress_ok"

    final_decision = {
        "recommended_action": recommended_action,
        "reason": reason,
        "control_run_name": control_row.get("run_name"),
        "control_profile_name": control_row.get("profile_name"),
        "focused_selected_run_name": focused["decision"].get("selected_run_name"),
        "pivot_used": pivot_used,
        "pivot_selected_run_name": None if pivot_result is None else pivot_result["decision"].get("selected_run_name"),
        "selected_run_name": None if selected_candidate is None else selected_candidate.get("run_name"),
        "selected_profile_name": None if selected_candidate is None else selected_candidate.get("profile_name"),
        "selected_candidate_eligible": False if selected_candidate is None else bool(selected_candidate.get("eligible", False)),
        "selected_stress_ok": False if selected_stress is None else bool(selected_stress.get("stress_ok", False)),
        "shortlist_count": len(shortlisted),
    }
    report_artifacts = write_operability_program_report(
        output_dir=config.run.output_dir,
        report_name=f"{config.run.name}_operability_program",
        control_row=control_row,
        focused_result=focused,
        pivot_result=pivot_result,
        shortlisted=ranked_shortlist,
        stress_results=stress_results,
        final_decision=final_decision,
    )
    return {
        "control": control_row,
        "focused_tranche": focused,
        "pivot_tranche": pivot_result,
        "shortlisted_candidates": ranked_shortlist,
        "stress_results": stress_results,
        "program_report": report_artifacts,
        "promotion_artifacts": promotion_artifacts,
        "final_decision": final_decision,
    }


def build_research_batch_jobs(
    config: AppConfig,
    config_path: str | Path,
    batch_preset: str,
    *,
    include_control: bool = True,
    priority_start: int = 100,
) -> list[dict[str, object]]:
    tranche_name, label, scenarios = _batch_preset_definition(config, batch_preset)
    specs: list[dict[str, object]] = []
    next_priority = priority_start
    if include_control:
        specs.append(
            {
                "command": "promotion-check",
                "config_path": str(config_path),
                "priority": next_priority,
                "research_variant": {
                    "kind": "control",
                    "tranche_name": tranche_name,
                    "scenario_name": "control",
                    "scenario_label": label,
                },
            }
        )
        next_priority += 1
    for scenario_name, overrides in scenarios:
        specs.append(
            {
                "command": "promotion-check",
                "config_path": str(config_path),
                "priority": next_priority,
                "research_variant": {
                    "kind": "candidate",
                    "tranche_name": tranche_name,
                    "scenario_name": scenario_name,
                    "scenario_label": label,
                    "overrides": overrides,
                },
            }
        )
        next_priority += 1
    return specs


def apply_research_variant(config: AppConfig, research_variant: dict[str, object]) -> AppConfig:
    kind = str(research_variant.get("kind", "candidate"))
    tranche_name = str(research_variant.get("tranche_name", "")).replace("-", "_")
    scenario_name = str(research_variant.get("scenario_name", "variant"))
    label = str(research_variant.get("scenario_label", scenario_label(tranche_name)))
    if kind == "control":
        run_name = f"{config.run.name}_{label}_{scenario_name}"
        return replace(config, run=replace(config.run, name=run_name))
    overrides = research_variant.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("research_variant.overrides must be a JSON object when provided")
    return _candidate_config(config, tranche_name, scenario_name, overrides)


def summarize_walkforward_promotion(
    results: list[BacktestResult],
    policy: PromotionPolicyConfig,
) -> dict[str, object]:
    window_count = len(results)
    pass_count = sum(1 for result in results if result.analytics.get("evaluation", {}).get("status") == "pass")
    average_excess_return = 0.0
    average_drawdown = 0.0
    average_turnover = 0.0
    if results:
        average_excess_return = sum(
            float(result.analytics.get("evaluation", {}).get("excess_return", 0.0) or 0.0)
            for result in results
        ) / window_count
        average_drawdown = sum(float(result.summary.get("max_drawdown", 0.0) or 0.0) for result in results) / window_count
        average_turnover = sum(float(result.summary.get("turnover", 0.0) or 0.0) for result in results) / window_count
    eligible = (
        window_count >= policy.min_windows
        and pass_count >= policy.min_pass_windows
        and average_excess_return >= policy.min_oos_excess_return
        and average_drawdown <= policy.max_oos_drawdown
        and average_turnover <= policy.max_oos_turnover
    )
    return {
        "eligible": eligible,
        "window_count": window_count,
        "pass_windows": pass_count,
        "average_excess_return": average_excess_return,
        "average_drawdown": average_drawdown,
        "average_turnover": average_turnover,
        "policy": {
            "min_pass_windows": policy.min_pass_windows,
            "min_windows": policy.min_windows,
            "max_oos_drawdown": policy.max_oos_drawdown,
            "max_oos_turnover": policy.max_oos_turnover,
            "min_oos_excess_return": policy.min_oos_excess_return,
        },
    }


def summarize_promotion_readiness(
    config: AppConfig,
    validation_results: list[BacktestResult],
    walkforward_results: list[BacktestResult],
) -> dict[str, object]:
    split_results = {
        str(result.analytics.get("period", {}).get("label", "full_sample")): result
        for result in validation_results
    }
    walkforward_summary = summarize_walkforward_promotion(walkforward_results, config.promotion)
    fail_reasons: list[str] = []

    validation_result = split_results.get("validation")
    holdout_result = split_results.get("holdout")

    if config.promotion.require_frozen_profile:
        if config.research.frozen_on is None:
            fail_reasons.append("profile_not_frozen")
        if not config.research.profile_version or config.research.profile_version == "unversioned":
            fail_reasons.append("profile_not_versioned")

    if not walkforward_summary.get("eligible", False):
        fail_reasons.append("walkforward_evidence_insufficient")

    if config.promotion.require_validation_pass:
        if validation_result is None:
            fail_reasons.append("validation_period_missing")
        elif str(validation_result.analytics.get("evaluation", {}).get("status", "unknown")) != "pass":
            fail_reasons.append("validation_not_pass")

    if validation_result is not None:
        validation_excess = float(validation_result.analytics.get("evaluation", {}).get("excess_return", 0.0) or 0.0)
        if validation_excess < config.promotion.min_validation_excess_return:
            fail_reasons.append("validation_excess_below_threshold")

    if config.promotion.require_holdout_pass:
        if holdout_result is None:
            fail_reasons.append("holdout_period_missing")
        elif str(holdout_result.analytics.get("evaluation", {}).get("status", "unknown")) != "pass":
            fail_reasons.append("holdout_not_pass")

    if holdout_result is not None:
        holdout_excess = float(holdout_result.analytics.get("evaluation", {}).get("excess_return", 0.0) or 0.0)
        if holdout_excess < config.promotion.min_holdout_excess_return:
            fail_reasons.append("holdout_excess_below_threshold")

    unique_fail_reasons = list(dict.fromkeys(fail_reasons))
    eligible = not unique_fail_reasons
    current_promoted = bool(config.research.promoted)
    if eligible and not current_promoted:
        recommended_action = "promote"
    elif not eligible and current_promoted:
        recommended_action = "demote"
    else:
        recommended_action = "retain"

    return {
        "eligible": eligible,
        "recommended_action": recommended_action,
        "current_promoted": current_promoted,
        "profile": {
            "profile_name": config.research.profile_name,
            "profile_version": config.research.profile_version,
            "frozen_on": None if config.research.frozen_on is None else config.research.frozen_on.isoformat(),
        },
        "split_summary": {
            label: _split_result_summary(result)
            for label, result in split_results.items()
        },
        "walkforward_summary": walkforward_summary,
        "policy": {
            "min_pass_windows": config.promotion.min_pass_windows,
            "min_windows": config.promotion.min_windows,
            "max_oos_drawdown": config.promotion.max_oos_drawdown,
            "max_oos_turnover": config.promotion.max_oos_turnover,
            "min_oos_excess_return": config.promotion.min_oos_excess_return,
            "require_frozen_profile": config.promotion.require_frozen_profile,
            "require_validation_pass": config.promotion.require_validation_pass,
            "require_holdout_pass": config.promotion.require_holdout_pass,
            "min_validation_excess_return": config.promotion.min_validation_excess_return,
            "min_holdout_excess_return": config.promotion.min_holdout_excess_return,
        },
        "fail_reasons": unique_fail_reasons,
    }


def write_experiment_comparison(
    results: list[BacktestResult],
    output_dir: Path,
    report_name: str,
    quality_gate: str = "all",
) -> dict[str, str]:
    rows = [_comparison_row(result) for result in results]
    outputs = write_comparison_report(
        output_dir=output_dir,
        report_name=report_name,
        rows=rows,
        quality_gate=quality_gate,
    )
    outputs["index_md"] = write_experiment_index(
        output_dir=output_dir,
        report_name=report_name,
        rows=rows,
        quality_gate=quality_gate,
    )
    return outputs


def _walkforward_windows(config: AppConfig) -> list[PeriodConfig]:
    if not config.walkforward.enabled:
        raise ValueError("walkforward is not enabled in the config")

    validation_period = _validation_period(config, "validation")
    if validation_period is not None and validation_period.start_date is not None and validation_period.end_date is not None:
        start_date = validation_period.start_date
        end_date = validation_period.end_date
        test_start = start_date
    else:
        anchors = [period for period in config.validation if period.start_date is not None and period.end_date is not None]
        if anchors:
            start_date = min(period.start_date for period in anchors if period.start_date is not None)
            end_date = max(period.end_date for period in anchors if period.end_date is not None)
        else:
            if config.period.start_date is None or config.period.end_date is None:
                raise ValueError("walkforward requires bounded validation or period dates")
            start_date = config.period.start_date
            end_date = config.period.end_date
        test_start = start_date + timedelta(days=config.walkforward.train_days)

    windows: list[PeriodConfig] = []
    window_index = 1
    while test_start <= end_date:
        test_end = min(test_start + timedelta(days=config.walkforward.test_days - 1), end_date)
        windows.append(
            PeriodConfig(
                label=f"walkforward_{window_index:02d}",
                start_date=test_start,
                end_date=test_end,
            )
        )
        window_index += 1
        test_start = test_start + timedelta(days=config.walkforward.step_days)

    return windows


def _validation_period(config: AppConfig, label: str) -> PeriodConfig | None:
    for period in config.validation:
        if period.label == label:
            return period
    return None


def _split_result_summary(result: BacktestResult) -> dict[str, object]:
    evaluation = result.analytics.get("evaluation", {})
    period = result.analytics.get("period", {})
    return {
        "label": period.get("label", "full_sample"),
        "status": evaluation.get("status", "unknown"),
        "total_return": float(result.summary.get("total_return", 0.0) or 0.0),
        "excess_return": float(evaluation.get("excess_return", 0.0) or 0.0),
        "max_drawdown": float(result.summary.get("max_drawdown", 0.0) or 0.0),
        "turnover": float(result.summary.get("turnover", 0.0) or 0.0),
        "results_path": result.results_path,
    }


def _comparison_row(result: BacktestResult) -> dict[str, object]:
    run_name = Path(result.results_path).parent.name
    benchmark = result.analytics.get("benchmark", {})
    benchmark_return = float(benchmark.get("total_return", 0.0) or 0.0)
    total_return = float(result.summary.get("total_return", 0.0))
    max_drawdown = float(result.summary.get("max_drawdown", 0.0))
    turnover = float(result.summary.get("turnover", 0.0))
    trade_count = float(result.summary.get("trade_count", 0.0))
    strategy_family, sweep_type, parameter_name, parameter_value = classify_run_name(run_name)
    evaluation = result.analytics.get("evaluation", {})
    warn_flags = evaluation.get("warn_flags", [])
    fail_flags = evaluation.get("fail_flags", [])
    benchmarks = result.analytics.get("benchmarks", {})
    equal_weight = benchmarks.get("equal_weight", {}) if isinstance(benchmarks, dict) else {}
    price_weighted = benchmarks.get("price_weighted", {}) if isinstance(benchmarks, dict) else {}
    primary_benchmark = str(result.analytics.get("primary_benchmark", "unknown"))
    period = result.analytics.get("period", {})
    metadata = result.analytics.get("run_metadata", {})
    research = result.analytics.get("research", {})
    return {
        "run_name": run_name,
        "evaluation_profile": evaluation.get("policy", {}).get("profile_name", "default"),
        "primary_benchmark": primary_benchmark,
        "period_label": period.get("label", "full_sample") if isinstance(period, dict) else "full_sample",
        "period_start": period.get("start_date") if isinstance(period, dict) else None,
        "period_end": period.get("end_date") if isinstance(period, dict) else None,
        "strategy_family": strategy_family,
        "sweep_type": sweep_type,
        "parameter_name": parameter_name,
        "parameter_value": parameter_value,
        "total_return": total_return,
        "benchmark_return": benchmark_return,
        "excess_return": total_return - benchmark_return,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "trade_count": trade_count,
        "zero_trade": trade_count == 0.0,
        "return_per_turnover": 0.0 if turnover == 0 else total_return / turnover,
        "return_per_drawdown": 0.0 if max_drawdown == 0 else total_return / max_drawdown,
        "evaluation_status": evaluation.get("status", "unknown"),
        "evaluation_flags": ",".join(evaluation.get("flags", [])),
        "evaluation_warn_flags": ",".join(warn_flags),
        "evaluation_fail_flags": ",".join(fail_flags),
        "evaluation_warn_count": len(warn_flags),
        "evaluation_fail_count": len(fail_flags),
        "equal_weight_return": float(equal_weight.get("total_return", 0.0) or 0.0),
        "price_weighted_return": float(price_weighted.get("total_return", 0.0) or 0.0),
        "excess_vs_equal_weight": total_return - float(equal_weight.get("total_return", 0.0) or 0.0),
        "excess_vs_price_weighted": total_return - float(price_weighted.get("total_return", 0.0) or 0.0),
        "ending_nav": float(result.summary.get("ending_nav", 0.0)),
        "research_tranche": metadata.get("research_tranche", research.get("research_tranche", "")),
        "research_slice_name": metadata.get("research_slice_name", research.get("research_slice_name", "all")),
        "ranking_mode": metadata.get("ranking_mode", "global"),
        "score_transform": metadata.get("score_transform", "raw"),
        "control_profile": metadata.get("control_profile", research.get("control_profile", "")),
        "promotion_candidate": bool(metadata.get("promotion_candidate", research.get("promotion_candidate", False))),
        "results_path": result.results_path,
    }


def _run_research_tranche(
    config: AppConfig,
    tranche_name: str,
    scenario_label: str,
    scenarios: list[tuple[str, dict[str, object]]],
    control_label: str,
    output_report_name: str,
) -> dict[str, object]:
    tranche_config = config
    if config.features.enabled:
        ensure_feature_set(config)
        tranche_config = replace(
            config,
            features=replace(config.features, materialize_on_backtest=False),
        )
    control_evaluation = _evaluate_candidate(
        tranche_config,
        scenario_name=control_label,
        scenario_label=scenario_label,
        tranche_name=tranche_name,
    )
    candidate_rows = [
        _evaluate_candidate(
            _candidate_config(tranche_config, tranche_name, scenario_name, overrides),
            scenario_name=scenario_name,
            scenario_label=scenario_label,
            tranche_name=tranche_name,
        )
        for scenario_name, overrides in scenarios
    ]
    decision = _select_tranche_candidate(control_evaluation, candidate_rows)
    artifacts = write_tranche_report(
        output_dir=config.run.output_dir,
        report_name=output_report_name,
        tranche_name=tranche_name,
        control_row=control_evaluation,
        candidate_rows=candidate_rows,
        decision=decision,
    )
    return {
        "control": control_evaluation,
        "candidates": candidate_rows,
        "top_candidate": decision.get("selected_candidate"),
        "decision": {key: value for key, value in decision.items() if key != "selected_candidate"},
        "artifacts": artifacts,
    }


def _run_operability_tranche(
    config: AppConfig,
    tranche_name: str,
    scenario_label: str,
    scenarios: list[tuple[str, dict[str, object]]],
    output_report_name: str,
    *,
    control_row: dict[str, object] | None = None,
) -> dict[str, object]:
    tranche_config = config
    if config.features.enabled:
        ensure_feature_set(config)
        tranche_config = replace(
            config,
            features=replace(config.features, materialize_on_backtest=False),
        )
    control_evaluation = control_row or _evaluate_candidate(
        tranche_config,
        scenario_name="control",
        scenario_label=scenario_label,
        tranche_name=tranche_name,
    )
    candidate_rows = [
        _evaluate_candidate(
            _candidate_config(tranche_config, tranche_name, scenario_name, overrides),
            scenario_name=scenario_name,
            scenario_label=scenario_label,
            tranche_name=tranche_name,
        )
        for scenario_name, overrides in scenarios
    ]
    decision = _select_operability_candidate(control_evaluation, candidate_rows)
    artifacts = write_tranche_report(
        output_dir=config.run.output_dir,
        report_name=output_report_name,
        tranche_name=tranche_name,
        control_row=control_evaluation,
        candidate_rows=candidate_rows,
        decision=decision,
    )
    return {
        "control": control_evaluation,
        "candidates": candidate_rows,
        "top_candidate": decision.get("selected_candidate"),
        "decision": {key: value for key, value in decision.items() if key != "selected_candidate"},
        "artifacts": artifacts,
    }


def _operability_shortlist(
    control_row: dict[str, object],
    candidate_rows: list[dict[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    viable = [row for row in candidate_rows if _operability_candidate_viable(row, control_row)]
    return sorted(viable, key=lambda row: row.get("decision_score", _candidate_decision_score(row)), reverse=True)[:limit]


def _evaluate_stress_pack(
    control_row: dict[str, object],
    candidate_config: AppConfig,
    candidate_row: dict[str, object],
) -> dict[str, object]:
    scenarios = []
    for scenario_name, overrides in _stress_scenarios(candidate_config):
        stress_config = _stress_config(candidate_config, scenario_name, overrides)
        stress_row = _evaluate_candidate(
            stress_config,
            scenario_name=scenario_name,
            scenario_label="stress",
            tranche_name="operability_stress",
        )
        stress_row["non_broken"] = _stress_row_non_broken(stress_row)
        scenarios.append(stress_row)
    non_broken_count = sum(1 for row in scenarios if bool(row.get("non_broken", False)))
    return {
        "candidate_run_name": candidate_row.get("run_name"),
        "candidate_profile_name": candidate_row.get("profile_name"),
        "control_holdout_excess_return": float(control_row.get("holdout_excess_return", 0.0) or 0.0),
        "scenario_count": len(scenarios),
        "non_broken_count": non_broken_count,
        "broken_count": len(scenarios) - non_broken_count,
        "stress_ok": non_broken_count == len(scenarios),
        "scenarios": scenarios,
    }


def _stress_config(candidate_config: AppConfig, scenario_name: str, overrides: dict[str, object]) -> AppConfig:
    stress_config = _candidate_config(candidate_config, "operability_stress", scenario_name, overrides)
    return replace(
        stress_config,
        research=replace(
            stress_config.research,
            control_profile=candidate_config.research.profile_name,
            promotion_candidate=False,
        ),
    )


def _batch_preset_definition(
    config: AppConfig,
    batch_preset: str,
) -> tuple[str, str, list[tuple[str, dict[str, object]]]]:
    preset_key = batch_preset.strip().lower()
    if preset_key == "universe-slice":
        return ("universe_slice", "slice", _universe_slice_scenarios(config))
    if preset_key == "ranking":
        return ("ranking", "ranking", _ranking_scenarios())
    if preset_key == "construction":
        return ("construction", "construct", _construction_scenarios())
    if preset_key == "risk":
        return ("risk", "risk", _risk_batch_scenarios(config))
    if preset_key == "regime":
        return ("regime", "regime", _regime_batch_scenarios())
    if preset_key == "sector":
        return ("sector", "sector", _sector_batch_scenarios())
    if preset_key == "operability":
        return ("operability", "operability", _operability_batch_scenarios(config))
    raise ValueError(
        f"Unsupported batch preset '{batch_preset}'. Available presets: {', '.join(BATCH_PRESETS)}"
    )


def _universe_slice_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    instruments = load_instruments(config.data.source_instruments_csv)
    available_universe_buckets = sorted(
        {instrument.universe_bucket for instrument in instruments.values() if instrument.universe_bucket}
    )
    available_benchmark_buckets = sorted(
        {instrument.benchmark_bucket for instrument in instruments.values() if instrument.benchmark_bucket}
    )
    available_liquidity_buckets = sorted(
        {instrument.liquidity_bucket for instrument in instruments.values() if instrument.liquidity_bucket},
        key=_liquidity_rank,
    )

    scenarios: list[tuple[str, dict[str, object]]] = [
        ("all", {}),
    ]
    if "core" in available_universe_buckets:
        scenarios.append(("core_only", {"allowed_universe_buckets": ("core",)}))
    if "explore" in available_universe_buckets:
        scenarios.append(("explore_only", {"allowed_universe_buckets": ("explore",)}))
    tighter_liquidity_bucket = _next_tighter_liquidity_bucket(
        available_liquidity_buckets,
        config.universe.excluded_liquidity_buckets,
    )
    if tighter_liquidity_bucket:
        scenarios.append(
            (
                f"exclude_{tighter_liquidity_bucket}",
                {
                    "excluded_liquidity_buckets": tuple(
                        sorted(
                            set(config.universe.excluded_liquidity_buckets) | {tighter_liquidity_bucket},
                            key=_liquidity_rank,
                        )
                    )
                },
            )
        )
    if "FTSE100" in available_benchmark_buckets:
        scenarios.append(("ftse100_only", {"allowed_benchmark_buckets": ("FTSE100",)}))
    if "FTSE250" in available_benchmark_buckets:
        scenarios.append(("ftse250_only", {"allowed_benchmark_buckets": ("FTSE250",)}))
    return scenarios


def _ranking_scenarios() -> list[tuple[str, dict[str, object]]]:
    return [
        ("global_raw", {"ranking_mode": "global", "score_transform": "raw"}),
        ("global_vol_adjusted", {"ranking_mode": "global", "score_transform": "vol_adjusted"}),
        ("sector_relative_raw", {"ranking_mode": "sector_relative", "score_transform": "raw"}),
        ("sector_relative_vol_adjusted", {"ranking_mode": "sector_relative", "score_transform": "vol_adjusted"}),
        (
            "benchmark_bucket_relative_raw",
            {"ranking_mode": "benchmark_bucket_relative", "score_transform": "raw"},
        ),
        (
            "benchmark_bucket_relative_vol_adjusted",
            {"ranking_mode": "benchmark_bucket_relative", "score_transform": "vol_adjusted"},
        ),
    ]


def _construction_scenarios() -> list[tuple[str, dict[str, object]]]:
    scenarios: list[tuple[str, dict[str, object]]] = []
    for top_n in (6, 8, 10):
        for gross_exposure in (0.50, 0.60, 0.70):
            for rebalance_frequency_days in (42, 63):
                for min_holding_days in (63, 84):
                    for selection_buffer_slots in (2, 3):
                        scenario_name = (
                            f"n{top_n}_g{int(gross_exposure * 100):02d}"
                            f"_r{rebalance_frequency_days}_h{min_holding_days}_b{selection_buffer_slots}"
                        )
                        scenarios.append(
                            (
                                scenario_name,
                                {
                                    "top_n": top_n,
                                    "target_gross_exposure": gross_exposure,
                                    "rebalance_frequency_days": rebalance_frequency_days,
                                    "min_holding_days": min_holding_days,
                                    "selection_buffer_slots": selection_buffer_slots,
                                },
                            )
                        )
    return scenarios


def _risk_scenarios(config: AppConfig, *, include_baseline: bool) -> list[tuple[str, dict[str, object]]]:
    scenarios = [
        (
            "baseline",
            {
                "top_n": config.strategy.top_n,
                "cash_buffer_pct": config.portfolio.cash_buffer_pct,
                "target_gross_exposure": config.portfolio.target_gross_exposure,
                "max_position_weight": config.portfolio.max_position_weight,
                "initial_deployment_turnover_pct": config.portfolio.initial_deployment_turnover_pct,
            },
        ),
        (
            "gross70_deploy12_n6_w09",
            {
                "top_n": 6,
                "cash_buffer_pct": 0.10,
                "target_gross_exposure": 0.70,
                "max_position_weight": 0.09,
                "initial_deployment_turnover_pct": 0.12,
            },
        ),
        (
            "gross70_deploy12_n8_w10",
            {
                "top_n": 8,
                "cash_buffer_pct": 0.10,
                "target_gross_exposure": 0.70,
                "max_position_weight": 0.10,
                "initial_deployment_turnover_pct": 0.12,
            },
        ),
        (
            "gross70_deploy20_n8_w10",
            {
                "top_n": 8,
                "cash_buffer_pct": 0.10,
                "target_gross_exposure": 0.70,
                "max_position_weight": 0.10,
                "initial_deployment_turnover_pct": 0.20,
            },
        ),
        (
            "gross60_deploy20_n8_w10",
            {
                "top_n": 8,
                "cash_buffer_pct": 0.10,
                "target_gross_exposure": 0.60,
                "max_position_weight": 0.10,
                "initial_deployment_turnover_pct": 0.20,
            },
        ),
        (
            "gross65_deploy20_n8_w09_cb12",
            {
                "top_n": 8,
                "cash_buffer_pct": 0.12,
                "target_gross_exposure": 0.65,
                "max_position_weight": 0.09,
                "initial_deployment_turnover_pct": 0.20,
            },
        ),
    ]
    return scenarios if include_baseline else scenarios[1:]


def _risk_batch_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    return _risk_scenarios(config, include_baseline=False)


def _regime_scenarios(*, include_off: bool) -> list[tuple[str, dict[str, object]]]:
    scenarios = [
        (
            "off",
            {
                "benchmark_regime_window_days": 0,
                "benchmark_regime_min_return": 0.0,
                "benchmark_regime_reduced_gross_exposure": 0.0,
                "benchmark_regime_force_rebalance": False,
            },
        ),
        (
            "bw126_re35_force",
            {
                "benchmark_regime_window_days": 126,
                "benchmark_regime_min_return": 0.0,
                "benchmark_regime_reduced_gross_exposure": 0.35,
                "benchmark_regime_force_rebalance": True,
            },
        ),
        (
            "bw126_re45_force",
            {
                "benchmark_regime_window_days": 126,
                "benchmark_regime_min_return": 0.0,
                "benchmark_regime_reduced_gross_exposure": 0.45,
                "benchmark_regime_force_rebalance": True,
            },
        ),
        (
            "bw252_re35_force",
            {
                "benchmark_regime_window_days": 252,
                "benchmark_regime_min_return": 0.0,
                "benchmark_regime_reduced_gross_exposure": 0.35,
                "benchmark_regime_force_rebalance": True,
            },
        ),
        (
            "bw252_re45_force",
            {
                "benchmark_regime_window_days": 252,
                "benchmark_regime_min_return": 0.0,
                "benchmark_regime_reduced_gross_exposure": 0.45,
                "benchmark_regime_force_rebalance": True,
            },
        ),
    ]
    return scenarios if include_off else scenarios[1:]


def _regime_batch_scenarios() -> list[tuple[str, dict[str, object]]]:
    return _regime_scenarios(include_off=False)


def _sector_scenarios(*, include_off: bool) -> list[tuple[str, int]]:
    scenarios = [
        ("off", 0),
        ("sec3", 3),
        ("sec2", 2),
        ("sec1", 1),
    ]
    return scenarios if include_off else scenarios[1:]


def _sector_batch_scenarios() -> list[tuple[str, dict[str, object]]]:
    return [
        (scenario_name, {"max_positions_per_sector": max_positions_per_sector})
        for scenario_name, max_positions_per_sector in _sector_scenarios(include_off=False)
    ]


def _operability_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    selection_buffers = sorted(
        {
            max(config.portfolio.selection_buffer_slots - 1, 1),
            config.portfolio.selection_buffer_slots,
            config.portfolio.selection_buffer_slots + 1,
        }
    )
    scenarios: list[tuple[str, dict[str, object]]] = []
    for rebalance_frequency_days in (42, 63, 84):
        for top_n in (6, 8, 10):
            for target_gross_exposure in (0.55, 0.60, 0.65):
                for max_rebalance_turnover_pct in (0.08, 0.09, 0.10):
                    for max_positions_per_sector in (2, 3, 4):
                        for selection_buffer_slots in selection_buffers:
                            scenario_name = (
                                f"rf{rebalance_frequency_days}"
                                f"_n{top_n}"
                                f"_g{int(target_gross_exposure * 100):02d}"
                                f"_t{int(max_rebalance_turnover_pct * 100):02d}"
                                f"_sec{max_positions_per_sector}"
                                f"_buf{selection_buffer_slots}"
                            )
                            scenarios.append(
                                (
                                    scenario_name,
                                    {
                                        "top_n": top_n,
                                        "target_gross_exposure": target_gross_exposure,
                                        "rebalance_frequency_days": rebalance_frequency_days,
                                        "max_rebalance_turnover_pct": max_rebalance_turnover_pct,
                                        "max_positions_per_sector": max_positions_per_sector,
                                        "selection_buffer_slots": selection_buffer_slots,
                                    },
                                )
                            )
    return scenarios


def _operability_batch_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    return _operability_scenarios(config)


def _benchmark_pivot_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    scenarios: list[tuple[str, dict[str, object]]] = []
    top_n_values = [config.strategy.top_n, max(config.strategy.top_n + 2, config.strategy.top_n)]
    for top_n in sorted(set(top_n_values)):
        for score_transform in ("raw", "vol_adjusted", "drawdown_penalized"):
            for max_positions_per_benchmark_bucket in (2, 3):
                for min_candidates_per_group in (1, 2):
                    scenario_name = (
                        f"bb_n{top_n}"
                        f"_{score_transform}"
                        f"_cap{max_positions_per_benchmark_bucket}"
                        f"_grp{min_candidates_per_group}"
                    )
                    scenarios.append(
                        (
                            scenario_name,
                            {
                                "top_n": top_n,
                                "ranking_mode": "benchmark_bucket_relative",
                                "score_transform": score_transform,
                                "min_candidates_per_group": min_candidates_per_group,
                                "max_positions_per_benchmark_bucket": max_positions_per_benchmark_bucket,
                            },
                        )
                    )
    return scenarios


def _stability_pivot_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    scenarios: list[tuple[str, dict[str, object]]] = []
    top_n_values = [config.strategy.top_n, config.strategy.top_n + 2]
    for ranking_mode in ("global", "sector_relative"):
        for score_transform in ("vol_adjusted", "drawdown_penalized"):
            for rebalance_frequency_days in (63, 84):
                for max_rebalance_turnover_pct in (0.08, 0.09):
                    for top_n in sorted(set(top_n_values)):
                        scenario_name = (
                            f"stability_{ranking_mode}"
                            f"_{score_transform}"
                            f"_rf{rebalance_frequency_days}"
                            f"_t{int(max_rebalance_turnover_pct * 100):02d}"
                            f"_n{top_n}"
                        )
                        scenarios.append(
                            (
                                scenario_name,
                                {
                                    "ranking_mode": ranking_mode,
                                    "score_transform": score_transform,
                                    "rebalance_frequency_days": rebalance_frequency_days,
                                    "max_rebalance_turnover_pct": max_rebalance_turnover_pct,
                                    "top_n": top_n,
                                },
                            )
                        )
    return scenarios


def _stress_scenarios(config: AppConfig) -> list[tuple[str, dict[str, object]]]:
    scenarios: list[tuple[str, dict[str, object]]] = [
        (
            "cost_step_up",
            {
                "commission_bps": config.execution.commission_bps + 2.0,
                "slippage_bps": config.execution.slippage_bps + 5.0,
                "spread_bps": config.execution.spread_bps + 4.0,
                "stamp_duty_bps": config.execution.stamp_duty_bps + 5.0,
            },
        ),
        (
            "participation_step_down",
            {
                "max_participation_rate": max(config.execution.max_participation_rate - 0.01, 0.01),
            },
        ),
        (
            "slower_deployment",
            {
                "initial_deployment_turnover_pct": max(config.portfolio.initial_deployment_turnover_pct - 0.08, 0.08),
            },
        ),
    ]
    tighter_liquidity_bucket = _next_tighter_liquidity_bucket(
        sorted(
            {
                instrument.liquidity_bucket
                for instrument in load_instruments(config.data.source_instruments_csv).values()
                if instrument.liquidity_bucket
            }
            ,
            key=_liquidity_rank,
        ),
        config.universe.excluded_liquidity_buckets,
    )
    if tighter_liquidity_bucket:
        scenarios.append(
            (
                f"exclude_{tighter_liquidity_bucket}",
                {
                    "excluded_liquidity_buckets": tuple(
                        sorted(
                            set(config.universe.excluded_liquidity_buckets) | {tighter_liquidity_bucket},
                            key=_liquidity_rank,
                        )
                    )
                },
            )
        )
    return scenarios


def _candidate_config(
    control_config: AppConfig,
    tranche_name: str,
    scenario_name: str,
    overrides: dict[str, object],
) -> AppConfig:
    strategy = control_config.strategy
    universe = control_config.universe
    portfolio = control_config.portfolio
    candidate_profile_name = f"momentum_candidate_{tranche_name}_{scenario_name}"
    research = replace(
        control_config.research,
        profile_name=candidate_profile_name,
        profile_version=f"{control_config.research.profile_version}-{tranche_name}-{scenario_name}",
        promoted=False,
        research_tranche=tranche_name,
        research_slice_name=_string_override(overrides, "research_slice_name", control_config.research.research_slice_name or "all"),
        control_profile=control_config.research.profile_name,
        promotion_candidate=True,
    )
    features = replace(
        control_config.features,
        set_name=control_config.features.set_name,
        materialize_on_backtest=False,
    )

    if "allowed_universe_buckets" in overrides:
        universe = replace(universe, allowed_universe_buckets=tuple(overrides["allowed_universe_buckets"]))
    if "allowed_benchmark_buckets" in overrides:
        universe = replace(universe, allowed_benchmark_buckets=tuple(overrides["allowed_benchmark_buckets"]))
    if "excluded_liquidity_buckets" in overrides:
        universe = replace(universe, excluded_liquidity_buckets=tuple(overrides["excluded_liquidity_buckets"]))
    if "ranking_mode" in overrides or "score_transform" in overrides or "min_candidates_per_group" in overrides:
        strategy = replace(
            strategy,
            ranking_mode=str(overrides.get("ranking_mode", strategy.ranking_mode)),
            score_transform=str(overrides.get("score_transform", strategy.score_transform)),
            min_candidates_per_group=int(overrides.get("min_candidates_per_group", strategy.min_candidates_per_group)),
        )
    if "top_n" in overrides:
        strategy = replace(strategy, top_n=int(overrides["top_n"]))
    portfolio_override_keys = {
        "cash_buffer_pct",
        "target_gross_exposure",
        "max_position_weight",
        "max_rebalance_turnover_pct",
        "initial_deployment_turnover_pct",
        "rebalance_frequency_days",
        "min_holding_days",
        "selection_buffer_slots",
        "max_positions_per_sector",
        "max_positions_per_benchmark_bucket",
        "benchmark_regime_window_days",
        "benchmark_regime_min_return",
        "benchmark_regime_reduced_gross_exposure",
        "benchmark_regime_force_rebalance",
    }
    if any(key in overrides for key in portfolio_override_keys):
        portfolio = replace(
            portfolio,
            cash_buffer_pct=float(overrides.get("cash_buffer_pct", portfolio.cash_buffer_pct)),
            target_gross_exposure=float(overrides.get("target_gross_exposure", portfolio.target_gross_exposure)),
            max_position_weight=float(overrides.get("max_position_weight", portfolio.max_position_weight)),
            max_rebalance_turnover_pct=float(
                overrides.get("max_rebalance_turnover_pct", portfolio.max_rebalance_turnover_pct)
            ),
            initial_deployment_turnover_pct=float(
                overrides.get("initial_deployment_turnover_pct", portfolio.initial_deployment_turnover_pct)
            ),
            rebalance_frequency_days=int(overrides.get("rebalance_frequency_days", portfolio.rebalance_frequency_days)),
            min_holding_days=int(overrides.get("min_holding_days", portfolio.min_holding_days)),
            selection_buffer_slots=int(overrides.get("selection_buffer_slots", portfolio.selection_buffer_slots)),
            max_positions_per_sector=int(overrides.get("max_positions_per_sector", portfolio.max_positions_per_sector)),
            max_positions_per_benchmark_bucket=int(
                overrides.get("max_positions_per_benchmark_bucket", portfolio.max_positions_per_benchmark_bucket)
            ),
            benchmark_regime_window_days=int(
                overrides.get("benchmark_regime_window_days", portfolio.benchmark_regime_window_days)
            ),
            benchmark_regime_min_return=float(
                overrides.get("benchmark_regime_min_return", portfolio.benchmark_regime_min_return)
            ),
            benchmark_regime_reduced_gross_exposure=float(
                overrides.get(
                    "benchmark_regime_reduced_gross_exposure",
                    portfolio.benchmark_regime_reduced_gross_exposure,
                )
            ),
            benchmark_regime_force_rebalance=bool(
                overrides.get("benchmark_regime_force_rebalance", portfolio.benchmark_regime_force_rebalance)
            ),
        )
    execution_override_keys = {
        "commission_bps",
        "slippage_bps",
        "spread_bps",
        "stamp_duty_bps",
        "max_participation_rate",
        "allow_partial_fills",
    }
    execution = control_config.execution
    if any(key in overrides for key in execution_override_keys):
        execution = replace(
            execution,
            commission_bps=float(overrides.get("commission_bps", execution.commission_bps)),
            slippage_bps=float(overrides.get("slippage_bps", execution.slippage_bps)),
            spread_bps=float(overrides.get("spread_bps", execution.spread_bps)),
            stamp_duty_bps=float(overrides.get("stamp_duty_bps", execution.stamp_duty_bps)),
            max_participation_rate=float(overrides.get("max_participation_rate", execution.max_participation_rate)),
            allow_partial_fills=bool(overrides.get("allow_partial_fills", execution.allow_partial_fills)),
        )

    run_name = f"{control_config.run.name}_{scenario_label(tranche_name)}_{scenario_name}"
    return replace(
        control_config,
        run=replace(control_config.run, name=run_name),
        strategy=strategy,
        universe=universe,
        portfolio=portfolio,
        execution=execution,
        research=research,
        features=features,
    )


def _evaluate_candidate(
    config: AppConfig,
    scenario_name: str,
    scenario_label: str,
    tranche_name: str,
) -> dict[str, object]:
    promotion = run_promotion_check(config)
    return _candidate_row_from_promotion(
        config,
        promotion["promotion_decision"],
        scenario_name=scenario_name,
        scenario_label=scenario_label,
        tranche_name=tranche_name,
    )


def _candidate_row_from_promotion(
    config: AppConfig,
    promotion_decision: dict[str, object],
    *,
    scenario_name: str,
    scenario_label: str,
    tranche_name: str,
) -> dict[str, object]:
    promotion = {"promotion_decision": promotion_decision}
    split_summary = promotion["promotion_decision"].get("split_summary", {})
    validation = split_summary.get("validation", {})
    holdout = split_summary.get("holdout", {})
    train = split_summary.get("train", {})
    walkforward = promotion["promotion_decision"].get("walkforward_summary", {})
    row = {
        "run_name": config.run.name,
        "scenario_name": scenario_name,
        "scenario_label": scenario_label,
        "tranche_name": tranche_name,
        "profile_name": config.research.profile_name,
        "profile_version": config.research.profile_version,
        "strategy_family": config.strategy.name,
        "research_tranche": config.research.research_tranche,
        "research_slice_name": config.research.research_slice_name,
        "ranking_mode": config.strategy.ranking_mode,
        "score_transform": config.strategy.score_transform,
        "min_candidates_per_group": config.strategy.min_candidates_per_group,
        "top_n": config.strategy.top_n,
        "allowed_universe_buckets": ",".join(config.universe.allowed_universe_buckets),
        "allowed_benchmark_buckets": ",".join(config.universe.allowed_benchmark_buckets),
        "excluded_liquidity_buckets": ",".join(config.universe.excluded_liquidity_buckets),
        "control_profile": config.research.control_profile,
        "promotion_candidate": config.research.promotion_candidate,
        "eligible": bool(promotion["promotion_decision"].get("eligible", False)),
        "recommended_action": str(promotion["promotion_decision"].get("recommended_action", "retain")),
        "fail_reasons": list(promotion["promotion_decision"].get("fail_reasons", [])),
        "train_status": str(train.get("status", "unknown")),
        "train_excess_return": float(train.get("excess_return", 0.0) or 0.0),
        "train_drawdown": float(train.get("max_drawdown", 0.0) or 0.0),
        "train_turnover": float(train.get("turnover", 0.0) or 0.0),
        "validation_status": str(validation.get("status", "unknown")),
        "validation_excess_return": float(validation.get("excess_return", 0.0) or 0.0),
        "validation_drawdown": float(validation.get("max_drawdown", 0.0) or 0.0),
        "validation_turnover": float(validation.get("turnover", 0.0) or 0.0),
        "holdout_status": str(holdout.get("status", "unknown")),
        "holdout_excess_return": float(holdout.get("excess_return", 0.0) or 0.0),
        "holdout_drawdown": float(holdout.get("max_drawdown", 0.0) or 0.0),
        "holdout_turnover": float(holdout.get("turnover", 0.0) or 0.0),
        "walkforward_window_count": int(walkforward.get("window_count", 0) or 0),
        "walkforward_pass_windows": int(walkforward.get("pass_windows", 0) or 0),
        "walkforward_avg_excess_return": float(walkforward.get("average_excess_return", 0.0) or 0.0),
        "walkforward_avg_drawdown": float(walkforward.get("average_drawdown", 0.0) or 0.0),
        "walkforward_avg_turnover": float(walkforward.get("average_turnover", 0.0) or 0.0),
        "cash_buffer_pct": config.portfolio.cash_buffer_pct,
        "target_gross_exposure": config.portfolio.target_gross_exposure,
        "max_position_weight": config.portfolio.max_position_weight,
        "max_rebalance_turnover_pct": config.portfolio.max_rebalance_turnover_pct,
        "initial_deployment_turnover_pct": config.portfolio.initial_deployment_turnover_pct,
        "rebalance_frequency_days": config.portfolio.rebalance_frequency_days,
        "min_holding_days": config.portfolio.min_holding_days,
        "selection_buffer_slots": config.portfolio.selection_buffer_slots,
        "max_positions_per_sector": config.portfolio.max_positions_per_sector,
        "max_positions_per_benchmark_bucket": config.portfolio.max_positions_per_benchmark_bucket,
        "commission_bps": config.execution.commission_bps,
        "slippage_bps": config.execution.slippage_bps,
        "spread_bps": config.execution.spread_bps,
        "stamp_duty_bps": config.execution.stamp_duty_bps,
        "max_participation_rate": config.execution.max_participation_rate,
        "promotion_decision": promotion["promotion_decision"],
    }
    row["decision_score"] = _candidate_decision_score(row)
    return row


def _select_tranche_candidate(
    control_row: dict[str, object],
    candidate_rows: list[dict[str, object]],
) -> dict[str, object]:
    valid_candidates = [row for row in candidate_rows if _candidate_beats_control(row, control_row)]
    ranked_candidates = sorted(
        valid_candidates,
        key=lambda row: (
            bool(row.get("eligible", False)),
            float(row.get("validation_excess_return", 0.0) or 0.0),
            float(row.get("holdout_excess_return", 0.0) or 0.0),
            int(row.get("walkforward_pass_windows", 0) or 0),
            -(float(row.get("holdout_turnover", 0.0) or 0.0) + float(row.get("validation_turnover", 0.0) or 0.0)),
            -(float(row.get("holdout_drawdown", 0.0) or 0.0) + float(row.get("validation_drawdown", 0.0) or 0.0)),
        ),
        reverse=True,
    )
    selected_candidate = ranked_candidates[0] if ranked_candidates else None
    rejected_candidates = []
    for row in candidate_rows:
        rejection_reason = _candidate_rejection_reason(row, control_row)
        if rejection_reason:
            rejected_candidates.append({"run_name": row["run_name"], "reason": rejection_reason})
            row["rejection_reason"] = rejection_reason
        else:
            row["rejection_reason"] = ""

    return {
        "selected_run_name": None if selected_candidate is None else selected_candidate.get("run_name"),
        "selected_profile_name": None if selected_candidate is None else selected_candidate.get("profile_name"),
        "selected_candidate": selected_candidate,
        "control_run_name": control_row.get("run_name"),
        "rejected_candidates": rejected_candidates,
        "candidate_count": len(candidate_rows),
        "improving_candidate_count": len(valid_candidates),
        "recommended_action": "promote_candidate"
        if selected_candidate is not None and bool(selected_candidate.get("eligible", False))
        else "continue_research",
        "reason": "candidate_improves_validation_and_holdout"
        if selected_candidate is not None
        else "no_candidate_improved_validation_and_holdout_without_policy_failure",
    }


def _candidate_beats_control(candidate: dict[str, object], control: dict[str, object]) -> bool:
    if candidate.get("validation_status") == "fail" or candidate.get("holdout_status") == "fail":
        return False
    return (
        float(candidate.get("validation_excess_return", 0.0) or 0.0)
        > float(control.get("validation_excess_return", 0.0) or 0.0)
        and float(candidate.get("holdout_excess_return", 0.0) or 0.0)
        > float(control.get("holdout_excess_return", 0.0) or 0.0)
    )


def _candidate_rejection_reason(candidate: dict[str, object], control: dict[str, object]) -> str:
    if candidate.get("validation_status") == "fail":
        return "validation_failed_policy"
    if candidate.get("holdout_status") == "fail":
        return "holdout_failed_policy"
    if float(candidate.get("validation_excess_return", 0.0) or 0.0) <= float(
        control.get("validation_excess_return", 0.0) or 0.0
    ):
        return "validation_excess_not_improved"
    if float(candidate.get("holdout_excess_return", 0.0) or 0.0) <= float(
        control.get("holdout_excess_return", 0.0) or 0.0
    ):
        return "holdout_excess_not_improved"
    return ""


def _select_operability_candidate(
    control_row: dict[str, object],
    candidate_rows: list[dict[str, object]],
) -> dict[str, object]:
    viable_candidates = [row for row in candidate_rows if _operability_candidate_viable(row, control_row)]
    ranked_candidates = sorted(
        viable_candidates,
        key=lambda row: row.get("decision_score", _candidate_decision_score(row)),
        reverse=True,
    )
    selected_candidate = ranked_candidates[0] if ranked_candidates else None
    focused_success = (
        selected_candidate is not None
        and int(selected_candidate.get("walkforward_pass_windows", 0) or 0)
        > int(control_row.get("walkforward_pass_windows", 0) or 0)
    )
    rejected_candidates = []
    for row in candidate_rows:
        rejection_reason = _operability_candidate_rejection_reason(row, control_row)
        row["rejection_reason"] = rejection_reason
        if rejection_reason:
            rejected_candidates.append({"run_name": row["run_name"], "reason": rejection_reason})

    if selected_candidate is not None and bool(selected_candidate.get("eligible", False)) and focused_success:
        recommended_action = "freeze_candidate"
        reason = "candidate_improves_walkforward_and_preserves_holdout_edge"
    elif selected_candidate is not None and focused_success:
        recommended_action = "continue_operability_validation"
        reason = "candidate_improves_walkforward_but_not_full_promotion_gate"
    else:
        recommended_action = "continue_benchmark_pivot"
        reason = "no_candidate_restored_walkforward_without_giving_back_holdout"

    return {
        "selected_run_name": None if selected_candidate is None else selected_candidate.get("run_name"),
        "selected_profile_name": None if selected_candidate is None else selected_candidate.get("profile_name"),
        "selected_candidate": selected_candidate,
        "control_run_name": control_row.get("run_name"),
        "rejected_candidates": rejected_candidates,
        "candidate_count": len(candidate_rows),
        "viable_candidate_count": len(viable_candidates),
        "focused_success": focused_success,
        "recommended_action": recommended_action,
        "reason": reason,
    }


def _operability_candidate_viable(
    candidate: dict[str, object],
    control: dict[str, object],
) -> bool:
    if candidate.get("validation_status") == "fail" or candidate.get("holdout_status") == "fail":
        return False
    holdout_excess = float(candidate.get("holdout_excess_return", 0.0) or 0.0)
    if holdout_excess <= 0.0:
        return False
    if holdout_excess < float(control.get("holdout_excess_return", 0.0) or 0.0):
        return False
    return True


def _operability_candidate_rejection_reason(
    candidate: dict[str, object],
    control: dict[str, object],
) -> str:
    if candidate.get("validation_status") == "fail":
        return "validation_failed_policy"
    if candidate.get("holdout_status") == "fail":
        return "holdout_failed_policy"
    if float(candidate.get("holdout_excess_return", 0.0) or 0.0) <= 0.0:
        return "holdout_excess_not_positive"
    if float(candidate.get("holdout_excess_return", 0.0) or 0.0) < float(
        control.get("holdout_excess_return", 0.0) or 0.0
    ):
        return "holdout_improvement_not_preserved"
    if int(candidate.get("walkforward_pass_windows", 0) or 0) <= int(control.get("walkforward_pass_windows", 0) or 0):
        return "walkforward_not_improved"
    return ""


def _stress_row_non_broken(row: dict[str, object]) -> bool:
    return row.get("validation_status") != "fail" and row.get("holdout_status") != "fail"


def _tranche_seed_config(
    fallback_config: AppConfig,
    tranche_result: dict[str, object],
) -> AppConfig:
    candidate = tranche_result.get("top_candidate")
    if not isinstance(candidate, dict):
        return fallback_config
    return _candidate_row_config(fallback_config, candidate)


def _candidate_row_config(
    fallback_config: AppConfig,
    candidate: dict[str, object],
) -> AppConfig:
    allowed_universe_buckets = tuple(
        value for value in str(candidate.get("allowed_universe_buckets", "") or "").split(",") if value
    )
    allowed_benchmark_buckets = tuple(
        value for value in str(candidate.get("allowed_benchmark_buckets", "") or "").split(",") if value
    )
    excluded_liquidity_buckets = tuple(
        value for value in str(candidate.get("excluded_liquidity_buckets", "") or "").split(",") if value
    )
    return _candidate_config(
        fallback_config,
        tranche_name=str(candidate.get("research_tranche", "")),
        scenario_name=str(candidate.get("scenario_name", "carry")),
        overrides={
            "allowed_universe_buckets": allowed_universe_buckets or fallback_config.universe.allowed_universe_buckets,
            "allowed_benchmark_buckets": allowed_benchmark_buckets or fallback_config.universe.allowed_benchmark_buckets,
            "excluded_liquidity_buckets": excluded_liquidity_buckets or fallback_config.universe.excluded_liquidity_buckets,
            "ranking_mode": candidate.get("ranking_mode", fallback_config.strategy.ranking_mode),
            "score_transform": candidate.get("score_transform", fallback_config.strategy.score_transform),
            "min_candidates_per_group": candidate.get(
                "min_candidates_per_group",
                fallback_config.strategy.min_candidates_per_group,
            ),
            "top_n": candidate.get("top_n", fallback_config.strategy.top_n),
            "cash_buffer_pct": candidate.get("cash_buffer_pct", fallback_config.portfolio.cash_buffer_pct),
            "target_gross_exposure": candidate.get("target_gross_exposure", fallback_config.portfolio.target_gross_exposure),
            "max_position_weight": candidate.get("max_position_weight", fallback_config.portfolio.max_position_weight),
            "max_rebalance_turnover_pct": candidate.get(
                "max_rebalance_turnover_pct",
                fallback_config.portfolio.max_rebalance_turnover_pct,
            ),
            "initial_deployment_turnover_pct": candidate.get(
                "initial_deployment_turnover_pct",
                fallback_config.portfolio.initial_deployment_turnover_pct,
            ),
            "rebalance_frequency_days": candidate.get(
                "rebalance_frequency_days",
                fallback_config.portfolio.rebalance_frequency_days,
            ),
            "min_holding_days": candidate.get("min_holding_days", fallback_config.portfolio.min_holding_days),
            "selection_buffer_slots": candidate.get(
                "selection_buffer_slots",
                fallback_config.portfolio.selection_buffer_slots,
            ),
            "max_positions_per_sector": candidate.get(
                "max_positions_per_sector",
                fallback_config.portfolio.max_positions_per_sector,
            ),
            "max_positions_per_benchmark_bucket": candidate.get(
                "max_positions_per_benchmark_bucket",
                fallback_config.portfolio.max_positions_per_benchmark_bucket,
            ),
            "commission_bps": candidate.get("commission_bps", fallback_config.execution.commission_bps),
            "slippage_bps": candidate.get("slippage_bps", fallback_config.execution.slippage_bps),
            "spread_bps": candidate.get("spread_bps", fallback_config.execution.spread_bps),
            "stamp_duty_bps": candidate.get("stamp_duty_bps", fallback_config.execution.stamp_duty_bps),
            "max_participation_rate": candidate.get(
                "max_participation_rate",
                fallback_config.execution.max_participation_rate,
            ),
            "research_slice_name": candidate.get("research_slice_name", fallback_config.research.research_slice_name),
        },
    )


def _candidate_decision_score(candidate: dict[str, object]) -> tuple[object, ...]:
    return (
        bool(candidate.get("eligible", False)),
        candidate.get("validation_status") != "fail",
        candidate.get("holdout_status") != "fail",
        float(candidate.get("holdout_excess_return", 0.0) or 0.0),
        float(candidate.get("validation_excess_return", 0.0) or 0.0),
        int(candidate.get("walkforward_pass_windows", 0) or 0),
        -(
            float(candidate.get("validation_turnover", 0.0) or 0.0)
            + float(candidate.get("holdout_turnover", 0.0) or 0.0)
            + float(candidate.get("walkforward_avg_turnover", 0.0) or 0.0)
        ),
        -(
            float(candidate.get("validation_drawdown", 0.0) or 0.0)
            + float(candidate.get("holdout_drawdown", 0.0) or 0.0)
            + float(candidate.get("walkforward_avg_drawdown", 0.0) or 0.0)
        ),
        int(candidate.get("rebalance_frequency_days", 0) or 0),
        -(float(candidate.get("max_rebalance_turnover_pct", 0.0) or 0.0)),
        -(int(candidate.get("selection_buffer_slots", 0) or 0)),
    )


def _next_tighter_liquidity_bucket(
    available_buckets: list[str],
    excluded_buckets: tuple[str, ...],
) -> str | None:
    for bucket in available_buckets:
        if bucket not in excluded_buckets:
            return bucket
    return None


def _liquidity_rank(bucket: str) -> int:
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(bucket.lower(), 99)


def _string_override(overrides: dict[str, object], key: str, default: str) -> str:
    value = overrides.get(key, default)
    return str(value)


def scenario_label(tranche_name: str) -> str:
    labels = {
        "universe_slice": "slice",
        "ranking": "ranking",
        "construction": "construct",
    }
    return labels.get(tranche_name, tranche_name)
