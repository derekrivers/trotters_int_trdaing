from __future__ import annotations

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
        self.socket_path = "/var/run/docker.sock"

    def self_project_name(self) -> str:
        return self.project_name

    def list_service_containers(self, *, project_name: str, service_name: str) -> list[dict[str, object]]:
        assert project_name == self.project_name
        return list(self.containers.get(service_name, []))

    def restart_container(self, container_id: str, *, timeout_seconds: int = 10) -> None:
        self.restarted.append(container_id)


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
