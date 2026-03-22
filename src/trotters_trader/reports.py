from __future__ import annotations

import csv
from datetime import datetime, UTC
import hashlib
import json
from pathlib import Path

from trotters_trader.catalog import register_catalog_entry


def write_report_artifacts(
    run_dir: Path,
    run_name: str,
    summary: dict[str, float],
    analytics: dict[str, object],
    fills: list[dict[str, object]],
    performance: list[dict[str, object]],
) -> dict[str, str]:
    summary_path = run_dir / "summary.md"
    performance_path = run_dir / "performance.csv"
    fills_path = run_dir / "fills.csv"
    closed_trades_path = run_dir / "closed_trades.csv"
    benchmark_path = run_dir / "benchmark_performance.csv"

    summary_path.write_text(
        _render_summary_markdown(run_name, summary, analytics),
        encoding="utf-8",
    )
    _write_csv(performance_path, performance)
    _write_csv(fills_path, fills)
    _write_csv(closed_trades_path, analytics.get("closed_trades", []))

    benchmark = analytics.get("benchmark", {})
    benchmark_performance = benchmark.get("performance", []) if isinstance(benchmark, dict) else []
    _write_csv(benchmark_path, benchmark_performance)

    return {
        "summary_md": str(summary_path),
        "performance_csv": str(performance_path),
        "fills_csv": str(fills_path),
        "closed_trades_csv": str(closed_trades_path),
        "benchmark_csv": str(benchmark_path),
    }


def write_comparison_report(
    output_dir: Path,
    report_name: str,
    rows: list[dict[str, object]],
    quality_gate: str = "all",
) -> dict[str, str]:
    report_dir = output_dir / safe_artifact_dirname(report_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = report_dir / "comparison_summary.md"
    rankings_path = report_dir / "comparison_rankings.csv"
    decision_json_path = report_dir / "research_decision.json"
    decision_md_path = report_dir / "research_decision.md"

    filtered_rows = _filter_comparison_rows(rows, quality_gate)
    ranked_rows = _rank_comparison_rows(filtered_rows)
    summary_path.write_text(
        _render_comparison_markdown(
            report_name,
            ranked_rows,
            quality_gate,
            _excluded_rows(rows, filtered_rows),
        ),
        encoding="utf-8",
    )
    _write_csv(rankings_path, ranked_rows)
    decision = _build_research_decision(report_name, ranked_rows, rows, quality_gate)
    decision_json_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    decision_md_path.write_text(_render_research_decision_markdown(decision), encoding="utf-8")
    profile_name = _decision_profile_name(ranked_rows, rows)
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "comparison_report",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": _dominant_value(ranked_rows or rows, "strategy_family"),
            "sweep_type": _dominant_value(ranked_rows or rows, "sweep_type"),
            "evaluation_status": decision.get("top_evaluation_status", "unknown"),
            "primary_path": str(summary_path),
            "rankings_path": str(rankings_path),
            "decision_path": str(decision_md_path),
        },
    )
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "research_decision",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": _dominant_value(ranked_rows or rows, "strategy_family"),
            "sweep_type": _dominant_value(ranked_rows or rows, "sweep_type"),
            "evaluation_status": decision.get("top_evaluation_status", "unknown"),
            "primary_path": str(decision_json_path),
            "summary_path": str(decision_md_path),
            "recommended_action": decision.get("recommended_action", "retain"),
        },
    )

    return {
        "summary_md": str(summary_path),
        "rankings_csv": str(rankings_path),
        "research_decision_json": str(decision_json_path),
        "research_decision_md": str(decision_md_path),
    }


def write_experiment_index(
    output_dir: Path,
    report_name: str,
    rows: list[dict[str, object]],
    quality_gate: str = "all",
) -> str:
    index_path = output_dir / safe_artifact_dirname(report_name) / "experiment_index.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    filtered_rows = _filter_comparison_rows(rows, quality_gate)
    index_path.write_text(
        _render_experiment_index(
            report_name,
            filtered_rows,
            quality_gate,
            _excluded_rows(rows, filtered_rows),
        ),
        encoding="utf-8",
    )
    return str(index_path)


def write_promotion_artifacts(
    output_dir: Path,
    report_name: str,
    promotion_decision: dict[str, object],
    config_path: str,
) -> dict[str, str]:
    report_dir = output_dir / safe_artifact_dirname(report_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "promotion_decision.json"
    markdown_path = report_dir / "promotion_summary.md"
    history_dir = output_dir / "profile_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    profile = promotion_decision.get("profile", {}) if isinstance(promotion_decision, dict) else {}
    profile_name = str(profile.get("profile_name", "unknown"))
    history_path = history_dir / f"{profile_name}.jsonl"
    previous_entry = _last_history_entry(history_path)

    history_entry = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "config_path": config_path,
        **promotion_decision,
    }

    json_path.write_text(json.dumps(history_entry, indent=2), encoding="utf-8")
    markdown_path.write_text(
        _render_promotion_markdown(history_entry, previous_entry),
        encoding="utf-8",
    )
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_entry) + "\n")
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "promotion",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "profile_version": str(profile.get("profile_version", "unversioned")),
            "strategy_family": "cross_sectional_momentum",
            "sweep_type": "promotion_check",
            "evaluation_status": "pass" if bool(promotion_decision.get("eligible", False)) else "fail",
            "primary_path": str(json_path),
            "summary_path": str(markdown_path),
        },
    )

    return {
        "promotion_json": str(json_path),
        "promotion_md": str(markdown_path),
        "history_jsonl": str(history_path),
    }


def write_tranche_report(
    output_dir: Path,
    report_name: str,
    tranche_name: str,
    control_row: dict[str, object],
    candidate_rows: list[dict[str, object] | None],
    decision: dict[str, object],
) -> dict[str, str]:
    report_dir = output_dir / safe_artifact_dirname(report_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = report_dir / "tranche_summary.md"
    rankings_path = report_dir / "tranche_rankings.csv"
    decision_json_path = report_dir / "tranche_decision.json"

    normalized_candidates = [row for row in candidate_rows if isinstance(row, dict)]
    ranked_candidates = _rank_tranche_rows(normalized_candidates)

    summary_path.write_text(
        _render_tranche_markdown(tranche_name, control_row, ranked_candidates, decision),
        encoding="utf-8",
    )
    _write_csv(
        rankings_path,
        [{key: value for key, value in row.items() if key != "promotion_decision"} for row in ranked_candidates],
    )
    decision_json_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    profile_name = str(control_row.get("control_profile") or control_row.get("profile_name", "default"))
    strategy_family = str(control_row.get("strategy_family", "cross_sectional_momentum"))
    evaluation_status = "pass" if decision.get("selected_run_name") else "warn"
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "tranche_report",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": strategy_family,
            "sweep_type": tranche_name,
            "evaluation_status": evaluation_status,
            "primary_path": str(summary_path),
            "rankings_path": str(rankings_path),
            "decision_path": str(decision_json_path),
        },
    )
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "tranche_decision",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": strategy_family,
            "sweep_type": tranche_name,
            "evaluation_status": evaluation_status,
            "primary_path": str(decision_json_path),
            "summary_path": str(summary_path),
            "recommended_action": decision.get("recommended_action", "continue_research"),
        },
    )

    return {
        "summary_md": str(summary_path),
        "rankings_csv": str(rankings_path),
        "decision_json": str(decision_json_path),
    }


