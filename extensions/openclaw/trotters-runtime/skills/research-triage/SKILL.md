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
- Persist one machine-readable result with `trotters_summaries` using `summaryType: campaign_triage_summary`.
- Use `openai/gpt-5-nano` assumptions: be terse, evidence-led, and avoid broad restatements.

Response contract:
- `status: recorded|blocked`
- `classification: promising|needs_followup|dead_end|blocked`
- `evidence: <short factual list>`
- `recommended_action: <single next action>`
