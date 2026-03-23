from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import uuid

from trotters_trader.research_programs import write_research_program_artifacts

RESEARCH_FAMILY_SCHEMA_VERSION = 1
RESEARCH_FAMILY_STATUS_ORDER = {
    "active": 7,
    "queued": 6,
    "approved": 5,
    "under_review": 4,
    "proposed": 3,
    "retired": 2,
    "rejected": 1,
}
RESEARCH_FAMILY_ALLOWED_APPROVALS = {
    "proposed",
    "under_review",
    "approved",
    "queued",
    "active",
    "retired",
    "rejected",
}


def build_research_family_comparison_summary(
    *,
    catalog_output_dir: Path,
    research_program_portfolio: dict[str, object] | None = None,
) -> dict[str, object]:
    proposals = load_research_family_proposals()
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
    runbook = _load_runbook()
    queue_entries = [
        dict(entry)
        for entry in runbook.get("work_queue", [])
        if isinstance(entry, dict)
    ] if isinstance(runbook.get("work_queue"), list) else []
    queue_by_plan_id = {
        str(entry.get("plan_id", "")).strip(): entry
        for entry in queue_entries
        if str(entry.get("plan_id", "")).strip()
    }

    families: list[dict[str, object]] = []
    for proposal in proposals:
        bootstrap = proposal.get("bootstrap", {}) if isinstance(proposal.get("bootstrap"), dict) else {}
        plan_id = str(bootstrap.get("plan_id", "") or proposal.get("plan_id", "") or "").strip()
        program_id = str(bootstrap.get("program_id", "") or proposal.get("program_id", "") or "").strip()
        queue_entry = queue_by_plan_id.get(plan_id)
        program = programs_by_plan_id.get(plan_id)
        approval_status = str(proposal.get("approval_status", "proposed") or "proposed").strip()
        family_status = _research_family_status(
            approval_status=approval_status,
            queue_entry=queue_entry,
            program=program,
        )
        program_status = str(program.get("status", "") or "") if isinstance(program, dict) else ""
        bootstrap_materialized = _bootstrap_materialized(bootstrap, queue_entry)
        record = {
            "proposal_id": str(proposal.get("proposal_id", proposal.get("title", "family-proposal"))),
            "title": str(proposal.get("title", "Research Family Proposal")),
            "strategy_family": str(proposal.get("strategy_family", "unknown")),
            "hypothesis": str(proposal.get("hypothesis", "")),
            "why_different_from_retired": [
                str(item)
                for item in proposal.get("why_different_from_retired", [])
                if str(item).strip()
            ] if isinstance(proposal.get("why_different_from_retired"), list) else [],
            "success_criteria": [
                str(item)
                for item in proposal.get("success_criteria", [])
                if str(item).strip()
            ] if isinstance(proposal.get("success_criteria"), list) else [],
            "stop_conditions": [
                item
                for item in proposal.get("stop_conditions", [])
                if isinstance(item, dict)
            ] if isinstance(proposal.get("stop_conditions"), list) else [],
            "approval_status": approval_status,
            "family_status": family_status,
            "plan_id": plan_id,
            "program_id": program_id,
            "program_title": str(program.get("title", "") or "") if isinstance(program, dict) else "",
            "program_status": program_status,
            "program_summary_path": str(program.get("summary_path", "") or "") if isinstance(program, dict) else "",
            "queue_enabled": bool(queue_entry.get("enabled", False)) if isinstance(queue_entry, dict) else False,
            "queue_priority": int(queue_entry.get("priority", 0) or 0) if isinstance(queue_entry, dict) else None,
            "queue_director_name": str(queue_entry.get("director_name", "") or "") if isinstance(queue_entry, dict) else "",
            "novelty_vs_retired": str(proposal.get("novelty_vs_retired", "unknown") or "unknown"),
            "implementation_readiness": str(proposal.get("implementation_readiness", "planned") or "planned"),
            "expected_evidence_cost": str(proposal.get("expected_evidence_cost", "unknown") or "unknown"),
            "promotion_path_compatibility": str(proposal.get("promotion_path_compatibility", "unknown") or "unknown"),
            "operator_recommendation": _family_operator_recommendation(
                approval_status=approval_status,
                family_status=family_status,
                bootstrap_materialized=bootstrap_materialized,
                queue_entry=queue_entry,
            ),
            "blocking_reason": _family_blocking_reason(
                approval_status=approval_status,
                family_status=family_status,
                bootstrap_materialized=bootstrap_materialized,
                program=program,
            ),
            "bootstrap_ready": approval_status == "approved",
            "bootstrap_materialized": bootstrap_materialized,
            "proposal_path": str(proposal.get("_proposal_path", "")),
            "recorded_at_utc": str(proposal.get("recorded_at_utc", "") or ""),
        }
        families.append(record)

    families.sort(key=_family_sort_key, reverse=True)
    current_proposal = _current_research_family(families)
    next_approved = next(
        (
            family
            for family in families
            if str(family.get("family_status", "")) in {"queued", "approved", "active"}
        ),
        None,
    )
    summary = {
        "schema_version": RESEARCH_FAMILY_SCHEMA_VERSION,
        "summary_type": "research_family_comparison_summary",
        "recorded_at_utc": _utcnow(),
        "status": "available" if families else "missing",
        "families": families,
        "current_proposal": current_proposal,
        "next_approved_family": next_approved,
        "counts": {
            "total": len(families),
            "proposed": sum(1 for family in families if str(family.get("family_status", "")) == "proposed"),
            "under_review": sum(1 for family in families if str(family.get("family_status", "")) == "under_review"),
            "approved": sum(1 for family in families if str(family.get("family_status", "")) == "approved"),
            "queued": sum(1 for family in families if str(family.get("family_status", "")) == "queued"),
            "active": sum(1 for family in families if str(family.get("family_status", "")) == "active"),
            "retired": sum(1 for family in families if str(family.get("family_status", "")) == "retired"),
            "rejected": sum(1 for family in families if str(family.get("family_status", "")) == "rejected"),
        },
    }
    _write_summary(catalog_output_dir, "research_family_comparison_summary", summary)
    return summary


