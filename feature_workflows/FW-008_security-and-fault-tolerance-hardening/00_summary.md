# FW-008 Summary

## Goal

Harden the single-host runtime so the dashboard is a real operator console, mutation routes require actor identity, and the core orchestration services self-report health.

## Status

`done`

## Dependency Chain

- depends on `FW-001` for the workflow system baseline
- depends on `FW-004` for the hardened OpenClaw control-plane assumptions
- builds on the existing localhost-only OpenClaw gateway posture

## Exit Criteria

- dashboard requires auth on every route except `/healthz`
- dashboard mutating POST controls require CSRF protection
- API and ops-bridge mutation requests reject missing `X-Trotters-Actor`
- runtime status includes service heartbeat state for `coordinator`, `campaign-manager`, and `research-director`
- Compose publishes dashboard and API on loopback by default and adds healthchecks / restart policy
- README and lessons-learned docs reflect the new operator model

## Commit Boundaries

1. shared security and heartbeat helpers plus Python surface changes
2. Compose and docs / workflow sync
