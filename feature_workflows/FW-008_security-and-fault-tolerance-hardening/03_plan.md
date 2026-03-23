# FW-008 Plan

## Implementation Steps

1. Add shared request-security helpers for bearer auth, basic auth, actor extraction, cookies, and CSRF token generation.
2. Harden the dashboard with HTTP Basic auth, CSRF validation, and hidden CSRF fields in mutating forms.
3. Switch API and ops-bridge bearer checks to constant-time comparison and reject mutation requests missing `X-Trotters-Actor`.
4. Add service-heartbeat helpers, wire heartbeat writes into the coordinator / campaign-manager / research-director loops, and expose heartbeat status through runtime status.
5. Add Compose restart policy and healthchecks, and narrow dashboard / API host publishes to loopback by default.
6. Update README and lessons-learned docs to reflect the hardened local runtime posture.

## Acceptance Criteria

- unit tests cover auth, CSRF, actor requirements, and service heartbeat behavior
- dashboard `/healthz` returns `200` unauthenticated while `/` returns `401` unauthenticated
- dashboard POST without CSRF returns `403`
- API mutation without actor returns `400`
- ops-bridge mutation without actor returns `400`
- Compose shows healthy dashboard / API / ops-bridge / coordinator / campaign-manager / research-director services
- OpenClaw skills still resolve after the API / ops hardening

## Rollout / Check Order

1. unit tests
2. OpenClaw plugin tests
3. rebuild Compose stack
4. restore worker pool to four replicas
5. verify localhost dashboard and API behavior
6. verify OpenClaw skill resolution
7. sync docs and workflow state
