from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
import json
import os
from pathlib import Path, PurePosixPath
import socketserver
from typing import Callable
from urllib.parse import parse_qs
import uuid
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from trotters_trader.agent_dispatches import load_dispatch_records, load_dispatch_summary
from trotters_trader.active_branch import build_active_branch_summary
from trotters_trader.agent_summaries import load_latest_summaries, load_summary_records
from trotters_trader.dashboard import _runtime_health
from trotters_trader.http_security import actor_label, is_bearer_authorized, request_actor
from trotters_trader.paper_rehearsal import paper_rehearsal_status, record_paper_trade_action
from trotters_trader.promotion_path import materialize_promotion_path, resolve_current_best_candidate
from trotters_trader.research_families import (
    build_next_family_status,
    build_research_family_comparison_summary,
    bootstrap_research_family,
)
from trotters_trader.runbook_queue import build_runbook_queue_summary
from trotters_trader.research_runtime import (
    DEFAULT_NOTIFICATION_EVENTS,
    ResearchRuntimePaths,
    artifact_status,
    campaign_status,
    director_status,
    job_status,
    pause_director,
    read_job_log,
    resume_director,
    runtime_status,
    skip_director_next,
    start_campaign,
    start_director,
    stop_campaign,
    stop_director,
)


class _ThreadingWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    daemon_threads = True


@dataclass(frozen=True)
class ApiResponse:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


