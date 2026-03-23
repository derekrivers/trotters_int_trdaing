# FW-014 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_active_branch tests.test_research_runtime tests.test_api tests.test_dashboard -v
python -m py_compile src/trotters_trader/active_branch.py src/trotters_trader/research_runtime.py src/trotters_trader/api.py src/trotters_trader/dashboard.py
```

## Live Checks

```powershell
docker compose restart research-api research-director dashboard
docker compose ps
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/overview -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/active-branch -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
```

## Expected Outcomes

- targeted tests pass
- the live runtime returns one active director and one active campaign, not duplicates
- the active-branch endpoint returns `200` and includes `recommended_action`, `director`, `campaign`, and `warnings`
- the dashboard overview returns `200` and renders the Active Research Branch panel
- Compose returns to healthy after the service restarts
