from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
import json
import os
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode
from wsgiref.simple_server import make_server

from trotters_trader.agent_dispatches import load_dispatch_records, load_dispatch_summary
from trotters_trader.agent_summaries import load_latest_summaries
from trotters_trader.active_branch import build_active_branch_summary
from trotters_trader.http_security import is_basic_authorized, new_csrf_token, parse_cookies
from trotters_trader.paper_rehearsal import paper_rehearsal_status
from trotters_trader.promotion_path import materialize_promotion_path, resolve_current_best_candidate
from trotters_trader.research_families import build_next_family_status, build_research_family_comparison_summary
from trotters_trader.runbook_queue import build_runbook_queue_summary
from trotters_trader.research_runtime import (
    ResearchRuntimePaths,
    campaign_status,
    director_status,
    pause_director,
    resume_director,
    runtime_status,
    skip_director_next,
    stop_campaign,
)
from trotters_trader.reports import build_operability_scorecard, operability_artifact_paths


@dataclass(frozen=True)
class DashboardResponse:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


class DashboardController:
    def __init__(self, paths: ResearchRuntimePaths) -> None:
        self._paths = paths

    def overview(self) -> dict[str, object]:
        status = runtime_status(self._paths)
        active_director_ids = [
            str(director.get("director_id", ""))
            for director in status.get("directors", [])
            if str(director.get("status", "")) in {"queued", "running"}
        ]
        active_directors = [
            director_status(self._paths, director_id).get("director", {})
            for director_id in active_director_ids
            if director_id
        ]
        active_campaign_ids = [
            str(campaign.get("campaign_id", ""))
            for campaign in status.get("campaigns", [])
            if str(campaign.get("status", "")) in {"queued", "running"}
        ]
        active_campaigns = [
            campaign_status(self._paths, campaign_id).get("campaign", {})
            for campaign_id in active_campaign_ids
            if campaign_id
        ]
        agent_summaries = load_latest_summaries(self._paths.catalog_output_dir)
        current_best_candidate = resolve_current_best_candidate(
            catalog_output_dir=self._paths.catalog_output_dir,
            active_campaigns=active_campaigns,
            most_recent_terminal={"campaign": _recent_outcomes(status.get("campaigns"), limit=1)[0]} if _recent_outcomes(status.get("campaigns"), limit=1) else {},
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
            "status": status,
            "catalog_status": _catalog_status(self._paths),
            "active_directors": active_directors,
            "active_campaigns": active_campaigns,
            "active_branch_summary": active_branch_summary,
            "runbook_queue_summary": runbook_queue_summary,
            "research_family_comparison_summary": research_family_comparison_summary,
            "next_family_status": next_family_status,
            "notifications": _load_notifications(self._paths, limit=25),
            "paper_rehearsal": paper_rehearsal_status(self._paths.catalog_output_dir, limit=5),
            "current_best_candidate": current_best_candidate,
            "candidate_progression_summary": promotion_path["candidate_progression_summary"],
            "paper_trade_entry_gate": promotion_path["paper_trade_entry_gate"],
            "research_program_portfolio": promotion_path["research_program_portfolio"],
            "agent_summaries": agent_summaries,
            "agent_dispatches": load_dispatch_records(self._paths.catalog_output_dir, limit=10),
            "agent_dispatch_summary": load_dispatch_summary(self._paths.catalog_output_dir, limit=100),
        }

    def campaign_detail(self, campaign_id: str) -> dict[str, object]:
        return campaign_status(self._paths, campaign_id)

    def director_detail(self, director_id: str) -> dict[str, object]:
        return director_status(self._paths, director_id)

    def pause_director(self, director_id: str, reason: str) -> dict[str, object]:
        return pause_director(self._paths, director_id, reason=reason)

    def resume_director(self, director_id: str, reason: str) -> dict[str, object]:
        return resume_director(self._paths, director_id, reason=reason)

    def skip_director_next(self, director_id: str, reason: str) -> dict[str, object]:
        return skip_director_next(self._paths, director_id, reason=reason)

    def stop_campaign(self, campaign_id: str, reason: str) -> dict[str, object]:
        return stop_campaign(self._paths, campaign_id, reason=reason)


class DashboardApp:
    def __init__(
        self,
        controller: DashboardController,
        *,
        refresh_seconds: int = 10,
        auth_username: str = "operator",
        auth_password: str = "change-me-local-only",
    ) -> None:
        self._controller = controller
        self._refresh_seconds = refresh_seconds
        self._auth_username = auth_username.strip()
        self._auth_password = auth_password.strip()
        if not self._auth_username or not self._auth_password:
            raise ValueError("Dashboard auth credentials are required")

    def __call__(self, environ: dict[str, object], start_response: Callable[[str, list[tuple[str, str]]], None]):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        body = _read_body(environ)
        cookies = parse_cookies(environ)
        csrf_cookie = cookies.get("trotters_csrf")

        if not (method == "GET" and path == "/healthz"):
            if not is_basic_authorized(environ, self._auth_username, self._auth_password):
                response = DashboardResponse(
                    "401 Unauthorized",
                    [
                        ("Content-Type", "text/plain; charset=utf-8"),
                        ("WWW-Authenticate", 'Basic realm="Trotters Dashboard"'),
                    ],
                    b"Unauthorized",
                )
                start_response(response.status, response.headers)
                return [response.body]
            if method == "POST":
                form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
                submitted = _query_value(form, "csrf_token")
                if not csrf_cookie or not submitted or submitted != csrf_cookie:
                    response = self._html_response(
                        "403 Forbidden",
                        _render_layout(
                            "Dashboard Error",
                            "<section class='panel'><h1>Forbidden</h1><p>Missing or invalid CSRF token.</p></section>",
                            refresh_seconds=0,
                        ),
                    )
                    start_response(response.status, response.headers)
                    return [response.body]
            if method == "GET" and not csrf_cookie:
                csrf_cookie = new_csrf_token()

        try:
            response = self.handle_request(method, path, query, body, csrf_token=csrf_cookie)
        except ValueError as exc:
            response = self._html_response(
                "400 Bad Request",
                _render_layout(
                    "Dashboard Error",
                    f"<section class='panel'><h1>Bad Request</h1><p>{escape(str(exc))}</p></section>",
                    refresh_seconds=0,
                ),
            )
        if method == "GET" and path != "/healthz" and csrf_cookie:
            response = _with_headers(
                response,
                [("Set-Cookie", _csrf_cookie_header(csrf_cookie))],
            )
        start_response(response.status, response.headers)
        return [response.body]

    def handle_request(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        body: bytes,
        *,
        csrf_token: str | None,
    ) -> DashboardResponse:
        if method == "GET" and path == "/healthz":
            return DashboardResponse("200 OK", [("Content-Type", "text/plain; charset=utf-8")], b"ok")
        if method == "GET" and path == "/guide":
            return self._html_response("200 OK", _render_guide(refresh_seconds=0))
        if method == "GET" and path == "/":
            payload = self._controller.overview()
            html = _render_overview(
                payload,
                refresh_seconds=self._refresh_seconds,
                flash=_query_value(query, "flash"),
                csrf_token=csrf_token,
            )
            return self._html_response("200 OK", html)
        if method == "GET" and path.startswith("/directors/"):
            director_id = path.removeprefix("/directors/").strip("/")
            if not director_id:
                raise ValueError("Director id is required")
            payload = self._controller.director_detail(director_id)
            html = _render_director_detail(
                payload,
                refresh_seconds=self._refresh_seconds,
                flash=_query_value(query, "flash"),
                csrf_token=csrf_token,
            )
            return self._html_response("200 OK", html)
        if method == "POST" and path.startswith("/directors/") and path.endswith("/pause"):
            director_id = path.removeprefix("/directors/").removesuffix("/pause").strip("/")
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            reason = _query_value(form, "reason") or "operator_pause"
            self._controller.pause_director(director_id, reason)
            location = f"/directors/{quote(director_id)}?{urlencode({'flash': 'Director paused'})}"
            return DashboardResponse("303 See Other", [("Location", location)], b"")
        if method == "POST" and path.startswith("/directors/") and path.endswith("/resume"):
            director_id = path.removeprefix("/directors/").removesuffix("/resume").strip("/")
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            reason = _query_value(form, "reason") or "operator_resume"
            self._controller.resume_director(director_id, reason)
            location = f"/directors/{quote(director_id)}?{urlencode({'flash': 'Director resumed'})}"
            return DashboardResponse("303 See Other", [("Location", location)], b"")
        if method == "POST" and path.startswith("/directors/") and path.endswith("/skip-next"):
            director_id = path.removeprefix("/directors/").removesuffix("/skip-next").strip("/")
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            reason = _query_value(form, "reason") or "operator_skip"
            self._controller.skip_director_next(director_id, reason)
            location = f"/directors/{quote(director_id)}?{urlencode({'flash': 'Director skipped next pending campaign'})}"
            return DashboardResponse("303 See Other", [("Location", location)], b"")
        if method == "GET" and path.startswith("/campaigns/"):
            if path.endswith("/handoff"):
                campaign_id = path.removeprefix("/campaigns/").removesuffix("/handoff").strip("/")
                if not campaign_id:
                    raise ValueError("Campaign id is required")
                payload = self._controller.campaign_detail(campaign_id)
                html = _render_campaign_handoff(
                    payload,
                    refresh_seconds=self._refresh_seconds,
                    flash=_query_value(query, "flash"),
                )
                return self._html_response("200 OK", html)
            if path.endswith("/comparison"):
                campaign_id = path.removeprefix("/campaigns/").removesuffix("/comparison").strip("/")
                if not campaign_id:
                    raise ValueError("Campaign id is required")
                payload = self._controller.campaign_detail(campaign_id)
                html = _render_campaign_comparison(
                    payload,
                    refresh_seconds=self._refresh_seconds,
                    flash=_query_value(query, "flash"),
                )
                return self._html_response("200 OK", html)
            if path.endswith("/scorecard"):
                campaign_id = path.removeprefix("/campaigns/").removesuffix("/scorecard").strip("/")
                if not campaign_id:
                    raise ValueError("Campaign id is required")
                payload = self._controller.campaign_detail(campaign_id)
                html = _render_campaign_scorecard(
                    payload,
                    refresh_seconds=self._refresh_seconds,
                    flash=_query_value(query, "flash"),
                )
                return self._html_response("200 OK", html)
            campaign_id = path.removeprefix("/campaigns/").strip("/")
            if not campaign_id:
                raise ValueError("Campaign id is required")
            payload = self._controller.campaign_detail(campaign_id)
            html = _render_campaign_detail(
                payload,
                refresh_seconds=self._refresh_seconds,
                flash=_query_value(query, "flash"),
                csrf_token=csrf_token,
            )
            return self._html_response("200 OK", html)
        if method == "POST" and path.startswith("/campaigns/") and path.endswith("/stop"):
            campaign_id = path.removeprefix("/campaigns/").removesuffix("/stop").strip("/")
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            reason = _query_value(form, "reason") or "dashboard_stop"
            self._controller.stop_campaign(campaign_id, reason)
            location = f"/campaigns/{quote(campaign_id)}?{urlencode({'flash': 'Campaign stop requested'})}"
            return DashboardResponse("303 See Other", [("Location", location)], b"")
        if method == "GET" and path == "/api/overview.json":
            payload = self._controller.overview()
            return self._json_response(payload)
        if method == "GET" and path.startswith("/api/campaigns/"):
            campaign_id = path.removeprefix("/api/campaigns/").strip("/")
            if not campaign_id:
                raise ValueError("Campaign id is required")
            return self._json_response(self._controller.campaign_detail(campaign_id))
        if method == "GET" and path.startswith("/api/directors/"):
            director_id = path.removeprefix("/api/directors/").strip("/")
            if not director_id:
                raise ValueError("Director id is required")
            return self._json_response(self._controller.director_detail(director_id))
        return self._html_response(
            "404 Not Found",
            _render_layout(
                "Not Found",
                "<section class='panel'><h1>Not Found</h1><p>The requested page does not exist.</p></section>",
                refresh_seconds=0,
            ),
        )

    def _html_response(self, status: str, html: str) -> DashboardResponse:
        return DashboardResponse(
            status,
            [("Content-Type", "text/html; charset=utf-8")],
            html.encode("utf-8"),
        )

    def _json_response(self, payload: dict[str, object]) -> DashboardResponse:
        return DashboardResponse(
            "200 OK",
            [("Content-Type", "application/json; charset=utf-8")],
            json.dumps(payload, indent=2, default=str).encode("utf-8"),
        )


def _with_headers(response: DashboardResponse, extra_headers: list[tuple[str, str]]) -> DashboardResponse:
    return DashboardResponse(response.status, [*response.headers, *extra_headers], response.body)


def serve_dashboard(
    paths: ResearchRuntimePaths,
    *,
    host: str = "0.0.0.0",
    port: int = 8888,
    refresh_seconds: int = 10,
) -> dict[str, object]:
    app = DashboardApp(
        DashboardController(paths),
        refresh_seconds=refresh_seconds,
        auth_username=os.environ.get("TROTTERS_DASHBOARD_USERNAME", "operator"),
        auth_password=os.environ.get("TROTTERS_DASHBOARD_PASSWORD", "change-me-local-only"),
    )
    with make_server(host, port, app) as server:
        print(f"Dashboard listening on http://{host}:{port}", flush=True)
        server.serve_forever()
    return {"host": host, "port": port}


def _load_notifications(paths: ResearchRuntimePaths, *, limit: int) -> list[dict[str, object]]:
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
            records.append(payload)
    return records[-limit:][::-1]


def _catalog_status(paths: ResearchRuntimePaths) -> dict[str, object]:
    catalog_jsonl = paths.catalog_output_dir / "research_catalog" / "catalog.jsonl"
    return {
        "available": catalog_jsonl.exists(),
        "catalog_jsonl": str(catalog_jsonl),
    }


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