class ApiController:
    def __init__(self, paths: ResearchRuntimePaths) -> None:
        self._paths = paths

    @property
    def paths(self) -> ResearchRuntimePaths:
        return self._paths

    def overview(self) -> dict[str, object]:
        status = runtime_status(self._paths)
        compact_status = _compact_overview_status(status)
        active_directors = [
            _detail_or_summary(
                lambda director_id=str(director.get("director_id", "")): director_status(self._paths, director_id).get("director", {}),
                director,
            )
            for director in status.get("directors", [])
            if isinstance(director, dict) and str(director.get("status", "")).lower() in {"queued", "running", "paused"}
        ]
        active_campaigns = [
            _detail_or_summary(
                lambda campaign_id=str(campaign.get("campaign_id", "")): campaign_status(self._paths, campaign_id).get("campaign", {}),
                campaign,
            )
            for campaign in status.get("campaigns", [])
            if isinstance(campaign, dict) and str(campaign.get("status", "")).lower() in {"queued", "running"}
        ]
        notifications = _load_notifications(self._paths, limit=25)
        most_recent_terminal = _most_recent_terminal(status)
        agent_summaries = load_latest_summaries(self._paths.catalog_output_dir)
        current_best_candidate = resolve_current_best_candidate(
            catalog_output_dir=self._paths.catalog_output_dir,
            active_campaigns=active_campaigns,
            most_recent_terminal=most_recent_terminal,
            agent_summaries=agent_summaries,
            fetch_campaign_detail=lambda campaign_id: campaign_status(self._paths, campaign_id).get("campaign", {}),
        )
        promotion_path = materialize_promotion_path(
            catalog_output_dir=self._paths.catalog_output_dir,
            current_best_candidate=current_best_candidate,
            agent_summaries=agent_summaries,
        )
        research_family_comparison_summary = build_research_family_comparison_summary(
            catalog_output_dir=self._paths.catalog_output_dir,
            research_program_portfolio=promotion_path["research_program_portfolio"],
        )
        active_branch_summary = build_active_branch_summary(
            active_directors=active_directors,
            active_campaigns=active_campaigns,
        )
        runbook_queue_summary = build_runbook_queue_summary(
            active_branch_summary=active_branch_summary,
            research_program_portfolio=promotion_path["research_program_portfolio"],
            research_family_comparison_summary=research_family_comparison_summary,
        )
        next_family_status = build_next_family_status(
            catalog_output_dir=self._paths.catalog_output_dir,
            runbook_queue_summary=runbook_queue_summary,
            research_family_comparison_summary=research_family_comparison_summary,
            active_branch_summary=active_branch_summary,
        )
        return {
            "status": compact_status,
            "active_directors": active_directors,
            "active_campaigns": active_campaigns,
            "active_branch_summary": active_branch_summary,
            "runbook_queue_summary": runbook_queue_summary,
            "research_family_comparison_summary": research_family_comparison_summary,
            "next_family_status": next_family_status,
            "notifications": notifications,
            "most_recent_terminal": most_recent_terminal,
            "health": _runtime_health(status=status, campaigns=active_campaigns, directors=active_directors, next_family_status=next_family_status),
            "paper_rehearsal": paper_rehearsal_status(self._paths.catalog_output_dir, limit=5),
            "current_best_candidate": current_best_candidate,
            "candidate_progression_summary": promotion_path["candidate_progression_summary"],
            "paper_trade_entry_gate": promotion_path["paper_trade_entry_gate"],
            "research_program_portfolio": promotion_path["research_program_portfolio"],
            "agent_summaries": agent_summaries,
            "agent_dispatches": load_dispatch_records(self._paths.catalog_output_dir, limit=10),
            "agent_dispatch_summary": load_dispatch_summary(self._paths.catalog_output_dir, limit=100),
        }

    def list_notifications(self, query: dict[str, list[str]]) -> dict[str, object]:
        return {
            "notifications": _load_notifications(
                self._paths,
                limit=_query_int(query, "limit", default=100),
                event_type=_query_value(query, "event_type"),
                campaign_id=_query_value(query, "campaign_id"),
                severity=_query_value(query, "severity"),
            )
        }

    def list_directors(self) -> dict[str, object]:
        return director_status(self._paths, None)

    def director_detail(self, director_id: str) -> dict[str, object]:
        return director_status(self._paths, director_id)

    def start_director(self, payload: dict[str, object]) -> dict[str, object]:
        config_path = _optional_config_path(payload.get("config_path"))
        director_plan_file = _optional_plan_path(payload.get("director_plan_file"))
        if config_path is None and director_plan_file is None:
            raise ValueError("director start requires config_path or director_plan_file")
        plan_payload = _load_plan_payload(director_plan_file) if director_plan_file else None
        notify_events = _notify_events(payload.get("notify_events"))
        return start_director(
            self._paths,
            config_path=config_path,
            director_name=_optional_text(payload.get("director_name")),
            evaluation_profile=_optional_text(payload.get("evaluation_profile")),
            quality_gate=_quality_gate(payload.get("quality_gate")),
            max_hours=_float_value(payload.get("campaign_max_hours"), default=24.0),
            max_jobs=_int_value(payload.get("campaign_max_jobs"), default=0),
            stage_candidate_limit=_int_value(payload.get("stage_candidate_limit"), default=0),
            shortlist_size=_int_value(payload.get("shortlist_size"), default=3),
            notification_command=_optional_text(payload.get("notification_command")),
            notify_events=notify_events or DEFAULT_NOTIFICATION_EVENTS,
            plan_payload=plan_payload,
            plan_file_path=director_plan_file,
            adopt_active_campaigns=bool(payload.get("adopt_active_campaigns", True)),
        )

    def pause_director(self, director_id: str, payload: dict[str, object]) -> dict[str, object]:
        return pause_director(self._paths, director_id, reason=_reason(payload, default="operator_pause"))

    def resume_director(self, director_id: str, payload: dict[str, object]) -> dict[str, object]:
        return resume_director(self._paths, director_id, reason=_reason(payload, default="operator_resume"))

    def skip_director_next(self, director_id: str, payload: dict[str, object]) -> dict[str, object]:
        return skip_director_next(self._paths, director_id, reason=_reason(payload, default="operator_skip"))

    def stop_director(self, director_id: str, payload: dict[str, object]) -> dict[str, object]:
        return stop_director(
            self._paths,
            director_id,
            stop_active_campaign=bool(payload.get("stop_active_campaign", False)),
            reason=_reason(payload, default="operator_stop"),
        )

    def list_campaigns(self) -> dict[str, object]:
        return campaign_status(self._paths, None)

    def campaign_detail(self, campaign_id: str) -> dict[str, object]:
        return campaign_status(self._paths, campaign_id)

    def start_campaign(self, payload: dict[str, object]) -> dict[str, object]:
        config_path = _required_config_path(payload.get("config_path"))
        notify_events = _notify_events(payload.get("notify_events"))
        return start_campaign(
            self._paths,
            config_path,
            campaign_name=_optional_text(payload.get("campaign_name")),
            evaluation_profile=_optional_text(payload.get("evaluation_profile")),
            quality_gate=_quality_gate(payload.get("quality_gate")),
            max_hours=_float_value(payload.get("campaign_max_hours"), default=24.0),
            max_jobs=_int_value(payload.get("campaign_max_jobs"), default=0),
            stage_candidate_limit=_int_value(payload.get("stage_candidate_limit"), default=0),
            shortlist_size=_int_value(payload.get("shortlist_size"), default=3),
            notification_command=_optional_text(payload.get("notification_command")),
            notify_events=notify_events or DEFAULT_NOTIFICATION_EVENTS,
        )

    def stop_campaign(self, campaign_id: str, payload: dict[str, object]) -> dict[str, object]:
        return stop_campaign(
            self._paths,
            campaign_id,
            cancel_queued=bool(payload.get("cancel_queued", True)),
            reason=_reason(payload, default="operator_stop"),
        )

    def list_jobs(self, query: dict[str, list[str]]) -> dict[str, object]:
        return job_status(
            self._paths,
            None,
            campaign_id=_query_value(query, "campaign_id"),
            status=_query_value(query, "status"),
        )

    def job_detail(self, job_id: str) -> dict[str, object]:
        return job_status(self._paths, job_id)

    def job_logs(self, job_id: str, query: dict[str, list[str]]) -> dict[str, object]:
        return read_job_log(
            self._paths,
            job_id,
            stream=_query_value(query, "stream") or "stderr",
            tail_lines=_query_int(query, "tail", default=200),
        )

    def list_artifacts(self, query: dict[str, list[str]]) -> dict[str, object]:
        return artifact_status(
            self._paths,
            job_id=_query_value(query, "job_id"),
            campaign_id=_query_value(query, "campaign_id"),
            artifact_type=_query_value(query, "artifact_type"),
            limit=_query_int(query, "limit", default=200),
        )

    def list_agent_summaries(self, query: dict[str, list[str]]) -> dict[str, object]:
        return {
            "agent_summaries": load_summary_records(
                self._paths.catalog_output_dir,
                summary_type=_query_value(query, "summary_type"),
                limit=_query_int(query, "limit", default=20),
            )
        }

    def list_agent_dispatches(self, query: dict[str, list[str]]) -> dict[str, object]:
        success_value = _query_value(query, "success")
        success_filter = None
        if success_value is not None:
            success_filter = success_value.strip().lower() in {"1", "true", "yes", "ok"}
        limit = _query_int(query, "limit", default=20)
        return {
            "agent_dispatches": load_dispatch_records(
                self._paths.catalog_output_dir,
                agent_id=_query_value(query, "agent_id"),
                event_type=_query_value(query, "event_type"),
                success=success_filter,
                limit=limit,
            ),
            "summary": load_dispatch_summary(self._paths.catalog_output_dir, limit=max(limit, 100)),
        }

    def paper_rehearsal_status(self, query: dict[str, list[str]]) -> dict[str, object]:
        return paper_rehearsal_status(
            self._paths.catalog_output_dir,
            limit=_query_int(query, "limit", default=10),
        )

    def candidate_progression_summary(self) -> dict[str, object]:
        return materialize_promotion_path(catalog_output_dir=self._paths.catalog_output_dir)["candidate_progression_summary"]

    def active_branch_summary(self) -> dict[str, object]:
        overview = self.overview()
        payload = overview.get("active_branch_summary")
        return payload if isinstance(payload, dict) else {}

    def current_best_candidate_summary(self) -> dict[str, object]:
        overview = self.overview()
        payload = overview.get("current_best_candidate")
        return payload if isinstance(payload, dict) else {}

    def runbook_queue_summary(self) -> dict[str, object]:
        overview = self.overview()
        payload = overview.get("runbook_queue_summary")
        return payload if isinstance(payload, dict) else {}

    def research_family_comparison_summary(self) -> dict[str, object]:
        overview = self.overview()
        payload = overview.get("research_family_comparison_summary")
        return payload if isinstance(payload, dict) else {}

    def current_research_family_proposal(self) -> dict[str, object]:
        summary = self.research_family_comparison_summary()
        payload = summary.get("current_proposal")
        return payload if isinstance(payload, dict) else {}

    def next_family_status(self) -> dict[str, object]:
        overview = self.overview()
        payload = overview.get("next_family_status")
        return payload if isinstance(payload, dict) else {}

    def paper_trade_entry_gate(self) -> dict[str, object]:
        return materialize_promotion_path(catalog_output_dir=self._paths.catalog_output_dir)["paper_trade_entry_gate"]

    def research_program_portfolio(self) -> dict[str, object]:
        return materialize_promotion_path(catalog_output_dir=self._paths.catalog_output_dir)["research_program_portfolio"]

    def bootstrap_research_family(self, payload: dict[str, object]) -> dict[str, object]:
        proposal_id = _optional_text(payload.get("proposal_id"))
        if not proposal_id:
            raise ValueError("proposal_id is required")
        return bootstrap_research_family(
            proposal_id=proposal_id,
            catalog_output_dir=self._paths.catalog_output_dir,
            enable_queue=bool(payload.get("enable_queue", True)),
        )

    def record_paper_rehearsal_action(self, payload: dict[str, object]) -> dict[str, object]:
        return record_paper_trade_action(
            self._paths.catalog_output_dir,
            action=str(payload.get("action", "")),
            day_id=_optional_text(payload.get("day_id")),
            actor=_optional_text(payload.get("actor")) or "api_operator",
            reason=_optional_text(payload.get("reason")),
            override_note=_optional_text(payload.get("override_note")),
        )

    def readiness(self) -> dict[str, object]:
        status = runtime_status(self._paths)
        active_directors = [
            dict(director)
            for director in status.get("directors", [])
            if isinstance(director, dict) and str(director.get("status", "")).lower() in {"queued", "running", "paused"}
        ] if isinstance(status.get("directors"), list) else []
        active_campaigns = [
            dict(campaign)
            for campaign in status.get("campaigns", [])
            if isinstance(campaign, dict) and str(campaign.get("status", "")).lower() in {"queued", "running"}
        ] if isinstance(status.get("campaigns"), list) else []
        service_heartbeats = [
            dict(record)
            for record in status.get("service_heartbeats", [])
            if isinstance(record, dict)
        ] if isinstance(status.get("service_heartbeats"), list) else []
        return {
            "ready": True,
            "health": _runtime_health(
                status=status,
                campaigns=active_campaigns,
                directors=active_directors,
                next_family_status=None,
            ),
            "counts": dict(status.get("counts", {})) if isinstance(status.get("counts"), dict) else {},
            "service_heartbeats": service_heartbeats,
        }


