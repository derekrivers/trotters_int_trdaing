# OpenClaw Iteration 2 Task List

## Goal

Turn the current OpenClaw setup from a working integration into a trusted low-cost operator layer for autonomous research and paper-trade preparation.

This task list is intentionally large and operational. It is meant to drive the next implementation pass end to end, not just describe ideas.

## Current Baseline

Already in place:
- one always-on `runtime-supervisor`
- event-driven `research-triage`, `candidate-review`, `paper-trade-readiness`, and `failure-postmortem`
- compact `trotters_*` plugin tools
- durable agent summary artifacts
- `ops-bridge` dispatch path into `openclaw-gateway`
- GitHub Actions test workflow for the Docker test suite

Main remaining gaps:
- no full supervisor drill harness for decision trust
- candidate and paper-trade agents are not fully wired into the automatic trigger chain
- operator visibility is still summary-panel level rather than decision-panel level
- duplicate/cooldown protection is still incomplete outside existing summary dedupe and service restart limits
- agent cost telemetry is not yet persisted as a first-class operator artifact

## Phase 1. Task List Foundation

### 1.1 Create a tracked task list
- write this note into `context/`
- index it from `context/README.md`

Acceptance:
- the note exists in the repo
- the note is discoverable from the context index

## Phase 2. Supervisor Trust And Drill Coverage

### 2.1 Add a supervisor drill harness
Implement controlled drill coverage for:
- healthy active runtime -> no action
- idle runtime after exhausted -> start next approved runbook item
- failed campaign -> investigate before acting
- service-health fault -> narrow restart or escalation only

Possible implementation surfaces:
- expand `tests/test_openclaw_supervisor_integration.py`
- add deterministic fixtures around runtime overview, runbook, and tool results
- validate resulting summaries, history records, and allowed mutations

Acceptance:
- drill coverage exists for all four cases
- failures are actionable and not UI-only

### 2.2 Add overnight-safety regression checks
- verify one cron job only
- verify repeated degraded cycles do not create repeated restart loops
- verify duplicate active directors are still prevented

Acceptance:
- supervisor can be trusted not to churn on simple repeat states

## Phase 3. Complete Specialist Trigger Chain

### 3.1 Trigger `candidate-review` on promoted/frozen candidate outcomes
- use `strategy_promoted` or equivalent freeze-candidate signals
- dispatch a compact candidate review job automatically
- persist `candidate_readiness_summary`

Acceptance:
- a promoted/frozen candidate creates a candidate readiness summary without manual intervention

### 3.2 Trigger `paper-trade-readiness` for the strongest candidate
- provide a daily or explicit manual trigger path
- persist `paper_trade_readiness_summary`
- keep it read-only and focused on freshness plus operator warnings

Acceptance:
- the system can produce a current paper-trade readiness note for the best candidate

### 3.3 Enrich `failure-postmortem` when compact evidence is insufficient
- keep compact pack first
- optionally include a narrow failed-job log slice only when required

Acceptance:
- postmortem summaries are evidence-led without exploding token usage

## Phase 4. Operator Visibility

### 4.1 Upgrade dashboard summary visibility
Add explicit sections for:
- latest supervisor incident
- latest campaign triage
- latest candidate readiness
- latest paper-trade readiness
- latest failure postmortem

Each section should show:
- status
- classification
- recommended action
- recorded timestamp
- linked campaign/profile/director context when present
- artifact references when present

Acceptance:
- operators can understand current agent conclusions without opening raw JSON files

### 4.2 Expose telemetry and summary history via API
- add API access for recent agent dispatch telemetry
- keep summary history queryable with useful filters

Acceptance:
- operator surfaces and tests can consume the data without scraping files directly

## Phase 5. Cooldowns, Dedupe, And Safety

### 5.1 Add dispatch-level duplicate suppression
- avoid re-running the same specialist agent for the same event/fingerprint inside a cooldown window
- keep summary dedupe as a second layer, not the only layer

Acceptance:
- repeated identical notifications do not cause repeated dispatch storms

### 5.2 Add stronger service-action cooldowns
- keep restart actions tied to incident context
- prevent repeated restart attempts for the same service-health fingerprint inside a short window

Acceptance:
- confirmed faults can be remediated once
- noisy loops do not keep restarting the same service

## Phase 6. Agent Cost Telemetry

### 6.1 Persist dispatch telemetry
Record for each dispatched specialist run:
- agent id
- event type
- campaign id / profile context if available
- provider
- model
- prompt/input/output tokens if present
- duration
- success/failure
- recorded timestamp

Suggested storage:
- `runtime/catalog/agent_telemetry/`

Acceptance:
- telemetry survives past a single log line
- the operator can see which agents are cheap and which are drifting upward in cost

### 6.2 Surface a compact telemetry view
- recent dispatches
- total prompt/input/output counts over the recent window
- worst offenders by cost/duration

Acceptance:
- low-cost claims are measurable

## Phase 7. Verification And Operational Check

### 7.1 Run targeted automated verification after each change cluster
Minimum checks:
- `node extensions/openclaw/trotters-runtime/index.test.js`
- targeted Python unittest modules for touched runtime/api/dashboard files
- any new integration harness coverage

### 7.2 Run live stack verification
Minimum checks:
- `docker compose ps`
- recent `openclaw-gateway` logs
- latest summary artifacts
- latest telemetry artifacts
- dashboard/API paths still render correctly

### 7.3 Hunt regressions before stopping
- worker count and queue health
- duplicate directors
- missing plugin/skill load
- summary write failures
- broken dashboard/API pages

Acceptance:
- the stack is not just passing tests; it is operationally coherent after the change set

## Proposed Build Order

1. Create and index this task list
2. Complete candidate-review and paper-trade trigger flow
3. Add dispatch telemetry persistence
4. Upgrade dashboard/API visibility for summaries and telemetry
5. Add dispatch cooldown and duplicate suppression
6. Add supervisor drill harness coverage
7. Run full targeted verification and live runtime checks
8. Commit grouped changes

## Definition Of Done

This iteration is complete when:
- promoted candidates automatically produce readiness summaries
- paper-trade readiness can be generated without manual repo spelunking
- telemetry shows what agent runs are costing
- the dashboard exposes useful agent conclusions and recent dispatches
- dispatch/restart churn is controlled by cooldowns
- supervisor decision behavior has deterministic drill coverage
- the live stack remains healthy after rollout
