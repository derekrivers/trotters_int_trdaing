# OpenClaw Agent Guide

## Purpose

Describe the OpenClaw setup currently implemented for the Trotters runtime, the agents we created, and the role each one plays.

This guide is about the system as it exists in the repo now. It is not a future-state wishlist.

## Where The OpenClaw System Lives

Primary repo-managed control points:
- `configs/openclaw/openclaw.json`
- `extensions/openclaw/trotters-runtime`
- `scripts/openclaw/runtime-supervisor-message.txt`
- `scripts/openclaw/start-openclaw.sh`

Runtime state is then materialized under OpenClaw state directories such as:
- `runtime/openclaw/*`
- `runtime/openclaw/workspaces/*`

## High-Level Design

The current design is intentionally conservative.

Principles:
- one always-on operator only
- specialist agents are event-driven, not always-on
- runtime mutation is tightly constrained
- summary artifacts are persisted so later agents do not need to re-derive the same conclusions
- all agents default to the cheapest working model path: `openai/gpt-5-nano`

The result is a small agent system with clear separation between:
- runtime continuity
- campaign outcome triage
- candidate readiness review
- paper-trade readiness review
- failure postmortems

## Agent Inventory

### 1. `runtime-supervisor`

Role:
- the only always-on operator
- watches the research runtime
- decides whether to do nothing, recover, or escalate
- starts the next approved runbook item only when the runtime is truly idle and the previous approved branch exhausted

Primary responsibilities:
- observe runtime health, workers, directors, campaigns, jobs, and notifications
- classify degraded vs idle vs active runtime states
- avoid starting extra directors when campaigns are already active
- treat missing workers during active campaigns as a service-health fault
- record recoveries and escalations
- write compact incident artifacts

Skills attached:
- `runtime-supervisor`
- `failure-investigator`
- `research-continuity`
- `service-recovery`

Why it exists:
- this is the runtime continuity layer for the system
- it prevents the runtime from quietly stalling or taking unsafe continuity actions

### 2. `research-triage`

Role:
- classify terminal campaign outcomes into:
  - `promising`
  - `needs_followup`
  - `dead_end`
  - `blocked`

Primary responsibilities:
- read compact campaign review packs
- prefer final decisions and report artifacts over raw logs
- produce a machine-readable summary artifact
- stay read-only

Why it exists:
- campaign completion produces a lot of output, but most of it is not decision-ready
- this agent turns a finished campaign into a compact triage result for the supervisor and operator surfaces

### 3. `candidate-review`

Role:
- review promoted or near-promoted candidates and decide whether they are ready for paper rehearsal or still research-only

Primary responsibilities:
- inspect promotion artifacts
- inspect operator scorecards
- inspect any existing paper-trade decision artifact
- emit a fixed readiness-style summary
- stay analysis-only

Typical classifications:
- `ready_for_paper_rehearsal`
- `research_only`
- `blocked`

Why it exists:
- this is the bridge between raw research output and operator-level candidate judgment
- it narrows the question from “did the campaign finish?” to “is this candidate actually usable for the next stage?”

### 4. `paper-trade-readiness`

Role:
- turn the strongest current candidate into a concise operator-ready note for paper-trading preparation

Primary responsibilities:
- read the latest candidate and paper-trade artifacts
- verify freshness of inputs
- summarize the paper-trade decision package instead of recomputing strategy logic
- remain strictly read-only

Typical classifications:
- `ready`
- `not_ready`
- `blocked`

Why it exists:
- this is the staging agent between candidate review and any human-led paper-trading workflow
- it keeps the system focused on rehearsal and governance, not live execution

### 5. `failure-postmortem`

Role:
- condense failures into a durable, repeatable postmortem summary

Primary responsibilities:
- read compact failure review packs
- inspect recent notifications and prior incident history
- only inspect raw job logs when compact evidence is still ambiguous
- write stable postmortem summaries
- stay read-only

Typical classifications:
- `service_health`
- `campaign_failure`
- `worker_failure`
- `unknown`
- `blocked`

