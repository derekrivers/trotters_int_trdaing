from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
import http.client
import json
import os
from pathlib import Path
import socket
from typing import Callable
from urllib.parse import parse_qs, quote
import uuid
from wsgiref.simple_server import make_server

from trotters_trader.agent_dispatches import append_dispatch_record
from trotters_trader.http_security import actor_label, is_bearer_authorized, request_actor
from trotters_trader.research_runtime import ResearchRuntimePaths
from trotters_trader.supervisor_runbook import SupervisorRunbook, load_supervisor_runbook


@dataclass(frozen=True)
class OpsBridgeResponse:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 10.0):
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(self._socket_path)
        self.sock = sock


class DockerEngineClient:
    def __init__(self, *, socket_path: str = "/var/run/docker.sock", timeout_seconds: float = 10.0) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds

    @property
    def socket_path(self) -> str:
        return self._socket_path

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | list[object] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = _UnixSocketHTTPConnection(self._socket_path, timeout=self._timeout_seconds)
        try:
            connection.request(method.upper(), path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
        finally:
            connection.close()
        if response.status not in expected_statuses:
            raise ValueError(f"Docker API {method.upper()} {path} returned {response.status}: {data.decode('utf-8', errors='replace')[:4000]}")
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | list[object] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        timeout_seconds: float | None = None,
    ) -> bytes:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = _UnixSocketHTTPConnection(
            self._socket_path,
            timeout=self._timeout_seconds if timeout_seconds is None else timeout_seconds,
        )
        try:
            connection.request(method.upper(), path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
        finally:
            connection.close()
        if response.status not in expected_statuses:
            raise ValueError(f"Docker API {method.upper()} {path} returned {response.status}: {data.decode('utf-8', errors='replace')[:4000]}")
        return data

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | list[object] | None = None,
        expected_statuses: tuple[int, ...] = (200, 204),
    ) -> None:
        self.request_json(method, path, payload=payload, expected_statuses=expected_statuses)

    def self_project_name(self) -> str:
        explicit = os.environ.get("COMPOSE_PROJECT_NAME", "").strip()
        if explicit:
            return explicit
        container_id = os.environ.get("HOSTNAME", "").strip()
        if not container_id:
            raise ValueError("Unable to determine the current container id from HOSTNAME")
        payload = self.request_json("GET", f"/containers/{quote(container_id, safe='')}/json")
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Docker container inspection payload")
        labels = payload.get("Config", {}).get("Labels", {})
        if not isinstance(labels, dict):
            labels = payload.get("Config", {}).get("Labels") or {}
        project_name = str(labels.get("com.docker.compose.project", "") or "").strip()
        if not project_name:
            raise ValueError("Unable to determine the Compose project label for ops-bridge")
        return project_name

    def list_service_containers(self, *, project_name: str, service_name: str) -> list[dict[str, object]]:
        filters = json.dumps(
            {
                "label": [
                    f"com.docker.compose.project={project_name}",
                    f"com.docker.compose.service={service_name}",
                ]
            }
        )
        payload = self.request_json("GET", f"/containers/json?all=1&filters={quote(filters, safe='')}")
        if not isinstance(payload, list):
            raise ValueError("Unexpected Docker containers payload")
        containers: list[dict[str, object]] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            names = entry.get("Names", [])
            if not isinstance(names, list):
                names = []
            containers.append(
                {
                    "container_id": str(entry.get("Id", "")),
                    "name": str(names[0] if names else entry.get("Id", "")),
                    "state": str(entry.get("State", "")),
                    "status": str(entry.get("Status", "")),
                    "image": str(entry.get("Image", "")),
                }
            )
        return containers

    def restart_container(self, container_id: str, *, timeout_seconds: int = 10) -> None:
        self.request(
            "POST",
            f"/containers/{quote(container_id, safe='')}/restart?t={int(timeout_seconds)}",
            expected_statuses=(204,),
        )

    def exec_command(
        self,
        container_id: str,
        command: list[str],
        *,
        timeout_seconds: float = 180.0,
    ) -> dict[str, object]:
        if not command:
            raise ValueError("Docker exec command must not be empty")
        payload = self.request_json(
            "POST",
            f"/containers/{quote(container_id, safe='')}/exec",
            payload={
                "AttachStdout": True,
                "AttachStderr": True,
                "Cmd": command,
                "Tty": True,
            },
            expected_statuses=(201,),
        )
        if not isinstance(payload, dict):
            raise ValueError("Unexpected Docker exec creation payload")
        exec_id = str(payload.get("Id", "")).strip()
        if not exec_id:
            raise ValueError("Docker exec creation did not return an exec id")
        output = self.request_raw(
            "POST",
            f"/exec/{quote(exec_id, safe='')}/start",
            payload={"Detach": False, "Tty": True},
            expected_statuses=(200,),
            timeout_seconds=timeout_seconds,
        )
        inspect = self.request_json("GET", f"/exec/{quote(exec_id, safe='')}/json")
        if not isinstance(inspect, dict):
            raise ValueError("Unexpected Docker exec inspect payload")
        return {
            "exec_id": exec_id,
            "exit_code": inspect.get("ExitCode"),
            "running": inspect.get("Running"),
            "output": output.decode("utf-8", errors="replace"),
        }