class ApiApp:
    def __init__(self, controller: ApiController, *, auth_token: str) -> None:
        self._controller = controller
        self._auth_token = auth_token.strip()
        if not self._auth_token:
            raise ValueError("TROTTERS_API_TOKEN is required to serve the API")
        self._audit_path = self._controller.paths.runtime_root / "exports" / "api_audit.jsonl"

    def __call__(self, environ: dict[str, object], start_response: Callable[[str, list[tuple[str, str]]], None]):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        query_string = str(environ.get("QUERY_STRING", ""))
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        body = _read_body(environ)
        request_id = _request_id(environ)
        actor = request_actor(environ)
        remote_addr = str(environ.get("REMOTE_ADDR", "") or "").strip() or None
        protected = _is_protected_path(path)
        mutation = _is_mutation_request(method)
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
                self._audit_path,
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
                self._audit_path,
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
            response = self.handle_request(method, path, query, body)
        except ValueError as exc:
            response = _json_error_response(_error_status_for(exc), str(exc))
        except Exception as exc:
            response = _json_error_response("500 Internal Server Error", f"Unhandled API error: {exc}")
        if protected and (mutation or response.status.startswith("5")):
            _write_audit_record(
                self._audit_path,
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
                    "outcome": "mutation" if mutation else "error",
                    "remote_addr": remote_addr,
                    "request_payload": audit_payload,
                },
            )
        response = _with_headers(response, [("X-Request-Id", request_id)])
        start_response(response.status, response.headers)
        return [response.body]

    def handle_request(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        body: bytes,
    ) -> ApiResponse:
        if method == "GET" and path == "/healthz":
            return ApiResponse("200 OK", [("Content-Type", "text/plain; charset=utf-8")], b"ok")
        if method == "GET" and path == "/readyz":
            return self._json_response(self._controller.readiness())
        if method == "GET" and path == "/api/v1/runtime/overview":
            return self._json_response(self._controller.overview())
        if method == "GET" and path == "/api/v1/notifications":
            return self._json_response(self._controller.list_notifications(query))
        if method == "GET" and path == "/api/v1/jobs":
            return self._json_response(self._controller.list_jobs(query))
        if method == "GET" and path == "/api/v1/artifacts":
            return self._json_response(self._controller.list_artifacts(query))
        if method == "GET" and path == "/api/v1/agent-summaries":
            return self._json_response(self._controller.list_agent_summaries(query))
        if method == "GET" and path == "/api/v1/agent-dispatches":
            return self._json_response(self._controller.list_agent_dispatches(query))
        if method == "GET" and path == "/api/v1/paper-trading/status":
            return self._json_response(self._controller.paper_rehearsal_status(query))
        if method == "GET" and path == "/api/v1/runtime/current-best-candidate":
            return self._json_response(self._controller.current_best_candidate_summary())
        if method == "GET" and path == "/api/v1/promotion-path/candidate-progression":
            return self._json_response(self._controller.candidate_progression_summary())
        if method == "GET" and path == "/api/v1/runtime/active-branch":
            return self._json_response(self._controller.active_branch_summary())
        if method == "GET" and path == "/api/v1/runtime/runbook-queue":
            return self._json_response(self._controller.runbook_queue_summary())
        if method == "GET" and path == "/api/v1/runtime/next-family-status":
            return self._json_response(self._controller.next_family_status())
        if method == "GET" and path == "/api/v1/promotion-path/paper-trade-entry-gate":
            return self._json_response(self._controller.paper_trade_entry_gate())
        if method == "GET" and path == "/api/v1/promotion-path/research-program-portfolio":
            return self._json_response(self._controller.research_program_portfolio())
        if method == "GET" and path == "/api/v1/research-programs/portfolio":
            return self._json_response(self._controller.research_program_portfolio())
        if method == "GET" and path == "/api/v1/research-families":
            return self._json_response(self._controller.research_family_comparison_summary())
        if method == "GET" and path == "/api/v1/research-families/current-proposal":
            return self._json_response(self._controller.current_research_family_proposal())
        if method == "POST" and path == "/api/v1/research-families/bootstrap":
            return self._json_response(self._controller.bootstrap_research_family(_json_body(body)), status="201 Created")
        if method == "POST" and path == "/api/v1/paper-trading/actions":
            return self._json_response(self._controller.record_paper_rehearsal_action(_json_body(body)), status="201 Created")
        if method == "GET" and path == "/api/v1/directors":
            return self._json_response(self._controller.list_directors())
        if method == "POST" and path == "/api/v1/directors":
            return self._json_response(self._controller.start_director(_json_body(body)), status="201 Created")
        if path.startswith("/api/v1/jobs/"):
            job_id, action = _resource_path(path, "/api/v1/jobs/")
            if action is None:
                if method != "GET":
                    raise ValueError("Only GET is supported for job detail routes")
                return self._json_response(self._controller.job_detail(job_id))
            if method != "GET":
                raise ValueError("Only GET is supported for job action routes")
            if action == "logs":
                return self._json_response(self._controller.job_logs(job_id, query))
            raise ValueError(f"Unknown job action '{action}'")
        if path.startswith("/api/v1/directors/"):
            director_id, action = _resource_path(path, "/api/v1/directors/")
            if action is None:
                if method != "GET":
                    raise ValueError("Only GET is supported for director detail routes")
                return self._json_response(self._controller.director_detail(director_id))
            payload = _json_body(body)
            if method != "POST":
                raise ValueError("Only POST is supported for director action routes")
            if action == "pause":
                return self._json_response(self._controller.pause_director(director_id, payload))
            if action == "resume":
                return self._json_response(self._controller.resume_director(director_id, payload))
            if action == "skip-next":
                return self._json_response(self._controller.skip_director_next(director_id, payload))
            if action == "stop":
                return self._json_response(self._controller.stop_director(director_id, payload))
            raise ValueError(f"Unknown director action '{action}'")
        if method == "GET" and path == "/api/v1/campaigns":
            return self._json_response(self._controller.list_campaigns())
        if method == "POST" and path == "/api/v1/campaigns":
            return self._json_response(self._controller.start_campaign(_json_body(body)), status="201 Created")
        if path.startswith("/api/v1/campaigns/"):
            campaign_id, action = _resource_path(path, "/api/v1/campaigns/")
            if action is None:
                if method != "GET":
                    raise ValueError("Only GET is supported for campaign detail routes")
                return self._json_response(self._controller.campaign_detail(campaign_id))
            payload = _json_body(body)
            if method != "POST":
                raise ValueError("Only POST is supported for campaign action routes")
            if action == "stop":
                return self._json_response(self._controller.stop_campaign(campaign_id, payload))
            raise ValueError(f"Unknown campaign action '{action}'")
        return _json_error_response("404 Not Found", f"Unknown route '{escape(path)}'")

    def _json_response(self, payload: dict[str, object], *, status: str = "200 OK") -> ApiResponse:
        return ApiResponse(
            status,
            [("Content-Type", "application/json; charset=utf-8")],
            json.dumps(payload, indent=2, default=str).encode("utf-8"),
        )


