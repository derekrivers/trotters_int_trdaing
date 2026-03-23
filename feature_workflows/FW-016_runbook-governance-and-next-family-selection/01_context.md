# Context

The runtime had reached the point where queue visibility existed, but continuation safety still depended on raw queue order.

Observed problems:

- `broad_operability` stayed enabled even though it had no tracked research-program definition
- the OpenClaw runbook tool could still fall back to the first enabled item when governed context was missing
- once `beta_defensive_continuation` and `refine_seed_continuation` were exhausted, the queue still advertised them as enabled until the operator cleaned it up manually

This workflow treats the governed empty queue as a correct operating state, not a failure.

Non-goals:

- inventing a new research family automatically
- re-opening retired branches
- adding new mutation powers to OpenClaw
