# FW-008 Context

## Operator Problem

The runtime was functioning, but its local control surfaces were softer than the rest of the system implied:

- the dashboard was an unauthenticated control plane with mutating forms
- the API and ops-bridge accepted mutations without requiring a meaningful actor identity
- service-level health was inferred indirectly from jobs and workers rather than from the orchestration loops themselves
- Compose restart and health behavior lagged behind the repo's autonomous-runtime story

## Stable References

- `README.md`
- `context/20_openclaw_lessons_learned.md`
- `context/21_openclaw_agent_guide.md`
- `feature_workflows/01_code_hotspots.md`

## Current Behavior Before This Workflow

- dashboard reachable on the host without auth
- dashboard POST controls depended only on browser access, not CSRF protection
- API and ops-bridge used bearer tokens, but token checks were plain string comparisons and mutation routes did not require `X-Trotters-Actor`
- only `openclaw-gateway` had an explicit restart policy in Compose
- coordinator, campaign manager, and research director had no direct heartbeat artifact or healthcheck contract

## Non-Goals

- no TLS, SSO, OAuth, or reverse proxy work
- no public-internet or shared-LAN deployment design
- no worker-specific container healthchecks in this iteration
- no OpenClaw runbook behavior change beyond the stronger health signal it consumes
