# Context

## Problem

- the live runtime exposed an active branch, a retired research-program portfolio, and a current-best-candidate surface that still looked like a real candidate even when no candidate existed
- the operator had no single summary for whether the OpenClaw runbook was actually aligned with the portfolio and the currently active plan
- one focused portfolio route existed, but route discovery and summary interpretation were still too guessy for operator use

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/18_openclaw_status_and_backlog.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- active operability work can appear as the current best candidate even when `best_candidate` is empty
- the promotion-path ledger can accidentally absorb that no-candidate branch unless the summary is normalized first
- the supervisor queue can silently point at retired or untracked work without one operator-facing summary to say so

## Non-Goals

- redesign the research-program definition format
- add a new research family to the runbook
- broaden OpenClaw mutation powers
