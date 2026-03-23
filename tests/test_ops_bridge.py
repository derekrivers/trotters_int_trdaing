from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
import json
import shutil
import unittest
import uuid

from trotters_trader.ops_bridge import OpsBridgeApp, OpsBridgeController
from trotters_trader.research_runtime import runtime_paths


class _FakeDockerClient:
    def __init__(self) -> None:
        self.project_name = "trottersindependanttraders"
        self.containers = {
            "research-api": [
                {
                    "container_id": "abc123",
                    "name": "/trottersindependanttraders-research-api-1",
                    "state": "running",
                    "status": "Up 10 minutes",
                    "image": "trotters:latest",
                }
            ],
            "openclaw-gateway": [
                {
                    "container_id": "gateway001",
                    "name": "/trottersindependanttraders-openclaw-gateway-1",
                    "state": "running",
                    "status": "Up 10 minutes",
                    "image": "ghcr.io/openclaw/openclaw:2026.3.1",
                }
            ],
            "worker": [
                {
                    "container_id": "worker001",
                    "name": "/trottersindependanttraders-worker-1",
                    "state": "running",
                    "status": "Up 10 minutes",
                    "image": "trotters:latest",
                },
                {
                    "container_id": "worker002",
                    "name": "/trottersindependanttraders-worker-2",
                    "state": "running",
                    "status": "Up 10 minutes",
                    "image": "trotters:latest",
                },
            ],
        }
        self.restarted: list[str] = []
        self.exec_calls: list[dict[str, object]] = []
        self.socket_path = "/var/run/docker.sock"

    def self_project_name(self) -> str:
        return self.project_name

    def list_service_containers(self, *, project_name: str, service_name: str) -> list[dict[str, object]]:
        assert project_name == self.project_name
        return list(self.containers.get(service_name, []))

    def restart_container(self, container_id: str, *, timeout_seconds: int = 10) -> None:
        self.restarted.append(container_id)

    def exec_command(
        self,
        container_id: str,
        command: list[str],
        *,
        timeout_seconds: float = 180.0,
    ) -> dict[str, object]:
        self.exec_calls.append(
            {
                "container_id": container_id,
                "command": list(command),
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "exec_id": "exec-1",
            "exit_code": 0,
            "running": False,
            "output": json.dumps({
                "runId": "run-1",
                "status": "ok",
                "summary": "completed",
                "result": {
                    "payloads": [{"text": "triage done"}],
                    "meta": {
                        "durationMs": 321,
                        "agentMeta": {
                            "provider": "openai",
                            "model": "gpt-5-nano",
                            "promptTokens": 123,
                            "usage": {"input": 11, "output": 7, "cacheRead": 5, "total": 23},
                        },
                    },
                },
            }),
        }


class OpsBridgeTests(unittest.TestCase):
    AUTH_TOKEN = "ops-token"

    def test_list_services_returns_allowlisted_service_snapshots(self) -> None:
        root = self._workspace_root("services")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=_FakeDockerClient())
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(app, "GET", "/api/v1/services", headers=self._auth_headers())
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["project_name"], "trottersindependanttraders")
        self.assertEqual(payload["services"][0]["service"], "research-api")

    def test_restart_service_rejects_non_allowlisted_service(self) -> None:
        root = self._workspace_root("service_blocked")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=_FakeDockerClient())
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/services/dashboard/restart",
                body=json.dumps({"reason": "investigate"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("allowed restart list", payload["error"])

    def test_restart_service_writes_audit_and_restarts_matching_containers(self) -> None:
        root = self._workspace_root("service_restart")
        docker = _FakeDockerClient()
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=docker)
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/services/worker/restart",
                body=json.dumps({"reason": "runtime_supervisor", "incident_id": "incident-1"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(actor="openclaw-supervisor"),
            )
            audit_lines = controller.audit_path.read_text(encoding="utf-8").splitlines()
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        audit_payload = json.loads(audit_lines[-1])
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["restarted_containers"]), 2)
        self.assertEqual(docker.restarted, ["worker001", "worker002"])
        self.assertEqual(audit_payload["actor"], "openclaw-supervisor")
        self.assertEqual(audit_payload["path"], "/api/v1/services/worker/restart")

    def test_restart_service_rejects_repeat_restart_inside_limit_window(self) -> None:
        root = self._workspace_root("service_limit")
        docker = _FakeDockerClient()
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=docker)
            controller.audit_path.parent.mkdir(parents=True, exist_ok=True)
            controller.audit_path.write_text(
                json.dumps(
                    {
                        "recorded_at_utc": datetime.now(UTC).isoformat(),
                        "path": "/api/v1/services/worker/restart",
                        "status": "200 OK",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/services/worker/restart",
                body=json.dumps({"reason": "runtime_supervisor", "incident_id": "incident-2"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(actor="openclaw-supervisor"),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("Restart limit reached", payload["error"])
        self.assertEqual(docker.restarted, [])

    def test_dispatch_agent_rejects_non_allowlisted_agent(self) -> None:
        root = self._workspace_root("agent_blocked")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=_FakeDockerClient())
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/agents/runtime-supervisor/dispatch",
                body=json.dumps({"message": "blocked"}).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("allowed dispatch list", payload["error"])

    def test_dispatch_agent_executes_openclaw_agent_in_gateway_container(self) -> None:
        root = self._workspace_root("agent_dispatch")
        docker = _FakeDockerClient()
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=docker)
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/agents/research-triage/dispatch",
                body=json.dumps(
                    {
                        "message": "triage campaign-1",
                        "campaign_id": "campaign-1",
                        "event_type": "campaign_finished",
                        "session_id": "research-triage-campaign-1",
                    }
                ).encode("utf-8"),
                content_type="application/json",
                headers=self._auth_headers(actor="runtime-notifier"),
            )
            audit_lines = controller.audit_path.read_text(encoding="utf-8").splitlines()
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        audit_payload = json.loads(audit_lines[-1])
        self.assertEqual(status, "200 OK")
        self.assertEqual(payload["agent_id"], "research-triage")
        self.assertEqual(payload["telemetry"]["model"], "gpt-5-nano")
        self.assertEqual(payload["telemetry"]["total_tokens"], 23)
        self.assertEqual(docker.exec_calls[0]["container_id"], "gateway001")
        self.assertIn("--agent", docker.exec_calls[0]["command"])
        self.assertIn("research-triage", docker.exec_calls[0]["command"])
        self.assertEqual(audit_payload["actor"], "runtime-notifier")
        self.assertEqual(audit_payload["path"], "/api/v1/agents/research-triage/dispatch")

    def test_protected_route_requires_bearer_token(self) -> None:
        root = self._workspace_root("auth_required")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=_FakeDockerClient())
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, headers, body = self._invoke(app, "GET", "/api/v1/services")
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(dict(headers)["WWW-Authenticate"], "Bearer")
        self.assertEqual(payload["error"], "Unauthorized")

    def test_mutation_route_requires_actor_header(self) -> None:
        root = self._workspace_root("actor_required")
        try:
            paths = runtime_paths(root / "runtime", catalog_output_dir=root / "catalog")
            runbook_path = self._write_runbook(root)
            controller = OpsBridgeController(paths, runbook_path=runbook_path, docker_client=_FakeDockerClient())
            app = OpsBridgeApp(controller, auth_token=self.AUTH_TOKEN)
            status, _, body = self._invoke(
                app,
                "POST",
                "/api/v1/services/worker/restart",
                body=json.dumps({"reason": "runtime_supervisor"}).encode("utf-8"),
                content_type="application/json",
                headers={"Authorization": f"Bearer {self.AUTH_TOKEN}"},
            )
            audit_lines = controller.audit_path.read_text(encoding="utf-8").splitlines()
        finally:
            shutil.rmtree(root, ignore_errors=True)

        payload = json.loads(body)
        audit_payload = json.loads(audit_lines[-1])
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(payload["error"], "Mutation requests require X-Trotters-Actor")
        self.assertEqual(audit_payload["outcome"], "actor_missing")
        self.assertEqual(audit_payload["actor"], "unknown")

    def _write_runbook(self, root: Path) -> Path:
        runbook_path = root / "trotters-runbook.json"
        runbook_path.write_text(
            json.dumps(
                {
                    "work_queue": [
                        {
                            "plan_id": "broad_operability",
                            "plan_file": "configs/directors/broad_operability.json",
                            "director_name": "broad-operability-director",
                            "enabled": True,
                            "priority": 1,
                        }
                    ],
                    "config_registry": {
                        "broad_primary": "configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml"
                    },
                    "service_allowlist": ["research-api", "worker"],
                    "agent_allowlist": ["research-triage", "failure-postmortem"],
                    "limits": {
                        "max_same_item_recoveries": 2,
                        "recovery_window_hours": 12,
                        "max_service_restarts_per_service_15m": 1,
                        "max_service_restarts_per_service_24h": 2,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return runbook_path

    def _invoke(
        self,
        app: OpsBridgeApp,
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
        root = Path("tests/.tmp_runtime") / f"ops_{label}_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _auth_headers(self, *, actor: str = "test-agent") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.AUTH_TOKEN}",
            "X-Trotters-Actor": actor,
            "X-Request-Id": "ops-request-id",
        }


if __name__ == "__main__":
    unittest.main()
