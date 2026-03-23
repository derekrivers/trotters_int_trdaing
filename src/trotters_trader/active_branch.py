from __future__ import annotations

from datetime import UTC, datetime


def build_active_branch_summary(
    *,
    active_directors: list[dict[str, object]],
    active_campaigns: list[dict[str, object]],
) -> dict[str, object]:
    directors = [dict(item) for item in active_directors if isinstance(item, dict)]
    campaigns = [dict(item) for item in active_campaigns if isinstance(item, dict)]
    if not directors and not campaigns:
        return {
            "status": "idle",
            "message": "No active research branch is running right now.",
            "recommended_action": "wait_for_next_branch",
            "director": None,
            "campaign": None,
            "job_counts": {},
            "stage": {},
            "warnings": [],
        }

    primary_director = _select_primary_director(directors)
    primary_campaign = _select_primary_campaign(primary_director, campaigns)
    warnings = _active_branch_warnings(primary_director, campaigns)
    stage = _stage_summary(primary_campaign)
    job_counts = stage.get("job_counts", {}) if isinstance(stage.get("job_counts"), dict) else {}
    return {
        "status": "active",
        "message": _active_branch_message(primary_director, primary_campaign, stage, warnings),
        "recommended_action": _recommended_action(primary_campaign, stage, warnings),
        "director": _director_summary(primary_director),
        "campaign": _campaign_summary(primary_campaign),
        "job_counts": job_counts,
        "stage": stage,
        "warnings": warnings,
        "active_director_count": len(directors),
        "active_campaign_count": len(campaigns),
    }