def write_operability_program_report(
    output_dir: Path,
    report_name: str,
    control_row: dict[str, object],
    focused_result: dict[str, object],
    pivot_result: dict[str, object] | None,
    shortlisted: list[dict[str, object]],
    stress_results: list[dict[str, object]],
    final_decision: dict[str, object],
) -> dict[str, str]:
    report_dir = output_dir / safe_artifact_dirname(report_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary_path = report_dir / "operability_program.md"
    decision_json_path = report_dir / "operability_program.json"
    shortlist_path = report_dir / "shortlist.csv"
    stress_path = report_dir / "stress_results.csv"
    scorecard_json_path = report_dir / "operator_scorecard.json"
    scorecard_md_path = report_dir / "operator_scorecard.md"
    comparison_md_path = report_dir / "candidate_comparison.md"

    stress_rows = _flatten_stress_rows(stress_results)
    scorecard = build_operability_scorecard(
        control_row=control_row,
        shortlisted=shortlisted,
        stress_results=stress_results,
        final_decision=final_decision,
    )
    summary_path.write_text(
        _render_operability_program_markdown(
            control_row=control_row,
            focused_result=focused_result,
            pivot_result=pivot_result,
            shortlisted=shortlisted,
            stress_results=stress_results,
            final_decision=final_decision,
        ),
        encoding="utf-8",
    )
    decision_json_path.write_text(
        json.dumps(
            {
                "control": control_row,
                "focused_result": focused_result,
                "pivot_result": pivot_result,
                "shortlisted": shortlisted,
                "stress_results": stress_results,
                "final_decision": final_decision,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    scorecard_json_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    scorecard_md_path.write_text(_render_operability_scorecard_markdown(scorecard), encoding="utf-8")
    comparison_md_path.write_text(_render_operability_comparison_markdown(scorecard), encoding="utf-8")
    _write_csv(
        shortlist_path,
        [{key: value for key, value in row.items() if key != "promotion_decision"} for row in shortlisted],
    )
    _write_csv(stress_path, stress_rows)

    profile_name = str(final_decision.get("selected_profile_name") or control_row.get("profile_name", "unknown"))
    evaluation_status = "pass" if bool(final_decision.get("selected_candidate_eligible", False)) else "warn"
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "operability_program",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": str(control_row.get("strategy_family", "cross_sectional_momentum")),
            "sweep_type": "operability_program",
            "evaluation_status": evaluation_status,
            "primary_path": str(summary_path),
            "decision_path": str(decision_json_path),
            "rankings_path": str(shortlist_path),
        },
    )
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "operator_scorecard",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": str(control_row.get("strategy_family", "cross_sectional_momentum")),
            "sweep_type": "operability_program",
            "evaluation_status": evaluation_status,
            "primary_path": str(scorecard_json_path),
            "summary_path": str(scorecard_md_path),
            "recommended_action": scorecard.get("operator_recommendation", "needs_more_research"),
        },
    )
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "candidate_comparison",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "strategy_family": str(control_row.get("strategy_family", "cross_sectional_momentum")),
            "sweep_type": "operability_program",
            "evaluation_status": evaluation_status,
            "primary_path": str(comparison_md_path),
            "recommended_action": scorecard.get("operator_recommendation", "needs_more_research"),
        },
    )

    return {
        "summary_md": str(summary_path),
        "decision_json": str(decision_json_path),
        "shortlist_csv": str(shortlist_path),
        "stress_csv": str(stress_path),
        "scorecard_json": str(scorecard_json_path),
        "scorecard_md": str(scorecard_md_path),
        "comparison_md": str(comparison_md_path),
    }


def write_paper_trade_decision_artifacts(
    output_dir: Path,
    report_name: str,
    decision_package: dict[str, object],
) -> dict[str, str]:
    report_dir = output_dir / safe_artifact_dirname(report_name)
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "paper_trade_decision.json"
    markdown_path = report_dir / "paper_trade_decision.md"
    targets_csv_path = report_dir / "paper_trade_targets.csv"

    target_rows = [
        row
        for row in decision_package.get("target_holdings", [])
        if isinstance(row, dict)
    ] if isinstance(decision_package, dict) else []

    json_path.write_text(json.dumps(decision_package, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_paper_trade_decision_markdown(decision_package), encoding="utf-8")
    _write_csv(targets_csv_path, target_rows)

    warnings = decision_package.get("warnings", []) if isinstance(decision_package, dict) else []
    profile_name = str(decision_package.get("profile_name", "unknown")) if isinstance(decision_package, dict) else "unknown"
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "paper_trade_decision",
            "artifact_name": report_name,
            "profile_name": profile_name,
            "profile_version": str(decision_package.get("profile_version", "unversioned")),
            "strategy_family": str(decision_package.get("strategy_name", "unknown")),
            "sweep_type": "paper_trade_decision",
            "evaluation_status": "warn" if warnings else "pass",
            "primary_path": str(json_path),
            "summary_path": str(markdown_path),
            "rankings_path": str(targets_csv_path),
            "recommended_action": "paper_trade_rehearsal",
        },
    )
    return {
        "decision_json": str(json_path),
        "decision_md": str(markdown_path),
        "targets_csv": str(targets_csv_path),
    }


def build_operability_scorecard(
    *,
    control_row: dict[str, object],
    shortlisted: list[dict[str, object]],
    stress_results: list[dict[str, object]],
    final_decision: dict[str, object],
) -> dict[str, object]:
    selected_candidate = _select_scorecard_candidate(shortlisted, final_decision)
    selected_stress = _select_scorecard_stress_result(stress_results, selected_candidate, final_decision)
    operator_recommendation = _operator_recommendation(final_decision)
    strengths = _scorecard_strengths(control_row, selected_candidate, selected_stress, final_decision)
    weaknesses = _scorecard_weaknesses(control_row, selected_candidate, selected_stress, final_decision)
    next_steps = _scorecard_next_steps(operator_recommendation)
    return {
        "campaign_decision": final_decision.get("recommended_action", "continue_research"),
        "campaign_reason": final_decision.get("reason", "unknown"),
        "operator_recommendation": operator_recommendation,
        "summary": _scorecard_summary(operator_recommendation, selected_candidate, final_decision),
        "selected_candidate": _scorecard_candidate_snapshot(selected_candidate, selected_stress),
        "control": _scorecard_candidate_snapshot(control_row, None),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "next_steps": next_steps,
        "comparison": _scorecard_comparison(control_row, selected_candidate, selected_stress),
    }


def operability_artifact_paths(latest_report_path: str | Path | None) -> dict[str, str]:
    report_path_text = str(latest_report_path or "").strip()
    if not report_path_text:
        return {}
    report_dir = Path(report_path_text).parent
    paths = {
        "summary_md": report_dir / "operability_program.md",
        "decision_json": report_dir / "operability_program.json",
        "scorecard_md": report_dir / "operator_scorecard.md",
        "scorecard_json": report_dir / "operator_scorecard.json",
        "comparison_md": report_dir / "candidate_comparison.md",
    }
    return {key: str(path) for key, path in paths.items() if path.exists()}


def build_campaign_operator_summary(
    campaign: dict[str, object],
    *,
    candidate_readiness: dict[str, object] | None = None,
    paper_trade_readiness: dict[str, object] | None = None,
) -> dict[str, object]:
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    control_row = state.get("control_row") if isinstance(state.get("control_row"), dict) else {}
    shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
    stress_results = [row for row in state.get("stress_results", []) if isinstance(row, dict)]
    final_decision = state.get("final_decision") if isinstance(state.get("final_decision"), dict) else {}
    selected_candidate = _select_scorecard_candidate(shortlisted, final_decision)
    selected_stress = _select_scorecard_stress_result(stress_results, selected_candidate, final_decision)
    scorecard = build_operability_scorecard(
        control_row=control_row,
        shortlisted=shortlisted,
        stress_results=stress_results,
        final_decision=final_decision,
    )
    next_steps = scorecard.get("next_steps", []) if isinstance(scorecard.get("next_steps"), list) else []
    return {
        "campaign_id": str(campaign.get("campaign_id", "")),
        "campaign_name": str(campaign.get("campaign_name", "unknown")),
        "campaign_status": str(campaign.get("status", "unknown")),
        "campaign_phase": str(campaign.get("phase", "unknown")),
        "campaign_updated_at": str(campaign.get("updated_at", "") or ""),
        "latest_report_path": str(campaign.get("latest_report_path", "") or ""),
        "operator_recommendation": str(scorecard.get("operator_recommendation", "needs_more_research")),
        "campaign_decision": str(scorecard.get("campaign_decision", "continue_research")),
        "campaign_reason": str(scorecard.get("campaign_reason", "unknown")),
        "headline": str(scorecard.get("summary", "")),
        "best_candidate": _scorecard_candidate_snapshot(selected_candidate, selected_stress)
        if selected_candidate is not None
        else None,
        "control_candidate": scorecard.get("control"),
        "why_this_candidate": scorecard.get("strengths", []),
        "what_failed_or_is_missing": scorecard.get("weaknesses", []),
        "next_action": str(next_steps[0]) if next_steps else "",
        "next_steps": next_steps,
        "artifact_paths": operability_artifact_paths(campaign.get("latest_report_path")),
        "progression": {
            "shortlist_count": len(shortlisted),
            "stress_result_count": len(stress_results),
            "selected_run_name": str(final_decision.get("selected_run_name") or selected_candidate.get("run_name") or "")
            if selected_candidate is not None
            else "",
            "selected_profile_name": str(final_decision.get("selected_profile_name") or selected_candidate.get("profile_name") or "")
            if selected_candidate is not None
            else "",
            "pivot_used": bool(final_decision.get("pivot_used", False)),
            "selected_candidate_eligible": bool(final_decision.get("selected_candidate_eligible", False)),
            "selected_stress_ok": bool(final_decision.get("selected_stress_ok", False)),
        },
        "supporting_summaries": {
            "candidate_readiness": _operator_supporting_summary(candidate_readiness),
            "paper_trade_readiness": _operator_supporting_summary(paper_trade_readiness),
        },
    }


