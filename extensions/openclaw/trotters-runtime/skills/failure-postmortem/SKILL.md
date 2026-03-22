---
name: failure-postmortem
description: "Condense failures, notifications, and incident history into a stable low-cost postmortem summary."
user-invocable: false
---

# Failure Postmortem

Use `trotters_review_pack` with `action: failure_postmortem` first.

Rules:
- Stay read-only. Do not take recovery actions.
- Inspect `trotters_jobs` logs only when the failure pack still leaves the cause ambiguous.
- Prefer repeatable failure classes over narrative prose.
- Persist one machine-readable result with `trotters_summaries` using `summaryType: failure_postmortem_summary`.

Response contract:
- `status: recorded|blocked`
- `classification: service_health|campaign_failure|worker_failure|unknown|blocked`
- `evidence: <short factual list>`
- `recommended_action: <single next action>`