Why it exists:
- failures should become reusable knowledge, not just ephemeral logs
- this agent supports incident memory, duplicate suppression, and better retry discipline

### 6. `runtime-debug`

Role:
- manual debug workspace for ad hoc inspection
- not part of the normal autonomous operating loop

Why it exists:
- sometimes we need an operator/debug agent separate from the conservative production supervisor path

## Supporting Skill Roles

The `runtime-supervisor` agent carries several helper skills because continuity decisions need multiple narrow reasoning modes.

### `failure-investigator`
- investigates failed or stopped directors/campaigns before action
- forces evidence gathering before recovery or escalation

### `research-continuity`
- handles the narrow case where approved research should continue from the runbook after exhaustion
- prevents improvising new work outside the approved queue

### `service-recovery`
- constrains service restarts to narrow, confirmed service-health faults
- keeps restart actions as a last remediation step rather than a default reaction

## Tool Surface

The custom OpenClaw plugin exposes the Trotters runtime through `trotters_*` tools.

Core tools:
- `trotters_overview`: compact runtime summary
- `trotters_director`: inspect/control directors within the runbook guardrails
- `trotters_campaign`: inspect/control campaigns within approved bounds
- `trotters_jobs`: inspect jobs, logs, and artifacts
- `trotters_runbook`: read next approved work items and record recoveries/escalations
- `trotters_service`: narrow service restart path through ops-bridge
- `trotters_review_pack`: compact artifact-driven context for specialist agents
- `trotters_summaries`: durable machine-readable summary artifacts with duplicate suppression

Design intent:
- use compact, task-shaped tools first
- avoid broad raw payload inspection unless debugging demands it

## Summary Artifacts

The specialist agents and supervisor now write compact summary artifacts rather than relying on transient chat output.

Current summary types:
- `supervisor_incident_summary`
- `campaign_triage_summary`
- `candidate_readiness_summary`
- `paper_trade_readiness_summary`
- `failure_postmortem_summary`

These are intended to help with:
- lower token usage
- better operator visibility
- repeatability across turns
- avoiding repeated re-analysis of the same incident or candidate

## Operating Model

### Always-on
- `runtime-supervisor`

### Event-driven or manual
- `research-triage`
- `candidate-review`
- `paper-trade-readiness`
- `failure-postmortem`
- `runtime-debug`

This is deliberate. We do not want multiple continuously active agents competing for authority or spending tokens to restate the same system state.

## What This Setup Is For

This OpenClaw system is meant to support the trading research pipeline, not to place live trades.

Current scope:
- runtime continuity
- research progression
- candidate assessment
- paper-trade readiness guidance
- incident summarization

Explicitly out of scope right now:
- live broker execution
- autonomous order placement
- many always-on conversational agents
- broad “chat with everything” agent behavior

## Practical Mental Model

Think of the agents in layers:

1. `runtime-supervisor`
   Keeps the machinery operating safely.

2. `research-triage`
   Decides what a finished campaign means.

3. `candidate-review`
   Decides what a candidate means.

4. `paper-trade-readiness`
   Decides whether the best candidate is ready for rehearsal.

5. `failure-postmortem`
   Decides what a failure should teach the system.

That layering is the main reason the architecture stays understandable and relatively cheap.

## Files To Read When Changing This System

If someone needs to change the OpenClaw setup, they should start here:
- `configs/openclaw/openclaw.json`
- `extensions/openclaw/trotters-runtime/index.js`
- `extensions/openclaw/trotters-runtime/skills/*/SKILL.md`
- `scripts/openclaw/runtime-supervisor-message.txt`
- `scripts/openclaw/start-openclaw.sh`
- `src/trotters_trader/agent_summaries.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`

## Bottom Line

What we built with OpenClaw is not a general AI shell around the project.

We built a small operator system:
- one conservative always-on supervisor
- four cheap specialist review agents
- one manual debug agent
- a compact tool and summary layer designed to keep token cost and behavioral drift under control

That is the current OpenClaw architecture for the Trotters runtime.
