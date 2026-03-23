# FW-009 Verification

## Targeted Tests

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_promotion_path tests.test_api tests.test_dashboard -v
```

## Live Checks

```powershell
docker compose up --build -d
docker compose up -d --scale worker=4
Invoke-WebRequest http://127.0.0.1:8888/ -Headers @{Authorization="Basic <base64 creds>"} -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8890/api/v1/promotion-path/candidate-progression -Headers @{Authorization="Bearer <token>"} -UseBasicParsing
```

## Expected Outcomes

- the dashboard renders a candidate progression section
- the progression endpoint returns a persisted summary with records and a leading candidate
- the leading candidate matches the overview payload
