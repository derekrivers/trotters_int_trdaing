# FW-008 Lessons

1. The hardest part of this iteration was not the auth code; it was making the runtime health contract concrete enough that Compose, the dashboard, the API, and OpenClaw could all agree on it.
2. Windows / PowerShell live checks need `-UseBasicParsing` for reliable `Invoke-WebRequest` verification in this environment.
3. Rebuilding the stack resets worker replicas back to the service default, so the intended worker scale must be restored explicitly after `docker compose up --build -d`.
4. Localhost bind intent should be verified with `docker compose ps -a` after recreation, not assumed from the Compose file diff.
5. The dashboard healthcheck can lag briefly behind startup even when manual `GET /healthz` works, so give it a short warm-up window before treating `health: starting` as a regression.
6. The ops-bridge remaining unreachable from `127.0.0.1` is correct: it is internal-only by design, and that should be treated as a positive security signal rather than a defect.
