# Context

## Problem

- the OpenClaw layer is working, but trust still depends too much on operator memory and known caveats
- repeated degraded cycles and overnight behavior need broader proof
- the gateway still has a trust/allowlist hygiene gap even though the plugin is functioning

## Linked Stable Docs

- `context/18_openclaw_status_and_backlog.md`
- `context/20_openclaw_lessons_learned.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- one always-on supervisor and several event-driven specialist agents are already implemented
- summary artifacts and dispatch telemetry are already surfaced
- repeated incidents can still be tightened further, and the plugin trust warning still exists

## Non-Goals

- no new always-on agents
- no live execution or broker work
- no broad raw-payload expansion of tool surfaces
