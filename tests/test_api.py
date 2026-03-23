from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import shutil
import unittest
from unittest.mock import patch
import uuid

from trotters_trader.api import ApiApp, ApiController
from trotters_trader.research_runtime import runtime_paths


class ApiTests(unittest.TestCase):
    AUTH_TOKEN = "test-token"

    def test_healthz_returns_ok(self) -> None:
        app = ApiApp(ApiController(runtime_paths(self._workspace_root("health") / "runtime")), auth_token=self.AUTH_TOKEN)

        status, headers, body = self._invoke(app, "GET", "/healthz")

        self.assertEqual(status, "200 OK")
        self.assertEqual(dict(headers)["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(body, "ok")

    def test_runtime_overview_returns_json_health_snapshot(self) -> None:
        root = self._workspace_root("overview")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
            notifications_path.parent.mkdir(parents=True, exist_ok=True)
            notifications_path.write_text(
                json.dumps(
                    {
                        "recorded_at_utc": "2026-03-22T07:00:00+00:00",
                        "campaign_id": "campaign-1",
                        "campaign_name": "broad-operability",
                        "event_type": "campaign_started",
                        "message": "Campaign started",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with (
                patch(
                    "trotters_trader.api.runtime_status",
                    return_value={
                        "counts": {"queued": 2, "running": 1},
                        "workers": [{"worker_id": "worker-01", "status": "running", "heartbeat_at": "2026-03-22T07:00:30+00:00"}],
                        "jobs": [],
                        "campaigns": [{"campaign_id": "campaign-1", "status": "running", "updated_at": "2026-03-22T07:00:00+00:00"}],
                        "directors": [{"director_id": "director-1", "status": "running", "updated_at": "2026-03-22T07:00:30+00:00"}],
                    },
                ),
                patch(
                    "trotters_trader.api.director_status",
                    return_value={"director": {"director_id": "director-1", "director_name": "broad-operability-director", "status": "running"}},
                ),
                patch(
                    "trotters_trader.api.campaign_status",
                    return_value={"campaign": {"campaign_id": "campaign-1", "campaign_name": "broad-operability", "status": "running"}},
                ),
            ):
                status, headers, body = self._invoke(app, "GET", "/api/v1/runtime/overview", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(dict(headers)["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("health", payload)
        self.assertIn(payload["health"]["status"], {"healthy", "warning"})
        self.assertEqual(payload["active_directors"][0]["director_id"], "director-1")
        self.assertEqual(payload["notifications"][0]["campaign_id"], "campaign-1")
        self.assertEqual(payload["most_recent_terminal"]["director"], None)
        self.assertIn("paper_rehearsal", payload)
        self.assertIn("candidate_progression_summary", payload)
        self.assertIn("paper_trade_entry_gate", payload)
        self.assertIn("research_program_portfolio", payload)

    def test_runtime_overview_includes_most_recent_terminal_summary(self) -> None:
        root = self._workspace_root("overview_terminal")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.runtime_status",
                return_value={
                    "counts": {},
                    "workers": [],
                    "jobs": [],
                    "campaigns": [
                        {"campaign_id": "campaign-active", "status": "running", "updated_at": "2026-03-22T07:00:00+00:00"},
                        {"campaign_id": "campaign-failed", "status": "failed", "updated_at": "2026-03-22T06:59:00+00:00", "last_error": "boom"},
                    ],
                    "directors": [
                        {"director_id": "director-exhausted", "status": "exhausted", "updated_at": "2026-03-22T06:58:00+00:00"},
                        {"director_id": "director-failed", "status": "failed", "updated_at": "2026-03-22T07:01:00+00:00", "last_error": "halt"},
                    ],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/api/v1/runtime/overview", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["most_recent_terminal"]["director"]["director_id"], "director-failed")
        self.assertEqual(payload["most_recent_terminal"]["campaign"]["campaign_id"], "campaign-failed")

    def test_runtime_overview_preserves_terminal_director_plan_name(self) -> None:
        root = self._workspace_root("overview_terminal_plan")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.runtime_status",
                return_value={
                    "counts": {},
                    "workers": [],
                    "jobs": [],
                    "campaigns": [
                        {
                            "campaign_id": "campaign-exhausted",
                            "status": "exhausted",
                            "updated_at": "2026-03-23T07:46:20+00:00",
                            "finished_at": "2026-03-23T07:46:20+00:00",
                        }
                    ],
                    "directors": [
                        {
                            "director_id": "director-exhausted",
                            "director_name": "beta-defensive-director",
                            "plan_name": "beta_defensive_continuation",
                            "status": "exhausted",
                            "updated_at": "2026-03-23T07:47:22+00:00",
                            "finished_at": "2026-03-23T07:47:22+00:00",
                        }
                    ],
                },
            ):
                status, _, body = self._invoke(app, "GET", "/api/v1/runtime/overview", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["most_recent_terminal"]["director"]["plan_name"], "beta_defensive_continuation")

    def test_runtime_overview_exposes_current_best_candidate_summary(self) -> None:
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
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with (
                patch(
                    "trotters_trader.api.runtime_status",
                    return_value={
                        "counts": {"queued": 2, "running": 1},
                        "workers": [],
                        "jobs": [],
                        "campaigns": [{"campaign_id": "campaign-1", "status": "running", "updated_at": "2026-03-22T07:00:00+00:00"}],
                        "directors": [{"director_id": "director-1", "status": "running", "updated_at": "2026-03-22T07:00:30+00:00"}],
                    },
                ),
                patch(
                    "trotters_trader.api.director_status",
                    return_value={"director": {"director_id": "director-1", "director_name": "broad-operability-director", "status": "running"}},
                ),
                patch(
                    "trotters_trader.api.campaign_status",
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
            ):
                status, _, body = self._invoke(app, "GET", "/api/v1/runtime/overview", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["current_best_candidate"]["campaign_id"], "campaign-1")
        self.assertEqual(payload["current_best_candidate"]["best_candidate"]["run_name"], "candidate-run")
        self.assertEqual(payload["current_best_candidate"]["source"], "active_campaign")
        self.assertEqual(
            payload["current_best_candidate"]["supporting_summaries"]["candidate_readiness"]["classification"],
            "research_only",
        )
        self.assertIn("leading_candidate", payload["candidate_progression_summary"])

    def test_start_director_route_uses_runtime_service(self) -> None:
        root = self._workspace_root("director_start")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.start_director",
                return_value={"director_id": "director-1", "outcome": "campaign_started"},
            ) as start_mock:
                status, _, body = self._invoke(
                    app,
                    "POST",
                    "/api/v1/directors",
                    body=json.dumps({"director_name": "test-director", "director_plan_file": "configs/directors/broad_operability.json"}).encode("utf-8"),
                    content_type="application/json",
                    headers=self._auth_headers(actor="test-agent"),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "201 Created")
        self.assertEqual(payload["director_id"], "director-1")
        start_mock.assert_called_once()

    def test_start_director_route_returns_bad_request_for_duplicate_plan(self) -> None:
        root = self._workspace_root("director_start_duplicate")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.start_director",
                side_effect=ValueError("Active director already running for plan 'broad_operability'"),
            ):
                status, _, body = self._invoke(
                    app,
                    "POST",
                    "/api/v1/directors",
                    body=json.dumps({"director_name": "test-director", "director_plan_file": "configs/directors/broad_operability.json"}).encode("utf-8"),
                    content_type="application/json",
                    headers=self._auth_headers(actor="test-agent"),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["error"], "Active director already running for plan 'broad_operability'")

    def test_pause_director_route_calls_pause(self) -> None:
        root = self._workspace_root("director_pause")
        audit_payload: dict[str, object] | None = None
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.pause_director",
                return_value={"director_id": "director-1", "status": "paused"},
            ) as pause_mock:
                status, _, body = self._invoke(
                    app,
                    "POST",
                    "/api/v1/directors/director-1/pause",
                    body=json.dumps({"reason": "api_pause"}).encode("utf-8"),
                    content_type="application/json",
                    headers=self._auth_headers(actor="openclaw"),
                )
            audit_lines = (paths.runtime_root / "exports" / "api_audit.jsonl").read_text(encoding="utf-8").splitlines()
            audit_payload = json.loads(audit_lines[-1])
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["status"], "paused")
        pause_mock.assert_called_once()
        self.assertIsNotNone(audit_payload)
        assert audit_payload is not None
        self.assertEqual(audit_payload["actor"], "openclaw")
        self.assertEqual(audit_payload["path"], "/api/v1/directors/director-1/pause")
        self.assertEqual(audit_payload["status"], "200 OK")
        self.assertTrue(audit_payload["mutation"])

    def test_mutation_route_requires_actor_header(self) -> None:
        root = self._workspace_root("actor_required")
        audit_payload: dict[str, object] | None = None
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/directors/director-1/pause",
                body=json.dumps({"reason": "api_pause"}).encode("utf-8"),
                content_type="application/json",
                headers={"Authorization": f"Bearer {self.AUTH_TOKEN}"},
            )
            audit_lines = (paths.runtime_root / "exports" / "api_audit.jsonl").read_text(encoding="utf-8").splitlines()
            audit_payload = json.loads(audit_lines[-1])
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["error"], "Mutation requests require X-Trotters-Actor")
        self.assertIsNotNone(audit_payload)
        assert audit_payload is not None
        self.assertEqual(audit_payload["outcome"], "actor_missing")
        self.assertEqual(audit_payload["actor"], "unknown")

    def test_start_campaign_route_uses_runtime_service(self) -> None:
        root = self._workspace_root("campaign_start")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.start_campaign",
                return_value={"campaign_id": "campaign-1", "outcome": "campaign_started"},
            ) as start_mock:
                status, _, body = self._invoke(
                    app,
                    "POST",
                    "/api/v1/campaigns",
                    body=json.dumps({"campaign_name": "manual-run", "config_path": "configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml"}).encode("utf-8"),
                    content_type="application/json",
                    headers=self._auth_headers(),
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "201 Created")
        self.assertEqual(payload["campaign_id"], "campaign-1")
        start_mock.assert_called_once()

    def test_job_detail_route_uses_runtime_service(self) -> None:
        root = self._workspace_root("job_detail")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.job_status",
                return_value={"job": {"job_id": "job-1", "status": "completed"}, "attempts": [], "artifacts": []},
            ) as job_mock:
                status, _, body = self._invoke(app, "GET", "/api/v1/jobs/job-1", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["job"]["job_id"], "job-1")
        job_mock.assert_called_once()

    def test_job_logs_route_returns_tail_payload(self) -> None:
        root = self._workspace_root("job_logs")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.read_job_log",
                return_value={"job_id": "job-1", "stream": "stderr", "tail_lines": 50, "lines": ["line a", "line b"]},
            ) as log_mock:
                status, _, body = self._invoke(app, "GET", "/api/v1/jobs/job-1/logs?stream=stderr&tail=50", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["stream"], "stderr")
        self.assertEqual(payload["tail_lines"], 50)
        self.assertEqual(payload["lines"], ["line a", "line b"])
        log_mock.assert_called_once()

    def test_artifacts_route_supports_campaign_filter(self) -> None:
        root = self._workspace_root("artifacts")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.artifact_status",
                return_value={"artifacts": [{"artifact_id": 1, "campaign_id": "campaign-1", "artifact_type": "report"}]},
            ) as artifact_mock:
                status, _, body = self._invoke(app, "GET", "/api/v1/artifacts?campaign_id=campaign-1&limit=25", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["artifacts"][0]["campaign_id"], "campaign-1")
        artifact_mock.assert_called_once()

    def test_notifications_route_supports_filters(self) -> None:
        root = self._workspace_root("notifications")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
            notifications_path.parent.mkdir(parents=True, exist_ok=True)
            notifications_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "recorded_at_utc": "2026-03-22T07:00:00+00:00",
                                "campaign_id": "campaign-1",
                                "event_type": "campaign_failed",
                                "severity": "error",
                            }
                        ),
                        json.dumps(
                            {
                                "recorded_at_utc": "2026-03-22T07:05:00+00:00",
                                "campaign_id": "campaign-2",
                                "event_type": "campaign_started",
                                "severity": "info",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "GET",
                "/api/v1/notifications?event_type=campaign_failed&severity=error&limit=5",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["notifications"]), 1)
        self.assertEqual(payload["notifications"][0]["campaign_id"], "campaign-1")

    def test_unknown_director_returns_not_found(self) -> None:
        root = self._workspace_root("director_missing")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            with patch(
                "trotters_trader.api.director_status",
                side_effect=ValueError("Unknown director 'director-missing'"),
            ):
                status, _, body = self._invoke(app, "GET", "/api/v1/directors/director-missing", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "404 Not Found")
        self.assertIn("Unknown director", payload["error"])

    def test_rejects_absolute_config_path(self) -> None:
        root = self._workspace_root("campaign_bad_path")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/campaigns",
                body=json.dumps({"config_path": "C:/temp/backtest.toml"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("repo-relative", payload["error"])

    def test_protected_route_requires_bearer_token(self) -> None:
        root = self._workspace_root("auth_required")
        try:
            app = ApiApp(ApiController(runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")), auth_token=self.AUTH_TOKEN)
            status, headers, body = self._invoke(app, "GET", "/api/v1/runtime/overview")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(dict(headers)["WWW-Authenticate"], "Bearer")
        self.assertEqual(payload["error"], "Unauthorized")

    def test_runtime_overview_includes_service_heartbeat_status(self) -> None:
        root = self._workspace_root("service_heartbeats")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            with (
                patch(
                    "trotters_trader.api.runtime_status",
                    return_value={
                        "counts": {"queued": 1, "running": 1},
                        "workers": [{"worker_id": "worker-01", "status": "running", "heartbeat_at": "2026-03-23T08:59:55+00:00"}],
                        "jobs": [{"job_id": "job-1", "status": "running", "updated_at": "2026-03-23T08:59:58+00:00"}],
                        "campaigns": [{"campaign_id": "campaign-1", "status": "running", "updated_at": "2026-03-23T08:59:59+00:00"}],
                        "directors": [{"director_id": "director-1", "status": "running", "updated_at": "2026-03-23T08:59:59+00:00"}],
                        "service_heartbeats": [
                            {"service": "coordinator", "status": "ok", "recorded_at_utc": "2026-03-23T08:59:59+00:00", "detail": "Heartbeat is fresh."},
                            {"service": "campaign-manager", "status": "stale", "recorded_at_utc": "2026-03-23T08:56:00+00:00", "detail": "Heartbeat is stale."},
                        ],
                    },
                ),
                patch("trotters_trader.api.director_status", return_value={"director": {"director_id": "director-1", "director_name": "director-1", "status": "running"}}),
                patch("trotters_trader.api.campaign_status", return_value={"campaign": {"campaign_id": "campaign-1", "campaign_name": "campaign-1", "status": "running"}}),
            ):
                status, _, body = self._invoke(app, "GET", "/api/v1/runtime/overview", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertIn(payload["health"]["status"], {"warning", "stalled"})
        self.assertEqual(payload["status"]["service_heartbeats"][1]["service"], "campaign-manager")

    def test_agent_summaries_route_returns_recorded_summaries(self) -> None:
        root = self._workspace_root("agent_summaries")
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
                    "recorded_at_utc": "2026-03-22T12:00:00+00:00",
                }),
                encoding="utf-8",
            )
            (paths.catalog_output_dir / "agent_summaries" / "index.json").write_text(
                json.dumps({"records": [{
                    "summary_type": "candidate_readiness_summary",
                    "agent_id": "candidate-review",
                    "classification": "research_only",
                    "status": "recorded",
                    "recorded_at_utc": "2026-03-22T12:00:00+00:00",
                }]}),
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(app, "GET", "/api/v1/agent-summaries", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["agent_summaries"][0]["agent_id"], "candidate-review")

    def test_agent_dispatches_route_returns_recent_telemetry(self) -> None:
        root = self._workspace_root("agent_dispatches")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            telemetry_dir = paths.catalog_output_dir / "agent_telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            (telemetry_dir / "dispatches.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "recorded_at_utc": "2026-03-22T12:10:00+00:00",
                        "agent_id": "research-triage",
                        "event_type": "campaign_finished",
                        "success": True,
                        "model": "gpt-5-nano",
                        "total_tokens": 321,
                    }),
                    json.dumps({
                        "recorded_at_utc": "2026-03-22T12:09:00+00:00",
                        "agent_id": "failure-postmortem",
                        "event_type": "campaign_failed",
                        "success": False,
                        "model": "gpt-5-nano",
                        "total_tokens": 111,
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(app, "GET", "/api/v1/agent-dispatches?limit=5", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["agent_dispatches"][0]["agent_id"], "research-triage")
        self.assertEqual(payload["summary"]["totals"]["runs"], 2)

    def test_paper_trading_status_route_returns_latest_day_and_action(self) -> None:
        root = self._workspace_root("paper_status")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            paper_root = paths.catalog_output_dir / "paper_trading"
            paper_root.mkdir(parents=True, exist_ok=True)
            (paper_root / "state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "portfolio": {"initialized": False, "cash": 0.0, "nav": 0.0, "holdings": []},
                    "current_day_status": "blocked",
                }),
                encoding="utf-8",
            )
            (paper_root / "days.jsonl").write_text(
                json.dumps({
                    "day_id": "paper-day-1",
                    "status": "blocked",
                    "summary": "Paper-trading rehearsal is blocked.",
                }) + "\n",
                encoding="utf-8",
            )
            (paper_root / "operator_actions.jsonl").write_text(
                json.dumps({
                    "action_id": "paper-action-1",
                    "action": "blocked",
                    "actor": "system",
                    "day_id": "paper-day-1",
                }) + "\n",
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(app, "GET", "/api/v1/paper-trading/status", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["latest_day"]["day_id"], "paper-day-1")
        self.assertEqual(payload["latest_action"]["action"], "blocked")
        self.assertIn("entry_gate", payload)

    def test_paper_trading_actions_route_records_operator_action(self) -> None:
        root = self._workspace_root("paper_action")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            paper_root = paths.catalog_output_dir / "paper_trading"
            day_dir = paper_root / "days" / "paper-day-1"
            day_dir.mkdir(parents=True, exist_ok=True)
            (day_dir / "paper_trade_decision.json").write_text(
                json.dumps({
                    "current_nav": 100000.0,
                    "target_holdings": [
                        {
                            "instrument": "ABC",
                            "projected_quantity": 10,
                            "reference_close": 100.0,
                            "projected_weight": 0.01,
                        }
                    ],
                }),
                encoding="utf-8",
            )
            (paper_root / "state.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "portfolio": {"initialized": False, "cash": 0.0, "nav": 0.0, "holdings": []},
                }),
                encoding="utf-8",
            )
            (paper_root / "days.jsonl").write_text(
                json.dumps({
                    "day_id": "paper-day-1",
                    "status": "ready",
                    "decision_date": "2026-03-22",
                    "profile_name": "sample_sma",
                    "artifact_paths": {"decision_json": str((day_dir / "paper_trade_decision.json").resolve())},
                }) + "\n",
                encoding="utf-8",
            )
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/paper-trading/actions",
                body=json.dumps({"action": "accepted", "day_id": "paper-day-1", "actor": "api-test", "reason": "accepted"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "201 Created")
        self.assertEqual(payload["action"]["action"], "accepted")
        self.assertTrue(payload["state"]["portfolio"]["initialized"])

    def test_promotion_path_routes_return_read_models(self) -> None:
        root = self._workspace_root("promotion_path")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            latest_dir = paths.catalog_output_dir / "agent_summaries" / "latest"
            latest_dir.mkdir(parents=True, exist_ok=True)
            app = ApiApp(ApiController(paths), auth_token=self.AUTH_TOKEN)
            progression_status, _, progression_body = self._invoke(
                app,
                "GET",
                "/api/v1/promotion-path/candidate-progression",
                headers=self._auth_headers(),
            )
            gate_status, _, gate_body = self._invoke(
                app,
                "GET",
                "/api/v1/promotion-path/paper-trade-entry-gate",
                headers=self._auth_headers(),
            )
            portfolio_status, _, portfolio_body = self._invoke(
                app,
                "GET",
                "/api/v1/promotion-path/research-program-portfolio",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        progression = json.loads(progression_body)
        gate = json.loads(gate_body)
        portfolio = json.loads(portfolio_body)
        self.assertEqual(progression_status, "200 OK")
        self.assertEqual(gate_status, "200 OK")
        self.assertEqual(portfolio_status, "200 OK")
        self.assertEqual(progression["summary_type"], "candidate_progression_summary")
        self.assertEqual(gate["summary_type"], "paper_trade_entry_gate")
        self.assertEqual(portfolio["summary_type"], "research_program_portfolio")
    def _invoke(
        self,
        app: ApiApp,
        method: str,
        path: str,
        *,
        body: bytes = b"",
        content_type: str = "text/plain",
        headers: dict[str, str] | None = None,
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
        for header_name, header_value in (headers or {}).items():
            environ_key = f"HTTP_{header_name.upper().replace('-', '_')}"
            environ[environ_key] = header_value
        chunks = app(environ, start_response)
        response_body = b"".join(chunks).decode("utf-8")
        return str(captured["status"]), list(captured["headers"]), response_body

    def _workspace_root(self, label: str) -> Path:
        root = Path("tests/.tmp_runtime") / f"api_{label}_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _auth_headers(self, *, actor: str = "test-agent") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.AUTH_TOKEN}",
            "X-Trotters-Actor": actor,
            "X-Request-Id": "test-request-id",
        }


if __name__ == "__main__":
    unittest.main()