def serve_api(
    paths: ResearchRuntimePaths,
    *,
    host: str = "0.0.0.0",
    port: int = 8890,
) -> dict[str, object]:
    auth_token = os.environ.get("TROTTERS_API_TOKEN", "").strip()
    app = ApiApp(ApiController(paths), auth_token=auth_token)
    with make_server(host, port, app, server_class=_ThreadingWSGIServer, handler_class=WSGIRequestHandler) as server:
        print(f"Research API listening on http://{host}:{port}", flush=True)
        server.serve_forever()
    return {"host": host, "port": port}


def _load_notifications(
    paths: ResearchRuntimePaths,
    *,
    limit: int,
    event_type: str | None = None,
    campaign_id: str | None = None,
    severity: str | None = None,
) -> list[dict[str, object]]:
    notifications_path = paths.runtime_root / "exports" / "campaign_notifications.jsonl"
    if not notifications_path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in notifications_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            if event_type and str(payload.get("event_type", "")).strip() != event_type:
                continue
            if campaign_id and str(payload.get("campaign_id", "")).strip() != campaign_id:
                continue
            if severity and str(payload.get("severity", "")).strip() != severity:
                continue
            records.append(payload)
    return records[-limit:][::-1]


def _most_recent_terminal(status: dict[str, object]) -> dict[str, object]:
    return {
        "director": _latest_terminal_entry(status.get("directors"), statuses={"failed", "stopped", "exhausted"}),
        "campaign": _latest_terminal_entry(status.get("campaigns"), statuses={"failed", "stopped", "exhausted", "completed"}),
    }