def _render_summary_markdown(
    run_name: str,
    summary: dict[str, float],
    analytics: dict[str, object],
) -> str:
    benchmark = analytics.get("benchmark", {})
    benchmarks = analytics.get("benchmarks", {})
    primary_benchmark = analytics.get("primary_benchmark", "unknown")
    benchmark_return = benchmark.get("total_return") if isinstance(benchmark, dict) else None
    excess_return = None
    if benchmark_return is not None:
        excess_return = summary["total_return"] - benchmark_return

    lines = [
        f"# Run Report: {run_name}",
        "",
    ]

    metadata = analytics.get("run_metadata", {})
    if isinstance(metadata, dict) and metadata:
        lines.extend(
            [
                "## Run Metadata",
                "",
                f"- Strategy family: {metadata.get('strategy_family', 'unknown')}",
                f"- Sweep type: {metadata.get('sweep_type', 'baseline')}",
                f"- Parameter: {metadata.get('parameter_name', 'run_name')}={metadata.get('parameter_value', run_name)}",
                f"- Ranking mode: {metadata.get('ranking_mode', 'global')}",
                f"- Score transform: {metadata.get('score_transform', 'raw')}",
                f"- Research tranche: {metadata.get('research_tranche', '') or 'none'}",
                f"- Research slice: {metadata.get('research_slice_name', 'all')}",
                f"- Control profile: {metadata.get('control_profile', '') or 'none'}",
                f"- Promotion candidate: {bool(metadata.get('promotion_candidate', False))}",
                "",
            ]
        )

    research = analytics.get("research", {})
    if isinstance(research, dict) and research:
        lines.extend(
            [
                "## Research Profile",
                "",
                f"- Profile name: {research.get('profile_name', 'default')}",
                f"- Profile version: {research.get('profile_version', 'unversioned')}",
                f"- Frozen on: {research.get('frozen_on', 'unfrozen') or 'unfrozen'}",
                f"- Promoted: {bool(research.get('promoted', False))}",
                f"- Research tranche: {research.get('research_tranche', '') or 'none'}",
                f"- Research slice: {research.get('research_slice_name', 'all')}",
                f"- Control profile: {research.get('control_profile', '') or 'none'}",
                f"- Promotion candidate: {bool(research.get('promotion_candidate', False))}",
                "",
            ]
        )

    data_policy = analytics.get("data_policy", {})
    if isinstance(data_policy, dict) and data_policy:
        lines.extend(
            [
                "## Data Policy",
                "",
                f"- Source name: {data_policy.get('source_name', 'unknown')}",
                f"- Adjustment policy: {data_policy.get('adjustment_policy', 'unknown')}",
                f"- Signal price field: {data_policy.get('signal_price_field', 'unknown')}",
                f"- Execution price field: {data_policy.get('execution_price_field', 'unknown')}",
                "",
            ]
        )

    feature_info = analytics.get("features", {})
    if isinstance(feature_info, dict) and feature_info:
        lines.extend(
            [
                "## Feature Set",
                "",
                f"- Enabled: {bool(feature_info.get('enabled', False))}",
                f"- Set name: {feature_info.get('set_name', 'default')}",
                f"- Used precomputed features: {bool(feature_info.get('used_precomputed', False))}",
                "",
            ]
        )

    universe_lifecycle = analytics.get("universe_lifecycle", {})
    if isinstance(universe_lifecycle, dict) and universe_lifecycle:
        lines.extend(["## Universe Lifecycle", "",])
        for label, value in sorted(universe_lifecycle.items()):
            lines.append(f"- {label}: {int(value)}")
        lines.append("")

    period = analytics.get("period", {})
    if isinstance(period, dict) and period:
        lines.extend(
            [
                "## Period",
                "",
                f"- Label: {period.get('label', 'full_sample')}",
                f"- Start date: {period.get('start_date', 'unbounded') or 'unbounded'}",
                f"- End date: {period.get('end_date', 'unbounded') or 'unbounded'}",
                f"- Trading days: {int(period.get('trading_days', 0) or 0)}",
                "",
            ]
        )

    lines.extend(
        [
        "## Strategy Summary",
        "",
        f"- Ending NAV: {_float(summary, 'ending_nav'):.2f}",
        f"- Total return: {_float(summary, 'total_return'):.4%}",
        f"- Max drawdown: {_float(summary, 'max_drawdown'):.4%}",
        f"- Average gross exposure: {_float(summary, 'average_gross_exposure'):.4f}",
        f"- Max gross exposure: {_float(summary, 'max_gross_exposure'):.4f}",
        f"- Turnover: {_float(summary, 'turnover'):.4f}",
        f"- Trade count: {_float(summary, 'trade_count'):.0f}",
        f"- Closed trade count: {_float(summary, 'closed_trade_count'):.0f}",
        f"- Win rate: {_float(summary, 'win_rate'):.4%}",
        f"- Average daily return: {_float(summary, 'average_daily_return'):.4%}",
        "",
        "## Costs",
        "",
        f"- Total commission: {_float(summary, 'total_commission'):.2f}",
        f"- Total slippage: {_float(summary, 'total_slippage'):.2f}",
        f"- Total spread cost: {_float(summary, 'total_spread_cost'):.2f}",
        f"- Total stamp duty: {_float(summary, 'total_stamp_duty'):.2f}",
        "",
        "## Benchmark Comparison",
        "",
        ]
    )

    if benchmark_return is None:
        lines.append("- Benchmark: unavailable")
    else:
        lines.extend(
            [
                f"- Benchmark ending NAV: {benchmark['ending_nav']:.2f}",
                f"- Benchmark model: {primary_benchmark}",
                f"- Benchmark total return: {benchmark_return:.4%}",
                f"- Benchmark max drawdown: {benchmark['max_drawdown']:.4%}",
                f"- Excess return: {excess_return:.4%}",
            ]
        )

    if isinstance(benchmarks, dict) and len(benchmarks) > 1:
        lines.extend(["", "## Additional Benchmarks", ""])
        for benchmark_name, values in sorted(benchmarks.items()):
            if benchmark_name == primary_benchmark or not isinstance(values, dict) or not values:
                continue
            lines.append(
                f"- {benchmark_name}: total_return={float(values.get('total_return', 0.0) or 0.0):.4%}, "
                f"ending_nav={float(values.get('ending_nav', 0.0) or 0.0):.2f}, "
                f"max_drawdown={float(values.get('max_drawdown', 0.0) or 0.0):.4%}"
            )

    evaluation = analytics.get("evaluation", {})
    risk_diagnostics = analytics.get("risk_diagnostics", {})
    basket_diagnostics = analytics.get("basket_diagnostics", {})
    if isinstance(evaluation, dict):
        flags = evaluation.get("flags", [])
        policy = evaluation.get("policy", {})
        lines.extend(["", "## Evaluation", ""])
        status = evaluation.get("status", "unknown")
        lines.append(f"- Status: {status}")
        lines.append(f"- Trade count: {float(evaluation.get('trade_count', 0.0) or 0.0):.0f}")
        lines.append(f"- Turnover: {float(evaluation.get('turnover', 0.0) or 0.0):.4f}")
        lines.append(f"- Max drawdown: {float(evaluation.get('max_drawdown', 0.0) or 0.0):.4%}")
        lines.append(f"- Strategy return: {float(evaluation.get('strategy_return', 0.0) or 0.0):.4%}")
        lines.append(f"- Benchmark return: {float(evaluation.get('benchmark_return', 0.0) or 0.0):.4%}")
        lines.append(f"- Excess return: {float(evaluation.get('excess_return', 0.0) or 0.0):.4%}")
        if isinstance(policy, dict):
            lines.append(
                f"- Policy: profile_name={policy.get('profile_name', 'default')}, "
                f"warn_turnover={float(policy.get('warn_turnover', 0.0) or 0.0):.4f}, "
                f"fail_turnover={float(policy.get('fail_turnover', 0.0) or 0.0):.4f}, "
                f"warn_min_trade_count={int(policy.get('warn_min_trade_count', 0) or 0)}, "
                f"fail_min_trade_count={int(policy.get('fail_min_trade_count', 0) or 0)}, "
                f"warn_max_drawdown={float(policy.get('warn_max_drawdown', 0.0) or 0.0):.4%}, "
                f"fail_max_drawdown={float(policy.get('fail_max_drawdown', 0.0) or 0.0):.4%}, "
                f"warn_min_excess_return={float(policy.get('warn_min_excess_return', 0.0) or 0.0):.4%}, "
                f"fail_min_excess_return={float(policy.get('fail_min_excess_return', 0.0) or 0.0):.4%}, "
                f"flag_underperform_benchmark={bool(policy.get('flag_underperform_benchmark', False))}, "
                f"fail_on_zero_trade_run={bool(policy.get('fail_on_zero_trade_run', False))}"
            )
        warn_flags = evaluation.get("warn_flags", [])
        fail_flags = evaluation.get("fail_flags", [])
        if fail_flags:
            for flag in fail_flags:
                lines.append(f"- Fail flag: {flag}")
        if warn_flags:
            for flag in warn_flags:
                lines.append(f"- Warn flag: {flag}")
        if flags:
            for flag in flags:
                lines.append(f"- Flag: {flag}")
        else:
            lines.append("- Flag: none")

    if isinstance(risk_diagnostics, dict) and risk_diagnostics:
        lines.extend(["", "## Risk Diagnostics", ""])
        lines.append(f"- Beta to benchmark: {float(risk_diagnostics.get('beta_to_benchmark', 0.0) or 0.0):.4f}")
        lines.append(
            f"- Correlation to benchmark: {float(risk_diagnostics.get('correlation_to_benchmark', 0.0) or 0.0):.4f}"
        )
        lines.append(f"- Tracking error: {float(risk_diagnostics.get('tracking_error', 0.0) or 0.0):.4f}")
        lines.append(
            f"- Relative volatility: {float(risk_diagnostics.get('relative_volatility', 0.0) or 0.0):.4f}"
        )

    if isinstance(basket_diagnostics, dict) and basket_diagnostics:
        lines.extend(["", "## Basket Diagnostics", ""])
        lines.append(
            f"- Average portfolio names: {float(basket_diagnostics.get('average_portfolio_names', 0.0) or 0.0):.2f}"
        )
        lines.append(
            f"- Average unique sectors: {float(basket_diagnostics.get('average_unique_sectors', 0.0) or 0.0):.2f}"
        )
        lines.append(
            f"- Average unique industries: {float(basket_diagnostics.get('average_unique_industries', 0.0) or 0.0):.2f}"
        )
        lines.append(
            f"- Average sector concentration: {float(basket_diagnostics.get('average_sector_concentration', 0.0) or 0.0):.4f}"
        )
        lines.append(
            f"- Max sector concentration: {float(basket_diagnostics.get('max_sector_concentration', 0.0) or 0.0):.4f}"
        )
        lines.append(
            f"- Average industry concentration: {float(basket_diagnostics.get('average_industry_concentration', 0.0) or 0.0):.4f}"
        )
        lines.append(
            f"- Average active sector deviation: {float(basket_diagnostics.get('average_active_sector_deviation', 0.0) or 0.0):.4f}"
        )
        lines.append(
            f"- Average active benchmark-bucket deviation: {float(basket_diagnostics.get('average_active_benchmark_bucket_deviation', 0.0) or 0.0):.4f}"
        )

    fills_by_instrument = analytics.get("fills_by_instrument", {})
    if isinstance(fills_by_instrument, dict) and fills_by_instrument:
        lines.extend(["", "## Instrument Activity", ""])
        for instrument, values in sorted(fills_by_instrument.items()):
            lines.append(
                f"- {instrument}: trades={values['trade_count']:.0f}, notional={values['gross_notional']:.2f}, "
                f"commission={values['commission']:.2f}, slippage={values['slippage']:.2f}, "
                f"spread={values['spread_cost']:.2f}, stamp_duty={values['stamp_duty']:.2f}"
            )

    return "\n".join(lines) + "\n"


