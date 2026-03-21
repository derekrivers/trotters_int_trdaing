from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path, PurePosixPath
import time

from trotters_trader.alpha_vantage import download_daily_series
from trotters_trader.backtest import build_daily_decision_package, run_backtest
from trotters_trader.catalog import load_catalog_entries
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import (
    RuntimeOverrides,
    apply_runtime_overrides,
    available_evaluation_profiles,
    load_config,
    scope_app_config,
)
from trotters_trader.coverage import summarize_data_coverage, write_coverage_artifacts
from trotters_trader.dashboard import serve_dashboard
from trotters_trader.eodhd import download_daily_series as download_eodhd_daily_series
from trotters_trader.experiments import (
    BATCH_PRESETS,
    apply_research_variant,
    build_research_batch_jobs,
    run_benchmark_comparison,
    run_construction_sweep,
    run_evaluation_profile_comparison,
    run_momentum_profile_comparison,
    run_momentum_refinement_sweep,
    run_momentum_sweep,
    run_promotion_check,
    run_ranking_sweep,
    run_regime_sweep,
    run_risk_sweep,
    run_sector_sweep,
    run_sensitivity_matrix,
    run_sma_grid,
    run_starter_tranche,
    run_operability_program,
    run_strategy_comparison,
    run_threshold_sweep,
    run_universe_slice_sweep,
    run_validation_split,
    run_walkforward_validation,
    summarize_walkforward_promotion,
    write_experiment_comparison,
)
from trotters_trader.features import materialize_feature_set
from trotters_trader.reports import write_paper_trade_decision_artifacts, write_promotion_artifacts
from trotters_trader.research_runtime import (
    campaign_manager_loop,
    campaign_status,
    collect_artifacts,
    coordinator_cycle,
    director_manager_loop,
    director_status,
    export_runtime_catalog,
    get_job,
    pause_director,
    resume_director,
    skip_director_next,
    start_director,
    start_campaign,
    runtime_paths,
    runtime_status,
    stop_director,
    stop_campaign,
    step_campaign,
    step_director,
    submit_jobs,
    summarize_job_result,
    worker_loop,
)
from trotters_trader.staging import stage_source_data

LEGACY_COMMANDS = [
    "download-alpha-vantage",
    "download-eodhd",
    "coverage",
    "stage",
    "ingest",
    "materialize-features",
    "research-catalog",
    "backtest",
    "experiment",
    "compare-strategies",
    "compare-profiles",
    "compare-benchmarks",
    "report",
    "sensitivity",
    "thresholds",
    "momentum-sweep",
    "momentum-refine",
    "compare-momentum-profiles",
    "validate-split",
    "risk-sweep",
    "regime-sweep",
    "sector-sweep",
    "walk-forward",
    "promotion-check",
    "universe-slice-sweep",
    "ranking-sweep",
    "construction-sweep",
    "starter-tranche",
    "operability-program",
    "paper-trade-decision",
]
RUNTIME_COMMANDS = [
    "research-coordinator",
    "research-worker",
    "research-submit",
    "research-batch",
    "research-status",
    "research-run-job",
    "research-campaign-start",
    "research-campaign-step",
    "research-campaign-stop",
    "research-campaign-status",
    "research-campaign-manager",
    "research-director-start",
    "research-director-step",
    "research-director-pause",
    "research-director-resume",
    "research-director-skip-next",
    "research-director-stop",
    "research-director-status",
    "research-director-manager",
    "research-dashboard",
]
ALL_COMMANDS = LEGACY_COMMANDS + RUNTIME_COMMANDS


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command in RUNTIME_COMMANDS:
        payload = _handle_runtime_command(args)
        print(json.dumps(payload, indent=2, default=str))
        return

    if not args.config:
        parser.error("--config is required for this command")

    config = load_config(args.config, evaluation_profile=args.evaluation_profile)
    payload = execute_command(
        command=args.command,
        config=config,
        config_path=args.config,
        quality_gate=args.quality_gate,
        scope_data_paths=True,
        prepare_data=True,
        command_args=args,
    )
    print(json.dumps(payload, indent=2, default=str))


