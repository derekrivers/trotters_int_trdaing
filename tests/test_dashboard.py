from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import shutil
import unittest
from unittest.mock import patch
import uuid

from trotters_trader.dashboard import DashboardApp, DashboardController
from trotters_trader.research_runtime import runtime_paths


class DashboardTests(unittest.TestCase):
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
                        "event_type": "campaign_finished",
                        "message": "Campaign completed",
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
        self.assertIn("Campaign completed", body)
        self.assertIn("worker-01", body)
        self.assertIn("2026-03-21T16:00:30+00:00", body)
        self.assertIn("2026-03-21T16:01:00+00:00", body)
        self.assertIn("ago", body)
        self.assertIn("broad-operability-plan", body)

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
                    body=b"reason=dashboard_stop",
                    content_type="application/x-www-form-urlencoded",
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        self.assertEqual(status, "303 See Other")
        self.assertEqual(dict(headers)["Location"], "/campaigns/campaign-1?flash=Campaign+stop+requested")
        stop_mock.assert_called_once()

    def _invoke(
        self,
        app: DashboardApp,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        content_type: str = "text/plain",
    ) -> tuple[str, list[tuple[str, str]], str]:
        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": content_type,
            "wsgi.input": BytesIO(body),
        }
        chunks = app(environ, start_response)
        response_body = b"".join(chunks).decode("utf-8")
        return str(captured["status"]), list(captured["headers"]), response_body

    def _workspace_root(self, label: str) -> Path:
        root = Path("tests/.tmp_runtime") / f"dashboard_{label}_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root


if __name__ == "__main__":
    unittest.main()
