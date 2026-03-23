# Context

- The live stack can now stop cleanly when no approved runnable family remains.
- `next_family_status` already reports governed blockers such as `blocked_pending_approval`.
- The shared runtime-health summary still reports generic `idle` wording in that state, which weakens the operator story on the main dashboard and in the API overview payload.
- OpenClaw already reads `next_family_status`, so improving the shared health wording mainly needs to land in the overview contract used by API and dashboard.
