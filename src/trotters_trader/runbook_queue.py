from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def build_runbook_queue_summary(
    *,
    active_branch_summary: dict[str, object] | None,
    research_program_portfolio: dict[str, object] | None,
) -> dict[str, object]:
    runbook = _load_runbook()
    queue_entries = [
        dict(entry)
        for entry in runbook.get("work_queue", [])
        if isinstance(entry, dict)
    ] if isinstance(runbook.get("work_queue"), list) else []
    portfolio = research_program_portfolio if isinstance(research_program_portfolio, dict) else {}
    programs = [
        dict(program)
        for program in portfolio.get("programs", [])
        if isinstance(program, dict)
    ] if isinstance(portfolio.get("programs"), list) else []
    programs_by_plan_id = {
        str(program.get("queue_plan_id", "")).strip(): program
        for program in programs
        if str(program.get("queue_plan_id", "")).strip()
    }

    director = (
        active_branch_summary.get("director")
        if isinstance(active_branch_summary, dict) and isinstance(active_branch_summary.get("director"), dict)
        else {}
    )
    active_plan_id = str(director.get("plan_name", "") or "").strip()
    active_entry_index = next(
        (
            index
            for index, entry in enumerate(queue_entries)
            if str(entry.get("plan_id", "")).strip() == active_plan_id
        ),
        None,
    )

    entries: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for index, entry in enumerate(queue_entries):
        plan_id = str(entry.get("plan_id", "")).strip()
        enabled = bool(entry.get("enabled", False))
        program = programs_by_plan_id.get(plan_id)
        queue_status = _entry_status(
            plan_id=plan_id,
            enabled=enabled,
            active_plan_id=active_plan_id,
            program=program,
        )
        detail = _entry_detail(
            plan_id=plan_id,
            queue_status=queue_status,
            program=program,
        )
        record = {
            "queue_index": index,
            "plan_id": plan_id,
            "plan_file": str(entry.get("plan_file", "") or ""),
            "director_name": str(entry.get("director_name", "") or ""),
            "enabled": enabled,
            "priority": int(entry.get("priority", index + 1) or index + 1),
            "queue_status": queue_status,
            "detail": detail,
            "program_status": str(program.get("status", "") or "") if isinstance(program, dict) else "",
            "program_title": str(program.get("title", "") or "") if isinstance(program, dict) else "",
            "program_summary_path": str(program.get("summary_path", "") or "") if isinstance(program, dict) else "",
        }
        entries.append(record)
        warning = _entry_warning(record)
        if warning:
            warnings.append(warning)

    if active_plan_id and active_entry_index is None:
        warnings.append(
            {
                "code": "active_plan_missing_from_runbook",
                "message": f"Active plan '{active_plan_id}' is not present in the supervisor work queue.",
                "plan_id": active_plan_id,
            }
        )
    elif active_plan_id and active_plan_id not in programs_by_plan_id:
        warnings.append(
            {
                "code": "active_plan_untracked",
                "message": f"Active plan '{active_plan_id}' is running, but it has no matching research-program definition.",
                "plan_id": active_plan_id,
            }
        )

    next_runnable = _next_runnable_entry(entries, start_index=(active_entry_index + 1) if isinstance(active_entry_index, int) else 0)
    if next_runnable is None and entries:
        if any(bool(entry.get("enabled", False)) for entry in entries):
            warnings.append(
                {
                    "code": "no_next_runnable_queue_item",
                    "message": "No enabled queue item is currently runnable after the active plan.",
                }
            )

    counts = {
        "total": len(entries),
        "enabled": sum(1 for entry in entries if bool(entry.get("enabled", False))),
        "active": sum(1 for entry in entries if str(entry.get("queue_status", "")) == "active"),
        "ready": sum(1 for entry in entries if str(entry.get("queue_status", "")) == "ready"),
        "blocked": sum(1 for entry in entries if str(entry.get("queue_status", "")) in {"blocked_retired", "blocked_promoted"}),
        "untracked": sum(1 for entry in entries if str(entry.get("queue_status", "")) == "untracked"),
    }
    return {
        "summary_type": "runbook_queue_summary",
        "recorded_at_utc": _utcnow(),
        "status": _summary_status(warnings, next_runnable),
        "message": _summary_message(active_plan_id=active_plan_id, next_runnable=next_runnable, warnings=warnings),
        "recommended_action": _recommended_action(warnings, next_runnable),
        "active_plan_id": active_plan_id or None,
        "next_runnable_plan_id": str(next_runnable.get("plan_id", "") or "") if isinstance(next_runnable, dict) else None,
        "counts": counts,
        "entries": entries,
        "warnings": warnings,
        "runbook_path": str(Path.cwd() / "configs" / "openclaw" / "trotters-runbook.json"),
    }


