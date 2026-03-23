from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Callable

from trotters_trader.active_branch import build_active_branch_summary
from trotters_trader.agent_dispatches import load_dispatch_records, load_dispatch_summary
from trotters_trader.agent_summaries import load_latest_summaries
from trotters_trader.paper_rehearsal import paper_rehearsal_status
from trotters_trader.promotion_path import materialize_promotion_path, resolve_current_best_candidate
from trotters_trader.research_families import build_next_family_status, build_research_family_comparison_summary
from trotters_trader.research_runtime import ResearchRuntimePaths
from trotters_trader.runbook_queue import build_runbook_queue_summary


def build_runtime_overview_payload(
    paths: ResearchRuntimePaths,
    *,
    status: dict[str, object],
    status_payload: dict[str, object],
    active_directors: list[dict[str, object]],
    active_campaigns: list[dict[str, object]],
    include_catalog_status: bool = False,
    include_health: bool = False,
    include_most_recent_terminal: bool = False,
    notification_limit: int = 25,
    fetch_campaign_detail: Callable[[str], dict[str, object]],
    resolve_current_best_candidate_fn: Callable[..., dict[str, object]] = resolve_current_best_candidate,
    materialize_promotion_path_fn: Callable[..., dict[str, object]] = materialize_promotion_path,
    build_research_family_comparison_summary_fn: Callable[..., dict[str, object]] = build_research_family_comparison_summary,
    build_runbook_queue_summary_fn: Callable[..., dict[str, object]] = build_runbook_queue_summary,
    build_next_family_status_fn: Callable[..., dict[str, object]] = build_next_family_status,
    load_latest_summaries_fn: Callable[..., dict[str, object]] = load_latest_summaries,
    load_dispatch_records_fn: Callable[..., list[dict[str, object]]] = load_dispatch_records,
    load_dispatch_summary_fn: Callable[..., dict[str, object]] = load_dispatch_summary,
    paper_rehearsal_status_fn: Callable[..., dict[str, object]] = paper_rehearsal_status,
) -> dict[str, object]:
    most_recent_terminal_summary = most_recent_terminal(status)
    agent_summaries = load_latest_summaries_fn(paths.catalog_output_dir)
    current_best_candidate = resolve_current_best_candidate_fn(
        catalog_output_dir=paths.catalog_output_dir,
        active_campaigns=active_campaigns,
        most_recent_terminal=most_recent_terminal_summary,
        agent_summaries=agent_summaries,
        fetch_campaign_detail=fetch_campaign_detail,
    )
    promotion_path = materialize_promotion_path_fn(
        catalog_output_dir=paths.catalog_output_dir,
        current_best_candidate=current_best_candidate,
        agent_summaries=agent_summaries,
    )
    research_family_comparison_summary = build_research_family_comparison_summary_fn(
        catalog_output_dir=paths.catalog_output_dir,
        research_program_portfolio=promotion_path["research_program_portfolio"],
    )
    active_branch_summary = build_active_branch_summary(
        active_directors=active_directors,
        active_campaigns=active_campaigns,
    )
    runbook_queue_summary = build_runbook_queue_summary_fn(
        active_branch_summary=active_branch_summary,
        research_program_portfolio=promotion_path["research_program_portfolio"],
        research_family_comparison_summary=research_family_comparison_summary,
    )
    next_family_status = build_next_family_status_fn(
        catalog_output_dir=paths.catalog_output_dir,
        runbook_queue_summary=runbook_queue_summary,
        research_family_comparison_summary=research_family_comparison_summary,
        active_branch_summary=active_branch_summary,
    )
    payload: dict[str, object] = {
        "status": status_payload,
        "active_directors": active_directors,
        "active_campaigns": active_campaigns,
        "active_branch_summary": active_branch_summary,
        "runbook_queue_summary": runbook_queue_summary,
        "research_family_comparison_summary": research_family_comparison_summary,
        "next_family_status": next_family_status,
        "notifications": load_runtime_notifications(paths, limit=notification_limit),
        "paper_rehearsal": paper_rehearsal_status_fn(paths.catalog_output_dir, limit=5),
        "current_best_candidate": current_best_candidate,
        "candidate_progression_summary": promotion_path["candidate_progression_summary"],
        "paper_trade_entry_gate": promotion_path["paper_trade_entry_gate"],
        "research_program_portfolio": promotion_path["research_program_portfolio"],
        "agent_summaries": agent_summaries,
        "agent_dispatches": load_dispatch_records_fn(paths.catalog_output_dir, limit=10),
        "agent_dispatch_summary": load_dispatch_summary_fn(paths.catalog_output_dir, limit=100),
    }
    if include_catalog_status:
        payload["catalog_status"] = catalog_status(paths)
    if include_health:
        payload["health"] = runtime_health(
            status=status,
            campaigns=active_campaigns,
            directors=active_directors,
            next_family_status=next_family_status,
        )
    if include_most_recent_terminal:
        payload["most_recent_terminal"] = most_recent_terminal_summary
    return payload


