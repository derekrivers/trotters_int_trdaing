# FW-008 Codebase Notes

## Touched Modules

- `src/trotters_trader/dashboard.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/ops_bridge.py`
- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/cli.py`
- `src/trotters_trader/http_security.py`
- `src/trotters_trader/service_heartbeats.py`
- `docker-compose.yml`
- `README.md`
- `context/20_openclaw_lessons_learned.md`

## Invariants

- `/healthz` remains public for the dashboard and ops-bridge
- `/readyz` remains the API health entrypoint
- OpenClaw still calls the API and ops-bridge with bearer auth and `X-Trotters-Actor`
- runtime status remains the shared health source for dashboard and API
- host-side operator access defaults to `127.0.0.1`

## Known Smells / Risk Zones

- `dashboard.py` already mixes routing, HTML, and presentation logic; adding auth there risks drift if helpers are not centralized
- `research_runtime.py` is still a large multi-responsibility module, so heartbeat additions should stay narrow and mechanical
- Compose rebuilds collapse worker replicas back to the default unless worker scale is re-applied after restart
- host-side commands can still hit the wrong runtime path if the operator forgets the named-volume versus local-path split

## Exact Files To Inspect First

1. `docker-compose.yml`
2. `src/trotters_trader/dashboard.py`
3. `src/trotters_trader/api.py`
4. `src/trotters_trader/ops_bridge.py`
5. `src/trotters_trader/research_runtime.py`
6. `tests/test_dashboard.py`
7. `tests/test_api.py`
8. `tests/test_ops_bridge.py`