def _entry_status(
    *,
    plan_id: str,
    enabled: bool,
    active_plan_id: str,
    program: dict[str, object] | None,
) -> str:
    if plan_id and active_plan_id and plan_id == active_plan_id:
        return "active"
    if not enabled:
        return "disabled"
    if not isinstance(program, dict):
        return "untracked"
    program_status = str(program.get("status", "") or "")
    if program_status == "retired":
        return "blocked_retired"
    if program_status == "promoted":
        return "blocked_promoted"
    return "ready"


def _entry_detail(*, plan_id: str, queue_status: str, program: dict[str, object] | None) -> str:
    if queue_status == "active":
        return f"{plan_id} is the currently active supervisor work item."
    if queue_status == "disabled":
        return f"{plan_id} is disabled in the supervisor runbook."
    if queue_status == "untracked":
        return f"{plan_id} has no research-program definition, so the portfolio cannot explain its state."
    if queue_status == "blocked_retired":
        summary = str(program.get("decision_summary", "") or "").strip() if isinstance(program, dict) else ""
        return summary or f"{plan_id} maps to a retired research program and is not a valid next branch."
    if queue_status == "blocked_promoted":
        return f"{plan_id} already maps to a promoted program and should not be re-queued blindly."
    return f"{plan_id} is enabled and remains eligible for future continuation."


def _entry_warning(entry: dict[str, object]) -> dict[str, object] | None:
    queue_status = str(entry.get("queue_status", "") or "")
    plan_id = str(entry.get("plan_id", "") or "")
    if queue_status == "untracked":
        return {
            "code": "enabled_untracked_plan",
            "message": f"Runbook item '{plan_id}' is enabled but has no matching research-program definition.",
            "plan_id": plan_id,
        }
    if queue_status == "blocked_retired":
        return {
            "code": "enabled_retired_program",
            "message": f"Runbook item '{plan_id}' is enabled even though its research program is retired.",
            "plan_id": plan_id,
        }
    if queue_status == "blocked_promoted":
        return {
            "code": "enabled_promoted_program",
            "message": f"Runbook item '{plan_id}' is enabled even though its research program is already promoted.",
            "plan_id": plan_id,
        }
    return None


def _next_runnable_entry(entries: list[dict[str, object]], *, start_index: int) -> dict[str, object] | None:
    for entry in entries[start_index:]:
        if str(entry.get("queue_status", "")) == "ready":
            return entry
    return None


def _summary_status(warnings: list[dict[str, object]], next_runnable: dict[str, object] | None) -> str:
    if warnings:
        return "attention"
    if next_runnable is not None:
        return "ready"
    return "aligned"


def _summary_message(
    *,
    active_plan_id: str,
    next_runnable: dict[str, object] | None,
    warnings: list[dict[str, object]],
) -> str:
    if warnings:
        return str(warnings[0].get("message", "Supervisor work queue needs attention."))
    if active_plan_id and isinstance(next_runnable, dict):
        return f"Active plan '{active_plan_id}' is aligned with the queue, and '{next_runnable.get('plan_id')}' is the next runnable branch."
    if active_plan_id:
        return f"Active plan '{active_plan_id}' is aligned with the queue, but no next runnable branch remains."
    if isinstance(next_runnable, dict):
        return f"No plan is active; '{next_runnable.get('plan_id')}' is the next runnable queue item."
    return "The supervisor work queue has no runnable entries."


def _recommended_action(warnings: list[dict[str, object]], next_runnable: dict[str, object] | None) -> str:
    if warnings:
        return "repair_runbook_alignment"
    if next_runnable is None:
        return "define_next_research_family"
    return "monitor_active_plan"


def _load_runbook() -> dict[str, object]:
    path = Path.cwd() / "configs" / "openclaw" / "trotters-runbook.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