def _render_overview(
    payload: dict[str, object],
    *,
    refresh_seconds: int,
    flash: str | None,
    csrf_token: str | None,
) -> str:
    status = payload.get("status", {}) if isinstance(payload.get("status"), dict) else {}
    counts = status.get("counts", {}) if isinstance(status.get("counts"), dict) else {}
    workers = status.get("workers", []) if isinstance(status.get("workers"), list) else []
    jobs = status.get("jobs", []) if isinstance(status.get("jobs"), list) else []
    all_directors = status.get("directors", []) if isinstance(status.get("directors"), list) else []
    all_campaigns = status.get("campaigns", []) if isinstance(status.get("campaigns"), list) else []
    directors = payload.get("active_directors", []) if isinstance(payload.get("active_directors"), list) else []
    campaigns = payload.get("active_campaigns", []) if isinstance(payload.get("active_campaigns"), list) else []
    notifications = payload.get("notifications", []) if isinstance(payload.get("notifications"), list) else []
    catalog_status = payload.get("catalog_status", {}) if isinstance(payload.get("catalog_status"), dict) else {}
    current_best_candidate = (
        payload.get("current_best_candidate", {})
        if isinstance(payload.get("current_best_candidate"), dict)
        else {}
    )
    active_branch_summary = (
        payload.get("active_branch_summary", {})
        if isinstance(payload.get("active_branch_summary"), dict)
        else {}
    )
    candidate_progression_summary = (
        payload.get("candidate_progression_summary", {})
        if isinstance(payload.get("candidate_progression_summary"), dict)
        else {}
    )
    paper_trade_entry_gate = (
        payload.get("paper_trade_entry_gate", {})
        if isinstance(payload.get("paper_trade_entry_gate"), dict)
        else {}
    )
    research_family_comparison_summary = (
        payload.get("research_family_comparison_summary", {})
        if isinstance(payload.get("research_family_comparison_summary"), dict)
        else {}
    )
    next_family_status = (
        payload.get("next_family_status", {})
        if isinstance(payload.get("next_family_status"), dict)
        else {}
    )
    research_program_portfolio = (
        payload.get("research_program_portfolio", {})
        if isinstance(payload.get("research_program_portfolio"), dict)
        else {}
    )
    runbook_queue_summary = (
        payload.get("runbook_queue_summary", {})
        if isinstance(payload.get("runbook_queue_summary"), dict)
        else {}
    )
    paper_rehearsal = payload.get("paper_rehearsal", {}) if isinstance(payload.get("paper_rehearsal"), dict) else {}
    agent_summaries = payload.get("agent_summaries", {}) if isinstance(payload.get("agent_summaries"), dict) else {}
    agent_dispatches = payload.get("agent_dispatches", []) if isinstance(payload.get("agent_dispatches"), list) else []
    agent_dispatch_summary = payload.get("agent_dispatch_summary", {}) if isinstance(payload.get("agent_dispatch_summary"), dict) else {}
    service_heartbeats = status.get("service_heartbeats", []) if isinstance(status.get("service_heartbeats"), list) else []
    health = _runtime_health(status=status, campaigns=campaigns, directors=directors, next_family_status=next_family_status)

    summary_cards = "".join(
        _summary_card(label, str(counts.get(label, 0)))
        for label in ("queued", "running", "completed", "failed", "cancelled")
    )
    outcome_cards = "".join(
        _summary_card(label, str(value))
        for label, value in [
            ("campaign completed", _status_count(all_campaigns, "completed")),
            ("campaign exhausted", _status_count(all_campaigns, "exhausted")),
            ("campaign failed", _status_count(all_campaigns, "failed")),
            ("campaign stopped", _status_count(all_campaigns, "stopped")),
            ("director completed", _status_count(all_directors, "completed")),
            ("director exhausted", _status_count(all_directors, "exhausted")),
            ("director failed", _status_count(all_directors, "failed")),
            ("director stopped", _status_count(all_directors, "stopped")),
        ]
    )
    director_rows = "".join(_director_row(director) for director in directors) or (
        "<tr><td colspan='7'>No active directors</td></tr>"
    )
    campaign_rows = "".join(_campaign_row(campaign) for campaign in campaigns) or (
        "<tr><td colspan='6'>No active campaigns</td></tr>"
    )
    worker_rows = "".join(_worker_row(worker) for worker in workers) or (
        "<tr><td colspan='4'>No workers recorded</td></tr>"
    )
    job_rows = "".join(_job_row(job) for job in jobs[:20]) or "<tr><td colspan='7'>No jobs recorded</td></tr>"
    notification_rows = "".join(_notification_row(record) for record in notifications) or (
        "<tr><td colspan='6'>No notifications yet</td></tr>"
    )
    recent_campaign_rows = "".join(_campaign_outcome_row(campaign) for campaign in _recent_outcomes(all_campaigns)) or (
        "<tr><td colspan='6'>No recent campaign outcomes</td></tr>"
    )
    recent_director_rows = "".join(_director_outcome_row(director) for director in _recent_outcomes(all_directors)) or (
        "<tr><td colspan='6'>No recent director outcomes</td></tr>"
    )
    recent_change_rows = "".join(
        _recent_change_row(change)
        for change in _recent_changes(all_campaigns, all_directors, notifications)
    ) or "<tr><td colspan='3'>No recent changes recorded</td></tr>"
    agent_summary_rows = "".join(_agent_summary_row(summary) for summary in agent_summaries.values() if isinstance(summary, dict)) or "<tr><td colspan='6'>No agent summaries yet</td></tr>"
    decision_snapshot_cards = "".join(
        _decision_snapshot_card(label, agent_summaries.get(summary_type))
        for label, summary_type in [
            ("Supervisor Incident", "supervisor_incident_summary"),
            ("Campaign Triage", "campaign_triage_summary"),
            ("Candidate Readiness", "candidate_readiness_summary"),
            ("Paper-Trade Readiness", "paper_trade_readiness_summary"),
            ("Failure Postmortem", "failure_postmortem_summary"),
        ]
    )
    dispatch_rows = "".join(_agent_dispatch_row(record) for record in agent_dispatches if isinstance(record, dict)) or "<tr><td colspan='7'>No agent dispatches recorded yet</td></tr>"
    dispatch_totals = agent_dispatch_summary.get("totals", {}) if isinstance(agent_dispatch_summary.get("totals"), dict) else {}
    dispatch_summary_cards = "".join(
        _summary_card(label, str(value))
        for label, value in [
            ("agent runs", dispatch_totals.get("runs", 0)),
            ("dispatch successes", dispatch_totals.get("successes", 0)),
            ("dispatch failures", dispatch_totals.get("failures", 0)),
            ("dispatch tokens", dispatch_totals.get("total_tokens", 0)),
        ]
    )

    body = f"""
    {_flash_banner(flash)}
    <section class="hero">
      <div>
        <h1>Research Runtime Dashboard</h1>
        <p>Queue, workers, campaigns, and notifications for the autonomous research stack.</p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/guide">Guide</a>
        <a class="button secondary" href="/api/overview.json">JSON</a>
      </div>
    </section>
    {_notification_banner(notifications, campaigns=campaigns, directors=directors)}
    {_catalog_status_banner(catalog_status)}
    {_health_panel(health)}
    {_service_heartbeat_section(service_heartbeats)}
    {_active_runtime_now_section(directors, campaigns, counts, next_family_status=next_family_status)}
    {_active_branch_summary_section(active_branch_summary)}
    {_current_best_candidate_section(current_best_candidate)}
    {_candidate_progression_section(candidate_progression_summary)}
    {_paper_trade_entry_gate_section(paper_trade_entry_gate)}
    {_next_family_status_section(next_family_status)}
    {_research_family_comparison_section(research_family_comparison_summary)}
    {_paper_rehearsal_section(paper_rehearsal)}
    {_research_program_portfolio_section(research_program_portfolio)}
    {_runbook_queue_summary_section(runbook_queue_summary)}
    <section class="summary-grid">{summary_cards}</section>
    <section class="panel">
      <h2>Decision Snapshots</h2>
      <p class="subtle">Latest operator-facing conclusion from each summary type.</p>
      <section class="summary-grid">{decision_snapshot_cards}</section>
    </section>
    <section class="panel">
      <h2>Agent Summaries</h2>
      <p class="subtle">Latest low-cost outputs from the supervisor and specialist review agents.</p>
      <table>
        <thead><tr><th>Agent</th><th>Summary</th><th>Classification</th><th>Status</th><th>Action</th><th>Recorded</th></tr></thead>
        <tbody>{agent_summary_rows}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Agent Dispatches</h2>
      <p class="subtle">Recent specialist-agent runs and their cost envelope.</p>
      <section class="summary-grid">{dispatch_summary_cards}</section>
      <table>
        <thead><tr><th>Agent</th><th>Event</th><th>Outcome</th><th>Model</th><th>Tokens</th><th>Duration</th><th>Recorded</th></tr></thead>
        <tbody>{dispatch_rows}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Outcome Summary</h2>
      <p class="subtle">Recent terminal outcomes across campaigns and directors.</p>
      <section class="summary-grid">{outcome_cards}</section>
    </section>
    <section class="panel">
      <h2>Active Directors</h2>
      <table>
        <thead><tr><th>Name</th><th>Status</th><th>Plan</th><th>Progress</th><th>Current Campaign</th><th>Successful Campaign</th><th>Last Result</th></tr></thead>
        <tbody>{director_rows}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Active Campaigns</h2>
      <table>
        <thead><tr><th>Name</th><th>Status</th><th>Phase</th><th>Updated</th><th>Report</th><th>Action</th></tr></thead>
        <tbody>{campaign_rows}</tbody>
      </table>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Workers</h2>
        <table>
          <thead><tr><th>Worker</th><th>Status</th><th>Current Job</th><th>Heartbeat</th></tr></thead>
          <tbody>{worker_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Recent Notifications</h2>
        <table>
          <thead><tr><th>Time</th><th>Severity</th><th>Event</th><th>Campaign</th><th>Message</th><th>Hook</th></tr></thead>
          <tbody>{notification_rows}</tbody>
        </table>
      </section>
    </section>
    <section class="panel">
      <h2>What Changed Since Last Check</h2>
      <p class="subtle">This feed highlights the most recent notifications and terminal state changes.</p>
      <table>
        <thead><tr><th>Time</th><th>Source</th><th>Change</th></tr></thead>
        <tbody>{recent_change_rows}</tbody>
      </table>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Recent Terminal Campaign Outcomes</h2>
        <table>
          <thead><tr><th>Campaign</th><th>Status</th><th>Phase</th><th>Updated</th><th>Report</th><th>Action</th></tr></thead>
          <tbody>{recent_campaign_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Recent Terminal Director Outcomes</h2>
        <table>
          <thead><tr><th>Director</th><th>Status</th><th>Plan</th><th>Updated</th><th>Successful Campaign</th><th>Action</th></tr></thead>
          <tbody>{recent_director_rows}</tbody>
        </table>
      </section>
    </section>
    <section class="panel">
      <h2>Recent Jobs</h2>
      <table>
        <thead><tr><th>Job</th><th>Campaign</th><th>Command</th><th>Status</th><th>Worker</th><th>Created</th><th>Updated</th></tr></thead>
        <tbody>{job_rows}</tbody>
      </table>
    </section>
    """
    return _render_layout("Research Runtime Dashboard", body, refresh_seconds=refresh_seconds)


def _active_branch_summary_section(summary: dict[str, object]) -> str:
    if not summary:
        return ""
    director = summary.get("director") if isinstance(summary.get("director"), dict) else {}
    campaign = summary.get("campaign") if isinstance(summary.get("campaign"), dict) else {}
    stage = summary.get("stage") if isinstance(summary.get("stage"), dict) else {}
    job_counts = summary.get("job_counts") if isinstance(summary.get("job_counts"), dict) else {}
    warnings = summary.get("warnings") if isinstance(summary.get("warnings"), list) else []
    warning_items = "".join(
        f"<li>{escape(str(item.get('message', 'unknown warning')))}</li>"
        for item in warnings
        if isinstance(item, dict)
    ) or "<li>No active-branch warnings recorded.</li>"
    return f"""
    <section class="panel">
      <h2>Active Research Branch</h2>
      <p class="subtle">Single-screen answer for which branch is currently executing and what should happen next while no promoted candidate exists yet.</p>
      <section class="summary-grid">
        {_summary_card("director", str(director.get("director_name", "none") or "none"))}
        {_summary_card("plan", str(director.get("plan_name", "unknown") or "unknown"))}
        {_summary_card("campaign", str(campaign.get("campaign_name", "none") or "none"))}
        {_summary_card("phase", str(campaign.get("phase", "unknown") or "unknown"))}
        {_summary_card("next action", str(summary.get("recommended_action", "wait_for_next_branch")))}
      </section>
      <p>{escape(str(summary.get("message", "No active branch summary available.")))}</p>
      <section class="summary-grid">
        {_summary_card("stage queued", str(job_counts.get("queued", 0)))}
        {_summary_card("stage running", str(job_counts.get("running", 0)))}
        {_summary_card("stage completed", str(job_counts.get("completed", 0)))}
        {_summary_card("stage failed", str(job_counts.get("failed", 0)))}
      </section>
      <p><strong>Latest report:</strong> {escape(str(stage.get("latest_report_path", "-") or "-"))}</p>
      <p><strong>Last stage event:</strong> {escape(str(stage.get("last_event", "none") or "none"))}</p>
      {f"<ul>{warning_items}</ul>" if warnings else ""}
    </section>
    """


def _current_best_candidate_section(summary: dict[str, object]) -> str:
    if not summary:
        return """
        <section class="panel">
          <h2>Current Best Candidate</h2>
          <p>No operator-ready candidate summary is available yet.</p>
        </section>
        """

    best_candidate = summary.get("best_candidate") if isinstance(summary.get("best_candidate"), dict) else None
    supporting = summary.get("supporting_summaries") if isinstance(summary.get("supporting_summaries"), dict) else {}
    progression = summary.get("progression") if isinstance(summary.get("progression"), dict) else {}
    why_best = _scorecard_list(summary.get("why_this_candidate"), empty_message="No strengths recorded yet.")
    what_failed = _scorecard_list(summary.get("what_failed_or_is_missing"), empty_message="No missing-evidence summary recorded yet.")
    next_steps = _scorecard_list(summary.get("next_steps"), empty_message="No next steps recorded yet.")
    candidate_snapshot = _candidate_snapshot(
        best_candidate or {},
        None,
        empty_message="No shortlisted candidate has been selected yet.",
    )
    supporting_rows = "".join(
        _operator_supporting_summary_row(label, details)
        for label, details in [
            ("Candidate readiness", supporting.get("candidate_readiness")),
            ("Paper-trade readiness", supporting.get("paper_trade_readiness")),
        ]
    ) or "<tr><td colspan='5'>No supporting specialist summaries recorded yet.</td></tr>"
    artifact_paths = summary.get("artifact_paths") if isinstance(summary.get("artifact_paths"), dict) else {}

    return f"""
    <section class="panel">
      <h2>Current Best Candidate</h2>
      <p class="subtle">Single-screen operator view of the current lead branch, why it leads, what is still weak, and what should happen next.</p>
      <section class="summary-grid">
        {_summary_card("status", str(summary.get("status", "unavailable")))}
        {_summary_card("source", str(summary.get("source", "active_campaign")))}
        {_summary_card("recommendation", str(summary.get("operator_recommendation", "needs_more_research")))}
        {_summary_card("candidate available", "yes" if bool(summary.get("candidate_available", False)) else "no")}
        {_summary_card("campaign status", str(summary.get("campaign_status", "unknown")))}
        {_summary_card("phase", str(summary.get("campaign_phase", "unknown")))}
        {_summary_card("shortlist", str(progression.get("shortlist_count", 0)))}
        {_summary_card("pivot used", "yes" if bool(progression.get("pivot_used", False)) else "no")}
      </section>
      <p><strong>{escape(str(summary.get("campaign_name", "unknown campaign")))}</strong> ({escape(str(summary.get("campaign_id", "")))})</p>
      <p>{escape(str(summary.get("display_message", "") or summary.get("headline", "") or "No candidate summary is available yet."))}</p>
      <p><strong>Immediate next action:</strong> {escape(str(summary.get("next_action", "")) or "No next action recorded yet.")}</p>
      {_scorecard_artifact_paths(artifact_paths)}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Why This Is The Current Lead</h2>
        {why_best}
      </section>
      <section class="panel">
        <h2>What Failed Or Is Missing</h2>
        {what_failed}
      </section>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Best Candidate Snapshot</h2>
        {candidate_snapshot}
      </section>
      <section class="panel">
        <h2>What Happens Next</h2>
        {next_steps}
      </section>
    </section>
    <section class="panel">
      <h2>Supporting Specialist Views</h2>
      <table>
        <thead><tr><th>Summary</th><th>Classification</th><th>Status</th><th>Action</th><th>Recorded</th></tr></thead>
        <tbody>{supporting_rows}</tbody>
      </table>
    </section>
    """


