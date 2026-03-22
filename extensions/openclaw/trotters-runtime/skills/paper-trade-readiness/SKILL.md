---
name: paper-trade-readiness
description: "Turn the strongest current candidate into a concise operator-ready paper-trade readiness note."
user-invocable: false
---

# Paper-Trade Readiness

Use `trotters_review_pack` with `action: paper_trade_readiness` first.

Rules:
- Stay read-only. No broker, order, or live-execution actions.
- Verify freshness before trust. Missing or stale artifacts mean not_ready.
- Summarize the existing paper-trade decision package instead of recomputing strategy logic.
- Persist exactly one machine-readable result with `trotters_summaries` using `action: record` and `summaryType: paper_trade_readiness_summary`.
- Use exact tool field names: `recommendedAction`, `artifactRefs`, `profileName`, `suppressIfRecent`.
- After the summary write attempt, end with one short confirmation sentence. Do not ask follow-up questions.

Required write shape:
- `status: recorded|blocked`
- `classification: ready|not_ready|blocked`
- `recommendedAction: <single next action>`
- `message: <one sentence>`
- `evidence: <short factual list>`
- `artifactRefs: <artifact paths from the pack>`
- `profileName: <profile name>`
- `fingerprint: paper:<profile_name>:<classification>`
- `suppressIfRecent: true`
