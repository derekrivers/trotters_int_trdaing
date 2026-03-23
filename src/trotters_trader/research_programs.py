from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from trotters_trader.catalog import load_catalog_entries, register_catalog_entry
from trotters_trader.reports import safe_artifact_dirname


def load_research_program_definition(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Research program definition '{path}' must contain a JSON object")
    return payload


def write_research_program_artifacts(
    *,
    output_dir: Path,
    definition: dict[str, object],
) -> dict[str, object]:
    program_id = str(definition.get("program_id", "research_program") or "research_program")
    report_dir = output_dir / safe_artifact_dirname(program_id)
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = build_research_program_summary(output_dir=output_dir, definition=definition)
    markdown_path = report_dir / "research_program.md"
    json_path = report_dir / "research_program.json"

    markdown_path.write_text(_render_research_program_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    final_step = summary.get("final_step") if isinstance(summary.get("final_step"), dict) else {}
    register_catalog_entry(
        output_dir=output_dir,
        entry={
            "artifact_type": "research_program",
            "artifact_name": program_id,
            "profile_name": str(final_step.get("profile_name", "unknown")),
            "strategy_family": str(definition.get("strategy_family", "cross_sectional_momentum")),
            "sweep_type": "research_program",
            "evaluation_status": _program_evaluation_status(summary),
            "primary_path": str(json_path),
            "summary_path": str(markdown_path),
            "recommended_action": str(
                (
                    summary.get("decision")
                    if isinstance(summary.get("decision"), dict)
                    else {}
                ).get("recommended_action", "continue_research")
            ),
        },
    )

    return {
        "summary": summary,
        "artifacts": {
            "research_program_json": str(json_path),
            "research_program_md": str(markdown_path),
        },
    }


def build_research_program_summary(*, output_dir: Path, definition: dict[str, object]) -> dict[str, object]:
    catalog_entries = load_catalog_entries(output_dir)
    latest_catalog = _latest_catalog_entries(catalog_entries)
    program_steps = [
        step
        for step in definition.get("campaign_path", [])
        if isinstance(step, dict)
    ]
    seed_stack = [
        seed
        for seed in definition.get("seed_stack", [])
        if isinstance(seed, dict)
    ]

    step_summaries = [
        _build_step_summary(
            output_dir=output_dir,
            latest_catalog=latest_catalog,
            step=step,
        )
        for step in program_steps
    ]
    decision = _program_decision(step_summaries)
    recorded_at = datetime.now(UTC).isoformat()

    return {
        "program_id": str(definition.get("program_id", "research_program")),
        "title": str(definition.get("title", "Research Program")),
        "status": str(decision.get("status", "active")),
        "recorded_at_utc": recorded_at,
        "objective": str(definition.get("objective", "")),
        "branch_rationale": str(definition.get("branch_rationale", "")),
        "seed_stack": seed_stack,
        "campaign_path": step_summaries,
        "final_step": step_summaries[-1] if step_summaries else {},
        "stop_conditions": [
            item
            for item in definition.get("stop_conditions", [])
            if isinstance(item, dict)
        ],
        "artifact_expectations": [
            item
            for item in definition.get("artifact_expectations", [])
            if isinstance(item, dict)
        ],
        "decision": decision,
        "positive_evidence": _positive_evidence(definition, step_summaries),
        "negative_evidence": _negative_evidence(step_summaries),
    }


def _build_step_summary(
    *,
    output_dir: Path,
    latest_catalog: dict[tuple[str, str], dict[str, object]],
    step: dict[str, object],
) -> dict[str, object]:
    profile_name = str(step.get("profile_name", "unknown"))
    history_path = output_dir / "profile_history" / f"{profile_name}.jsonl"
    history_entry = _last_history_entry(history_path)
    latest_promotion = latest_catalog.get((profile_name, "promotion"))
    latest_program = latest_catalog.get((profile_name, "operability_program"))
    latest_scorecard = latest_catalog.get((profile_name, "operator_scorecard"))
    latest_paper = latest_catalog.get((profile_name, "paper_trade_decision"))

    status = "not_run"
    eligible = False
    fail_reasons: list[str] = []
    recommended_action = ""
    split_summary: dict[str, object] = {}
    walkforward_summary: dict[str, object] = {}
    if history_entry is not None:
        eligible = bool(history_entry.get("eligible", False))
        status = "pass" if eligible else "fail"
        fail_reasons = [
            str(reason)
            for reason in history_entry.get("fail_reasons", [])
            if str(reason).strip()
        ]
        recommended_action = str(history_entry.get("recommended_action", "") or "")
        split_summary = history_entry.get("split_summary", {}) if isinstance(history_entry.get("split_summary"), dict) else {}
        walkforward_summary = (
            history_entry.get("walkforward_summary", {})
            if isinstance(history_entry.get("walkforward_summary"), dict)
            else {}
        )

    artifact_refs = [
        ref
        for ref in (
            _catalog_ref(latest_promotion),
            _catalog_ref(latest_program),
            _catalog_ref(latest_scorecard),
            _catalog_ref(latest_paper),
        )
        if ref is not None
    ]
    artifact_refs.extend(_fallback_artifact_refs(history_path, split_summary))

    return {
        "step_id": str(step.get("step_id", "")),
        "label": str(step.get("label", step.get("step_id", "step"))),
        "profile_name": profile_name,
        "config_path": str(step.get("config_path", "")),
        "purpose": str(step.get("purpose", "")),
        "status": status,
        "eligible": eligible,
        "recommended_action": recommended_action,
        "fail_reasons": fail_reasons,
        "history_entry": history_entry,
        "artifact_refs": artifact_refs,
        "latest_split_summary": split_summary,
        "latest_walkforward_summary": walkforward_summary,
    }


def _program_decision(step_summaries: list[dict[str, object]]) -> dict[str, object]:
    if not step_summaries:
        return {
            "status": "active",
            "recommended_action": "define_branch",
            "reason": "no_campaign_path",
            "summary": "No campaign path is defined for this research program.",
        }

    first_unrun = next((step for step in step_summaries if step.get("status") == "not_run"), None)
    passing_step = next((step for step in reversed(step_summaries) if bool(step.get("eligible", False))), None)
    final_step = step_summaries[-1]

    if passing_step is not None:
        return {
            "status": "promoted",
            "recommended_action": "freeze_candidate",
            "reason": "candidate_passed_promotion_policy",
            "summary": (
                f"The branch produced a promotion-eligible candidate at "
                f"{passing_step.get('label', passing_step.get('step_id', 'unknown'))}."
            ),
            "selected_step_id": str(passing_step.get("step_id", "")),
        }
    if first_unrun is not None:
        return {
            "status": "active",
            "recommended_action": "run_next_step",
            "reason": "awaiting_branch_execution",
            "summary": (
                f"The branch remains active. The next required step is "
                f"{first_unrun.get('label', first_unrun.get('step_id', 'unknown'))}."
            ),
            "selected_step_id": str(first_unrun.get("step_id", "")),
        }

    fail_reasons = [
        str(reason)
        for reason in final_step.get("fail_reasons", [])
        if str(reason).strip()
    ]
    summary_suffix = (
        f" Latest terminal fail reasons: {', '.join(fail_reasons)}."
        if fail_reasons
        else ""
    )
    return {
        "status": "retired",
        "recommended_action": "retire_branch",
        "reason": "terminal_branch_failure",
        "summary": (
            f"The branch has exhausted its defined path without producing a promotion-eligible candidate."
            f"{summary_suffix}"
        ),
        "selected_step_id": str(final_step.get("step_id", "")),
    }


def _positive_evidence(definition: dict[str, object], step_summaries: list[dict[str, object]]) -> list[str]:
    evidence = [
        str(item)
        for item in definition.get("positive_hypotheses", [])
        if str(item).strip()
    ]
    for step in step_summaries:
        walkforward = step.get("latest_walkforward_summary", {})
        if not isinstance(walkforward, dict):
            continue
        pass_windows = int(walkforward.get("pass_windows", 0) or 0)
        if pass_windows > 0:
            evidence.append(
                f"{step.get('label', step.get('step_id', 'unknown'))} preserved at least {pass_windows} walk-forward pass windows."
            )
    if not evidence:
        evidence.append("This branch was selected because earlier batch work identified it as the strongest available holdout-improvement path.")
    return evidence


def _negative_evidence(step_summaries: list[dict[str, object]]) -> list[str]:
    evidence: list[str] = []
    for step in step_summaries:
        label = str(step.get("label", step.get("step_id", "unknown")))
        if step.get("status") == "not_run":
            evidence.append(f"{label} has not produced a recorded promotion decision yet.")
            continue
        if bool(step.get("eligible", False)):
            continue
        fail_reasons = [
            str(reason)
            for reason in step.get("fail_reasons", [])
            if str(reason).strip()
        ]
        if fail_reasons:
            evidence.append(f"{label} failed the promotion policy: {', '.join(fail_reasons)}.")
            continue
        evidence.append(f"{label} has recorded evidence but is still not promotion-eligible.")
    return evidence


def _latest_catalog_entries(entries: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    latest: dict[tuple[str, str], dict[str, object]] = {}
    for entry in entries:
        profile_name = str(entry.get("profile_name", "") or "")
        artifact_type = str(entry.get("artifact_type", "") or "")
        if not profile_name or not artifact_type:
            continue
        latest[(profile_name, artifact_type)] = entry
    return latest


def _catalog_ref(entry: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(entry, dict):
        return None
    return {
        "artifact_type": str(entry.get("artifact_type", "unknown")),
        "artifact_name": str(entry.get("artifact_name", "unknown")),
        "primary_path": str(entry.get("primary_path", "")),
        "summary_path": str(entry.get("summary_path", "")),
        "evaluation_status": str(entry.get("evaluation_status", "unknown")),
        "recorded_at_utc": str(entry.get("recorded_at_utc", "")),
    }


def _last_history_entry(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _program_evaluation_status(summary: dict[str, object]) -> str:
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    status = str(decision.get("status", "active"))
    if status == "promoted":
        return "pass"
    if status == "retired":
        return "fail"
    return "warn"


def _fallback_artifact_refs(
    history_path: Path,
    split_summary: dict[str, object],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    if history_path.exists():
        refs.append(
            {
                "artifact_type": "promotion_artifacts",
                "artifact_name": history_path.name,
                "primary_path": str(history_path),
                "summary_path": "",
                "evaluation_status": "unknown",
                "recorded_at_utc": "",
            }
        )
    for label in ("train", "validation", "holdout"):
        split = split_summary.get(label, {}) if isinstance(split_summary, dict) else {}
        if not isinstance(split, dict):
            continue
        results_path = str(split.get("results_path", "") or "")
        if not results_path:
            continue
        refs.append(
            {
                "artifact_type": f"{label}_results",
                "artifact_name": Path(results_path).name,
                "primary_path": results_path,
                "summary_path": "",
                "evaluation_status": str(split.get("status", "unknown")),
                "recorded_at_utc": "",
            }
        )
    return refs


def _render_research_program_markdown(summary: dict[str, object]) -> str:
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    lines = [
        f"# {summary.get('title', 'Research Program')}",
        "",
        "## Overview",
        "",
        f"- Program ID: {summary.get('program_id', 'unknown')}",
        f"- Status: {summary.get('status', 'active')}",
        f"- Recorded at: {summary.get('recorded_at_utc', '')}",
        f"- Objective: {summary.get('objective', '')}",
        f"- Branch rationale: {summary.get('branch_rationale', '')}",
        "",
        "## Decision",
        "",
        f"- Recommended action: {decision.get('recommended_action', 'continue_research')}",
        f"- Reason: {decision.get('reason', 'unknown')}",
        f"- Summary: {decision.get('summary', '')}",
        "",
        "## Seed Stack",
        "",
    ]
    seed_stack = summary.get("seed_stack", [])
    if isinstance(seed_stack, list) and seed_stack:
        for seed in seed_stack:
            if not isinstance(seed, dict):
                continue
            lines.extend(
                [
                    f"- {seed.get('label', 'seed')}: {seed.get('profile_name', 'unknown')} ({seed.get('config_path', '')})",
                    f"  Rationale: {seed.get('rationale', '')}",
                ]
            )
    else:
        lines.append("- No seed stack defined.")

    lines.extend(["", "## Campaign Path", ""])
    for step in summary.get("campaign_path", []):
        if not isinstance(step, dict):
            continue
        split_summary = step.get("latest_split_summary", {})
        validation = split_summary.get("validation", {}) if isinstance(split_summary, dict) else {}
        holdout = split_summary.get("holdout", {}) if isinstance(split_summary, dict) else {}
        walkforward = step.get("latest_walkforward_summary", {})
        lines.extend(
            [
                f"### {step.get('label', step.get('step_id', 'step'))}",
                "",
                f"- Profile: {step.get('profile_name', 'unknown')}",
                f"- Config: {step.get('config_path', '')}",
                f"- Purpose: {step.get('purpose', '')}",
                f"- Status: {step.get('status', 'unknown')}",
                f"- Promotion eligible: {bool(step.get('eligible', False))}",
                f"- Recommended action: {step.get('recommended_action', '')}",
                f"- Validation excess return: {_percent(validation.get('excess_return'))}",
                f"- Holdout excess return: {_percent(holdout.get('excess_return'))}",
                f"- Walk-forward pass windows: {int(walkforward.get('pass_windows', 0) or 0)}",
            ]
        )
        fail_reasons = step.get("fail_reasons", [])
        if isinstance(fail_reasons, list) and fail_reasons:
            lines.append(f"- Fail reasons: {', '.join(str(reason) for reason in fail_reasons)}")
        artifact_refs = step.get("artifact_refs", [])
        if isinstance(artifact_refs, list) and artifact_refs:
            lines.append("- Artifact refs:")
            for ref in artifact_refs:
                if not isinstance(ref, dict):
                    continue
                lines.append(
                    f"  - {ref.get('artifact_type', 'artifact')}: {ref.get('primary_path', '')}"
                )
        lines.append("")

    lines.extend(["## Positive Evidence", ""])
    for item in summary.get("positive_evidence", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Negative Evidence", ""])
    for item in summary.get("negative_evidence", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Stop Conditions", ""])
    stop_conditions = summary.get("stop_conditions", [])
    if isinstance(stop_conditions, list) and stop_conditions:
        for condition in stop_conditions:
            if not isinstance(condition, dict):
                continue
            lines.append(
                f"- {condition.get('decision', 'decision')}: {condition.get('when', '')}"
            )
    else:
        lines.append("- No stop conditions defined.")

    return "\n".join(lines) + "\n"


def _percent(value: object) -> str:
    try:
        if value is None:
            return "n/a"
        return f"{float(value):.4%}"
    except (TypeError, ValueError):
        return "n/a"