def _select_primary_director(directors: list[dict[str, object]]) -> dict[str, object]:
    if not directors:
        return {}
    ranked = sorted(
        directors,
        key=lambda director: (
            1 if str(director.get("status", "")).lower() == "running" else 0,
            str(director.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return ranked[0]


def _select_primary_campaign(primary_director: dict[str, object], campaigns: list[dict[str, object]]) -> dict[str, object]:
    if not campaigns:
        return {}
    current_campaign_id = str(primary_director.get("current_campaign_id") or "").strip()
    if current_campaign_id:
        for campaign in campaigns:
            if str(campaign.get("campaign_id") or "").strip() == current_campaign_id:
                return campaign
    ranked = sorted(
        campaigns,
        key=lambda campaign: (
            1 if str(campaign.get("status", "")).lower() == "running" else 0,
            str(campaign.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return ranked[0]


def _active_branch_warnings(primary_director: dict[str, object], campaigns: list[dict[str, object]]) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    if not primary_director:
        return warnings
    director_id = str(primary_director.get("director_id") or "").strip()
    if not director_id:
        return warnings
    director_campaigns = [
        campaign for campaign in campaigns
        if str(campaign.get("director_id") or "").strip() == director_id
    ]
    if len(director_campaigns) > 1:
        warnings.append(
            {
                "code": "duplicate_active_campaigns",
                "message": f"Director has {len(director_campaigns)} active campaigns; expected one.",
                "campaign_ids": [str(campaign.get("campaign_id") or "") for campaign in director_campaigns],
            }
        )
    current_campaign_id = str(primary_director.get("current_campaign_id") or "").strip()
    if current_campaign_id and all(str(campaign.get("campaign_id") or "").strip() != current_campaign_id for campaign in director_campaigns):
        warnings.append(
            {
                "code": "director_campaign_mismatch",
                "message": "Director current_campaign_id does not match any active campaign detail.",
                "current_campaign_id": current_campaign_id,
            }
        )
    return warnings


def _stage_summary(campaign: dict[str, object]) -> dict[str, object]:
    if not campaign:
        return {}
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    pending_stage = state.get("pending_stage", {}) if isinstance(state.get("pending_stage"), dict) else {}
    jobs = [dict(job) for job in campaign.get("jobs", []) if isinstance(job, dict)] if isinstance(campaign.get("jobs"), list) else []
    counts = _job_counts(jobs)
    stage_label = str(pending_stage.get("phase") or campaign.get("phase") or "unknown")
    return {
        "phase": str(campaign.get("phase", "unknown")),
        "pending_phase": stage_label,
        "pending_stage_id": pending_stage.get("stage_id"),
        "job_counts": counts,
        "latest_report_path": campaign.get("latest_report_path"),
        "updated_at": campaign.get("updated_at"),
        "last_event": _last_event_label(campaign),
    }


def _job_counts(jobs: list[dict[str, object]]) -> dict[str, int]:
    counts = {
        "total": len(jobs),
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for job in jobs:
        status = str(job.get("status", "")).lower()
        if status in counts:
            counts[status] += 1
    return counts


def _last_event_label(campaign: dict[str, object]) -> str | None:
    events = [dict(event) for event in campaign.get("events", []) if isinstance(event, dict)] if isinstance(campaign.get("events"), list) else []
    if not events:
        return None
    latest = max(
        events,
        key=lambda event: str(event.get("recorded_at_utc") or ""),
    )
    return str(latest.get("event_type") or latest.get("message") or "").strip() or None


def _active_branch_message(
    primary_director: dict[str, object],
    primary_campaign: dict[str, object],
    stage: dict[str, object],
    warnings: list[dict[str, object]],
) -> str:
    if warnings:
        return str(warnings[0].get("message") or "Active branch state needs operator attention.")
    director_name = str(primary_director.get("director_name") or primary_director.get("director_id") or "unknown director")
    campaign_name = str(primary_campaign.get("campaign_name") or primary_campaign.get("campaign_id") or "unknown campaign")
    phase = str(stage.get("phase") or primary_campaign.get("phase") or "unknown")
    job_counts = stage.get("job_counts", {}) if isinstance(stage.get("job_counts"), dict) else {}
    running = int(job_counts.get("running", 0) or 0)
    queued = int(job_counts.get("queued", 0) or 0)
    completed = int(job_counts.get("completed", 0) or 0)
    return (
        f"{director_name} is running {campaign_name} in {phase}. "
        f"{running} stage jobs are running, {queued} queued, and {completed} completed."
    )


def _recommended_action(
    primary_campaign: dict[str, object],
    stage: dict[str, object],
    warnings: list[dict[str, object]],
) -> str:
    if warnings:
        return "inspect_active_branch"
    status = str(primary_campaign.get("status", "")).lower()
    job_counts = stage.get("job_counts", {}) if isinstance(stage.get("job_counts"), dict) else {}
    if status in {"queued", "running"} and int(job_counts.get("queued", 0) or 0) > 0:
        return "wait_for_stage_jobs"
    if status in {"queued", "running"} and int(job_counts.get("running", 0) or 0) > 0:
        return "monitor_stage_progress"
    if status in {"queued", "running"}:
        return "await_next_campaign_step"
    return "inspect_active_branch"


def _director_summary(director: dict[str, object]) -> dict[str, object] | None:
    if not director:
        return None
    state = director.get("state", {}) if isinstance(director.get("state"), dict) else {}
    launch = state.get("launch_in_progress", {}) if isinstance(state.get("launch_in_progress"), dict) else {}
    return {
        "director_id": director.get("director_id"),
        "director_name": director.get("director_name"),
        "status": director.get("status"),
        "plan_name": state.get("plan_name") or director.get("plan_name"),
        "plan_source": state.get("plan_source"),
        "current_campaign_id": director.get("current_campaign_id"),
        "launch_in_progress": {
            "queue_index": launch.get("queue_index"),
            "config_path": launch.get("config_path"),
            "claimed_at": launch.get("claimed_at"),
        } if launch else None,
    }


def _campaign_summary(campaign: dict[str, object]) -> dict[str, object] | None:
    if not campaign:
        return None
    return {
        "campaign_id": campaign.get("campaign_id"),
        "campaign_name": campaign.get("campaign_name"),
        "status": campaign.get("status"),
        "phase": campaign.get("phase"),
        "config_path": campaign.get("config_path"),
        "latest_report_path": campaign.get("latest_report_path"),
        "updated_at": campaign.get("updated_at"),
    }


def launch_claim_is_stale(claimed_at: object, *, max_age_seconds: int = 120) -> bool:
    if not isinstance(claimed_at, str) or not claimed_at.strip():
        return True
    try:
        timestamp = datetime.fromisoformat(claimed_at)
    except ValueError:
        return True
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    age_seconds = (datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()
    return age_seconds > max_age_seconds