def build_next_family_status(
    *,
    catalog_output_dir: Path,
    runbook_queue_summary: dict[str, object] | None,
    research_family_comparison_summary: dict[str, object] | None,
    active_branch_summary: dict[str, object] | None,
) -> dict[str, object]:
    queue_summary = runbook_queue_summary if isinstance(runbook_queue_summary, dict) else {}
    family_summary = research_family_comparison_summary if isinstance(research_family_comparison_summary, dict) else {}
    active_branch = active_branch_summary if isinstance(active_branch_summary, dict) else {}
    director = active_branch.get("director", {}) if isinstance(active_branch.get("director"), dict) else {}
    current_family = family_summary.get("current_proposal", {}) if isinstance(family_summary.get("current_proposal"), dict) else {}
    next_family = family_summary.get("next_approved_family", {}) if isinstance(family_summary.get("next_approved_family"), dict) else {}
    active_plan_id = str(queue_summary.get("active_plan_id", "") or str(director.get("plan_name", "") or "")).strip()
    next_runnable_plan_id = str(queue_summary.get("next_runnable_plan_id", "") or "").strip()

    status = "blocked_pending_approval"
    recommended_action = "define_next_research_family"
    message = "No approved runnable family remains in the supervisor queue."
    blocking_reason = "No approved research family proposal exists yet."

    if active_plan_id:
        status = "active"
        recommended_action = "monitor_active_plan"
        message = f"Active research family '{active_plan_id}' is currently running."
        blocking_reason = ""
    elif next_runnable_plan_id:
        status = "queued"
        recommended_action = "start_approved_family"
        message = f"Approved family '{next_runnable_plan_id}' is queued and ready for controlled resumption."
        blocking_reason = ""
    elif current_family:
        family_status = str(current_family.get("family_status", "") or "")
        operator_recommendation = str(current_family.get("operator_recommendation", "") or "")
        blocking_reason = str(current_family.get("blocking_reason", "") or "")
        if family_status == "approved":
            status = "blocked_pending_bootstrap"
            recommended_action = "bootstrap_approved_family"
            message = f"Approved family '{current_family.get('plan_id', current_family.get('proposal_id', 'proposal'))}' still needs bootstrap before it can re-enter the queue."
        elif family_status in {"proposed", "under_review"}:
            status = "blocked_pending_approval"
            recommended_action = "approve_research_family"
            message = f"Current family proposal '{current_family.get('proposal_id', 'proposal')}' is not approved yet."
        elif family_status == "queued":
            status = "queued"
            recommended_action = "start_approved_family"
            message = f"Approved family '{current_family.get('plan_id', current_family.get('proposal_id', 'proposal'))}' is queued and ready for resumption."
            blocking_reason = ""
        elif family_status == "rejected":
            status = "blocked_pending_approval"
            recommended_action = "define_next_research_family"
            message = f"Current family proposal '{current_family.get('proposal_id', 'proposal')}' was rejected."
        elif family_status == "retired":
            status = "blocked_pending_approval"
            recommended_action = "define_next_research_family"
            message = f"Current family proposal '{current_family.get('proposal_id', 'proposal')}' is retired and cannot re-enter the queue."
        if operator_recommendation and status.startswith("blocked"):
            recommended_action = operator_recommendation
    elif next_family:
        status = "blocked_pending_bootstrap"
        recommended_action = "bootstrap_approved_family"
        message = f"Approved family '{next_family.get('plan_id', next_family.get('proposal_id', 'proposal'))}' exists but is not yet runnable."
        blocking_reason = str(next_family.get("blocking_reason", "") or "")

    summary = {
        "schema_version": RESEARCH_FAMILY_SCHEMA_VERSION,
        "summary_type": "next_family_status",
        "recorded_at_utc": _utcnow(),
        "status": status,
        "recommended_action": recommended_action,
        "message": message,
        "blocking_reason": blocking_reason,
        "active_plan_id": active_plan_id or None,
        "next_runnable_plan_id": next_runnable_plan_id or None,
        "current_proposal": current_family,
        "next_approved_family": next_family,
    }
    _write_summary(catalog_output_dir, "next_family_status", summary)
    return summary


