# Context

## Problem

- the system is healthy but idle because the supervisor exhausted the only approved runbook item
- `FW-005` retired the `risk + sector` family, so the previous assumption that OpenClaw would "just start the next one" is no longer true without a new approved queue item

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- `configs/openclaw/trotters-runbook.json` contains only one enabled `work_queue` item: `broad_operability`
- the runtime supervisor only auto-advances when:
  - there are no active directors and no active campaigns
  - the latest exhausted signal is recent
  - there is a next approved runbook item
- the current runtime is idle because all three conditions are not satisfied at once

## Non-Goals

- do not restart the retired `risk + sector` family under a new name
- do not weaken promotion policy just to keep the queue busy
- do not let the supervisor invent research families without repo-managed approval
