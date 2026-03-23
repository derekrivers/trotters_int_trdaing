# FW-012 Context

## Operator Problem

Once multiple research families existed, the next branch decision depended on remembering which programs were active, exhausted, retired, or still queue-eligible. That was too easy to lose across dashboard views, runbook config, and roadmap notes.

## Stable References

- `context/14_delivery_roadmap.md`
- `feature_workflows/FW-005_risk-sector-promotion-program`
- `feature_workflows/FW-007_queue-expansion-and-family-pipeline`

## Current Behavior At Start

- research-program JSON definitions existed
- some program summaries existed in `runtime/catalog`
- the runbook queue encoded execution order
- but there was no single compact operator board that joined those facts together

## Non-Goals

- no automatic invention of new research branches
- no OpenClaw mutation expansion
- no replacement of repo-managed program definitions