def _compact_overview_status(status: dict[str, object], *, queued_preview_limit: int = 10) -> dict[str, object]:
    counts = dict(status.get("counts", {})) if isinstance(status.get("counts"), dict) else {}
    workers = [
        dict(worker)
        for worker in status.get("workers", [])
        if isinstance(worker, dict)
    ] if isinstance(status.get("workers"), list) else []
    jobs = [
        dict(job)
        for job in status.get("jobs", [])
        if isinstance(job, dict)
    ] if isinstance(status.get("jobs"), list) else []
    campaigns = [
        dict(campaign)
        for campaign in status.get("campaigns", [])
        if isinstance(campaign, dict)
    ] if isinstance(status.get("campaigns"), list) else []
    directors = [
        dict(director)
        for director in status.get("directors", [])
        if isinstance(director, dict)
    ] if isinstance(status.get("directors"), list) else []
    queued_jobs = [job for job in jobs if str(job.get("status", "")).lower() == "queued"]
    running_jobs = [job for job in jobs if str(job.get("status", "")).lower() == "running"]
    service_heartbeats = [
        dict(record)
        for record in status.get("service_heartbeats", [])
        if isinstance(record, dict)
    ] if isinstance(status.get("service_heartbeats"), list) else []
    compact = {
        "counts": counts,
        "workers": workers,
        "running_jobs": running_jobs,
        "queued_jobs_preview": queued_jobs[:queued_preview_limit],
        "queued_jobs_total": len(queued_jobs),
        "service_heartbeats": service_heartbeats,
        "recent_terminal_campaigns": _recent_terminal_entries(campaigns, statuses={"failed", "stopped", "exhausted", "completed"}, limit=5),
        "recent_terminal_directors": _recent_terminal_entries(directors, statuses={"failed", "stopped", "exhausted"}, limit=5),
    }
    if "database_path" in status:
        compact["database_path"] = status["database_path"]
    return compact


