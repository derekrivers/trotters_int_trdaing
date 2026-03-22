# Runtime Agent API Plan

## Goal

Add a local control API so an agent can operate the research runtime without relying on shell commands or direct database access.

The API should let an agent:

- inspect runtime health
- inspect active and historical directors and campaigns
- start and stop directors and campaigns
- pause, resume, and skip director queue entries
- consume machine-readable status instead of scraping the dashboard

## Current State

The project already has most of the domain operations implemented:

- runtime status snapshots in `src/trotters_trader/research_runtime.py`
- director and campaign control functions in `src/trotters_trader/research_runtime.py`
- a dashboard with a small JSON surface in `src/trotters_trader/dashboard.py`
- a CLI entrypoint in `src/trotters_trader/cli.py`

What is missing is a dedicated JSON-only control plane that an external agent can call safely and consistently.

## Recommended Boundary

Split control into two layers:

1. `research-api`
   Exposes typed runtime operations only.

2. `ops-bridge`
   Optional later service for narrow Docker or host actions such as restarting services.

For the first implementation, only ship `research-api`.

## API v1 Scope

### Step 1: Read-only

- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/runtime/overview`
- `GET /api/v1/directors`
- `GET /api/v1/directors/{director_id}`
- `GET /api/v1/campaigns`
- `GET /api/v1/campaigns/{campaign_id}`

### Step 2: Director and Campaign Control

- `POST /api/v1/directors`
- `POST /api/v1/directors/{director_id}/pause`
- `POST /api/v1/directors/{director_id}/resume`
- `POST /api/v1/directors/{director_id}/skip-next`
- `POST /api/v1/directors/{director_id}/stop`
- `POST /api/v1/campaigns`
- `POST /api/v1/campaigns/{campaign_id}/stop`

## Input Rules

Do not accept arbitrary absolute filesystem paths from API callers.

For v1:

- campaign configs must be repo-relative files under `configs/` and end in `.toml`
- director plans must be repo-relative files under `configs/directors/` and end in `.json`

This is not a complete allowlist yet, but it is a safer boundary than raw path passthrough.

## Deployment Shape

Add a new Compose service:

- service name: `research-api`
- port: `8890`
- runtime root: `/runtime/research_runtime`
- catalog output: `/runtime/catalog`

The service should share the same runtime volume and catalog mount as the existing runtime services.

## OpenClaw Integration

OpenClaw should sit beside the runtime services and call only `research-api`.

Recommended environment variables:

- `TROTTERS_API_BASE=http://research-api:8890`
- `TROTTERS_API_TOKEN=<later phase>`

Do not give OpenClaw direct Docker socket access in the first integration.

## Deferred Work

The following should come after the first API slice:

- job log endpoints
- artifact and notification endpoints beyond the overview payload
- bearer token authentication
- audit logging for API mutations
- optional `ops-bridge` for restarting services
- OpenClaw plugin or typed tool wrapper over the API

## Sources

- OpenClaw overview: <https://docs.openclaw.ai/>
- OpenClaw gateway model and local dashboard defaults: <https://docs.openclaw.ai/>
