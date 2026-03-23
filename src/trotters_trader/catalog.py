from __future__ import annotations

import csv
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
import uuid

CATALOG_REPLACE_RETRIES = 5
CATALOG_REPLACE_SLEEP_SECONDS = 0.1


def register_catalog_entry(output_dir: Path, entry: dict[str, object]) -> dict[str, str]:
    catalog_dir = output_dir / "research_catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = catalog_dir / "catalog.jsonl"
    entry_with_timestamp = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        **entry,
    }
    entries = load_catalog_entries(output_dir)
    entries.append(entry_with_timestamp)
    return write_catalog_snapshot(output_dir, entries)


def write_catalog_snapshot(output_dir: Path, entries: list[dict[str, object]]) -> dict[str, str]:
    catalog_dir = output_dir / "research_catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = catalog_dir / "catalog.jsonl"
    json_path = catalog_dir / "experiment_catalog.json"
    csv_path = catalog_dir / "experiment_catalog.csv"
    latest_path = catalog_dir / "latest_profile_artifacts.json"

    jsonl_content = "\n".join(json.dumps(entry) for entry in entries)
    if jsonl_content:
        jsonl_content += "\n"
    _atomic_write_text(jsonl_path, jsonl_content)
    _atomic_write_text(json_path, json.dumps(entries, indent=2))
    _write_catalog_csv(csv_path, entries)
    _atomic_write_text(latest_path, json.dumps(_latest_profile_artifacts(entries), indent=2))

    return {
        "catalog_jsonl": str(jsonl_path),
        "catalog_json": str(json_path),
        "catalog_csv": str(csv_path),
        "latest_profiles_json": str(latest_path),
    }


def load_catalog_entries(output_dir: Path) -> list[dict[str, object]]:
    jsonl_path = output_dir / "research_catalog" / "catalog.jsonl"
    if not jsonl_path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                # Best-effort recovery for a previously interrupted write.
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    return entries


def _write_catalog_csv(path: Path, entries: list[dict[str, object]]) -> None:
    if not entries:
        _atomic_write_text(path, "")
        return
    fieldnames = sorted({key for entry in entries for key in entry.keys()})
    temp_path = _temporary_path(path)
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(entries)
        _replace_with_retry(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = _temporary_path(path)
    try:
        temp_path.write_text(content, encoding="utf-8")
        _replace_with_retry(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _replace_with_retry(temp_path: Path, path: Path) -> None:
    attempts = 0
    while True:
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            attempts += 1
            if attempts >= CATALOG_REPLACE_RETRIES:
                raise
            time.sleep(CATALOG_REPLACE_SLEEP_SECONDS)


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")


def _latest_profile_artifacts(entries: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for entry in entries:
        profile_name = str(entry.get("profile_name", "") or "")
        if not profile_name:
            continue
        bucket = latest.setdefault(profile_name, {})
        artifact_type = str(entry.get("artifact_type", "unknown") or "unknown")
        bucket[f"latest_{artifact_type}"] = _artifact_pointer(entry)
        evaluation_status = str(entry.get("evaluation_status", "") or "")
        if artifact_type == "run" and evaluation_status in {"pass", "warn"}:
            bucket["latest_valid_run"] = _artifact_pointer(entry)
        if artifact_type == "promotion":
            bucket["latest_promotion"] = _artifact_pointer(entry)
        if artifact_type == "research_decision":
            bucket["latest_research_decision"] = _artifact_pointer(entry)
    return latest


def _artifact_pointer(entry: dict[str, object]) -> dict[str, object]:
    return {
        "recorded_at_utc": entry.get("recorded_at_utc"),
        "artifact_name": entry.get("artifact_name"),
        "artifact_type": entry.get("artifact_type"),
        "primary_path": entry.get("primary_path"),
        "evaluation_status": entry.get("evaluation_status"),
        "strategy_family": entry.get("strategy_family"),
        "sweep_type": entry.get("sweep_type"),
    }