def current_research_family_proposal(*, catalog_output_dir: Path) -> dict[str, object]:
    summary = build_research_family_comparison_summary(catalog_output_dir=catalog_output_dir)
    proposal = summary.get("current_proposal")
    return proposal if isinstance(proposal, dict) else {}


def bootstrap_research_family(
    *,
    proposal_id: str,
    catalog_output_dir: Path,
    enable_queue: bool = True,
) -> dict[str, object]:
    proposal = load_research_family_proposal(proposal_id)
    approval_status = str(proposal.get("approval_status", "proposed") or "proposed")
    if approval_status != "approved":
        raise ValueError(f"Research family proposal '{proposal_id}' is not approved")
    bootstrap = proposal.get("bootstrap", {}) if isinstance(proposal.get("bootstrap"), dict) else {}
    plan_id = str(bootstrap.get("plan_id", "") or proposal_id).strip()
    if not plan_id:
        raise ValueError(f"Research family proposal '{proposal_id}' must define bootstrap.plan_id")
    plan_path = _repo_root() / "configs" / "directors" / f"{plan_id}.json"
    program_path = _repo_root() / "configs" / "research_programs" / f"{plan_id}.json"

    director_payload = {
        "plan_name": plan_id,
        "campaigns": [
            {
                "campaign_name": str(bootstrap.get("campaign_name", f"{plan_id}-primary")),
                "config_path": str(bootstrap.get("config_path", "")),
                "campaign_max_hours": int(bootstrap.get("campaign_max_hours", 24) or 24),
                "campaign_max_jobs": int(bootstrap.get("campaign_max_jobs", 1500) or 1500),
                "stage_candidate_limit": int(bootstrap.get("stage_candidate_limit", 36) or 36),
                "shortlist_size": int(bootstrap.get("shortlist_size", 3) or 3),
                "quality_gate": str(bootstrap.get("quality_gate", "pass_warn") or "pass_warn"),
            }
        ],
    }
    program_payload = {
        "program_id": str(bootstrap.get("program_id", f"{plan_id}_program")),
        "title": str(bootstrap.get("program_title", proposal.get("title", "Research Program"))),
        "strategy_family": str(proposal.get("strategy_family", "unknown")),
        "objective": str(bootstrap.get("objective", proposal.get("hypothesis", ""))),
        "branch_rationale": str(bootstrap.get("branch_rationale", proposal.get("hypothesis", ""))),
        "positive_hypotheses": [
            str(item)
            for item in bootstrap.get("positive_hypotheses", [])
            if str(item).strip()
        ] if isinstance(bootstrap.get("positive_hypotheses"), list) else [],
        "seed_stack": [
            item
            for item in bootstrap.get("seed_stack", [])
            if isinstance(item, dict)
        ] if isinstance(bootstrap.get("seed_stack"), list) else [],
        "campaign_path": [
            item
            for item in bootstrap.get("campaign_path", [])
            if isinstance(item, dict)
        ] if isinstance(bootstrap.get("campaign_path"), list) else [],
        "artifact_expectations": [
            item
            for item in bootstrap.get("artifact_expectations", [])
            if isinstance(item, dict)
        ] if isinstance(bootstrap.get("artifact_expectations"), list) else [],
        "stop_conditions": [
            item
            for item in proposal.get("stop_conditions", [])
            if isinstance(item, dict)
        ] if isinstance(proposal.get("stop_conditions"), list) else [],
    }

    _write_json(plan_path, director_payload)
    _write_json(program_path, program_payload)
    updated_runbook = _update_runbook_entry(
        plan_id=plan_id,
        plan_file=f"configs/directors/{plan_id}.json",
        director_name=str(bootstrap.get("director_name", f"{plan_id}-director")),
        enabled=enable_queue,
        priority=int(bootstrap.get("queue_priority", _next_runbook_priority()) or _next_runbook_priority()),
    )
    artifacts = write_research_program_artifacts(
        output_dir=catalog_output_dir,
        definition=program_payload,
    )
    return {
        "proposal_id": proposal_id,
        "plan_id": plan_id,
        "program_id": str(program_payload.get("program_id", "")),
        "artifacts": artifacts.get("artifacts", {}),
        "director_plan_file": str(plan_path),
        "research_program_file": str(program_path),
        "runbook_path": str(_runbook_path()),
        "runbook": updated_runbook,
    }


