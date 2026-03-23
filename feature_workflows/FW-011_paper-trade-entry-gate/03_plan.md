# FW-011 Plan

## Implementation Steps

1. Build a dedicated paper-trade entry gate from candidate progression and existing rehearsal prerequisites.
2. Persist the gate summary under the promotion-path artifact layer.
3. Have the paper runner consume the gate directly.
4. Expose the gate through API and dashboard with explicit next action and blocking reasons.

## Chosen Interfaces

- `paper_trade_entry_gate`
- paper-rehearsal status includes the latest gate snapshot
- focused API endpoint for the entry gate

## Acceptance Criteria

- no promoted candidate resolves to `blocked`
- stale evidence resolves to `stale`
- a valid promoted target can resolve to `ready`
- the paper runner records gate-driven decisions consistently

## Rollout / Check Order

1. paper-rehearsal and promotion-path tests
2. API/dashboard tests
3. live authenticated status and overview checks
