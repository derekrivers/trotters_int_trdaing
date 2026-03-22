from __future__ import annotations

import csv
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid

from trotters_trader.catalog import write_catalog_snapshot
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import RuntimeOverrides, apply_runtime_overrides, load_config
from trotters_trader.experiments import (
    apply_research_variant,
    _batch_preset_definition,
    _benchmark_pivot_scenarios,
    _candidate_config,
    _candidate_decision_score,
    _candidate_row_config,
    _candidate_row_from_promotion,
    _operability_shortlist,
    _select_operability_candidate,
    _stability_pivot_scenarios,
    _stress_config,
    _stress_row_non_broken,
    _stress_scenarios,
)
from trotters_trader.features import materialize_feature_set
from trotters_trader.reports import write_operability_program_report, write_promotion_artifacts, write_tranche_report

SUPPORTED_RESEARCH_COMMANDS = {
    "backtest",
    "report",
    "experiment",
    "compare-strategies",
    "compare-profiles",
    "compare-benchmarks",
    "sensitivity",
    "thresholds",
    "momentum-sweep",
    "momentum-refine",
    "compare-momentum-profiles",
    "validate-split",
    "risk-sweep",
    "regime-sweep",
    "sector-sweep",
    "walk-forward",
    "promotion-check",
    "universe-slice-sweep",
    "ranking-sweep",
    "construction-sweep",
    "starter-tranche",
    "operability-program",
}

PATH_SUFFIXES = {".json", ".jsonl", ".md", ".csv"}
ACTIVE_CAMPAIGN_STATUSES = {"queued", "running"}
ACTIVE_DIRECTOR_STATUSES = {"queued", "running"}
DEFAULT_NOTIFICATION_EVENTS = ("campaign_finished", "campaign_stopped", "campaign_failed", "strategy_promoted")
CAMPAIGN_NOTIFICATION_JSONL = "campaign_notifications.jsonl"
DEFAULT_DIRECTOR_PRIMARY_CONFIG = "configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml"
DEFAULT_DIRECTOR_FALLBACK_CONFIGS = (
    "configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml",
    "configs/eodhd_momentum_broad_candidate_beta_n4_ms002_rf63.toml",
)
DIRECTOR_PLAN_QUALITY_GATES = {"all", "pass_warn", "pass"}
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_CONNECT_TIMEOUT_SECONDS = SQLITE_BUSY_TIMEOUT_MS / 1000
SQLITE_INIT_MAX_ATTEMPTS = 5
SQLITE_INIT_RETRY_SECONDS = 0.25
CAMPAIGN_RUNTIME_RETRY_LIMIT = 2
RETRYABLE_RUNTIME_ERROR_MARKERS = (
    "disk i/o error",
    "database is locked",
    "unable to open database file",
    "unterminated string",
    "jsondecodeerror",
)
AGENT_TRIGGER_EVENT_MAP = {
    "campaign_finished": "research-triage",
    "campaign_failed": "failure-postmortem",
    "campaign_stopped": "failure-postmortem",
}


@dataclass(frozen=True)
class ResearchRuntimePaths:
    runtime_root: Path
    state_dir: Path
    database_path: Path
    job_outputs_dir: Path
    logs_dir: Path
    director_specs_dir: Path
    catalog_output_dir: Path


@dataclass(frozen=True)
class ResearchJob:
    job_id: str
    campaign_id: str | None
    command: str
    config_path: str
    spec_json: str
    priority: int
    status: str
    attempt_count: int
    max_attempts: int
    output_root: str
    input_dataset_ref: str | None
    feature_set_ref: str | None
    control_profile: str | None
    quality_gate: str
    evaluation_profile: str | None

    @property
    def spec(self) -> dict[str, object]:
        return json.loads(self.spec_json)


@dataclass(frozen=True)
class ResearchCampaign:
    campaign_id: str
    director_id: str | None
    campaign_name: str
    config_path: str
    status: str
    phase: str
    spec_json: str
    state_json: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    latest_report_path: str | None
    last_error: str | None

    @property
    def spec(self) -> dict[str, object]:
        payload = json.loads(self.spec_json)
        return payload if isinstance(payload, dict) else {}

    @property
    def state(self) -> dict[str, object]:
        payload = json.loads(self.state_json)
        return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class ResearchDirector:
    director_id: str
    director_name: str
    status: str
    spec_json: str
    state_json: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    current_campaign_id: str | None
    successful_campaign_id: str | None
    last_error: str | None

    @property
    def spec(self) -> dict[str, object]:
        payload = json.loads(self.spec_json)
        return payload if isinstance(payload, dict) else {}

    @property
    def state(self) -> dict[str, object]:
        payload = json.loads(self.state_json)
        return payload if isinstance(payload, dict) else {}


def runtime_paths(runtime_root: Path | str, catalog_output_dir: Path | str = "runs") -> ResearchRuntimePaths:
    root = Path(runtime_root)
    return ResearchRuntimePaths(
        runtime_root=root,
        state_dir=root / "state",
        database_path=root / "state" / "research_runtime.sqlite3",
        job_outputs_dir=root / "job_outputs",
        logs_dir=root / "logs",
        director_specs_dir=root / "director_specs",
        catalog_output_dir=Path(catalog_output_dir),
    )


