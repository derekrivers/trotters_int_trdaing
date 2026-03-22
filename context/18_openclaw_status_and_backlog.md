# OpenClaw Status And Backlog

## Purpose

Keep one current note for the OpenClaw control-plane work: what is implemented, what lessons are already captured elsewhere, and what still remains on the backlog.

This replaces older transitional planning notes whose contents are now either implemented or superseded.

## Current State

The following pieces are implemented in the repo and runtime:

- `research-api` exposes runtime status, directors, campaigns, jobs, artifacts, notifications, summaries, and dispatch telemetry
- `ops-bridge` exists as a narrow internal control plane for allowlisted restarts and agent dispatches
- the OpenClaw gateway loads the repo-managed `trotters-runtime` plugin
- `runtime-supervisor` runs as the always-on operator
- `research-triage`, `candidate-review`, `paper-trade-readiness`, and `failure-postmortem` exist as event-driven specialist agents
- the gateway bootstrap keeps exactly one supervisor cron job and now seeds minimal supervisor workspace files
- supervisor behavior has deterministic drill coverage for healthy-active, active-degraded, idle-after-exhausted, and failed-idle scenarios
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

## Remaining Backlog

### 1. Broader Supervisor Trust Drills

The current drill coverage is useful, but trust should be extended further with more end-to-end runtime scenarios, especially repeated degraded cycles and overnight behavior.

### 2. Stronger Service-Action Cooldowns

Restart limits exist, but service-health recovery policy can still be tightened around repeated incidents and clearer incident fingerprinting.

### 3. Better Summary Quality From Specialist Agents

The runtime now tolerates drift in summary calls, but the quality of the specialist output should keep improving so the summaries become more decision-ready and less generic.

### 4. Better Operator Views For Candidate Progression

The dashboard now shows agent summaries and dispatches, but the path from candidate emergence to paper-trade readiness could still be clearer for a non-developer operator.

### 5. Explicit OpenClaw Plugin Trust Configuration

The gateway still warns that `plugins.allow` is empty. The plugin is loading correctly, but production hygiene would be better with an explicit allowlist.

## Maintenance Rule

If a future OpenClaw note is only a temporary task list or rollout checklist, prefer updating this file or a tracked issue instead of creating another long-lived context document.
