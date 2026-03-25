# Context

## Problem

- the Compose runtime reached the practical coordination ceiling of SQLite under concurrent worker and coordinator startup, with real `database is locked` failures escaping into runtime logs and downstream review agents
- the codebase still treats the runtime state store as an implementation detail inside `research_runtime.py`, which makes future scaling, observability, and service-boundary work harder to plan cleanly

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/22_tech_stack_and_runtime_brief.md`

## Current Behavior

- the runtime remains local-first and Compose-centric, but the orchestration database is now the main architecture bottleneck rather than missing product features
- the filesystem-backed research catalog, notifications, paper-trading artifacts, and promotion-path summaries are still working well enough to keep in place for this workflow
- API, dashboard, and OpenClaw operator flows already rely on stable runtime contracts, so the DB migration must preserve those read/write shapes
- SQLite remains the safe live default until a dedicated state-migration workflow exists; Postgres is introduced here as the chosen next backend and a verified opt-in path

## Non-Goals

- do not rewrite the dashboard or API into a new web framework in this workflow
- do not replace the filesystem-backed catalog and artifact model in this workflow
- do not force an implicit live cutover from SQLite to Postgres before migration and rollback behavior are designed explicitly
- do not introduce a cloud deployment target, broker integration, or a broad refactor-only program detached from a concrete runtime deliverable