# Context

- The governed queue can stop safely when no approved runnable family remains, but that still creates an operator halt every time the current approved branch retires.
- The queue already understands multiple ready items; the missing piece was exposing backlog depth clearly and actually seeding fresh approved successors with new plan/program IDs.
- Re-enabling retired plan IDs would only recreate blocked-retired queue entries, so continuity requires new approved family artifacts rather than another runbook-only change.