def _float(summary: dict[str, float], key: str) -> float:
    return float(summary.get(key, 0.0) or 0.0)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_comparison_markdown(
    report_name: str,
    rows: list[dict[str, object]],
    quality_gate: str = "all",
    excluded_rows: list[dict[str, object]] | None = None,
) -> str:
    lines = [
        f"# Comparison Report: {report_name}",
        "",
        "## Ranked Runs",
        "",
        f"- Quality gate: {quality_gate}",
        "",
    ]

    if not rows:
        lines.append("- No runs available")
        return "\n".join(lines) + "\n"

    active_rows = [row for row in rows if not bool(row.get("zero_trade", False))]
    zero_trade_rows = [row for row in rows if bool(row.get("zero_trade", False))]

    lines.extend(
        [
            f"- Pass runs: {sum(1 for row in rows if row.get('evaluation_status') == 'pass')}",
            f"- Warn runs: {sum(1 for row in rows if row.get('evaluation_status') == 'warn')}",
            f"- Fail runs: {sum(1 for row in rows if row.get('evaluation_status') == 'fail')}",
            "",
        ]
    )

    excluded = excluded_rows or []
    if excluded:
        lines.extend(["## Excluded Runs", ""])
        lines.append(f"- Excluded by quality gate: {len(excluded)}")
        for reason, count in sorted(_flag_counts(excluded).items()):
            lines.append(f"- Exclusion reason {reason}: {count}")
        lines.append("")

    profile_summary = _profile_summary(rows)
    if profile_summary:
        lines.extend(["## Profile Summary", ""])
        for profile_name, metrics in profile_summary.items():
            lines.append(
                f"- {profile_name}: pass={metrics['pass']}, warn={metrics['warn']}, fail={metrics['fail']}, "
                f"avg_excess_return={metrics['avg_excess_return']:.4%}, avg_total_return={metrics['avg_total_return']:.4%}"
            )
        lines.append("")

    for index, row in enumerate(active_rows, start=1):
        fail_flags = str(row.get("evaluation_fail_flags", "") or "")
        warn_flags = str(row.get("evaluation_warn_flags", "") or "")
        detail = ""
        if fail_flags:
            detail = f", fail_flags={fail_flags}"
        elif warn_flags:
            detail = f", warn_flags={warn_flags}"
        lines.append(
            f"{index}. {row['run_name']} [{row.get('strategy_family', 'unknown')}, profile={row.get('evaluation_profile', 'default')}, benchmark={row.get('primary_benchmark', 'unknown')}, period={row.get('period_label', 'full_sample')}]: total_return={float(row['total_return']):.4%}, "
            f"excess_return={float(row['excess_return']):.4%}, "
            f"excess_vs_equal_weight={float(row.get('excess_vs_equal_weight', 0.0)):.4%}, "
            f"excess_vs_price_weighted={float(row.get('excess_vs_price_weighted', 0.0)):.4%}, "
            f"max_drawdown={float(row['max_drawdown']):.4%}, "
            f"turnover={float(row['turnover']):.4f}, "
            f"trade_count={int(float(row['trade_count']))}, "
            f"return/turnover={float(row.get('return_per_turnover', 0.0)):.4f}, "
            f"return/drawdown={float(row.get('return_per_drawdown', 0.0)):.4f}, "
            f"status={row.get('evaluation_status', 'unknown')}{detail}"
        )

    if zero_trade_rows:
        lines.extend(["", "## Zero-Trade Runs", ""])
        for row in zero_trade_rows:
            lines.append(
                f"- {row['run_name']} [{row.get('strategy_family', 'unknown')}]: "
                f"profile={row.get('evaluation_profile', 'default')}, "
                f"benchmark={row.get('primary_benchmark', 'unknown')}, "
                f"period={row.get('period_label', 'full_sample')}, "
                f"parameter={row.get('parameter_name', 'unknown')}={row.get('parameter_value', '')}, "
                f"status={row.get('evaluation_status', 'unknown')}, "
                f"fail_flags={row.get('evaluation_fail_flags', '')}"
            )

    if active_rows:
        lines.extend(["", "## Notes", ""])
        lines.append("- Ranking prioritizes evaluation status first: pass runs, then warn runs, then fail runs. Within each class it ranks by excess return and then total return.")
        lines.append("- Zero-trade runs remain separated because they are usually structurally uninformative for strategy selection.")

    return "\n".join(lines) + "\n"


def _rank_comparison_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            _status_rank(str(row.get("evaluation_status", "unknown"))),
            not bool(row.get("zero_trade", False)),
            -int(row.get("evaluation_fail_count", 0) or 0),
            -int(row.get("evaluation_warn_count", 0) or 0),
            float(row.get("excess_return", 0.0)),
            float(row.get("total_return", 0.0)),
        ),
        reverse=True,
    )


def _status_rank(status: str) -> int:
    if status == "pass":
        return 3
    if status == "warn":
        return 2
    if status == "fail":
        return 1
    return 0


def _filter_comparison_rows(rows: list[dict[str, object]], quality_gate: str) -> list[dict[str, object]]:
    if quality_gate == "pass":
        return [row for row in rows if row.get("evaluation_status") == "pass"]
    if quality_gate == "pass_warn":
        return [row for row in rows if row.get("evaluation_status") in {"pass", "warn"}]
    return list(rows)