class OpsBridgeController:
    def __init__(
        self,
        paths: ResearchRuntimePaths,
        *,
        runbook_path: Path | str,
        docker_client: DockerEngineClient | None = None,
    ) -> None:
        self._paths = paths
        self._runbook_path = Path(runbook_path)
        self._docker_client = docker_client or DockerEngineClient()
        self._audit_path = self._paths.runtime_root / "exports" / "ops_audit.jsonl"

    @property
    def audit_path(self) -> Path:
        return self._audit_path

    def health(self) -> dict[str, object]:
        project_name = None
        error = None
        try:
            project_name = self._docker_client.self_project_name()
        except Exception as exc:  # pragma: no cover - defensive guard
            error = str(exc)
        return {
            "ok": error is None,
            "docker_socket_path": self._docker_client.socket_path,
            "project_name": project_name,
            "error": error,
        }

    def list_services(self) -> dict[str, object]:
        runbook = self._load_runbook()
        project_name = self._docker_client.self_project_name()
        services = [self._service_snapshot(project_name, service_name, runbook) for service_name in runbook.service_allowlist]
        return {
            "project_name": project_name,
            "service_allowlist": list(runbook.service_allowlist),
            "services": services,
            "limits": _limits_payload(runbook),
        }

    def restart_service(self, service_name: str, payload: dict[str, object]) -> dict[str, object]:
        runbook = self._load_runbook()
        normalized = service_name.strip()
        if normalized not in runbook.service_allowlist:
            raise ValueError(f"Service '{service_name}' is not in the allowed restart list")
        counts = _recent_restart_counts(self._audit_path, normalized)
        limits = runbook.limits
        if counts["last_15m"] >= limits.max_service_restarts_per_service_15m:
            raise ValueError(f"Restart limit reached for service '{normalized}' in the last 15 minutes")
        if counts["last_24h"] >= limits.max_service_restarts_per_service_24h:
            raise ValueError(f"Restart limit reached for service '{normalized}' in the last 24 hours")

        project_name = self._docker_client.self_project_name()
        containers = self._docker_client.list_service_containers(project_name=project_name, service_name=normalized)
        if not containers:
            raise ValueError(f"No Compose containers found for service '{normalized}'")
        restarted: list[dict[str, object]] = []
        for container in containers:
            container_id = str(container.get("container_id", "")).strip()
            if not container_id:
                continue
            self._docker_client.restart_container(container_id)
            restarted.append(
                {
                    "container_id": container_id,
                    "name": container.get("name"),
                }
            )
        return {
            "service": normalized,
            "project_name": project_name,
            "restarted_containers": restarted,
            "reason": _optional_text(payload.get("reason")) or "operator_restart",
            "incident_id": _optional_text(payload.get("incident_id")),
            "counts_before_restart": counts,
            "limits": _limits_payload(runbook),
        }

    def dispatch_agent(self, agent_id: str, payload: dict[str, object]) -> dict[str, object]:
        runbook = self._load_runbook()
        normalized = agent_id.strip()
        if normalized not in runbook.agent_allowlist:
            raise ValueError(f"Agent '{agent_id}' is not in the allowed dispatch list")
        message = _required_text(payload.get("message"), "message")
        project_name = self._docker_client.self_project_name()
        containers = self._docker_client.list_service_containers(project_name=project_name, service_name="openclaw-gateway")
        container = next((entry for entry in containers if str(entry.get("state", "")).lower() == "running"), None)
        if container is None:
            raise ValueError("No running openclaw-gateway container found")
        container_id = str(container.get("container_id", "")).strip()
        if not container_id:
            raise ValueError("openclaw-gateway container id is unavailable")
        command = [
            "openclaw",
            "agent",
            "--agent",
            normalized,
            "--message",
            message,
            "--json",
            "--thinking",
            _optional_text(payload.get("thinking")) or "low",
            "--timeout",
            str(int(payload.get("timeout_seconds", 180) or 180)),
        ]
        session_id = _optional_text(payload.get("session_id"))
        if session_id:
            command.extend(["--session-id", session_id])
        execution = self._docker_client.exec_command(
            container_id,
            command,
            timeout_seconds=float(payload.get("timeout_seconds", 180) or 180),
        )
        output_text = str(execution.get("output", ""))
        try:
            parsed_output = json.loads(output_text) if output_text.strip() else {}
        except json.JSONDecodeError:
            parsed_output = {"raw": output_text}
        event_type = _optional_text(payload.get("event_type"))
        campaign_id = _optional_text(payload.get("campaign_id"))
        profile_name = _optional_text(payload.get("profile_name"))
        telemetry = _agent_dispatch_telemetry(
            agent_id=normalized,
            event_type=event_type,
            campaign_id=campaign_id,
            profile_name=profile_name,
            session_id=session_id,
            fingerprint=_optional_text(payload.get("fingerprint")),
            parsed_output=parsed_output,
            execution=execution,
        )
        append_dispatch_record(self._paths.catalog_output_dir, telemetry)
        exit_code = execution.get("exit_code")
        if exit_code not in (0, None):
            raise ValueError(f"OpenClaw agent dispatch for '{normalized}' failed with exit code {exit_code}")
        return {
            "agent_id": normalized,
            "project_name": project_name,
            "container_id": container_id,
            "session_id": session_id,
            "event_type": event_type,
            "campaign_id": campaign_id,
            "result": parsed_output,
            "exec": execution,
            "telemetry": telemetry,
        }

    def _load_runbook(self) -> SupervisorRunbook:
        return load_supervisor_runbook(self._runbook_path)

    def _service_snapshot(
        self,
        project_name: str,
        service_name: str,
        runbook: SupervisorRunbook,
    ) -> dict[str, object]:
        containers = self._docker_client.list_service_containers(project_name=project_name, service_name=service_name)
        running = sum(1 for entry in containers if str(entry.get("state", "")).lower() == "running")
        return {
            "service": service_name,
            "container_count": len(containers),
            "running_count": running,
            "containers": containers,
            "restart_counts": _recent_restart_counts(self._audit_path, service_name),
            "limits": _limits_payload(runbook),
        }


