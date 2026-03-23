# Plan

1. Tighten `runbook_queue_summary` so only `ready` entries count as runnable.
2. Make `trotters_runbook.get` and `trotters_runbook.next_work_item` load the governed queue summary from the API.
3. Return explicit blocked context when no approved runnable branch exists.
4. Disable retired and untracked entries in the live runbook config.
5. Verify both tests and live services, including the dashboard and OpenClaw skill readiness.
