# FW-002 Candidate Handoff And Dashboard

## Goal

- make the dashboard and API answer the operator questions that matter:
  - what is the best current candidate
  - why it is the best
  - what failed
  - what should happen next

## Status

- `done`

## Dependency Chain

- `FW-001`

## Exit Criteria

- dashboard overview and candidate surfaces clearly expose the best current candidate and recommendation state
- API exposes the same decision-ready summary without requiring raw artifact inspection
- artifact links and progression history are visible enough for operator review
- `dashboard.py` is split by responsibility where the feature benefits from it

## Commit Boundaries

- one commit for API/dashboard contract additions
- one commit for dashboard structure cleanup and rendering/tests if the split is large enough to justify it

## Delivered

- added a shared operator-facing current-best-candidate summary contract in `reports.py`
- exposed that summary from `/api/v1/runtime/overview` as `current_best_candidate`
- rendered a prominent `Current Best Candidate` section on the dashboard overview with strengths, missing evidence, next action, and supporting specialist summaries
- kept scorecard and comparison artifacts linked from the overview instead of forcing raw catalog inspection
- cleaned the dashboard guide copy so operator-facing text is plain ASCII again
