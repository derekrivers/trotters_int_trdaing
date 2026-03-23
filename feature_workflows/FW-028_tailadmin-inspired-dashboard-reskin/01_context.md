# Context

## Problem

- the dashboard has grown into a serious operator surface, but its current hand-rolled styling is still custom and incremental rather than backed by a coherent admin design system
- TailAdmin looks like a viable visual direction, but the repo should not absorb a hidden framework migration just to improve the dashboard shell and component styling

## Linked Stable Docs

- `context/11_architecture_principles.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- the dashboard is a server-rendered WSGI app in `src/trotters_trader/dashboard.py`
- current styling is inline and local to the Python-rendered HTML layout
- current auth, CSRF, runtime actions, and read-model assembly already work and should remain the behavioral baseline

## Non-Goals

- no React, Next.js, Vue, Angular, or SPA migration
- no runtime, governance, API, or queue-contract redesign as part of the visual reskin