def execute_command(
    command: str,
    config,
    config_path: str,
    quality_gate: str = "all",
    scope_data_paths: bool = True,
    prepare_data: bool = True,
    command_args: argparse.Namespace | None = None,
) -> dict[str, object]:
    if command == "download-alpha-vantage":
        return download_daily_series(
            config.data,
            adjusted=not bool(getattr(command_args, "raw_series", False)),
            outputsize=str(getattr(command_args, "outputsize", "full")),
            limit=getattr(command_args, "limit", None),
            requested_instruments=getattr(command_args, "instrument", None),
            force=bool(getattr(command_args, "force", False)),
        )
    if command == "download-eodhd":
        return download_eodhd_daily_series(
            config.data,
            date_from=getattr(command_args, "from_date", None),
            date_to=getattr(command_args, "to_date", None),
            limit=getattr(command_args, "limit", None),
            requested_instruments=getattr(command_args, "instrument", None),
            force=bool(getattr(command_args, "force", False)),
        )

    if scope_data_paths:
        config = scope_app_config(config, f"{config.run.name}_{command}")

    if command == "stage":
        return stage_source_data(config.data)
    if command == "coverage":
        results = summarize_data_coverage(config.data)
        results["artifacts"] = write_coverage_artifacts(results, report_name=config.run.name)
        return results
    if command == "ingest":
        return materialize_canonical_data(config.data)
    if command == "research-catalog":
        entries = load_catalog_entries(config.run.output_dir)
        latest_profiles_path = config.run.output_dir / "research_catalog" / "latest_profile_artifacts.json"
        return {
            "entry_count": len(entries),
            "catalog_jsonl": str(config.run.output_dir / "research_catalog" / "catalog.jsonl"),
            "catalog_json": str(config.run.output_dir / "research_catalog" / "experiment_catalog.json"),
            "catalog_csv": str(config.run.output_dir / "research_catalog" / "experiment_catalog.csv"),
            "latest_profiles_json": str(latest_profiles_path),
            "entries": entries[-20:],
        }

    if prepare_data:
        materialize_canonical_data(config.data)

    if command == "materialize-features":
        return materialize_feature_set(config)
    if command == "backtest":
        return _format_result(run_backtest(config))
    if command == "report":
        result = run_backtest(config)
        payload = _format_result(result)
        payload["report_files"] = _report_files(result.results_path)
        return payload
    if command == "experiment":
        return _comparison_payload(run_sma_grid(config), config.run.output_dir, f"{config.run.name}_experiment_report", quality_gate, config.evaluation.profile_name)
    if command == "sensitivity":
        return _comparison_payload(run_sensitivity_matrix(config), config.run.output_dir, f"{config.run.name}_sensitivity_report", quality_gate, config.evaluation.profile_name)
    if command == "thresholds":
        return _comparison_payload(run_threshold_sweep(config), config.run.output_dir, f"{config.run.name}_threshold_report", quality_gate, config.evaluation.profile_name)
    if command == "momentum-sweep":
        return _comparison_payload(run_momentum_sweep(config), config.run.output_dir, f"{config.run.name}_momentum_report", quality_gate, config.evaluation.profile_name)
    if command == "momentum-refine":
        return _comparison_payload(run_momentum_refinement_sweep(config), config.run.output_dir, f"{config.run.name}_momentum_refine_report", quality_gate, config.evaluation.profile_name)
    if command == "compare-momentum-profiles":
        return _comparison_payload(run_momentum_profile_comparison(config), config.run.output_dir, f"{config.run.name}_momentum_profiles_report", quality_gate, config.evaluation.profile_name)
    if command == "validate-split":
        results = run_validation_split(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_validation_report", quality_gate, None)
        payload["periods"] = [result.analytics.get("period", {}) for result in results]
        return payload
    if command == "risk-sweep":
        results = run_risk_sweep(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_risk_report", quality_gate, None)
        payload["periods"] = [result.analytics.get("period", {}) for result in results]
        return payload
    if command == "regime-sweep":
        results = run_regime_sweep(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_regime_report", quality_gate, None)
        payload["periods"] = [result.analytics.get("period", {}) for result in results]
        return payload
    if command == "sector-sweep":
        results = run_sector_sweep(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_sector_report", quality_gate, None)
        payload["periods"] = [result.analytics.get("period", {}) for result in results]
        return payload
    if command == "walk-forward":
        results = run_walkforward_validation(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_walkforward_report", quality_gate, None)
        payload["promotion_decision"] = summarize_walkforward_promotion(results, config.promotion)
        return payload
    if command == "promotion-check":
        promotion = run_promotion_check(config)
        return {
            "validation_runs": [_format_result(result) for result in promotion["validation_results"]],
            "walkforward_runs": [_format_result(result) for result in promotion["walkforward_results"]],
            "validation_report": write_experiment_comparison(
                results=promotion["validation_results"],
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_promotion_validation_report",
                quality_gate=quality_gate,
            ),
            "walkforward_report": write_experiment_comparison(
                results=promotion["walkforward_results"],
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_promotion_walkforward_report",
                quality_gate=quality_gate,
            ),
            "promotion_decision": promotion["promotion_decision"],
            "promotion_artifacts": write_promotion_artifacts(
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_promotion_report",
                promotion_decision=promotion["promotion_decision"],
                config_path=config_path,
            ),
            "quality_gate": quality_gate,
        }
    if command == "universe-slice-sweep":
        return run_universe_slice_sweep(config)
    if command == "ranking-sweep":
        return run_ranking_sweep(config)
    if command == "construction-sweep":
        return run_construction_sweep(config)
    if command == "starter-tranche":
        return run_starter_tranche(config)
    if command == "operability-program":
        return run_operability_program(config)
    if command == "paper-trade-decision":
        decision_package = build_daily_decision_package(
            config,
            reference_date=getattr(command_args, "reference_date", None),
        )
        return {
            "decision_package": decision_package,
            "artifacts": write_paper_trade_decision_artifacts(
                output_dir=config.run.output_dir,
                report_name=f"{config.run.name}_paper_trade_decision",
                decision_package=decision_package,
            ),
        }
    if command == "compare-profiles":
        profile_configs = [
            apply_runtime_overrides(
                load_config(config_path, evaluation_profile=name),
                RuntimeOverrides(
                    output_dir=config.run.output_dir,
                    staging_dir=config.data.staging_dir,
                    canonical_dir=config.data.canonical_dir,
                    raw_dir=config.data.raw_dir,
                    feature_dir=config.features.feature_dir,
                    feature_set_name=config.features.set_name,
                    control_profile=config.research.control_profile,
                    disable_feature_materialization=not config.features.materialize_on_backtest,
                    force_precomputed_features=config.features.use_precomputed,
                ),
            )
            for name in available_evaluation_profiles(config_path)
        ]
        results = run_evaluation_profile_comparison(profile_configs)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_profile_report", quality_gate, None)
        payload["profiles"] = available_evaluation_profiles(config_path)
        return payload
    if command == "compare-benchmarks":
        results = run_benchmark_comparison(config)
        payload = _comparison_payload(results, config.run.output_dir, f"{config.run.name}_benchmark_report", quality_gate, None)
        payload["benchmarks"] = list(config.benchmark.models)
        return payload
    results = run_strategy_comparison(config)
    return _comparison_payload(results, config.run.output_dir, f"{config.run.name}_strategy_report", quality_gate, config.evaluation.profile_name)


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _handle_runtime_command(args: argparse.Namespace) -> dict[str, object]:
    paths = runtime_paths(args.runtime_root, catalog_output_dir=args.catalog_output_dir)
    if args.command == "research-submit":
        if not args.spec:
            raise ValueError("research-submit requires --spec")
        return submit_jobs(paths, _load_spec_payload(args.spec))
    if args.command == "research-batch":
        if not args.config:
            raise ValueError("research-batch requires --config")
        config = load_config(args.config, evaluation_profile=args.evaluation_profile)
        batch_dataset_ref = _prepare_batch_inputs(config, paths, args.batch_preset)
        jobs = build_research_batch_jobs(
            config,
            args.config,
            args.batch_preset,
            include_control=not args.exclude_control,
            priority_start=args.priority_start,
        )
        jobs = [
            {
                **job,
                "input_dataset_ref": batch_dataset_ref,
                "input_dataset_ref_mode": "runtime_relative",
            }
            for job in jobs
        ]
        submission = submit_jobs(paths, {"jobs": jobs})
        return {
            **submission,
            "batch_preset": args.batch_preset,
            "include_control": not args.exclude_control,
            "job_count": len(jobs),
            "input_dataset_ref": batch_dataset_ref,
        }
    if args.command == "research-status":
        status = runtime_status(paths)
        status["catalog_exports"] = export_runtime_catalog(paths)
        return status
    if args.command == "research-campaign-start":
        if not args.config:
            raise ValueError("research-campaign-start requires --config")
        notify_events = tuple(
            event.strip()
            for event in str(getattr(args, "notify_events", "")).split(",")
            if event.strip()
        )
        return start_campaign(
            paths,
            args.config,
            campaign_name=getattr(args, "campaign_name", None),
            evaluation_profile=args.evaluation_profile,
            quality_gate=args.quality_gate,
            max_hours=float(getattr(args, "campaign_max_hours", 24.0)),
            max_jobs=int(getattr(args, "campaign_max_jobs", 0)),
            stage_candidate_limit=int(getattr(args, "stage_candidate_limit", 0)),
            shortlist_size=int(getattr(args, "shortlist_size", 3)),
            notification_command=getattr(args, "notification_command", None),
            notify_events=notify_events,
        )
    if args.command == "research-campaign-step":
        if not args.campaign_id:
            raise ValueError("research-campaign-step requires --campaign-id")
        return step_campaign(paths, args.campaign_id)
    if args.command == "research-campaign-stop":
        if not args.campaign_id:
            raise ValueError("research-campaign-stop requires --campaign-id")
        return stop_campaign(
            paths,
            args.campaign_id,
            cancel_queued=not bool(getattr(args, "keep_queued_jobs", False)),
            reason=str(getattr(args, "stop_reason", "operator_stop")),
        )
    if args.command == "research-campaign-status":
        return campaign_status(paths, getattr(args, "campaign_id", None))
    if args.command == "research-campaign-manager":
        return campaign_manager_loop(paths, poll_seconds=args.poll_seconds, once=args.once)
    if args.command == "research-director-start":
        plan_payload = None
        if getattr(args, "director_plan_file", None):
            plan_payload = _load_spec_payload(args.director_plan_file)
        notify_events = tuple(
            event.strip()
            for event in str(getattr(args, "notify_events", "")).split(",")
            if event.strip()
        )
        return start_director(
            paths,
            config_path=getattr(args, "config", None),
            director_name=getattr(args, "director_name", None),
            evaluation_profile=args.evaluation_profile,
            quality_gate=args.quality_gate,
            max_hours=float(getattr(args, "campaign_max_hours", 24.0)),
            max_jobs=int(getattr(args, "campaign_max_jobs", 0)),
            stage_candidate_limit=int(getattr(args, "stage_candidate_limit", 0)),
            shortlist_size=int(getattr(args, "shortlist_size", 3)),
            notification_command=getattr(args, "notification_command", None),
            notify_events=notify_events,
            plan_payload=plan_payload,
            plan_file_path=getattr(args, "director_plan_file", None),
            adopt_active_campaigns=not bool(getattr(args, "disable_director_adoption", False)),
        )
    if args.command == "research-director-step":
        if not args.director_id:
            raise ValueError("research-director-step requires --director-id")
        return step_director(paths, args.director_id)
    if args.command == "research-director-pause":
        if not args.director_id:
            raise ValueError("research-director-pause requires --director-id")
        return pause_director(paths, args.director_id, reason=str(getattr(args, "stop_reason", "operator_pause")))
    if args.command == "research-director-resume":
        if not args.director_id:
            raise ValueError("research-director-resume requires --director-id")
        return resume_director(paths, args.director_id, reason=str(getattr(args, "stop_reason", "operator_resume")))
    if args.command == "research-director-skip-next":
        if not args.director_id:
            raise ValueError("research-director-skip-next requires --director-id")
        return skip_director_next(paths, args.director_id, reason=str(getattr(args, "stop_reason", "operator_skip")))
    if args.command == "research-director-stop":
        if not args.director_id:
            raise ValueError("research-director-stop requires --director-id")
        return stop_director(
            paths,
            args.director_id,
            stop_active_campaign=bool(getattr(args, "stop_active_campaign", False)),
            reason=str(getattr(args, "stop_reason", "operator_stop")),
        )
    if args.command == "research-director-status":
        return director_status(paths, getattr(args, "director_id", None))
    if args.command == "research-director-manager":
        return director_manager_loop(paths, poll_seconds=args.poll_seconds, once=args.once)
    if args.command == "research-dashboard":
        return serve_dashboard(
            paths,
            host=args.dashboard_host,
            port=args.dashboard_port,
            refresh_seconds=args.dashboard_refresh_seconds,
        )
    if args.command == "research-coordinator":
        if args.once:
            return coordinator_cycle(paths, lease_timeout_seconds=args.lease_timeout_seconds)
        while True:
            coordinator_cycle(paths, lease_timeout_seconds=args.lease_timeout_seconds)
            time.sleep(max(args.poll_seconds, 0.1))
    if args.command == "research-worker":
        return worker_loop(
            paths,
            worker_id=args.worker_id,
            poll_seconds=args.poll_seconds,
            lease_timeout_seconds=args.lease_timeout_seconds,
            once=args.once,
        )
    if args.command == "research-run-job":
        if not args.job_id:
            raise ValueError("research-run-job requires --job-id")
        job = get_job(paths, args.job_id)
        config = load_config(job.config_path, evaluation_profile=job.evaluation_profile)
        variant = job.spec.get("research_variant")
        if isinstance(variant, dict):
            config = apply_research_variant(config, variant)
        output_root = _resolve_runtime_job_path(
            job.output_root,
            paths.runtime_root,
            str(job.spec.get("output_root_mode", "raw")),
        )
        input_dataset_ref = _resolve_runtime_ref(
            job.input_dataset_ref,
            paths.runtime_root,
            str(job.spec.get("input_dataset_ref_mode", "raw")),
        )
        feature_set_ref = _resolve_runtime_ref(
            job.feature_set_ref,
            paths.runtime_root,
            str(job.spec.get("feature_set_ref_mode", "raw")),
        )
        config = apply_runtime_overrides(
            config,
            RuntimeOverrides(
                output_dir=output_root,
                staging_dir=output_root / "_runtime" / "staging",
                canonical_dir=input_dataset_ref,
                raw_dir=output_root / "_runtime" / "raw",
                feature_set_ref=feature_set_ref,
                control_profile=job.control_profile,
                disable_feature_materialization=True,
                force_precomputed_features=bool(job.feature_set_ref),
            ),
        )
        if config.features.enabled and not config.features.use_precomputed:
            raise ValueError("worker-safe execution requires precomputed features or an explicit feature_set_ref")
        payload = execute_command(
            command=job.command,
            config=config,
            config_path=job.config_path,
            quality_gate=job.quality_gate,
            scope_data_paths=False,
            prepare_data=False,
            command_args=None,
        )
        return {
            "job_id": job.job_id,
            "command": job.command,
            "config_path": job.config_path,
            "output_root": str(output_root),
            "profile": {
                "profile_name": config.research.profile_name,
                "profile_version": config.research.profile_version,
                "strategy_family": config.strategy.name,
                "research_tranche": config.research.research_tranche,
                "control_profile": config.research.control_profile,
            },
            "result_summary": summarize_job_result(job.command, payload),
            "promotion_decision": payload.get("promotion_decision") if isinstance(payload, dict) else None,
            "artifacts": collect_artifacts(payload),
        }
    raise ValueError(f"Unsupported runtime command '{args.command}'")


def _comparison_payload(results, output_dir: Path, report_name: str, quality_gate: str, evaluation_profile: str | None) -> dict[str, object]:
    return {
        "runs": [_format_result(result) for result in results],
        "comparison_report": write_experiment_comparison(
            results=results,
            output_dir=output_dir,
            report_name=report_name,
            quality_gate=quality_gate,
        ),
        "quality_gate": quality_gate,
        "evaluation_profile": evaluation_profile,
    }


def _format_result(result: object) -> dict[str, object]:
    benchmark = getattr(result, "analytics", {}).get("benchmark", {})
    evaluation = getattr(result, "analytics", {}).get("evaluation", {})
    run_metadata = getattr(result, "analytics", {}).get("run_metadata", {})
    period = getattr(result, "analytics", {}).get("period", {})
    benchmark_return = benchmark.get("total_return")
    strategy_return = getattr(result, "summary", {}).get("total_return")
    excess_return = None if benchmark_return is None or strategy_return is None else strategy_return - benchmark_return
    return {
        "summary": getattr(result, "summary"),
        "benchmark": {
            "total_return": benchmark_return,
            "ending_nav": benchmark.get("ending_nav"),
            "max_drawdown": benchmark.get("max_drawdown"),
            "excess_return": excess_return,
        },
        "evaluation": evaluation,
        "run_metadata": run_metadata,
        "period": period,
        "results_path": getattr(result, "results_path"),
    }


def _report_files(results_path: str) -> dict[str, str]:
    run_dir = Path(results_path).parent
    return {
        "summary_md": str(run_dir / "summary.md"),
        "performance_csv": str(run_dir / "performance.csv"),
        "fills_csv": str(run_dir / "fills.csv"),
        "closed_trades_csv": str(run_dir / "closed_trades.csv"),
        "benchmark_csv": str(run_dir / "benchmark_performance.csv"),
    }


def _load_spec_payload(spec: str) -> object:
    spec_path = Path(spec)
    if spec_path.exists():
        return json.loads(spec_path.read_text(encoding="utf-8"))
    return json.loads(spec)


def _prepare_batch_inputs(config, paths, batch_preset: str) -> str:
    dataset_scope = _safe_runtime_name(f"{config.run.name}_{batch_preset}")
    dataset_root = paths.runtime_root / "datasets" / dataset_scope
    batch_config = apply_runtime_overrides(
        config,
        RuntimeOverrides(
            staging_dir=dataset_root / "staging",
            canonical_dir=dataset_root / "canonical",
            raw_dir=dataset_root / "raw",
        ),
    )
    materialize_canonical_data(batch_config.data)
    return str(PurePosixPath("datasets") / dataset_scope / "canonical")


def _resolve_runtime_job_path(value: str, runtime_root: Path, mode: str) -> Path:
    if mode == "runtime_relative":
        return runtime_root / Path(value)
    path = Path(value)
    if path.is_absolute():
        return path
    return path


def _resolve_runtime_ref(value: str | None, runtime_root: Path, mode: str) -> Path | None:
    if not value:
        return None
    if mode == "runtime_relative":
        return runtime_root / Path(value)
    path = Path(value)
    if path.is_absolute():
        return path
    return path


def _safe_runtime_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return safe or "batch"


def _default_worker_id() -> str:
    hostname = os.environ.get("HOSTNAME", "").strip()
    if hostname:
        return f"worker-{hostname}"
    return "worker-01"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run historical research commands and orchestration jobs.")
    parser.add_argument("command", nargs="?", default="backtest", choices=ALL_COMMANDS, help="Operation to run.")
    parser.add_argument("--config", help="Path to a TOML configuration file.")
    parser.add_argument("--quality-gate", choices=["all", "pass_warn", "pass"], default="all")
    parser.add_argument("--evaluation-profile", help="Named evaluation profile from the config file.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--outputsize", choices=["compact", "full"], default="full")
    parser.add_argument("--raw-series", action="store_true")
    parser.add_argument("--instrument", action="append")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--reference-date", type=_parse_iso_date)
    parser.add_argument("--runtime-root", default="runtime/research_runtime")
    parser.add_argument("--catalog-output-dir", default="runs")
    parser.add_argument("--spec", help="JSON string or path to a JSON job spec.")
    parser.add_argument("--batch-preset", choices=BATCH_PRESETS, default="ranking")
    parser.add_argument("--exclude-control", action="store_true")
    parser.add_argument("--priority-start", type=int, default=100)
    parser.add_argument("--worker-id", default=_default_worker_id())
    parser.add_argument("--job-id")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lease-timeout-seconds", type=int, default=900)
    parser.add_argument("--campaign-name")
    parser.add_argument("--campaign-id")
    parser.add_argument("--director-name")
    parser.add_argument("--director-id")
    parser.add_argument("--director-plan-file")
    parser.add_argument("--disable-director-adoption", action="store_true")
    parser.add_argument("--stop-active-campaign", action="store_true")
    parser.add_argument("--campaign-max-hours", type=float, default=24.0)
    parser.add_argument("--campaign-max-jobs", type=int, default=0)
    parser.add_argument("--stage-candidate-limit", type=int, default=0)
    parser.add_argument("--shortlist-size", type=int, default=3)
    parser.add_argument("--notification-command")
    parser.add_argument(
        "--notify-events",
        default="campaign_finished,campaign_stopped,campaign_failed",
        help="Comma-separated campaign events that should trigger the notification command.",
    )
    parser.add_argument("--stop-reason", default="operator_stop")
    parser.add_argument("--keep-queued-jobs", action="store_true")
    parser.add_argument("--dashboard-host", default="0.0.0.0")
    parser.add_argument("--dashboard-port", type=int, default=8888)
    parser.add_argument("--dashboard-refresh-seconds", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    return parser


if __name__ == "__main__":
    main()