def initialize_runtime(paths: ResearchRuntimePaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.job_outputs_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.director_specs_dir.mkdir(parents=True, exist_ok=True)
    paths.catalog_output_dir.mkdir(parents=True, exist_ok=True)
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(SQLITE_INIT_MAX_ATTEMPTS):
        try:
            with _connect(paths) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        campaign_id TEXT,
                        command TEXT NOT NULL,
                        config_path TEXT NOT NULL,
                        spec_json TEXT NOT NULL,
                        priority INTEGER NOT NULL DEFAULT 100,
                        status TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        lease_expires_at TEXT,
                        leased_by TEXT,
                        started_at TEXT,
                        finished_at TEXT,
                        exit_code INTEGER,
                        output_root TEXT NOT NULL,
                        stdout_path TEXT,
                        stderr_path TEXT,
                        error_message TEXT,
                        input_dataset_ref TEXT,
                        feature_set_ref TEXT,
                        control_profile TEXT,
                        quality_gate TEXT NOT NULL DEFAULT 'all',
                        evaluation_profile TEXT,
                        result_json TEXT
                    );
                    CREATE TABLE IF NOT EXISTS job_attempts (
                        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL,
                        attempt_number INTEGER NOT NULL,
                        worker_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        exit_code INTEGER,
                        stdout_path TEXT,
                        stderr_path TEXT,
                        error_message TEXT
                    );
                    CREATE TABLE IF NOT EXISTS workers (
                        worker_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        current_job_id TEXT,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS worker_heartbeats (
                        worker_id TEXT PRIMARY KEY,
                        heartbeat_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS artifacts (
                        artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL,
                        recorded_at_utc TEXT NOT NULL,
                        artifact_key TEXT NOT NULL,
                        artifact_type TEXT NOT NULL,
                        artifact_name TEXT NOT NULL,
                        primary_path TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS campaigns (
                        campaign_id TEXT PRIMARY KEY,
                        director_id TEXT,
                        campaign_name TEXT NOT NULL,
                        config_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        spec_json TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        latest_report_path TEXT,
                        last_error TEXT
                    );
                    CREATE TABLE IF NOT EXISTS campaign_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id TEXT NOT NULL,
                        recorded_at_utc TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS directors (
                        director_id TEXT PRIMARY KEY,
                        director_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        spec_json TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        current_campaign_id TEXT,
                        successful_campaign_id TEXT,
                        last_error TEXT
                    );
                    CREATE TABLE IF NOT EXISTS director_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        director_id TEXT NOT NULL,
                        recorded_at_utc TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    """
                )
                _ensure_column(connection, "jobs", "campaign_id", "TEXT")
                _ensure_column(connection, "campaigns", "director_id", "TEXT")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == SQLITE_INIT_MAX_ATTEMPTS - 1:
                raise
            last_error = exc
            time.sleep(SQLITE_INIT_RETRY_SECONDS * (attempt + 1))
    if last_error is not None:
        raise last_error


def submit_jobs(paths: ResearchRuntimePaths, payload: object) -> dict[str, object]:
    initialize_runtime(paths)
    specs = _normalize_job_specs(payload)
    now = _utcnow()
    job_ids: list[str] = []
    with _connect(paths) as connection:
        for raw_spec in specs:
            spec = dict(raw_spec)
            command = str(spec["command"])
            if command not in SUPPORTED_RESEARCH_COMMANDS:
                raise ValueError(f"Unsupported research command '{command}'")
            job_id = str(spec.get("job_id") or uuid.uuid4().hex)
            output_root, output_root_mode = _normalize_output_root(spec.get("output_root"), job_id)
            normalized_spec = {
                **spec,
                "job_id": job_id,
                "output_root": output_root,
                "output_root_mode": output_root_mode,
            }
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, input_dataset_ref, feature_set_ref, control_profile,
                    quality_gate, evaluation_profile
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    _optional_text(spec.get("campaign_id")),
                    command,
                    str(spec["config_path"]),
                    json.dumps(normalized_spec, indent=2),
                    int(spec.get("priority", 100)),
                    int(spec.get("max_attempts", 3)),
                    now,
                    now,
                    output_root,
                    _optional_text(spec.get("input_dataset_ref")),
                    _optional_text(spec.get("feature_set_ref")),
                    _optional_text(spec.get("control_profile")),
                    str(spec.get("quality_gate", "all")),
                    _optional_text(spec.get("evaluation_profile")),
                ),
            )
            job_ids.append(job_id)
    return {"submitted": len(job_ids), "job_ids": job_ids, "database_path": str(paths.database_path)}


def coordinator_cycle(paths: ResearchRuntimePaths, lease_timeout_seconds: int = 900) -> dict[str, object]:
    initialize_runtime(paths)
    now_dt = _parse_timestamp(_utcnow())
    cutoff = _isoformat(now_dt - timedelta(seconds=max(lease_timeout_seconds, 1)))
    worker_cutoff = _isoformat(now_dt - timedelta(seconds=min(max(lease_timeout_seconds, 1), 30)))
    stale_running_cutoff = _isoformat(now_dt - timedelta(seconds=max(60, min(max(lease_timeout_seconds, 1), 180))))
    requeued = 0
    failed = 0
    with _connect(paths) as connection:
        expired = connection.execute(
            """
            SELECT job_id, attempt_count, max_attempts
            FROM jobs
            WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
            """,
            (cutoff,),
        ).fetchall()
        now = _utcnow()
        for row in expired:
            next_status = "queued" if int(row["attempt_count"]) < int(row["max_attempts"]) else "failed"
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, leased_by = NULL, lease_expires_at = NULL, updated_at = ?,
                    finished_at = CASE WHEN ? = 'failed' THEN ? ELSE finished_at END,
                    error_message = CASE WHEN ? = 'failed' THEN 'lease_expired' ELSE error_message END
                WHERE job_id = ?
                """,
                (next_status, now, next_status, now, next_status, row["job_id"]),
            )
            if next_status == "queued":
                requeued += 1
            else:
                failed += 1
        recovered = _recover_stale_running_jobs(connection, stale_running_cutoff)
        requeued += recovered["requeued"]
        failed += recovered["failed"]
        _prune_stale_workers(connection, worker_cutoff)
        snapshot = _build_status_snapshot(connection)
    exports = export_runtime_catalog(paths)
    return {**snapshot, "requeued_jobs": requeued, "failed_expired_jobs": failed, "catalog_exports": exports}


def heartbeat_worker(paths: ResearchRuntimePaths, worker_id: str, current_job_id: str | None, status: str) -> None:
    initialize_runtime(paths)
    now = _utcnow()
    with _connect(paths) as connection:
        connection.execute(
            """
            INSERT INTO workers (worker_id, status, current_job_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                status = excluded.status,
                current_job_id = excluded.current_job_id,
                updated_at = excluded.updated_at
            """,
            (worker_id, status, current_job_id, now),
        )
        connection.execute(
            """
            INSERT INTO worker_heartbeats (worker_id, heartbeat_at)
            VALUES (?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at
            """,
            (worker_id, now),
        )


def renew_job_lease(paths: ResearchRuntimePaths, job_id: str, worker_id: str, lease_timeout_seconds: int) -> None:
    initialize_runtime(paths)
    now = _utcnow()
    lease_expires_at = _isoformat(_parse_timestamp(now) + timedelta(seconds=max(lease_timeout_seconds, 1)))
    with _connect(paths) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET lease_expires_at = ?, updated_at = ?
            WHERE job_id = ? AND status = 'running' AND leased_by = ?
            """,
            (lease_expires_at, now, job_id, worker_id),
        )


def lease_next_job(paths: ResearchRuntimePaths, worker_id: str, lease_timeout_seconds: int) -> ResearchJob | None:
    initialize_runtime(paths)
    now = _utcnow()
    lease_expires_at = _isoformat(_parse_timestamp(now) + timedelta(seconds=max(lease_timeout_seconds, 1)))
    with _connect(paths) as connection:
        for _ in range(5):
            row = connection.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY priority ASC, created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            attempt_number = int(row["attempt_count"]) + 1
            updated = connection.execute(
                """
                UPDATE jobs
                SET status = 'running', leased_by = ?, lease_expires_at = ?, attempt_count = ?,
                    started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (worker_id, lease_expires_at, attempt_number, now, now, row["job_id"]),
            )
            if updated.rowcount == 0:
                continue
            connection.execute(
                """
                INSERT INTO job_attempts (job_id, attempt_number, worker_id, status, started_at)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (row["job_id"], attempt_number, worker_id, now),
            )
            leased = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (row["job_id"],)).fetchone()
            return _row_to_job(leased)
        return None


def get_job(paths: ResearchRuntimePaths, job_id: str) -> ResearchJob:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown job '{job_id}'")
        return _row_to_job(row)


def job_status(
    paths: ResearchRuntimePaths,
    job_id: str | None = None,
    *,
    campaign_id: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        if job_id is None:
            conditions: list[str] = []
            parameters: list[object] = []
            if campaign_id:
                conditions.append("campaign_id = ?")
                parameters.append(campaign_id)
            if status:
                conditions.append("status = ?")
                parameters.append(status)
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            jobs = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT
                        job_id,
                        campaign_id,
                        command,
                        config_path,
                        status,
                        priority,
                        attempt_count,
                        max_attempts,
                        leased_by,
                        started_at,
                        finished_at,
                        exit_code,
                        stdout_path,
                        stderr_path,
                        error_message,
                        created_at,
                        updated_at
                    FROM jobs
                    {where_clause}
                    ORDER BY created_at ASC
                    """,
                    tuple(parameters),
                ).fetchall()
            ]
            return {"jobs": jobs}

        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown job '{job_id}'")
        attempts = [
            dict(attempt_row)
            for attempt_row in connection.execute(
                """
                SELECT
                    attempt_id,
                    attempt_number,
                    worker_id,
                    status,
                    started_at,
                    finished_at,
                    exit_code,
                    stdout_path,
                    stderr_path,
                    error_message
                FROM job_attempts
                WHERE job_id = ?
                ORDER BY attempt_number ASC
                """,
                (job_id,),
            ).fetchall()
        ]
        artifacts = [
            {
                **dict(artifact_row),
                "metadata": _load_result_payload(artifact_row["metadata_json"]),
            }
            for artifact_row in connection.execute(
                """
                SELECT
                    artifact_id,
                    recorded_at_utc,
                    artifact_key,
                    artifact_type,
                    artifact_name,
                    primary_path,
                    metadata_json
                FROM artifacts
                WHERE job_id = ?
                ORDER BY recorded_at_utc ASC, artifact_id ASC
                """,
                (job_id,),
            ).fetchall()
        ]
        return {
            "job": {
                "job_id": row["job_id"],
                "campaign_id": row["campaign_id"],
                "command": row["command"],
                "config_path": row["config_path"],
                "status": row["status"],
                "priority": row["priority"],
                "attempt_count": row["attempt_count"],
                "max_attempts": row["max_attempts"],
                "leased_by": row["leased_by"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "exit_code": row["exit_code"],
                "output_root": row["output_root"],
                "stdout_path": row["stdout_path"],
                "stderr_path": row["stderr_path"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "spec": _load_result_payload(row["spec_json"]),
                "result": _load_result_payload(row["result_json"]),
            },
            "attempts": attempts,
            "artifacts": artifacts,
        }


def read_job_log(
    paths: ResearchRuntimePaths,
    job_id: str,
    *,
    stream: str = "stderr",
    tail_lines: int = 200,
) -> dict[str, object]:
    initialize_runtime(paths)
    normalized_stream = stream.strip().lower()
    if normalized_stream not in {"stdout", "stderr"}:
        raise ValueError("stream must be 'stdout' or 'stderr'")
    with _connect(paths) as connection:
        row = connection.execute(
            """
            SELECT job_id, campaign_id, status, stdout_path, stderr_path, updated_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown job '{job_id}'")
    path_value = row["stdout_path"] if normalized_stream == "stdout" else row["stderr_path"]
    normalized_tail = min(max(int(tail_lines), 1), 2000)
    lines: list[str] = []
    if isinstance(path_value, str) and path_value:
        log_path = Path(path_value)
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-normalized_tail:]
    return {
        "job_id": row["job_id"],
        "campaign_id": row["campaign_id"],
        "status": row["status"],
        "stream": normalized_stream,
        "path": path_value,
        "tail_lines": normalized_tail,
        "updated_at": row["updated_at"],
        "lines": lines,
    }


def artifact_status(
    paths: ResearchRuntimePaths,
    *,
    job_id: str | None = None,
    campaign_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = 200,
) -> dict[str, object]:
    initialize_runtime(paths)
    conditions: list[str] = []
    parameters: list[object] = []
    if job_id:
        conditions.append("artifacts.job_id = ?")
        parameters.append(job_id)
    if campaign_id:
        conditions.append("jobs.campaign_id = ?")
        parameters.append(campaign_id)
    if artifact_type:
        conditions.append("artifacts.artifact_type = ?")
        parameters.append(artifact_type)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    normalized_limit = min(max(int(limit), 1), 1000)
    parameters.append(normalized_limit)
    with _connect(paths) as connection:
        artifacts = [
            {
                **dict(row),
                "metadata": _load_result_payload(row["metadata_json"]),
            }
            for row in connection.execute(
                f"""
                SELECT
                    artifacts.artifact_id,
                    artifacts.job_id,
                    jobs.campaign_id,
                    artifacts.recorded_at_utc,
                    artifacts.artifact_key,
                    artifacts.artifact_type,
                    artifacts.artifact_name,
                    artifacts.primary_path,
                    artifacts.metadata_json
                FROM artifacts
                INNER JOIN jobs ON jobs.job_id = artifacts.job_id
                {where_clause}
                ORDER BY artifacts.recorded_at_utc DESC, artifacts.artifact_id DESC
                LIMIT ?
                """,
                tuple(parameters),
            ).fetchall()
        ]
    return {"artifacts": artifacts}


def worker_loop(
    paths: ResearchRuntimePaths,
    worker_id: str,
    poll_seconds: float = 2.0,
    lease_timeout_seconds: int = 900,
    once: bool = False,
) -> dict[str, object]:
    initialize_runtime(paths)
    completed_jobs = 0
    failed_jobs = 0
    while True:
        heartbeat_worker(paths, worker_id, current_job_id=None, status="idle")
        job = lease_next_job(paths, worker_id, lease_timeout_seconds)
        if job is None:
            if once:
                break
            time.sleep(max(poll_seconds, 0.1))
            continue
        heartbeat_worker(paths, worker_id, current_job_id=job.job_id, status="running")
        if execute_leased_job(paths, worker_id, job, lease_timeout_seconds=lease_timeout_seconds):
            completed_jobs += 1
        else:
            failed_jobs += 1
        heartbeat_worker(paths, worker_id, current_job_id=None, status="idle")
        if once:
            break
    return {"worker_id": worker_id, "completed_jobs": completed_jobs, "failed_jobs": failed_jobs}


def execute_leased_job(
    paths: ResearchRuntimePaths,
    worker_id: str,
    job: ResearchJob,
    *,
    lease_timeout_seconds: int,
) -> bool:
    attempt_number = job.attempt_count
    log_dir = paths.logs_dir / job.job_id
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"attempt_{attempt_number:02d}.stdout.json"
    stderr_path = log_dir / f"attempt_{attempt_number:02d}.stderr.log"
    env = os.environ.copy()
    pythonpath_entries = [str(Path.cwd() / "src")]
    if env.get("PYTHONPATH"):
        pythonpath_entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    command = [
        sys.executable,
        "-m",
        "trotters_trader.cli",
        "research-run-job",
        "--runtime-root",
        str(paths.runtime_root),
        "--job-id",
        job.job_id,
    ]
    heartbeat_interval = max(5.0, min(30.0, 15.0))
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            cwd=Path.cwd(),
            env=env,
        )
        last_heartbeat = time.monotonic()
        while True:
            returncode = process.poll()
            now = time.monotonic()
            if returncode is not None:
                completed_returncode = returncode
                break
            if now - last_heartbeat >= heartbeat_interval:
                heartbeat_worker(paths, worker_id, current_job_id=job.job_id, status="running")
                renew_job_lease(paths, job.job_id, worker_id, lease_timeout_seconds)
                last_heartbeat = now
            time.sleep(1.0)
    if completed_returncode == 0:
        payload = json.loads(stdout_path.read_text(encoding="utf-8"))
        complete_job(paths, job.job_id, worker_id, completed_returncode, payload, stdout_path, stderr_path)
        return True
    error_message = stderr_path.read_text(encoding="utf-8").strip() or stdout_path.read_text(encoding="utf-8").strip()
    fail_job(paths, job.job_id, worker_id, completed_returncode, error_message, stdout_path, stderr_path)
    return False


def complete_job(
    paths: ResearchRuntimePaths,
    job_id: str,
    worker_id: str,
    exit_code: int,
    payload: dict[str, object],
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    initialize_runtime(paths)
    now = _utcnow()
    with _connect(paths) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = 'completed', leased_by = NULL, lease_expires_at = NULL,
                finished_at = ?, updated_at = ?, exit_code = ?, stdout_path = ?, stderr_path = ?,
                error_message = NULL, result_json = ?
            WHERE job_id = ?
            """,
            (now, now, exit_code, str(stdout_path), str(stderr_path), json.dumps(payload, indent=2), job_id),
        )
        _finish_attempt(connection, job_id, worker_id, "completed", now, exit_code, stdout_path, stderr_path, None)
        connection.execute(
            "UPDATE workers SET status = 'idle', current_job_id = NULL, updated_at = ? WHERE worker_id = ?",
            (now, worker_id),
        )
        connection.execute("DELETE FROM artifacts WHERE job_id = ?", (job_id,))
        for artifact in payload.get("artifacts", []):
            if not isinstance(artifact, dict):
                continue
            connection.execute(
                """
                INSERT INTO artifacts (
                    job_id, recorded_at_utc, artifact_key, artifact_type, artifact_name, primary_path, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    now,
                    str(artifact.get("artifact_key", "artifact")),
                    str(artifact.get("artifact_type", "artifact")),
                    str(artifact.get("artifact_name", Path(str(artifact.get("path", ""))).name or "artifact")),
                    str(artifact.get("path", "")),
                    json.dumps(artifact, indent=2),
                ),
            )


def fail_job(
    paths: ResearchRuntimePaths,
    job_id: str,
    worker_id: str,
    exit_code: int,
    error_message: str,
    stdout_path: Path,
    stderr_path: Path,
) -> None:
    initialize_runtime(paths)
    now = _utcnow()
    with _connect(paths) as connection:
        row = connection.execute("SELECT attempt_count, max_attempts FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return
        status = "queued" if int(row["attempt_count"]) < int(row["max_attempts"]) else "failed"
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, leased_by = NULL, lease_expires_at = NULL, updated_at = ?, exit_code = ?,
                stdout_path = ?, stderr_path = ?, error_message = ?,
                finished_at = CASE WHEN ? = 'failed' THEN ? ELSE finished_at END
            WHERE job_id = ?
            """,
            (status, now, exit_code, str(stdout_path), str(stderr_path), error_message[:4000], status, now, job_id),
        )
        _finish_attempt(connection, job_id, worker_id, "failed", now, exit_code, stdout_path, stderr_path, error_message[:4000])
        connection.execute(
            "UPDATE workers SET status = 'idle', current_job_id = NULL, updated_at = ? WHERE worker_id = ?",
            (now, worker_id),
        )


def runtime_status(paths: ResearchRuntimePaths) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        return _build_status_snapshot(connection)


def start_campaign(
    paths: ResearchRuntimePaths,
    config_path: str,
    *,
    director_id: str | None = None,
    campaign_name: str | None = None,
    evaluation_profile: str | None = None,
    quality_gate: str = "all",
    max_hours: float = 24.0,
    max_jobs: int = 0,
    stage_candidate_limit: int = 0,
    shortlist_size: int = 3,
    notification_command: str | None = None,
    notify_events: tuple[str, ...] = DEFAULT_NOTIFICATION_EVENTS,
) -> dict[str, object]:
    initialize_runtime(paths)
    campaign_id = uuid.uuid4().hex
    now = _utcnow()
    config = load_config(config_path, evaluation_profile=evaluation_profile)
    dataset_ref, feature_set_ref = _prepare_campaign_inputs(paths, config, campaign_id)
    resolved_campaign_name = campaign_name or f"{Path(config_path).stem}-{campaign_id[:8]}"
    spec = {
        "config_path": config_path,
        "evaluation_profile": evaluation_profile,
        "quality_gate": quality_gate,
        "input_dataset_ref": dataset_ref,
        "input_dataset_ref_mode": "runtime_relative",
        "feature_set_ref": feature_set_ref,
        "feature_set_ref_mode": "runtime_relative" if feature_set_ref else "raw",
        "max_hours": max_hours,
        "max_jobs": max_jobs,
        "stage_candidate_limit": stage_candidate_limit,
        "shortlist_size": shortlist_size,
        "notification_command": notification_command,
        "notify_events": list(notify_events),
    }
    state = {
        "seed_overrides": {},
        "control_row": None,
        "candidate_pool": [],
        "focused_result": None,
        "pivot_result": None,
        "stability_result": None,
        "shortlisted": [],
        "stress_results": [],
        "final_decision": None,
        "pending_stage": None,
    }
    with _connect(paths) as connection:
        connection.execute(
            """
            INSERT INTO campaigns (
                campaign_id, director_id, campaign_name, config_path, status, phase, spec_json, state_json,
                created_at, updated_at, started_at
            ) VALUES (?, ?, ?, ?, 'running', 'focused_operability', ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                director_id,
                resolved_campaign_name,
                config_path,
                json.dumps(spec, indent=2),
                json.dumps(state, indent=2),
                now,
                now,
                now,
            ),
        )
        _record_campaign_event(
            connection,
            campaign_id,
            "campaign_started",
            f"Campaign '{resolved_campaign_name}' started",
            {"phase": "focused_operability", "config_path": config_path},
        )
    _emit_campaign_notification(
        paths,
        campaign_id=campaign_id,
        campaign_name=resolved_campaign_name,
        event_type="campaign_started",
        message=f"Campaign '{resolved_campaign_name}' started",
        payload={"phase": "focused_operability", "config_path": config_path},
        spec=spec,
    )
    step = step_campaign(paths, campaign_id)
    return {"campaign_id": campaign_id, "campaign_name": resolved_campaign_name, **step}


def campaign_status(paths: ResearchRuntimePaths, campaign_id: str | None = None) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        if campaign_id is None:
            campaigns = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT campaign_id, director_id, campaign_name, status, phase, created_at, updated_at, latest_report_path, last_error
                    FROM campaigns
                    ORDER BY created_at ASC
                    """
                ).fetchall()
            ]
            return {"campaigns": campaigns}
        campaign = _get_campaign(connection, campaign_id)
        events = [
            dict(row)
            for row in connection.execute(
                """
                SELECT recorded_at_utc, event_type, message, payload_json
                FROM campaign_events
                WHERE campaign_id = ?
                ORDER BY event_id ASC
                """,
                (campaign_id,),
            ).fetchall()
        ]
        jobs = [
            dict(row)
            for row in connection.execute(
                """
                SELECT job_id, status, priority, created_at, updated_at, command
                FROM jobs
                WHERE campaign_id = ?
                ORDER BY created_at ASC
                """,
                (campaign_id,),
            ).fetchall()
        ]
        return {
            "campaign": {
                "campaign_id": campaign.campaign_id,
                "director_id": campaign.director_id,
                "campaign_name": campaign.campaign_name,
                "config_path": campaign.config_path,
                "status": campaign.status,
                "phase": campaign.phase,
                "latest_report_path": campaign.latest_report_path,
                "last_error": campaign.last_error,
                "state": campaign.state,
                "spec": campaign.spec,
            },
            "events": events,
            "jobs": jobs,
        }


def stop_campaign(
    paths: ResearchRuntimePaths,
    campaign_id: str,
    *,
    cancel_queued: bool = True,
    reason: str = "operator_stop",
) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        campaign = _get_campaign(connection, campaign_id)
        if campaign.status not in ACTIVE_CAMPAIGN_STATUSES:
            return {
                "campaign_id": campaign.campaign_id,
                "campaign_name": campaign.campaign_name,
                "status": campaign.status,
                "phase": campaign.phase,
                "outcome": "campaign_not_active",
            }
        now = _utcnow()
        queued_cancelled = 0
        if cancel_queued:
            updated = connection.execute(
                """
                UPDATE jobs
                SET status = 'cancelled', updated_at = ?, error_message = ?
                WHERE campaign_id = ? AND status = 'queued'
                """,
                (now, reason, campaign_id),
            )
            queued_cancelled = int(updated.rowcount or 0)
        running_jobs = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE campaign_id = ? AND status = 'running'",
                (campaign_id,),
            ).fetchone()["count"]
        )
        state = campaign.state
        state["pending_stage"] = None
        state["final_decision"] = {
            "recommended_action": "stopped",
            "reason": reason,
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
        connection.execute(
            """
            UPDATE campaigns
            SET status = 'stopped', state_json = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?)
            WHERE campaign_id = ?
            """,
            (json.dumps(state, indent=2), now, now, campaign_id),
        )
        payload = {
            "reason": reason,
            "queued_jobs_cancelled": queued_cancelled,
            "running_jobs_remaining": running_jobs,
        }
        _record_campaign_event(
            connection,
            campaign_id,
            "campaign_stopped",
            f"Campaign stopped: {reason}",
            payload,
        )
        spec = campaign.spec
        campaign_name = campaign.campaign_name
    _emit_campaign_notification(
        paths,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        event_type="campaign_stopped",
        message=f"Campaign stopped: {reason}",
        payload=payload,
        spec=spec,
    )
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "status": "stopped",
        "outcome": "campaign_stopped",
        "queued_jobs_cancelled": queued_cancelled,
        "running_jobs_remaining": running_jobs,
    }


