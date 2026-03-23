# FW-007 Queue Expansion And Family Pipeline

## Goal

- expand the OpenClaw work queue beyond the first two approved items while keeping every queued family evidence-backed, bounded, and runnable

## Status

- `done`

## Dependency Chain

- `FW-006`

## Exit Criteria

- the runbook has at least one additional approved runnable family after `beta_defensive_continuation`
- the added family is documented as lower-priority fallback work rather than a new top-conviction branch
- the workflow layer records which candidate families are approved, deferred, or rejected for queue use
- the live runtime remains healthy while the queue grows

## Commit Boundaries

- keep runnable queue/config changes separate from workflow and roadmap sync when practical
- do not mix speculative family creation with simple queue expansion
