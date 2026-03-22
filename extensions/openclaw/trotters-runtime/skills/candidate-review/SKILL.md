---
name: candidate-review
description: "Review promoted or near-promoted candidates and emit a fixed readiness scorecard for paper rehearsal versus more research."
user-invocable: false
---

# Candidate Review

Use `trotters_review_pack` with `action: candidate_review` first.

Rules:
- Stay analysis-only. No runtime mutation.
- Prefer operator scorecard, promotion decision, and paper-trade artifacts over raw experiment outputs.
- If key artifacts are missing or stale, classify as blocked or research_only instead of inferring readiness.
- Persist exactly one machine-readable result with `trotters_summaries` using `action: record` and `summaryType: candidate_readiness_summary`.
- Use exact tool field names: `recommendedAction`, `artifactRefs`, `profileName`, `suppressIfRecent`.
- After the summary write attempt, end with one short confirmation sentence. Do not ask follow-up questions.

Required write shape:
- `status: recorded|blocked`
- `classification: ready_for_paper_rehearsal|research_only|blocked`
- `recommendedAction: <single next action>`
- `message: <one sentence>`
- `evidence: <short factual list>`
- `artifactRefs: <artifact paths from the pack>`
- `profileName: <profile name>`
- `fingerprint: candidate:<profile_name>:<classification>`
- `suppressIfRecent: true`