def _latest_terminal_entry(entries: object, *, statuses: set[str]) -> dict[str, object] | None:
    terminal = _recent_terminal_entries(entries, statuses=statuses, limit=1)
    return terminal[0] if terminal else None


def _recent_terminal_entries(entries: object, *, statuses: set[str], limit: int) -> list[dict[str, object]]:
    if not isinstance(entries, list):
        return []
    terminal: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized_status = str(entry.get("status", "")).lower()
        if normalized_status not in statuses:
            continue
        terminal.append(dict(entry))
    terminal.sort(
        key=lambda item: str(item.get("finished_at") or item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )
    return terminal[:limit]


def _detail_or_summary(fetch_detail: Callable[[], dict[str, object]], summary: dict[str, object]) -> dict[str, object]:
    try:
        detail = fetch_detail()
    except ValueError:
        return summary
    return detail if isinstance(detail, dict) and detail else summary


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


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key, [])
    if not values:
        return None
    text = str(values[0] or "").strip()
    return text or None


def _query_int(query: dict[str, list[str]], key: str, *, default: int) -> int:
    value = _query_value(query, key)
    if value is None:
        return default
    return int(value)


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
) -> ApiResponse:
    return ApiResponse(
        status,
        [("Content-Type", "application/json; charset=utf-8"), *(extra_headers or [])],
        json.dumps({"error": message}, indent=2).encode("utf-8"),
    )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_value(value: object, *, default: int) -> int:
    if value in {None, ""}:
        return default
    return int(value)


