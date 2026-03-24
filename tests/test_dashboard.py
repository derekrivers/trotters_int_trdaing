from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
import base64
import json
import shutil
import unittest
from unittest.mock import MagicMock, patch
import uuid

from trotters_trader.dashboard import DashboardApp, DashboardController, _ThreadingWSGIServer, _display_timestamp, serve_dashboard
from trotters_trader.research_runtime import runtime_paths


class DashboardTests(unittest.TestCase):
    AUTH_USERNAME = "operator"
    AUTH_PASSWORD = "change-me-local-only"

    def test_display_timestamp_trims_subsecond_precision(self) -> None:
        self.assertEqual(
            _display_timestamp("2026-03-23T21:54:15.212999+00:00"),
            "2026-03-23T21:54:15+00:00",
        )

    def test_overview_links_compiled_dashboard_stylesheet(self) -> None:
        root = self._workspace_root("compiled_stylesheet")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}),
                patch("trotters_trader.dashboard.campaign_status", return_value={"campaign": {}}),
                patch("trotters_trader.dashboard.director_status", return_value={"director": {}}),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn('<link rel="stylesheet" href="/assets/dashboard.css?v=', body)
        self.assertIn('class="dashboard-app"', body)
        self.assertNotIn("<style>", body)

    def test_dashboard_serves_compiled_stylesheet_asset(self) -> None:
        root = self._workspace_root("stylesheet_asset")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            status, headers, body = self._invoke(app, "GET", "/assets/dashboard.css")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertEqual(dict(headers)["Content-Type"], "text/css; charset=utf-8")
        self.assertIn("font-size:1.35rem", body)
        self.assertIn("font-size:1.7rem", body)
        self.assertIn(".hero{display:flex", body)

    def test_overview_renders_catalog_pending_banner_when_catalog_missing(self) -> None:
        root = self._workspace_root("catalog_pending")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}),
                patch("trotters_trader.dashboard.campaign_status", return_value={"campaign": {}}),
                patch("trotters_trader.dashboard.director_status", return_value={"director": {}}),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Catalog snapshot not available yet.", body)
        self.assertIn("catalog.jsonl", body)

    def test_overview_page_renders_campaigns_and_notifications(self) -> None:
        root = self._workspace_root("overview")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
            notifications_path.parent.mkdir(parents=True, exist_ok=True)
            notifications_path.write_text(
                json.dumps(
                    {
                        "recorded_at_utc": "2026-03-21T16:00:00+00:00",
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "event_type": "strategy_promoted",
                        "severity": "success",
                        "message": "Strategy promoted and frozen for review",
                        "notification_requested": False,
                        "hook": {"success": None},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 3, "running": 1, "completed": 9},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "running",
                                "current_job_id": "job-1",
                                "heartbeat_at": "2026-03-21T16:01:00+00:00",
                            }
                        ],
                        "jobs": [
                            {
                                "job_id": "job-1",
                                "campaign_id": "campaign-1",
                                "command": "promotion-check",
                                "status": "running",
                                "leased_by": "worker-01",
                                "created_at": "2026-03-21T16:00:30+00:00",
                                "updated_at": "2026-03-21T16:01:00+00:00",
                            }
                        ],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "running",
                                "phase": "stress_pack",
                                "updated_at": "2026-03-21T16:01:00+00:00",
                            },
                            {
                                "campaign_id": "campaign-2",
                                "campaign_name": "completed-operability",
                                "status": "completed",
                                "phase": "stress_pack",
                                "updated_at": "2026-03-21T16:02:00+00:00",
                                "latest_report_path": "runtime/catalog/completed.md",
                            }
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "status": "running",
                            },
                            {
                                "director_id": "director-2",
                                "director_name": "archived-director",
                                "status": "exhausted",
                                "successful_campaign_id": None,
                                "updated_at": "2026-03-21T16:03:00+00:00",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "broad-operability",
                            "status": "running",
                            "phase": "stress_pack",
                            "updated_at": "2026-03-21T16:01:00+00:00",
                            "latest_report_path": "runtime/catalog/report.md",
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}, {"status": "pending"}]},
                        }
                    },
                ),
            ):
                status, headers, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn(("Content-Type", "text/html; charset=utf-8"), headers)
        self.assertIn("Research Runtime Dashboard", body)
        self.assertIn("broad-operability", body)
        self.assertIn("Strategy promoted and frozen for review", body)
        self.assertIn("worker-01", body)
        self.assertIn("ago", body)
        self.assertIn("broad-operability-plan", body)
        self.assertIn("Strategy promoted:", body)
        self.assertIn("success", body)
        self.assertIn("Active Runtime Now", body)
        self.assertIn("Active Directors", body)
        self.assertIn("Active Campaigns", body)
        self.assertIn("Diagnostics", body)
        self.assertIn("Recent Notifications", body)
        self.assertNotIn("Outcome Summary", body)
        self.assertNotIn("What Changed Since Last Check", body)
        self.assertNotIn("Recent Terminal Campaign Outcomes", body)
        self.assertNotIn("Recent Terminal Director Outcomes", body)
        self.assertNotIn("Recent Jobs", body)

    def test_overview_ignores_stale_stopped_banner_when_replacement_campaign_is_running(self) -> None:
        root = self._workspace_root("overview_stale_stop")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
            notifications_path.parent.mkdir(parents=True, exist_ok=True)
            notifications_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "recorded_at_utc": "2026-03-21T16:05:00+00:00",
                                "campaign_id": "campaign-old",
                                "campaign_name": "broad-operability-primary",
                                "event_type": "campaign_stopped",
                                "severity": "warning",
                                "message": "Campaign was stopped and will not advance.",
                                "notification_requested": False,
                                "hook": {"success": None},
                            }
                        ),
                        json.dumps(
                            {
                                "recorded_at_utc": "2026-03-21T16:00:00+00:00",
                                "campaign_id": "campaign-old",
                                "campaign_name": "broad-operability-primary",
                                "event_type": "campaign_finished",
                                "severity": "warning",
                                "message": "Campaign exhausted.",
                                "notification_requested": False,
                                "hook": {"success": None},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 2, "running": 1, "completed": 9},
                        "workers": [],
                        "jobs": [],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-new",
                                "campaign_name": "broad-operability-replacement",
                                "status": "running",
                                "phase": "focused_operability",
                                "updated_at": "2026-03-21T16:06:00+00:00",
                            },
                            {
                                "campaign_id": "campaign-old",
                                "campaign_name": "broad-operability-primary",
                                "status": "stopped",
                                "phase": "focused_operability",
                                "updated_at": "2026-03-21T16:05:00+00:00",
                            },
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "director_name": "broad-operability-director",
                                "status": "running",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-new",
                            "campaign_name": "broad-operability-replacement",
                            "status": "running",
                            "phase": "focused_operability",
                            "updated_at": "2026-03-21T16:06:00+00:00",
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-new",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}]},
                        }
                    },
                ),
            ):
                status, headers, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn(("Content-Type", "text/html; charset=utf-8"), headers)
        self.assertIn("broad-operability-replacement", body)
        self.assertNotIn(
            "Campaign stopped: broad-operability-primary will not advance until you restart or replace it.",
            body,
        )

    def test_overview_renders_healthy_system_health_panel(self) -> None:
        root = self._workspace_root("overview_health_ok")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            now = datetime(2026, 3, 21, 21, 40, tzinfo=UTC)
            with (
                patch("trotters_trader.dashboard._utc_now", return_value=now),
                patch("trotters_trader.runtime_overview._utc_now", return_value=now),
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 2, "running": 3, "completed": 9},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "running",
                                "current_job_id": "job-1",
                                "heartbeat_at": "2026-03-21T21:39:30+00:00",
                            }
                        ],
                        "jobs": [
                            {
                                "job_id": "job-1",
                                "campaign_id": "campaign-1",
                                "command": "promotion-check",
                                "status": "running",
                                "leased_by": "worker-01",
                                "created_at": "2026-03-21T21:35:00+00:00",
                                "updated_at": "2026-03-21T21:39:20+00:00",
                            }
                        ],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "running",
                                "phase": "focused_operability",
                                "updated_at": "2026-03-21T21:39:00+00:00",
                            }
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "status": "running",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "broad-operability",
                            "status": "running",
                            "phase": "focused_operability",
                            "updated_at": "2026-03-21T21:39:00+00:00",
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}]},
                        }
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("System Health", body)
        self.assertIn("Research runtime is healthy and actively progressing.", body)
        self.assertIn("worker pool", body)
        self.assertIn("job activity", body)

    def test_overview_renders_current_best_candidate_section(self) -> None:
        root = self._workspace_root("overview_best_candidate")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            latest_dir = paths.catalog_output_dir / "agent_summaries" / "latest"
            latest_dir.mkdir(parents=True, exist_ok=True)
            (latest_dir / "candidate_readiness_summary.json").write_text(
                json.dumps({
                    "summary_type": "candidate_readiness_summary",
                    "agent_id": "candidate-review",
                    "classification": "research_only",
                    "status": "recorded",
                    "recommended_action": "continue_research",
                    "message": "Candidate still needs deeper validation.",
                    "recorded_at_utc": "2026-03-22T12:00:00+00:00",
                }),
                encoding="utf-8",
            )
            (latest_dir / "paper_trade_readiness_summary.json").write_text(
                json.dumps({
                    "summary_type": "paper_trade_readiness_summary",
                    "agent_id": "paper-trade-readiness",
                    "classification": "not_ready",
                    "status": "recorded",
                    "recommended_action": "analyze_candidate",
                    "message": "Paper-trade evidence is incomplete.",
                    "recorded_at_utc": "2026-03-22T12:01:00+00:00",
                }),
                encoding="utf-8",
            )
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 2, "running": 1, "completed": 9},
                        "workers": [],
                        "jobs": [],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "running",
                                "phase": "benchmark_pivot",
                                "updated_at": "2026-03-22T07:00:00+00:00",
                            }
                        ],
                        "directors": [{"director_id": "director-1", "status": "running"}],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "broad-operability",
                            "status": "running",
                            "phase": "benchmark_pivot",
                            "updated_at": "2026-03-22T07:00:00+00:00",
                            "latest_report_path": "runtime/catalog/campaign-1/operability_program.md",
                            "state": {
                                "control_row": {
                                    "run_name": "control-run",
                                    "profile_name": "control-profile",
                                    "validation_excess_return": -0.01,
                                    "holdout_excess_return": -0.03,
                                    "walkforward_pass_windows": 0,
                                },
                                "shortlisted": [
                                    {
                                        "run_name": "candidate-run",
                                        "profile_name": "candidate-profile",
                                        "eligible": True,
                                        "validation_excess_return": 0.04,
                                        "holdout_excess_return": 0.01,
                                        "walkforward_pass_windows": 2,
                                        "rebalance_frequency_days": 84,
                                        "max_rebalance_turnover_pct": 0.08,
                                    }
                                ],
                                "stress_results": [],
                                "final_decision": {
                                    "recommended_action": "continue_research",
                                    "reason": "campaign_in_progress",
                                    "selected_run_name": "candidate-run",
                                    "selected_profile_name": "candidate-profile",
                                    "selected_candidate_eligible": True,
                                    "selected_stress_ok": False,
                                    "pivot_used": True,
                                },
                            },
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}]},
                        }
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Current Best Candidate", body)
        self.assertIn("candidate available", body)
        self.assertIn("Why This Is The Current Lead", body)
        self.assertIn("What Failed Or Is Missing", body)
        self.assertIn("Immediate next action", body)
        self.assertIn("candidate-run", body)
        self.assertIn("Supporting Specialist Views", body)
        self.assertNotIn("Candidate Progression", body)

    def test_overview_renders_active_research_branch_section(self) -> None:
        root = self._workspace_root("overview_active_branch")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 8, "running": 3, "completed": 12},
                        "workers": [],
                        "jobs": [],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "beta-defensive-primary",
                                "status": "running",
                                "phase": "stability_pivot",
                                "updated_at": "2026-03-23T10:00:00+00:00",
                            }
                        ],
                        "directors": [{"director_id": "director-1", "status": "running"}],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "beta-defensive-primary",
                            "status": "running",
                            "phase": "stability_pivot",
                            "updated_at": "2026-03-23T10:00:00+00:00",
                            "jobs": [
                                {"job_id": "job-1", "status": "running"},
                                {"job_id": "job-2", "status": "queued"},
                            ],
                            "events": [{"event_type": "campaign_progress", "recorded_at_utc": "2026-03-23T10:00:00+00:00"}],
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "beta-defensive-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "beta_defensive_continuation"},
                            "state": {"plan_name": "beta_defensive_continuation"},
                        }
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Active Research Branch", body)
        self.assertIn("beta-defensive-director", body)
        self.assertIn("beta_defensive_continuation", body)

    def test_overview_warns_when_system_is_quiet_with_stale_signals(self) -> None:
        root = self._workspace_root("overview_health_warn")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            now = datetime(2026, 3, 21, 21, 40, tzinfo=UTC)
            with (
                patch("trotters_trader.dashboard._utc_now", return_value=now),
                patch("trotters_trader.runtime_overview._utc_now", return_value=now),
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 0, "running": 0, "completed": 9},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "idle",
                                "current_job_id": None,
                                "heartbeat_at": "2026-03-21T21:30:00+00:00",
                            }
                        ],
                        "jobs": [],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "running",
                                "phase": "focused_operability",
                                "updated_at": "2026-03-21T21:20:00+00:00",
                            }
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "status": "running",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "broad-operability",
                            "status": "running",
                            "phase": "focused_operability",
                            "updated_at": "2026-03-21T21:20:00+00:00",
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}]},
                        }
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("System Health", body)
        self.assertIn("Research runtime is degraded: activity exists, but some signals look stale.", body)
        self.assertIn("stale heartbeats older than 3 minutes", body)

    def test_overview_marks_stalled_when_running_jobs_are_stale(self) -> None:
        root = self._workspace_root("overview_health_stalled")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            now = datetime(2026, 3, 21, 21, 40, tzinfo=UTC)
            with (
                patch("trotters_trader.dashboard._utc_now", return_value=now),
                patch("trotters_trader.runtime_overview._utc_now", return_value=now),
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 0, "running": 2, "completed": 9},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "idle",
                                "current_job_id": None,
                                "heartbeat_at": "2026-03-21T21:39:50+00:00",
                            }
                        ],
                        "jobs": [
                            {
                                "job_id": "job-1",
                                "campaign_id": "campaign-1",
                                "command": "promotion-check",
                                "status": "running",
                                "leased_by": "worker-old",
                                "created_at": "2026-03-21T21:00:00+00:00",
                                "updated_at": "2026-03-21T21:20:00+00:00",
                            }
                        ],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "running",
                                "phase": "focused_operability",
                                "updated_at": "2026-03-21T21:23:00+00:00",
                            }
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "status": "running",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.campaign_status",
                    return_value={
                        "campaign": {
                            "campaign_id": "campaign-1",
                            "campaign_name": "broad-operability",
                            "status": "running",
                            "phase": "focused_operability",
                            "updated_at": "2026-03-21T21:23:00+00:00",
                        }
                    },
                ),
                patch(
                    "trotters_trader.dashboard.director_status",
                    return_value={
                        "director": {
                            "director_id": "director-1",
                            "director_name": "broad-operability-director",
                            "status": "running",
                            "current_campaign_id": "campaign-1",
                            "successful_campaign_id": None,
                            "spec": {"plan_name": "broad-operability-plan"},
                            "state": {"campaign_queue": [{"status": "running"}]},
                        }
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Research runtime looks stalled: jobs are marked running, but their progress signals are stale.", body)
        self.assertIn("running job(s) have not updated for more than 15 minutes", body)

    def test_overview_flags_idle_runtime_when_latest_director_failed(self) -> None:
        root = self._workspace_root("overview_health_no_director")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=5)
            now = datetime(2026, 3, 21, 21, 40, tzinfo=UTC)
            with (
                patch("trotters_trader.dashboard._utc_now", return_value=now),
                patch("trotters_trader.runtime_overview._utc_now", return_value=now),
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 0, "running": 0, "completed": 9, "failed": 1},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "idle",
                                "current_job_id": None,
                                "heartbeat_at": "2026-03-21T21:39:50+00:00",
                            }
                        ],
                        "jobs": [],
                        "campaigns": [
                            {
                                "campaign_id": "campaign-1",
                                "campaign_name": "broad-operability",
                                "status": "failed",
                                "phase": "stability_pivot",
                                "updated_at": "2026-03-21T21:38:00+00:00",
                            }
                        ],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "director_name": "broad-operability-director",
                                "status": "failed",
                                "updated_at": "2026-03-21T21:39:00+00:00",
                            }
                        ],
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn(
            "Research runtime needs attention: no active directors remain after the latest director failed.",
            body,
        )
        self.assertIn("director activity", body)
        self.assertIn("No active directors. Most recent director broad-operability-director failed 1m ago.", body)

    def test_director_detail_page_renders_plan_queue(self) -> None:
        root = self._workspace_root("director")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.director_status",
                return_value={
                    "director": {
                        "director_id": "director-1",
                        "director_name": "broad-operability",
                        "status": "running",
                        "current_campaign_id": "campaign-1",
                        "successful_campaign_id": None,
                        "last_error": None,
                        "spec": {
                            "plan_name": "broad-operability-plan",
                            "plan_source": "configs/directors/broad_operability.json",
                            "adopt_active_campaigns": True,
                            "quality_gate": "all",
                        },
                        "state": {
                            "campaign_queue": [
                                {
                                    "queue_index": 0,
                                    "campaign_name": "primary",
                                    "entry_name": "primary",
                                    "config_path": "configs/backtest.toml",
                                    "status": "running",
                                    "campaign_id": "campaign-1",
                                    "campaign_max_hours": 24,
                                    "campaign_max_jobs": 1500,
                                    "outcome": None,
                                },
                                {
                                    "queue_index": 1,
                                    "campaign_name": "fallback",
                                    "entry_name": "fallback",
                                    "config_path": "configs/eodhd_momentum.toml",
                                    "status": "pending",
                                    "campaign_id": None,
                                    "campaign_max_hours": 24,
                                    "campaign_max_jobs": 1500,
                                    "outcome": None,
                                },
                            ],
                            "final_result": None,
                        },
                    },
                    "events": [
                        {
                            "recorded_at_utc": "2026-03-21T16:00:00+00:00",
                            "event_type": "campaign_started",
                            "message": "Director started campaign campaign-1",
                            "payload_json": "{\"campaign_id\": \"campaign-1\"}",
                        }
                    ],
                    "campaigns": [
                        {
                            "campaign_id": "campaign-1",
                            "campaign_name": "primary",
                            "status": "running",
                            "phase": "focused_operability",
                            "updated_at": "2026-03-21T16:01:00+00:00",
                            "latest_report_path": "runtime/catalog/program.md",
                        }
                    ],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/directors/director-1")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("broad-operability-plan", body)
        self.assertIn("Plan Queue", body)
        self.assertIn("primary", body)
        self.assertIn("fallback", body)
        self.assertIn("0 / 2", body)
        self.assertIn("Pause Director", body)
        self.assertIn("Skip Next Campaign", body)

    def test_director_pause_post_redirects(self) -> None:
        root = self._workspace_root("director_pause")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch("trotters_trader.dashboard.pause_director", return_value={"status": "paused"}) as pause_mock:
                status, headers, _ = self._invoke(
                    app,
                    "POST",
                    "/directors/director-1/pause",
                    body=b"reason=operator_pause&csrf_token=test-csrf",
                    content_type="application/x-www-form-urlencoded",
                    headers={"Cookie": "trotters_csrf=test-csrf"},
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "303 See Other")
        self.assertEqual(dict(headers)["Location"], "/directors/director-1?flash=Director+paused")
        pause_mock.assert_called_once()

    def test_campaign_detail_page_renders_state_and_events(self) -> None:
        root = self._workspace_root("detail")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.campaign_status",
                return_value={
                    "campaign": {
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "config_path": "configs/eodhd_momentum.toml",
                        "status": "running",
                        "phase": "benchmark_pivot",
                        "latest_report_path": "runtime/catalog/program.md",
                        "last_error": None,
                        "state": {
                            "control_row": {"run_name": "control-run"},
                            "shortlisted": [{"run_name": "candidate-run"}],
                            "final_decision": None,
                        },
                    },
                    "events": [
                        {
                            "recorded_at_utc": "2026-03-21T16:00:00+00:00",
                            "event_type": "stage_processed",
                            "message": "Processed focused_operability and advanced to benchmark_pivot",
                            "payload_json": "{\"phase\": \"focused_operability\"}",
                        }
                    ],
                    "jobs": [
                        {
                            "job_id": "job-1",
                            "command": "promotion-check",
                            "status": "completed",
                            "priority": 100,
                            "updated_at": "2026-03-21T16:01:00+00:00",
                        }
                    ],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/campaigns/campaign-1")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("benchmark_pivot", body)
        self.assertIn("Processed focused_operability", body)
        self.assertIn("Stop Campaign", body)
        self.assertIn("Handoff", body)
        self.assertIn("Compare", body)

    def test_campaign_detail_page_renders_exhausted_banner(self) -> None:
        root = self._workspace_root("detail_exhausted")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.campaign_status",
                return_value={
                    "campaign": {
                        "campaign_id": "campaign-2",
                        "campaign_name": "exhausted-operability",
                        "config_path": "configs/eodhd_momentum.toml",
                        "status": "exhausted",
                        "phase": "stability_pivot",
                        "latest_report_path": "runtime/catalog/program.md",
                        "last_error": None,
                        "state": {
                            "final_decision": {
                                "recommended_action": "exhausted",
                                "reason": "stability_pivot_did_not_produce_viable_candidate",
                            }
                        },
                    },
                    "events": [],
                    "jobs": [],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/campaigns/campaign-2")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("exhausted its search path", body)

    def test_campaign_handoff_page_renders_plain_english_summary(self) -> None:
        root = self._workspace_root("handoff")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.campaign_status",
                return_value={
                    "campaign": {
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "config_path": "configs/eodhd_momentum.toml",
                        "status": "completed",
                        "phase": "stress_pack",
                        "latest_report_path": "runtime/catalog/program.md",
                        "last_error": None,
                        "state": {
                            "control_row": {
                                "run_name": "control-run",
                                "profile_name": "control-profile",
                                "validation_excess_return": -0.03,
                                "holdout_excess_return": -0.12,
                                "walkforward_pass_windows": 0,
                                "rebalance_frequency_days": 63,
                            },
                            "shortlisted": [
                                {
                                    "run_name": "candidate-run",
                                    "profile_name": "candidate-profile",
                                    "eligible": True,
                                    "validation_excess_return": 0.04,
                                    "holdout_excess_return": 0.02,
                                    "walkforward_pass_windows": 2,
                                    "rebalance_frequency_days": 84,
                                    "max_rebalance_turnover_pct": 0.08,
                                    "target_gross_exposure": 0.65,
                                    "top_n": 8,
                                    "sector_cap": 3,
                                }
                            ],
                            "stress_results": [
                                {
                                    "candidate_run_name": "candidate-run",
                                    "stress_ok": True,
                                    "non_broken_count": 4,
                                    "scenario_count": 4,
                                    "broken_count": 0,
                                }
                            ],
                            "final_decision": {
                                "recommended_action": "freeze_candidate",
                                "reason": "candidate_passed_promotion_and_stress_pack",
                                "selected_run_name": "candidate-run",
                                "selected_profile_name": "candidate-profile",
                                "selected_candidate_eligible": True,
                                "selected_stress_ok": True,
                                "pivot_used": False,
                            },
                        },
                    },
                    "events": [],
                    "jobs": [],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/campaigns/campaign-1/handoff")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Promotion Handoff", body)
        self.assertIn("What The Strategy Does", body)
        self.assertIn("Why It Passed", body)
        self.assertIn("Where It Is Weak", body)
        self.assertIn("What Should Happen Next", body)
        self.assertIn("candidate-run", body)
        self.assertIn("Compare Candidates", body)
        self.assertIn("operator recommendation", body)
        self.assertIn("paper_trade_next", body)

    def test_campaign_scorecard_page_renders_operator_recommendation(self) -> None:
        root = self._workspace_root("scorecard")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.campaign_status",
                return_value={
                    "campaign": {
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "latest_report_path": str((root / "catalog" / "campaign-1" / "operability_program.md").resolve()),
                        "state": {
                            "control_row": {
                                "run_name": "control-run",
                                "profile_name": "control-profile",
                                "validation_excess_return": -0.03,
                                "holdout_excess_return": -0.12,
                                "walkforward_pass_windows": 0,
                            },
                            "shortlisted": [
                                {
                                    "run_name": "candidate-run",
                                    "profile_name": "candidate-profile",
                                    "eligible": True,
                                    "validation_excess_return": 0.04,
                                    "holdout_excess_return": 0.02,
                                    "walkforward_pass_windows": 2,
                                    "rebalance_frequency_days": 84,
                                    "max_rebalance_turnover_pct": 0.08,
                                }
                            ],
                            "stress_results": [
                                {
                                    "candidate_run_name": "candidate-run",
                                    "stress_ok": True,
                                    "non_broken_count": 4,
                                    "scenario_count": 4,
                                }
                            ],
                            "final_decision": {
                                "recommended_action": "freeze_candidate",
                                "reason": "candidate_passed_promotion_and_stress_pack",
                                "selected_run_name": "candidate-run",
                                "selected_profile_name": "candidate-profile",
                                "selected_candidate_eligible": True,
                                "selected_stress_ok": True,
                                "pivot_used": False,
                            },
                        },
                    },
                    "events": [],
                    "jobs": [],
                },
            ):
                artifact_dir = root / "catalog" / "campaign-1"
                artifact_dir.mkdir(parents=True, exist_ok=True)
                (artifact_dir / "operator_scorecard.md").write_text("scorecard", encoding="utf-8")
                (artifact_dir / "operator_scorecard.json").write_text("{}", encoding="utf-8")
                (artifact_dir / "candidate_comparison.md").write_text("comparison", encoding="utf-8")
                (artifact_dir / "operability_program.md").write_text("program", encoding="utf-8")
                status, _, body = self._invoke(app, "GET", "/campaigns/campaign-1/scorecard")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Operator Scorecard", body)
        self.assertIn("paper_trade_next", body)
        self.assertIn("scorecard md", body)
        self.assertIn("comparison md", body)
        self.assertIn("Strengths", body)
        self.assertIn("Weaknesses", body)

    def test_campaign_comparison_page_renders_control_and_shortlist(self) -> None:
        root = self._workspace_root("comparison")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch(
                "trotters_trader.dashboard.campaign_status",
                return_value={
                    "campaign": {
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "status": "completed",
                        "phase": "stress_pack",
                        "state": {
                            "control_row": {
                                "run_name": "control-run",
                                "profile_name": "control-profile",
                                "validation_excess_return": -0.03,
                                "holdout_excess_return": -0.12,
                                "walkforward_pass_windows": 0,
                                "rebalance_frequency_days": 63,
                                "max_rebalance_turnover_pct": 0.09,
                            },
                            "shortlisted": [
                                {
                                    "run_name": "candidate-run",
                                    "profile_name": "candidate-profile",
                                    "eligible": True,
                                    "validation_excess_return": 0.04,
                                    "holdout_excess_return": 0.02,
                                    "walkforward_pass_windows": 2,
                                    "rebalance_frequency_days": 84,
                                    "max_rebalance_turnover_pct": 0.08,
                                }
                            ],
                            "stress_results": [
                                {
                                    "candidate_run_name": "candidate-run",
                                    "stress_ok": True,
                                    "non_broken_count": 4,
                                    "scenario_count": 4,
                                }
                            ],
                            "final_decision": {
                                "recommended_action": "freeze_candidate",
                                "selected_run_name": "candidate-run",
                            },
                        },
                    },
                    "events": [],
                    "jobs": [],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/campaigns/campaign-1/comparison")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Candidate Comparison", body)
        self.assertIn("control-run", body)
        self.assertIn("candidate-run", body)
        self.assertIn("Selected candidate", body)
        self.assertIn("Baseline for comparison", body)

    def test_guide_page_renders_plain_english_application_help(self) -> None:
        root = self._workspace_root("guide")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            status, _, body = self._invoke(app, "GET", "/guide")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Application Guide", body)
        self.assertIn("Purpose", body)
        self.assertIn("What It Is Trying To Achieve", body)
        self.assertIn("What We Intend To Do With A Solid Candidate", body)

    def test_stop_campaign_post_redirects(self) -> None:
        root = self._workspace_root("stop")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch("trotters_trader.dashboard.stop_campaign", return_value={"status": "stopped"}) as stop_mock:
                status, headers, _ = self._invoke(
                    app,
                    "POST",
                    "/campaigns/campaign-1/stop",
                    body=b"reason=dashboard_stop&csrf_token=test-csrf",
                    content_type="application/x-www-form-urlencoded",
                    headers={"Cookie": "trotters_csrf=test-csrf"},
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "303 See Other")
        self.assertEqual(dict(headers)["Location"], "/campaigns/campaign-1?flash=Campaign+stop+requested")
        stop_mock.assert_called_once()

    def test_overview_keeps_agent_telemetry_off_the_main_page(self) -> None:
        root = self._workspace_root("agent_summaries")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            latest_dir = paths.catalog_output_dir / "agent_summaries" / "latest"
            latest_dir.mkdir(parents=True, exist_ok=True)
            (latest_dir / "supervisor_incident_summary.json").write_text(
                json.dumps({
                    "summary_type": "supervisor_incident_summary",
                    "agent_id": "runtime-supervisor",
                    "classification": "service_health",
                    "status": "escalated",
                    "recommended_action": "manual_investigation",
                    "recorded_at_utc": "2026-03-22T12:05:00+00:00",
                }),
                encoding="utf-8",
            )
            telemetry_dir = paths.catalog_output_dir / "agent_telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            (telemetry_dir / "dispatches.jsonl").write_text(
                json.dumps({
                    "recorded_at_utc": "2026-03-22T12:06:00+00:00",
                    "agent_id": "research-triage",
                    "event_type": "campaign_finished",
                    "success": True,
                    "model": "gpt-5-nano",
                    "total_tokens": 210,
                }) + "\n",
                encoding="utf-8",
            )
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}),
                patch("trotters_trader.dashboard.campaign_status", return_value={"campaign": {}}),
                patch("trotters_trader.dashboard.director_status", return_value={"director": {}}),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Diagnostics", body)
        self.assertIn("/api/overview.json", body)
        self.assertNotIn("Decision Snapshots", body)
        self.assertNotIn("Agent Summaries", body)
        self.assertNotIn("Agent Dispatches", body)
        self.assertNotIn("runtime-supervisor", body)
        self.assertNotIn("research-triage", body)
        self.assertNotIn("service_health", body)

    def test_overview_renders_paper_rehearsal_panel(self) -> None:
        root = self._workspace_root("paper_rehearsal")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            paper_root = paths.catalog_output_dir / "paper_trading"
            paper_root.mkdir(parents=True, exist_ok=True)
            (paper_root / "state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "active_profile": None,
                    "portfolio": {"initialized": False, "cash": 0.0, "nav": 0.0, "holdings": []},
                    "current_day_status": "blocked",
                }),
                encoding="utf-8",
            )
            (paper_root / "days.jsonl").write_text(
                json.dumps({
                    "day_id": "paper-day-1",
                    "recorded_at_utc": "2026-03-22T12:30:00+00:00",
                    "status": "blocked",
                    "profile_name": "",
                    "decision_date": "",
                    "next_trade_date": "",
                    "summary": "Paper-trading rehearsal is blocked.",
                    "block_reasons": [{"code": "no_promoted_candidate", "message": "No promoted frozen candidate is available for paper-trading rehearsal."}],
                }) + "\n",
                encoding="utf-8",
            )
            (paper_root / "operator_actions.jsonl").write_text(
                json.dumps({
                    "action_id": "paper-action-1",
                    "recorded_at_utc": "2026-03-22T12:30:01+00:00",
                    "action": "blocked",
                    "actor": "system",
                    "day_id": "paper-day-1",
                    "reason": "No promoted frozen candidate is available for paper-trading rehearsal.",
                }) + "\n",
                encoding="utf-8",
            )
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}),
                patch("trotters_trader.dashboard.campaign_status", return_value={"campaign": {}}),
                patch("trotters_trader.dashboard.director_status", return_value={"director": {}}),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Paper-Trade Entry Gate", body)
        self.assertNotIn("Paper Rehearsal", body)
        self.assertIn("Diagnostics", body)

    def test_healthz_is_public_without_dashboard_auth(self) -> None:
        root = self._workspace_root("healthz")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            status, headers, body = self._invoke(app, "GET", "/healthz", authenticated=False)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertEqual(dict(headers)["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(body, "ok")

    def test_dashboard_requires_basic_auth_for_overview(self) -> None:
        root = self._workspace_root("auth_required")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            status, headers, body = self._invoke(app, "GET", "/", authenticated=False)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(dict(headers)["WWW-Authenticate"], 'Basic realm="Trotters Dashboard"')
        self.assertEqual(body, "Unauthorized")

    def test_authenticated_get_sets_csrf_cookie(self) -> None:
        root = self._workspace_root("csrf_cookie")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}):
                status, headers, _ = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Set-Cookie", dict(headers))
        self.assertIn("trotters_csrf=", dict(headers)["Set-Cookie"])

    def test_post_without_csrf_token_is_forbidden(self) -> None:
        root = self._workspace_root("csrf_required")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            status, _, body = self._invoke(
                app,
                "POST",
                "/campaigns/campaign-1/stop",
                body=b"reason=dashboard_stop",
                content_type="application/x-www-form-urlencoded",
                headers={"Cookie": "trotters_csrf=test-csrf"},
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "403 Forbidden")
        self.assertIn("Missing or invalid CSRF token", body)

    def test_overview_renders_service_heartbeat_panel(self) -> None:
        root = self._workspace_root("service_heartbeats")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            now = datetime(2026, 3, 23, 9, 0, tzinfo=UTC)
            with (
                patch("trotters_trader.dashboard._utc_now", return_value=now),
                patch("trotters_trader.runtime_overview._utc_now", return_value=now),
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 1, "running": 1},
                        "workers": [{"worker_id": "worker-01", "status": "running", "heartbeat_at": "2026-03-23T08:59:45+00:00"}],
                        "jobs": [{"job_id": "job-1", "status": "running", "updated_at": "2026-03-23T08:59:50+00:00"}],
                        "campaigns": [{"campaign_id": "campaign-1", "status": "running", "updated_at": "2026-03-23T08:59:55+00:00"}],
                        "directors": [{"director_id": "director-1", "status": "running", "updated_at": "2026-03-23T08:59:55+00:00"}],
                        "service_heartbeats": [
                            {
                                "service": "coordinator",
                                "label": "Coordinator",
                                "status": "ok",
                                "recorded_at_utc": "2026-03-23T08:59:55+00:00",
                                "pid": 101,
                                "detail": "Heartbeat is fresh.",
                            },
                            {
                                "service": "campaign-manager",
                                "label": "Campaign Manager",
                                "status": "stale",
                                "recorded_at_utc": "2026-03-23T08:56:00+00:00",
                                "pid": 202,
                                "detail": "Heartbeat is 180s old; expected <= 90s.",
                            },
                        ],
                    },
                ),
                patch("trotters_trader.dashboard.campaign_status", return_value={"campaign": {"campaign_id": "campaign-1", "campaign_name": "campaign-1", "status": "running"}}),
                patch("trotters_trader.dashboard.director_status", return_value={"director": {"director_id": "director-1", "director_name": "director-1", "status": "running"}}),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Service Heartbeats", body)
        self.assertIn("Campaign Manager", body)
        self.assertIn("Research runtime is degraded", body)

    def test_overview_renders_research_program_portfolio_section(self) -> None:
        root = self._workspace_root("program_portfolio")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with patch("trotters_trader.dashboard.runtime_status", return_value={"counts": {}, "workers": [], "jobs": [], "campaigns": [], "directors": []}):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Next Family Status", body)
        self.assertIn("Supervisor Work Queue", body)
        self.assertNotIn("Research Program Portfolio", body)
        self.assertNotIn("Research Family Comparison", body)
        self.assertTrue(
            "define_next_research_family" in body
            or "start_approved_family" in body
            or "bootstrap_approved_family" in body
        )

    def test_overview_marks_governed_blocked_idle_state(self) -> None:
        root = self._workspace_root("governed_blocked_idle")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 0, "running": 0},
                        "workers": [
                            {
                                "worker_id": "worker-01",
                                "status": "idle",
                                "current_job_id": None,
                                "heartbeat_at": "2999-03-23T08:59:59+00:00",
                            }
                        ],
                        "jobs": [],
                        "campaigns": [],
                        "directors": [
                            {
                                "director_id": "director-1",
                                "director_name": "sma-cross-director",
                                "status": "exhausted",
                                "updated_at": "2026-03-23T08:59:59+00:00",
                            }
                        ],
                        "service_heartbeats": [
                            {
                                "service": "coordinator",
                                "label": "Coordinator",
                                "status": "ok",
                                "recorded_at_utc": "2999-03-23T08:59:59+00:00",
                                "pid": 101,
                                "detail": "Heartbeat is fresh.",
                            }
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.build_next_family_status",
                    return_value={
                        "status": "blocked_pending_approval",
                        "recommended_action": "define_next_research_family",
                        "message": "Current family proposal 'sma-cross' is retired and cannot re-enter the queue.",
                        "blocking_reason": "The branch exhausted its defined path without producing a promotion-eligible candidate.",
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("Research runtime is intentionally blocked", body)
        self.assertIn("queue governance", body)
        self.assertIn("Current family proposal &#x27;sma-cross&#x27; is retired and cannot re-enter the queue.", body)

    def test_overview_renders_approved_backlog_status_for_next_family(self) -> None:
        root = self._workspace_root("next_family_backlog")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = DashboardApp(DashboardController(paths), refresh_seconds=0)
            with (
                patch(
                    "trotters_trader.dashboard.runtime_status",
                    return_value={
                        "counts": {"queued": 0, "running": 0},
                        "workers": [{"worker_id": "worker-01", "status": "idle", "heartbeat_at": "2999-03-23T08:59:59+00:00"}],
                        "jobs": [],
                        "campaigns": [],
                        "directors": [],
                        "service_heartbeats": [
                            {"service": "coordinator", "label": "Coordinator", "status": "ok", "recorded_at_utc": "2999-03-23T08:59:59+00:00", "pid": 101, "detail": "Heartbeat is fresh."},
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.build_next_family_status",
                    return_value={
                        "status": "queued",
                        "recommended_action": "start_approved_family",
                        "message": "Approved family 'sma_cross_broad_confirmation' is queued and ready for controlled resumption.",
                        "blocking_reason": "",
                        "next_runnable_plan_id": "sma_cross_broad_confirmation",
                        "approved_backlog_depth": 6,
                        "approved_backlog_status": "healthy",
                        "approved_backlog_message": "6 approved standby families remain beyond the current queue head.",
                        "approved_backlog_plan_ids": [
                            "mean_reversion_broad_fastcycle",
                            "momentum_drawdown_sector_guard",
                            "beta_defensive_continuation",
                            "refine_seed_continuation",
                            "mean_reversion_broad_residual_cap",
                            "sma_cross_broad_trend_guard",
                        ],
                    },
                ),
                patch(
                    "trotters_trader.dashboard.build_research_family_comparison_summary",
                    return_value={
                        "families": [
                            {
                                "proposal_id": f"family_{index}",
                                "title": f"Family {index}",
                                "family_status": "queued",
                                "approval_status": "approved",
                                "plan_id": f"family_{index}",
                                "program_id": f"family_{index}_program",
                                "novelty_vs_retired": "material",
                                "implementation_readiness": "ready",
                                "operator_recommendation": "start_approved_family",
                            }
                            for index in range(10)
                        ],
                        "counts": {"total": 10, "approved": 0, "queued": 10, "active": 0, "under_review": 0},
                        "approved_backlog_depth": 6,
                        "approved_backlog_status": "healthy",
                        "approved_backlog_message": "6 approved standby families remain beyond the current queue head.",
                        "approved_backlog": [
                            {"proposal_id": "mean_reversion_broad_fastcycle", "title": "Mean-Reversion Fast Cycle", "plan_id": "mean_reversion_broad_fastcycle"},
                            {"proposal_id": "momentum_drawdown_sector_guard", "title": "Momentum Drawdown Sector Guard", "plan_id": "momentum_drawdown_sector_guard"},
                            {"proposal_id": "beta_defensive_continuation", "title": "Beta-Defensive Continuation", "plan_id": "beta_defensive_continuation"},
                            {"proposal_id": "refine_seed_continuation", "title": "Refine-Seed Continuation", "plan_id": "refine_seed_continuation"},
                            {"proposal_id": "mean_reversion_broad_residual_cap", "title": "Mean-Reversion Residual Cap", "plan_id": "mean_reversion_broad_residual_cap"},
                            {"proposal_id": "sma_cross_broad_trend_guard", "title": "SMA Cross Trend Guard", "plan_id": "sma_cross_broad_trend_guard"},
                        ],
                    },
                ),
            ):
                status, _, body = self._invoke(app, "GET", "/")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "200 OK")
        self.assertIn("approved standby", body)
        self.assertIn("backlog status", body)
        self.assertIn("6 approved standby families remain beyond the current queue head.", body)
        self.assertIn("mean_reversion_broad_fastcycle", body)

    def test_serve_dashboard_uses_threaded_wsgi_server(self) -> None:
        root = self._workspace_root("serve_dashboard")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            server = MagicMock()
            server.__enter__.return_value = server
            server.__exit__.return_value = False
            server.serve_forever.side_effect = RuntimeError("stop-server")
            with patch("trotters_trader.dashboard.make_server", return_value=server) as make_server:
                with self.assertRaisesRegex(RuntimeError, "stop-server"):
                    serve_dashboard(paths, host="127.0.0.1", port=8888, refresh_seconds=0)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertIs(make_server.call_args.kwargs["server_class"], _ThreadingWSGIServer)

    def _invoke(
        self,
        app: DashboardApp,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        content_type: str = "text/plain",
        headers: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> tuple[str, list[tuple[str, str]], str]:
        captured: dict[str, object] = {}
        route, _, query_string = path.partition("?")

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": route,
            "QUERY_STRING": query_string,
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": content_type,
            "wsgi.input": BytesIO(body),
        }
        request_headers = {}
        if authenticated:
            request_headers.update(self._auth_headers())
        if headers:
            request_headers.update(headers)
        for header_name, header_value in request_headers.items():
            environ_key = f"HTTP_{header_name.upper().replace('-', '_')}"
            environ[environ_key] = header_value
        chunks = app(environ, start_response)
        response_body = b"".join(chunks).decode("utf-8")
        return str(captured["status"]), list(captured["headers"]), response_body

    def _workspace_root(self, label: str) -> Path:
        root = Path("tests/.tmp_runtime") / f"dashboard_{label}_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _auth_headers(self) -> dict[str, str]:
        encoded = base64.b64encode(f"{self.AUTH_USERNAME}:{self.AUTH_PASSWORD}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}


if __name__ == "__main__":
    unittest.main()
