# Plan

1. Extend `runbook_queue_summary` with approval-state fields.
2. Block unapproved, rejected, retired, and missing-definition families from runnable state.
3. Surface the blocked reason in API and OpenClaw tool outputs.
4. Keep disabled history entries intact without making them runnable.

Acceptance criteria:

- exactly approved families become queue-eligible
- blocked reasons are operator-readable and stable