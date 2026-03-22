from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_SERVICE_ALLOWLIST = (
    "research-api",
    "coordinator",
    "campaign-manager",
    "research-director",
    "worker",
)

DEFAULT_AGENT_ALLOWLIST = (
    "research-triage",
    "candidate-review",
    "paper-trade-readiness",
    "failure-postmortem",
)


@dataclass(frozen=True)
class RunbookWorkItem:
    plan_id: str
    plan_file: str
    director_name: str
    enabled: bool
    priority: int
    fallback_to: str | None


@dataclass(frozen=True)
class RunbookLimits:
    max_same_item_recoveries: int = 2
    recovery_window_hours: int = 12
    max_service_restarts_per_service_15m: int = 1
    max_service_restarts_per_service_24h: int = 2


@dataclass(frozen=True)
class SupervisorRunbook:
    source_path: Path
    work_queue: tuple[RunbookWorkItem, ...]
    config_registry: dict[str, str]
    service_allowlist: tuple[str, ...]
    agent_allowlist: tuple[str, ...]
    limits: RunbookLimits


def load_supervisor_runbook(path: Path | str) -> SupervisorRunbook:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Supervisor runbook must contain a JSON object")

    raw_queue = payload.get("work_queue", [])
    if not isinstance(raw_queue, list) or not raw_queue:
        raise ValueError("Supervisor runbook requires a non-empty work_queue")
    work_queue: list[RunbookWorkItem] = []
    seen_plan_ids: set[str] = set()
    for index, entry in enumerate(raw_queue):
        if not isinstance(entry, dict):
            raise ValueError(f"Supervisor runbook work_queue[{index}] must be an object")
        plan_id = _required_text(entry.get("plan_id"), f"work_queue[{index}].plan_id")
        if plan_id in seen_plan_ids:
            raise ValueError(f"Duplicate runbook plan_id '{plan_id}'")
        seen_plan_ids.add(plan_id)
        work_queue.append(
            RunbookWorkItem(
                plan_id=plan_id,
                plan_file=_required_text(entry.get("plan_file"), f"work_queue[{index}].plan_file"),
                director_name=_required_text(
                    entry.get("director_name"),
                    f"work_queue[{index}].director_name",
                ),
                enabled=bool(entry.get("enabled", True)),
                priority=int(entry.get("priority", index + 1)),
                fallback_to=_optional_text(entry.get("fallback_to")),
            )
        )

    config_registry = _load_config_registry(payload.get("config_registry"))

    raw_services = payload.get("service_allowlist", list(DEFAULT_SERVICE_ALLOWLIST))
    if not isinstance(raw_services, list):
        raise ValueError("Supervisor runbook service_allowlist must be a list")
    service_allowlist = tuple(
        service.strip()
        for service in (str(entry) for entry in raw_services)
        if service.strip()
    )
    if not service_allowlist:
        raise ValueError("Supervisor runbook service_allowlist must not be empty")

    raw_agents = payload.get("agent_allowlist", list(DEFAULT_AGENT_ALLOWLIST))
    if not isinstance(raw_agents, list):
        raise ValueError("Supervisor runbook agent_allowlist must be a list")
    agent_allowlist = tuple(
        agent.strip()
        for agent in (str(entry) for entry in raw_agents)
        if agent.strip()
    )
    if not agent_allowlist:
        raise ValueError("Supervisor runbook agent_allowlist must not be empty")

    raw_limits = payload.get("limits", {})
    if raw_limits is None:
        raw_limits = {}
    if not isinstance(raw_limits, dict):
        raise ValueError("Supervisor runbook limits must be an object")
    limits = RunbookLimits(
        max_same_item_recoveries=int(raw_limits.get("max_same_item_recoveries", 2)),
        recovery_window_hours=int(raw_limits.get("recovery_window_hours", 12)),
        max_service_restarts_per_service_15m=int(raw_limits.get("max_service_restarts_per_service_15m", 1)),
        max_service_restarts_per_service_24h=int(raw_limits.get("max_service_restarts_per_service_24h", 2)),
    )

    for item in work_queue:
        if item.fallback_to and item.fallback_to not in seen_plan_ids:
            raise ValueError(f"Runbook fallback_to '{item.fallback_to}' does not match any plan_id")

    return SupervisorRunbook(
        source_path=source_path,
        work_queue=tuple(sorted(work_queue, key=lambda item: (item.priority, item.plan_id))),
        config_registry=config_registry,
        service_allowlist=service_allowlist,
        agent_allowlist=agent_allowlist,
        limits=limits,
    )


def resolve_runbook_plan(runbook: SupervisorRunbook, plan_id: str) -> RunbookWorkItem:
    normalized = plan_id.strip()
    for item in runbook.work_queue:
        if item.plan_id == normalized:
            return item
    raise ValueError(f"Unknown runbook plan_id '{plan_id}'")


def resolve_runbook_config(runbook: SupervisorRunbook, config_id: str) -> str:
    normalized = config_id.strip()
    resolved = runbook.config_registry.get(normalized)
    if not resolved:
        raise ValueError(f"Unknown runbook config_id '{config_id}'")
    return resolved


def _load_config_registry(value: object) -> dict[str, str]:
    if value is None or value == "":
        return {}
    if not isinstance(value, dict):
        raise ValueError("Supervisor runbook config_registry must be an object")
    registry: dict[str, str] = {}
    for key, raw_path in value.items():
        config_id = str(key).strip()
        if not config_id:
            continue
        config_path = _required_text(raw_path, f"config_registry.{config_id}")
        registry[config_id] = config_path
    return registry


def _required_text(value: object, label: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
