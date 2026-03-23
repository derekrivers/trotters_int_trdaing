# Plan

## Implementation Steps

1. audit the current dashboard CSS and identify the most oversized headings, metrics, and dense panel text
2. normalize dashboard timestamp rendering to second precision wherever raw operator timestamps are shown
3. update dashboard tests and live-verify the main overview/detail routes after the presentation cleanup

## Interface Changes

- dashboard HTML/CSS presentation will become more compact and balanced
- raw dashboard timestamps will omit sub-second precision while keeping relative-age labels

## Acceptance Criteria

- the main dashboard reads more compactly without reducing information density or breaking visual hierarchy
- no dashboard route shows microsecond precision unless there is a deliberate exception with a clear reason

## Rollout And Check Order

1. run focused dashboard tests locally
2. restart the dashboard service and confirm `/healthz` plus authenticated `/` still behave correctly