class OpsBridgeApp:
    def __init__(self, controller: OpsBridgeController, *, auth_token: str) -> None:
        self._controller = controller
        self._auth_token = auth_token.strip()
        if not self._auth_token:
            raise ValueError("TROTTERS_OPS_BRIDGE_TOKEN is required to serve ops-bridge")

    def __call__(self, environ: dict[str, object], start_response: Callable[[str, list[tuple[str, str]]], None]):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        query_string = str(environ.get("QUERY_STRING", ""))
        body = _read_body(environ)
        request_id = _request_id(environ)
        actor = request_actor(environ)
        remote_addr = str(environ.get("REMOTE_ADDR", "") or "").strip() or None
        protected = path.startswith("/api/v1")
        mutation = method in {"POST", "PUT", "PATCH", "DELETE"}
        audit_payload = _audit_payload(body)

        if protected and not is_bearer_authorized(environ, self._auth_token):
            response = _with_headers(
                _json_error_response(
                    "401 Unauthorized",
                    "Unauthorized",
                    extra_headers=[("WWW-Authenticate", "Bearer")],
                ),
                [("X-Request-Id", request_id)],
            )
            _write_audit_record(
                self._controller.audit_path,
                {
                    "recorded_at_utc": _utcnow(),
                    "request_id": request_id,
                    "actor": actor_label(actor),
                    "method": method,
                    "path": path,
                    "query_string": query_string,
                    "status": response.status,
                    "mutation": mutation,
                    "authenticated": False,
                    "outcome": "auth_failed",
                    "remote_addr": remote_addr,
                    "request_payload": audit_payload,
                },
            )
            start_response(response.status, response.headers)
            return [response.body]
        if protected and mutation and not actor:
            response = _with_headers(
                _json_error_response("400 Bad Request", "Mutation requests require X-Trotters-Actor"),
                [("X-Request-Id", request_id)],
            )
            _write_audit_record(
                self._controller.audit_path,
                {
                    "recorded_at_utc": _utcnow(),
                    "request_id": request_id,
                    "actor": actor_label(actor),
                    "method": method,
                    "path": path,
                    "query_string": query_string,
                    "status": response.status,
                    "mutation": mutation,
                    "authenticated": True,
                    "outcome": "actor_missing",
                    "remote_addr": remote_addr,
                    "request_payload": audit_payload,
                },
            )
            start_response(response.status, response.headers)
            return [response.body]
        try:
            response = self.handle_request(method, path, body)
        except ValueError as exc:
            response = _json_error_response(_error_status_for(exc), str(exc))
        except Exception as exc:  # pragma: no cover - defensive guard
            response = _json_error_response("500 Internal Server Error", f"Unhandled ops-bridge error: {exc}")
        if protected:
            outcome = "mutation" if mutation and response.status.startswith("2") else "error" if response.status.startswith("5") else "read"
            _write_audit_record(
                self._controller.audit_path,
                {
                    "recorded_at_utc": _utcnow(),
                    "request_id": request_id,
                    "actor": actor_label(actor),
                    "method": method,
                    "path": path,
                    "query_string": query_string,
                    "status": response.status,
                    "mutation": mutation,
                    "authenticated": True,
                    "outcome": outcome,
                    "remote_addr": remote_addr,
                    "request_payload": audit_payload,
                },
            )
        response = _with_headers(response, [("X-Request-Id", request_id)])
        start_response(response.status, response.headers)
        return [response.body]

    def handle_request(self, method: str, path: str, body: bytes) -> OpsBridgeResponse:
        if method == "GET" and path == "/healthz":
            return self._json_response(self._controller.health())
        if method == "GET" and path == "/api/v1/services":
            return self._json_response(self._controller.list_services())
        if path.startswith("/api/v1/agents/"):
            agent_id, action = _resource_path(path, "/api/v1/agents/")
            if action != "dispatch":
                raise ValueError(f"Unknown agent action '{action}'")
            if method != "POST":
                raise ValueError("Only POST is supported for agent action routes")
            return self._json_response(self._controller.dispatch_agent(agent_id, _json_body(body)))
        if path.startswith("/api/v1/services/"):
            service_name, action = _resource_path(path, "/api/v1/services/")
            if action != "restart":
                raise ValueError(f"Unknown service action '{action}'")
            if method != "POST":
                raise ValueError("Only POST is supported for service action routes")
            return self._json_response(self._controller.restart_service(service_name, _json_body(body)))
        return _json_error_response("404 Not Found", f"Unknown route '{escape(path)}'")

    def _json_response(self, payload: dict[str, object], *, status: str = "200 OK") -> OpsBridgeResponse:
        return OpsBridgeResponse(
            status,
            [("Content-Type", "application/json; charset=utf-8")],
            json.dumps(payload, indent=2, default=str).encode("utf-8"),
        )


