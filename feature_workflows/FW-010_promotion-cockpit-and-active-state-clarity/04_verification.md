# FW-010 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_api tests.test_dashboard -v
```

## Live Checks

```powershell
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/overview -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
```

## Expected Outcomes

- overview page contains `Active Runtime Now`
- overview page contains `Candidate Progression`
- overview page contains `Paper-Trade Entry Gate`
- terminal outcomes are labeled as terminal / recent outcomes, not implied live state
