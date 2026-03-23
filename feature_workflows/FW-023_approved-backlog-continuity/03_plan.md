# Plan

1. Extend research-family and runbook-queue summaries with standby backlog depth and low-backlog messaging.
2. Surface the new backlog state in the dashboard and API overview contracts.
3. Seed multiple fresh approved families with new plan/program IDs and queue priorities.
4. Verify the queue resumes on the new head while preserving standby depth behind it.

Acceptance criteria:

- queue head ordering follows runbook priority instead of arbitrary proposal-name ordering
- one active or queued family does not collapse the next-family contract down to a single opaque branch
- live runtime can run the new head while still reporting at least two standby families behind it