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
                        "state": {"final_decision": None},
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