def serve_ops_bridge(
    paths: ResearchRuntimePaths,
    *,
    runbook_path: Path | str,
    host: str = "0.0.0.0",
    port: int = 8891,
    docker_socket_path: str = "/var/run/docker.sock",
) -> dict[str, object]:
    auth_token = os.environ.get("TROTTERS_OPS_BRIDGE_TOKEN", "").strip()
    controller = OpsBridgeController(
        paths,
        runbook_path=runbook_path,
        docker_client=DockerEngineClient(socket_path=docker_socket_path),
    )
    app = OpsBridgeApp(controller, auth_token=auth_token)
    with make_server(host, port, app) as server:
        print(f"Ops bridge listening on http://{host}:{port}", flush=True)
        server.serve_forever()
    return {"host": host, "port": port}


def _agent_dispatch_telemetry(
    *,
    agent_id: str,
    event_type: str | None,
    campaign_id: str | None,
    profile_name: str | None,
    session_id: str | None,
    fingerprint: str | None,
    parsed_output: dict[str, object],
    execution: dict[str, object],
) -> dict[str, object]:
    recorded_at = _utcnow()
    result_payload = parsed_output.get("result") if isinstance(parsed_output.get("result"), dict) else {}
    meta = result_payload.get("meta") if isinstance(result_payload.get("meta"), dict) else {}
    agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
    usage = agent_meta.get("usage") if isinstance(agent_meta.get("usage"), dict) else {}
    payloads = result_payload.get("payloads") if isinstance(result_payload.get("payloads"), list) else []
    first_payload = payloads[0] if payloads and isinstance(payloads[0], dict) else {}
    summary_text = str(first_payload.get("text", "") or "").strip()
    return {
        "dispatch_id": uuid.uuid4().hex,
        "recorded_at_utc": recorded_at,
        "agent_id": agent_id,
        "event_type": event_type,
        "campaign_id": campaign_id,
        "profile_name": profile_name,
        "session_id": session_id,
        "fingerprint": fingerprint,
        "attempted": True,
        "success": execution.get("exit_code") in (0, None),
        "suppressed": False,
        "provider": _optional_text(agent_meta.get("provider")),
        "model": _optional_text(agent_meta.get("model")),
        "duration_ms": int(meta.get("durationMs", 0) or 0),
        "prompt_tokens": int(agent_meta.get("promptTokens", 0) or 0),
        "input_tokens": int(usage.get("input", 0) or 0),
        "output_tokens": int(usage.get("output", 0) or 0),
        "cache_read_tokens": int(usage.get("cacheRead", 0) or 0),
        "cache_write_tokens": int(usage.get("cacheWrite", 0) or 0),
        "total_tokens": int(usage.get("total", 0) or 0),
        "response_summary": summary_text[:400] if summary_text else None,
        "status_code": execution.get("exit_code"),
        "error": None if execution.get("exit_code") in (0, None) else str(execution.get("output", "") or "")[:400],
    }