def _active_runtime_now_section(
    directors: list[dict[str, object]],
    campaigns: list[dict[str, object]],
    counts: dict[str, object],
    *,
    next_family_status: dict[str, object] | None = None,
) -> str:
    active_director_names = ", ".join(
        str(director.get("director_name") or director.get("director_id") or "unknown director")
        for director in directors
        if isinstance(director, dict)
    ) or "None"
    active_campaign_names = ", ".join(
        str(campaign.get("campaign_name") or campaign.get("campaign_id") or "unknown campaign")
        for campaign in campaigns
        if isinstance(campaign, dict)
    ) or "None"
    next_family = next_family_status if isinstance(next_family_status, dict) else {}
    next_family_state = str(next_family.get("status", "")).lower()
    blocked_by_governance = next_family_state in {"blocked_pending_approval", "blocked_pending_bootstrap"}
    blocked_message = str(next_family.get("message", "")).strip()
    if directors or campaigns:
        summary = "The runtime is currently executing live research work."
    elif blocked_by_governance:
        summary = (
            f"The runtime is currently blocked by queue governance. {blocked_message}"
            if blocked_message
            else "The runtime is currently blocked by queue governance until the next approved family is defined."
        )
    else:
        summary = "The runtime is currently idle. Recent terminal outcomes are historical, not live work."
    return f"""
    <section class="panel">
      <h2>Active Runtime Now</h2>
      <p class="subtle">This section is the live state. It is separate from the terminal-outcomes panels further down the page.</p>
      <section class="summary-grid">
        {_summary_card("active directors", str(len(directors)))}
        {_summary_card("active campaigns", str(len(campaigns)))}
        {_summary_card("queued jobs", str(counts.get("queued", 0)))}
        {_summary_card("running jobs", str(counts.get("running", 0)))}
      </section>
      <p>{escape(summary)}</p>
      <p><strong>Directors:</strong> {escape(active_director_names)}</p>
      <p><strong>Campaigns:</strong> {escape(active_campaign_names)}</p>
    </section>
    """


def _candidate_progression_section(summary: dict[str, object]) -> str:
    records = [record for record in summary.get("records", []) if isinstance(record, dict)] if isinstance(summary.get("records"), list) else []
    rows = "".join(_candidate_progression_row(record) for record in records[:8]) or "<tr><td colspan='8'>No candidate progression records yet.</td></tr>"
    counts = summary.get("counts", {}) if isinstance(summary.get("counts"), dict) else {}
    return f"""
    <section class="panel">
      <h2>Candidate Progression</h2>
      <p class="subtle">Normalized promotion-path view across active candidates, profile history, and research-program evidence.</p>
      <section class="summary-grid">
        {_summary_card("records", str(counts.get("total", 0)))}
        {_summary_card("paper-trade next", str(counts.get("paper_trade_next", 0)))}
        {_summary_card("needs follow-up", str(counts.get("needs_followup", 0)))}
        {_summary_card("blocked", str(counts.get("promotion_blocked", 0)))}
      </section>
      <table>
        <thead><tr><th>Profile</th><th>Source</th><th>Recommendation</th><th>Validation</th><th>Holdout</th><th>WF</th><th>Next Action</th><th>Recorded</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _paper_trade_entry_gate_section(summary: dict[str, object]) -> str:
    target = summary.get("target", {}) if isinstance(summary.get("target"), dict) else {}
    reasons = summary.get("block_reasons", []) if isinstance(summary.get("block_reasons"), list) else []
    reason_items = "".join(
        f"<li>{escape(str(reason.get('message', 'unknown reason')))}</li>"
        for reason in reasons
        if isinstance(reason, dict)
    ) or "<li>No blocking reasons recorded.</li>"
    return f"""
    <section class="panel">
      <h2>Paper-Trade Entry Gate</h2>
      <p class="subtle">Explicit decision boundary for whether the current lead candidate may enter paper-trade rehearsal.</p>
      <section class="summary-grid">
        {_summary_card("gate status", str(summary.get("status", "not_applicable")))}
        {_summary_card("recommended action", str(summary.get("recommended_action", "wait_for_candidate")))}
        {_summary_card("target profile", str(target.get("profile_name", "none") or "none"))}
        {_summary_card("latest paper day", str((summary.get("paper_rehearsal_state", {}) if isinstance(summary.get("paper_rehearsal_state"), dict) else {}).get("latest_day_status", "none") or "none"))}
      </section>
      <p>{escape(str(summary.get("message", "No paper-trade gate decision is available.")))}</p>
      <ul>{reason_items}</ul>
    </section>
    """


def _next_family_status_section(summary: dict[str, object]) -> str:
    if not summary:
        return ""
    current_proposal = summary.get("current_proposal", {}) if isinstance(summary.get("current_proposal"), dict) else {}
    return f"""
    <section class="panel">
      <h2>Next Family Status</h2>
      <p class="subtle">Governed resumption state for the next approved research family.</p>
      <section class="summary-grid">
        {_summary_card("status", str(summary.get("status", "unknown")))}
        {_summary_card("recommended action", str(summary.get("recommended_action", "define_next_research_family")))}
        {_summary_card("active plan", str(summary.get("active_plan_id", "none") or "none"))}
        {_summary_card("next runnable", str(summary.get("next_runnable_plan_id", "none") or "none"))}
        {_summary_card("current proposal", str(current_proposal.get("proposal_id", "none") or "none"))}
      </section>
      <p>{escape(str(summary.get("message", "No next-family status is available.")))}</p>
      {f"<p><strong>Blocking reason:</strong> {escape(str(summary.get('blocking_reason', '')))}</p>" if str(summary.get('blocking_reason', '')).strip() else ""}
    </section>
    """


def _research_family_comparison_section(summary: dict[str, object]) -> str:
    if not summary:
        return ""
    counts = summary.get("counts", {}) if isinstance(summary.get("counts"), dict) else {}
    families = [family for family in summary.get("families", []) if isinstance(family, dict)] if isinstance(summary.get("families"), list) else []
    rows = "".join(_research_family_row(family) for family in families[:8]) or "<tr><td colspan='8'>No research family proposals recorded.</td></tr>"
    return f"""
    <section class="panel">
      <h2>Research Family Comparison</h2>
      <p class="subtle">Proposal, approval, and queue-readiness view for the next materially different strategy family.</p>
      <section class="summary-grid">
        {_summary_card("families", str(counts.get("total", 0)))}
        {_summary_card("approved", str(counts.get("approved", 0)))}
        {_summary_card("queued", str(counts.get("queued", 0)))}
        {_summary_card("active", str(counts.get("active", 0)))}
        {_summary_card("under review", str(counts.get("under_review", 0)))}
      </section>
      <table>
        <thead><tr><th>Proposal</th><th>Status</th><th>Approval</th><th>Novelty</th><th>Readiness</th><th>Recommendation</th><th>Plan</th><th>Program</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _paper_rehearsal_section(summary: dict[str, object]) -> str:
    state = summary.get("state") if isinstance(summary.get("state"), dict) else {}
    latest_day = summary.get("latest_day") if isinstance(summary.get("latest_day"), dict) else {}
    latest_action = summary.get("latest_action") if isinstance(summary.get("latest_action"), dict) else {}
    portfolio = state.get("portfolio") if isinstance(state.get("portfolio"), dict) else {}
    recent_days = summary.get("recent_days") if isinstance(summary.get("recent_days"), list) else []
    recent_actions = summary.get("recent_actions") if isinstance(summary.get("recent_actions"), list) else []
    day_rows = "".join(_paper_day_row(day) for day in recent_days if isinstance(day, dict)) or "<tr><td colspan='6'>No paper-trading days recorded yet.</td></tr>"
    action_rows = "".join(_paper_action_row(action) for action in recent_actions if isinstance(action, dict)) or "<tr><td colspan='5'>No operator actions recorded yet.</td></tr>"
    latest_action_text = (
        f"{latest_action.get('action', 'unknown')} at {latest_action.get('recorded_at_utc', '-')}"
        if latest_action
        else "none"
    )
    latest_block_reason = ""
    if latest_day:
        block_reasons = latest_day.get("block_reasons", []) if isinstance(latest_day.get("block_reasons"), list) else []
        if block_reasons and isinstance(block_reasons[0], dict):
            latest_block_reason = str(block_reasons[0].get("message", "") or "")

    return f"""
    <section class="panel">
      <h2>Paper Rehearsal</h2>
      <p class="subtle">Operational rehearsal state for the current promoted candidate, separate from research runtime state.</p>
      <section class="summary-grid">
        {_summary_card("paper day", str(latest_day.get("status", "none") or "none"))}
        {_summary_card("profile", str((state.get("active_profile", {}) if isinstance(state.get("active_profile"), dict) else {}).get("profile_name", "none")))}
        {_summary_card("portfolio", "initialized" if bool(portfolio.get("initialized", False)) else "not initialized")}
        {_summary_card("last action", latest_action_text)}
      </section>
      <p><strong>Latest paper summary:</strong> {escape(str(latest_day.get("summary", "") or "No paper-trading day has been generated yet."))}</p>
      {f"<p><strong>Current block:</strong> {escape(latest_block_reason)}</p>" if latest_block_reason else ""}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Recent Paper Days</h2>
        <table>
          <thead><tr><th>Recorded</th><th>Status</th><th>Profile</th><th>Decision Date</th><th>Next Trade</th><th>Summary</th></tr></thead>
          <tbody>{day_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Operator Decisions</h2>
        <table>
          <thead><tr><th>Recorded</th><th>Action</th><th>Actor</th><th>Day</th><th>Reason</th></tr></thead>
          <tbody>{action_rows}</tbody>
        </table>
      </section>
    </section>
    """


def _research_family_row(family: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td><strong>{escape(str(family.get('title', family.get('proposal_id', 'proposal'))))}</strong><br><span class='subtle'>{escape(str(family.get('proposal_id', '')))}</span></td>"
        f"<td>{_status_pill(str(family.get('family_status', 'unknown')))}</td>"
        f"<td>{escape(str(family.get('approval_status', 'unknown')))}</td>"
        f"<td>{escape(str(family.get('novelty_vs_retired', 'unknown')))}</td>"
        f"<td>{escape(str(family.get('implementation_readiness', 'planned')))}</td>"
        f"<td>{escape(str(family.get('operator_recommendation', 'review_research_family')))}</td>"
        f"<td><code>{escape(str(family.get('plan_id', '')))}</code></td>"
        f"<td>{escape(str(family.get('program_title', family.get('program_id', '')) or '-'))}</td>"
        "</tr>"
    )


def _research_program_portfolio_section(summary: dict[str, object]) -> str:
    programs = [program for program in summary.get("programs", []) if isinstance(program, dict)] if isinstance(summary.get("programs"), list) else []
    counts = summary.get("counts", {}) if isinstance(summary.get("counts"), dict) else {}
    rows = "".join(_research_program_row(program) for program in programs) or "<tr><td colspan='8'>No research programs recorded.</td></tr>"
    return f"""
    <section class="panel">
      <h2>Research Program Portfolio</h2>
      <p class="subtle">Evidence-backed view of active, retired, and queued research families.</p>
      <section class="summary-grid">
        {_summary_card("programs", str(counts.get("total", 0)))}
        {_summary_card("active", str(counts.get("active", 0)))}
        {_summary_card("retired", str(counts.get("retired", 0)))}
        {_summary_card("queue eligible", str(counts.get("queue_eligible", 0)))}
      </section>
      <table>
        <thead><tr><th>Program</th><th>Status</th><th>Queue</th><th>Focus Candidate</th><th>Next Step</th><th>Reason</th><th>Recorded</th><th>Artifacts</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _runbook_queue_summary_section(summary: dict[str, object]) -> str:
    if not summary:
        return ""
    counts = summary.get("counts", {}) if isinstance(summary.get("counts"), dict) else {}
    entries = [entry for entry in summary.get("entries", []) if isinstance(entry, dict)] if isinstance(summary.get("entries"), list) else []
    warnings = [warning for warning in summary.get("warnings", []) if isinstance(warning, dict)] if isinstance(summary.get("warnings"), list) else []
    rows = "".join(_runbook_queue_row(entry) for entry in entries) or "<tr><td colspan='6'>No supervisor queue entries recorded.</td></tr>"
    warning_items = "".join(f"<li>{escape(str(warning.get('message', 'unknown warning')))}</li>" for warning in warnings) or "<li>No queue warnings recorded.</li>"
    return f"""
    <section class="panel">
      <h2>Supervisor Work Queue</h2>
      <p class="subtle">Alignment check between the OpenClaw runbook, the active branch, and the research-program portfolio.</p>
      <section class="summary-grid">
        {_summary_card("queue status", str(summary.get("status", "unknown")))}
        {_summary_card("active plan", str(summary.get("active_plan_id", "none") or "none"))}
        {_summary_card("next runnable", str(summary.get("next_runnable_plan_id", "none") or "none"))}
        {_summary_card("recommended action", str(summary.get("recommended_action", "monitor_active_plan")))}
        {_summary_card("enabled", str(counts.get("enabled", 0)))}
        {_summary_card("blocked", str(counts.get("blocked", 0)))}
        {_summary_card("untracked", str(counts.get("untracked", 0)))}
      </section>
      <p>{escape(str(summary.get("message", "No runbook summary is available.")))}</p>
      {f"<ul>{warning_items}</ul>" if warnings else ""}
      <table>
        <thead><tr><th>Plan</th><th>Status</th><th>Enabled</th><th>Program</th><th>Director</th><th>Detail</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _runbook_queue_row(entry: dict[str, object]) -> str:
    program_title = str(entry.get("program_title", "") or "not tracked")
    return (
        "<tr>"
        f"<td><code>{escape(str(entry.get('plan_id', 'unknown')))}</code></td>"
        f"<td>{_status_pill(str(entry.get('queue_status', 'unknown')))}</td>"
        f"<td>{'yes' if bool(entry.get('enabled', False)) else 'no'}</td>"
        f"<td>{escape(program_title)}</td>"
        f"<td>{escape(str(entry.get('director_name', '') or '-'))}</td>"
        f"<td>{escape(str(entry.get('detail', '') or '-'))}</td>"
        "</tr>"
    )


