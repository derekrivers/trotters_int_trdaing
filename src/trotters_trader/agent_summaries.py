from __future__ import annotations

import json
from pathlib import Path

SUMMARY_TYPES = [
    "supervisor_incident_summary",
    "campaign_triage_summary",
    "candidate_readiness_summary",
    "paper_trade_readiness_summary",
    "failure_postmortem_summary",
]


def summary_root(catalog_output_dir: Path) -> Path:
    return catalog_output_dir / "agent_summaries"


def load_summary_records(catalog_output_dir: Path, *, summary_type: str | None = None, limit: int = 20) -> list[dict[str, object]]:
    root = summary_root(catalog_output_dir)
    index_path = root / "index.json"
    if not index_path.exists():
        return []
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    filtered = [
        record
        for record in records
        if isinstance(record, dict) and (summary_type is None or str(record.get("summary_type", "")) == summary_type)
    ]
    return filtered[: max(1, limit)]


def load_latest_summaries(catalog_output_dir: Path) -> dict[str, dict[str, object]]:
    latest_dir = summary_root(catalog_output_dir) / "latest"
    if not latest_dir.exists():
        return {}
    result: dict[str, dict[str, object]] = {}
    for summary_type in SUMMARY_TYPES:
        path = latest_dir / f"{summary_type}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            result[summary_type] = payload
    return result