def load_runtime_notifications(
    paths: ResearchRuntimePaths,
    *,
    limit: int,
    event_type: str | None = None,
    campaign_id: str | None = None,
    severity: str | None = None,
) -> list[dict[str, object]]:
    notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
    if not notifications_path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in notifications_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if event_type and str(payload.get("event_type", "")).strip() != event_type:
            continue
        if campaign_id and str(payload.get("campaign_id", "")).strip() != campaign_id:
            continue
        if severity and str(payload.get("severity", "")).strip() != severity:
            continue
        records.append(payload)
    return records[-limit:][::-1]


def catalog_status(paths: ResearchRuntimePaths) -> dict[str, object]:
    catalog_jsonl = paths.catalog_output_dir / "research_catalog" / "catalog.jsonl"
    return {
        "available": catalog_jsonl.exists(),
        "catalog_jsonl": str(catalog_jsonl),
    }


def most_recent_terminal(status: dict[str, object]) -> dict[str, object]:
    return {
        "campaign": latest_terminal_entry(
            status.get("campaigns"),
            statuses={"failed", "stopped", "exhausted", "completed"},
        ),
        "director": latest_terminal_entry(
            status.get("directors"),
            statuses={"failed", "stopped", "exhausted"},
        ),
    }


def compact_overview_status(status: dict[str, object], *, queued_preview_limit: int = 10) -> dict[str, object]:
    counts = dict(status.get("counts", {})) if isinstance(status.get("counts"), dict) else {}
    workers = [
        dict(worker)
        for worker in status.get("workers", [])
        if isinstance(worker, dict)
    ] if isinstance(status.get("workers"), list) else []
    jobs = [
        dict(job)
        for job in status.get("jobs", [])
        if isinstance(job, dict)
    ] if isinstance(status.get("jobs"), list) else []
    campaigns = [
        dict(campaign)
        for campaign in status.get("campaigns", [])
        if isinstance(campaign, dict)
    ] if isinstance(status.get("campaigns"), list) else []
    directors = [
        dict(director)
        for director in status.get("directors", [])
        if isinstance(director, dict)
    ] if isinstance(status.get("directors"), list) else []
    queued_jobs = [job for job in jobs if str(job.get("status", "")).lower() == "queued"]
    running_jobs = [job for job in jobs if str(job.get("status", "")).lower() == "running"]
    service_heartbeats = [
        dict(record)
        for record in status.get("service_heartbeats", [])
        if isinstance(record, dict)
    ] if isinstance(status.get("service_heartbeats"), list) else []
    compact = {
        "counts": counts,
        "workers": workers,
        "running_jobs": running_jobs,
        "queued_jobs_preview": queued_jobs[:queued_preview_limit],
        "queued_jobs_total": len(queued_jobs),
        "service_heartbeats": service_heartbeats,
        "recent_terminal_campaigns": recent_terminal_entries(
            campaigns,
            statuses={"failed", "stopped", "exhausted", "completed"},
            limit=5,
        ),
        "recent_terminal_directors": recent_terminal_entries(
            directors,
            statuses={"failed", "stopped", "exhausted"},
            limit=5,
        ),
    }
    if "database_path" in status:
        compact["database_path"] = status["database_path"]
    return compact


def detail_or_summary(fetch_detail: Callable[[], dict[str, object]], summary: dict[str, object]) -> dict[str, object]:
    try:
        detail = fetch_detail()
    except ValueError:
        return summary
    return detail if isinstance(detail, dict) and detail else summary


def recent_outcomes(items: object, *, limit: int = 6) -> list[dict[str, object]]:
    return recent_terminal_entries(
        items,
        statuses={"completed", "exhausted", "failed", "stopped"},
        limit=limit,
    )


