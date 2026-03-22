# Plan

## Implementation Steps

1. lock the named seed stack for the branch:
   - broad seed reference
   - `gross65_deploy20_n8_w09_cb12` risk seed
   - `sec3` sector follow-up
2. define the campaign path aimed at restoring walk-forward robustness while preserving the improved holdout profile
3. define explicit stop conditions for branch exhaustion so the repo can retire the branch cleanly if needed
4. make the evidence trail easy to read through stable artifacts and operator-facing summaries
5. limit code cleanup to research/reporting changes that improve evidence quality or branch reproducibility

## Interface Changes

- one maintained research-program context for this branch
- clearer artifact expectations for each step in the branch

## Acceptance Criteria

- the active branch can be described without digging through old runtime outputs
- every new branch result updates the same evidence trail
- the program ends in either promotion or explicit retirement with reasons

## Rollout And Check Order

1. lock the branch definition
2. update research campaign planning/reporting as needed
3. run the chosen branch work
4. update the evidence context after each meaningful result