def step_campaign(paths: ResearchRuntimePaths, campaign_id: str) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        campaign = _get_campaign(connection, campaign_id)
        if campaign.status not in {"queued", "running"}:
            return _campaign_step_payload(campaign, "campaign_not_active")
        state = campaign.state
        final_decision = state.get("final_decision")
        if isinstance(final_decision, dict):
            _mark_campaign_finished(connection, campaign, status="completed")
            return _campaign_step_payload(_get_campaign(connection, campaign_id), "campaign_completed")
        if _campaign_budget_exhausted(connection, campaign):
            final_decision = {
                "recommended_action": "exhausted",
                "reason": "campaign_budget_exhausted",
                "selected_run_name": None,
                "selected_profile_name": None,
                "selected_candidate_eligible": False,
                "selected_stress_ok": False,
                "pivot_used": bool(state.get("pivot_result")),
            }
            _set_campaign_final_decision(
                connection,
                campaign,
                final_decision,
                status="exhausted",
            )
            _emit_campaign_notification(
                paths,
                campaign_id=campaign.campaign_id,
                campaign_name=campaign.campaign_name,
                event_type="campaign_finished",
                message="Campaign finished with status exhausted",
                payload=final_decision,
                spec=campaign.spec,
            )
            return _campaign_step_payload(_get_campaign(connection, campaign_id), "campaign_budget_exhausted")

        pending_stage = state.get("pending_stage")
        if isinstance(pending_stage, dict) and pending_stage.get("job_ids"):
            stage_rows = _campaign_stage_jobs(connection, pending_stage["job_ids"])
            statuses = {str(row["status"]) for row in stage_rows}
            if statuses & ACTIVE_CAMPAIGN_STATUSES:
                return _campaign_step_payload(campaign, "waiting_for_stage_jobs")
            outcome = _process_campaign_stage(paths, connection, campaign, pending_stage, stage_rows)
            return _campaign_step_payload(_get_campaign(connection, campaign_id), outcome)

        submission = _submit_campaign_phase_jobs(paths, connection, campaign)
        return _campaign_step_payload(_get_campaign(connection, campaign_id), submission)


def campaign_manager_loop(
    paths: ResearchRuntimePaths,
    *,
    poll_seconds: float = 15.0,
    once: bool = False,
) -> dict[str, object]:
    initialize_runtime(paths)
    stepped = 0
    while True:
        with _connect(paths) as connection:
            campaign_ids = [
                row["campaign_id"]
                for row in connection.execute(
                    """
                    SELECT campaign_id
                    FROM campaigns
                    WHERE status IN ('queued', 'running')
                    ORDER BY created_at ASC
                    """
                ).fetchall()
            ]
        for campaign_id in campaign_ids:
            try:
                step_campaign(paths, campaign_id)
            except Exception as exc:
                _handle_campaign_runtime_error(paths, campaign_id, exc)
            stepped += 1
        if once:
            return {"stepped_campaigns": stepped, "active_campaigns": len(campaign_ids)}
        time.sleep(max(poll_seconds, 0.1))


def start_director(
    paths: ResearchRuntimePaths,
    *,
    config_path: str | None = None,
    director_name: str | None = None,
    evaluation_profile: str | None = None,
    quality_gate: str = "all",
    max_hours: float = 24.0,
    max_jobs: int = 0,
    stage_candidate_limit: int = 0,
    shortlist_size: int = 3,
    notification_command: str | None = None,
    notify_events: tuple[str, ...] = DEFAULT_NOTIFICATION_EVENTS,
    plan_payload: object | None = None,
    plan_file_path: str | None = None,
    adopt_active_campaigns: bool = True,
) -> dict[str, object]:
    initialize_runtime(paths)
    director_id = uuid.uuid4().hex
    now = _utcnow()
    plan_resolution = _resolve_director_plan(
        config_path=config_path,
        plan_payload=plan_payload,
        plan_file_path=plan_file_path,
    )
    plan = plan_resolution["campaigns"]
    resolved_name = director_name or f"research-director-{director_id[:8]}"
    spec = {
        "seed_config_path": config_path or plan[0]["config_path"],
        "plan_name": plan_resolution["plan_name"],
        "plan_source": plan_resolution["plan_source"],
        "plan": plan,
        "evaluation_profile": evaluation_profile,
        "quality_gate": quality_gate,
        "max_hours": max_hours,
        "max_jobs": max_jobs,
        "stage_candidate_limit": stage_candidate_limit,
        "shortlist_size": shortlist_size,
        "notification_command": notification_command,
        "notify_events": list(notify_events),
        "adopt_active_campaigns": adopt_active_campaigns,
    }
    state = {
        "campaign_queue": [
            {
                "queue_index": index,
                "config_path": entry["config_path"],
                "campaign_name": entry.get("campaign_name") or f"{resolved_name}-{Path(entry['config_path']).stem}",
                "entry_name": entry.get("entry_name") or Path(entry["config_path"]).stem,
                "evaluation_profile": entry.get("evaluation_profile"),
                "quality_gate": entry.get("quality_gate"),
                "campaign_max_hours": entry.get("campaign_max_hours"),
                "campaign_max_jobs": entry.get("campaign_max_jobs"),
                "stage_candidate_limit": entry.get("stage_candidate_limit"),
                "shortlist_size": entry.get("shortlist_size"),
                "status": "pending",
                "campaign_id": None,
                "completed_at": None,
                "outcome": None,
            }
            for index, entry in enumerate(plan)
        ],
        "plan_name": plan_resolution["plan_name"],
        "plan_source": plan_resolution["plan_source"],
        "active_campaign_id": None,
        "successful_campaign_id": None,
        "final_result": None,
    }
    with _connect(paths) as connection:
        duplicate = _find_active_plan_duplicate(connection, spec)
        if duplicate is not None:
            current_campaign_id = str(duplicate.get("current_campaign_id") or "").strip()
            raise ValueError(
                "Active director already running for plan "
                f"'{plan_resolution['plan_name']}' "
                f"(director_id='{duplicate['director_id']}', current_campaign_id='{current_campaign_id or '-'}'). "
                "Stop or finish that director before starting another."
            )
        connection.execute(
            """
            INSERT INTO directors (
                director_id, director_name, status, spec_json, state_json,
                created_at, updated_at, started_at
            ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
            """,
            (
                director_id,
                resolved_name,
                json.dumps(spec, indent=2),
                json.dumps(state, indent=2),
                now,
                now,
                now,
            ),
        )
        _record_director_event(
            connection,
            director_id,
            "director_started",
            f"Director '{resolved_name}' started",
            {"plan_length": len(plan), "seed_config_path": spec["seed_config_path"]},
        )
    _write_director_spec(
        paths,
        director_id,
        {
            "director_id": director_id,
            "director_name": resolved_name,
            "plan_name": plan_resolution["plan_name"],
            "plan_source": plan_resolution["plan_source"],
            "spec": spec,
        },
    )
    step = step_director(paths, director_id)
    return {"director_id": director_id, "director_name": resolved_name, **step}


def _find_active_plan_duplicate(connection: sqlite3.Connection, incoming_spec: dict[str, object]) -> dict[str, object] | None:
    incoming_identity = _director_plan_identity(incoming_spec)
    for row in connection.execute(
        """
        SELECT director_id, director_name, current_campaign_id, spec_json
        FROM directors
        WHERE status IN ('queued', 'running')
        ORDER BY created_at ASC
        """
    ).fetchall():
        try:
            existing_spec = json.loads(row["spec_json"]) if row["spec_json"] else {}
        except json.JSONDecodeError:
            existing_spec = {}
        if not isinstance(existing_spec, dict):
            existing_spec = {}
        if _director_plan_identity(existing_spec) != incoming_identity:
            continue
        return {
            "director_id": row["director_id"],
            "director_name": row["director_name"],
            "current_campaign_id": row["current_campaign_id"],
        }
    return None


def _director_plan_identity(spec: dict[str, object]) -> tuple[object, ...]:
    plan_name = str(spec.get("plan_name") or "").strip()
    plan_source = str(spec.get("plan_source") or "").strip()
    campaign_paths: list[str] = []
    raw_plan = spec.get("plan")
    if isinstance(raw_plan, list):
        for entry in raw_plan:
            if not isinstance(entry, dict):
                continue
            config_path = str(entry.get("config_path") or "").strip()
            if config_path:
                campaign_paths.append(config_path)
    return (plan_name, plan_source, tuple(campaign_paths))


