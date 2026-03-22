---
name: research-continuity
description: "Keep approved research moving from the curated runbook queue. Start the next enabled work item when the runtime is idle because the previous approved branch exhausted."
user-invocable: false
---

# Research Continuity

Use the runbook as the sole source of approved work.

Rules:

- When the last terminal result is `exhausted`, pick the next enabled runbook item.
- If there is no next approved item, escalate instead of improvising.
- Record recoveries and escalations in the runbook history tool.
- Prefer director-level starts over raw campaign starts unless you are doing an intentional manual recovery.