def _render_campaign_detail(
    payload: dict[str, object],
    *,
    refresh_seconds: int,
    flash: str | None,
    csrf_token: str | None,
) -> str:
    campaign = payload.get("campaign", {}) if isinstance(payload.get("campaign"), dict) else {}
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
    jobs = payload.get("jobs", []) if isinstance(payload.get("jobs"), list) else []

    final_decision = state.get("final_decision")
    final_decision_html = (
        f"<pre>{escape(json.dumps(final_decision, indent=2, default=str))}</pre>"
        if isinstance(final_decision, dict)
        else "<p>No final decision yet.</p>"
    )
    event_rows = "".join(_campaign_event_row(event) for event in events[-30:][::-1]) or (
        "<tr><td colspan='4'>No campaign events</td></tr>"
    )
    job_rows = "".join(_campaign_job_row(job) for job in jobs[-50:][::-1]) or (
        "<tr><td colspan='5'>No campaign jobs</td></tr>"
    )
    can_stop = str(campaign.get("status", "")) in {"queued", "running"}
    report_path = escape(str(campaign.get("latest_report_path") or ""))
    campaign_id = str(campaign.get("campaign_id", ""))
    handoff_links = _campaign_handoff_links(campaign, state)

    body = f"""
    {_flash_banner(flash)}
    {_campaign_state_banner(campaign, state)}
    <section class="hero">
      <div>
        <p><a href="/">Back to overview</a></p>
        <h1>{escape(str(campaign.get("campaign_name", "Unknown campaign")))}</h1>
        <p>Campaign id: <code>{escape(campaign_id)}</code></p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/guide">Guide</a>
        {handoff_links}
        <a class="button secondary" href="/api/campaigns/{quote(campaign_id)}">JSON</a>
      </div>
    </section>
    <section class="summary-grid">
      {_summary_card("status", str(campaign.get("status", "unknown")))}
      {_summary_card("phase", str(campaign.get("phase", "unknown")))}
      {_summary_card("jobs", str(len(jobs)))}
      {_summary_card("events", str(len(events)))}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Campaign State</h2>
        <p><strong>Config:</strong> <code>{escape(str(campaign.get("config_path", "")))}</code></p>
        <p><strong>Latest report:</strong> <code>{report_path or 'None'}</code></p>
        <p><strong>Last error:</strong> <code>{escape(str(campaign.get("last_error") or "")) or 'None'}</code></p>
        {_stop_form(str(campaign.get("campaign_id", "")), csrf_token=csrf_token) if can_stop else "<p>This campaign is not active.</p>"}
      </section>
      <section class="panel">
        <h2>Final Decision</h2>
        {final_decision_html}
      </section>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Events</h2>
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Message</th><th>Payload</th></tr></thead>
          <tbody>{event_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Jobs</h2>
        <table>
          <thead><tr><th>Job</th><th>Command</th><th>Status</th><th>Priority</th><th>Updated</th></tr></thead>
          <tbody>{job_rows}</tbody>
        </table>
      </section>
    </section>
    """
    return _render_layout(str(campaign.get("campaign_name", "Campaign")), body, refresh_seconds=refresh_seconds)


def _render_director_detail(
    payload: dict[str, object],
    *,
    refresh_seconds: int,
    flash: str | None,
    csrf_token: str | None,
) -> str:
    director = payload.get("director", {}) if isinstance(payload.get("director"), dict) else {}
    state = director.get("state", {}) if isinstance(director.get("state"), dict) else {}
    spec = director.get("spec", {}) if isinstance(director.get("spec"), dict) else {}
    queue = state.get("campaign_queue", []) if isinstance(state.get("campaign_queue"), list) else []
    events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
    campaigns = payload.get("campaigns", []) if isinstance(payload.get("campaigns"), list) else []
    plan_name = str(spec.get("plan_name") or state.get("plan_name") or "unnamed_plan")
    plan_source = str(spec.get("plan_source") or state.get("plan_source") or "unknown")
    queue_rows = "".join(_director_queue_row(entry) for entry in queue if isinstance(entry, dict)) or (
        "<tr><td colspan='8'>No queued campaigns recorded.</td></tr>"
    )
    event_rows = "".join(_director_event_row(event) for event in events[-30:][::-1]) or (
        "<tr><td colspan='4'>No director events</td></tr>"
    )
    campaign_rows = "".join(_director_campaign_row(campaign) for campaign in campaigns) or (
        "<tr><td colspan='6'>No campaigns recorded for this director.</td></tr>"
    )
    controls = _director_controls(director, queue, csrf_token=csrf_token)

    body = f"""
    {_flash_banner(flash)}
    <section class="hero">
      <div>
        <p><a href="/">Back to overview</a></p>
        <h1>{escape(str(director.get("director_name", "Unknown director")))}</h1>
        <p>Director id: <code>{escape(str(director.get("director_id", "")))}</code></p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/api/directors/{quote(str(director.get('director_id', '')))}">JSON</a>
      </div>
    </section>
    <section class="summary-grid">
      {_summary_card("status", str(director.get("status", "unknown")))}
      {_summary_card("plan", plan_name)}
      {_summary_card("queue progress", _director_progress_text(queue))}
      {_summary_card("current campaign", str(director.get("current_campaign_id") or "-"))}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Plan Metadata</h2>
        <p><strong>Plan name:</strong> <code>{escape(plan_name)}</code></p>
        <p><strong>Plan source:</strong> <code>{escape(plan_source)}</code></p>
        <p><strong>Adopt active campaigns:</strong> {bool(spec.get("adopt_active_campaigns", True))}</p>
        <p><strong>Default quality gate:</strong> <code>{escape(str(spec.get("quality_gate", "all")))}</code></p>
        {controls}
      </section>
      <section class="panel">
        <h2>Final Result</h2>
        <pre>{escape(json.dumps(state.get("final_result"), indent=2, default=str)) if state.get("final_result") is not None else "No final result yet."}</pre>
      </section>
    </section>
    <section class="panel">
      <h2>Plan Queue</h2>
      <table>
        <thead><tr><th>#</th><th>Entry</th><th>Config</th><th>Status</th><th>Campaign</th><th>Hours</th><th>Jobs</th><th>Outcome</th></tr></thead>
        <tbody>{queue_rows}</tbody>
      </table>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Director Events</h2>
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Message</th><th>Payload</th></tr></thead>
          <tbody>{event_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Campaigns</h2>
        <table>
          <thead><tr><th>Name</th><th>Status</th><th>Phase</th><th>Updated</th><th>Report</th><th>Action</th></tr></thead>
          <tbody>{campaign_rows}</tbody>
        </table>
      </section>
    </section>
    """
    return _render_layout(str(director.get("director_name", "Director")), body, refresh_seconds=refresh_seconds)