def director_status(paths: ResearchRuntimePaths, director_id: str | None = None) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        if director_id is None:
            directors = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT director_id, director_name, status, current_campaign_id, successful_campaign_id,
                           created_at, updated_at, finished_at, last_error
                    FROM directors
                    ORDER BY created_at ASC
                    """
                ).fetchall()
            ]
            return {"directors": directors}
        director = _get_director(connection, director_id)
        events = [
            dict(row)
            for row in connection.execute(
                """
                SELECT recorded_at_utc, event_type, message, payload_json
                FROM director_events
                WHERE director_id = ?
                ORDER BY event_id ASC
                """,
                (director_id,),
            ).fetchall()
        ]
        campaigns = [
            dict(row)
            for row in connection.execute(
                """
                SELECT campaign_id, director_id, campaign_name, config_path, status, phase, updated_at, latest_report_path
                FROM campaigns
                WHERE director_id = ?
                ORDER BY created_at ASC
                """,
                (director_id,),
            ).fetchall()
        ]
        return {
            "director": {
                "director_id": director.director_id,
                "director_name": director.director_name,
                "status": director.status,
                "current_campaign_id": director.current_campaign_id,
                "successful_campaign_id": director.successful_campaign_id,
                "last_error": director.last_error,
                "state": director.state,
                "spec": director.spec,
            },
            "events": events,
            "campaigns": campaigns,
        }


def stop_director(
    paths: ResearchRuntimePaths,
    director_id: str,
    *,
    stop_active_campaign: bool = False,
    reason: str = "operator_stop",
) -> dict[str, object]:
    initialize_runtime(paths)
    active_campaign_id = None
    director_name = director_id
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status not in ACTIVE_DIRECTOR_STATUSES:
            return {
                "director_id": director.director_id,
                "director_name": director.director_name,
                "status": director.status,
                "outcome": "director_not_active",
            }
        now = _utcnow()
        state = director.state
        active_campaign_id = state.get("active_campaign_id") if isinstance(state.get("active_campaign_id"), str) else None
        state["final_result"] = {
            "recommended_action": "stopped",
            "reason": reason,
            "active_campaign_id": active_campaign_id,
        }
        connection.execute(
            """
            UPDATE directors
            SET status = 'stopped', state_json = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?)
            WHERE director_id = ?
            """,
            (json.dumps(state, indent=2), now, now, director_id),
        )
        _record_director_event(
            connection,
            director_id,
            "director_stopped",
            f"Director stopped: {reason}",
            {"active_campaign_id": active_campaign_id, "stop_active_campaign": stop_active_campaign},
        )
        director_name = director.director_name
    stopped_campaign = None
    if stop_active_campaign and active_campaign_id:
        stopped_campaign = stop_campaign(paths, active_campaign_id, reason=f"director_stop:{reason}")
    return {
        "director_id": director_id,
        "director_name": director_name,
        "status": "stopped",
        "outcome": "director_stopped",
        "active_campaign_id": active_campaign_id,
        "stopped_campaign": stopped_campaign,
    }


def pause_director(
    paths: ResearchRuntimePaths,
    director_id: str,
    *,
    reason: str = "operator_pause",
) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status == "paused":
            return _director_step_payload(director, "director_already_paused")
        if director.status not in ACTIVE_DIRECTOR_STATUSES:
            return _director_step_payload(director, "director_not_active")
        state = director.state
        state["pause_reason"] = reason
        connection.execute(
            """
            UPDATE directors
            SET status = 'paused', state_json = ?, updated_at = ?
            WHERE director_id = ?
            """,
            (json.dumps(state, indent=2), _utcnow(), director_id),
        )
        _record_director_event(
            connection,
            director_id,
            "director_paused",
            f"Director paused: {reason}",
            {"reason": reason, "active_campaign_id": director.current_campaign_id},
        )
        refreshed = _get_director(connection, director_id)
    return _director_step_payload(refreshed, "director_paused")


def resume_director(
    paths: ResearchRuntimePaths,
    director_id: str,
    *,
    reason: str = "operator_resume",
) -> dict[str, object]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status != "paused":
            return _director_step_payload(director, "director_not_paused")
        state = director.state
        state["pause_reason"] = None
        connection.execute(
            """
            UPDATE directors
            SET status = 'running', state_json = ?, updated_at = ?
            WHERE director_id = ?
            """,
            (json.dumps(state, indent=2), _utcnow(), director_id),
        )
        _record_director_event(
            connection,
            director_id,
            "director_resumed",
            f"Director resumed: {reason}",
            {"reason": reason, "active_campaign_id": director.current_campaign_id},
        )
    return step_director(paths, director_id)


def skip_director_next(
    paths: ResearchRuntimePaths,
    director_id: str,
    *,
    reason: str = "operator_skip",
) -> dict[str, object]:
    initialize_runtime(paths)
    should_step = False
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status not in ACTIVE_DIRECTOR_STATUSES | {"paused"}:
            return _director_step_payload(director, "director_not_skippable")
        state = director.state
        queue = _director_queue(state)
        entry = _next_director_queue_entry(queue)
        if entry is None:
            return _director_step_payload(director, "director_no_pending_campaign")
        entry["status"] = "skipped"
        entry["completed_at"] = _utcnow()
        entry["outcome"] = reason
        _update_director_state(connection, director_id, state)
        _record_director_event(
            connection,
            director_id,
            "director_campaign_skipped",
            f"Director skipped pending campaign {entry.get('campaign_name', 'unknown')}",
            {
                "reason": reason,
                "queue_index": entry.get("queue_index"),
                "config_path": entry.get("config_path"),
                "campaign_name": entry.get("campaign_name"),
            },
        )
        should_step = director.status in ACTIVE_DIRECTOR_STATUSES and not bool(director.current_campaign_id)
        refreshed = _get_director(connection, director_id)
    if should_step:
        return step_director(paths, director_id)
    return _director_step_payload(refreshed, "director_campaign_skipped")


def step_director(paths: ResearchRuntimePaths, director_id: str) -> dict[str, object]:
    initialize_runtime(paths)
    director = None
    launch_entry = None
    adopt_campaign_id = None
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status == "paused":
            return _director_step_payload(director, "director_paused")
        if director.status not in ACTIVE_DIRECTOR_STATUSES:
            return _director_step_payload(director, "director_not_active")
        state = director.state
        queue = _director_queue(state)
        active_campaign_id = state.get("active_campaign_id") if isinstance(state.get("active_campaign_id"), str) else None
        if active_campaign_id:
            campaign = _get_campaign(connection, active_campaign_id)
            if campaign.status in ACTIVE_CAMPAIGN_STATUSES:
                return _director_step_payload(director, "waiting_for_campaign")
            outcome = _process_director_campaign_outcome(connection, director, campaign, queue)
            return _director_step_payload(_get_director(connection, director_id), outcome)
        launch_entry = _next_director_queue_entry(queue)
        if launch_entry is None:
            _finish_director(
                connection,
                director,
                status="exhausted",
                final_result={"recommended_action": "exhausted", "reason": "director_queue_exhausted"},
            )
            return _director_step_payload(_get_director(connection, director_id), "director_exhausted")
        if bool(director.spec.get("adopt_active_campaigns", True)):
            adopt_campaign_id = _find_adoptable_campaign(connection, launch_entry["config_path"])
            if adopt_campaign_id:
                now = _utcnow()
                launch_entry["campaign_id"] = adopt_campaign_id
                launch_entry["status"] = "running"
                state["active_campaign_id"] = adopt_campaign_id
                connection.execute(
                    "UPDATE campaigns SET director_id = ?, updated_at = ? WHERE campaign_id = ?",
                    (director.director_id, now, adopt_campaign_id),
                )
                _update_director_state(
                    connection,
                    director.director_id,
                    state,
                    current_campaign_id=adopt_campaign_id,
                )
                _record_director_event(
                    connection,
                    director.director_id,
                    "campaign_adopted",
                    f"Director adopted existing campaign {adopt_campaign_id}",
                    {"campaign_id": adopt_campaign_id, "config_path": launch_entry["config_path"]},
                )
                return _director_step_payload(_get_director(connection, director_id), "campaign_adopted")
    assert director is not None
    assert launch_entry is not None
    started = start_campaign(
        paths,
        launch_entry["config_path"],
        director_id=director.director_id,
        campaign_name=launch_entry["campaign_name"],
        evaluation_profile=_director_entry_value(launch_entry, "evaluation_profile", director.spec.get("evaluation_profile")),
        quality_gate=str(_director_entry_value(launch_entry, "quality_gate", director.spec.get("quality_gate", "all"))),
        max_hours=float(_director_entry_value(launch_entry, "campaign_max_hours", director.spec.get("max_hours", 24.0))),
        max_jobs=int(_director_entry_value(launch_entry, "campaign_max_jobs", director.spec.get("max_jobs", 0))),
        stage_candidate_limit=int(
            _director_entry_value(launch_entry, "stage_candidate_limit", director.spec.get("stage_candidate_limit", 0))
        ),
        shortlist_size=int(_director_entry_value(launch_entry, "shortlist_size", director.spec.get("shortlist_size", 3))),
        notification_command=director.spec.get("notification_command"),
        notify_events=tuple(str(item) for item in director.spec.get("notify_events", DEFAULT_NOTIFICATION_EVENTS)),
    )
    with _connect(paths) as connection:
        refreshed = _get_director(connection, director_id)
        state = refreshed.state
        queue = _director_queue(state)
        queued_entry = _find_director_queue_entry(queue, launch_entry["queue_index"])
        if queued_entry is not None:
            queued_entry["campaign_id"] = started["campaign_id"]
            queued_entry["status"] = "running"
        state["active_campaign_id"] = started["campaign_id"]
        _update_director_state(
            connection,
            director_id,
            state,
            current_campaign_id=started["campaign_id"],
        )
        _record_director_event(
            connection,
            director_id,
            "campaign_started",
            f"Director started campaign {started['campaign_name']}",
            {"campaign_id": started["campaign_id"], "config_path": launch_entry["config_path"]},
        )
        refreshed = _get_director(connection, director_id)
        return _director_step_payload(refreshed, "campaign_started")


def director_manager_loop(
    paths: ResearchRuntimePaths,
    *,
    poll_seconds: float = 30.0,
    once: bool = False,
) -> dict[str, object]:
    initialize_runtime(paths)
    stepped = 0
    while True:
        with _connect(paths) as connection:
            director_ids = [
                row["director_id"]
                for row in connection.execute(
                    """
                    SELECT director_id
                    FROM directors
                    WHERE status IN ('queued', 'running')
                    ORDER BY created_at ASC
                    """
                ).fetchall()
            ]
        for director_id in director_ids:
            try:
                step_director(paths, director_id)
            except Exception as exc:
                _handle_director_runtime_error(paths, director_id, exc)
            stepped += 1
        if once:
            return {"stepped_directors": stepped, "active_directors": len(director_ids)}
        time.sleep(max(poll_seconds, 0.1))


def _resolve_director_plan(
    *,
    config_path: str | None,
    plan_payload: object | None,
    plan_file_path: str | None,
) -> dict[str, object]:
    if plan_payload is None:
        seed = config_path or DEFAULT_DIRECTOR_PRIMARY_CONFIG
        ordered = [seed, *DEFAULT_DIRECTOR_FALLBACK_CONFIGS]
        seen: set[str] = set()
        plan = []
        for candidate in ordered:
            if candidate in seen:
                continue
            seen.add(candidate)
            plan.append({"config_path": _validate_director_plan_config_path(candidate, 0)})
        return {
            "plan_name": "default_broad_operability",
            "plan_source": "built_in_default",
            "campaigns": plan,
        }
    if isinstance(plan_payload, list):
        raw_entries = plan_payload
        plan_name = "custom_director_plan"
    elif isinstance(plan_payload, dict):
        raw_entries = plan_payload.get("campaigns", [])
        raw_plan_name = plan_payload.get("plan_name")
        plan_name = (
            raw_plan_name.strip()
            if isinstance(raw_plan_name, str) and raw_plan_name.strip()
            else "custom_director_plan"
        )
    else:
        raise ValueError("Director plan must be a list or an object with a 'campaigns' list.")
    plan: list[dict[str, object]] = []
    for index, entry in enumerate(raw_entries):
        if isinstance(entry, str):
            plan.append({"config_path": _validate_director_plan_config_path(entry, index)})
            continue
        if isinstance(entry, dict):
            config_value = entry.get("config_path")
            if not isinstance(config_value, str) or not config_value.strip():
                raise ValueError(f"Director plan entry {index} is missing config_path")
            normalized: dict[str, object] = {
                "config_path": _validate_director_plan_config_path(config_value.strip(), index)
            }
            for key in ("campaign_name", "entry_name", "evaluation_profile"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    normalized[key] = value.strip()
            quality_gate = entry.get("quality_gate")
            if quality_gate is not None:
                if not isinstance(quality_gate, str) or quality_gate.strip() not in DIRECTOR_PLAN_QUALITY_GATES:
                    raise ValueError(
                        f"Director plan entry {index} has invalid quality_gate; expected one of {sorted(DIRECTOR_PLAN_QUALITY_GATES)}"
                    )
                normalized["quality_gate"] = quality_gate.strip()
            for key in ("campaign_max_hours", "campaign_max_jobs", "stage_candidate_limit", "shortlist_size"):
                if key not in entry or entry.get(key) is None:
                    continue
                normalized[key] = _validate_director_plan_numeric_field(key, entry.get(key), index)
            plan.append(normalized)
            continue
        raise ValueError(f"Unsupported director plan entry at index {index}")
    if not plan:
        raise ValueError("Director plan must contain at least one campaign config.")
    return {
        "plan_name": plan_name,
        "plan_source": str(plan_file_path) if plan_file_path else "inline_payload",
        "campaigns": plan,
    }


def _validate_director_plan_config_path(config_path: str, index: int) -> str:
    candidate = config_path.strip()
    if not candidate:
        raise ValueError(f"Director plan entry {index} is missing config_path")
    if not Path(candidate).exists():
        raise ValueError(f"Director plan entry {index} references missing config_path '{candidate}'")
    return candidate


def _validate_director_plan_numeric_field(field_name: str, value: object, index: int) -> int | float:
    if field_name == "campaign_max_hours":
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Director plan entry {index} has invalid {field_name}") from exc
        if numeric <= 0:
            raise ValueError(f"Director plan entry {index} has invalid {field_name}; expected > 0")
        return numeric
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Director plan entry {index} has invalid {field_name}") from exc
    minimum = 1 if field_name == "shortlist_size" else 0
    if numeric < minimum:
        comparator = "> 0" if field_name == "shortlist_size" else ">= 0"
        raise ValueError(f"Director plan entry {index} has invalid {field_name}; expected {comparator}")
    return numeric


def _write_director_spec(paths: ResearchRuntimePaths, director_id: str, payload: dict[str, object]) -> None:
    spec_path = paths.director_specs_dir / f"{director_id}.json"
    spec_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _get_director(connection: sqlite3.Connection, director_id: str) -> ResearchDirector:
    row = connection.execute("SELECT * FROM directors WHERE director_id = ?", (director_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown director '{director_id}'")
    return ResearchDirector(
        director_id=row["director_id"],
        director_name=row["director_name"],
        status=row["status"],
        spec_json=row["spec_json"],
        state_json=row["state_json"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        current_campaign_id=row["current_campaign_id"],
        successful_campaign_id=row["successful_campaign_id"],
        last_error=row["last_error"],
    )


def _director_queue(state: dict[str, object]) -> list[dict[str, object]]:
    queue = state.get("campaign_queue")
    if isinstance(queue, list):
        return [entry for entry in queue if isinstance(entry, dict)]
    return []


def _next_director_queue_entry(queue: list[dict[str, object]]) -> dict[str, object] | None:
    for entry in queue:
        if str(entry.get("status", "pending")) == "pending":
            return entry
    return None


def _director_entry_value(entry: dict[str, object], key: str, fallback: object) -> object:
    if key in entry and entry.get(key) is not None:
        return entry.get(key)
    return fallback


def _find_director_queue_entry(queue: list[dict[str, object]], queue_index: object) -> dict[str, object] | None:
    for entry in queue:
        if entry.get("queue_index") == queue_index:
            return entry
    return None


def _update_director_state(
    connection: sqlite3.Connection,
    director_id: str,
    state: dict[str, object],
    *,
    current_campaign_id: str | None | object = ...,
    successful_campaign_id: str | None | object = ...,
) -> None:
    assignments = ["state_json = ?", "updated_at = ?"]
    params: list[object] = [json.dumps(state, indent=2), _utcnow()]
    if current_campaign_id is not ...:
        assignments.append("current_campaign_id = ?")
        params.append(current_campaign_id)
    if successful_campaign_id is not ...:
        assignments.append("successful_campaign_id = ?")
        params.append(successful_campaign_id)
    params.append(director_id)
    connection.execute(
        f"UPDATE directors SET {', '.join(assignments)} WHERE director_id = ?",
        params,
    )


def _finish_director(
    connection: sqlite3.Connection,
    director: ResearchDirector,
    *,
    status: str,
    final_result: dict[str, object],
    current_campaign_id: str | None = None,
    successful_campaign_id: str | None = None,
    last_error: str | None = None,
) -> None:
    state = director.state
    state["final_result"] = final_result
    now = _utcnow()
    connection.execute(
        """
        UPDATE directors
        SET status = ?, state_json = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?),
            current_campaign_id = ?, successful_campaign_id = COALESCE(?, successful_campaign_id), last_error = ?
        WHERE director_id = ?
        """,
        (
            status,
            json.dumps(state, indent=2),
            now,
            now,
            current_campaign_id,
            successful_campaign_id,
            last_error,
            director.director_id,
        ),
    )
    _record_director_event(
        connection,
        director.director_id,
        f"director_{status}",
        f"Director finished with status {status}",
        final_result,
    )


def _record_director_event(
    connection: sqlite3.Connection,
    director_id: str,
    event_type: str,
    message: str,
    payload: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO director_events (director_id, recorded_at_utc, event_type, message, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (director_id, _utcnow(), event_type, message, json.dumps(payload, indent=2)),
    )


def _process_director_campaign_outcome(
    connection: sqlite3.Connection,
    director: ResearchDirector,
    campaign: ResearchCampaign,
    queue: list[dict[str, object]],
) -> str:
    state = director.state
    entry = next((row for row in queue if str(row.get("campaign_id", "")) == campaign.campaign_id), None)
    decision = campaign.state.get("final_decision") if isinstance(campaign.state.get("final_decision"), dict) else {}
    if entry is not None:
        entry["completed_at"] = campaign.finished_at or _utcnow()
        entry["outcome"] = decision.get("recommended_action") or campaign.status
    state["active_campaign_id"] = None
    if campaign.status == "completed" and decision.get("recommended_action") == "freeze_candidate":
        if entry is not None:
            entry["status"] = "completed"
        state["successful_campaign_id"] = campaign.campaign_id
        _finish_director(
            connection,
            director,
            status="completed",
            final_result={
                "recommended_action": "freeze_candidate",
                "reason": "director_found_viable_strategy",
                "campaign_id": campaign.campaign_id,
                "selected_profile_name": decision.get("selected_profile_name"),
            },
            current_campaign_id=None,
            successful_campaign_id=campaign.campaign_id,
        )
        return "director_completed"
    if campaign.status == "exhausted" or (
        campaign.status == "completed" and decision.get("recommended_action") != "freeze_candidate"
    ):
        if entry is not None:
            entry["status"] = "exhausted"
        _update_director_state(connection, director.director_id, state, current_campaign_id=None)
        _record_director_event(
            connection,
            director.director_id,
            "campaign_exhausted",
            f"Campaign {campaign.campaign_name} exhausted without a viable strategy",
            {"campaign_id": campaign.campaign_id, "config_path": campaign.config_path},
        )
        return "campaign_exhausted"
    if campaign.status == "stopped":
        if entry is not None:
            entry["status"] = "stopped"
        _finish_director(
            connection,
            director,
            status="stopped",
            final_result={
                "recommended_action": "stopped",
                "reason": "campaign_stopped",
                "campaign_id": campaign.campaign_id,
            },
            current_campaign_id=None,
        )
        return "director_stopped"
    if entry is not None:
        entry["status"] = "failed"
    _finish_director(
        connection,
        director,
        status="failed",
        final_result={
            "recommended_action": "failed",
            "reason": "campaign_failed",
            "campaign_id": campaign.campaign_id,
        },
        current_campaign_id=None,
        last_error=campaign.last_error,
    )
    return "director_failed"


def _find_adoptable_campaign(connection: sqlite3.Connection, config_path: str) -> str | None:
    row = connection.execute(
        """
        SELECT campaign_id
        FROM campaigns
        WHERE config_path = ?
          AND status IN ('queued', 'running')
          AND (director_id IS NULL OR director_id = '')
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (config_path,),
    ).fetchone()
    return None if row is None else str(row["campaign_id"])


