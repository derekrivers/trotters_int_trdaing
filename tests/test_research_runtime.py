from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.research_runtime import (
    campaign_manager_loop,
    campaign_status,
    coordinator_cycle,
    director_status,
    get_job,
    initialize_runtime,
    pause_director,
    resume_director,
    skip_director_next,
    start_director,
    runtime_paths,
    runtime_status,
    step_director,
    start_campaign,
    stop_director,
    stop_campaign,
    step_campaign,
    submit_jobs,
    worker_loop,
)
from tests.support import IsolatedWorkspaceTestCase


class ResearchRuntimeTests(IsolatedWorkspaceTestCase):
    def _prepared_dataset(self) -> Path:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        return config.data.canonical_dir

    def test_submit_records_queued_jobs(self) -> None:
        canonical_dir = self._prepared_dataset()
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        result = submit_jobs(
            paths,
            {
                "job_id": "job-1",
                "command": "backtest",
                "config_path": "configs/backtest.toml",
                "input_dataset_ref": str(canonical_dir),
            },
        )

        self.assertEqual(result["submitted"], 1)
        status = runtime_status(paths)
        self.assertEqual(status["counts"].get("queued"), 1)
        self.assertEqual(status["jobs"][0]["output_root"], "job_outputs/job-1")

    def test_initialize_runtime_enables_wal_mode(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")

        initialize_runtime(paths)

        with sqlite3.connect(paths.database_path) as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(str(mode).lower(), "wal")

    def test_concurrent_initialize_runtime_calls_do_not_fail(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(initialize_runtime, paths) for _ in range(4)]
            for future in futures:
                future.result()

        with sqlite3.connect(paths.database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        self.assertIn("jobs", tables)
        self.assertIn("campaigns", tables)

    def test_submit_preserves_explicit_posix_worker_paths(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        submit_jobs(
            paths,
            {
                "job_id": "compose-smoke-01",
                "command": "backtest",
                "config_path": "configs/backtest.toml",
                "input_dataset_ref": "/runtime/docker_smoke/dataset/canonical",
                "output_root": "/runtime/docker_smoke/job_outputs/compose-smoke-01",
            },
        )

        status = runtime_status(paths)
        self.assertEqual(status["jobs"][0]["output_root"], "/runtime/docker_smoke/job_outputs/compose-smoke-01")

    def test_three_workers_complete_independent_jobs_and_export_catalog(self) -> None:
        canonical_dir = self._prepared_dataset()
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        payload = {
            "jobs": [
                {
                    "job_id": f"job-{index}",
                    "command": "backtest",
                    "config_path": "configs/backtest.toml",
                    "input_dataset_ref": str(canonical_dir),
                    "output_root": str(self.temp_root / f"job_output_{index}"),
                    "priority": index,
                }
                for index in range(1, 4)
            ]
        }
        submit_jobs(paths, payload)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(worker_loop, paths, f"worker-{index}", 0.1, 300, True)
                for index in range(1, 4)
            ]
            results = [future.result() for future in futures]

        self.assertEqual(sum(result["completed_jobs"] for result in results), 3)

        snapshot = coordinator_cycle(paths, lease_timeout_seconds=300)
        self.assertEqual(snapshot["counts"].get("completed"), 3)

        catalog_json = self.temp_root / "catalog" / "research_catalog" / "experiment_catalog.json"
        self.assertTrue(catalog_json.exists())
        entries = json.loads(catalog_json.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 3)
        for index in range(1, 4):
            results_json = self.temp_root / f"job_output_{index}" / "sample_sma_backtest" / "results.json"
            self.assertTrue(results_json.exists())

    def test_coordinator_prunes_stale_idle_workers(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        submit_jobs(
            paths,
            {
                "job_id": "job-1",
                "command": "backtest",
                "config_path": "configs/backtest.toml",
            },
        )
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO workers (worker_id, status, current_job_id, updated_at)
                VALUES ('worker-stale', 'idle', NULL, '2000-01-01T00:00:00+00:00')
                """
            )
            connection.execute(
                """
                INSERT INTO worker_heartbeats (worker_id, heartbeat_at)
                VALUES ('worker-stale', '2000-01-01T00:00:00+00:00')
                """
            )

        snapshot = coordinator_cycle(paths, lease_timeout_seconds=300)
        worker_ids = [worker["worker_id"] for worker in snapshot["workers"]]
        self.assertNotIn("worker-stale", worker_ids)

    def test_cli_submit_accepts_spec_file(self) -> None:
        canonical_dir = self._prepared_dataset()
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        spec_path = self.temp_root / "job_spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "command": "backtest",
                    "config_path": "configs/backtest.toml",
                    "input_dataset_ref": str(canonical_dir),
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "trotters_trader.cli",
                "research-submit",
                "--runtime-root",
                str(paths.runtime_root),
                "--catalog-output-dir",
                str(paths.catalog_output_dir),
                "--spec",
                str(spec_path),
            ],
            cwd=Path.cwd(),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["submitted"], 1)

    def test_cli_research_batch_submits_ranking_jobs(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "trotters_trader.cli",
                "research-batch",
                "--config",
                "configs/backtest.toml",
                "--runtime-root",
                str(paths.runtime_root),
                "--catalog-output-dir",
                str(paths.catalog_output_dir),
                "--batch-preset",
                "ranking",
            ],
            cwd=Path.cwd(),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["submitted"], 7)
        self.assertEqual(payload["job_count"], 7)
        self.assertTrue((paths.runtime_root / payload["input_dataset_ref"] / "daily_bars.csv").exists())
        status = runtime_status(paths)
        self.assertEqual(status["counts"].get("queued"), 7)
        first_job = get_job(paths, payload["job_ids"][0])
        self.assertEqual(first_job.input_dataset_ref, payload["input_dataset_ref"])
        self.assertEqual(first_job.spec["input_dataset_ref_mode"], "runtime_relative")

    def test_start_campaign_records_running_campaign(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        with (
            patch(
                "trotters_trader.research_runtime._prepare_campaign_inputs",
                return_value=("datasets/test/canonical", "datasets/test/features/test"),
            ),
            patch(
                "trotters_trader.research_runtime.step_campaign",
                return_value={"outcome": "stage_submitted"},
            ),
        ):
            payload = start_campaign(
                paths,
                "configs/backtest.toml",
                campaign_name="autonomy-test",
                max_hours=2.0,
                max_jobs=25,
            )

        self.assertIn("campaign_id", payload)
        status = campaign_status(paths, payload["campaign_id"])
        self.assertEqual(status["campaign"]["campaign_name"], "autonomy-test")
        self.assertEqual(status["campaign"]["status"], "running")
        self.assertEqual(status["campaign"]["phase"], "focused_operability")

    def test_start_campaign_writes_notification_record(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        with (
            patch(
                "trotters_trader.research_runtime._prepare_campaign_inputs",
                return_value=("datasets/test/canonical", "datasets/test/features/test"),
            ),
            patch(
                "trotters_trader.research_runtime.step_campaign",
                return_value={"outcome": "stage_submitted"},
            ),
        ):
            payload = start_campaign(
                paths,
                "configs/backtest.toml",
                campaign_name="autonomy-test",
            )

        notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
        self.assertTrue(notifications_path.exists())
        records = [
            json.loads(line)
            for line in notifications_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        started = next(record for record in records if record["event_type"] == "campaign_started")
        self.assertEqual(started["campaign_id"], payload["campaign_id"])
        self.assertFalse(started["notification_requested"])
        self.assertEqual(started["severity"], "info")

    def test_start_director_records_running_director_and_writes_spec(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        with patch(
            "trotters_trader.research_runtime.step_director",
            return_value={"outcome": "campaign_started"},
        ):
            payload = start_director(
                paths,
                config_path="configs/backtest.toml",
                director_name="director-test",
            )

        self.assertIn("director_id", payload)
        status = director_status(paths, payload["director_id"])
        self.assertEqual(status["director"]["director_name"], "director-test")
        self.assertEqual(status["director"]["spec"]["plan_name"], "default_broad_operability")
        spec_path = paths.director_specs_dir / f"{payload['director_id']}.json"
        self.assertTrue(spec_path.exists())

    def test_start_director_accepts_valid_plan_payload(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        with patch(
            "trotters_trader.research_runtime.step_director",
            return_value={"outcome": "campaign_started"},
        ):
            payload = start_director(
                paths,
                director_name="director-plan",
                plan_payload={
                    "plan_name": "custom-plan",
                    "campaigns": [
                        {
                            "config_path": "configs/backtest.toml",
                            "campaign_name": "phase-one",
                            "campaign_max_hours": 12,
                            "campaign_max_jobs": 250,
                            "stage_candidate_limit": 10,
                            "shortlist_size": 2,
                            "quality_gate": "pass_warn",
                        }
                    ],
                },
                plan_file_path="configs/directors/custom.json",
            )

        status = director_status(paths, payload["director_id"])
        queue = status["director"]["state"]["campaign_queue"]
        self.assertEqual(status["director"]["spec"]["plan_name"], "custom-plan")
        self.assertEqual(status["director"]["spec"]["plan_source"], "configs/directors/custom.json")
        self.assertEqual(queue[0]["campaign_name"], "phase-one")
        self.assertEqual(queue[0]["campaign_max_jobs"], 250)
        self.assertEqual(queue[0]["shortlist_size"], 2)

    def test_start_director_rejects_missing_plan_config(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")

        with self.assertRaisesRegex(ValueError, "missing config_path"):
            start_director(
                paths,
                plan_payload={"campaigns": [{"campaign_name": "bad-entry"}]},
            )

    def test_start_director_rejects_nonexistent_plan_config(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")

        with self.assertRaisesRegex(ValueError, "references missing config_path"):
            start_director(
                paths,
                plan_payload={"campaigns": [{"config_path": "configs/does_not_exist.toml"}]},
            )

    def test_step_director_launches_first_campaign(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO directors (
                    director_id, director_name, status, spec_json, state_json, created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "director-1",
                    "director-1",
                    "running",
                    json.dumps(
                        {
                            "plan": [{"config_path": "configs/backtest.toml"}],
                            "quality_gate": "all",
                            "notify_events": [],
                            "adopt_active_campaigns": False,
                        }
                    ),
                    json.dumps(
                        {
                            "campaign_queue": [
                                {
                                    "queue_index": 0,
                                    "config_path": "configs/backtest.toml",
                                    "campaign_name": "director-1-backtest",
                                    "campaign_max_hours": 12,
                                    "campaign_max_jobs": 250,
                                    "stage_candidate_limit": 10,
                                    "shortlist_size": 2,
                                    "quality_gate": "pass_warn",
                                    "status": "pending",
                                    "campaign_id": None,
                                    "completed_at": None,
                                    "outcome": None,
                                }
                            ],
                            "active_campaign_id": None,
                            "successful_campaign_id": None,
                            "final_result": None,
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.commit()

        with patch(
            "trotters_trader.research_runtime.start_campaign",
            return_value={"campaign_id": "campaign-1", "campaign_name": "director-1-backtest"},
        ) as start_campaign_mock:
            payload = step_director(paths, "director-1")

        self.assertEqual(payload["outcome"], "campaign_started")
        status = director_status(paths, "director-1")
        self.assertEqual(status["director"]["current_campaign_id"], "campaign-1")
        queue = status["director"]["state"]["campaign_queue"]
        self.assertEqual(queue[0]["status"], "running")
        self.assertEqual(queue[0]["campaign_id"], "campaign-1")
        start_campaign_mock.assert_called_once()
        _, kwargs = start_campaign_mock.call_args
        self.assertEqual(kwargs["quality_gate"], "pass_warn")
        self.assertEqual(kwargs["max_hours"], 12.0)
        self.assertEqual(kwargs["max_jobs"], 250)
        self.assertEqual(kwargs["stage_candidate_limit"], 10)
        self.assertEqual(kwargs["shortlist_size"], 2)

    def test_step_director_adopts_matching_active_campaign(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO directors (
                    director_id, director_name, status, spec_json, state_json, created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "director-2",
                    "director-2",
                    "running",
                    json.dumps({"plan": [{"config_path": "configs/backtest.toml"}], "adopt_active_campaigns": True}),
                    json.dumps(
                        {
                            "campaign_queue": [
                                {
                                    "queue_index": 0,
                                    "config_path": "configs/backtest.toml",
                                    "campaign_name": "director-2-backtest",
                                    "status": "pending",
                                    "campaign_id": None,
                                    "completed_at": None,
                                    "outcome": None,
                                }
                            ],
                            "active_campaign_id": None,
                            "successful_campaign_id": None,
                            "final_result": None,
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-existing",
                    "campaign-existing",
                    "configs/backtest.toml",
                    "running",
                    "focused_operability",
                    json.dumps({}),
                    json.dumps({"final_decision": None}),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.commit()

        payload = step_director(paths, "director-2")

        self.assertEqual(payload["outcome"], "campaign_adopted")
        status = director_status(paths, "director-2")
        self.assertEqual(status["director"]["current_campaign_id"], "campaign-existing")
        self.assertEqual(status["campaigns"][0]["director_id"], "director-2")

    def test_step_director_completes_on_freeze_candidate(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO directors (
                    director_id, director_name, status, spec_json, state_json, created_at, updated_at, started_at,
                    current_campaign_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "director-3",
                    "director-3",
                    "running",
                    json.dumps({"plan": [{"config_path": "configs/backtest.toml"}]}),
                    json.dumps(
                        {
                            "campaign_queue": [
                                {
                                    "queue_index": 0,
                                    "config_path": "configs/backtest.toml",
                                    "campaign_name": "director-3-backtest",
                                    "status": "running",
                                    "campaign_id": "campaign-freeze",
                                    "completed_at": None,
                                    "outcome": None,
                                }
                            ],
                            "active_campaign_id": "campaign-freeze",
                            "successful_campaign_id": None,
                            "final_result": None,
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "campaign-freeze",
                ),
            )
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, director_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-freeze",
                    "director-3",
                    "campaign-freeze",
                    "configs/backtest.toml",
                    "completed",
                    "stress_pack",
                    json.dumps({}),
                    json.dumps(
                        {
                            "final_decision": {
                                "recommended_action": "freeze_candidate",
                                "selected_profile_name": "profile-1",
                            }
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:30:00+00:00",
                ),
            )
            connection.commit()

        payload = step_director(paths, "director-3")

        self.assertEqual(payload["outcome"], "director_completed")
        status = director_status(paths, "director-3")
        self.assertEqual(status["director"]["status"], "completed")
        self.assertEqual(status["director"]["successful_campaign_id"], "campaign-freeze")

    def test_pause_and_resume_director(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        with patch(
            "trotters_trader.research_runtime.step_director",
            return_value={"outcome": "campaign_started"},
        ):
            payload = start_director(
                paths,
                config_path="configs/backtest.toml",
                director_name="director-pause",
            )

        paused = pause_director(paths, payload["director_id"], reason="operator_pause")
        self.assertEqual(paused["outcome"], "director_paused")
        status = director_status(paths, payload["director_id"])
        self.assertEqual(status["director"]["status"], "paused")
        self.assertEqual(status["director"]["state"]["pause_reason"], "operator_pause")

        with patch(
            "trotters_trader.research_runtime.step_director",
            return_value={"outcome": "campaign_started"},
        ) as step_mock:
            resumed = resume_director(paths, payload["director_id"], reason="operator_resume")
        self.assertEqual(resumed["outcome"], "campaign_started")
        step_mock.assert_called_once()

    def test_skip_director_next_marks_pending_entry_skipped(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO directors (
                    director_id, director_name, status, spec_json, state_json, created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "director-skip",
                    "director-skip",
                    "paused",
                    json.dumps({"plan": [{"config_path": "configs/backtest.toml"}]}),
                    json.dumps(
                        {
                            "campaign_queue": [
                                {
                                    "queue_index": 0,
                                    "config_path": "configs/backtest.toml",
                                    "campaign_name": "first",
                                    "status": "pending",
                                    "campaign_id": None,
                                    "completed_at": None,
                                    "outcome": None,
                                },
                                {
                                    "queue_index": 1,
                                    "config_path": "configs/eodhd_momentum.toml",
                                    "campaign_name": "second",
                                    "status": "pending",
                                    "campaign_id": None,
                                    "completed_at": None,
                                    "outcome": None,
                                },
                            ],
                            "active_campaign_id": None,
                            "successful_campaign_id": None,
                            "final_result": None,
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.commit()

        skipped = skip_director_next(paths, "director-skip", reason="operator_skip")
        self.assertEqual(skipped["outcome"], "director_campaign_skipped")
        status = director_status(paths, "director-skip")
        queue = status["director"]["state"]["campaign_queue"]
        self.assertEqual(queue[0]["status"], "skipped")
        self.assertEqual(queue[0]["outcome"], "operator_skip")

    def test_stop_campaign_marks_campaign_stopped_and_invokes_notification_hook(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-stop",
                    "campaign-stop",
                    "configs/backtest.toml",
                    "running",
                    "focused_operability",
                    json.dumps(
                        {
                            "config_path": "configs/backtest.toml",
                            "quality_gate": "all",
                            "input_dataset_ref": "datasets/test/canonical",
                            "input_dataset_ref_mode": "runtime_relative",
                            "feature_set_ref": None,
                            "feature_set_ref_mode": "raw",
                            "notification_command": "echo campaign",
                            "notify_events": ["campaign_stopped"],
                        }
                    ),
                    json.dumps(
                        {
                            "seed_overrides": {},
                            "control_row": None,
                            "candidate_pool": [],
                            "focused_result": None,
                            "pivot_result": None,
                            "stability_result": None,
                            "shortlisted": [],
                            "stress_results": [],
                            "final_decision": None,
                            "pending_stage": {"phase": "focused_operability", "stage_id": "stage-1", "job_ids": ["job-1"]},
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, quality_gate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-queued",
                    "campaign-stop",
                    "promotion-check",
                    "configs/backtest.toml",
                    json.dumps({}),
                    100,
                    "queued",
                    0,
                    3,
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "job_outputs/job-queued",
                    "all",
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, quality_gate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-running",
                    "campaign-stop",
                    "promotion-check",
                    "configs/backtest.toml",
                    json.dumps({}),
                    101,
                    "running",
                    1,
                    3,
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "job_outputs/job-running",
                    "all",
                ),
            )
            connection.commit()

        with patch("trotters_trader.research_runtime.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(args="echo campaign", returncode=0, stdout="ok", stderr="")
            payload = stop_campaign(paths, "campaign-stop", reason="operator_pause")

        self.assertEqual(payload["status"], "stopped")
        self.assertEqual(payload["queued_jobs_cancelled"], 1)
        self.assertEqual(payload["running_jobs_remaining"], 1)
        status = campaign_status(paths, "campaign-stop")
        self.assertEqual(status["campaign"]["status"], "stopped")
        self.assertEqual(status["campaign"]["state"]["final_decision"]["recommended_action"], "stopped")
        self.assertEqual(run_mock.call_count, 1)
        notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
        records = [
            json.loads(line)
            for line in notifications_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        stopped = next(record for record in records if record["event_type"] == "campaign_stopped")
        self.assertTrue(stopped["hook"]["executed"])
        self.assertTrue(stopped["hook"]["success"])
        self.assertEqual(stopped["severity"], "warning")

    def test_campaign_manager_marks_campaign_failed_on_runtime_error(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-fail",
                    "campaign-fail",
                    "configs/backtest.toml",
                    "running",
                    "focused_operability",
                    json.dumps(
                        {
                            "config_path": "configs/backtest.toml",
                            "quality_gate": "all",
                            "input_dataset_ref": "datasets/test/canonical",
                            "input_dataset_ref_mode": "runtime_relative",
                            "feature_set_ref": None,
                            "feature_set_ref_mode": "raw",
                        }
                    ),
                    json.dumps(
                        {
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
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.commit()

        with patch("trotters_trader.research_runtime.step_campaign", side_effect=RuntimeError("boom")):
            payload = campaign_manager_loop(paths, once=True)

        self.assertEqual(payload["active_campaigns"], 1)
        status = campaign_status(paths, "campaign-fail")
        self.assertEqual(status["campaign"]["status"], "failed")
        self.assertIn("boom", status["campaign"]["last_error"])
        self.assertEqual(status["campaign"]["state"]["final_decision"]["reason"], "campaign_runtime_error")
        notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
        records = [
            json.loads(line)
            for line in notifications_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failed = next(record for record in records if record["event_type"] == "campaign_failed")
        self.assertIn("boom", failed["message"])
        self.assertEqual(failed["severity"], "error")

    def test_step_campaign_submits_focused_operability_jobs(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-1",
                    "campaign-1",
                    "configs/backtest.toml",
                    "running",
                    "focused_operability",
                    json.dumps(
                        {
                            "config_path": "configs/backtest.toml",
                            "quality_gate": "all",
                            "input_dataset_ref": "datasets/test/canonical",
                            "input_dataset_ref_mode": "runtime_relative",
                            "feature_set_ref": None,
                            "feature_set_ref_mode": "raw",
                            "stage_candidate_limit": 5,
                            "shortlist_size": 2,
                        }
                    ),
                    json.dumps(
                        {
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
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.commit()

        payload = step_campaign(paths, "campaign-1")

        self.assertEqual(payload["outcome"], "stage_submitted")
        status = campaign_status(paths, "campaign-1")
        self.assertEqual(status["campaign"]["phase"], "focused_operability")
        self.assertTrue(status["campaign"]["state"]["pending_stage"]["job_ids"])
        runtime = runtime_status(paths)
        self.assertGreater(runtime["counts"].get("queued", 0), 0)

    def test_step_campaign_processes_completed_stage_and_advances(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        canonical_dir = self._prepared_dataset()
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-2",
                    "campaign-2",
                    "configs/backtest.toml",
                    "running",
                    "focused_operability",
                    json.dumps(
                        {
                            "config_path": "configs/backtest.toml",
                            "quality_gate": "all",
                            "input_dataset_ref": str(canonical_dir),
                            "input_dataset_ref_mode": "raw",
                            "feature_set_ref": None,
                            "feature_set_ref_mode": "raw",
                            "stage_candidate_limit": 2,
                            "shortlist_size": 1,
                        }
                    ),
                    json.dumps(
                        {
                            "seed_overrides": {},
                            "control_row": None,
                            "candidate_pool": [],
                            "focused_result": None,
                            "pivot_result": None,
                            "stability_result": None,
                            "shortlisted": [],
                            "stress_results": [],
                            "final_decision": None,
                            "pending_stage": {
                                "phase": "focused_operability",
                                "stage_id": "stage-1",
                                "job_ids": ["job-control", "job-candidate"],
                            },
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            control_spec = {
                "campaign_phase": "focused_operability",
                "campaign_stage_id": "stage-1",
                "campaign_is_control": True,
                "research_variant": {
                    "kind": "control",
                    "tranche_name": "focused_operability",
                    "scenario_name": "control",
                    "scenario_label": "operability",
                },
            }
            candidate_spec = {
                "campaign_phase": "focused_operability",
                "campaign_stage_id": "stage-1",
                "campaign_is_control": False,
                "research_variant": {
                    "kind": "candidate",
                    "tranche_name": "focused_operability",
                    "scenario_name": "candidate-1",
                    "scenario_label": "operability",
                    "overrides": {"top_n": 6},
                },
            }
            promotion_control = {
                "eligible": False,
                "profile": {"profile_name": "control_profile", "profile_version": "v1", "frozen_on": None},
                "split_summary": {
                    "validation": {"status": "warn", "excess_return": 0.01, "max_drawdown": 0.05, "turnover": 0.2},
                    "holdout": {"status": "warn", "excess_return": -0.02, "max_drawdown": 0.05, "turnover": 0.2},
                    "train": {"status": "pass", "excess_return": 0.03, "max_drawdown": 0.04, "turnover": 0.2},
                },
                "walkforward_summary": {
                    "window_count": 3,
                    "pass_windows": 0,
                    "average_excess_return": -0.01,
                    "average_drawdown": 0.05,
                    "average_turnover": 0.2,
                },
            }
            promotion_candidate = {
                "eligible": True,
                "profile": {"profile_name": "candidate_profile", "profile_version": "v2", "frozen_on": None},
                "split_summary": {
                    "validation": {"status": "pass", "excess_return": 0.03, "max_drawdown": 0.04, "turnover": 0.1},
                    "holdout": {"status": "pass", "excess_return": 0.01, "max_drawdown": 0.04, "turnover": 0.1},
                    "train": {"status": "pass", "excess_return": 0.04, "max_drawdown": 0.04, "turnover": 0.1},
                },
                "walkforward_summary": {
                    "window_count": 3,
                    "pass_windows": 1,
                    "average_excess_return": 0.01,
                    "average_drawdown": 0.04,
                    "average_turnover": 0.1,
                },
            }
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, quality_gate, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-control",
                    "campaign-2",
                    "promotion-check",
                    "configs/backtest.toml",
                    json.dumps(control_spec),
                    100,
                    "completed",
                    1,
                    3,
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "job_outputs/job-control",
                    "all",
                    json.dumps({"promotion_decision": promotion_control}),
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, quality_gate, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-candidate",
                    "campaign-2",
                    "promotion-check",
                    "configs/backtest.toml",
                    json.dumps(candidate_spec),
                    101,
                    "completed",
                    1,
                    3,
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "job_outputs/job-candidate",
                    "all",
                    json.dumps({"promotion_decision": promotion_candidate}),
                ),
            )
            connection.commit()

        payload = step_campaign(paths, "campaign-2")

        self.assertEqual(payload["outcome"], "stage_processed")
        status = campaign_status(paths, "campaign-2")
        self.assertEqual(status["campaign"]["phase"], "stress_pack")
        self.assertEqual(len(status["campaign"]["state"]["shortlisted"]), 1)

    def test_successful_campaign_emits_strategy_promoted_notification(self) -> None:
        paths = runtime_paths(self.temp_root / "runtime", catalog_output_dir=self.temp_root / "catalog")
        initialize_runtime(paths)
        with sqlite3.connect(paths.database_path) as connection:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_name, config_path, status, phase, spec_json, state_json,
                    created_at, updated_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "campaign-promote",
                    "campaign-promote",
                    "configs/backtest.toml",
                    "running",
                    "stress_pack",
                    json.dumps(
                        {
                            "config_path": "configs/backtest.toml",
                            "quality_gate": "all",
                            "input_dataset_ref": "datasets/test/canonical",
                            "input_dataset_ref_mode": "runtime_relative",
                            "feature_set_ref": None,
                            "feature_set_ref_mode": "raw",
                            "notify_events": ["campaign_finished", "strategy_promoted"],
                        }
                    ),
                    json.dumps(
                        {
                            "seed_overrides": {},
                            "control_row": None,
                            "candidate_pool": [],
                            "focused_result": None,
                            "pivot_result": {"decision": {}},
                            "stability_result": {"decision": {}},
                            "shortlisted": [{"run_name": "candidate-1", "profile_name": "candidate_profile", "eligible": True}],
                            "stress_results": [],
                            "final_decision": None,
                            "pending_stage": {
                                "phase": "stress_pack",
                                "stage_id": "stage-promote",
                                "job_ids": ["job-stress-1"],
                            },
                        }
                    ),
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, campaign_id, command, config_path, spec_json, priority, status, attempt_count, max_attempts,
                    created_at, updated_at, output_root, quality_gate, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-stress-1",
                    "campaign-promote",
                    "promotion-check",
                    "configs/backtest.toml",
                    json.dumps(
                        {
                            "campaign_phase": "stress_pack",
                            "campaign_stage_id": "stage-promote",
                            "campaign_candidate_run_name": "candidate-1",
                            "campaign_candidate_profile_name": "candidate_profile",
                            "research_variant": {
                                "kind": "stress",
                                "scenario_name": "stress-1",
                                "scenario_label": "stress",
                                "tranche_name": "stress_pack",
                            },
                        }
                    ),
                    100,
                    "completed",
                    1,
                    3,
                    "2026-03-21T00:00:00+00:00",
                    "2026-03-21T00:00:00+00:00",
                    "job_outputs/job-stress-1",
                    "all",
                    json.dumps({"promotion_decision": {"eligible": True}}),
                ),
            )
            connection.commit()

        with (
            patch(
                "trotters_trader.research_runtime._campaign_stress_decision",
                return_value=(
                    {
                        "profile_name": "candidate_profile",
                        "promotion_decision": {"eligible": True},
                    },
                    {
                        "recommended_action": "freeze_candidate",
                        "reason": "candidate_passed_promotion_and_stress_pack",
                        "selected_run_name": "candidate-1",
                        "selected_profile_name": "candidate_profile",
                        "selected_candidate_eligible": True,
                        "selected_stress_ok": True,
                        "pivot_used": True,
                    },
                ),
            ),
            patch(
                "trotters_trader.research_runtime._write_campaign_program_report",
                return_value="runtime/catalog/promoted.md",
            ),
            patch("trotters_trader.research_runtime.write_promotion_artifacts"),
        ):
            payload = step_campaign(paths, "campaign-promote")

        self.assertEqual(payload["outcome"], "campaign_completed")
        notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
        records = [
            json.loads(line)
            for line in notifications_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        promoted = next(record for record in records if record["event_type"] == "strategy_promoted")
        self.assertEqual(promoted["campaign_id"], "campaign-promote")
        self.assertEqual(promoted["payload"]["selected_profile_name"], "candidate_profile")
        self.assertEqual(promoted["severity"], "success")