def load_research_family_proposals() -> list[dict[str, object]]:
    proposals: list[dict[str, object]] = []
    for path in sorted(_proposal_dir().glob("*.json")):
        proposals.append(load_research_family_proposal_definition(path))
    return proposals


def load_research_family_proposal(proposal_id: str) -> dict[str, object]:
    for proposal in load_research_family_proposals():
        if str(proposal.get("proposal_id", "")) == proposal_id:
            return proposal
    raise ValueError(f"Unknown research family proposal '{proposal_id}'")


def load_research_family_proposal_definition(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Research family proposal '{path}' must contain a JSON object")
    required = [
        "proposal_id",
        "title",
        "strategy_family",
        "hypothesis",
        "why_different_from_retired",
        "success_criteria",
        "stop_conditions",
        "approval_status",
    ]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"Research family proposal '{path}' is missing required fields: {', '.join(missing)}")
    approval_status = str(payload.get("approval_status", "") or "")
    if approval_status not in RESEARCH_FAMILY_ALLOWED_APPROVALS:
        raise ValueError(f"Research family proposal '{path}' has unsupported approval_status '{approval_status}'")
    if not isinstance(payload.get("why_different_from_retired"), list) or not payload.get("why_different_from_retired"):
        raise ValueError(f"Research family proposal '{path}' must explain why it differs from retired work")
    if not isinstance(payload.get("stop_conditions"), list) or not payload.get("stop_conditions"):
        raise ValueError(f"Research family proposal '{path}' must define stop_conditions")
    normalized = dict(payload)
    normalized["_proposal_path"] = str(path)
    return normalized


def _current_research_family(families: list[dict[str, object]]) -> dict[str, object] | None:
    return families[0] if families else None


def _family_sort_key(record: dict[str, object]) -> tuple[int, int, str]:
    family_status = str(record.get("family_status", "proposed"))
    approval_status = str(record.get("approval_status", "proposed"))
    queue_rank = 1 if bool(record.get("queue_enabled", False)) else 0
    rank = RESEARCH_FAMILY_STATUS_ORDER.get(family_status, RESEARCH_FAMILY_STATUS_ORDER.get(approval_status, 0))
    return (rank, queue_rank, str(record.get("proposal_id", "")))


def _research_family_status(
    *,
    approval_status: str,
    queue_entry: dict[str, object] | None,
    program: dict[str, object] | None,
) -> str:
    if isinstance(program, dict):
        program_status = str(program.get("status", "") or "")
        if program_status == "retired":
            return "retired"
    if isinstance(queue_entry, dict) and bool(queue_entry.get("enabled", False)) and approval_status == "approved":
        return "queued"
    if approval_status in RESEARCH_FAMILY_ALLOWED_APPROVALS:
        return approval_status
    return "proposed"