def _director_step_payload(director: ResearchDirector, outcome: str) -> dict[str, object]:
    return {
        "director_id": director.director_id,
        "director_name": director.director_name,
        "status": director.status,
        "current_campaign_id": director.current_campaign_id,
        "successful_campaign_id": director.successful_campaign_id,
        "outcome": outcome,
    }


def _handle_director_runtime_error(paths: ResearchRuntimePaths, director_id: str, exc: Exception) -> None:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        director = _get_director(connection, director_id)
        if director.status not in ACTIVE_DIRECTOR_STATUSES:
            return
        state = director.state
        state["final_result"] = {
            "recommended_action": "failed",
            "reason": "director_runtime_error",
            "message": str(exc),
        }
        now = _utcnow()
        connection.execute(
            """
            UPDATE directors
            SET status = 'failed', state_json = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?), last_error = ?
            WHERE director_id = ?
            """,
            (json.dumps(state, indent=2), now, now, str(exc), director_id),
        )
        _record_director_event(
            connection,
            director_id,
            "director_failed",
            f"Director failed: {exc}",
            {"reason": "director_runtime_error", "message": str(exc)},
        )


def export_runtime_catalog(paths: ResearchRuntimePaths) -> dict[str, str]:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        rows = connection.execute(
            """
            SELECT
                artifacts.recorded_at_utc,
                artifacts.artifact_key,
                artifacts.artifact_type,
                artifacts.artifact_name,
                artifacts.primary_path,
                jobs.job_id,
                jobs.command,
                jobs.config_path,
                jobs.control_profile,
                jobs.result_json
            FROM artifacts
            INNER JOIN jobs ON jobs.job_id = artifacts.job_id
            ORDER BY artifacts.recorded_at_utc ASC, artifacts.artifact_id ASC
            """
        ).fetchall()
    entries: list[dict[str, object]] = []
    for row in rows:
        payload = _load_result_payload(row["result_json"])
        profile = payload.get("profile", {}) if isinstance(payload, dict) else {}
        summary = payload.get("result_summary", {}) if isinstance(payload, dict) else {}
        entries.append(
            {
                "recorded_at_utc": row["recorded_at_utc"],
                "artifact_type": row["artifact_type"],
                "artifact_name": row["artifact_name"],
                "profile_name": str(profile.get("profile_name", "")),
                "profile_version": str(profile.get("profile_version", "")),
                "strategy_family": str(profile.get("strategy_family", "unknown")),
                "sweep_type": str(row["command"]),
                "research_tranche": str(profile.get("research_tranche", "")),
                "control_profile": str(profile.get("control_profile", row["control_profile"] or "")),
                "evaluation_status": str(summary.get("evaluation_status", "unknown")),
                "primary_path": row["primary_path"],
                "config_path": row["config_path"],
                "job_id": row["job_id"],
                "artifact_key": row["artifact_key"],
            }
        )
    outputs = write_catalog_snapshot(paths.catalog_output_dir, entries)
    _write_runtime_status_exports(paths)
    _write_profile_history_snapshot(paths)
    return outputs


def _prepare_campaign_inputs(
    paths: ResearchRuntimePaths,
    config,
    campaign_id: str,
) -> tuple[str, str | None]:
    dataset_root = paths.runtime_root / "datasets" / campaign_id
    campaign_config = apply_runtime_overrides(
        config,
        RuntimeOverrides(
            staging_dir=dataset_root / "staging",
            canonical_dir=dataset_root / "canonical",
            raw_dir=dataset_root / "raw",
            feature_dir=dataset_root / "features",
            feature_set_name=config.features.set_name,
        ),
    )
    materialize_canonical_data(campaign_config.data)
    feature_set_ref = None
    if campaign_config.features.enabled:
        materialize_feature_set(campaign_config)
        feature_set_ref = str(PurePosixPath("datasets") / campaign_id / "features" / campaign_config.features.set_name)
    dataset_ref = str(PurePosixPath("datasets") / campaign_id / "canonical")
    return dataset_ref, feature_set_ref


def _campaign_budget_exhausted(connection: sqlite3.Connection, campaign: ResearchCampaign) -> bool:
    spec = campaign.spec
    max_jobs = int(spec.get("max_jobs", 0) or 0)
    if max_jobs > 0:
        job_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE campaign_id = ?",
                (campaign.campaign_id,),
            ).fetchone()["count"]
        )
        if job_count >= max_jobs:
            return True
    max_hours = float(spec.get("max_hours", 0.0) or 0.0)
    if max_hours > 0 and campaign.started_at:
        elapsed_hours = (
            _parse_timestamp(_utcnow()) - _parse_timestamp(campaign.started_at)
        ).total_seconds() / 3600.0
        if elapsed_hours >= max_hours:
            return True
    return False


def _submit_campaign_phase_jobs(
    paths: ResearchRuntimePaths,
    connection: sqlite3.Connection,
    campaign: ResearchCampaign,
) -> str:
    spec = campaign.spec
    state = campaign.state
    phase = campaign.phase
    base_config = load_config(campaign.config_path, evaluation_profile=spec.get("evaluation_profile"))
    seed_overrides = state.get("seed_overrides") if isinstance(state.get("seed_overrides"), dict) else {}
    seed_config = _candidate_config(base_config, phase, "seed", seed_overrides) if seed_overrides else base_config
    stage_label = _campaign_phase_label(phase)
    stage_id = uuid.uuid4().hex
    priority_start = _campaign_priority_seed(connection, campaign.campaign_id)

    if phase == "focused_operability":
        _, _, scenarios = _batch_preset_definition(seed_config, "operability")
        stage_specs = _campaign_phase_specs(
            campaign,
            phase,
            stage_id,
            stage_label,
            scenarios,
            seed_overrides,
            include_control=True,
            priority_start=priority_start,
        )
    elif phase == "benchmark_pivot":
        scenarios = _benchmark_pivot_scenarios(seed_config)
        stage_specs = _campaign_phase_specs(
            campaign,
            phase,
            stage_id,
            stage_label,
            scenarios,
            seed_overrides,
            include_control=True,
            priority_start=priority_start,
        )
    elif phase == "stability_pivot":
        scenarios = _stability_pivot_scenarios(seed_config)
        stage_specs = _campaign_phase_specs(
            campaign,
            phase,
            stage_id,
            stage_label,
            scenarios,
            seed_overrides,
            include_control=True,
            priority_start=priority_start,
        )
    elif phase == "stress_pack":
        shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
        stage_specs = _campaign_stress_specs(campaign, phase, stage_id, shortlisted, priority_start)
    else:
        final_decision = {
            "recommended_action": "exhausted",
            "reason": f"no_stage_handler_for_{phase}",
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="exhausted",
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_finished",
            message="Campaign finished with status exhausted",
            payload=final_decision,
            spec=campaign.spec,
        )
        return "campaign_exhausted"

    if not stage_specs:
        final_decision = {
            "recommended_action": "exhausted",
            "reason": f"no_jobs_generated_for_{phase}",
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="exhausted",
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_finished",
            message="Campaign finished with status exhausted",
            payload=final_decision,
            spec=campaign.spec,
        )
        return "campaign_exhausted"

    submit_jobs(paths, {"jobs": stage_specs})
    state["pending_stage"] = {
        "phase": phase,
        "stage_id": stage_id,
        "job_ids": [spec["job_id"] for spec in stage_specs],
    }
    _update_campaign_state(connection, campaign.campaign_id, phase, state)
    _record_campaign_event(
        connection,
        campaign.campaign_id,
        "stage_submitted",
        f"Submitted {len(stage_specs)} jobs for {phase}",
        {"phase": phase, "stage_id": stage_id, "job_count": len(stage_specs)},
    )
    _emit_campaign_notification(
        paths,
        campaign_id=campaign.campaign_id,
        campaign_name=campaign.campaign_name,
        event_type="stage_submitted",
        message=f"Submitted {len(stage_specs)} jobs for {phase}",
        payload={"phase": phase, "stage_id": stage_id, "job_count": len(stage_specs)},
        spec=spec,
    )
    return "stage_submitted"


def _campaign_phase_specs(
    campaign: ResearchCampaign,
    phase: str,
    stage_id: str,
    stage_label: str,
    scenarios: list[tuple[str, dict[str, object]]],
    seed_overrides: dict[str, object],
    *,
    include_control: bool,
    priority_start: int,
) -> list[dict[str, object]]:
    spec = campaign.spec
    limit = int(spec.get("stage_candidate_limit", 0) or 0)
    selected_scenarios = scenarios[:limit] if limit > 0 else scenarios
    job_specs: list[dict[str, object]] = []
    next_priority = priority_start
    if include_control:
        control_variant = _campaign_research_variant(
            phase=phase,
            stage_label=stage_label,
            scenario_name="control",
            seed_overrides=seed_overrides,
            scenario_overrides={},
            is_control=True,
        )
        job_specs.append(
            _campaign_job_spec(
                campaign,
                stage_id,
                phase,
                next_priority,
                control_variant,
                is_control=True,
            )
        )
        next_priority += 1
    for scenario_name, overrides in selected_scenarios:
        variant = _campaign_research_variant(
            phase=phase,
            stage_label=stage_label,
            scenario_name=scenario_name,
            seed_overrides=seed_overrides,
            scenario_overrides=overrides,
            is_control=False,
        )
        job_specs.append(
            _campaign_job_spec(
                campaign,
                stage_id,
                phase,
                next_priority,
                variant,
                is_control=False,
            )
        )
        next_priority += 1
    return job_specs


