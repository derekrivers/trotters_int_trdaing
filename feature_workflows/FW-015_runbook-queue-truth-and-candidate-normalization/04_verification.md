# FW-015 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_runbook_queue tests.test_promotion_path tests.test_api tests.test_dashboard -v
python -m py_compile src/trotters_trader/runbook_queue.py src/trotters_trader/promotion_path.py src/trotters_trader/api.py src/trotters_trader/dashboard.py
```

## Live Checks

```powershell
docker compose restart research-api dashboard
docker compose ps
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/runbook-queue -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/current-best-candidate -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
```

## Expected Outcomes

- targeted tests pass
- Compose returns to healthy after the restart
- the runbook queue route returns `attention` with alignment warnings when enabled items are retired or untracked
- the current-best-candidate route returns `no_selected_candidate` when the active branch has no selected candidate
- the dashboard overview renders `Supervisor Work Queue` and the candidate-status cards cleanly
