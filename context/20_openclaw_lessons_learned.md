# OpenClaw Lessons Learned

## Purpose

Capture the practical lessons from integrating, debugging, and hardening OpenClaw for the Trotters runtime.

This note is not a product overview. It is a record of the mistakes, hidden constraints, and operational gotchas we hit so future work starts from the real failure modes instead of the idealized design.

## Main Lessons

### 1. Repo config is not the same thing as runtime state

OpenClaw has a repo-managed side and a stateful runtime side.

Repo-managed inputs:
- `configs/openclaw/openclaw.json`
- `extensions/openclaw/trotters-runtime`
- `scripts/openclaw/*`

Runtime state:
- `runtime/openclaw/*`
- installed plugin state under `~/.openclaw/extensions`
- agent workspaces under `~/.openclaw/workspaces`
- auth profiles and cron state under `~/.openclaw/agents` and `~/.openclaw/cron`

Implication:
- editing repo files does not guarantee the gateway is actually using them
- every meaningful change must be verified in the running gateway, not assumed from the working tree

## 2. OpenClaw plugin loading is fragile around file formatting

The custom plugin failed hard when `openclaw.plugin.json` was written with a UTF-8 BOM.

Observed failure:
- gateway restart loops
- plugin install fails with `failed to parse plugin manifest`
- error text includes `Unexpected token '﻿'`

Implication:
- OpenClaw manifest parsing in this build is intolerant of BOM-prefixed JSON
- any generated JSON or skill file written from PowerShell should be treated as suspect until verified

Rule:
- write OpenClaw JSON manifests without BOM
- if plugin load suddenly breaks after an edit, inspect encoding before debugging logic

## 3. Skills existing on disk does not mean OpenClaw is indexing them

We had custom skill folders physically present under the installed plugin path while `openclaw skills list` still did not show them.

What mattered:
- plugin installed correctly
- gateway stable after restart
- skill files readable and correctly formatted
- OpenClaw skill index refreshed inside the container

Rule:
- after adding or editing skills, verify with:
  - `openclaw skills list`
  - `openclaw skills info <skill-name>`

Do not trust the filesystem alone.

## 4. Supervisor auth is a separate operational problem from ChatGPT access

ChatGPT Plus / Pro / Business does not provide API access for OpenClaw.

Observed blocker:
- cron job existed
- supervisor wiring existed
- scheduled turns still failed because the gateway had no provider API key available at runtime

Rule:
- treat model auth as infrastructure, not application logic
- verify a real provider key or auth profile exists inside `openclaw-gateway`
- do not call the supervisor operational until scheduled turns complete successfully

## 5. Cron sessions cache model/provider state in ways that survive config edits

The supervisor runs in isolated cron sessions. Old session state kept stale provider/model choices alive even after config changes.

Observed consequence:
- the gateway kept using old provider/model assumptions after auth and model changes

Fix that worked:
- clear stale supervisor session metadata during gateway bootstrap

Rule:
- when changing supervisor model or auth behavior, consider cached session state part of the deployment surface
- verify the next cron run, not just the config file

## 6. The cheapest usable model is the cheapest model the running build actually supports

There was a difference between current public model naming and what the installed OpenClaw build accepted.

Observed behavior:
- one nominal model name failed as unknown in this gateway build
- another low-cost variant worked and scheduled turns completed on it

Rule:
- validate model identifiers in the running gateway build
- do not trust naming assumptions from docs alone when integrating through another tool layer

## 7. Compact tool output is mandatory, not optional

The first supervisor path pulled too much raw runtime state and wasted tokens badly.

Observed consequence:
- very high token usage for routine turns
- poor operator behavior because the model was reading noisy payloads instead of decision-ready summaries

Fix that worked:
- compact `trotters_overview`
- compact review packs for campaign triage, candidate review, paper-trade readiness, and failures

Rule:
- default every agent-facing tool to summary mode
- only expose raw payloads behind explicit debug flags
- cost control has to be architectural, not prompt-only

## 8. Always-on should be only one agent

The right topology here was one always-on operator and several event-driven specialists.

Why this matters:
- multiple always-on agents would create noise, duplication, and unnecessary model spend
- the runtime needs a single continuity authority, not a committee

Rule:
- keep `runtime-supervisor` as the only always-on agent
- trigger specialist agents only from clear events or manual review points

## 9. Workspace core files are secondary, not authoritative

The user was right that the supervisor workspace lacked useful core files, but the main control plane still had to stay repo-managed.

