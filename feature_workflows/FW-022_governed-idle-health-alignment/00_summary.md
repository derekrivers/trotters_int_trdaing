# FW-022 Governed Idle Health Alignment

Status: `done`

## Goal

Keep the main runtime-health contract aligned with governed next-family blockers so the operator sees "intentionally blocked" instead of a generic idle state when no approved runnable family remains.

## Dependency Chain

- `FW-021` created the governed next-family state across API, dashboard, and OpenClaw.
- `FW-022` aligns the higher-level runtime-health summary with that governed state.

## Exit Criteria

- API overview health distinguishes governed blocked-idle from generic idle
- dashboard health panel and status styling make blocked-idle states explicit
- blocked queue wording stays consistent with `next_family_status`

## Commit Boundaries

1. shared health/status presentation and regression tests
2. workflow and roadmap documentation
