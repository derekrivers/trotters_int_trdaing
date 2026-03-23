# FW-011 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_paper_rehearsal tests.test_promotion_path tests.test_api tests.test_dashboard -v
```

## Live Checks

```powershell
Invoke-WebRequest http://127.0.0.1:8890/api/v1/promotion-path/paper-trade-entry-gate -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/runtime/overview -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
```

## Expected Outcomes

- the gate endpoint returns `blocked`, `ready`, `stale`, or `not_applicable`
- overview exposes the same gate result
- the dashboard renders explicit blocking reasons and next action
