from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import time
import uuid
from typing import Callable

from trotters_trader.reports import build_campaign_operator_summary, safe_artifact_dirname
from trotters_trader.research_programs import build_research_program_summary, load_research_program_definition

PROMOTION_PATH_SCHEMA_VERSION = 1
PROMOTION_PATH_STALE_HOURS = 48
PROMOTION_PATH_REPLACE_RETRIES = 5
PROMOTION_PATH_REPLACE_SLEEP_SECONDS = 0.1


def resolve_current_best_candidate(
    *,
    catalog_output_dir: Path,
    active_campaigns: list[dict[str, object]],
    most_recent_terminal: dict[str, object] | None,
    agent_summaries: dict[str, dict[str, object]],
    fetch_campaign_detail: Callable[[str], dict[str, object]],
) -> dict[str, object] | None:
    focus_campaign = _latest_campaign(active_campaigns)
    source = "active_campaign"
    if focus_campaign is None:
        terminal_campaign = (
            most_recent_terminal.get("campaign")
            if isinstance(most_recent_terminal, dict) and isinstance(most_recent_terminal.get("campaign"), dict)
            else None
        )
        campaign_id = str(terminal_campaign.get("campaign_id", "")) if terminal_campaign else ""
        if campaign_id:
            try:
                focus_campaign = fetch_campaign_detail(campaign_id)
            except ValueError:
                focus_campaign = terminal_campaign
            source = "most_recent_terminal_campaign"
    if not isinstance(focus_campaign, dict) or not focus_campaign:
        return {
            "status": "unavailable",
            "candidate_available": False,
            "source": "none",
            "operator_recommendation": "needs_more_research",
            "recommendation_state": "research_only",
            "headline": "No active or recent campaign is available for operator review.",
            "display_message": "No active or recent campaign is available for operator review.",
            "what_failed_or_is_missing": ["No active or recent campaign is available for operator review."],
            "next_action": "wait_for_next_branch",
            "next_steps": ["Wait for the next active or terminal campaign before choosing a leading candidate."],
            "best_candidate": None,
            "supporting_summaries": {},
            "campaign_id": "",
            "campaign_name": "",
            "campaign_status": "missing",
            "campaign_phase": "unknown",
            "progression": {"selected_candidate_eligible": False},
            "artifact_paths": {},
        }
    summary = build_campaign_operator_summary(
        focus_campaign,
        candidate_readiness=agent_summaries.get("candidate_readiness_summary"),
        paper_trade_readiness=agent_summaries.get("paper_trade_readiness_summary"),
    )
    return _normalize_current_best_candidate(summary, source=source)


