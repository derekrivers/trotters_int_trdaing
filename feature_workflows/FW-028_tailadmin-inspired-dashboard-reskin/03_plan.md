# Plan

## Implemented Steps

1. added a Python-native dashboard asset build module that compiles `dashboard.src.css` into the served package asset
2. wired the compiled CSS into the existing server-rendered layout and added a single authenticated asset route for `/assets/dashboard.css`
3. migrated the dashboard shell, cards, tables, alerts, forms, and layout rhythm toward a TailAdmin-inspired visual system without changing operator routes or actions

## Interface Changes

- the dashboard now depends on a compiled package CSS asset instead of an inline `<style>` block
- dashboard pages keep the same routes and operator actions while adopting a new visual system

## Acceptance Criteria

- the dashboard looks and feels TailAdmin-inspired while still behaving like the current Python-rendered operator app
- no runtime/read-model change is required beyond what is strictly necessary to load and serve the new assets

## Rollout And Check Order

1. rebuild the dashboard asset with `python -m trotters_trader.dashboard_assets`
2. run `python -m unittest tests.test_dashboard`
3. start the dashboard locally and verify `/healthz`, authenticated `/`, and authenticated `/assets/dashboard.css`
