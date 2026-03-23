# FW-021 Supervisor Resume And Blocked-State UX

Status: `done`

## Goal

Make the queue's blocked, bootstrap-required, approved, and active states explicit to the operator and the OpenClaw supervisor.

## Dependency Chain

- `FW-018` created the comparison and proposal read model.
- `FW-019` created approval-aware queue summaries.
- `FW-020` created the approved-family bootstrap path.
- `FW-021` surfaces the resulting next-family state across API, dashboard, and OpenClaw.

## Exit Criteria

- API overview exposes compact next-family state
- dashboard explains the governed blocked or active state clearly
- OpenClaw supervisor uses governed next-family wording instead of generic idle text

## Commit Boundaries

1. next-family read model and OpenClaw/dashboard/API integration
2. workflow and roadmap documentation