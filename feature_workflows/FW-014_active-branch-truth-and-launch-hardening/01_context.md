# Context

## Problem

- the runtime could report a healthy active director while quietly carrying two running campaigns for the same director and config
- the dashboard was improving, but there was still no single compact summary that answered "what branch is running right now?"
- operators and the supervisor need one truthful read model for the active branch, especially when there is no promotion-ready candidate yet

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/18_openclaw_status_and_backlog.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- `step_director()` can be invoked concurrently by the live runtime loop and the queue handoff before `current_campaign_id` is durably written back
- `/api/v1/runtime/overview` already exposes compact counts, but not one branch-focused explanation of the active director/campaign pair
- the dashboard can still be misread if the operator looks at historical outcomes before live branch state

## Non-Goals

- redesign the supervisor runbook model
- add new research families or change the approved queue
- replace existing director/campaign detail endpoints