def _campaign_stress_specs(
    campaign: ResearchCampaign,
    phase: str,
    stage_id: str,
    shortlisted: list[dict[str, object]],
    priority_start: int,
) -> list[dict[str, object]]:
    spec = campaign.spec
    base_config = load_config(campaign.config_path, evaluation_profile=spec.get("evaluation_profile"))
    job_specs: list[dict[str, object]] = []
    next_priority = priority_start
    for candidate_row in shortlisted:
        candidate_config = _candidate_row_config(base_config, candidate_row)
        for scenario_name, overrides in _stress_scenarios(candidate_config):
            merged_overrides = _merge_overrides(
                _dict_copy(candidate_row.get("merged_overrides")),
                overrides,
            )
            variant = {
                "kind": "candidate",
                "tranche_name": phase,
                "scenario_name": scenario_name,
                "scenario_label": _campaign_phase_label(phase),
                "overrides": merged_overrides,
            }
            job_specs.append(
                _campaign_job_spec(
                    campaign,
                    stage_id,
                    phase,
                    next_priority,
                    variant,
                    is_control=False,
                    campaign_candidate_run_name=str(candidate_row.get("run_name", "")),
                    campaign_candidate_profile_name=str(candidate_row.get("profile_name", "")),
                )
            )
            next_priority += 1
    return job_specs


def _campaign_job_spec(
    campaign: ResearchCampaign,
    stage_id: str,
    phase: str,
    priority: int,
    research_variant: dict[str, object],
    *,
    is_control: bool,
    campaign_candidate_run_name: str | None = None,
    campaign_candidate_profile_name: str | None = None,
) -> dict[str, object]:
    spec = campaign.spec
    payload = {
        "job_id": uuid.uuid4().hex,
        "campaign_id": campaign.campaign_id,
        "command": "promotion-check",
        "config_path": campaign.config_path,
        "priority": priority,
        "quality_gate": str(spec.get("quality_gate", "all")),
        "evaluation_profile": _optional_text(spec.get("evaluation_profile")),
        "input_dataset_ref": spec.get("input_dataset_ref"),
        "input_dataset_ref_mode": str(spec.get("input_dataset_ref_mode", "runtime_relative")),
        "feature_set_ref": spec.get("feature_set_ref"),
        "feature_set_ref_mode": str(spec.get("feature_set_ref_mode", "raw")),
        "research_variant": research_variant,
        "campaign_phase": phase,
        "campaign_stage_id": stage_id,
        "campaign_is_control": is_control,
    }
    if campaign_candidate_run_name:
        payload["campaign_candidate_run_name"] = campaign_candidate_run_name
    if campaign_candidate_profile_name:
        payload["campaign_candidate_profile_name"] = campaign_candidate_profile_name
    return payload


def _campaign_research_variant(
    *,
    phase: str,
    stage_label: str,
    scenario_name: str,
    seed_overrides: dict[str, object],
    scenario_overrides: dict[str, object],
    is_control: bool,
) -> dict[str, object]:
    merged_overrides = _merge_overrides(seed_overrides, scenario_overrides)
    if is_control and not merged_overrides:
        return {
            "kind": "control",
            "tranche_name": phase,
            "scenario_name": "control",
            "scenario_label": stage_label,
        }
    return {
        "kind": "candidate",
        "tranche_name": phase,
        "scenario_name": scenario_name,
        "scenario_label": stage_label,
        "overrides": merged_overrides,
    }


def _process_campaign_stage(
    paths: ResearchRuntimePaths,
    connection: sqlite3.Connection,
    campaign: ResearchCampaign,
    pending_stage: dict[str, object],
    stage_rows: list[sqlite3.Row],
) -> str:
    phase = str(pending_stage.get("phase", campaign.phase))
    state = campaign.state
    base_config = load_config(campaign.config_path, evaluation_profile=campaign.spec.get("evaluation_profile"))
    completed_jobs = [row for row in stage_rows if row["status"] == "completed"]
    if phase in {"focused_operability", "benchmark_pivot", "stability_pivot"}:
        outcome = _process_search_stage(paths, connection, campaign, state, phase, base_config, completed_jobs)
    elif phase == "stress_pack":
        outcome = _process_stress_stage(paths, connection, campaign, state, base_config, completed_jobs)
    else:
        outcome = "unknown_phase"
    state = _get_campaign(connection, campaign.campaign_id).state
    state["pending_stage"] = None
    _update_campaign_state(connection, campaign.campaign_id, _get_campaign(connection, campaign.campaign_id).phase, state)
    return outcome


def _process_search_stage(
    paths: ResearchRuntimePaths,
    connection: sqlite3.Connection,
    campaign: ResearchCampaign,
    state: dict[str, object],
    phase: str,
    base_config,
    completed_jobs: list[sqlite3.Row],
) -> str:
    rows = [_campaign_candidate_row(base_config, row) for row in completed_jobs]
    control_row = next((row for row in rows if bool(row.get("campaign_is_control", False))), None)
    candidate_rows = [row for row in rows if not bool(row.get("campaign_is_control", False))]
    if control_row is None:
        control_row = state.get("control_row")
    if not isinstance(control_row, dict):
        final_decision = {
            "recommended_action": "exhausted",
            "reason": f"{phase}_control_missing",
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="failed",
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_failed",
            message=f"Campaign failed in {phase}: control missing",
            payload=final_decision,
            spec=campaign.spec,
        )
        return "campaign_failed"
    decision = _select_operability_candidate(control_row, candidate_rows)
    artifacts = write_tranche_report(
        output_dir=paths.catalog_output_dir,
        report_name=f"{campaign.campaign_name}_{phase}_report",
        tranche_name=phase,
        control_row=control_row,
        candidate_rows=candidate_rows,
        decision=decision,
    )
    result = {
        "control": control_row,
        "candidates": candidate_rows,
        "top_candidate": decision.get("selected_candidate"),
        "decision": {key: value for key, value in decision.items() if key != "selected_candidate"},
        "artifacts": artifacts,
    }
    state["control_row"] = control_row
    pool = [row for row in state.get("candidate_pool", []) if isinstance(row, dict)]
    pool.extend(candidate_rows)
    state["candidate_pool"] = pool
    if phase == "focused_operability":
        state["focused_result"] = result
        if decision.get("selected_candidate"):
            state["seed_overrides"] = _dict_copy(decision["selected_candidate"].get("merged_overrides"))
        next_phase = "stress_pack" if bool(decision.get("focused_success", False)) else "benchmark_pivot"
    elif phase == "benchmark_pivot":
        state["pivot_result"] = result
        if decision.get("selected_candidate"):
            state["seed_overrides"] = _dict_copy(decision["selected_candidate"].get("merged_overrides"))
            next_phase = "stress_pack"
        else:
            next_phase = "stability_pivot"
    else:
        state["stability_result"] = result
        if decision.get("selected_candidate"):
            state["seed_overrides"] = _dict_copy(decision["selected_candidate"].get("merged_overrides"))
            next_phase = "stress_pack"
        else:
            next_phase = "exhausted"
    if next_phase == "stress_pack":
        state["shortlisted"] = _operability_shortlist(
            control_row,
            [row for row in state.get("candidate_pool", []) if isinstance(row, dict)],
            limit=int(campaign.spec.get("shortlist_size", 3) or 3),
        )
    latest_report_path = _write_campaign_program_report(paths, campaign, state)
    if next_phase == "exhausted":
        final_decision = {
            "recommended_action": "exhausted",
            "reason": f"{phase}_did_not_produce_viable_candidate",
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="exhausted",
            latest_report_path=latest_report_path,
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_finished",
            message="Campaign finished with status exhausted",
            payload={**final_decision, "latest_report_path": latest_report_path},
            spec=campaign.spec,
        )
        return "campaign_exhausted"
    _update_campaign_state(connection, campaign.campaign_id, next_phase, state, latest_report_path=latest_report_path)
    _record_campaign_event(
        connection,
        campaign.campaign_id,
        "stage_processed",
        f"Processed {phase} and advanced to {next_phase}",
        {"phase": phase, "next_phase": next_phase},
    )
    _emit_campaign_notification(
        paths,
        campaign_id=campaign.campaign_id,
        campaign_name=campaign.campaign_name,
        event_type="stage_processed",
        message=f"Processed {phase} and advanced to {next_phase}",
        payload={"phase": phase, "next_phase": next_phase, "latest_report_path": latest_report_path},
        spec=campaign.spec,
    )
    return "stage_processed"


def _process_stress_stage(
    paths: ResearchRuntimePaths,
    connection: sqlite3.Connection,
    campaign: ResearchCampaign,
    state: dict[str, object],
    base_config,
    completed_jobs: list[sqlite3.Row],
) -> str:
    grouped: dict[str, list[dict[str, object]]] = {}
    candidate_names: dict[str, str] = {}
    for row in completed_jobs:
        payload = _load_result_payload(row["result_json"])
        promotion = payload.get("promotion_decision")
        if not isinstance(promotion, dict):
            continue
        spec_json = json.loads(row["spec_json"])
        variant = spec_json.get("research_variant", {})
        config = base_config
        if isinstance(variant, dict):
            config = _apply_variant_to_config(base_config, variant)
        scenario_row = _candidate_row_from_promotion(
            config,
            promotion,
            scenario_name=str(variant.get("scenario_name", "stress")),
            scenario_label=str(variant.get("scenario_label", "stress")),
            tranche_name="stress_pack",
        )
        scenario_row["non_broken"] = _stress_row_non_broken(scenario_row)
        scenario_row["merged_overrides"] = _dict_copy(variant.get("overrides"))
        candidate_run_name = str(spec_json.get("campaign_candidate_run_name", "unknown"))
        candidate_names[candidate_run_name] = str(spec_json.get("campaign_candidate_profile_name", "unknown"))
        grouped.setdefault(candidate_run_name, []).append(scenario_row)

    stress_results: list[dict[str, object]] = []
    shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
    for candidate_row in shortlisted:
        candidate_run_name = str(candidate_row.get("run_name", "unknown"))
        scenarios = grouped.get(candidate_run_name, [])
        non_broken_count = sum(1 for row in scenarios if bool(row.get("non_broken", False)))
        stress_results.append(
            {
                "candidate_run_name": candidate_run_name,
                "candidate_profile_name": candidate_names.get(
                    candidate_run_name,
                    str(candidate_row.get("profile_name", "unknown")),
                ),
                "scenario_count": len(scenarios),
                "non_broken_count": non_broken_count,
                "broken_count": len(scenarios) - non_broken_count,
                "stress_ok": bool(scenarios) and non_broken_count == len(scenarios),
                "scenarios": scenarios,
            }
        )
    state["stress_results"] = stress_results
    selected_candidate, final_decision = _campaign_stress_decision(campaign, state, stress_results)
    latest_report_path = _write_campaign_program_report(paths, campaign, state, final_decision=final_decision)
    if selected_candidate is not None and final_decision["recommended_action"] == "freeze_candidate":
        write_promotion_artifacts(
            output_dir=paths.catalog_output_dir,
            report_name=f"{campaign.campaign_name}_promotion_report",
            promotion_decision=dict(selected_candidate.get("promotion_decision", {})),
            config_path=f"generated:{selected_candidate.get('profile_name', 'candidate')}",
        )
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="completed",
            latest_report_path=latest_report_path,
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_finished",
            message="Campaign finished with status completed",
            payload={**final_decision, "latest_report_path": latest_report_path},
            spec=campaign.spec,
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="strategy_promoted",
            message="Strategy promoted and frozen for review",
            payload={**final_decision, "latest_report_path": latest_report_path},
            spec=campaign.spec,
        )
        return "campaign_completed"

    if not state.get("pivot_result"):
        next_phase = "benchmark_pivot"
    elif not state.get("stability_result"):
        next_phase = "stability_pivot"
    else:
        _set_campaign_final_decision(
            connection,
            campaign,
            final_decision,
            status="exhausted",
            latest_report_path=latest_report_path,
        )
        _emit_campaign_notification(
            paths,
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            event_type="campaign_finished",
            message="Campaign finished with status exhausted",
            payload={**final_decision, "latest_report_path": latest_report_path},
            spec=campaign.spec,
        )
        return "campaign_exhausted"
    _update_campaign_state(connection, campaign.campaign_id, next_phase, state, latest_report_path=latest_report_path)
    _record_campaign_event(
        connection,
        campaign.campaign_id,
        "stress_processed",
        f"Stress pack did not freeze a candidate; advancing to {next_phase}",
        {"next_phase": next_phase, "reason": final_decision.get("reason", "unknown")},
    )
    _emit_campaign_notification(
        paths,
        campaign_id=campaign.campaign_id,
        campaign_name=campaign.campaign_name,
        event_type="stress_processed",
        message=f"Stress pack did not freeze a candidate; advancing to {next_phase}",
        payload={
            "next_phase": next_phase,
            "reason": final_decision.get("reason", "unknown"),
            "latest_report_path": latest_report_path,
        },
        spec=campaign.spec,
    )
    return "stage_processed"


def _campaign_candidate_row(base_config, row: sqlite3.Row) -> dict[str, object]:
    payload = _load_result_payload(row["result_json"])
    promotion = payload.get("promotion_decision")
    if not isinstance(promotion, dict):
        return {}
    spec = json.loads(row["spec_json"])
    variant = spec.get("research_variant", {})
    config = _apply_variant_to_config(base_config, variant)
    candidate_row = _candidate_row_from_promotion(
        config,
        promotion,
        scenario_name=str(variant.get("scenario_name", "unknown")),
        scenario_label=str(variant.get("scenario_label", "campaign")),
        tranche_name=str(variant.get("tranche_name", spec.get("campaign_phase", "campaign"))),
    )
    candidate_row["merged_overrides"] = _dict_copy(variant.get("overrides"))
    candidate_row["campaign_is_control"] = bool(spec.get("campaign_is_control", False))
    return candidate_row


