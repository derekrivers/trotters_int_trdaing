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
- Persist one machine-readable result with `trotters_summaries` using `summaryType: paper_trade_readiness_summary`.

Response contract:
- `status: recorded|blocked`
- `classification: ready|not_ready|blocked`
- `evidence: <short factual list>`
- `recommended_action: <single next action>`
