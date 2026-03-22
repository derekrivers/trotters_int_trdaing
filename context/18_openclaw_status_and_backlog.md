# OpenClaw Status And Backlog

## Purpose

Keep one current note for the OpenClaw control-plane work: what is implemented, what lessons are already captured elsewhere, and what still remains on the backlog.

This replaces older transitional planning notes whose contents are now either implemented or superseded.

## Current State

The following pieces are implemented in the repo and runtime:

- `research-api` exposes runtime status, directors, campaigns, jobs, artifacts, notifications, summaries, and dispatch telemetry
- `ops-bridge` exists as a narrow internal control plane for allowlisted restarts and agent dispatches
- the OpenClaw gateway loads the repo-managed `trotters-runtime` plugin with explicit trusted plugin config in `runtime/openclaw/openclaw.json`
- `runtime-supervisor` runs as the always-on operator
- `research-triage`, `candidate-review`, `paper-trade-readiness`, and `failure-postmortem` exist as event-driven specialist agents
- the gateway bootstrap keeps exactly one supervisor cron job, stages a bootstrap-safe config before plugin install, then reapplies the final trusted plugin config, and seeds minimal supervisor workspace files
- supervisor behavior now has deterministic drill coverage for healthy-active, active-degraded, repeated degraded cooldown, idle-after-exhausted, stale exhausted idle, and failed-idle scenarios
- repeated degraded incidents now emit stable fingerprints and cooldown state so the supervisor can suppress restart/escalation churn deterministically
- dispatch telemetry and agent summaries are surfaced in the dashboard and API

## Where The Stable Documentation Now Lives

Use these files for durable OpenClaw context:

- `20_openclaw_lessons_learned.md` for mistakes, gotchas, and operational lessons
- `21_openclaw_agent_guide.md` for the current agent set and responsibilities

This file should stay focused on current status and backlog, not repeat the full guide.

## What Is No Longer A Blocker

The following items were earlier planning concerns and are now implemented:

- local agent control API
- `ops-bridge`
- plugin and bootstrap regression coverage
- specialist trigger chain for candidate review and paper-trade readiness
- dashboard visibility for summaries and dispatch telemetry
- duplicate active directors and duplicate active director campaigns
- supervisor auth and low-cost OpenAI model activation
- repeated degraded-cycle cooldowns in the supervisor decision path
- explicit OpenClaw plugin trust configuration for the custom runtime plugin

## Remaining Backlog

### 1. Longer Running Live Supervisor Drills

The current drill harness covers the main decision classes, but we still do not have long-running overnight or multi-incident live rehearsals that prove behavior over time rather than in single-turn snapshots.

### 2. Stronger Service-Action Cooldowns Below The Supervisor Layer

The supervisor now cools down repeated incidents clearly, but the lower restart/control path could still be tightened further if we want service actions themselves to carry stronger incident-aware cooldown semantics.

### 3. Better Summary Quality From Specialist Agents

The runtime now normalizes missing recommended actions, but the content quality of specialist summaries can still improve so the operator sees less generic evidence and stronger next-step recommendations.

### 4. Better Operator Views For Candidate Progression

The dashboard now shows agent summaries and dispatches, but the path from candidate emergence to paper-trade readiness could still be clearer for a non-developer operator.

## Maintenance Rule

If a future OpenClaw note is only a temporary task list or rollout checklist, prefer updating this file or a tracked issue instead of creating another long-lived context document.
