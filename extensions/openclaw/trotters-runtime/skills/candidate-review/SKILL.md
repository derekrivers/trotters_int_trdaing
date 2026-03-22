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
- Persist one machine-readable result with `trotters_summaries` using `summaryType: candidate_readiness_summary`.

Response contract:
- `status: recorded|blocked`
- `classification: ready_for_paper_rehearsal|research_only|blocked`
- `evidence: <short factual list>`
- `recommended_action: <single next action>`
