# Plan

## Implementation Steps

1. choose the next additional family from current repo-backed seeds
2. define it as a director plan and research program
3. add it to the OpenClaw runbook as the next approved item after `beta_defensive_continuation`
4. record which families remain outside the queue and why
5. verify the queue order and live runtime health

## Acceptance Criteria

- the work queue grows from `2` to `3` enabled items
- the third item is explicitly framed as fallback work, not the new strongest branch
- regression coverage proves queue order after `beta_defensive_continuation`
- the live app remains healthy and the active branch stays intact