def _family_operator_recommendation(
    *,
    approval_status: str,
    family_status: str,
    bootstrap_materialized: bool,
    queue_entry: dict[str, object] | None,
) -> str:
    if family_status == "active":
        return "monitor_active_plan"
    if family_status == "queued":
        return "start_approved_family"
    if approval_status == "approved" and not bootstrap_materialized:
        return "bootstrap_approved_family"
    if approval_status == "approved" and not isinstance(queue_entry, dict):
        return "queue_approved_family"
    if approval_status == "under_review":
        return "approve_research_family"
    if approval_status == "rejected":
        return "define_next_research_family"
    if family_status == "retired":
        return "define_next_research_family"
    return "approve_research_family"


def _family_blocking_reason(
    *,
    approval_status: str,
    family_status: str,
    bootstrap_materialized: bool,
    program: dict[str, object] | None,
) -> str:
    if family_status == "retired":
        return str(program.get("decision_summary", "") or "This family is retired and cannot re-enter the queue.") if isinstance(program, dict) else "This family is retired and cannot re-enter the queue."
    if approval_status in {"proposed", "under_review"}:
        return "This family still needs explicit approval before it can re-enter the supervisor queue."
    if approval_status == "rejected":
        return "This family was rejected and cannot enter the supervisor queue."
    if approval_status == "approved" and not bootstrap_materialized:
        return "This family is approved, but its runnable program and director plan have not been materialized yet."
    return ""


def _bootstrap_materialized(bootstrap: dict[str, object], queue_entry: dict[str, object] | None) -> bool:
    plan_id = str(bootstrap.get("plan_id", "") or "").strip()
    if not plan_id:
        return False
    plan_path = _repo_root() / "configs" / "directors" / f"{plan_id}.json"
    program_path = _repo_root() / "configs" / "research_programs" / f"{plan_id}.json"
    return plan_path.exists() and program_path.exists() and isinstance(queue_entry, dict)


def _proposal_dir() -> Path:
    return _repo_root() / "configs" / "research_family_proposals"


def _runbook_path() -> Path:
    return _repo_root() / "configs" / "openclaw" / "trotters-runbook.json"


def _repo_root() -> Path:
    return Path.cwd()


def _load_runbook() -> dict[str, object]:
    path = _runbook_path()
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _update_runbook_entry(
    *,
    plan_id: str,
    plan_file: str,
    director_name: str,
    enabled: bool,
    priority: int,
) -> dict[str, object]:
    runbook = _load_runbook()
    queue = [
        dict(entry)
        for entry in runbook.get("work_queue", [])
        if isinstance(entry, dict)
    ] if isinstance(runbook.get("work_queue"), list) else []
    existing = next((entry for entry in queue if str(entry.get("plan_id", "")).strip() == plan_id), None)
    if existing is None:
        queue.append(
            {
                "plan_id": plan_id,
                "plan_file": plan_file,
                "director_name": director_name,
                "enabled": enabled,
                "priority": priority,
            }
        )
    else:
        existing.update(
            {
                "plan_file": plan_file,
                "director_name": director_name,
                "enabled": enabled,
                "priority": priority,
            }
        )
    queue.sort(key=lambda entry: int(entry.get("priority", 999) or 999))
    runbook["work_queue"] = queue
    _write_json(_runbook_path(), runbook)
    return runbook


def _next_runbook_priority() -> int:
    runbook = _load_runbook()
    queue = [
        dict(entry)
        for entry in runbook.get("work_queue", [])
        if isinstance(entry, dict)
    ] if isinstance(runbook.get("work_queue"), list) else []
    if not queue:
        return 1
    return max(int(entry.get("priority", 0) or 0) for entry in queue) + 1


def _write_summary(catalog_output_dir: Path, summary_type: str, payload: dict[str, object]) -> None:
    root = Path(catalog_output_dir) / "promotion_path"
    latest_dir = root / "latest"
    archive_dir = root / summary_type
    latest_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_dir / f"{summary_type}.json"
    snapshot_path = archive_dir / f"{_timestamp_slug(_utcnow())}__{uuid.uuid4().hex}.json"
    _write_json(latest_path, payload)
    _write_json(snapshot_path, payload)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".tmp-{uuid.uuid4().hex}.json"
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _timestamp_slug(value: str) -> str:
    return value.replace(":", "").replace("+00:00", "Z")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
