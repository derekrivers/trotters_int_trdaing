# FW-017 New-Family Thesis And Approval Pack

Status: `done`

## Goal

Create a first-class proposal artifact for the next research family so the system can approve one materially new branch before it re-enters the governed supervisor queue.

## Dependency Chain

- `FW-016` ended with an intentionally blocked queue and no approved runnable family.
- `FW-017` establishes the proposal and approval boundary needed before any new branch can re-enter the queue.

## Exit Criteria

- a repo-tracked proposal artifact exists with the required approval fields
- the proposal explains why the new family is materially different from retired branches
- one chosen replacement family is approved instead of leaving a vague shortlist

## Commit Boundaries

1. proposal/config/code changes for proposal loading and validation
2. workflow and roadmap documentation