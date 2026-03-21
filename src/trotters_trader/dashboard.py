from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
import json
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode
from wsgiref.simple_server import make_server

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
from trotters_trader.reports import build_operability_scorecard


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
        return {
            "status": status,
            "active_directors": active_directors,
            "active_campaigns": active_campaigns,
            "notifications": _load_notifications(self._paths, limit=25),
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
    def __init__(self, controller: DashboardController, *, refresh_seconds: int = 10) -> None:
        self._controller = controller
        self._refresh_seconds = refresh_seconds

    def __call__(self, environ: dict[str, object], start_response: Callable[[str, list[tuple[str, str]]], None]):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        body = _read_body(environ)

        try:
            response = self.handle_request(method, path, query, body)
        except ValueError as exc:
            response = self._html_response(
                "400 Bad Request",
                _render_layout(
                    "Dashboard Error",
                    f"<section class='panel'><h1>Bad Request</h1><p>{escape(str(exc))}</p></section>",
                    refresh_seconds=0,
                ),
            )
        start_response(response.status, response.headers)
        return [response.body]

    def handle_request(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]],
        body: bytes,
    ) -> DashboardResponse:
        if method == "GET" and path == "/healthz":
            return DashboardResponse("200 OK", [("Content-Type", "text/plain; charset=utf-8")], b"ok")
        if method == "GET" and path == "/guide":
            return self._html_response("200 OK", _render_guide(refresh_seconds=0))
        if method == "GET" and path == "/":
            payload = self._controller.overview()
            html = _render_overview(payload, refresh_seconds=self._refresh_seconds, flash=_query_value(query, "flash"))
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


def serve_dashboard(
    paths: ResearchRuntimePaths,
    *,
    host: str = "0.0.0.0",
    port: int = 8888,
    refresh_seconds: int = 10,
) -> dict[str, object]:
    app = DashboardApp(DashboardController(paths), refresh_seconds=refresh_seconds)
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


def _render_overview(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
    status = payload.get("status", {}) if isinstance(payload.get("status"), dict) else {}
    counts = status.get("counts", {}) if isinstance(status.get("counts"), dict) else {}
    workers = status.get("workers", []) if isinstance(status.get("workers"), list) else []
    jobs = status.get("jobs", []) if isinstance(status.get("jobs"), list) else []
    directors = payload.get("active_directors", []) if isinstance(payload.get("active_directors"), list) else []
    campaigns = payload.get("active_campaigns", []) if isinstance(payload.get("active_campaigns"), list) else []
    notifications = payload.get("notifications", []) if isinstance(payload.get("notifications"), list) else []

    summary_cards = "".join(
        _summary_card(label, str(counts.get(label, 0)))
        for label in ("queued", "running", "completed", "failed", "cancelled")
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
        "<tr><td colspan='5'>No notifications yet</td></tr>"
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
    <section class="summary-grid">{summary_cards}</section>
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
          <thead><tr><th>Time</th><th>Event</th><th>Campaign</th><th>Message</th><th>Hook</th></tr></thead>
          <tbody>{notification_rows}</tbody>
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


def _render_campaign_detail(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
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
        {_stop_form(str(campaign.get("campaign_id", ""))) if can_stop else "<p>This campaign is not active.</p>"}
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


def _render_director_detail(payload: dict[str, object], *, refresh_seconds: int, flash: str | None) -> str:
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
    controls = _director_controls(director, queue)

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
        <p>Success does not mean “best looking line on a chart.” It means the system found a candidate strong enough to freeze as a serious strategy proposal.</p>
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


def _summary_card(label: str, value: str) -> str:
    return f"<section class='card'><h2>{escape(label)}</h2><div class='metric'>{escape(value)}</div></section>"


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
        f"<td>{_status_pill(str(record.get('event_type', 'notification')))}</td>"
        f"<td>{campaign_link}</td>"
        f"<td>{escape(str(record.get('message', '')))}</td>"
        f"<td><span class='pill{hook_class}'>{escape(hook_text)}</span></td>"
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


def _campaign_scorecard_artifact_paths(campaign: dict[str, object]) -> dict[str, str]:
    latest_report_path = str(campaign.get("latest_report_path") or "")
    if not latest_report_path:
        return {}
    report_dir = Path(latest_report_path).parent
    paths = {
        "scorecard_md": report_dir / "operator_scorecard.md",
        "scorecard_json": report_dir / "operator_scorecard.json",
        "comparison_md": report_dir / "candidate_comparison.md",
    }
    return {key: str(path) for key, path in paths.items() if path.exists()}


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
    if lowered in {"failed", "campaign_failed", "stopped"}:
        css = " danger"
    elif lowered in {"queued", "warn", "stage_submitted"}:
        css = " warn"
    return f"<span class='pill{css}'>{escape(value)}</span>"


def _timestamp_with_age(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return escape(text)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    delta_seconds = max(int((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()), 0)
    if delta_seconds < 60:
        age = f"{delta_seconds}s ago"
    elif delta_seconds < 3600:
        age = f"{delta_seconds // 60}m ago"
    elif delta_seconds < 86400:
        age = f"{delta_seconds // 3600}h ago"
    else:
        age = f"{delta_seconds // 86400}d ago"
    return f"{escape(text)} <span class='subtle'>({escape(age)})</span>"


def _stop_form(campaign_id: str) -> str:
    return f"""
    <form class="inline" action="/campaigns/{quote(campaign_id)}/stop" method="post">
      <input type="text" name="reason" value="dashboard_stop" aria-label="Stop reason">
      <button class="button danger" type="submit">Stop Campaign</button>
    </form>
    """


def _director_controls(director: dict[str, object], queue: list[dict[str, object]]) -> str:
    director_id = str(director.get("director_id", ""))
    status = str(director.get("status", "unknown"))
    has_pending = _next_pending_director_entry(queue) is not None
    parts: list[str] = []
    if status in {"running", "queued"}:
        parts.append(_director_control_form(director_id, "pause", "operator_pause", "Pause Director", button_class="danger"))
    if status == "paused":
        parts.append(_director_control_form(director_id, "resume", "operator_resume", "Resume Director"))
    if status in {"running", "queued", "paused"} and has_pending:
        parts.append(_director_control_form(director_id, "skip-next", "operator_skip", "Skip Next Campaign", button_class="secondary"))
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
) -> str:
    class_name = "button"
    if button_class:
        class_name += f" {button_class}"
    return f"""
    <form class="inline" action="/directors/{quote(director_id)}/{action}" method="post">
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


def _query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]
