---
name: research-triage
description: "Classify terminal campaign outcomes into promising, needs_followup, or dead_end using compact review packs and summary artifacts."
user-invocable: false
---

# Research Triage

Use `trotters_review_pack` with `action: campaign_triage` first.

Rules:
- Stay read-only. Do not start, stop, pause, resume, or restart anything.
- Prefer report artifacts and final decisions over raw logs.
- If the pack is missing, record a blocked summary instead of guessing.
- Persist exactly one machine-readable result with `trotters_summaries` using `action: record` and `summaryType: campaign_triage_summary`.
- Use exact tool field names: `recommendedAction`, `artifactRefs`, `campaignId`, `directorId`, `suppressIfRecent`.
- After the summary write attempt, end with one short confirmation sentence. Do not ask follow-up questions.
- Use `openai/gpt-5-nano` assumptions: be terse, evidence-led, and avoid broad restatements.

Required write shape:
- `status: recorded|blocked`
- `classification: promising|needs_followup|dead_end|blocked`
- `recommendedAction: <single next action>`
- `message: <one sentence>`
- `evidence: <short factual list>`
- `artifactRefs: <artifact paths from the pack>`
- `campaignId: <campaign id>`
- `directorId: <director id if present>`
- `fingerprint: triage:<campaign_id>:<classification>`
- `suppressIfRecent: true`