def _excluded_rows(
    all_rows: list[dict[str, object]],
    filtered_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    allowed_names = {str(row.get("run_name")) for row in filtered_rows}
    return [row for row in all_rows if str(row.get("run_name")) not in allowed_names]


def _flag_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        fail_flags = str(row.get("evaluation_fail_flags", "") or "")
        warn_flags = str(row.get("evaluation_warn_flags", "") or "")
        status = str(row.get("evaluation_status", "unknown") or "unknown")
        raw_flags = ",".join(part for part in [fail_flags, warn_flags] if part)
        if not raw_flags:
            counts[f"status:{status}"] = counts.get(f"status:{status}", 0) + 1
            continue
        for flag in [item.strip() for item in raw_flags.split(",") if item.strip()]:
            counts[flag] = counts.get(flag, 0) + 1
    return counts


def _profile_summary(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    profiles = {str(row.get("evaluation_profile", "default")) for row in rows}
    if len(profiles) <= 1:
        return {}

    summary: dict[str, dict[str, float]] = {}
    for profile_name in sorted(profiles):
        profile_rows = [row for row in rows if str(row.get("evaluation_profile", "default")) == profile_name]
        count = len(profile_rows)
        summary[profile_name] = {
            "pass": float(sum(1 for row in profile_rows if row.get("evaluation_status") == "pass")),
            "warn": float(sum(1 for row in profile_rows if row.get("evaluation_status") == "warn")),
            "fail": float(sum(1 for row in profile_rows if row.get("evaluation_status") == "fail")),
            "avg_excess_return": 0.0 if count == 0 else sum(float(row.get("excess_return", 0.0) or 0.0) for row in profile_rows) / count,
            "avg_total_return": 0.0 if count == 0 else sum(float(row.get("total_return", 0.0) or 0.0) for row in profile_rows) / count,
        }
    return summary


def _render_experiment_index(
    report_name: str,
    rows: list[dict[str, object]],
    quality_gate: str = "all",
    excluded_rows: list[dict[str, object]] | None = None,
) -> str:
    lines = [
        f"# Experiment Index: {report_name}",
        "",
        "## Summary",
        "",
        f"- Quality gate: {quality_gate}",
        f"- Total runs: {len(rows)}",
        f"- Zero-trade runs: {sum(1 for row in rows if bool(row.get('zero_trade', False)))}",
        f"- Underperforming benchmark: {sum(1 for row in rows if float(row.get('excess_return', 0.0)) < 0)}",
        "",
    ]

    excluded = excluded_rows or []
    if excluded:
        lines.extend(
            [
                "## Excluded Runs",
                "",
                f"- Excluded by quality gate: {len(excluded)}",
            ]
        )
        for reason, count in sorted(_flag_counts(excluded).items()):
            lines.append(f"- Exclusion reason {reason}: {count}")
        lines.extend(["", "## Runs", ""])
    else:
        lines.extend([
        "## Runs",
        "",
        ])

    for row in sorted(rows, key=lambda item: item["run_name"]):
        lines.append(
            f"- {row['run_name']}: strategy={row.get('strategy_family', 'unknown')}, "
            f"profile={row.get('evaluation_profile', 'default')}, "
            f"benchmark={row.get('primary_benchmark', 'unknown')}, "
            f"period={row.get('period_label', 'full_sample')}, "
            f"sweep={row.get('sweep_type', 'unknown')}, "
            f"parameter={row.get('parameter_name', 'unknown')}={row.get('parameter_value', '')}, "
            f"status={row.get('evaluation_status', 'unknown')}, "
            f"zero_trade={row.get('zero_trade', False)}"
        )

    return "\n".join(lines) + "\n"


def _render_promotion_markdown(
    entry: dict[str, object],
    previous_entry: dict[str, object] | None,
) -> str:
    profile = entry.get("profile", {}) if isinstance(entry, dict) else {}
    walkforward = entry.get("walkforward_summary", {}) if isinstance(entry, dict) else {}
    split_summary = entry.get("split_summary", {}) if isinstance(entry, dict) else {}
    fail_reasons = entry.get("fail_reasons", []) if isinstance(entry, dict) else []
    policy = entry.get("policy", {}) if isinstance(entry, dict) else {}

    lines = [
        "# Promotion Summary",
        "",
        "## Profile",
        "",
        f"- Profile name: {profile.get('profile_name', 'unknown')}",
        f"- Profile version: {profile.get('profile_version', 'unversioned')}",
        f"- Frozen on: {profile.get('frozen_on', 'unfrozen') or 'unfrozen'}",
        f"- Current promoted flag: {bool(entry.get('current_promoted', False))}",
        f"- Eligible: {bool(entry.get('eligible', False))}",
        f"- Recommended action: {entry.get('recommended_action', 'retain')}",
        f"- Recorded at UTC: {entry.get('recorded_at_utc', 'unknown')}",
        f"- Config path: {entry.get('config_path', 'unknown')}",
        "",
        "## Walk-Forward",
        "",
        f"- Window count: {int(walkforward.get('window_count', 0) or 0)}",
        f"- Pass windows: {int(walkforward.get('pass_windows', 0) or 0)}",
        f"- Eligible: {bool(walkforward.get('eligible', False))}",
        f"- Average excess return: {float(walkforward.get('average_excess_return', 0.0) or 0.0):.4%}",
        f"- Average drawdown: {float(walkforward.get('average_drawdown', 0.0) or 0.0):.4%}",
        f"- Average turnover: {float(walkforward.get('average_turnover', 0.0) or 0.0):.4f}",
        "",
        "## Split Summary",
        "",
    ]

    for label, result in sorted(split_summary.items()):
        if not isinstance(result, dict):
            continue
        lines.append(
            f"- {label}: status={result.get('status', 'unknown')}, "
            f"total_return={float(result.get('total_return', 0.0) or 0.0):.4%}, "
            f"excess_return={float(result.get('excess_return', 0.0) or 0.0):.4%}, "
            f"max_drawdown={float(result.get('max_drawdown', 0.0) or 0.0):.4%}, "
            f"turnover={float(result.get('turnover', 0.0) or 0.0):.4f}"
        )

    lines.extend(["", "## Policy", ""])
    for key, value in policy.items():
        if isinstance(value, float):
            if "drawdown" in key or "return" in key:
                lines.append(f"- {key}: {value:.4%}")
            else:
                lines.append(f"- {key}: {value:.4f}")
        else:
            lines.append(f"- {key}: {value}")

    lines.extend(["", "## Decision", ""])
    if fail_reasons:
        for reason in fail_reasons:
            lines.append(f"- Fail reason: {reason}")
    else:
        lines.append("- Fail reason: none")

    if previous_entry:
        previous_profile = previous_entry.get("profile", {}) if isinstance(previous_entry, dict) else {}
        lines.extend(["", "## Previous Record", ""])
        lines.append(f"- Previous version: {previous_profile.get('profile_version', 'unknown')}")
        lines.append(f"- Previous eligible: {bool(previous_entry.get('eligible', False))}")
        lines.append(f"- Previous recorded at UTC: {previous_entry.get('recorded_at_utc', 'unknown')}")

    return "\n".join(lines) + "\n"


def _build_research_decision(
    report_name: str,
    ranked_rows: list[dict[str, object]],
    all_rows: list[dict[str, object]],
    quality_gate: str,
) -> dict[str, object]:
    if not ranked_rows:
        return {
            "report_name": report_name,
            "quality_gate": quality_gate,
            "recommended_action": "no_candidate",
            "reason": "no_ranked_runs_after_quality_gate",
            "top_evaluation_status": "unknown",
        }

    top = ranked_rows[0]
    raw_return_leader = max(all_rows, key=lambda row: float(row.get("total_return", 0.0) or 0.0)) if all_rows else top
    recommended_action = "investigate_top_candidate"
    reason = "top_ranked_run_balances_return_and_evaluation"
    if str(top.get("evaluation_status", "unknown")) == "fail":
        recommended_action = "reject_current_set"
        reason = "best_available_run_still_fails_evaluation"
    elif str(raw_return_leader.get("run_name")) != str(top.get("run_name")):
        reason = "higher_raw_return_run_rejected_by_evaluation_or_quality_gate"

    return {
        "report_name": report_name,
        "quality_gate": quality_gate,
        "recommended_action": recommended_action,
        "reason": reason,
        "top_run_name": top.get("run_name"),
        "top_evaluation_status": top.get("evaluation_status", "unknown"),
        "top_total_return": float(top.get("total_return", 0.0) or 0.0),
        "top_excess_return": float(top.get("excess_return", 0.0) or 0.0),
        "top_max_drawdown": float(top.get("max_drawdown", 0.0) or 0.0),
        "top_turnover": float(top.get("turnover", 0.0) or 0.0),
        "higher_raw_return_run_name": raw_return_leader.get("run_name"),
        "higher_raw_return": float(raw_return_leader.get("total_return", 0.0) or 0.0),
        "top_profile_name": top.get("evaluation_profile", "default"),
        "strategy_family": top.get("strategy_family", "unknown"),
        "sweep_type": top.get("sweep_type", "unknown"),
    }


def _render_research_decision_markdown(decision: dict[str, object]) -> str:
    lines = [
        "# Research Decision",
        "",
        f"- Recommended action: {decision.get('recommended_action', 'retain')}",
        f"- Reason: {decision.get('reason', 'unknown')}",
        f"- Quality gate: {decision.get('quality_gate', 'all')}",
        f"- Top run: {decision.get('top_run_name', 'none')}",
        f"- Top status: {decision.get('top_evaluation_status', 'unknown')}",
        f"- Top total return: {float(decision.get('top_total_return', 0.0) or 0.0):.4%}",
        f"- Top excess return: {float(decision.get('top_excess_return', 0.0) or 0.0):.4%}",
        f"- Top max drawdown: {float(decision.get('top_max_drawdown', 0.0) or 0.0):.4%}",
        f"- Top turnover: {float(decision.get('top_turnover', 0.0) or 0.0):.4f}",
        f"- Higher raw return run: {decision.get('higher_raw_return_run_name', 'none')}",
        f"- Higher raw return: {float(decision.get('higher_raw_return', 0.0) or 0.0):.4%}",
    ]
    return "\n".join(lines) + "\n"


def _select_scorecard_candidate(
    shortlisted: list[dict[str, object]],
    final_decision: dict[str, object],
) -> dict[str, object] | None:
    selected_run_name = str(final_decision.get("selected_run_name") or "")
    if selected_run_name:
        for row in shortlisted:
            if str(row.get("run_name", "")) == selected_run_name:
                return row
    return shortlisted[0] if shortlisted else None


def _select_scorecard_stress_result(
    stress_results: list[dict[str, object]],
    selected_candidate: dict[str, object] | None,
    final_decision: dict[str, object],
) -> dict[str, object] | None:
    selected_run_name = str(final_decision.get("selected_run_name") or "")
    if not selected_run_name and selected_candidate is not None:
        selected_run_name = str(selected_candidate.get("run_name", ""))
    for row in stress_results:
        if str(row.get("candidate_run_name", "")) == selected_run_name:
            return row
    return None


def _operator_recommendation(final_decision: dict[str, object]) -> str:
    action = str(final_decision.get("recommended_action", "continue_research"))
    if action == "freeze_candidate":
        return "paper_trade_next"
    if action in {
        "continue_research",
        "continue_benchmark_pivot",
        "continue_focused_research",
        "continue_operability_validation",
        "stopped",
    }:
        return "needs_more_research"
    return "reject"


def _scorecard_summary(
    operator_recommendation: str,
    selected_candidate: dict[str, object] | None,
    final_decision: dict[str, object],
) -> str:
    if operator_recommendation == "paper_trade_next" and selected_candidate is not None:
        return (
            f"The current best candidate is {selected_candidate.get('run_name', 'unknown')}. "
            "It passed the promotion gate and the configured stress pack, so the next boundary is paper-trading preparation."
        )
    if operator_recommendation == "needs_more_research":
        return (
            "The campaign found useful evidence, but the result is not yet strong enough to treat as paper-trading ready. "
            "More research or a policy pivot is still required."
        )
    return (
        "This campaign should be treated as a rejected current branch. "
        f"Recorded campaign reason: {final_decision.get('reason', 'unknown')}."
    )


def _scorecard_strengths(
    control_row: dict[str, object],
    selected_candidate: dict[str, object] | None,
    selected_stress: dict[str, object] | None,
    final_decision: dict[str, object],
) -> list[str]:
    if selected_candidate is None:
        return ["No candidate emerged strongly enough to summarize as an operational strength."]
    strengths: list[str] = []
    if bool(selected_candidate.get("eligible", False)):
        strengths.append("Passed the promotion eligibility gate.")
    validation = float(selected_candidate.get("validation_excess_return", 0.0) or 0.0)
    if validation > 0:
        strengths.append(f"Produced positive validation excess return of {validation:.2%}.")
    holdout = float(selected_candidate.get("holdout_excess_return", 0.0) or 0.0)
    if holdout > 0:
        strengths.append(f"Produced positive holdout excess return of {holdout:.2%}.")
    candidate_windows = int(selected_candidate.get("walkforward_pass_windows", 0) or 0)
    control_windows = int(control_row.get("walkforward_pass_windows", 0) or 0)
    if candidate_windows > control_windows:
        strengths.append(
            f"Improved walk-forward pass windows from {control_windows} on the control to {candidate_windows}."
        )
    if selected_stress is not None and bool(selected_stress.get("stress_ok", False)):
        strengths.append("Stayed non-broken across all configured stress scenarios.")
    if final_decision.get("recommended_action") == "freeze_candidate":
        strengths.append("Strong enough to freeze as the current best strategy candidate.")
    return strengths or ["The candidate reached the shortlist, which means it outperformed many weaker variants."]


def _scorecard_weaknesses(
    control_row: dict[str, object],
    selected_candidate: dict[str, object] | None,
    selected_stress: dict[str, object] | None,
    final_decision: dict[str, object],
) -> list[str]:
    weaknesses: list[str] = []
    if selected_candidate is None:
        weaknesses.append("No selected candidate is available for operator review.")
    else:
        if float(selected_candidate.get("holdout_excess_return", 0.0) or 0.0) <= 0:
            weaknesses.append("Holdout excess return is not yet convincingly positive.")
        if int(selected_candidate.get("walkforward_pass_windows", 0) or 0) <= int(
            control_row.get("walkforward_pass_windows", 0) or 0
        ):
            weaknesses.append("Walk-forward evidence did not clearly beat the control.")
        if selected_stress is not None and not bool(selected_stress.get("stress_ok", False)):
            weaknesses.append("Stress-pack evidence is incomplete or contains broken scenarios.")
        rejection_reason = str(selected_candidate.get("rejection_reason", "") or "")
        if rejection_reason:
            weaknesses.append(f"Recorded rejection warning: {rejection_reason}.")
    if final_decision.get("recommended_action") in {"failed", "exhausted"}:
        weaknesses.append("The campaign finished without enough evidence to keep this branch alive.")
    if final_decision.get("pivot_used"):
        weaknesses.append("The campaign required a pivot to recover evidence, which suggests the base family was fragile.")
    return weaknesses or ["No major weakness was recorded, but operator review is still required before any paper phase."]


def _scorecard_next_steps(operator_recommendation: str) -> list[str]:
    if operator_recommendation == "paper_trade_next":
        return [
            "Review the frozen candidate and confirm the result is understandable to the operator.",
            "Prepare the paper-trading boundary: daily decision exports, monitoring, and operational checks.",
            "Do not move to live trading until paper-trading design and controls are in place.",
        ]
    if operator_recommendation == "needs_more_research":
        return [
            "Keep this candidate in research mode rather than treating it as deployable.",
            "Use the scorecard weaknesses to decide whether to continue the family or pivot to the next branch.",
            "Wait for stronger holdout, walk-forward, or stress evidence before paper-trading consideration.",
        ]
    return [
        "Treat the current branch as rejected.",
        "Do not promote it into paper trading.",
        "Move research effort to the next approved family or director plan entry.",
    ]


def _scorecard_candidate_snapshot(
    row: dict[str, object] | None,
    stress_result: dict[str, object] | None,
) -> dict[str, object]:
    payload = row if isinstance(row, dict) else {}
    snapshot = {
        "run_name": str(payload.get("run_name", "unknown")),
        "profile_name": str(payload.get("profile_name", "unknown")),
        "validation_excess_return": float(payload.get("validation_excess_return", 0.0) or 0.0),
        "holdout_excess_return": float(payload.get("holdout_excess_return", 0.0) or 0.0),
        "walkforward_pass_windows": int(payload.get("walkforward_pass_windows", 0) or 0),
        "rebalance_frequency_days": int(payload.get("rebalance_frequency_days", 0) or 0),
        "max_rebalance_turnover_pct": float(payload.get("max_rebalance_turnover_pct", 0.0) or 0.0),
        "eligible": bool(payload.get("eligible", False)),
    }
    if stress_result is not None:
        snapshot["stress_ok"] = bool(stress_result.get("stress_ok", False))
        snapshot["stress_non_broken_count"] = int(stress_result.get("non_broken_count", 0) or 0)
        snapshot["stress_scenario_count"] = int(stress_result.get("scenario_count", 0) or 0)
    return snapshot


def _scorecard_comparison(
    control_row: dict[str, object],
    selected_candidate: dict[str, object] | None,
    selected_stress: dict[str, object] | None,
) -> dict[str, object]:
    control_validation = float(control_row.get("validation_excess_return", 0.0) or 0.0)
    control_holdout = float(control_row.get("holdout_excess_return", 0.0) or 0.0)
    control_walkforward = int(control_row.get("walkforward_pass_windows", 0) or 0)
    if selected_candidate is None:
        return {
            "control": _scorecard_candidate_snapshot(control_row, None),
            "candidate": None,
            "deltas": {
                "validation_excess_return": None,
                "holdout_excess_return": None,
                "walkforward_pass_windows": None,
            },
        }
    return {
        "control": _scorecard_candidate_snapshot(control_row, None),
        "candidate": _scorecard_candidate_snapshot(selected_candidate, selected_stress),
        "deltas": {
            "validation_excess_return": float(selected_candidate.get("validation_excess_return", 0.0) or 0.0)
            - control_validation,
            "holdout_excess_return": float(selected_candidate.get("holdout_excess_return", 0.0) or 0.0)
            - control_holdout,
            "walkforward_pass_windows": int(selected_candidate.get("walkforward_pass_windows", 0) or 0)
            - control_walkforward,
        },
    }


def _operator_supporting_summary(summary: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(summary, dict) or not summary:
        return None
    return {
        "agent_id": str(summary.get("agent_id", "unknown")),
        "classification": str(summary.get("classification", "unknown")),
        "status": str(summary.get("status", "unknown")),
        "recommended_action": str(summary.get("recommended_action", "unknown")),
        "message": str(summary.get("message", "") or ""),
        "recorded_at_utc": str(summary.get("recorded_at_utc", "") or ""),
    }


def _render_operability_scorecard_markdown(scorecard: dict[str, object]) -> str:
    selected = scorecard.get("selected_candidate", {}) if isinstance(scorecard.get("selected_candidate"), dict) else {}
    control = scorecard.get("control", {}) if isinstance(scorecard.get("control"), dict) else {}
    comparison = scorecard.get("comparison", {}) if isinstance(scorecard.get("comparison"), dict) else {}
    deltas = comparison.get("deltas", {}) if isinstance(comparison.get("deltas"), dict) else {}
    lines = [
        "# Operator Scorecard",
        "",
        f"- Operator recommendation: {scorecard.get('operator_recommendation', 'needs_more_research')}",
        f"- Campaign decision: {scorecard.get('campaign_decision', 'continue_research')}",
        f"- Campaign reason: {scorecard.get('campaign_reason', 'unknown')}",
        "",
        "## Summary",
        "",
        str(scorecard.get("summary", "")),
        "",
        "## Selected Candidate",
        "",
        f"- Run: {selected.get('run_name', 'unknown')}",
        f"- Profile: {selected.get('profile_name', 'unknown')}",
        f"- Validation excess return: {float(selected.get('validation_excess_return', 0.0) or 0.0):.4%}",
        f"- Holdout excess return: {float(selected.get('holdout_excess_return', 0.0) or 0.0):.4%}",
        f"- Walk-forward pass windows: {int(selected.get('walkforward_pass_windows', 0) or 0)}",
        "",
        "## Control Comparison",
        "",
        f"- Control run: {control.get('run_name', 'unknown')}",
        f"- Validation excess delta: {_format_optional_percent(deltas.get('validation_excess_return'))}",
        f"- Holdout excess delta: {_format_optional_percent(deltas.get('holdout_excess_return'))}",
        f"- Walk-forward delta: {_format_optional_int(deltas.get('walkforward_pass_windows'))}",
        "",
        "## Strengths",
        "",
    ]
    for item in scorecard.get("strengths", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Weaknesses", ""])
    for item in scorecard.get("weaknesses", []):
        lines.append(f"- {item}")
    lines.extend(["", "## Next Steps", ""])
    for item in scorecard.get("next_steps", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _render_operability_comparison_markdown(scorecard: dict[str, object]) -> str:
    comparison = scorecard.get("comparison", {}) if isinstance(scorecard.get("comparison"), dict) else {}
    control = comparison.get("control", {}) if isinstance(comparison.get("control"), dict) else {}
    candidate = comparison.get("candidate", {}) if isinstance(comparison.get("candidate"), dict) else {}
    deltas = comparison.get("deltas", {}) if isinstance(comparison.get("deltas"), dict) else {}
    lines = [
        "# Candidate Comparison",
        "",
        "## Control",
        "",
        f"- Run: {control.get('run_name', 'unknown')}",
        f"- Profile: {control.get('profile_name', 'unknown')}",
        f"- Validation excess return: {float(control.get('validation_excess_return', 0.0) or 0.0):.4%}",
        f"- Holdout excess return: {float(control.get('holdout_excess_return', 0.0) or 0.0):.4%}",
        f"- Walk-forward pass windows: {int(control.get('walkforward_pass_windows', 0) or 0)}",
        "",
        "## Selected Candidate",
        "",
        f"- Run: {candidate.get('run_name', 'unknown')}",
        f"- Profile: {candidate.get('profile_name', 'unknown')}",
        f"- Validation excess return: {float(candidate.get('validation_excess_return', 0.0) or 0.0):.4%}",
        f"- Holdout excess return: {float(candidate.get('holdout_excess_return', 0.0) or 0.0):.4%}",
        f"- Walk-forward pass windows: {int(candidate.get('walkforward_pass_windows', 0) or 0)}",
        "",
        "## Deltas",
        "",
        f"- Validation excess delta: {_format_optional_percent(deltas.get('validation_excess_return'))}",
        f"- Holdout excess delta: {_format_optional_percent(deltas.get('holdout_excess_return'))}",
        f"- Walk-forward delta: {_format_optional_int(deltas.get('walkforward_pass_windows'))}",
    ]
    return "\n".join(lines) + "\n"


def _rank_tranche_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: row.get(
            "decision_score",
            (
                bool(row.get("eligible", False)),
                float(row.get("validation_excess_return", 0.0) or 0.0),
                float(row.get("holdout_excess_return", 0.0) or 0.0),
                int(row.get("walkforward_pass_windows", 0) or 0),
                -(float(row.get("validation_turnover", 0.0) or 0.0) + float(row.get("holdout_turnover", 0.0) or 0.0)),
                -(float(row.get("validation_drawdown", 0.0) or 0.0) + float(row.get("holdout_drawdown", 0.0) or 0.0)),
            ),
        ),
        reverse=True,
    )


def _render_tranche_markdown(
    tranche_name: str,
    control_row: dict[str, object],
    candidate_rows: list[dict[str, object]],
    decision: dict[str, object],
) -> str:
    lines = [
        f"# Research Tranche Report: {tranche_name}",
        "",
        "## Control",
        "",
        f"- Run: {control_row.get('run_name', 'unknown')}",
        f"- Profile: {control_row.get('profile_name', 'unknown')}",
        f"- Validation excess return: {float(control_row.get('validation_excess_return', 0.0) or 0.0):.4%}",
        f"- Holdout excess return: {float(control_row.get('holdout_excess_return', 0.0) or 0.0):.4%}",
        f"- Walk-forward pass windows: {int(control_row.get('walkforward_pass_windows', 0) or 0)}",
        "",
        "## Candidates",
        "",
    ]
    if not candidate_rows:
        lines.append("- No candidates available")
    else:
        for index, row in enumerate(candidate_rows, start=1):
            rejection_reason = str(row.get("rejection_reason", "") or "")
            extra = f", rejection_reason={rejection_reason}" if rejection_reason else ""
            lines.append(
                f"{index}. {row.get('run_name', 'unknown')} "
                f"[slice={row.get('research_slice_name', 'all')}, ranking={row.get('ranking_mode', 'global')}, transform={row.get('score_transform', 'raw')}]: "
                f"validation_excess={float(row.get('validation_excess_return', 0.0) or 0.0):.4%}, "
                f"holdout_excess={float(row.get('holdout_excess_return', 0.0) or 0.0):.4%}, "
                f"wf_pass={int(row.get('walkforward_pass_windows', 0) or 0)}, "
                f"eligible={bool(row.get('eligible', False))}, "
                f"validation_status={row.get('validation_status', 'unknown')}, "
                f"holdout_status={row.get('holdout_status', 'unknown')}{extra}"
            )

    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Recommended action: {decision.get('recommended_action', 'continue_research')}",
            f"- Reason: {decision.get('reason', 'unknown')}",
            f"- Selected run: {decision.get('selected_run_name', 'none') or 'none'}",
            f"- Selected profile: {decision.get('selected_profile_name', 'none') or 'none'}",
        ]
    )

    rejected_candidates = decision.get("rejected_candidates", [])
    if isinstance(rejected_candidates, list) and rejected_candidates:
        lines.extend(["", "## Rejected Candidates", ""])
        for entry in rejected_candidates:
            if isinstance(entry, dict):
                lines.append(f"- {entry.get('run_name', 'unknown')}: {entry.get('reason', 'unknown')}")

    return "\n".join(lines) + "\n"


def _dominant_value(rows: list[dict[str, object]], key: str) -> str:
    if not rows:
        return "unknown"
    return str(rows[0].get(key, "unknown"))


def _decision_profile_name(
    ranked_rows: list[dict[str, object]],
    all_rows: list[dict[str, object]],
) -> str:
    source = ranked_rows or all_rows
    if not source:
        return "unknown"
    return str(source[0].get("evaluation_profile", "default"))


def safe_artifact_dirname(name: str, *, max_length: int = 96) -> str:
    cleaned = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in name)
    cleaned = cleaned.strip("._") or "artifact"
    if len(cleaned) <= max_length:
        return cleaned
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    keep = max(8, max_length - len(digest) - 1)
    return f"{cleaned[:keep]}-{digest}"


def _last_history_entry(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if line.strip():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


def _render_operability_program_markdown(
    control_row: dict[str, object],
    focused_result: dict[str, object],
    pivot_result: dict[str, object] | None,
    shortlisted: list[dict[str, object]],
    stress_results: list[dict[str, object]],
    final_decision: dict[str, object],
) -> str:
    lines = [
        "# Operability Program",
        "",
        "## Control",
        "",
        f"- Run: {control_row.get('run_name', 'unknown')}",
        f"- Profile: {control_row.get('profile_name', 'unknown')}",
        f"- Validation excess return: {float(control_row.get('validation_excess_return', 0.0) or 0.0):.4%}",
        f"- Holdout excess return: {float(control_row.get('holdout_excess_return', 0.0) or 0.0):.4%}",
        f"- Walk-forward pass windows: {int(control_row.get('walkforward_pass_windows', 0) or 0)}",
        "",
        "## Focused Tranche",
        "",
        f"- Selected run: {focused_result.get('decision', {}).get('selected_run_name', 'none') or 'none'}",
        f"- Candidate count: {int(focused_result.get('decision', {}).get('candidate_count', 0) or 0)}",
        f"- Viable candidates: {int(focused_result.get('decision', {}).get('viable_candidate_count', 0) or 0)}",
        f"- Focused success: {bool(focused_result.get('decision', {}).get('focused_success', False))}",
        f"- Reason: {focused_result.get('decision', {}).get('reason', 'unknown')}",
        "",
    ]
    if pivot_result:
        lines.extend(
            [
                "## Pivot Tranche",
                "",
                f"- Selected run: {pivot_result.get('decision', {}).get('selected_run_name', 'none') or 'none'}",
                f"- Candidate count: {int(pivot_result.get('decision', {}).get('candidate_count', 0) or 0)}",
                f"- Viable candidates: {int(pivot_result.get('decision', {}).get('viable_candidate_count', 0) or 0)}",
                f"- Focused success: {bool(pivot_result.get('decision', {}).get('focused_success', False))}",
                f"- Reason: {pivot_result.get('decision', {}).get('reason', 'unknown')}",
                "",
            ]
        )
    lines.extend(["## Shortlist", ""])
    if not shortlisted:
        lines.append("- No shortlisted candidates")
    else:
        for row in shortlisted:
            lines.append(
                f"- {row.get('run_name', 'unknown')}: eligible={bool(row.get('eligible', False))}, "
                f"validation_excess={float(row.get('validation_excess_return', 0.0) or 0.0):.4%}, "
                f"holdout_excess={float(row.get('holdout_excess_return', 0.0) or 0.0):.4%}, "
                f"wf_pass={int(row.get('walkforward_pass_windows', 0) or 0)}, "
                f"rebalance_days={int(row.get('rebalance_frequency_days', 0) or 0)}, "
                f"max_rebalance_turnover={float(row.get('max_rebalance_turnover_pct', 0.0) or 0.0):.4f}"
            )
    lines.extend(["", "## Stress Pack", ""])
    if not stress_results:
        lines.append("- No stress results")
    else:
        for result in stress_results:
            lines.append(
                f"- {result.get('candidate_run_name', 'unknown')}: "
                f"stress_ok={bool(result.get('stress_ok', False))}, "
                f"non_broken={int(result.get('non_broken_count', 0) or 0)}/{int(result.get('scenario_count', 0) or 0)}"
            )
            for scenario in result.get("scenarios", []):
                if not isinstance(scenario, dict):
                    continue
                lines.append(
                    f"- scenario={scenario.get('scenario_name', 'unknown')}, "
                    f"validation_status={scenario.get('validation_status', 'unknown')}, "
                    f"holdout_status={scenario.get('holdout_status', 'unknown')}, "
                    f"holdout_excess={float(scenario.get('holdout_excess_return', 0.0) or 0.0):.4%}, "
                    f"non_broken={bool(scenario.get('non_broken', False))}"
                )
    lines.extend(
        [
            "",
            "## Final Recommendation",
            "",
            f"- Recommended action: {final_decision.get('recommended_action', 'continue_research')}",
            f"- Reason: {final_decision.get('reason', 'unknown')}",
            f"- Selected run: {final_decision.get('selected_run_name', 'none') or 'none'}",
            f"- Selected profile: {final_decision.get('selected_profile_name', 'none') or 'none'}",
            f"- Selected candidate eligible: {bool(final_decision.get('selected_candidate_eligible', False))}",
            f"- Selected stress ok: {bool(final_decision.get('selected_stress_ok', False))}",
            f"- Pivot used: {bool(final_decision.get('pivot_used', False))}",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_paper_trade_decision_markdown(decision_package: dict[str, object]) -> str:
    summary = str(decision_package.get("summary", ""))
    warnings = decision_package.get("warnings", []) if isinstance(decision_package.get("warnings"), list) else []
    action_summary = decision_package.get("action_summary", {}) if isinstance(decision_package.get("action_summary"), dict) else {}
    target_rows = [
        row for row in decision_package.get("target_holdings", []) if isinstance(row, dict)
    ] if isinstance(decision_package.get("target_holdings"), list) else []
    lines = [
        "# Paper-Trade Decision Package",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Package Metadata",
        "",
        f"- Decision date: {decision_package.get('decision_date', 'unknown')}",
        f"- Reference date: {decision_package.get('reference_date', 'unspecified') or 'unspecified'}",
        f"- Latest data date: {decision_package.get('latest_data_date', 'unknown')}",
        f"- Next trade date: {decision_package.get('next_trade_date', 'unavailable') or 'unavailable'}",
        f"- Profile name: {decision_package.get('profile_name', 'unknown')}",
        f"- Profile version: {decision_package.get('profile_version', 'unversioned')}",
        f"- Promoted flag: {bool(decision_package.get('promoted', False))}",
        f"- Strategy name: {decision_package.get('strategy_name', 'unknown')}",
        f"- Current NAV: {float(decision_package.get('current_nav', 0.0) or 0.0):.2f}",
        f"- Target gross exposure: {float(decision_package.get('target_gross_exposure', 0.0) or 0.0):.2%}",
        f"- Expected turnover: {float(decision_package.get('expected_turnover', 0.0) or 0.0):.2%}",
        "",
        "## Rebalance Action Summary",
        "",
        f"- Adds: {int(action_summary.get('adds', 0) or 0)}",
        f"- Increases: {int(action_summary.get('increases', 0) or 0)}",
        f"- Trims: {int(action_summary.get('trims', 0) or 0)}",
        f"- Exits: {int(action_summary.get('exits', 0) or 0)}",
        f"- Holds: {int(action_summary.get('holds', 0) or 0)}",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")

    lines.extend(["", "## Target Holdings", ""])
    for row in target_rows:
        lines.append(
            f"- {row.get('instrument', 'unknown')}: action={row.get('action', 'hold')}, "
            f"current_quantity={int(row.get('current_quantity', 0) or 0)}, "
            f"projected_quantity={int(row.get('projected_quantity', 0) or 0)}, "
            f"target_weight={float(row.get('target_weight', 0.0) or 0.0):.2%}, "
            f"projected_weight={float(row.get('projected_weight', 0.0) or 0.0):.2%}"
        )
    return "\n".join(lines) + "\n"


def _flatten_stress_rows(stress_results: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in stress_results:
        candidate_run_name = str(result.get("candidate_run_name", "unknown"))
        candidate_profile_name = str(result.get("candidate_profile_name", "unknown"))
        for scenario in result.get("scenarios", []):
            if not isinstance(scenario, dict):
                continue
            rows.append(
                {
                    "candidate_run_name": candidate_run_name,
                    "candidate_profile_name": candidate_profile_name,
                    "stress_ok": bool(result.get("stress_ok", False)),
                    "scenario_name": str(scenario.get("scenario_name", "unknown")),
                    "validation_status": str(scenario.get("validation_status", "unknown")),
                    "holdout_status": str(scenario.get("holdout_status", "unknown")),
                    "holdout_excess_return": float(scenario.get("holdout_excess_return", 0.0) or 0.0),
                    "walkforward_pass_windows": int(scenario.get("walkforward_pass_windows", 0) or 0),
                    "non_broken": bool(scenario.get("non_broken", False)),
                }
            )
    return rows


def _format_optional_percent(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value or 0.0):.4%}"


def _format_optional_int(value: object) -> str:
    if value is None:
        return "n/a"
    return str(int(value or 0))
