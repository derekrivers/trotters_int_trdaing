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
- Persist exactly one machine-readable result with `trotters_summaries` using `action: record` and `summaryType: failure_postmortem_summary`.
- Use exact tool field names: `recommendedAction`, `artifactRefs`, `campaignId`, `directorId`, `suppressIfRecent`.
- After the summary write attempt, end with one short confirmation sentence. Do not ask follow-up questions.

Required write shape:
- `status: recorded|blocked`
- `classification: service_health|campaign_failure|worker_failure|unknown|blocked`
- `recommendedAction: <single next action>`
- `message: <one sentence>`
- `evidence: <short factual list>`
- `artifactRefs: <artifact paths from the pack>`
- `campaignId: <campaign id if present>`
- `directorId: <director id if present>`
- `fingerprint: postmortem:<campaign_id_or_runtime>:<classification>`
- `suppressIfRecent: true`