Best split:
- policy and behavior in plugin/config/bootstrap/prompt files
- workspace docs for lightweight identity and orientation

Rule:
- never put critical safety rules only in `IDENTITY.md`, `AGENTS.md`, or `TOOLS.md`
- use workspace files to help the agent, not to define the system of record

## 10. Partial Compose startup creates misleading runtime failures

At one stage the supervisor looked wrong because workers and dashboard were absent.

Root cause:
- only a partial Compose graph had been started
- missing services looked like runtime faults when they were really deployment omissions

Rule:
- before debugging runtime behavior, confirm the intended service set is actually running
- distinguish clearly between:
  - not started
  - started and unhealthy
  - started and behaviorally wrong

## 11. Some failures were ordinary code bugs, not OpenClaw problems

The `ops-bridge` outage came from a normal Python import/order bug, not from OpenClaw.

Lesson:
- not every symptom near the supervisor belongs to the agent layer
- keep service debugging disciplined and local to the failing layer

Rule:
- separate gateway/plugin/skill faults from Python service faults from Compose/runtime faults
- fix the narrowest real cause first

## 12. Windows + Docker privilege boundaries are a recurring source of friction

We repeatedly hit Docker access issues from PowerShell on Windows when commands were not running with the required privilege level.

Rule:
- expect `docker compose exec`, `logs`, and similar commands to be sensitive to Windows privilege context
- when debugging container state, keep this in mind before assuming the container itself is broken

## 13. Verification must happen in three layers

Every OpenClaw change should be verified in all of these layers:

1. Static code layer
- syntax and local tests

2. Runtime API / dashboard layer
- Python service tests
- summary artifacts visible in operator surfaces

3. OpenClaw runtime layer
- plugin loaded
- skill recognized
- gateway stable
- cron/job behavior confirmed

If only one layer is checked, regressions leak through.

## 14. Explicit plugin trust has bootstrap-order constraints

We tried to make plugin trust explicit with `plugins.allow`, but the gateway initially rejected the config because the custom plugin path did not exist yet at validation time.

Observed behavior:
- gateway startup failed with `plugins.allow: plugin not found`
- adding `plugins.load.paths` alone still failed when the config was copied before the plugin install created the target path
- the working solution was to stage a bootstrap-safe config first, install the plugin, then copy the final trusted config before starting the gateway

Rule:
- treat trusted plugin config as part of bootstrap sequencing, not just static JSON
- if OpenClaw says a custom trusted plugin is missing, verify whether the plugin path exists at validation time before assuming the id is wrong

## Concrete Gotchas

### Encoding gotchas
- BOM in `openclaw.plugin.json` can break plugin parsing
- generated PowerShell writes can silently introduce encoding problems

### State gotchas
- old cron/session state can pin stale behavior
- installed plugin state can lag behind repo edits until restart/reinstall

### Runtime gotchas
- partial Compose startup can mimic service failure
- zero workers with active campaigns is a service-health fault, not a reason to start more directors

### Cost gotchas
- broad overview payloads are too expensive
- reading artifacts is cheaper and usually more useful than reading raw logs

### Verification gotchas
- filesystem presence is not enough
- `openclaw skills info <name>` is a much stronger check than just looking at directories

## Working Rules Going Forward

1. Treat OpenClaw changes as deployment changes, not just code edits.
2. Write manifests and skill files without BOM.
3. Verify plugin load, skill discovery, and runtime stability after every gateway-affecting change.
4. Keep the supervisor prompt/tool surface compact by default.
5. Keep one always-on operator only.
6. Use specialist agents only on explicit triggers.
7. Persist machine-readable summaries so later agents do not re-derive the same conclusions.
8. Separate service bugs from agent bugs aggressively.
9. Confirm the Compose graph before diagnosing behavioral faults.
10. Never call the supervisor "working" until an actual scheduled turn succeeds end-to-end.

## Useful Verification Commands

```powershell
docker compose ps -a
docker compose logs --tail=120 openclaw-gateway
docker compose exec openclaw-gateway openclaw plugins list
docker compose exec openclaw-gateway openclaw skills list
docker compose exec openclaw-gateway openclaw skills info runtime-supervisor
docker compose exec openclaw-gateway openclaw skills info research-triage
```

## Bottom Line

The hard part of working with OpenClaw was not writing prompts or adding skills.

The hard part was respecting the boundary between:
- repo intent
- gateway runtime state
- container deployment reality
- model auth and provider compatibility

When those layers drift apart, the system looks mysterious. When they are checked explicitly, the problems become ordinary and fixable.
