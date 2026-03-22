# Phase 10 Task List

## Purpose

This file is now the phase-level index for Phase 10.

Detailed active planning lives under `feature_workflows/`.
Use this file to understand what Phase 10 has already delivered, what is still open, and which workflow should move next.

## Already Delivered In Phase 10

The repo already has these Phase 10 foundations in place:

- promotion handoff pages and candidate scorecards
- candidate comparison and operator recommendation surfaces
- director plan files plus pause/resume/skip controls
- dashboard history, notification severity, and operator summaries
- paper-trade decision export and readiness review artifacts
- OpenClaw runtime supervisor, specialist agents, summaries, and dispatch telemetry
- a basic GitHub Actions test workflow

## Active Workflow Queue

Use these workflow folders as the real source of active execution detail:

1. `FW-001_docs-and-planning-sync`
   Status: `done`
2. `FW-002_candidate-handoff-and-dashboard`
   Status: `ready`
3. `FW-003_paper-trading-rehearsal-core`
   Status: `ready`
4. `FW-004_openclaw-trust-hardening`
   Status: `ready`
5. `FW-005_risk-sector-promotion-program`
   Status: `ready`

## Execution Rules

For every workflow:

1. complete one logical change set at a time
2. run the relevant repo checks and live app-status checks
3. keep cleanup tied to the feature that benefits from it
4. update the workflow files as implementation reality changes
5. only merge durable lessons back into `context/` after the workflow has actually taught us something stable

## Phase 10 Done Criteria

Phase 10 should be considered complete only when all of these are true:

- the current best candidate and next operator action are obvious in the dashboard and API
- paper-trading rehearsal has separate state, a daily runner, hard blocking, and operator decision logging
- OpenClaw repeated-incident behavior and trust hygiene are hardened further
- the strongest `risk + sector` branch is either promoted under the current policy or explicitly retired with evidence

## Deferred Until Later

Keep these out of the current phase unless priorities change:

- broker integration
- live order routing
- real-money execution
- broad autonomous live-trading control
- a large refactor-only program detached from feature work
- CI hardening beyond the current basic test workflow
