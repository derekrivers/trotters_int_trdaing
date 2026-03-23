# Lessons

## During Implementation

- adding a second runbook item was not enough by itself because the supervisor summary was not carrying the exhausted plan identity forward into the next-work-item call
- the OpenClaw plugin had drifted from the API contract: `/api/v1/runtime/overview` returns nested `most_recent_terminal.director` and `most_recent_terminal.campaign` objects, so the supervisor summary needed to normalize that shape before making stale/fresh decisions
- live verification must happen inside the Compose-backed runtime; host-side CLI commands against `runtime/research_runtime` can create a separate local runtime that the containers and dashboard do not see

## Durable Takeaways

- autonomous supervision only works when the queue of approved work is maintained as carefully as the code
- runbook continuation logic needs both a queued next item and a stable exhausted-plan identifier, otherwise the supervisor can only restart from queue position one
- the runtime-target warning is correct and should be treated as a hard signal during operator verification, not as ignorable noise