def _campaign_stress_decision(
    campaign: ResearchCampaign,
    state: dict[str, object],
    stress_results: list[dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    stress_by_run = {str(result.get("candidate_run_name", "")): result for result in stress_results}
    shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
    ranked_shortlist = sorted(
        shortlisted,
        key=lambda row: (
            bool(stress_by_run.get(str(row.get("run_name", "")), {}).get("stress_ok", False)),
            row.get("decision_score", _candidate_decision_score(row)),
        ),
        reverse=True,
    )
    selected_candidate = ranked_shortlist[0] if ranked_shortlist else None
    selected_stress = None if selected_candidate is None else stress_by_run.get(str(selected_candidate.get("run_name", "")))
    stress_ok = bool(selected_stress and selected_stress.get("stress_ok", False))
    if selected_candidate is not None and bool(selected_candidate.get("eligible", False)) and stress_ok:
        return selected_candidate, {
            "recommended_action": "freeze_candidate",
            "reason": "candidate_passed_promotion_and_stress_pack",
            "selected_run_name": selected_candidate.get("run_name"),
            "selected_profile_name": selected_candidate.get("profile_name"),
            "selected_candidate_eligible": True,
            "selected_stress_ok": True,
            "pivot_used": bool(state.get("pivot_result")),
        }
    return selected_candidate, {
        "recommended_action": "continue_research",
        "reason": "no_stress_validated_candidate",
        "selected_run_name": None if selected_candidate is None else selected_candidate.get("run_name"),
        "selected_profile_name": None if selected_candidate is None else selected_candidate.get("profile_name"),
        "selected_candidate_eligible": False if selected_candidate is None else bool(selected_candidate.get("eligible", False)),
        "selected_stress_ok": stress_ok,
        "pivot_used": bool(state.get("pivot_result")),
    }


def _write_campaign_program_report(
    paths: ResearchRuntimePaths,
    campaign: ResearchCampaign,
    state: dict[str, object],
    *,
    final_decision: dict[str, object] | None = None,
) -> str:
    decision = final_decision or (
        state.get("final_decision")
        if isinstance(state.get("final_decision"), dict)
        else {
            "recommended_action": "continue_research",
            "reason": "campaign_in_progress",
            "selected_run_name": None,
            "selected_profile_name": None,
            "selected_candidate_eligible": False,
            "selected_stress_ok": False,
            "pivot_used": bool(state.get("pivot_result")),
        }
    )
    artifacts = write_operability_program_report(
        output_dir=paths.catalog_output_dir,
        report_name=f"{campaign.campaign_name}_operability_program",
        control_row=state.get("control_row") or {},
        focused_result=state.get("focused_result") or {"decision": {}},
        pivot_result=(state.get("pivot_result") or state.get("stability_result")),
        shortlisted=[row for row in state.get("shortlisted", []) if isinstance(row, dict)],
        stress_results=[row for row in state.get("stress_results", []) if isinstance(row, dict)],
        final_decision=decision,
    )
    return str(artifacts["summary_md"])


def _apply_variant_to_config(base_config, variant: object):
    if isinstance(variant, dict):
        return apply_research_variant(base_config, variant)
    return base_config


def _campaign_priority_seed(connection: sqlite3.Connection, campaign_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(priority), 99) AS priority FROM jobs WHERE campaign_id = ?",
        (campaign_id,),
    ).fetchone()
    return int(row["priority"] or 99) + 1


def _campaign_stage_jobs(connection: sqlite3.Connection, job_ids: list[str]) -> list[sqlite3.Row]:
    if not job_ids:
        return []
    placeholders = ",".join("?" for _ in job_ids)
    return connection.execute(
        f"SELECT job_id, status, spec_json, result_json FROM jobs WHERE job_id IN ({placeholders}) ORDER BY created_at ASC",
        tuple(job_ids),
    ).fetchall()


def _get_campaign(connection: sqlite3.Connection, campaign_id: str) -> ResearchCampaign:
    row = connection.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown campaign '{campaign_id}'")
    return ResearchCampaign(
        campaign_id=row["campaign_id"],
        director_id=row["director_id"],
        campaign_name=row["campaign_name"],
        config_path=row["config_path"],
        status=row["status"],
        phase=row["phase"],
        spec_json=row["spec_json"],
        state_json=row["state_json"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        latest_report_path=row["latest_report_path"],
        last_error=row["last_error"],
    )


def _update_campaign_state(
    connection: sqlite3.Connection,
    campaign_id: str,
    phase: str,
    state: dict[str, object],
    *,
    latest_report_path: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE campaigns
        SET phase = ?, state_json = ?, updated_at = ?, latest_report_path = COALESCE(?, latest_report_path)
        WHERE campaign_id = ?
        """,
        (phase, json.dumps(state, indent=2), _utcnow(), latest_report_path, campaign_id),
    )


def _set_campaign_final_decision(
    connection: sqlite3.Connection,
    campaign: ResearchCampaign,
    final_decision: dict[str, object],
    *,
    status: str,
    latest_report_path: str | None = None,
) -> None:
    state = campaign.state
    state["final_decision"] = final_decision
    now = _utcnow()
    connection.execute(
        """
        UPDATE campaigns
        SET status = ?, state_json = ?, updated_at = ?, finished_at = ?, latest_report_path = COALESCE(?, latest_report_path)
        WHERE campaign_id = ?
        """,
        (status, json.dumps(state, indent=2), now, now, latest_report_path, campaign.campaign_id),
    )
    _record_campaign_event(
        connection,
        campaign.campaign_id,
        "campaign_finished",
        f"Campaign finished with status {status}",
        final_decision,
    )


def _mark_campaign_finished(connection: sqlite3.Connection, campaign: ResearchCampaign, *, status: str) -> None:
    now = _utcnow()
    connection.execute(
        "UPDATE campaigns SET status = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?) WHERE campaign_id = ?",
        (status, now, now, campaign.campaign_id),
    )


def _record_campaign_event(
    connection: sqlite3.Connection,
    campaign_id: str,
    event_type: str,
    message: str,
    payload: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO campaign_events (campaign_id, recorded_at_utc, event_type, message, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (campaign_id, _utcnow(), event_type, message, json.dumps(payload, indent=2)),
    )


def _emit_campaign_notification(
    paths: ResearchRuntimePaths,
    *,
    campaign_id: str,
    campaign_name: str,
    event_type: str,
    message: str,
    payload: dict[str, object],
    spec: dict[str, object],
) -> None:
    exports_dir = paths.runtime_root / "exports"
    notifications_dir = exports_dir / "campaign_notifications"
    exports_dir.mkdir(parents=True, exist_ok=True)
    notifications_dir.mkdir(parents=True, exist_ok=True)

    recorded_at = _utcnow()
    notify_events = {
        str(value)
        for value in spec.get("notify_events", DEFAULT_NOTIFICATION_EVENTS)
        if isinstance(value, str) and value
    }
    notification_command = _optional_text(spec.get("notification_command"))
    severity = _notification_severity(event_type, payload)
    payload_stem = (
        f"{_timestamp_slug(recorded_at)}_{_safe_filename_component(campaign_name)}_"
        f"{_safe_filename_component(event_type)}_{uuid.uuid4().hex[:8]}"
    )
    payload_path = notifications_dir / f"{payload_stem}.json"
    record = {
        "recorded_at_utc": recorded_at,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "payload": payload,
        "payload_path": str(payload_path),
        "notification_command": notification_command,
        "notification_requested": bool(notification_command and event_type in notify_events),
        "hook": {
            "executed": False,
            "success": None,
            "exit_code": None,
            "stdout_path": None,
            "stderr_path": None,
            "error": None,
        },
        "agent_dispatches": [],
    }
    payload_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    if notification_command and event_type in notify_events:
        stdout_path = notifications_dir / f"{payload_stem}.stdout.log"
        stderr_path = notifications_dir / f"{payload_stem}.stderr.log"
        env = os.environ.copy()
        env.update(
            {
                "TROTTERS_CAMPAIGN_ID": campaign_id,
                "TROTTERS_CAMPAIGN_NAME": campaign_name,
                "TROTTERS_EVENT_TYPE": event_type,
                "TROTTERS_EVENT_SEVERITY": severity,
                "TROTTERS_EVENT_MESSAGE": message,
                "TROTTERS_EVENT_RECORDED_AT_UTC": recorded_at,
                "TROTTERS_NOTIFICATION_PAYLOAD_PATH": str(payload_path),
                "TROTTERS_RUNTIME_ROOT": str(paths.runtime_root),
                "TROTTERS_CATALOG_OUTPUT_DIR": str(paths.catalog_output_dir),
            }
        )
        try:
            completed = subprocess.run(
                notification_command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=Path.cwd(),
                env=env,
                check=False,
            )
            stdout_path.write_text(completed.stdout or "", encoding="utf-8")
            stderr_path.write_text(completed.stderr or "", encoding="utf-8")
            record["hook"] = {
                "executed": True,
                "success": completed.returncode == 0,
                "exit_code": completed.returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "error": None,
            }
        except Exception as exc:
            stderr_path.write_text(str(exc), encoding="utf-8")
            record["hook"] = {
                "executed": True,
                "success": False,
                "exit_code": None,
                "stdout_path": None,
                "stderr_path": str(stderr_path),
                "error": str(exc),
            }
    for dispatch in _agent_dispatch_specs(record):
        record["agent_dispatches"].append(_dispatch_agent_trigger(dispatch))
    payload_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with (exports_dir / CAMPAIGN_NOTIFICATION_JSONL).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")


def _agent_dispatch_specs(record: dict[str, object]) -> list[dict[str, object]]:
    event_type = str(record.get("event_type", "") or "").strip().lower()
    agent_id = AGENT_TRIGGER_EVENT_MAP.get(event_type)
    if not agent_id:
        return []
    campaign_id = str(record.get("campaign_id", "") or "").strip()
    campaign_name = str(record.get("campaign_name", "") or "").strip()
    recorded_at = str(record.get("recorded_at_utc", "") or "").strip()
    severity = str(record.get("severity", "") or "").strip()
    message = str(record.get("message", "") or "").strip()
    payload_path = str(record.get("payload_path", "") or "").strip()
    if agent_id == "research-triage":
        session_id = f"research-triage-{campaign_id}" if campaign_id else None
        dispatch_message = (
            f"Process a research-triage trigger for campaign {campaign_id or 'unknown'}"
            f" ({campaign_name or 'unknown'}) after {event_type} at {recorded_at}. "
            f"Severity: {severity or 'unknown'}. Message: {message or 'none'}. "
            f"Notification payload: {payload_path or 'n/a'}. "
            "Use `trotters_review_pack` with `action: campaign_triage` first. Then call "
            "`trotters_summaries` with `action: record`, `summaryType: campaign_triage_summary`, "
            "exact field names `status`, `classification`, `recommendedAction`, `message`, "
            "`evidence`, `artifactRefs`, `campaignId`, `directorId`, `fingerprint`, and "
            "`suppressIfRecent: true`. End with one short confirmation sentence and do not ask questions."
        )
    else:
        session_id = f"failure-postmortem-{campaign_id}" if campaign_id else None
        dispatch_message = (
            f"Process a failure-postmortem trigger for campaign {campaign_id or 'unknown'}"
            f" ({campaign_name or 'unknown'}) after {event_type} at {recorded_at}. "
            f"Severity: {severity or 'unknown'}. Message: {message or 'none'}. "
            f"Notification payload: {payload_path or 'n/a'}. "
            "Use `trotters_review_pack` with `action: failure_postmortem` first. Then call "
            "`trotters_summaries` with `action: record`, `summaryType: failure_postmortem_summary`, "
            "exact field names `status`, `classification`, `recommendedAction`, `message`, "
            "`evidence`, `artifactRefs`, `campaignId`, `directorId`, `fingerprint`, and "
            "`suppressIfRecent: true`. End with one short confirmation sentence and do not ask questions."
        )
    return [
        {
            "agent_id": agent_id,
            "campaign_id": campaign_id or None,
            "event_type": event_type,
            "session_id": session_id,
            "message": dispatch_message,
        }
    ]


def _dispatch_agent_trigger(dispatch: dict[str, object]) -> dict[str, object]:
    base_url = str(os.environ.get("TROTTERS_OPS_BRIDGE_BASE", "") or "").strip()
    token = str(os.environ.get("TROTTERS_OPS_BRIDGE_TOKEN", "") or "").strip()
    if not base_url or not token:
        return {
            "agent_id": dispatch.get("agent_id"),
            "attempted": False,
            "success": False,
            "error": "ops_bridge_not_configured",
        }
    agent_id = str(dispatch.get("agent_id", "") or "").strip()
    payload = {
        "message": str(dispatch.get("message", "") or ""),
        "campaign_id": dispatch.get("campaign_id"),
        "event_type": dispatch.get("event_type"),
        "session_id": dispatch.get("session_id"),
        "thinking": "low",
        "timeout_seconds": 180,
    }
    request = Request(
        f"{base_url}/api/v1/agents/{quote(agent_id)}/dispatch",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
            "X-Trotters-Actor": "runtime-notifier",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=190) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            response_payload = json.loads(response_text) if response_text.strip() else {}
        return {
            "agent_id": agent_id,
            "attempted": True,
            "success": True,
            "response": response_payload,
        }
    except HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        return {
            "agent_id": agent_id,
            "attempted": True,
            "success": False,
            "status_code": exc.code,
            "error": error_text or str(exc),
        }
    except (URLError, TimeoutError, ValueError) as exc:
        return {
            "agent_id": agent_id,
            "attempted": True,
            "success": False,
            "error": str(exc),
        }


def _notification_severity(event_type: str, payload: dict[str, object]) -> str:
    normalized = event_type.lower()
    if normalized == "strategy_promoted":
        return "success"
    if normalized == "campaign_retry_scheduled":
        return "warning"
    if normalized in {"campaign_failed"}:
        return "error"
    if normalized in {"campaign_stopped"}:
        return "warning"
    if normalized == "campaign_finished":
        action = str(payload.get("recommended_action", "")).lower()
        if action == "freeze_candidate":
            return "success"
        if action in {"exhausted", "failed", "stopped"}:
            return "warning" if action != "failed" else "error"
        return "success"
    if normalized in {"stress_processed"}:
        return "warning"
    return "info"


def _is_retryable_runtime_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.OperationalError):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in RETRYABLE_RUNTIME_ERROR_MARKERS)


def _handle_campaign_runtime_error(
    paths: ResearchRuntimePaths,
    campaign_id: str,
    exc: Exception,
) -> None:
    initialize_runtime(paths)
    with _connect(paths) as connection:
        campaign = _get_campaign(connection, campaign_id)
        if campaign.status not in ACTIVE_CAMPAIGN_STATUSES:
            return
        state = campaign.state
        retry_count = int(state.get("runtime_retry_count", 0) or 0)
        retryable = _is_retryable_runtime_error(exc) and retry_count < CAMPAIGN_RUNTIME_RETRY_LIMIT
        if retryable:
            retry_count += 1
            state["runtime_retry_count"] = retry_count
            state["last_runtime_error"] = str(exc)
            state.setdefault("runtime_retry_errors", []).append(str(exc))
            now = _utcnow()
            connection.execute(
                """
                UPDATE campaigns
                SET status = 'running', state_json = ?, updated_at = ?, last_error = ?
                WHERE campaign_id = ?
                """,
                (json.dumps(state, indent=2), now, str(exc), campaign_id),
            )
            _record_campaign_event(
                connection,
                campaign_id,
                "campaign_retry_scheduled",
                f"Retrying campaign after runtime error: {exc}",
                {
                    "retry_count": retry_count,
                    "retry_limit": CAMPAIGN_RUNTIME_RETRY_LIMIT,
                    "error": str(exc),
                },
            )
            campaign_name = campaign.campaign_name
            spec = campaign.spec
        else:
            state["pending_stage"] = None
            final_decision = {
                "recommended_action": "failed",
                "reason": "campaign_runtime_error",
                "selected_run_name": None,
                "selected_profile_name": None,
                "selected_candidate_eligible": False,
                "selected_stress_ok": False,
                "pivot_used": bool(state.get("pivot_result")),
                "error": str(exc),
            }
            state["final_decision"] = final_decision
            now = _utcnow()
            connection.execute(
                """
                UPDATE campaigns
                SET status = 'failed', state_json = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?), last_error = ?
                WHERE campaign_id = ?
                """,
                (json.dumps(state, indent=2), now, now, str(exc), campaign_id),
            )
            _record_campaign_event(
                connection,
                campaign_id,
                "campaign_failed",
                f"Campaign failed due to runtime error: {exc}",
                final_decision,
            )
            campaign_name = campaign.campaign_name
            spec = campaign.spec
    if retryable:
        _emit_campaign_notification(
            paths,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            event_type="campaign_retry_scheduled",
            message=f"Retrying campaign after runtime error ({retry_count}/{CAMPAIGN_RUNTIME_RETRY_LIMIT}): {exc}",
            payload={
                "retry_count": retry_count,
                "retry_limit": CAMPAIGN_RUNTIME_RETRY_LIMIT,
                "error": str(exc),
            },
            spec=spec,
        )
        return
    _emit_campaign_notification(
        paths,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        event_type="campaign_failed",
        message=f"Campaign failed due to runtime error: {exc}",
        payload=final_decision,
        spec=spec,
    )


def _campaign_step_payload(campaign: ResearchCampaign, outcome: str) -> dict[str, object]:
    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.campaign_name,
        "status": campaign.status,
        "phase": campaign.phase,
        "latest_report_path": campaign.latest_report_path,
        "outcome": outcome,
    }


def _campaign_phase_label(phase: str) -> str:
    labels = {
        "focused_operability": "operability",
        "benchmark_pivot": "pivot",
        "stability_pivot": "stability",
        "stress_pack": "stress",
    }
    return labels.get(phase, phase)


def _merge_overrides(base: dict[str, object] | None, extra: dict[str, object] | None) -> dict[str, object]:
    merged: dict[str, object] = {}
    if isinstance(base, dict):
        merged.update(base)
    if isinstance(extra, dict):
        merged.update(extra)
    return merged


def _dict_copy(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def collect_artifacts(payload: object) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []

    def visit(value: object, key_path: list[str]) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(nested, [*key_path, str(key)])
            return
        if isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, [*key_path, str(index)])
            return
        if not isinstance(value, str):
            return
        path = Path(value)
        if path.suffix.lower() not in PATH_SUFFIXES:
            return
        artifacts.append(
            {
                "artifact_key": ".".join(key_path) or "artifact",
                "artifact_type": key_path[0] if key_path else "artifact",
                "artifact_name": path.name,
                "path": value,
            }
        )

    visit(payload, [])
    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for artifact in artifacts:
        deduped[(artifact["artifact_key"], artifact["path"])] = artifact
    return list(deduped.values())


def summarize_job_result(command: str, payload: dict[str, object]) -> dict[str, object]:
    promotion = payload.get("promotion_decision")
    if isinstance(promotion, dict):
        return {
            "evaluation_status": "pass" if bool(promotion.get("eligible", False)) else "fail",
            "recommended_action": promotion.get("recommended_action", "retain"),
        }
    evaluation = payload.get("evaluation")
    if isinstance(evaluation, dict):
        return {"evaluation_status": str(evaluation.get("status", "unknown"))}
    runs = payload.get("runs")
    if isinstance(runs, list):
        for row in runs:
            if isinstance(row, dict):
                item_evaluation = row.get("evaluation")
                if isinstance(item_evaluation, dict):
                    return {"evaluation_status": str(item_evaluation.get("status", "unknown")), "run_count": len(runs)}
        return {"evaluation_status": "unknown", "run_count": len(runs)}
    return {"evaluation_status": "unknown", "command": command}


def _normalize_job_specs(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("jobs"), list):
            return [dict(spec) for spec in payload["jobs"] if isinstance(spec, dict)]
        return [dict(payload)]
    if isinstance(payload, list):
        return [dict(spec) for spec in payload if isinstance(spec, dict)]
    raise ValueError("Job spec must be a JSON object or list of objects")


def _finish_attempt(
    connection: sqlite3.Connection,
    job_id: str,
    worker_id: str,
    status: str,
    finished_at: str,
    exit_code: int,
    stdout_path: Path,
    stderr_path: Path,
    error_message: str | None,
) -> None:
    row = connection.execute(
        """
        SELECT attempt_id
        FROM job_attempts
        WHERE job_id = ? AND worker_id = ? AND status = 'running'
        ORDER BY attempt_id DESC
        LIMIT 1
        """,
        (job_id, worker_id),
    ).fetchone()
    if row is None:
        return
    connection.execute(
        """
        UPDATE job_attempts
        SET status = ?, finished_at = ?, exit_code = ?, stdout_path = ?, stderr_path = ?, error_message = ?
        WHERE attempt_id = ?
        """,
        (status, finished_at, exit_code, str(stdout_path), str(stderr_path), error_message, row["attempt_id"]),
    )


def _prune_stale_workers(connection: sqlite3.Connection, cutoff: str) -> None:
    stale_workers = connection.execute(
        """
        SELECT workers.worker_id
        FROM workers
        LEFT JOIN worker_heartbeats ON worker_heartbeats.worker_id = workers.worker_id
        WHERE COALESCE(worker_heartbeats.heartbeat_at, workers.updated_at) < ?
          AND (
              workers.current_job_id IS NULL
              OR NOT EXISTS (
                  SELECT 1
                  FROM jobs
                  WHERE jobs.job_id = workers.current_job_id
                    AND jobs.status = 'running'
                    AND jobs.leased_by = workers.worker_id
              )
          )
        """,
        (cutoff,),
    ).fetchall()
    for row in stale_workers:
        connection.execute("DELETE FROM workers WHERE worker_id = ?", (row["worker_id"],))
        connection.execute("DELETE FROM worker_heartbeats WHERE worker_id = ?", (row["worker_id"],))


def _recover_stale_running_jobs(connection: sqlite3.Connection, cutoff: str) -> dict[str, int]:
    stale_jobs = connection.execute(
        """
        SELECT jobs.job_id, jobs.attempt_count, jobs.max_attempts, jobs.leased_by
        FROM jobs
        LEFT JOIN workers ON workers.worker_id = jobs.leased_by
        LEFT JOIN worker_heartbeats ON worker_heartbeats.worker_id = jobs.leased_by
        WHERE jobs.status = 'running'
          AND (
              jobs.leased_by IS NULL
              OR workers.worker_id IS NULL
              OR COALESCE(worker_heartbeats.heartbeat_at, workers.updated_at, jobs.updated_at) < ?
          )
        """,
        (cutoff,),
    ).fetchall()
    now = _utcnow()
    requeued = 0
    failed = 0
    for row in stale_jobs:
        next_status = "queued" if int(row["attempt_count"]) < int(row["max_attempts"]) else "failed"
        error_message = "worker_heartbeat_stale" if next_status == "failed" else "worker_recovered"
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, leased_by = NULL, lease_expires_at = NULL, updated_at = ?,
                finished_at = CASE WHEN ? = 'failed' THEN ? ELSE finished_at END,
                error_message = CASE WHEN ? = 'failed' THEN ? ELSE error_message END
            WHERE job_id = ?
            """,
            (next_status, now, next_status, now, next_status, error_message, row["job_id"]),
        )
        if row["leased_by"]:
            connection.execute(
                "UPDATE workers SET status = 'idle', current_job_id = NULL, updated_at = ? WHERE worker_id = ?",
                (now, row["leased_by"]),
            )
        if next_status == "queued":
            requeued += 1
        else:
            failed += 1
    return {"requeued": requeued, "failed": failed}


def _write_runtime_status_exports(paths: ResearchRuntimePaths) -> None:
    status_dir = paths.runtime_root / "exports"
    status_dir.mkdir(parents=True, exist_ok=True)
    status = runtime_status(paths)
    (status_dir / "runtime_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    jobs = status.get("jobs", [])
    if isinstance(jobs, list):
        _write_csv(status_dir / "jobs.csv", jobs)
    workers = status.get("workers", [])
    if isinstance(workers, list):
        _write_csv(status_dir / "workers.csv", workers)
    campaigns = status.get("campaigns", [])
    if isinstance(campaigns, list):
        _write_csv(status_dir / "campaigns.csv", campaigns)
    directors = status.get("directors", [])
    if isinstance(directors, list):
        _write_csv(status_dir / "directors.csv", directors)


def _write_profile_history_snapshot(paths: ResearchRuntimePaths) -> None:
    with _connect(paths) as connection:
        rows = connection.execute(
            "SELECT result_json FROM jobs WHERE status = 'completed' AND result_json IS NOT NULL ORDER BY finished_at ASC"
        ).fetchall()
    history_by_profile: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        payload = _load_result_payload(row["result_json"])
        promotion = payload.get("promotion_decision") if isinstance(payload, dict) else None
        if not isinstance(promotion, dict):
            continue
        profile = promotion.get("profile", {})
        if not isinstance(profile, dict):
            continue
        profile_name = str(profile.get("profile_name", "") or "")
        if not profile_name:
            continue
        history_by_profile.setdefault(profile_name, []).append(promotion)
    history_dir = paths.catalog_output_dir / "profile_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    for profile_name, entries in history_by_profile.items():
        content = "\n".join(json.dumps(entry) for entry in entries)
        if content:
            content += "\n"
        (history_dir / f"{profile_name}.jsonl").write_text(content, encoding="utf-8")


def _build_status_snapshot(connection: sqlite3.Connection) -> dict[str, object]:
    counts = {
        row["status"]: row["count"]
        for row in connection.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
    }
    workers = [
        dict(row)
        for row in connection.execute(
            """
            SELECT workers.worker_id, workers.status, workers.current_job_id, workers.updated_at, worker_heartbeats.heartbeat_at
            FROM workers
            LEFT JOIN worker_heartbeats ON worker_heartbeats.worker_id = workers.worker_id
            ORDER BY workers.worker_id ASC
            """
        ).fetchall()
    ]
    jobs = [
        dict(row)
        for row in connection.execute(
            """
            SELECT job_id, campaign_id, command, status, priority, attempt_count, max_attempts, leased_by, output_root, created_at, updated_at
            FROM jobs
            ORDER BY priority ASC, created_at ASC
            """
        ).fetchall()
    ]
    campaigns = [
        dict(row)
        for row in connection.execute(
            """
            SELECT campaign_id, director_id, campaign_name, status, phase, created_at, updated_at, finished_at,
                   latest_report_path, last_error
            FROM campaigns
            ORDER BY created_at ASC
            """
        ).fetchall()
    ]
    directors = [
        dict(row)
        for row in connection.execute(
            """
            SELECT director_id, director_name, status, current_campaign_id, successful_campaign_id, created_at,
                   updated_at, finished_at, last_error
            FROM directors
            ORDER BY created_at ASC
            """
        ).fetchall()
    ]
    return {
        "database_path": str(connection.execute("PRAGMA database_list").fetchone()["file"]),
        "counts": counts,
        "workers": workers,
        "jobs": jobs,
        "campaigns": campaigns,
        "directors": directors,
    }


def _row_to_job(row: sqlite3.Row) -> ResearchJob:
    return ResearchJob(
        job_id=row["job_id"],
        campaign_id=row["campaign_id"],
        command=row["command"],
        config_path=row["config_path"],
        spec_json=row["spec_json"],
        priority=int(row["priority"]),
        status=row["status"],
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        output_root=row["output_root"],
        input_dataset_ref=row["input_dataset_ref"],
        feature_set_ref=row["feature_set_ref"],
        control_profile=row["control_profile"],
        quality_gate=row["quality_gate"],
        evaluation_profile=row["evaluation_profile"],
    )


def _load_result_payload(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _timestamp_slug(value: str) -> str:
    return value.replace(":", "").replace("+00:00", "Z")


def _safe_filename_component(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)
    return safe or "campaign"


@contextmanager
def _connect(paths: ResearchRuntimePaths):
    connection = sqlite3.connect(paths.database_path, timeout=SQLITE_CONNECT_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
        connection.commit()
    finally:
        connection.close()


def _optional_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _normalize_output_root(value: object, job_id: str) -> tuple[str, str]:
    if value in (None, ""):
        return (str(PurePosixPath("job_outputs") / job_id), "runtime_relative")
    return (str(value), "raw")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column in columns:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
