# OpenClaw Supervisor Next Steps

## Purpose

Capture the immediate next actions after the first OpenClaw runtime-supervisor integration.

This note is intentionally practical. It reflects the current implementation state in the repo, the remaining blockers, and the sequence needed to move from "wired up" to "trusted operator".

## Current State

The following pieces are now implemented in the working tree:

- `research-api` exposes runtime status, directors, campaigns, jobs, artifacts, and notifications
- `ops-bridge` exists as a narrow internal restart service for an allowlisted set of Compose services
- the OpenClaw gateway loads a repo-managed `trotters-runtime` plugin
- the default OpenClaw agent is `runtime-supervisor`
- a curated runbook exists at `configs/openclaw/trotters-runbook.json`
- the gateway bootstrap seeds a recurring isolated cron job named `trotters-runtime-supervisor`
- the cron bootstrap now correctly keeps only one supervisor cron job instead of accumulating duplicates

What is not yet complete:

- the supervisor cannot run autonomously until model-provider auth is available inside `openclaw-gateway`
- the supervisor policy is encoded in prompt/skills, but not yet validated by end-to-end incident drills
- the plugin has no dedicated automated test suite yet
- the work is still uncommitted in the repo

## Main Blocker

### 1. Supervisor Model Auth

The current gateway logs show that scheduled supervisor turns fail with:

- `No API key found for provider "anthropic"`

This is the primary activation blocker. Until it is fixed, the cron job exists but the supervisor does not actually operate the system.

Required outcome:

- `runtime-supervisor` can execute scheduled turns without auth errors

Acceptable ways to resolve it:

- provide a provider key in `.env` such as `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`
- or copy an existing OpenClaw agent auth profile into `runtime-supervisor`
- or set `OPENCLAW_SUPERVISOR_AUTH_SOURCE_AGENT` to a valid agent with working auth and recreate the gateway

Acceptance criteria:

- no more `No API key found for provider ...` entries in `openclaw-gateway` logs after restart
- at least one scheduled cron run completes successfully

## Recommended Execution Order

### Phase 1. Activate The Supervisor

1. Add model-provider auth for the OpenClaw gateway.
2. Recreate `openclaw-gateway`.
3. Confirm the supervisor cron job still exists.
4. Confirm scheduled turns no longer fail on auth.

Checks:

- `docker compose logs --tail=120 openclaw-gateway`
- `docker compose exec openclaw-gateway openclaw cron list --json`

Success condition:

- one supervisor cron job
- successful scheduled runs

### Phase 2. Validate Real Runtime Decisions

Run controlled drills against the runtime and verify the supervisor behavior matches policy.

Minimum drills:

1. Healthy active runtime
   Expected result: no action.
2. Idle runtime after `exhausted`
   Expected result: start the next approved runbook item.
3. Failed campaign with readable evidence
   Expected result: investigate before acting.
4. Service-health fault
   Expected result: use `ops-bridge` only if the symptom is confirmed.

Evidence to capture for each drill:

- overview before
- tool decisions taken
- notifications after
- audit log records
- whether the action matched the written guardrails

Success condition:

- the supervisor makes the intended decision in each drill
- no out-of-policy action occurs

### Phase 3. Add Missing Automated Tests

The Python service layer has coverage, but the OpenClaw plugin path still needs direct tests.

Add tests for:

- plugin request shaping and auth header injection
- `X-Trotters-Actor` header injection
- runbook allowlist resolution for `plan_id` and `config_id`
- service restart rejection for non-allowlisted services
- runbook history recording
- cron bootstrap behavior where an old supervisor job is replaced by exactly one current job

Recommended scope:

- lightweight Node-level tests for `extensions/openclaw/trotters-runtime/index.js`
- one shell/bootstrap smoke test for `scripts/openclaw/start-openclaw.sh`

Success condition:

- the supervisor integration can be regression-tested without manual UI checks

### Phase 4. Tighten Safety Before Trusting It Overnight

The current version is useful, but it should not yet be treated as a fully trusted unattended operator.

Hardening items:

1. Add explicit escalation records for ambiguous incidents.
2. Add stronger duplicate-action protection around repeated retries.
3. Add clearer separation between:
   - retry same work item
   - fallback to another approved item
   - escalate and stop
4. Add a small incident summary artifact per supervisor action cycle.
5. Consider forcing service restart actions to include a linked incident id.

Success condition:

- every mutation is explainable after the fact
- repeated failures do not create silent retry loops

### Phase 5. Commit And Operationalize

Once activation and drills pass:

1. review the working tree carefully
2. update README and context notes if the auth flow or operator workflow changed during validation
3. commit the supervisor integration as one coherent feature
4. bring the stack back up with the final env configuration
5. run one monitored overnight trial

Overnight trial success criteria:

- supervisor cron keeps running
- no auth failures
- no duplicate cron jobs
- if runtime is idle after `exhausted`, the next approved item starts
- if runtime fails, the supervisor investigates and records the incident rather than blindly looping

## Priority Summary

Highest priority:

1. fix supervisor model auth
2. run end-to-end decision drills
3. add plugin/bootstrap regression tests

Medium priority:

4. improve incident recording and retry guardrails
5. commit the work and rerun a monitored unattended session

## Suggested Immediate Next Command Set

Once you are ready to resume:

1. set one provider key in `.env`
2. bring the stack up
3. inspect supervisor logs and cron state

Example:

```powershell
docker compose up --build -d --scale worker=6
docker compose logs --tail=120 openclaw-gateway
docker compose exec openclaw-gateway openclaw cron list --json
```

## Decision Standard

Do not call this integration "done" just because the API, plugin, and cron job exist.

It is only operationally complete when:

- auth is working
- scheduled turns execute
- the supervisor behaves correctly in controlled drills
- the behavior is covered by regression tests
- the full change set is committed cleanly