def recent_terminal_entries(entries: object, *, statuses: set[str], limit: int) -> list[dict[str, object]]:
    if not isinstance(entries, list):
        return []
    terminal: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized_status = str(entry.get("status", "")).lower()
        if normalized_status not in statuses:
            continue
        terminal.append(dict(entry))
    terminal.sort(
        key=lambda item: timestamp_sort_key(item.get("finished_at") or item.get("updated_at") or item.get("created_at")),
        reverse=True,
    )
    return terminal[:limit]


def latest_terminal_entry(entries: object, *, statuses: set[str]) -> dict[str, object] | None:
    terminal = recent_terminal_entries(entries, statuses=statuses, limit=1)
    return terminal[0] if terminal else None


def runtime_health(
    *,
    status: dict[str, object],
    campaigns: list[dict[str, object]],
    directors: list[dict[str, object]],
    next_family_status: dict[str, object] | None = None,
) -> dict[str, object]:
    counts = status.get("counts", {}) if isinstance(status.get("counts"), dict) else {}
    all_directors = [director for director in status.get("directors", []) if isinstance(director, dict)] if isinstance(status.get("directors"), list) else []
    workers = [worker for worker in status.get("workers", []) if isinstance(worker, dict)] if isinstance(status.get("workers"), list) else []
    jobs = [job for job in status.get("jobs", []) if isinstance(job, dict)] if isinstance(status.get("jobs"), list) else []
    service_heartbeats = [
        record
        for record in status.get("service_heartbeats", [])
        if isinstance(record, dict)
    ] if isinstance(status.get("service_heartbeats"), list) else []
    queued = int(counts.get("queued", 0) or 0)
    running = int(counts.get("running", 0) or 0)
    active_director_count = len(directors)
    most_recent_director = max(
        all_directors,
        key=lambda director: timestamp_sort_key(director.get("updated_at") or director.get("created_at")),
        default=None,
    )
    most_recent_director_status = str(most_recent_director.get("status", "")).lower() if isinstance(most_recent_director, dict) else ""
    most_recent_director_name = (
        str(most_recent_director.get("director_name") or most_recent_director.get("director_id") or "unknown director")
        if isinstance(most_recent_director, dict)
        else "unknown director"
    )
    most_recent_director_age = (
        age_seconds(most_recent_director.get("updated_at") or most_recent_director.get("created_at"))
        if isinstance(most_recent_director, dict)
        else None
    )
    director_requires_attention = active_director_count == 0 and most_recent_director_status in {"failed", "stopped"}
    active_worker_count = sum(
        1
        for worker in workers
        if str(worker.get("status", "")).lower() in {"running", "idle"}
    )
    stale_worker_count = sum(
        1
        for worker in workers
        if age_seconds(worker.get("heartbeat_at") or worker.get("updated_at")) is not None
        and age_seconds(worker.get("heartbeat_at") or worker.get("updated_at")) > 180
    )
    stale_running_job_count = sum(
        1
        for job in jobs
        if str(job.get("status", "")).lower() == "running"
        and (age_seconds(job.get("updated_at")) or 0) > 900
    )
    oldest_running_job_age = max(
        (
            age_seconds(job.get("updated_at")) or 0
            for job in jobs
            if str(job.get("status", "")).lower() == "running"
        ),
        default=0,
    )
    freshest_campaign_age = min(
        (
            age_seconds(campaign.get("updated_at")) or 0
            for campaign in campaigns
        ),
        default=None,
    )
    degraded_services = [
        record
        for record in service_heartbeats
        if str(record.get("status", "")).lower() != "ok"
    ]
    next_family = next_family_status if isinstance(next_family_status, dict) else {}
    next_family_state = str(next_family.get("status", "")).lower()
    governance_blocked = next_family_state in {"blocked_pending_approval", "blocked_pending_bootstrap"}
    governance_message = str(next_family.get("message", "")).strip()
    governance_reason = str(next_family.get("blocking_reason", "")).strip()

    checks: list[dict[str, str]] = []
    checks.append(
        {
            "name": "service heartbeats",
            "status": "ok" if not degraded_services else "error",
            "detail": (
                "Coordinator, campaign manager, and research director heartbeats are fresh."
                if not degraded_services
                else "Degraded services: "
                + ", ".join(
                    f"{record.get('service')} ({record.get('status')})"
                    for record in degraded_services
                )
                + "."
            ),
        }
    )
    checks.append(
        {
            "name": "worker pool",
            "status": "ok" if active_worker_count > 0 else "error",
            "detail": (
                f"{active_worker_count} workers active."
                if active_worker_count > 0
                else "No active workers are reporting. Research cannot progress."
            ),
        }
    )
    checks.append(
        {
            "name": "worker heartbeats",
            "status": "ok" if stale_worker_count == 0 else "warning",
            "detail": (
                "All worker heartbeats are fresh."
                if stale_worker_count == 0
                else f"{stale_worker_count} worker records have stale heartbeats older than 3 minutes."
            ),
        }
    )
    checks.append(
        {
            "name": "job activity",
            "status": "ok" if running > 0 or queued > 0 else "warning",
            "detail": (
                f"{running} running and {queued} queued jobs."
                if running > 0 or queued > 0
                else "No queued or running jobs. The system is waiting for the next campaign decision or is idle."
            ),
        }
    )
    checks.append(
        {
            "name": "campaign activity",
            "status": (
                "ok"
                if campaigns and (freshest_campaign_age is None or freshest_campaign_age <= 900)
                else "warning"
            ),
            "detail": (
                f"{len(campaigns)} active campaign(s); most recent update {format_age_seconds(freshest_campaign_age)}."
                if campaigns
                else "No active campaigns. The director may be idle, paused, or complete."
            ),
        }
    )
    checks.append(
        {
            "name": "director activity",
            "status": "ok" if active_director_count > 0 else "warning",
            "detail": (
                f"{active_director_count} active director(s)."
                if active_director_count > 0
                else (
                    f"No active directors. Most recent director {most_recent_director_name} "
                    f"{most_recent_director_status or 'finished'} {format_age_seconds(most_recent_director_age)}."
                    if isinstance(most_recent_director, dict)
                    else "No active directors. Start a director to submit the next campaign."
                )
            ),
        }
    )
    if governance_blocked:
        checks.append(
            {
                "name": "queue governance",
                "status": "warning",
                "detail": (
                    f"{governance_message} {governance_reason}".strip()
                    if governance_message or governance_reason
                    else "The supervisor queue is intentionally blocked pending research-family governance."
                ),
            }
        )
    if running > 0:
        checks.append(
            {
                "name": "running job freshness",
                "status": "ok" if stale_running_job_count == 0 else "warning",
                "detail": (
                    f"{stale_running_job_count} running job(s) have not updated for more than 15 minutes; oldest update {format_age_seconds(oldest_running_job_age)}."
                    if stale_running_job_count > 0
                    else "Running jobs are updating normally."
                ),
            }
        )

    overall = "healthy"
    summary = "Research runtime is healthy and actively progressing."
    if degraded_services:
        overall = "warning"
        summary = "Research runtime is degraded: one or more orchestration service heartbeats are stale."
    if active_worker_count == 0:
        overall = "critical"
        summary = "Research runtime is unhealthy: no workers are active."
    elif stale_running_job_count > 0:
        overall = "stalled"
        summary = "Research runtime looks stalled: jobs are marked running, but their progress signals are stale."
    elif stale_worker_count > 0 or oldest_running_job_age > 1800:
        overall = "warning"
        summary = "Research runtime is degraded: activity exists, but some signals look stale."
    elif running == 0 and queued == 0 and campaigns:
        overall = "warning"
        summary = "Research runtime is quiet: campaigns are active but no jobs are currently queued or running."
    elif director_requires_attention:
        overall = "warning"
        summary = (
            "Research runtime needs attention: no active directors remain after the latest director "
            f"{most_recent_director_status}."
        )
    elif governance_blocked and running == 0 and queued == 0 and not campaigns and not directors:
        overall = "blocked"
        summary = (
            f"Research runtime is intentionally blocked: {governance_message}"
            if governance_message
            else "Research runtime is intentionally blocked pending research-family governance."
        )
    elif running == 0 and queued == 0 and not campaigns and not directors:
        overall = "idle"
        summary = "Research runtime is idle: there is no active director, active campaign, or queued work."
    return {"status": overall, "summary": summary, "checks": checks}


def timestamp_sort_key(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).timestamp()


def format_age_seconds(delta_seconds: int | None) -> str:
    return format_age_label_from_seconds(delta_seconds) or "at an unknown time"


def format_age_label_from_seconds(delta_seconds: int | None) -> str | None:
    if delta_seconds is None:
        return None
    if delta_seconds < 60:
        return f"{delta_seconds}s ago"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m ago"
    if delta_seconds < 86400:
        return f"{delta_seconds // 3600}h ago"
    return f"{delta_seconds // 86400}d ago"


def age_seconds(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(int((_utc_now() - timestamp.astimezone(UTC)).total_seconds()), 0)


def _utc_now() -> datetime:
    return datetime.now(UTC)
