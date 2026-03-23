# FW-013 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_api -v
python -m py_compile src/trotters_trader/api.py
```

## Live Checks

```powershell
docker compose restart research-api
docker compose ps
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/overview -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8888/guide -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
```

## Expected Outcomes

- the overview route still returns `200`
- the overview `status` has `workers`, `running_jobs`, `queued_jobs_preview`, `queued_jobs_total`, and `service_heartbeats`
- the overview `status` no longer includes raw `jobs`, `campaigns`, or `directors`
- response size is materially smaller than the previous multi-megabyte payload
- Compose returns to all-healthy after the API restart
