# Context

## Problem

- the repo can already emit a daily decision package
- but it does not yet persist a separate rehearsal portfolio or record what the operator did with the day package
- that means the project is close to paper-trading readiness conceptually, but not operationally

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- paper-trade decision artifacts can be generated
- no separate paper portfolio state exists
- no operator accept/skip/override decision log exists
- no dedicated daily paper runner exists

## Non-Goals

- no broker integration
- no live order routing
- no intraday or account synchronization work
