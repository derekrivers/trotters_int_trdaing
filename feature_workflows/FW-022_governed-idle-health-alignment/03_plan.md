# Plan

1. Extend the shared runtime-health helper to accept governed next-family context.
2. Mark blocked-idle runtime as intentionally blocked when the queue is governance-blocked.
3. Tighten blocked status presentation in the dashboard status pills.
4. Add focused dashboard and API regression tests.

Acceptance criteria:

- no-active-work plus `blocked_pending_approval` or `blocked_pending_bootstrap` yields blocked wording instead of generic idle
- the dashboard body shows the blocked message without relying on the operator to infer it from a separate next-family panel
