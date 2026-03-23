# FW-008 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_service_heartbeats tests.test_cli tests.test_api tests.test_ops_bridge tests.test_dashboard -v
node extensions/openclaw/trotters-runtime/index.test.js
```

## Live Checks

```powershell
docker compose up --build -d
docker compose up -d --scale worker=4
docker compose ps -a
Invoke-WebRequest http://127.0.0.1:8888/healthz -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/overview -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
docker compose exec openclaw-gateway openclaw skills info runtime-supervisor
docker compose exec openclaw-gateway openclaw skills info research-triage
```

## Expected Outcomes

- dashboard and API are published on `127.0.0.1`
- dashboard `/` returns `401` without auth and `200` with valid Basic auth
- dashboard mutating POST without CSRF returns `403`
- API protected GET without bearer returns `401`
- API mutation without actor returns `400`
- runtime overview includes `service_heartbeats` and reports them as `ok` when the loops are alive
- worker pool is restored to four replicas after the rebuild
