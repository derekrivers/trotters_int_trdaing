from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path

DEFAULT_SERVICE_HEARTBEAT_POLICIES: dict[str, dict[str, object]] = {
    "coordinator": {
        "service": "coordinator",
        "label": "Coordinator",
        "max_age_seconds": 30,
    },
    "campaign-manager": {
        "service": "campaign-manager",
        "label": "Campaign Manager",
        "max_age_seconds": 90,
    },
    "research-director": {
        "service": "research-director",
        "label": "Research Director",
        "max_age_seconds": 150,
    },
}


def write_service_heartbeat(
    runtime_root: Path | str,
    service: str,
    *,
    metadata: dict[str, object] | None = None,
    pid: int | None = None,
) -> dict[str, object]:
    record = {
        "service": service,
        "recorded_at_utc": _utcnow(),
        "pid": int(os.getpid() if pid is None else pid),
    }
    if isinstance(metadata, dict):
        record.update(metadata)
    heartbeat_path(runtime_root, service).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def load_service_heartbeats(
    runtime_root: Path | str,
    *,
    policies: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    definitions = policies or DEFAULT_SERVICE_HEARTBEAT_POLICIES
    now = datetime.now(UTC)
    for service, policy in definitions.items():
        heartbeat_file = heartbeat_path(runtime_root, service)
        payload = _load_payload(heartbeat_file)
        recorded_at = str(payload.get("recorded_at_utc", "") or "").strip() if payload else ""
        age_seconds = _age_seconds(recorded_at, now=now)
        max_age_seconds = int(policy.get("max_age_seconds", 60) or 60)
        status = "ok"
        detail = "Heartbeat is fresh."
        if not payload:
            status = "missing"
            detail = "No heartbeat file recorded yet."
        elif age_seconds is None:
            status = "stale"
            detail = "Heartbeat timestamp is unreadable."
        elif age_seconds > max_age_seconds:
            status = "stale"
            detail = f"Heartbeat is {age_seconds}s old; expected <= {max_age_seconds}s."
        records.append(
            {
                "service": service,
                "label": str(policy.get("label", service)),
                "recorded_at_utc": recorded_at or None,
                "pid": payload.get("pid") if payload else None,
                "path": str(heartbeat_file),
                "age_seconds": age_seconds,
                "max_age_seconds": max_age_seconds,
                "status": status,
                "detail": detail,
                "metadata": payload if payload else {},
            }
        )
    return records


def check_service_heartbeat(
    runtime_root: Path | str,
    service: str,
    *,
    max_age_seconds: int | None = None,
) -> dict[str, object]:
    definitions = dict(DEFAULT_SERVICE_HEARTBEAT_POLICIES)
    if service not in definitions:
        definitions[service] = {
            "service": service,
            "label": service,
            "max_age_seconds": int(max_age_seconds or 60),
        }
    elif max_age_seconds is not None:
        definitions[service] = {
            **definitions[service],
            "max_age_seconds": int(max_age_seconds),
        }
    record = next(
        item for item in load_service_heartbeats(runtime_root, policies={service: definitions[service]})
        if str(item.get("service")) == service
    )
    if str(record.get("status", "")) != "ok":
        raise ValueError(f"Service heartbeat check failed for {service}: {record.get('detail', 'heartbeat missing')}")
    return record


def heartbeat_path(runtime_root: Path | str, service: str) -> Path:
    directory = Path(runtime_root) / "exports" / "service_heartbeats"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{service}.json"


def _load_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _age_seconds(value: str, *, now: datetime) -> int | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(int((now - timestamp.astimezone(UTC)).total_seconds()), 0)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