def materialize_promotion_path(
    *,
    catalog_output_dir: Path,
    current_best_candidate: dict[str, object] | None = None,
    agent_summaries: dict[str, dict[str, object]] | None = None,
    explicit_target: dict[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    summaries = agent_summaries if isinstance(agent_summaries, dict) else {}
    portfolio = build_research_program_portfolio(catalog_output_dir)
    progression = build_candidate_progression_summary(
        catalog_output_dir,
        current_best_candidate=current_best_candidate,
        agent_summaries=summaries,
        research_program_portfolio=portfolio,
    )
    gate = build_paper_trade_entry_gate(
        catalog_output_dir,
        candidate_progression_summary=progression,
        explicit_target=explicit_target,
    )
    _write_promotion_summary(catalog_output_dir, "research_program_portfolio", portfolio)
    _write_promotion_summary(catalog_output_dir, "candidate_progression_summary", progression)
    _write_promotion_summary(catalog_output_dir, "paper_trade_entry_gate", gate)
    return {
        "candidate_progression_summary": progression,
        "paper_trade_entry_gate": gate,
        "research_program_portfolio": portfolio,
    }


def build_research_program_portfolio(catalog_output_dir: Path) -> dict[str, object]:
    definitions_dir = Path.cwd() / "configs" / "research_programs"
    runbook = _load_runbook()
    queue_entries = [entry for entry in runbook.get("work_queue", []) if isinstance(entry, dict)]
    programs: list[dict[str, object]] = []
    for definition_path in sorted(definitions_dir.glob("*.json")):
        definition = load_research_program_definition(definition_path)
        summary = build_research_program_summary(output_dir=catalog_output_dir, definition=definition)
        program_id = str(summary.get("program_id", "research_program"))
        queue_plan_id = _queue_plan_id(program_id)
        queue_entry = next(
            (entry for entry in queue_entries if str(entry.get("plan_id", "")) == queue_plan_id),
            None,
        )
        focus_step = _selected_program_step(summary)
        decision = summary.get("decision", {}) if isinstance(summary.get("decision"), dict) else {}
        programs.append(
            {
                "program_id": program_id,
                "title": str(summary.get("title", definition_path.stem)),
                "status": str(summary.get("status", "active")),
                "recommended_action": str(decision.get("recommended_action", "continue_research")),
                "decision_reason": str(decision.get("reason", "unknown")),
                "decision_summary": str(decision.get("summary", "")),
                "queue_plan_id": queue_plan_id,
                "queue_enabled": bool(queue_entry.get("enabled", False)) if isinstance(queue_entry, dict) else False,
                "queue_priority": int(queue_entry.get("priority", 0) or 0) if isinstance(queue_entry, dict) else None,
                "queue_director_name": str(queue_entry.get("director_name", "")) if isinstance(queue_entry, dict) else "",
                "focus_profile_name": str(focus_step.get("profile_name", "")),
                "focus_step_id": str(focus_step.get("step_id", "")),
                "focus_step_label": str(focus_step.get("label", "")),
                "focus_step_status": str(focus_step.get("status", "unknown")),
                "focus_step_eligible": bool(focus_step.get("eligible", False)),
                "strongest_candidate": _program_candidate_snapshot(focus_step),
                "retirement_reason": _program_retirement_reason(summary),
                "next_step": _program_next_step(summary),
                "artifact_refs": focus_step.get("artifact_refs", []) if isinstance(focus_step.get("artifact_refs"), list) else [],
                "summary_path": _research_program_summary_path(catalog_output_dir, program_id),
                "recorded_at_utc": str(summary.get("recorded_at_utc", "")),
            }
        )

    programs.sort(key=_program_sort_key)
    return {
        "schema_version": PROMOTION_PATH_SCHEMA_VERSION,
        "summary_type": "research_program_portfolio",
        "recorded_at_utc": _utcnow(),
        "counts": {
            "total": len(programs),
            "active": sum(1 for program in programs if str(program.get("status", "")) == "active"),
            "retired": sum(1 for program in programs if str(program.get("status", "")) == "retired"),
            "promoted": sum(1 for program in programs if str(program.get("status", "")) == "promoted"),
            "queue_eligible": sum(1 for program in programs if bool(program.get("queue_enabled", False))),
        },
        "active_program_ids": [
            str(program.get("program_id", ""))
            for program in programs
            if str(program.get("status", "")) == "active"
        ],
        "programs": programs,
    }


def build_candidate_progression_summary(
    catalog_output_dir: Path,
    *,
    current_best_candidate: dict[str, object] | None = None,
    agent_summaries: dict[str, dict[str, object]] | None = None,
    research_program_portfolio: dict[str, object] | None = None,
) -> dict[str, object]:
    summaries = agent_summaries if isinstance(agent_summaries, dict) else {}
    history_by_profile = _latest_profile_history(catalog_output_dir)
    program_portfolio = (
        research_program_portfolio
        if isinstance(research_program_portfolio, dict)
        else build_research_program_portfolio(catalog_output_dir)
    )
    records_by_profile: dict[str, dict[str, object]] = {}
    for program in program_portfolio.get("programs", []):
        if not isinstance(program, dict):
            continue
        profile_name = str(program.get("focus_profile_name", "") or "")
        if not profile_name:
            continue
        history_entry = history_by_profile.get(profile_name)
        records_by_profile[profile_name] = _record_from_program(program=program, history_entry=history_entry)

    for profile_name, history_entry in history_by_profile.items():
        if profile_name in records_by_profile:
            records_by_profile[profile_name] = _merge_record_with_history(records_by_profile[profile_name], history_entry)
            continue
        records_by_profile[profile_name] = _record_from_history(profile_name=profile_name, history_entry=history_entry)

    current_summary = current_best_candidate if isinstance(current_best_candidate, dict) else None
    if current_summary:
        if "status" not in current_summary:
            current_summary = _normalize_current_best_candidate(
                current_summary,
                source=str(current_summary.get("source", "active_campaign") or "active_campaign"),
            )
        current_record = _record_from_current_best_candidate(current_summary)
        if current_record is None:
            current_record = {}
        profile_name = str(current_record.get("profile_name", "") or "")
        if profile_name and profile_name in records_by_profile:
            records_by_profile[profile_name] = _merge_candidate_records(records_by_profile[profile_name], current_record)
        elif profile_name:
            records_by_profile[profile_name] = current_record
        for key, value in summaries.items():
            if not isinstance(value, dict):
                continue
            summary_profile = str(value.get("profile_name", "") or "")
            if summary_profile and summary_profile == profile_name:
                supporting = records_by_profile[profile_name].setdefault("supporting_summaries", {})
                if isinstance(supporting, dict):
                    supporting[key] = value

    records = sorted(records_by_profile.values(), key=_candidate_record_sort_key, reverse=True)
    leading = records[0] if records else None
    return {
        "schema_version": PROMOTION_PATH_SCHEMA_VERSION,
        "summary_type": "candidate_progression_summary",
        "recorded_at_utc": _utcnow(),
        "status": "available" if records else "missing",
        "leading_candidate": leading,
        "records": records,
        "counts": {
            "total": len(records),
            "paper_trade_next": sum(1 for record in records if str(record.get("recommendation_state", "")) == "paper_trade_next"),
            "promotion_blocked": sum(1 for record in records if str(record.get("recommendation_state", "")) == "promotion_blocked"),
            "needs_followup": sum(1 for record in records if str(record.get("recommendation_state", "")) == "needs_followup"),
        },
    }


def build_paper_trade_entry_gate(
    catalog_output_dir: Path,
    *,
    candidate_progression_summary: dict[str, object] | None = None,
    explicit_target: dict[str, object] | None = None,
) -> dict[str, object]:
    target = explicit_target if isinstance(explicit_target, dict) else None
    leading_candidate = None
    if target is None and isinstance(candidate_progression_summary, dict):
        leading_candidate = (
            candidate_progression_summary.get("leading_candidate")
            if isinstance(candidate_progression_summary.get("leading_candidate"), dict)
            else None
        )
        if isinstance(leading_candidate, dict):
            target = {
                "config_path": str(leading_candidate.get("config_path", "") or ""),
                "profile_name": str(leading_candidate.get("profile_name", "") or ""),
                "profile_version": str(leading_candidate.get("profile_version", "") or ""),
                "strategy_name": str(leading_candidate.get("strategy_name", "") or "cross_sectional_momentum"),
                "promoted": bool(leading_candidate.get("current_promoted", False)),
                "frozen_on": str(leading_candidate.get("frozen_on", "") or ""),
            }

    block_reasons: list[dict[str, str]] = []
    status = "not_applicable"
    recommended_action = "wait_for_candidate"
    message = "No promotion-path candidate is available for paper-trade entry review."

    if target is None:
        status = "blocked"
        block_reasons.append(
            {
                "code": "no_promoted_candidate",
                "message": "No promoted frozen candidate is available for paper-trading rehearsal.",
            }
        )
        message = block_reasons[0]["message"]
    else:
        promoted = bool(target.get("promoted", False))
        frozen_on = str(target.get("frozen_on", "") or "")
        config_path = str(target.get("config_path", "") or "")
        if not promoted:
            status = "blocked"
            block_reasons.append(
                {
                    "code": "no_promoted_candidate",
                    "message": "No promoted frozen candidate is available for paper-trading rehearsal.",
                }
            )
            message = block_reasons[0]["message"]
        elif not frozen_on:
            status = "blocked"
            recommended_action = "freeze_candidate"
            block_reasons.append(
                {
                    "code": "profile_not_frozen",
                    "message": "The selected profile is not frozen, so paper trading is blocked.",
                }
            )
            message = block_reasons[0]["message"]
        elif not config_path:
            status = "blocked"
            recommended_action = "repair_candidate_metadata"
            block_reasons.append(
                {
                    "code": "config_path_missing",
                    "message": "The promoted candidate does not have a usable config path for paper-trade entry.",
                }
            )
            message = block_reasons[0]["message"]
        elif isinstance(leading_candidate, dict):
            recommendation_state = str(leading_candidate.get("recommendation_state", "research_only"))
            if recommendation_state != "paper_trade_next":
                status = "blocked"
                recommended_action = str(leading_candidate.get("next_action", "") or "continue_research")
                block_reasons.append(
                    {
                        "code": "recommendation_not_ready",
                        "message": "The leading candidate is not yet recommended for paper-trade entry.",
                    }
                )
                message = block_reasons[0]["message"]
            elif _is_stale_timestamp(leading_candidate.get("recorded_at_utc")):
                status = "stale"
                recommended_action = "refresh_candidate_review"
                block_reasons.append(
                    {
                        "code": "promotion_path_stale",
                        "message": "The leading candidate evidence is stale and should be refreshed before paper-trade entry.",
                    }
                )
                message = block_reasons[0]["message"]
            else:
                status = "ready"
                recommended_action = "run_paper_trade_rehearsal"
                message = "The promoted candidate is ready to enter paper-trade rehearsal."
        else:
            status = "ready"
            recommended_action = "run_paper_trade_rehearsal"
            message = "The explicit promoted profile is ready to enter paper-trade rehearsal."

    paper_status = _load_json_file(paper_rehearsal_root(catalog_output_dir) / "state.json")
    latest_day = _load_json_file(paper_rehearsal_root(catalog_output_dir) / "latest_day.json")
    return {
        "schema_version": PROMOTION_PATH_SCHEMA_VERSION,
        "summary_type": "paper_trade_entry_gate",
        "recorded_at_utc": _utcnow(),
        "status": status,
        "recommended_action": recommended_action,
        "message": message,
        "block_reasons": block_reasons,
        "target": target or {},
        "leading_candidate": leading_candidate,
        "paper_rehearsal_state": {
            "current_day_status": paper_status.get("current_day_status"),
            "last_ready_decision_date": paper_status.get("last_ready_decision_date"),
            "latest_day_status": latest_day.get("status"),
            "latest_day_id": latest_day.get("day_id"),
        },
    }


def paper_rehearsal_root(catalog_output_dir: Path) -> Path:
    return Path(catalog_output_dir) / "paper_trading"


def _queue_plan_id(program_id: str) -> str:
    return program_id.removesuffix("_program")


def _research_program_summary_path(catalog_output_dir: Path, program_id: str) -> str:
    path = Path(catalog_output_dir) / safe_artifact_dirname(program_id) / "research_program.json"
    return str(path) if path.exists() else ""


def _selected_program_step(summary: dict[str, object]) -> dict[str, object]:
    decision = summary.get("decision", {}) if isinstance(summary.get("decision"), dict) else {}
    selected_step_id = str(decision.get("selected_step_id", "") or "")
    steps = [step for step in summary.get("campaign_path", []) if isinstance(step, dict)]
    if selected_step_id:
        for step in steps:
            if str(step.get("step_id", "")) == selected_step_id:
                return step
    executed = [step for step in steps if str(step.get("status", "")) != "not_run"]
    if executed:
        return executed[-1]
    return steps[-1] if steps else {}


def _program_candidate_snapshot(step: dict[str, object]) -> dict[str, object]:
    split_summary = step.get("latest_split_summary", {}) if isinstance(step.get("latest_split_summary"), dict) else {}
    walkforward = step.get("latest_walkforward_summary", {}) if isinstance(step.get("latest_walkforward_summary"), dict) else {}
    validation = split_summary.get("validation", {}) if isinstance(split_summary.get("validation"), dict) else {}
    holdout = split_summary.get("holdout", {}) if isinstance(split_summary.get("holdout"), dict) else {}
    return {
        "profile_name": str(step.get("profile_name", "")),
        "config_path": str(step.get("config_path", "")),
        "status": str(step.get("status", "unknown")),
        "eligible": bool(step.get("eligible", False)),
        "validation_status": str(validation.get("status", "unknown")),
        "validation_excess_return": _float(validation.get("excess_return")),
        "holdout_status": str(holdout.get("status", "unknown")),
        "holdout_excess_return": _float(holdout.get("excess_return")),
        "walkforward_pass_windows": int(walkforward.get("pass_windows", 0) or 0),
    }


def _program_retirement_reason(summary: dict[str, object]) -> str:
    if str(summary.get("status", "")) != "retired":
        return ""
    decision = summary.get("decision", {}) if isinstance(summary.get("decision"), dict) else {}
    return str(decision.get("summary", "") or "")


def _program_next_step(summary: dict[str, object]) -> str:
    if str(summary.get("status", "")) == "retired":
        return ""
    decision = summary.get("decision", {}) if isinstance(summary.get("decision"), dict) else {}
    return str(decision.get("summary", "") or "")


def _record_from_program(*, program: dict[str, object], history_entry: dict[str, object] | None) -> dict[str, object]:
    strongest = program.get("strongest_candidate", {}) if isinstance(program.get("strongest_candidate"), dict) else {}
    fail_reasons = _fail_reasons_from_history(history_entry)
    current_promoted = bool(history_entry.get("current_promoted", False)) if isinstance(history_entry, dict) else False
    profile = history_entry.get("profile", {}) if isinstance(history_entry, dict) and isinstance(history_entry.get("profile"), dict) else {}
    recommendation_state = _recommendation_state(
        operator_recommendation="paper_trade_next" if current_promoted or bool(strongest.get("eligible", False)) else "needs_more_research",
        fail_reasons=fail_reasons,
        promoted=current_promoted,
        eligible=bool(strongest.get("eligible", False)),
        program_status=str(program.get("status", "active")),
    )
    artifact_refs = program.get("artifact_refs", []) if isinstance(program.get("artifact_refs"), list) else []
    return {
        "candidate_id": str(program.get("focus_profile_name", "")),
        "profile_name": str(program.get("focus_profile_name", "")),
        "profile_version": str(profile.get("profile_version", "")),
        "frozen_on": str(profile.get("frozen_on", "")),
        "config_path": str(strongest.get("config_path", "")),
        "run_name": "",
        "strategy_name": "cross_sectional_momentum",
        "source_type": "research_program",
        "source_status": str(program.get("status", "active")),
        "campaign_id": "",
        "campaign_name": "",
        "director_id": "",
        "research_program_id": str(program.get("program_id", "")),
        "research_program_title": str(program.get("title", "")),
        "queue_plan_id": str(program.get("queue_plan_id", "")),
        "program_queue_enabled": bool(program.get("queue_enabled", False)),
        "operator_recommendation": "paper_trade_next" if recommendation_state == "paper_trade_next" else "needs_more_research",
        "recommendation_state": recommendation_state,
        "validation_status": str(strongest.get("validation_status", "unknown")),
        "validation_excess_return": _float(strongest.get("validation_excess_return")),
        "holdout_status": str(strongest.get("holdout_status", "unknown")),
        "holdout_excess_return": _float(strongest.get("holdout_excess_return")),
        "walkforward_pass_windows": int(strongest.get("walkforward_pass_windows", 0) or 0),
        "walkforward_eligible": bool((history_entry or {}).get("walkforward_summary", {}).get("eligible", False))
        if isinstance(history_entry, dict)
        else False,
        "stress_ok": None,
        "promotion_eligible": bool(strongest.get("eligible", False)),
        "current_promoted": current_promoted,
        "blocking_reasons": fail_reasons or _program_blocking_reasons(program),
        "headline": str(program.get("decision_summary", "")),
        "next_action": str(program.get("recommended_action", "continue_research")),
        "artifact_refs": artifact_refs,
        "supporting_summaries": {},
        "recorded_at_utc": str(program.get("recorded_at_utc", "")),
    }


def _record_from_history(*, profile_name: str, history_entry: dict[str, object]) -> dict[str, object]:
    profile = history_entry.get("profile", {}) if isinstance(history_entry.get("profile"), dict) else {}
    split_summary = history_entry.get("split_summary", {}) if isinstance(history_entry.get("split_summary"), dict) else {}
    validation = split_summary.get("validation", {}) if isinstance(split_summary.get("validation"), dict) else {}
    holdout = split_summary.get("holdout", {}) if isinstance(split_summary.get("holdout"), dict) else {}
    walkforward = history_entry.get("walkforward_summary", {}) if isinstance(history_entry.get("walkforward_summary"), dict) else {}
    fail_reasons = _fail_reasons_from_history(history_entry)
    promoted = bool(history_entry.get("current_promoted", False))
    eligible = bool(history_entry.get("eligible", False))
    recommendation_state = _recommendation_state(
        operator_recommendation="paper_trade_next" if promoted or eligible else "needs_more_research",
        fail_reasons=fail_reasons,
        promoted=promoted,
        eligible=eligible,
        program_status="history",
    )
    return {
        "candidate_id": profile_name,
        "profile_name": profile_name,
        "profile_version": str(profile.get("profile_version", "")),
        "frozen_on": str(profile.get("frozen_on", "")),
        "config_path": str(history_entry.get("config_path", "")),
        "run_name": "",
        "strategy_name": "cross_sectional_momentum",
        "source_type": "profile_history",
        "source_status": "promoted" if promoted else "history",
        "campaign_id": "",
        "campaign_name": "",
        "director_id": "",
        "research_program_id": "",
        "research_program_title": "",
        "queue_plan_id": "",
        "program_queue_enabled": False,
        "operator_recommendation": "paper_trade_next" if recommendation_state == "paper_trade_next" else "needs_more_research",
        "recommendation_state": recommendation_state,
        "validation_status": str(validation.get("status", "unknown")),
        "validation_excess_return": _float(validation.get("excess_return")),
        "holdout_status": str(holdout.get("status", "unknown")),
        "holdout_excess_return": _float(holdout.get("excess_return")),
        "walkforward_pass_windows": int(walkforward.get("pass_windows", 0) or 0),
        "walkforward_eligible": bool(walkforward.get("eligible", False)),
        "stress_ok": None,
        "promotion_eligible": eligible,
        "current_promoted": promoted,
        "blocking_reasons": fail_reasons,
        "headline": str(history_entry.get("recommended_action", "retain")),
        "next_action": str(history_entry.get("recommended_action", "retain")),
        "artifact_refs": _artifact_refs_from_history(profile_name, history_entry),
        "supporting_summaries": {},
        "recorded_at_utc": str(history_entry.get("recorded_at_utc", "")),
    }


def _record_from_current_best_candidate(summary: dict[str, object]) -> dict[str, object] | None:
    if str(summary.get("status", "") or "") != "available":
        return None
    candidate = summary.get("best_candidate", {}) if isinstance(summary.get("best_candidate"), dict) else {}
    progression = summary.get("progression", {}) if isinstance(summary.get("progression"), dict) else {}
    operator_recommendation = str(summary.get("operator_recommendation", "needs_more_research"))
    missing_evidence = [
        str(item)
        for item in summary.get("what_failed_or_is_missing", [])
        if str(item).strip()
    ] if isinstance(summary.get("what_failed_or_is_missing"), list) else []
    recommendation_state = _recommendation_state(
        operator_recommendation=operator_recommendation,
        fail_reasons=[],
        promoted=False,
        eligible=bool(progression.get("selected_candidate_eligible", False)),
        program_status=str(summary.get("campaign_status", "unknown")),
    )
    profile_name = str(candidate.get("profile_name", "") or progression.get("selected_profile_name", "") or "")
    if not profile_name:
        return None
    return {
        "candidate_id": profile_name or str(summary.get("campaign_id", "")),
        "profile_name": profile_name,
        "profile_version": "",
        "frozen_on": "",
        "config_path": "",
        "run_name": str(candidate.get("run_name", "")),
        "strategy_name": "cross_sectional_momentum",
        "source_type": str(summary.get("source", "active_campaign")),
        "source_status": str(summary.get("campaign_status", "unknown")),
        "campaign_id": str(summary.get("campaign_id", "")),
        "campaign_name": str(summary.get("campaign_name", "")),
        "director_id": "",
        "research_program_id": "",
        "research_program_title": "",
        "queue_plan_id": "",
        "program_queue_enabled": False,
        "operator_recommendation": operator_recommendation,
        "recommendation_state": recommendation_state,
        "validation_status": "pass" if _float(candidate.get("validation_excess_return")) > 0 else "fail",
        "validation_excess_return": _float(candidate.get("validation_excess_return")),
        "holdout_status": "pass" if _float(candidate.get("holdout_excess_return")) > 0 else "fail",
        "holdout_excess_return": _float(candidate.get("holdout_excess_return")),
        "walkforward_pass_windows": int(candidate.get("walkforward_pass_windows", 0) or 0),
        "walkforward_eligible": int(candidate.get("walkforward_pass_windows", 0) or 0) >= 2,
        "stress_ok": candidate.get("stress_ok"),
        "promotion_eligible": bool(progression.get("selected_candidate_eligible", False)),
        "current_promoted": False,
        "blocking_reasons": missing_evidence,
        "headline": str(summary.get("headline", "")),
        "next_action": str(summary.get("next_action", "")),
        "artifact_refs": _artifact_refs_from_summary(summary),
        "supporting_summaries": {
            key: value
            for key, value in (summary.get("supporting_summaries", {}) if isinstance(summary.get("supporting_summaries"), dict) else {}).items()
            if isinstance(value, dict)
        },
        "recorded_at_utc": str(summary.get("campaign_updated_at", "")),
    }


def _normalize_current_best_candidate(summary: dict[str, object], *, source: str) -> dict[str, object]:
    normalized = dict(summary)
    candidate = normalized.get("best_candidate") if isinstance(normalized.get("best_candidate"), dict) else None
    progression = normalized.get("progression") if isinstance(normalized.get("progression"), dict) else {}
    has_selected_candidate = bool(candidate and (str(candidate.get("run_name", "") or "").strip() or str(candidate.get("profile_name", "") or "").strip()))
    normalized["source"] = source
    normalized["status"] = "available" if has_selected_candidate else "no_selected_candidate"
    normalized["candidate_available"] = has_selected_candidate
    normalized["recommendation_state"] = _recommendation_state(
        operator_recommendation=str(normalized.get("operator_recommendation", "needs_more_research")),
        fail_reasons=[],
        promoted=False,
        eligible=bool(progression.get("selected_candidate_eligible", False)),
        program_status=str(normalized.get("campaign_status", "unknown")),
    )
    if has_selected_candidate:
        normalized["display_message"] = str(normalized.get("headline", "") or "")
        return normalized
    normalized["best_candidate"] = None
    missing = [
        str(item)
        for item in normalized.get("what_failed_or_is_missing", [])
        if str(item).strip()
    ] if isinstance(normalized.get("what_failed_or_is_missing"), list) else []
    fallback = missing[0] if missing else "No selected candidate is available for operator review."
    normalized["display_message"] = fallback
    return normalized


def _merge_record_with_history(record: dict[str, object], history_entry: dict[str, object]) -> dict[str, object]:
    history_record = _record_from_history(profile_name=str(record.get("profile_name", "")), history_entry=history_entry)
    return _merge_candidate_records(history_record, record)


def _merge_candidate_records(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "artifact_refs":
            merged[key] = _dedupe_artifact_refs(
                [
                    *(merged.get(key, []) if isinstance(merged.get(key), list) else []),
                    *(value if isinstance(value, list) else []),
                ]
            )
            continue
        if key == "supporting_summaries":
            current = merged.get(key, {}) if isinstance(merged.get(key), dict) else {}
            merged[key] = {**current, **(value if isinstance(value, dict) else {})}
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        merged[key] = value
    return merged


def _artifact_refs_from_summary(summary: dict[str, object]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    artifact_paths = summary.get("artifact_paths", {}) if isinstance(summary.get("artifact_paths"), dict) else {}
    for artifact_type, path in artifact_paths.items():
        text = str(path or "").strip()
        if not text:
            continue
        refs.append({"artifact_type": artifact_type, "primary_path": text})
    return refs


def _artifact_refs_from_history(profile_name: str, history_entry: dict[str, object]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    history_path = Path("runtime") / "catalog" / "profile_history" / f"{profile_name}.jsonl"
    if history_path.exists():
        refs.append({"artifact_type": "promotion_history", "primary_path": str(history_path)})
    split_summary = history_entry.get("split_summary", {}) if isinstance(history_entry.get("split_summary"), dict) else {}
    for label in ("train", "validation", "holdout"):
        split = split_summary.get(label, {}) if isinstance(split_summary.get(label), dict) else {}
        results_path = str(split.get("results_path", "") or "")
        if results_path:
            refs.append({"artifact_type": f"{label}_results", "primary_path": results_path})
    return refs


def _fail_reasons_from_history(history_entry: dict[str, object] | None) -> list[str]:
    if not isinstance(history_entry, dict):
        return []
    return [str(reason) for reason in history_entry.get("fail_reasons", []) if str(reason).strip()]


def _program_blocking_reasons(program: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    focus_status = str(program.get("focus_step_status", "unknown"))
    if focus_status == "not_run":
        reasons.append("No recorded promotion decision exists yet for this branch.")
    decision_reason = str(program.get("decision_reason", "") or "")
    if decision_reason == "terminal_branch_failure":
        reasons.append("This research program is already retired.")
    return reasons


def _recommendation_state(
    *,
    operator_recommendation: str,
    fail_reasons: list[str],
    promoted: bool,
    eligible: bool,
    program_status: str,
) -> str:
    if promoted or eligible or operator_recommendation == "paper_trade_next":
        return "paper_trade_next"
    if fail_reasons or program_status == "retired" or operator_recommendation == "reject":
        return "promotion_blocked"
    if operator_recommendation == "needs_more_research" or program_status in {"active", "running", "queued"}:
        return "needs_followup"
    return "research_only"


def _candidate_record_sort_key(record: dict[str, object]) -> tuple[int, int, int, str]:
    recommendation_state = str(record.get("recommendation_state", "research_only"))
    source_type = str(record.get("source_type", "history"))
    source_rank = {
        "active_campaign": 4,
        "most_recent_terminal_campaign": 3,
        "research_program": 2,
        "profile_history": 1,
    }.get(source_type, 0)
    recommendation_rank = {
        "paper_trade_next": 4,
        "needs_followup": 3,
        "research_only": 2,
        "promotion_blocked": 1,
    }.get(recommendation_state, 0)
    return (
        recommendation_rank,
        source_rank,
        1 if bool(record.get("current_promoted", False)) else 0,
        str(record.get("recorded_at_utc", "")),
    )


def _program_sort_key(program: dict[str, object]) -> tuple[int, int, str]:
    status_rank = {"active": 3, "promoted": 2, "retired": 1}.get(str(program.get("status", "")), 0)
    queue_rank = int(program.get("queue_priority", 999) or 999)
    return (-status_rank, queue_rank, str(program.get("program_id", "")))


def _latest_campaign(campaigns: list[dict[str, object]]) -> dict[str, object] | None:
    valid = [campaign for campaign in campaigns if isinstance(campaign, dict)]
    if not valid:
        return None
    return max(valid, key=lambda campaign: str(campaign.get("updated_at", "") or ""))


def _latest_profile_history(catalog_output_dir: Path) -> dict[str, dict[str, object]]:
    history_dir = Path(catalog_output_dir) / "profile_history"
    latest: dict[str, dict[str, object]] = {}
    if not history_dir.exists():
        return latest
    for path in history_dir.glob("*.jsonl"):
        entry = _latest_jsonl_entry(path)
        if not isinstance(entry, dict):
            continue
        profile = entry.get("profile", {}) if isinstance(entry.get("profile"), dict) else {}
        profile_name = str(profile.get("profile_name", "") or path.stem)
        if profile_name:
            latest[profile_name] = entry
    return latest


def _load_runbook() -> dict[str, object]:
    path = Path.cwd() / "configs" / "openclaw" / "trotters-runbook.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_jsonl_entry(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    latest: dict[str, object] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            latest = payload
    return latest


def _is_stale_timestamp(value: object) -> bool:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return True
    return timestamp < datetime.now(UTC) - timedelta(hours=PROMOTION_PATH_STALE_HOURS)


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _write_promotion_summary(catalog_output_dir: Path, summary_type: str, payload: dict[str, object]) -> None:
    root = Path(catalog_output_dir) / "promotion_path"
    latest_dir = root / "latest"
    archive_dir = root / summary_type
    latest_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_dir / f"{summary_type}.json"
    snapshot_path = archive_dir / f"{_timestamp_slug(_utcnow())}__{uuid.uuid4().hex}.json"
    _write_json(latest_path, payload)
    _write_json(snapshot_path, payload)
    index_path = root / "index.json"
    index_payload = _load_json_file(index_path)
    records = [
        record
        for record in index_payload.get("records", [])
        if isinstance(record, dict) and str(record.get("summary_type", "")) != summary_type
    ]
    records.append(
        {
            "summary_type": summary_type,
            "latest_path": str(latest_path),
            "snapshot_path": str(snapshot_path),
            "recorded_at_utc": str(payload.get("recorded_at_utc", "")),
        }
    )
    _write_json(index_path, {"records": records})


def _load_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _replace_with_retry(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _replace_with_retry(temp_path: Path, path: Path) -> None:
    last_error: PermissionError | None = None
    for attempt in range(PROMOTION_PATH_REPLACE_RETRIES):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt >= PROMOTION_PATH_REPLACE_RETRIES - 1:
                break
            time.sleep(PROMOTION_PATH_REPLACE_SLEEP_SECONDS)
    if last_error is not None:
        raise last_error


def _dedupe_artifact_refs(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        artifact_type = str(entry.get("artifact_type", "artifact"))
        primary_path = str(entry.get("primary_path", ""))
        deduped[(artifact_type, primary_path)] = entry
    return list(deduped.values())


def _timestamp_slug(value: str) -> str:
    return value.replace(":", "").replace("+00:00", "Z")


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
