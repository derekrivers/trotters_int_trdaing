from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path


def dispatch_root(catalog_output_dir: Path) -> Path:
    return catalog_output_dir / "agent_telemetry"


def append_dispatch_record(catalog_output_dir: Path, record: dict[str, object]) -> dict[str, object]:
    root = dispatch_root(catalog_output_dir)
    root.mkdir(parents=True, exist_ok=True)
    dispatches_path = root / "dispatches.jsonl"
    with dispatches_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str))
        handle.write("\n")
    return record


def load_dispatch_records(
    catalog_output_dir: Path,
    *,
    agent_id: str | None = None,
    event_type: str | None = None,
    success: bool | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    path = dispatch_root(catalog_output_dir) / "dispatches.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if agent_id and str(payload.get("agent_id", "")) != agent_id:
            continue
        if event_type and str(payload.get("event_type", "")) != event_type:
            continue
        if success is not None and bool(payload.get("success")) is not success:
            continue
        records.append(payload)
    records.sort(key=lambda record: _timestamp_sort_key(record.get("recorded_at_utc")), reverse=True)
    return records[: max(1, limit)]


def load_dispatch_summary(catalog_output_dir: Path, *, limit: int = 100) -> dict[str, object]:
    records = load_dispatch_records(catalog_output_dir, limit=max(1, limit))
    totals = {
        "runs": len(records),
        "successes": sum(1 for record in records if bool(record.get("success"))),
        "failures": sum(1 for record in records if record.get("success") is False),
        "suppressed": sum(1 for record in records if bool(record.get("suppressed"))),
        "duration_ms": sum(_int_value(record.get("duration_ms")) for record in records),
        "prompt_tokens": sum(_int_value(record.get("prompt_tokens")) for record in records),
        "input_tokens": sum(_int_value(record.get("input_tokens")) for record in records),
        "output_tokens": sum(_int_value(record.get("output_tokens")) for record in records),
        "cache_read_tokens": sum(_int_value(record.get("cache_read_tokens")) for record in records),
        "cache_write_tokens": sum(_int_value(record.get("cache_write_tokens")) for record in records),
        "total_tokens": sum(_int_value(record.get("total_tokens")) for record in records),
    }
    by_agent: dict[str, dict[str, object]] = {}
    for record in records:
        agent_key = str(record.get("agent_id", "unknown") or "unknown")
        bucket = by_agent.setdefault(
            agent_key,
            {
                "agent_id": agent_key,
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "suppressed": 0,
                "duration_ms": 0,
                "total_tokens": 0,
                "latest_recorded_at_utc": None,
                "latest_model": None,
            },
        )
        bucket["runs"] = int(bucket["runs"]) + 1
        if bool(record.get("success")):
            bucket["successes"] = int(bucket["successes"]) + 1
        if record.get("success") is False:
            bucket["failures"] = int(bucket["failures"]) + 1
        if bool(record.get("suppressed")):
            bucket["suppressed"] = int(bucket["suppressed"]) + 1
        bucket["duration_ms"] = int(bucket["duration_ms"]) + _int_value(record.get("duration_ms"))
        bucket["total_tokens"] = int(bucket["total_tokens"]) + _int_value(record.get("total_tokens"))
        recorded_at = str(record.get("recorded_at_utc", "") or "").strip() or None
        if recorded_at and _timestamp_sort_key(recorded_at) >= _timestamp_sort_key(bucket.get("latest_recorded_at_utc")):
            bucket["latest_recorded_at_utc"] = recorded_at
            bucket["latest_model"] = str(record.get("model", "") or "") or None
    ranked_agents = sorted(
        by_agent.values(),
        key=lambda record: (_int_value(record.get("total_tokens")), _timestamp_sort_key(record.get("latest_recorded_at_utc"))),
        reverse=True,
    )
    return {
        "totals": totals,
        "by_agent": ranked_agents,
        "recent_dispatches": records[: min(10, len(records))],
    }


def has_recent_successful_dispatch(
    catalog_output_dir: Path,
    *,
    fingerprint: str,
    cooldown_seconds: int,
) -> bool:
    if not fingerprint.strip() or cooldown_seconds <= 0:
        return False
    now = datetime.now(UTC)
    for record in load_dispatch_records(catalog_output_dir, limit=500):
        if str(record.get("fingerprint", "")) != fingerprint:
            continue
        if not bool(record.get("success")):
            continue
        recorded_at = _parse_timestamp(record.get("recorded_at_utc"))
        if recorded_at is None:
            continue
        if (now - recorded_at).total_seconds() <= cooldown_seconds:
            return True
    return False


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp_sort_key(value: object) -> float:
    parsed = _parse_timestamp(value)
    return parsed.timestamp() if parsed is not None else 0.0


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
