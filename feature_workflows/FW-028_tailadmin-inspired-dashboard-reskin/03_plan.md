# Plan

## Implementation Steps

1. add a minimal main-app asset build for Tailwind/TailAdmin-inspired dashboard styling
2. wire the compiled dashboard CSS into the existing server-rendered layout without changing route behavior
3. migrate the core dashboard shell, cards, tables, alerts, and layout rhythm toward TailAdmin HTML patterns and verify desktop/mobile rendering

## Interface Changes

- the dashboard gains a minimal asset pipeline for compiled styling
- dashboard pages keep the same routes and operator actions while adopting a new visual system

## Acceptance Criteria

- the dashboard looks and feels TailAdmin-inspired while still behaving like the current Python-rendered operator app
- no runtime/read-model change is required beyond what is strictly necessary to load and serve the new assets

## Rollout And Check Order

1. validate asset build and dashboard tests locally
2. restart the live dashboard and verify `/healthz` plus authenticated `/`
