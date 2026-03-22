# FW-005 Risk-Sector Promotion Program

## Goal

- treat the strongest current `risk + sector` branch as the active research program until it is either promoted under the existing policy or explicitly retired with evidence

## Status

- `done`

## Dependency Chain

- `FW-001`

## Exit Criteria

- named seeds, campaign path, stop conditions, and artifact expectations are fixed
- positive and negative evidence for the branch is captured in one maintained place
- the branch ends with either a promotable candidate or an explicit retirement decision

## Commit Boundaries

- one commit per research/control-plane adjustment
- keep report or evidence-capture refactors separate from strategy-parameter changes when practical

## Outcome

- the branch is now explicitly retired, not left open-ended
- `configs/research_programs/risk_sector_promotion.json` fixes the seed stack, campaign path, artifact expectations, and stop conditions
- `runtime/catalog/risk_sector_promotion_program/research_program.json` is now the maintained evidence artifact for this branch