def _render_campaign_handoff(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
    campaign = payload.get("campaign", {}) if isinstance(payload.get("campaign"), dict) else {}
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    campaign_id = str(campaign.get("campaign_id", ""))
    control_row = state.get("control_row") if isinstance(state.get("control_row"), dict) else {}
    shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
    stress_results = [row for row in state.get("stress_results", []) if isinstance(row, dict)]
    final_decision = state.get("final_decision") if isinstance(state.get("final_decision"), dict) else {}
    scorecard = build_operability_scorecard(
        control_row=control_row,
        shortlisted=shortlisted,
        stress_results=stress_results,
        final_decision=final_decision,
    )
    selected_candidate = _selected_candidate(shortlisted, final_decision)
    selected_stress = _selected_stress_result(stress_results, final_decision, selected_candidate)
    artifact_paths = _campaign_scorecard_artifact_paths(campaign)

    body = f"""
    {_flash_banner(flash)}
    {_campaign_state_banner(campaign, state)}
    <section class="hero">
      <div>
        <p><a href="/campaigns/{quote(campaign_id)}">Back to campaign</a></p>
        <h1>Promotion Handoff</h1>
        <p>Plain-English summary for {escape(str(campaign.get("campaign_name", "unknown campaign")))}.</p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/campaigns/{quote(campaign_id)}/scorecard">Scorecard</a>
        <a class="button secondary" href="/campaigns/{quote(campaign_id)}/comparison">Compare Candidates</a>
        <a class="button secondary" href="/api/campaigns/{quote(campaign_id)}">JSON</a>
      </div>
    </section>
    <section class="summary-grid">
      {_summary_card("campaign status", str(campaign.get("status", "unknown")))}
      {_summary_card("phase", str(campaign.get("phase", "unknown")))}
      {_summary_card("shortlist", str(len(shortlisted)))}
      {_summary_card("decision", str(final_decision.get("recommended_action", "pending")))}
      {_summary_card("operator recommendation", str(scorecard.get("operator_recommendation", "needs_more_research")))}
    </section>
    <section class="panel">
      <h2>Operator Recommendation</h2>
      <p><strong>{escape(str(scorecard.get("operator_recommendation", "needs_more_research")))}</strong></p>
      <p>{escape(str(scorecard.get("summary", "")))}</p>
      {_scorecard_artifact_paths(artifact_paths)}
    </section>
    <section class="panel">
      <h2>What The Strategy Does</h2>
      {_handoff_strategy_description(control_row, selected_candidate)}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Why It Passed</h2>
        {_handoff_why_it_passed(control_row, selected_candidate, selected_stress, final_decision)}
      </section>
      <section class="panel">
        <h2>Where It Is Weak</h2>
        {_handoff_where_it_is_weak(control_row, selected_candidate, selected_stress, final_decision)}
      </section>
    </section>
    <section class="panel">
      <h2>What Should Happen Next</h2>
      {_scorecard_list(scorecard.get("next_steps"), empty_message="No next steps recorded yet.")}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Selected Candidate Snapshot</h2>
        {_candidate_snapshot(selected_candidate, selected_stress, empty_message="No shortlisted candidate has been selected yet.")}
      </section>
      <section class="panel">
        <h2>Control Snapshot</h2>
        {_candidate_snapshot(control_row, None, empty_message="Control metrics are not available yet.", is_control=True)}
      </section>
    </section>
    """
    return _render_layout("Promotion Handoff", body, refresh_seconds=refresh_seconds)


def _render_campaign_scorecard(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
    campaign = payload.get("campaign", {}) if isinstance(payload.get("campaign"), dict) else {}
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    campaign_id = str(campaign.get("campaign_id", ""))
    scorecard = build_operability_scorecard(
        control_row=state.get("control_row") if isinstance(state.get("control_row"), dict) else {},
        shortlisted=[row for row in state.get("shortlisted", []) if isinstance(row, dict)],
        stress_results=[row for row in state.get("stress_results", []) if isinstance(row, dict)],
        final_decision=state.get("final_decision") if isinstance(state.get("final_decision"), dict) else {},
    )
    artifact_paths = _campaign_scorecard_artifact_paths(campaign)

    body = f"""
    {_flash_banner(flash)}
    {_campaign_state_banner(campaign, state)}
    <section class="hero">
      <div>
        <p><a href="/campaigns/{quote(campaign_id)}/handoff">Back to handoff</a></p>
        <h1>Operator Scorecard</h1>
        <p>Plain-English operator recommendation for {escape(str(campaign.get("campaign_name", "unknown campaign")))}.</p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/campaigns/{quote(campaign_id)}/comparison">Compare Candidates</a>
        <a class="button secondary" href="/api/campaigns/{quote(campaign_id)}">JSON</a>
      </div>
    </section>
    <section class="summary-grid">
      {_summary_card("operator recommendation", str(scorecard.get("operator_recommendation", "needs_more_research")))}
      {_summary_card("campaign decision", str(scorecard.get("campaign_decision", "continue_research")))}
    </section>
    <section class="panel">
      <h2>Summary</h2>
      <p>{escape(str(scorecard.get("summary", "")))}</p>
      {_scorecard_artifact_paths(artifact_paths)}
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>Strengths</h2>
        {_scorecard_list(scorecard.get("strengths"), empty_message="No strengths recorded.")}
      </section>
      <section class="panel">
        <h2>Weaknesses</h2>
        {_scorecard_list(scorecard.get("weaknesses"), empty_message="No weaknesses recorded.")}
      </section>
    </section>
    <section class="panel">
      <h2>Next Steps</h2>
      {_scorecard_list(scorecard.get("next_steps"), empty_message="No next steps recorded.")}
    </section>
    """
    return _render_layout("Operator Scorecard", body, refresh_seconds=refresh_seconds)


def _render_campaign_comparison(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
    campaign = payload.get("campaign", {}) if isinstance(payload.get("campaign"), dict) else {}
    state = campaign.get("state", {}) if isinstance(campaign.get("state"), dict) else {}
    campaign_id = str(campaign.get("campaign_id", ""))
    control_row = state.get("control_row") if isinstance(state.get("control_row"), dict) else {}
    shortlisted = [row for row in state.get("shortlisted", []) if isinstance(row, dict)]
    stress_results = [row for row in state.get("stress_results", []) if isinstance(row, dict)]
    stress_by_run = {
        str(row.get("candidate_run_name", "")): row
        for row in stress_results
        if isinstance(row, dict)
    }
    final_decision = state.get("final_decision") if isinstance(state.get("final_decision"), dict) else {}
    selected_run_name = str(final_decision.get("selected_run_name") or "")

    comparison_rows = []
    if control_row:
        comparison_rows.append(_comparison_row(control_row, is_control=True, is_selected=False, stress_result=None))
    comparison_rows.extend(
        _comparison_row(
            row,
            is_control=False,
            is_selected=str(row.get("run_name", "")) == selected_run_name,
            stress_result=stress_by_run.get(str(row.get("run_name", ""))),
        )
        for row in shortlisted
    )
    rows_html = "".join(comparison_rows) or "<tr><td colspan='10'>No comparison data is available yet.</td></tr>"

    body = f"""
    {_flash_banner(flash)}
    <section class="hero">
      <div>
        <p><a href="/campaigns/{quote(campaign_id)}/handoff">Back to handoff</a></p>
        <h1>Candidate Comparison</h1>
        <p>Side-by-side metrics for the control strategy and the campaign shortlist.</p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/campaigns/{quote(campaign_id)}">Campaign</a>
        <a class="button secondary" href="/api/campaigns/{quote(campaign_id)}">JSON</a>
      </div>
    </section>
    <section class="panel">
      <h2>Comparison Table</h2>
      <table>
        <thead>
          <tr>
            <th>Role</th>
            <th>Run</th>
            <th>Profile</th>
            <th>Validation Excess</th>
            <th>Holdout Excess</th>
            <th>Walk-Forward</th>
            <th>Turnover Limit</th>
            <th>Rebalance Days</th>
            <th>Stress</th>
            <th>Operator Note</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
    """
    return _render_layout("Candidate Comparison", body, refresh_seconds=refresh_seconds)


def _render_guide(*, refresh_seconds: int) -> str:
    body = """
    <section class="hero">
      <div>
        <p><a href="/">Back to overview</a></p>
        <h1>Application Guide</h1>
        <p>A plain-English walkthrough of what this system is, what it is trying to achieve, and what happens when it succeeds.</p>
      </div>
      <div class="hero-links">
        <a class="button secondary" href="/">Dashboard</a>
      </div>
    </section>
    <section class="panel">
      <h2>Purpose</h2>
      <p>This application is a strategy research and selection system for UK equities. It tests many stock-selection ideas, rejects weak ones, and tries to find a small number of robust candidates that still look sensible after tougher checks.</p>
      <p>It is not a live trading bot today. Its current job is to do research in a disciplined way so that only stronger candidates survive.</p>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>What It Is Trying To Achieve</h2>
        <p>The system is trying to find one strategy that is good enough to promote. Promotion means the idea did not only look good in one backtest. It also held up when tested on separate periods and under tougher assumptions.</p>
        <ol>
          <li>Validation: does it still work on reserved data?</li>
          <li>Holdout: does it keep working on later unseen data?</li>
          <li>Walk-forward: does it remain reasonably stable through time?</li>
          <li>Stress pack: does it remain usable under more realistic cost and execution assumptions?</li>
        </ol>
      </section>
      <section class="panel">
        <h2>What Success Means</h2>
        <p>Success does not mean "best looking line on a chart." It means the system found a candidate strong enough to freeze as a serious strategy proposal.</p>
        <p>When that happens, the application writes promotion artifacts, marks the campaign as completed, and emits a dedicated promotion notification. That is the point where a human review should happen.</p>
      </section>
    </section>
    <section class="panel">
      <h2>Architecture</h2>
      <table>
        <thead><tr><th>Part</th><th>Role</th></tr></thead>
        <tbody>
          <tr><td><strong>Coordinator</strong></td><td>Keeps the research queue healthy and leases jobs to workers.</td></tr>
          <tr><td><strong>Workers</strong></td><td>Run the actual research jobs in parallel.</td></tr>
          <tr><td><strong>Campaign Manager</strong></td><td>Runs one strategy family through focused tuning, pivots, and stress testing.</td></tr>
          <tr><td><strong>Research Director</strong></td><td>Chooses the next approved campaign when one campaign exhausts.</td></tr>
          <tr><td><strong>Dashboard</strong></td><td>Shows what the system is doing and lets the operator stop work if needed.</td></tr>
          <tr><td><strong>Runtime Database</strong></td><td>Stores persistent state for jobs, campaigns, directors, and events.</td></tr>
          <tr><td><strong>Catalog</strong></td><td>Stores reports, profile history, and promotion evidence.</td></tr>
        </tbody>
      </table>
    </section>
    <section class="split-grid">
      <section class="panel">
        <h2>How To Read The Dashboard</h2>
        <p><strong>Current Best Candidate</strong> is the fastest operator answer for what the system currently thinks is the lead branch, why it leads, what is still weak, and what should happen next.</p>
        <p><strong>Active Directors</strong> are the highest-level search programs. A director can launch the next campaign automatically.</p>
        <p><strong>Active Campaigns</strong> are the current strategy families being tested.</p>
        <p><strong>Workers</strong> tell you whether the machine is actively processing jobs.</p>
        <p><strong>Recent Notifications</strong> show major events such as failures, stops, and successful promotions.</p>
        <p><strong>Recent Jobs</strong> show the lower-level queue activity behind the higher-level orchestration.</p>
      </section>
      <section class="panel">
        <h2>Important Terms</h2>
        <p><strong>Strategy</strong>: a rules-based way to select and weight stocks.</p>
        <p><strong>Campaign</strong>: one bounded search across a strategy family.</p>
        <p><strong>Director</strong>: the controller that chains campaigns together.</p>
        <p><strong>Validation / Holdout</strong>: reserved testing periods used to avoid fooling ourselves.</p>
        <p><strong>Walk-forward</strong>: repeated rolling tests that check stability through time.</p>
        <p><strong>Stress pack</strong>: harsher assumptions for spreads, costs, execution, or availability.</p>
        <p><strong>Promotion</strong>: freezing a candidate because it passed the required gates.</p>
      </section>
    </section>
    <section class="panel">
      <h2>What The System Is Achieving Day To Day</h2>
      <p>Most of the time, the system is reducing uncertainty rather than celebrating wins. It is proving which ideas do not survive robust testing. That is useful progress because it narrows the search and prevents weak strategies from reaching later stages.</p>
      <p>If you see a lot of jobs and no promoted strategy yet, that usually means the filtering process is still doing its job. Promoted candidates should be rare compared with the total number of tested variants.</p>
    </section>
    <section class="panel">
      <h2>What We Intend To Do With A Solid Candidate</h2>
      <p>Once a strategy is promoted, the next step is not immediate live trading. The intended path is controlled review and operational hardening:</p>
      <ol>
        <li>review the frozen candidate and its evidence</li>
        <li>decide whether it should go to paper trading first</li>
        <li>define broker integration, risk controls, and monitoring</li>
        <li>only then consider a live-trading implementation</li>
      </ol>
      <p>So this system is the research and evidence engine. A future live bot would be a later phase built on top of a candidate that has already passed this process.</p>
    </section>
    """
    return _render_layout("Application Guide", body, refresh_seconds=refresh_seconds)


def _render_layout(title: str, body: str, *, refresh_seconds: int) -> str:
    refresh_meta = f'<meta http-equiv="refresh" content="{refresh_seconds}">' if refresh_seconds > 0 else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_meta}
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f1e8;
      --panel: #fffaf0;
      --ink: #1d2a24;
      --muted: #5a6b61;
      --line: #d7d0c0;
      --accent: #145a4a;
      --accent-soft: #dceee8;
      --warn: #8b5a00;
      --danger: #8f2d2d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, #efe6cf 0, transparent 28rem),
        linear-gradient(180deg, #f7f4eb 0%, var(--bg) 100%);
    }}
    main {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem; }}
    a {{ color: var(--accent); }}
    code, pre {{
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 0.9rem;
    }}
    .hero, .summary-grid, .split-grid {{ margin-bottom: 1.25rem; }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: end;
    }}
    .hero h1 {{ margin: 0 0 0.35rem 0; font-size: 2rem; }}
    .hero p {{ margin: 0.15rem 0; color: var(--muted); }}
    .hero-links {{ display: flex; gap: 0.75rem; align-items: center; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.85rem;
    }}
    .split-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 1rem;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(29, 42, 36, 0.06);
    }}
    .card {{ padding: 1rem; }}
    .card h2, .panel h2 {{
      margin: 0 0 0.75rem 0;
      font-size: 1rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .metric {{
      font-size: 1.8rem;
      font-weight: bold;
    }}
    .panel {{ padding: 1rem; overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      padding: 0.6rem 0.5rem;
      border-bottom: 1px solid var(--line);
    }}
    th {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .pill {{
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.82rem;
      white-space: nowrap;
    }}
    .pill.info {{ background: var(--accent-soft); color: var(--accent); }}
    .pill.success {{ background: #dceee8; color: #1e6a4c; }}
    .pill.warn {{ background: #f3e5bf; color: var(--warn); }}
    .pill.danger {{ background: #f1d7d7; color: var(--danger); }}
    .button {{
      display: inline-block;
      padding: 0.55rem 0.9rem;
      border-radius: 999px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      border: 0;
      cursor: pointer;
      font: inherit;
    }}
    .button.secondary {{
      background: transparent;
      color: var(--accent);
      border: 1px solid var(--accent);
    }}
    .button.danger {{
      background: var(--danger);
    }}
    .flash {{
      margin-bottom: 1rem;
      padding: 0.9rem 1rem;
      border-radius: 14px;
      background: #dceee8;
      border: 1px solid #9ecbbb;
      color: var(--accent);
    }}
    .flash.info {{ background: #dceee8; border-color: #9ecbbb; color: var(--accent); }}
    .flash.success {{ background: #dceee8; border-color: #9ecbbb; color: #1e6a4c; }}
    .flash.warn {{ background: #fff2d4; border-color: #e0c483; color: var(--warn); }}
    .flash.danger {{ background: #f6dede; border-color: #d49b9b; color: var(--danger); }}
    form.inline {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.65rem;
      align-items: center;
      margin-top: 0.8rem;
    }}
    input[type="text"] {{
      flex: 1 1 260px;
      padding: 0.55rem 0.7rem;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: white;
      font: inherit;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 0.82rem;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>"""


def _agent_summary_row(summary: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(summary.get('agent_id', '-')))}</td>"
        f"<td>{escape(str(summary.get('summary_type', '-')))}</td>"
        f"<td>{escape(str(summary.get('classification', '-')))}</td>"
        f"<td>{escape(str(summary.get('status', '-')))}</td>"
        f"<td>{escape(str(summary.get('recommended_action', '-')))}</td>"
        f"<td>{_timestamp_with_age(summary.get('recorded_at_utc'))}</td>"
        "</tr>"
    )

def _decision_snapshot_card(label: str, summary: object) -> str:
    if not isinstance(summary, dict):
        return (
            f"<section class='card'><h2>{escape(label)}</h2>"
            "<p class='subtle'>No summary yet</p></section>"
        )
    context_bits = [
        str(summary.get("campaign_id") or "").strip(),
        str(summary.get("profile_name") or "").strip(),
        str(summary.get("director_id") or "").strip(),
    ]
    context_text = " | ".join(bit for bit in context_bits if bit) or "-"
    action = str(summary.get("recommended_action") or "-")
    return (
        f"<section class='card'><h2>{escape(label)}</h2>"
        f"<div class='metric'>{escape(str(summary.get('classification') or '-'))}</div>"
        f"<p><strong>Status:</strong> {escape(str(summary.get('status') or '-'))}</p>"
        f"<p><strong>Action:</strong> {escape(action)}</p>"
        f"<p><strong>Context:</strong> {escape(context_text)}</p>"
        f"<p class='subtle'>{escape(str(summary.get('message') or '')[:180])}</p>"
        f"<p class='subtle'>{_timestamp_with_age(summary.get('recorded_at_utc'))}</p>"
        "</section>"
    )


def _agent_dispatch_row(record: dict[str, object]) -> str:
    outcome = "suppressed" if bool(record.get("suppressed")) else "success" if bool(record.get("success")) else "failed" if record.get("success") is False else "pending"
    model = str(record.get("model") or record.get("provider") or "-")
    duration_ms = str(record.get("duration_ms") or "-")
    tokens = str(record.get("total_tokens") or "-")
    return (
        "<tr>"
        f"<td>{escape(str(record.get('agent_id', '-')))}</td>"
        f"<td>{escape(str(record.get('event_type', '-')))}</td>"
        f"<td>{_status_pill(outcome)}</td>"
        f"<td>{escape(model)}</td>"
        f"<td>{escape(tokens)}</td>"
        f"<td>{escape(duration_ms)}</td>"
        f"<td>{_timestamp_with_age(record.get('recorded_at_utc'))}</td>"
        "</tr>"
    )


def _summary_card(label: str, value: str) -> str:    return f"<section class='card'><h2>{escape(label)}</h2><div class='metric'>{escape(value)}</div></section>"


def _health_panel(health: dict[str, object]) -> str:
    status = str(health.get("status", "unknown"))
    summary = str(health.get("summary", "No health summary available."))
    checks = health.get("checks", [])
    rows = "".join(_health_check_row(check) for check in checks if isinstance(check, dict))
    if not rows:
        rows = "<tr><td colspan='3'>No health checks available.</td></tr>"
    return f"""
    <section class="panel">
      <h2>System Health</h2>
      {_alert_banner(summary, _health_severity(status))}
      <table>
        <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _service_heartbeat_section(records: list[dict[str, object]]) -> str:
    rows = "".join(_service_heartbeat_row(record) for record in records if isinstance(record, dict))
    if not rows:
        rows = "<tr><td colspan='5'>No service heartbeat records available.</td></tr>"
    return f"""
    <section class="panel">
      <h2>Service Heartbeats</h2>
      <p class="subtle">Health signal from the coordinator, campaign manager, and research director control loops.</p>
      <table>
        <thead><tr><th>Service</th><th>Status</th><th>Recorded</th><th>PID</th><th>Detail</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _health_check_row(check: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(check.get('name', 'check')))}</td>"
        f"<td>{_status_pill(str(check.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(check.get('detail', '')))}</td>"
        "</tr>"
    )


def _service_heartbeat_row(record: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(record.get('label') or record.get('service') or 'unknown'))}</td>"
        f"<td>{_status_pill(str(record.get('status', 'unknown')))}</td>"
        f"<td>{_timestamp_with_age(record.get('recorded_at_utc'))}</td>"
        f"<td>{escape(str(record.get('pid') or '-'))}</td>"
        f"<td>{escape(str(record.get('detail', '')))}</td>"
        "</tr>"
    )


def _health_severity(status: str) -> str:
    lowered = status.lower()
    if lowered in {"critical", "error", "stalled"}:
        return "error"
    if lowered in {"warning", "degraded", "idle", "blocked"}:
        return "warning"
    return "success"


def _status_count(items: object, status: str) -> int:
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and str(item.get("status", "")).lower() == status.lower())


def _campaign_row(campaign: object) -> str:
    if not isinstance(campaign, dict):
        return ""
    report = escape(str(campaign.get("latest_report_path") or ""))
    campaign_id = str(campaign.get("campaign_id", ""))
    return (
        "<tr>"
        f"<td><a href='/campaigns/{quote(campaign_id)}'>{escape(str(campaign.get('campaign_name', campaign_id)))}</a></td>"
        f"<td>{_status_pill(str(campaign.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(campaign.get('phase', 'unknown')))}</td>"
        f"<td>{_timestamp_with_age(campaign.get('updated_at'))}</td>"
        f"<td><code>{report or 'None'}</code></td>"
        f"<td><a class='button secondary' href='/campaigns/{quote(campaign_id)}'>View</a> "
        f"<a class='button secondary' href='/campaigns/{quote(campaign_id)}/handoff'>Handoff</a></td>"
        "</tr>"
    )


def _director_row(director: object) -> str:
    payload = director if isinstance(director, dict) else {}
    state = payload.get("state", {}) if isinstance(payload.get("state"), dict) else {}
    spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
    final_result = state.get("final_result", {}) if isinstance(state.get("final_result"), dict) else {}
    queue = state.get("campaign_queue", []) if isinstance(state.get("campaign_queue"), list) else []
    director_id = str(payload.get("director_id", ""))
    plan_name = str(spec.get("plan_name") or state.get("plan_name") or "unnamed_plan")
    return (
        "<tr>"
        f"<td><a href='/directors/{quote(director_id)}'>{escape(str(payload.get('director_name', 'unknown')))}</a></td>"
        f"<td>{_status_pill(str(payload.get('status', 'unknown')))}</td>"
        f"<td><code>{escape(plan_name)}</code></td>"
        f"<td>{escape(_director_progress_text(queue))}</td>"
        f"<td><code>{escape(str(payload.get('current_campaign_id', '') or '-'))}</code></td>"
        f"<td><code>{escape(str(payload.get('successful_campaign_id', '') or '-'))}</code></td>"
        f"<td>{escape(str(final_result.get('recommended_action', '-')))}</td>"
        "</tr>"
    )


def _worker_row(worker: object) -> str:
    if not isinstance(worker, dict):
        return ""
    return (
        "<tr>"
        f"<td>{escape(str(worker.get('worker_id', '')))}</td>"
        f"<td>{_status_pill(str(worker.get('status', 'unknown')))}</td>"
        f"<td><code>{escape(str(worker.get('current_job_id') or '')) or 'Idle'}</code></td>"
        f"<td>{_timestamp_with_age(worker.get('heartbeat_at') or worker.get('updated_at'))}</td>"
        "</tr>"
    )


def _job_row(job: object) -> str:
    if not isinstance(job, dict):
        return ""
    campaign_id = str(job.get("campaign_id") or "")
    campaign_link = (
        f"<a href='/campaigns/{quote(campaign_id)}'><code>{escape(campaign_id)}</code></a>"
        if campaign_id
        else "<span>-</span>"
    )
    return (
        "<tr>"
        f"<td><code>{escape(str(job.get('job_id', '')))}</code></td>"
        f"<td>{campaign_link}</td>"
        f"<td>{escape(str(job.get('command', '')))}</td>"
        f"<td>{_status_pill(str(job.get('status', 'unknown')))}</td>"
        f"<td><code>{escape(str(job.get('leased_by') or '')) or 'Unleased'}</code></td>"
        f"<td>{_timestamp_with_age(job.get('created_at'))}</td>"
        f"<td>{_timestamp_with_age(job.get('updated_at'))}</td>"
        "</tr>"
    )


def _notification_row(record: object) -> str:
    if not isinstance(record, dict):
        return ""
    severity = str(record.get("severity", "info"))
    hook = record.get("hook", {}) if isinstance(record.get("hook"), dict) else {}
    hook_text = "not requested"
    hook_class = ""
    if bool(record.get("notification_requested")):
        hook_success = hook.get("success")
        if hook_success is True:
            hook_text = "hook ok"
        elif hook_success is False:
            hook_text = "hook failed"
            hook_class = " danger"
        else:
            hook_text = "hook pending"
            hook_class = " warn"
    campaign_id = str(record.get("campaign_id", ""))
    campaign_name = escape(str(record.get("campaign_name", campaign_id)))
    campaign_link = f"<a href='/campaigns/{quote(campaign_id)}'>{campaign_name}</a>" if campaign_id else campaign_name
    return (
        "<tr>"
        f"<td>{_timestamp_with_age(record.get('recorded_at_utc'))}</td>"
        f"<td>{_severity_pill(severity)}</td>"
        f"<td>{_status_pill(str(record.get('event_type', 'notification')))}</td>"
        f"<td>{campaign_link}</td>"
        f"<td>{escape(str(record.get('message', '')))}</td>"
        f"<td><span class='pill{hook_class}'>{escape(hook_text)}</span></td>"
        "</tr>"
    )


def _campaign_outcome_row(campaign: object) -> str:
    if not isinstance(campaign, dict):
        return ""
    report = escape(str(campaign.get("latest_report_path") or ""))
    campaign_id = str(campaign.get("campaign_id", ""))
    return (
        "<tr>"
        f"<td><a href='/campaigns/{quote(campaign_id)}'>{escape(str(campaign.get('campaign_name', campaign_id)))}</a></td>"
        f"<td>{_status_pill(str(campaign.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(campaign.get('phase', 'unknown')))}</td>"
        f"<td>{_timestamp_with_age(campaign.get('updated_at'))}</td>"
        f"<td><code>{report or 'None'}</code></td>"
        f"<td><a class='button secondary' href='/campaigns/{quote(campaign_id)}'>View</a></td>"
        "</tr>"
    )


def _director_outcome_row(director: object) -> str:
    payload = director if isinstance(director, dict) else {}
    director_id = str(payload.get("director_id", ""))
    plan_name = str(payload.get("plan_name") or payload.get("spec", {}).get("plan_name", "unnamed_plan")) if isinstance(payload.get("spec"), dict) else str(payload.get("plan_name") or "unnamed_plan")
    return (
        "<tr>"
        f"<td><a href='/directors/{quote(director_id)}'>{escape(str(payload.get('director_name', director_id or 'unknown')))}</a></td>"
        f"<td>{_status_pill(str(payload.get('status', 'unknown')))}</td>"
        f"<td><code>{escape(plan_name)}</code></td>"
        f"<td>{_timestamp_with_age(payload.get('updated_at'))}</td>"
        f"<td><code>{escape(str(payload.get('successful_campaign_id') or '-'))}</code></td>"
        f"<td><a class='button secondary' href='/directors/{quote(director_id)}'>View</a></td>"
        "</tr>"
    )


def _recent_change_row(change: object) -> str:
    if not isinstance(change, dict):
        return ""
    return (
        "<tr>"
        f"<td>{_timestamp_with_age(change.get('timestamp'))}</td>"
        f"<td>{escape(str(change.get('source', 'unknown')))}</td>"
        f"<td>{escape(str(change.get('message', '')))}</td>"
        "</tr>"
    )


def _campaign_event_row(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    payload = event.get("payload_json")
    if isinstance(payload, str):
        payload_text = payload
    else:
        payload_text = json.dumps(payload, indent=2, default=str)
    return (
        "<tr>"
        f"<td>{escape(str(event.get('recorded_at_utc', '')))}</td>"
        f"<td>{_status_pill(str(event.get('event_type', 'event')))}</td>"
        f"<td>{escape(str(event.get('message', '')))}</td>"
        f"<td><pre>{escape(payload_text)}</pre></td>"
        "</tr>"
    )


def _campaign_job_row(job: object) -> str:
    if not isinstance(job, dict):
        return ""
    return (
        "<tr>"
        f"<td><code>{escape(str(job.get('job_id', '')))}</code></td>"
        f"<td>{escape(str(job.get('command', '')))}</td>"
        f"<td>{_status_pill(str(job.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(job.get('priority', '')))}</td>"
        f"<td>{_timestamp_with_age(job.get('updated_at'))}</td>"
        "</tr>"
    )


def _director_queue_row(entry: object) -> str:
    if not isinstance(entry, dict):
        return ""
    campaign_id = str(entry.get("campaign_id") or "")
    campaign_cell = (
        f"<a href='/campaigns/{quote(campaign_id)}'><code>{escape(campaign_id)}</code></a>"
        if campaign_id
        else "-"
    )
    return (
        "<tr>"
        f"<td>{escape(str(entry.get('queue_index', '')))}</td>"
        f"<td>{escape(str(entry.get('campaign_name') or entry.get('entry_name') or 'unknown'))}</td>"
        f"<td><code>{escape(str(entry.get('config_path', '')))}</code></td>"
        f"<td>{_status_pill(str(entry.get('status', 'pending')))}</td>"
        f"<td>{campaign_cell}</td>"
        f"<td>{escape(str(entry.get('campaign_max_hours', '-')))}</td>"
        f"<td>{escape(str(entry.get('campaign_max_jobs', '-')))}</td>"
        f"<td>{escape(str(entry.get('outcome') or '-'))}</td>"
        "</tr>"
    )


def _director_event_row(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    payload = event.get("payload_json")
    payload_text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return (
        "<tr>"
        f"<td>{_timestamp_with_age(event.get('recorded_at_utc'))}</td>"
        f"<td>{_status_pill(str(event.get('event_type', 'event')))}</td>"
        f"<td>{escape(str(event.get('message', '')))}</td>"
        f"<td><pre>{escape(payload_text)}</pre></td>"
        "</tr>"
    )


def _director_campaign_row(campaign: object) -> str:
    if not isinstance(campaign, dict):
        return ""
    campaign_id = str(campaign.get("campaign_id", ""))
    report = escape(str(campaign.get("latest_report_path") or ""))
    return (
        "<tr>"
        f"<td><a href='/campaigns/{quote(campaign_id)}'>{escape(str(campaign.get('campaign_name', campaign_id)))}</a></td>"
        f"<td>{_status_pill(str(campaign.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(campaign.get('phase', 'unknown')))}</td>"
        f"<td>{_timestamp_with_age(campaign.get('updated_at'))}</td>"
        f"<td><code>{report or 'None'}</code></td>"
        f"<td><a class='button secondary' href='/campaigns/{quote(campaign_id)}'>View</a></td>"
        "</tr>"
    )


def _campaign_handoff_links(campaign: dict[str, object], state: dict[str, object]) -> str:
    campaign_id = str(campaign.get("campaign_id", ""))
    if not campaign_id:
        return ""
    has_candidate_context = bool(state.get("control_row")) or bool(state.get("shortlisted")) or bool(state.get("final_decision"))
    if not has_candidate_context:
        return ""
    return (
        f"<a class='button secondary' href='/campaigns/{quote(campaign_id)}/handoff'>Handoff</a>"
        f"<a class='button secondary' href='/campaigns/{quote(campaign_id)}/scorecard'>Scorecard</a>"
        f"<a class='button secondary' href='/campaigns/{quote(campaign_id)}/comparison'>Compare</a>"
    )


def _selected_candidate(shortlisted: list[dict[str, object]], final_decision: dict[str, object]) -> dict[str, object] | None:
    selected_run_name = str(final_decision.get("selected_run_name") or "")
    if selected_run_name:
        for row in shortlisted:
            if str(row.get("run_name", "")) == selected_run_name:
                return row
    return shortlisted[0] if shortlisted else None


def _selected_stress_result(
    stress_results: list[dict[str, object]],
    final_decision: dict[str, object],
    selected_candidate: dict[str, object] | None,
) -> dict[str, object] | None:
    selected_run_name = str(final_decision.get("selected_run_name") or "")
    if not selected_run_name and selected_candidate is not None:
        selected_run_name = str(selected_candidate.get("run_name", ""))
    for row in stress_results:
        if str(row.get("candidate_run_name", "")) == selected_run_name:
            return row
    return None


def _handoff_strategy_description(control_row: dict[str, object], selected_candidate: dict[str, object] | None) -> str:
    if selected_candidate is None:
        return (
            "<p>No shortlisted candidate is ready to describe yet. The campaign is still searching or has not produced a viable candidate.</p>"
        )
    rebalance_days = int(selected_candidate.get("rebalance_frequency_days", 0) or 0)
    top_n = int(selected_candidate.get("top_n", 0) or 0)
    gross = float(selected_candidate.get("target_gross_exposure", 0.0) or 0.0)
    turnover_limit = float(selected_candidate.get("max_rebalance_turnover_pct", 0.0) or 0.0)
    sector_cap = selected_candidate.get("sector_cap")
    comparison = ""
    control_rebalance_days = int(control_row.get("rebalance_frequency_days", 0) or 0)
    if control_rebalance_days and rebalance_days:
        if rebalance_days > control_rebalance_days:
            comparison = " It rebalances more slowly than the control strategy."
        elif rebalance_days < control_rebalance_days:
            comparison = " It rebalances more often than the control strategy."
    sector_text = "no explicit sector cap"
    if sector_cap not in {None, ""}:
        sector_text = f"a sector cap of {int(sector_cap)} names"
    return (
        f"<p>This candidate is a long-only UK equity basket that typically holds about {top_n} names and "
        f"targets roughly {gross:.0%} gross exposure.</p>"
        f"<p>It is designed to rebalance every {rebalance_days} trading days with a turnover cap of {turnover_limit:.0%} "
        f"and {sector_text}.{comparison}</p>"
    )


def _handoff_why_it_passed(
    control_row: dict[str, object],
    selected_candidate: dict[str, object] | None,
    selected_stress: dict[str, object] | None,
    final_decision: dict[str, object],
) -> str:
    if selected_candidate is None:
        return "<p>No candidate has earned a pass-style explanation yet.</p>"
    reasons: list[str] = []
    if bool(selected_candidate.get("eligible", False)):
        reasons.append("It passed the promotion eligibility checks.")
    validation = float(selected_candidate.get("validation_excess_return", 0.0) or 0.0)
    holdout = float(selected_candidate.get("holdout_excess_return", 0.0) or 0.0)
    if validation > 0:
        reasons.append(f"It beat the benchmark in validation by {validation:.2%}.")
    if holdout > 0:
        reasons.append(f"It kept positive holdout excess return at {holdout:.2%}.")
    candidate_windows = int(selected_candidate.get("walkforward_pass_windows", 0) or 0)
    control_windows = int(control_row.get("walkforward_pass_windows", 0) or 0)
    if candidate_windows > 0:
        if control_windows:
            reasons.append(
                f"It achieved {candidate_windows} walk-forward pass windows compared with {control_windows} for the control."
            )
        else:
            reasons.append(f"It achieved {candidate_windows} walk-forward pass windows.")
    if selected_stress is not None and bool(selected_stress.get("stress_ok", False)):
        reasons.append("It stayed non-broken across the configured stress scenarios.")
    if final_decision.get("recommended_action") == "freeze_candidate":
        reasons.append("The campaign judged it strong enough to freeze for human review.")
    if not reasons:
        reasons.append("The campaign has not produced a fully positive pass case yet.")
    return _paragraph_list(reasons)


def _handoff_where_it_is_weak(
    control_row: dict[str, object],
    selected_candidate: dict[str, object] | None,
    selected_stress: dict[str, object] | None,
    final_decision: dict[str, object],
) -> str:
    weaknesses: list[str] = []
    if selected_candidate is None:
        weaknesses.append("There is no selected candidate yet, so the campaign is still in search mode.")
    else:
        validation = float(selected_candidate.get("validation_excess_return", 0.0) or 0.0)
        holdout = float(selected_candidate.get("holdout_excess_return", 0.0) or 0.0)
        if validation <= 0:
            weaknesses.append("Validation excess return is not positive.")
        if holdout <= 0:
            weaknesses.append("Holdout excess return is not positive.")
        candidate_windows = int(selected_candidate.get("walkforward_pass_windows", 0) or 0)
        control_windows = int(control_row.get("walkforward_pass_windows", 0) or 0)
        if candidate_windows <= control_windows:
            weaknesses.append("Walk-forward robustness did not clearly improve over the control.")
        rejection_reason = str(selected_candidate.get("rejection_reason", "") or "")
        if rejection_reason:
            weaknesses.append(f"The candidate still carries a rejection warning: {rejection_reason}.")
        if selected_stress is not None and not bool(selected_stress.get("stress_ok", False)):
            broken_count = int(selected_stress.get("broken_count", 0) or 0)
            weaknesses.append(f"It broke under {broken_count} stress scenarios.")
    if final_decision.get("recommended_action") in {"continue_research", "exhausted"}:
        weaknesses.append("The campaign did not find evidence strong enough to freeze a candidate.")
    if final_decision.get("pivot_used"):
        weaknesses.append("The campaign needed a pivot, which suggests the original family was not sufficient on its own.")
    if not weaknesses:
        weaknesses.append("No major weakness was recorded at this stage, but human review is still required.")
    return _paragraph_list(weaknesses)


def _handoff_next_steps(final_decision: dict[str, object]) -> str:
    action = str(final_decision.get("recommended_action", "pending"))
    reason = str(final_decision.get("reason", "unknown"))
    if action == "freeze_candidate":
        lines = [
            "The next step is operator review, not live trading.",
            "Review the frozen evidence pack, decide whether the candidate should move into paper trading, and only then plan operational hardening.",
        ]
    elif action in {"continue_research", "continue_benchmark_pivot", "continue_focused_research", "continue_operability_validation"}:
        lines = [
            "The system should keep researching this area rather than treating the current candidate as deployable.",
            f"Current reason: {reason}.",
        ]
    elif action == "stopped":
        lines = [
            "The campaign was stopped by the operator.",
            f"Recorded reason: {reason}.",
        ]
    elif action in {"failed", "exhausted"}:
        lines = [
            "This branch should be treated as exhausted unless a new research idea justifies reopening it.",
            f"Recorded reason: {reason}.",
        ]
    else:
        lines = [f"The current campaign decision is {action}.", f"Recorded reason: {reason}."]
    return _paragraph_list(lines)


def _candidate_snapshot(
    row: dict[str, object] | None,
    stress_result: dict[str, object] | None,
    *,
    empty_message: str,
    is_control: bool = False,
) -> str:
    if not row:
        return f"<p>{escape(empty_message)}</p>"
    lines = [
        f"<p><strong>Run:</strong> <code>{escape(str(row.get('run_name', 'unknown')))}</code></p>",
        f"<p><strong>Profile:</strong> <code>{escape(str(row.get('profile_name', 'unknown')))}</code></p>",
        f"<p><strong>Validation excess return:</strong> {_percent(row.get('validation_excess_return'))}</p>",
        f"<p><strong>Holdout excess return:</strong> {_percent(row.get('holdout_excess_return'))}</p>",
        f"<p><strong>Walk-forward pass windows:</strong> {int(row.get('walkforward_pass_windows', 0) or 0)}</p>",
    ]
    if not is_control:
        lines.extend(
            [
                f"<p><strong>Eligible:</strong> {bool(row.get('eligible', False))}</p>",
                f"<p><strong>Rebalance days:</strong> {int(row.get('rebalance_frequency_days', 0) or 0)}</p>",
                f"<p><strong>Turnover limit:</strong> {_percent(row.get('max_rebalance_turnover_pct'))}</p>",
            ]
        )
    if stress_result is not None:
        lines.extend(
            [
                f"<p><strong>Stress ok:</strong> {bool(stress_result.get('stress_ok', False))}</p>",
                f"<p><strong>Stress scenarios non-broken:</strong> {int(stress_result.get('non_broken_count', 0) or 0)}/{int(stress_result.get('scenario_count', 0) or 0)}</p>",
            ]
        )
    return "".join(lines)


def _comparison_row(
    row: dict[str, object],
    *,
    is_control: bool,
    is_selected: bool,
    stress_result: dict[str, object] | None,
) -> str:
    role = "Control" if is_control else ("Selected candidate" if is_selected else "Shortlisted candidate")
    stress_text = "-"
    if stress_result is not None:
        stress_text = (
            f"{bool(stress_result.get('stress_ok', False))} "
            f"({int(stress_result.get('non_broken_count', 0) or 0)}/{int(stress_result.get('scenario_count', 0) or 0)})"
        )
    note = "Baseline for comparison" if is_control else _operator_note(row, stress_result, is_selected=is_selected)
    return (
        "<tr>"
        f"<td>{escape(role)}</td>"
        f"<td><code>{escape(str(row.get('run_name', 'unknown')))}</code></td>"
        f"<td><code>{escape(str(row.get('profile_name', 'unknown')))}</code></td>"
        f"<td>{_percent(row.get('validation_excess_return'))}</td>"
        f"<td>{_percent(row.get('holdout_excess_return'))}</td>"
        f"<td>{int(row.get('walkforward_pass_windows', 0) or 0)}</td>"
        f"<td>{_percent(row.get('max_rebalance_turnover_pct'))}</td>"
        f"<td>{int(row.get('rebalance_frequency_days', 0) or 0)}</td>"
        f"<td>{escape(stress_text)}</td>"
        f"<td>{escape(note)}</td>"
        "</tr>"
    )


def _operator_note(row: dict[str, object], stress_result: dict[str, object] | None, *, is_selected: bool) -> str:
    if is_selected and bool(row.get("eligible", False)) and stress_result is not None and bool(stress_result.get("stress_ok", False)):
        return "Best current candidate for review."
    if bool(row.get("eligible", False)):
        return "Passed promotion gates but still needs operator review."
    rejection_reason = str(row.get("rejection_reason", "") or "")
    if rejection_reason:
        return rejection_reason
    return "Shortlisted, but not yet strong enough to freeze."


def _operator_supporting_summary_row(label: str, summary: object) -> str:
    details = summary if isinstance(summary, dict) else {}
    if not details:
        return ""
    return (
        "<tr>"
        f"<td>{escape(label)}</td>"
        f"<td>{escape(str(details.get('classification', 'unknown')))}</td>"
        f"<td>{escape(str(details.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(details.get('recommended_action', 'unknown')))}</td>"
        f"<td>{escape(str(details.get('recorded_at_utc', '') or '-'))}</td>"
        "</tr>"
    )


def _paper_day_row(day: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(day.get('recorded_at_utc', '') or '-'))}</td>"
        f"<td>{escape(str(day.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(day.get('profile_name', '') or '-'))}</td>"
        f"<td>{escape(str(day.get('decision_date', '') or '-'))}</td>"
        f"<td>{escape(str(day.get('next_trade_date', '') or '-'))}</td>"
        f"<td>{escape(str(day.get('summary', '') or '-'))}</td>"
        "</tr>"
    )


def _paper_action_row(action: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(str(action.get('recorded_at_utc', '') or '-'))}</td>"
        f"<td>{escape(str(action.get('action', 'unknown')))}</td>"
        f"<td>{escape(str(action.get('actor', 'unknown')))}</td>"
        f"<td>{escape(str(action.get('day_id', '') or '-'))}</td>"
        f"<td>{escape(str(action.get('reason', '') or '-'))}</td>"
        "</tr>"
    )


def _candidate_progression_row(record: dict[str, object]) -> str:
    validation = _percent(record.get("validation_excess_return"))
    holdout = _percent(record.get("holdout_excess_return"))
    return (
        "<tr>"
        f"<td>{escape(str(record.get('profile_name', '') or '-'))}</td>"
        f"<td>{escape(str(record.get('source_type', '') or '-'))}</td>"
        f"<td>{_status_pill(str(record.get('recommendation_state', 'unknown')))}</td>"
        f"<td>{escape(str(record.get('validation_status', 'unknown')))} / {validation}</td>"
        f"<td>{escape(str(record.get('holdout_status', 'unknown')))} / {holdout}</td>"
        f"<td>{escape(str(int(record.get('walkforward_pass_windows', 0) or 0)))}</td>"
        f"<td>{escape(str(record.get('next_action', '') or '-'))}</td>"
        f"<td>{_timestamp_with_age(record.get('recorded_at_utc'))}</td>"
        "</tr>"
    )


def _research_program_row(program: dict[str, object]) -> str:
    queue_text = "enabled" if bool(program.get("queue_enabled", False)) else "not queued"
    summary_path = str(program.get("summary_path", "") or "")
    summary_html = f"<code>{escape(summary_path)}</code>" if summary_path else "-"
    reason = str(program.get("decision_summary", "") or program.get("retirement_reason", "") or "-")
    return (
        "<tr>"
        f"<td>{escape(str(program.get('title', '') or '-'))}</td>"
        f"<td>{_status_pill(str(program.get('status', 'unknown')))}</td>"
        f"<td>{escape(queue_text)}</td>"
        f"<td>{escape(str(program.get('focus_profile_name', '') or '-'))}</td>"
        f"<td>{escape(str(program.get('next_step', '') or '-'))}</td>"
        f"<td>{escape(reason)}</td>"
        f"<td>{_timestamp_with_age(program.get('recorded_at_utc'))}</td>"
        f"<td>{summary_html}</td>"
        "</tr>"
    )


def _campaign_scorecard_artifact_paths(campaign: dict[str, object]) -> dict[str, str]:
    return operability_artifact_paths(campaign.get("latest_report_path"))


def _scorecard_artifact_paths(paths: dict[str, str]) -> str:
    if not paths:
        return "<p class='subtle'>No scorecard artifact files have been written yet.</p>"
    return "".join(
        f"<p><strong>{escape(label.replace('_', ' '))}:</strong> <code>{escape(path)}</code></p>"
        for label, path in sorted(paths.items())
    )


def _scorecard_list(items: object, *, empty_message: str) -> str:
    values = [str(item) for item in items] if isinstance(items, list) else []
    if not values:
        return f"<p>{escape(empty_message)}</p>"
    joined = "".join(f"<li>{escape(item)}</li>" for item in values)
    return f"<ul>{joined}</ul>"


def _director_progress_text(queue: object) -> str:
    entries = [entry for entry in queue if isinstance(entry, dict)] if isinstance(queue, list) else []
    if not entries:
        return "0 / 0"
    finished = sum(1 for entry in entries if str(entry.get("status", "")) in {"completed", "exhausted", "failed", "stopped"})
    return f"{finished} / {len(entries)}"


def _recent_outcomes(items: object, *, limit: int = 6) -> list[dict[str, object]]:
    terminal_statuses = {"completed", "exhausted", "failed", "stopped"}
    candidates = [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("status", "")).lower() in terminal_statuses
    ] if isinstance(items, list) else []
    return sorted(candidates, key=lambda item: _timestamp_sort_key(item.get("updated_at")), reverse=True)[:limit]


def _recent_changes(
    campaigns: object,
    directors: object,
    notifications: object,
    *,
    limit: int = 8,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if isinstance(notifications, list):
        for record in notifications:
            if not isinstance(record, dict):
                continue
            items.append(
                {
                    "timestamp": record.get("recorded_at_utc"),
                    "source": "notification",
                    "message": str(record.get("message", "") or record.get("event_type", "notification")),
                }
            )
    if isinstance(campaigns, list):
        for campaign in campaigns:
            if not isinstance(campaign, dict):
                continue
            status = str(campaign.get("status", "")).lower()
            if status not in {"completed", "exhausted", "failed", "stopped"}:
                continue
            items.append(
                {
                    "timestamp": campaign.get("updated_at"),
                    "source": "campaign",
                    "message": (
                        f"{campaign.get('campaign_name', campaign.get('campaign_id', 'unknown campaign'))} "
                        f"is now {status}."
                    ),
                }
            )
    if isinstance(directors, list):
        for director in directors:
            if not isinstance(director, dict):
                continue
            status = str(director.get("status", "")).lower()
            if status not in {"completed", "exhausted", "failed", "stopped"}:
                continue
            items.append(
                {
                    "timestamp": director.get("updated_at"),
                    "source": "director",
                    "message": (
                        f"{director.get('director_name', director.get('director_id', 'unknown director'))} "
                        f"is now {status}."
                    ),
                }
            )
    return sorted(items, key=lambda item: _timestamp_sort_key(item.get("timestamp")), reverse=True)[:limit]


def _runtime_health(
    *,
    status: dict[str, object],
    campaigns: list[dict[str, object]],
    directors: list[dict[str, object]],
    next_family_status: dict[str, object] | None = None,
) -> dict[str, object]:
    counts = status.get("counts", {}) if isinstance(status.get("counts"), dict) else {}
    all_directors = [director for director in status.get("directors", []) if isinstance(director, dict)] if isinstance(status.get("directors"), list) else []
    workers = [worker for worker in status.get("workers", []) if isinstance(worker, dict)] if isinstance(status.get("workers"), list) else []
    jobs = [job for job in status.get("jobs", []) if isinstance(job, dict)] if isinstance(status.get("jobs"), list) else []
    service_heartbeats = [
        record
        for record in status.get("service_heartbeats", [])
        if isinstance(record, dict)
    ] if isinstance(status.get("service_heartbeats"), list) else []
    queued = int(counts.get("queued", 0) or 0)
    running = int(counts.get("running", 0) or 0)
    active_director_count = len(directors)
    most_recent_director = max(
        all_directors,
        key=lambda director: _timestamp_sort_key(director.get("updated_at") or director.get("created_at")),
        default=None,
    )
    most_recent_director_status = str(most_recent_director.get("status", "")).lower() if isinstance(most_recent_director, dict) else ""
    most_recent_director_name = (
        str(most_recent_director.get("director_name") or most_recent_director.get("director_id") or "unknown director")
        if isinstance(most_recent_director, dict)
        else "unknown director"
    )
    most_recent_director_age = (
        _age_seconds(most_recent_director.get("updated_at") or most_recent_director.get("created_at"))
        if isinstance(most_recent_director, dict)
        else None
    )
    director_requires_attention = active_director_count == 0 and most_recent_director_status in {"failed", "stopped"}
    active_worker_count = sum(
        1
        for worker in workers
        if str(worker.get("status", "")).lower() in {"running", "idle"}
    )
    stale_worker_count = sum(
        1
        for worker in workers
        if _age_seconds(worker.get("heartbeat_at") or worker.get("updated_at")) is not None
        and _age_seconds(worker.get("heartbeat_at") or worker.get("updated_at")) > 180
    )
    stale_running_job_count = sum(
        1
        for job in jobs
        if str(job.get("status", "")).lower() == "running"
        and (_age_seconds(job.get("updated_at")) or 0) > 900
    )
    oldest_running_job_age = max(
        (
            _age_seconds(job.get("updated_at")) or 0
            for job in jobs
            if str(job.get("status", "")).lower() == "running"
        ),
        default=0,
    )
    freshest_campaign_age = min(
        (
            _age_seconds(campaign.get("updated_at")) or 0
            for campaign in campaigns
        ),
        default=None,
    )
    degraded_services = [
        record
        for record in service_heartbeats
        if str(record.get("status", "")).lower() != "ok"
    ]
    next_family = next_family_status if isinstance(next_family_status, dict) else {}
    next_family_state = str(next_family.get("status", "")).lower()
    governance_blocked = next_family_state in {"blocked_pending_approval", "blocked_pending_bootstrap"}
    governance_message = str(next_family.get("message", "")).strip()
    governance_reason = str(next_family.get("blocking_reason", "")).strip()

    checks: list[dict[str, str]] = []
    checks.append(
        {
            "name": "service heartbeats",
            "status": "ok" if not degraded_services else "error",
            "detail": (
                "Coordinator, campaign manager, and research director heartbeats are fresh."
                if not degraded_services
                else "Degraded services: "
                + ", ".join(
                    f"{record.get('service')} ({record.get('status')})"
                    for record in degraded_services
                )
                + "."
            ),
        }
    )
    checks.append(
        {
            "name": "worker pool",
            "status": "ok" if active_worker_count > 0 else "error",
            "detail": (
                f"{active_worker_count} workers active."
                if active_worker_count > 0
                else "No active workers are reporting. Research cannot progress."
            ),
        }
    )
    checks.append(
        {
            "name": "worker heartbeats",
            "status": "ok" if stale_worker_count == 0 else "warning",
            "detail": (
                "All worker heartbeats are fresh."
                if stale_worker_count == 0
                else f"{stale_worker_count} worker records have stale heartbeats older than 3 minutes."
            ),
        }
    )
    checks.append(
        {
            "name": "job activity",
            "status": "ok" if running > 0 or queued > 0 else "warning",
            "detail": (
                f"{running} running and {queued} queued jobs."
                if running > 0 or queued > 0
                else "No queued or running jobs. The system is waiting for the next campaign decision or is idle."
            ),
        }
    )
    checks.append(
        {
            "name": "campaign activity",
            "status": (
                "ok"
                if campaigns and (freshest_campaign_age is None or freshest_campaign_age <= 900)
                else "warning"
            ),
            "detail": (
                f"{len(campaigns)} active campaign(s); most recent update {_format_age_seconds(freshest_campaign_age)}."
                if campaigns
                else "No active campaigns. The director may be idle, paused, or complete."
            ),
        }
    )
    checks.append(
        {
            "name": "director activity",
            "status": "ok" if active_director_count > 0 else "warning",
            "detail": (
                f"{active_director_count} active director(s)."
                if active_director_count > 0
                else (
                    f"No active directors. Most recent director {most_recent_director_name} "
                    f"{most_recent_director_status or 'finished'} {_format_age_seconds(most_recent_director_age)}."
                    if isinstance(most_recent_director, dict)
                    else "No active directors. Start a director to submit the next campaign."
                )
            ),
        }
    )
    if governance_blocked:
        checks.append(
            {
                "name": "queue governance",
                "status": "warning",
                "detail": (
                    f"{governance_message} {governance_reason}".strip()
                    if governance_message or governance_reason
                    else "The supervisor queue is intentionally blocked pending research-family governance."
                ),
            }
        )
    if running > 0:
        checks.append(
            {
                "name": "running job freshness",
                "status": "ok" if stale_running_job_count == 0 else "warning",
                "detail": (
                    f"{stale_running_job_count} running job(s) have not updated for more than 15 minutes; oldest update {_format_age_seconds(oldest_running_job_age)}."
                    if stale_running_job_count > 0
                    else "Running jobs are updating normally."
                ),
            }
        )

    overall = "healthy"
    summary = "Research runtime is healthy and actively progressing."
    if degraded_services:
        overall = "warning"
        summary = "Research runtime is degraded: one or more orchestration service heartbeats are stale."
    if active_worker_count == 0:
        overall = "critical"
        summary = "Research runtime is unhealthy: no workers are active."
    elif stale_running_job_count > 0:
        overall = "stalled"
        summary = "Research runtime looks stalled: jobs are marked running, but their progress signals are stale."
    elif stale_worker_count > 0 or oldest_running_job_age > 1800:
        overall = "warning"
        summary = "Research runtime is degraded: activity exists, but some signals look stale."
    elif running == 0 and queued == 0 and campaigns:
        overall = "warning"
        summary = "Research runtime is quiet: campaigns are active but no jobs are currently queued or running."
    elif director_requires_attention:
        overall = "warning"
        summary = (
            "Research runtime needs attention: no active directors remain after the latest director "
            f"{most_recent_director_status}."
        )
    elif governance_blocked and running == 0 and queued == 0 and not campaigns and not directors:
        overall = "blocked"
        summary = (
            f"Research runtime is intentionally blocked: {governance_message}"
            if governance_message
            else "Research runtime is intentionally blocked pending research-family governance."
        )
    elif running == 0 and queued == 0 and not campaigns and not directors:
        overall = "idle"
        summary = "Research runtime is idle: there is no active director, active campaign, or queued work."
    return {"status": overall, "summary": summary, "checks": checks}


def _timestamp_sort_key(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).timestamp()


def _paragraph_list(lines: list[str]) -> str:
    return "".join(f"<p>{escape(line)}</p>" for line in lines)


def _percent(value: object) -> str:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    return f"{numeric:.2%}"


def _status_pill(value: str) -> str:
    lowered = value.lower()
    css = ""
    if lowered in {"failed", "campaign_failed", "stopped", "error", "missing"}:
        css = " danger"
    elif lowered.startswith("blocked") or lowered in {"queued", "warn", "stage_submitted", "warning", "stale", "retired"}:
        css = " warn"
    return f"<span class='pill{css}'>{escape(value)}</span>"


def _timestamp_with_age(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    age = _format_age_label(value)
    if age is None:
        return escape(text)
    return f"{escape(text)} <span class='subtle'>({escape(age)})</span>"


def _format_age_label(value: object) -> str | None:
    delta_seconds = _age_seconds(value)
    return _format_age_label_from_seconds(delta_seconds)


def _format_age_label_from_seconds(delta_seconds: int | None) -> str | None:
    if delta_seconds is None:
        return None
    if delta_seconds < 60:
        return f"{delta_seconds}s ago"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m ago"
    if delta_seconds < 86400:
        return f"{delta_seconds // 3600}h ago"
    return f"{delta_seconds // 86400}d ago"


def _format_age_seconds(delta_seconds: int | None) -> str:
    return _format_age_label_from_seconds(delta_seconds) or "at an unknown time"


def _csrf_hidden_input(csrf_token: str | None) -> str:
    value = escape(str(csrf_token or ""))
    return f'<input type="hidden" name="csrf_token" value="{value}">'


def _csrf_cookie_header(csrf_token: str) -> str:
    return f"trotters_csrf={csrf_token}; Path=/; SameSite=Strict; HttpOnly"


def _age_seconds(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(int((_utc_now() - timestamp.astimezone(UTC)).total_seconds()), 0)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _stop_form(campaign_id: str, *, csrf_token: str | None) -> str:
    return f"""
    <form class="inline" action="/campaigns/{quote(campaign_id)}/stop" method="post">
      {_csrf_hidden_input(csrf_token)}
      <input type="text" name="reason" value="dashboard_stop" aria-label="Stop reason">
      <button class="button danger" type="submit">Stop Campaign</button>
    </form>
    """


def _director_controls(director: dict[str, object], queue: list[dict[str, object]], *, csrf_token: str | None) -> str:
    director_id = str(director.get("director_id", ""))
    status = str(director.get("status", "unknown"))
    has_pending = _next_pending_director_entry(queue) is not None
    parts: list[str] = []
    if status in {"running", "queued"}:
        parts.append(
            _director_control_form(
                director_id,
                "pause",
                "operator_pause",
                "Pause Director",
                button_class="danger",
                csrf_token=csrf_token,
            )
        )
    if status == "paused":
        parts.append(
            _director_control_form(
                director_id,
                "resume",
                "operator_resume",
                "Resume Director",
                csrf_token=csrf_token,
            )
        )
    if status in {"running", "queued", "paused"} and has_pending:
        parts.append(
            _director_control_form(
                director_id,
                "skip-next",
                "operator_skip",
                "Skip Next Campaign",
                button_class="secondary",
                csrf_token=csrf_token,
            )
        )
    if not parts:
        return "<p class='subtle'>No director controls are available in the current state.</p>"
    return "".join(parts)


def _director_control_form(
    director_id: str,
    action: str,
    default_reason: str,
    label: str,
    *,
    button_class: str = "",
    csrf_token: str | None,
) -> str:
    class_name = "button"
    if button_class:
        class_name += f" {button_class}"
    return f"""
    <form class="inline" action="/directors/{quote(director_id)}/{action}" method="post">
      {_csrf_hidden_input(csrf_token)}
      <input type="text" name="reason" value="{escape(default_reason)}" aria-label="{escape(label)} reason">
      <button class="{class_name}" type="submit">{escape(label)}</button>
    </form>
    """


def _next_pending_director_entry(queue: list[dict[str, object]]) -> dict[str, object] | None:
    for entry in queue:
        if str(entry.get("status", "")) == "pending":
            return entry
    return None


def _flash_banner(message: str | None) -> str:
    if not message:
        return ""
    return f"<div class='flash'>{escape(message)}</div>"


def _notification_banner(
    notifications: object,
    *,
    campaigns: object | None = None,
    directors: object | None = None,
) -> str:
    if not isinstance(notifications, list):
        return ""
    active_campaign_ids = {
        str(campaign.get("campaign_id", ""))
        for campaign in campaigns
        if isinstance(campaign, dict) and str(campaign.get("campaign_id", ""))
    } if isinstance(campaigns, list) else set()
    has_active_work = bool(active_campaign_ids) or any(
        isinstance(director, dict) and str(director.get("status", "")).lower() in {"queued", "running", "paused"}
        for director in directors
    ) if isinstance(directors, list) else bool(active_campaign_ids)
    record = next(
        (
            entry
            for entry in notifications
            if _should_show_notification_banner(
                entry,
                active_campaign_ids=active_campaign_ids,
                has_active_work=has_active_work,
            )
        ),
        None,
    )
    if not isinstance(record, dict):
        return ""
    severity = str(record.get("severity", "info")).lower()
    event_type = str(record.get("event_type", "notification"))
    campaign_name = str(record.get("campaign_name", "unknown campaign"))
    if event_type == "strategy_promoted":
        message = (
            f"Strategy promoted: {campaign_name} produced a frozen candidate for human review. "
            "The next step is paper-trading review, not live trading."
        )
    elif event_type == "campaign_failed":
        message = f"Campaign failed: {campaign_name} needs investigation before this branch is reused."
    elif event_type == "campaign_stopped":
        message = f"Campaign stopped: {campaign_name} will not advance until you restart or replace it."
    elif event_type == "campaign_finished" and severity == "warning":
        message = f"Campaign exhausted: {campaign_name} did not find a viable strategy in this branch."
    else:
        message = str(record.get("message", "") or event_type)
    return _alert_banner(message, severity)


def _catalog_status_banner(catalog_status: dict[str, object]) -> str:
    if bool(catalog_status.get("available", False)):
        return ""
    path = str(catalog_status.get("catalog_jsonl", "") or "runtime/catalog/research_catalog/catalog.jsonl")
    return _alert_banner(
        (
            "Catalog snapshot not available yet. Live runtime panels still work, "
            f"but portfolio and promotion sections will stay empty until the first catalog export is written to {path}."
        ),
        "warning",
    )


def _should_show_notification_banner(
    record: object,
    *,
    active_campaign_ids: set[str],
    has_active_work: bool,
) -> bool:
    if not isinstance(record, dict):
        return False
    severity = str(record.get("severity", "info")).lower()
    if severity not in {"success", "warning", "error"}:
        return False
    event_type = str(record.get("event_type", "notification")).lower()
    campaign_id = str(record.get("campaign_id", ""))
    if not has_active_work:
        return True
    if event_type in {"campaign_stopped", "campaign_failed"}:
        return campaign_id in active_campaign_ids
    if event_type == "campaign_finished" and severity == "warning":
        return campaign_id in active_campaign_ids
    return True


def _campaign_state_banner(campaign: dict[str, object], state: dict[str, object]) -> str:
    final_decision = state.get("final_decision", {}) if isinstance(state.get("final_decision"), dict) else {}
    action = str(final_decision.get("recommended_action", "") or campaign.get("status", "")).lower()
    campaign_name = str(campaign.get("campaign_name", "This campaign"))
    if action == "freeze_candidate":
        return _alert_banner(
            f"{campaign_name} has promoted a strategy and frozen it for operator review. Move to paper-trading review, not live deployment.",
            "success",
        )
    if action in {"exhausted"}:
        return _alert_banner(
            f"{campaign_name} exhausted its search path without producing a viable strategy. Treat this branch as finished unless you open a new idea.",
            "warning",
        )
    if action in {"failed"}:
        return _alert_banner(
            f"{campaign_name} failed and needs investigation before it should be trusted again.",
            "error",
        )
    if action in {"stopped"}:
        return _alert_banner(
            f"{campaign_name} was stopped by the operator and will not advance further.",
            "warning",
        )
    return ""


def _alert_banner(message: str, severity: str) -> str:
    css = _severity_class(severity)
    return f"<div class='flash {css}'>{escape(message)}</div>"


def _severity_pill(value: str) -> str:
    css = _severity_class(value)
    return f"<span class='pill {css}'>{escape(value)}</span>"


def _severity_class(value: str) -> str:
    lowered = value.lower()
    if lowered in {"error", "failed", "danger"}:
        return "danger"
    if lowered in {"warning", "warn", "stopped", "exhausted"}:
        return "warn"
    if lowered in {"success", "completed", "promoted"}:
        return "success"
    return "info"


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]