def _recent_restart_counts(audit_path: Path, service_name: str) -> dict[str, int]:
    records = _read_jsonl(audit_path)
    now = datetime.now(UTC)
    fifteen_minutes_ago = now - timedelta(minutes=15)
    twenty_four_hours_ago = now - timedelta(hours=24)
    last_15m = 0
    last_24h = 0
    for entry in records:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("path", "")) != f"/api/v1/services/{service_name}/restart":
            continue
        if not str(entry.get("status", "")).startswith("2"):
            continue
        recorded_at = _parse_timestamp(_optional_text(entry.get("recorded_at_utc")))
        if recorded_at is None:
            continue
        if recorded_at >= twenty_four_hours_ago:
            last_24h += 1
        if recorded_at >= fifteen_minutes_ago:
            last_15m += 1
    return {"last_15m": last_15m, "last_24h": last_24h}


def _limits_payload(runbook: SupervisorRunbook) -> dict[str, int]:
    return {
        "max_same_item_recoveries": runbook.limits.max_same_item_recoveries,
        "recovery_window_hours": runbook.limits.recovery_window_hours,
        "max_service_restarts_per_service_15m": runbook.limits.max_service_restarts_per_service_15m,
        "max_service_restarts_per_service_24h": runbook.limits.max_service_restarts_per_service_24h,
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _read_body(environ: dict[str, object]) -> bytes:
    length_text = str(environ.get("CONTENT_LENGTH", "") or "0").strip()
    try:
        length = int(length_text)
    except ValueError:
        length = 0
    body_stream = environ.get("wsgi.input")
    if length <= 0 or body_stream is None:
        return b""
    return body_stream.read(length)


def _json_body(body: bytes) -> dict[str, object]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _resource_path(path: str, prefix: str) -> tuple[str, str | None]:
    suffix = path.removeprefix(prefix).strip("/")
    if not suffix:
        raise ValueError("Resource id is required")
    parts = suffix.split("/")
    resource_id = parts[0]
    if not resource_id:
        raise ValueError("Resource id is required")
    if len(parts) == 1:
        return resource_id, None
    return resource_id, parts[1]


def _error_status_for(exc: ValueError) -> str:
    message = str(exc)
    if message.startswith("Unknown "):
        return "404 Not Found"
    return "400 Bad Request"


def _json_error_response(
    status: str,
    message: str,
    *,
    extra_headers: list[tuple[str, str]] | None = None,
) -> OpsBridgeResponse:
    return OpsBridgeResponse(
        status,
        [("Content-Type", "application/json; charset=utf-8"), *(extra_headers or [])],
        json.dumps({"error": message}, indent=2).encode("utf-8"),
    )


def _required_text(value: object, label: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _request_id(environ: dict[str, object]) -> str:
    provided = str(environ.get("HTTP_X_REQUEST_ID", "") or "").strip()
    return provided or uuid.uuid4().hex


def _audit_payload(body: bytes) -> object:
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")[:4000]
    if isinstance(payload, (dict, list)):
        return payload
    return str(payload)[:4000]


def _write_audit_record(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")


def _with_headers(response: OpsBridgeResponse, extra_headers: list[tuple[str, str]]) -> OpsBridgeResponse:
    return OpsBridgeResponse(response.status, [*response.headers, *extra_headers], response.body)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