def _float_value(value: object, *, default: float) -> float:
    if value in {None, ""}:
        return default
    return float(value)


def _reason(payload: dict[str, object], *, default: str) -> str:
    return _optional_text(payload.get("reason")) or default


def _notify_events(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        events = [str(item).strip() for item in value if str(item).strip()]
        return tuple(events)
    if isinstance(value, str):
        events = [item.strip() for item in value.split(",") if item.strip()]
        return tuple(events)
    return ()


def _quality_gate(value: object) -> str:
    text = _optional_text(value)
    return text or "all"


def _required_config_path(value: object) -> str:
    return _resolve_repo_config_path(value, expected_root=PurePosixPath("configs"), suffix=".toml")


def _optional_config_path(value: object) -> str | None:
    if value in {None, ""}:
        return None
    return _required_config_path(value)


def _optional_plan_path(value: object) -> str | None:
    if value in {None, ""}:
        return None
    return _resolve_repo_config_path(value, expected_root=PurePosixPath("configs", "directors"), suffix=".json")


def _resolve_repo_config_path(value: object, *, expected_root: PurePosixPath, suffix: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        raise ValueError("config path is required")
    candidate = PurePosixPath(text)
    if candidate.is_absolute() or (candidate.parts and candidate.parts[0].endswith(":")):
        raise ValueError("config paths must be repo-relative")
    if candidate.suffix.lower() != suffix:
        raise ValueError(f"config path must end in {suffix}")
    if not candidate.parts or candidate.parts[: len(expected_root.parts)] != expected_root.parts:
        raise ValueError(f"config path must be under {expected_root.as_posix()}/")
    resolved = Path.cwd() / Path(*candidate.parts)
    if not resolved.exists():
        raise ValueError(f"Unknown config path '{candidate.as_posix()}'")
    return candidate.as_posix()


def _load_plan_payload(path_text: str) -> dict[str, object]:
    path = Path.cwd() / Path(*PurePosixPath(path_text).parts)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Director plan '{path_text}' must contain a JSON object")
    return payload


def _with_headers(response: ApiResponse, extra_headers: list[tuple[str, str]]) -> ApiResponse:
    return ApiResponse(response.status, [*response.headers, *extra_headers], response.body)


def _is_protected_path(path: str) -> bool:
    return path.startswith("/api/v1")


def _is_mutation_request(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _request_id(environ: dict[str, object]) -> str:
    provided = str(environ.get("HTTP_X_REQUEST_ID", "") or "").strip()
    return provided or uuid.uuid4().hex


def _audit_payload(body: bytes) -> object:
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text = body.decode("utf-8", errors="replace")
        return text[:4000]
    if isinstance(payload, (dict, list)):
        return payload
    return str(payload)[:4000]


def _write_audit_record(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str))
        handle.write("\n")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()
