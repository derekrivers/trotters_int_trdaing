# FW-028 TailAdmin-Inspired Dashboard Reskin

## Goal

- land a TailAdmin-inspired reskin of the existing Python-rendered dashboard without turning it into a frontend rewrite

## Status

- `done`

## Dependency Chain

- `FW-026`
- `FW-027`

## Exit Criteria

- the existing server-rendered dashboard uses a TailAdmin-style visual system via a minimal asset pipeline while preserving current behavior and operator workflows
- the workflow stays presentation-first and does not move dashboard truth or operator actions out of the current Python-rendered application

## Implementation Notes

- moved dashboard styling out of inline HTML and into a compiled package asset served at `/assets/dashboard.css`
- kept the existing WSGI routes, auth, CSRF handling, and render contracts intact while restyling the shell, cards, tables, alerts, and controls
- added a Python-native asset build entrypoint via `python -m trotters_trader.dashboard_assets`
