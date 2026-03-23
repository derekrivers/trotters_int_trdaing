# FW-012 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_promotion_path tests.test_api tests.test_dashboard -v
```

## Live Checks

```powershell
Invoke-WebRequest http://127.0.0.1:8890/api/v1/promotion-path/research-program-portfolio -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
```

## Expected Outcomes

- the portfolio endpoint returns a stable program list with queue eligibility
- the dashboard renders the research-program portfolio
- retired programs are still visible, but clearly marked as retired
