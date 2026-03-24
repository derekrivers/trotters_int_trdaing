# Context

## Problem

- the runtime hot path still serializes too many SQLite writes for comfortable high worker counts, especially around heartbeats, lease churn, and coordinator export work
- the overview dashboard has accumulated enough sections that first-screen operator signal is diluted by repeated outcome feeds, agent internals, and job-level noise

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/18_openclaw_status_and_backlog.md`
- `context/21_openclaw_agent_guide.md`
- `context/22_tech_stack_and_runtime_brief.md`

## Current Behavior

- runtime workers, coordinator, dashboard, and API all share one SQLite-backed control plane
- the runtime already uses WAL mode and lock-retry writes, but workers still write liveness and lease state frequently under contention
- the dashboard overview renders nearly every operator and diagnostic panel on one page

## Non-Goals

- no replacement of SQLite with Postgres, Redis, or another control-plane store
- no dashboard frontend rewrite or new UI framework
- no public API contract redesign
