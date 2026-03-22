# Trotters Independent Traders

This repository currently contains:

- stable project context in [`context/README.md`](context/README.md)
- active feature workflows in [`feature_workflows/README.md`](feature_workflows/README.md)
- a Python scaffold for a simple historical backtesting bot in `src/`

## Current Scope

The scaffold is intentionally narrow:

- UK-equity style daily-bar backtesting
- offline simulation only
- deterministic execution model
- no live trading or broker integration

## Fidelity Features

The current scaffold includes:

- source-to-canonical ingestion
- explicit raw-to-staging-to-canonical ingestion
- explicit source adjustment-policy handling
- instrument lifecycle validation with listing and delisting support
- instrument eligibility filtering
- market-data validation
- canonical adjusted-close generation from corporate actions
- explicit trading-calendar handling
- momentum feature materialization and optional precomputed feature usage
- run artifacts with exposure, turnover, drawdown, and trade statistics
- execution simulation with spread, slippage, participation caps, and partial fills
- strategy ranking with top-N selection and configurable weighting
- benchmark tracking against a simple equal-weight buy-and-hold portfolio
- multiple strategy families including SMA trend, cross-sectional momentum, and mean reversion
- markdown and CSV report artifacts per run
- aggregate markdown and CSV comparison reports for experiment batches
- multidimensional sensitivity sweeps across portfolio and execution assumptions
- dedicated threshold sweeps for signal selectivity research
- configurable rebalance cadence and per-rebalance turnover budgeting
- machine-readable research catalog and research decision artifacts under `runs/research_catalog`

## Strategy Config Shape

Strategy parameters now live in strategy-specific TOML blocks:

```toml
[strategy]
name = "sma_cross"
top_n = 2
weighting = "equal"
ranking_mode = "global"
score_transform = "raw"
min_candidates_per_group = 1

[strategy.sma_cross]
short_window = 3
long_window = 5

[strategy.cross_sectional_momentum]
lookback_window = 5
max_trailing_drawdown = 1.0

[strategy.mean_reversion]
lookback_window = 3

[evaluation]
warn_turnover = 2.0
fail_turnover = 3.0
warn_min_trade_count = 3
fail_min_trade_count = 1
warn_max_drawdown = 0.10
fail_max_drawdown = 0.20
warn_min_excess_return = 0.0
fail_min_excess_return = -0.05
flag_underperform_benchmark = true
fail_on_zero_trade_run = true

[evaluation_profiles.lenient]
warn_turnover = 3.0
fail_turnover = 4.5

[evaluation_profiles.research]
warn_turnover = 2.0
fail_turnover = 3.0

[evaluation_profiles.strict]
warn_turnover = 1.5
fail_turnover = 2.5
```

The `evaluation` block controls report judgment policy. It now supports separate warn/fail bands for turnover, trade count, drawdown, and excess return, so experiment triage is explicit and configurable.
Use `--evaluation-profile <name>` to switch to one of the named presets without editing the config file.

The `data` block now also carries `adjustment_policy`. Supported values are:

- `raw_close`
- `vendor_adjusted_close`
- `dividends_from_actions`
- `splits_and_dividends_from_actions`

That policy is persisted into the canonical dataset manifest and surfaced in run reports so signal semantics are explicit.

The `portfolio` block now also supports:

- `target_gross_exposure`
- `rebalance_frequency_days`
- `max_rebalance_turnover_pct`
- `initial_deployment_turnover_pct`
- `volatility_target`
- `volatility_lookback_days`
- `drawdown_reduce_threshold`
- `drawdown_reduced_gross_exposure`
- `drawdown_force_rebalance`
- `selection_buffer_slots`
- `max_positions_per_sector`
- `max_positions_per_industry`
- `max_positions_per_benchmark_bucket`
- `min_holding_days`

`target_gross_exposure` is an explicit deployment target for the book. It lets you control intended invested exposure directly instead of inferring it only from `cash_buffer_pct`.
`rebalance_frequency_days`, `max_rebalance_turnover_pct`, and `initial_deployment_turnover_pct` are the main anti-churn and deployment levers for larger universes.
`volatility_target`, the drawdown controls, and the benchmark-regime controls are optional risk overlays. They are available for experiments, but they are not currently part of the current EODHD momentum baseline.
The latter two reduce ranking churn by keeping near-cutoff holdings and preventing immediate exits after entry.
`initial_deployment_turnover_pct` is separate from steady-state turnover control. It exists so a strategy that starts from cash can build a realistic book without being trapped for years by an ultra-low rebalance budget.
`max_positions_per_sector` is an optional basket-construction cap that uses sector metadata from the instrument master.
`max_positions_per_industry` and `max_positions_per_benchmark_bucket` extend that same basket-construction path to richer metadata once the instrument master carries it.
Available weighting modes now include `equal`, `vol_inverse`, and experimental `beta_vol_inverse`.
The `strategy` block now also supports:

- `ranking_mode = "global" | "sector_relative" | "benchmark_bucket_relative"`
- `score_transform = "raw" | "vol_adjusted" | "drawdown_penalized"`
- `min_candidates_per_group`

Grouped ranking modes are intended for research, not yet as a promoted baseline. `vol_adjusted` and `drawdown_penalized` reuse the same materialized momentum feature set.

The `features` block supports:

- `enabled`
- `feature_dir`
- `set_name`
- `use_precomputed`
- `materialize_on_backtest`

At present the materialized feature path is implemented for cross-sectional momentum. When enabled, the repo persists a feature set and can reuse it during backtests instead of recomputing the momentum inputs inline.

## Quick Start

1. Use Python 3.11 or later.
2. Put historical daily-bar CSV data into `data/sample/daily_bars.csv` or replace it with your own dataset.
3. Run:

```bash
python -m trotters_trader.cli --config configs/backtest.toml
```

To materialize canonical datasets from source CSV files first:

```bash
python -m trotters_trader.cli stage --config configs/backtest.toml
python -m trotters_trader.cli ingest --config configs/backtest.toml
python -m trotters_trader.cli materialize-features --config configs/eodhd_momentum.toml
python -m trotters_trader.cli backtest --config configs/backtest.toml
python -m trotters_trader.cli report --config configs/backtest.toml
python -m trotters_trader.cli download-alpha-vantage --config configs/backtest.toml --limit 5
python -m trotters_trader.cli download-alpha-vantage --config configs/backtest.toml --instrument TSCO.L --raw-series --outputsize compact
python -m trotters_trader.cli download-eodhd --config configs/eodhd.toml --instrument TSCO.L --from-date 2018-01-01
python -m trotters_trader.cli experiment --config configs/backtest.toml
python -m trotters_trader.cli sensitivity --config configs/backtest.toml
python -m trotters_trader.cli thresholds --config configs/backtest.toml
python -m trotters_trader.cli compare-strategies --config configs/backtest.toml
python -m trotters_trader.cli compare-profiles --config configs/backtest.toml
python -m trotters_trader.cli compare-benchmarks --config configs/backtest.toml
python -m trotters_trader.cli compare-strategies --config configs/backtest.toml --quality-gate pass_warn
python -m trotters_trader.cli compare-strategies --config configs/backtest.toml --evaluation-profile strict
python -m trotters_trader.cli validate-split --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli research-catalog --config configs/eodhd_momentum.toml
python -m trotters_trader.cli universe-slice-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli ranking-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli construction-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli starter-tranche --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli operability-program --config configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml --quality-gate pass_warn
python -m trotters_trader.cli paper-trade-decision --config configs/backtest.toml --reference-date 2026-03-21
python -m trotters_trader.cli research-campaign-start --config configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml --runtime-root runtime/research_runtime --catalog-output-dir runtime/catalog --campaign-name broad-operability
python -m trotters_trader.cli research-campaign-status --runtime-root runtime/research_runtime --campaign-id <campaign_id>
```

`--quality-gate` applies only to comparison outputs. It does not skip running scenarios; it filters the generated comparison summary, ranking CSV, and experiment index to one of `all`, `pass_warn`, or `pass`.
`compare-profiles` runs the same strategy comparison under each named evaluation profile and writes one aggregate report so you can see how research conclusions change under different review standards.
`compare-benchmarks` runs the same strategy comparison against each configured primary benchmark and writes benchmark-specific excess-return columns into the aggregate report.
`operability-program` runs the robustness-first promotion workflow: focused operability tranche, optional benchmark-aware pivot, stress pack on the shortlist, and one final handoff report.
`paper-trade-decision` writes a daily decision package with target holdings, rebalance actions, expected turnover, and warnings for stale or incomplete inputs. It is intended for paper-trading rehearsal once a strategy is promoted.
`research-campaign-start` creates a persisted autonomous campaign in the runtime database; the campaign manager can keep advancing it in the background until it freezes a candidate or exhausts its budget.

## Docker

The repo has two separate Compose entrypoints:

- [`docker-compose.yml`](c:/Dev/TrottersIndependantTraders/docker-compose.yml) for the research runtime stack
- [`docker-compose.test.yml`](c:/Dev/TrottersIndependantTraders/docker-compose.test.yml) for the test runner

Common commands:

```bash
# Start the runtime with 4 research workers
docker compose up --build -d --scale worker=4

# Check runtime container status
docker compose ps

# Start an autonomous research campaign
python -m trotters_trader.cli research-campaign-start --config configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml --runtime-root runtime/research_runtime --catalog-output-dir runtime/catalog --campaign-name broad-operability

# Start a deterministic research director that can chain campaigns
python -m trotters_trader.cli research-director-start --config configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml --runtime-root runtime/research_runtime --catalog-output-dir runtime/catalog --director-name broad-director

# Open the local runtime dashboard
# http://localhost:8888

# Inspect campaign state and latest recommendation
python -m trotters_trader.cli research-campaign-status --runtime-root runtime/research_runtime

# Scale the worker pool up or down
docker compose up --build -d --scale worker=6

# Run the full unittest suite in an isolated test container
docker compose -f docker-compose.test.yml run --rm test-runner

# Stop the runtime stack
docker compose down

# Stop the runtime stack and remove orphaned old services
docker compose down --remove-orphans
```

The runtime stack now includes dedicated `campaign-manager` and `research-director` services. The campaign manager advances one campaign through focused tuning, pivots, and stress. The research director sits one level higher: it can launch the next approved campaign automatically when the previous one exhausts, and stop only when it finds a frozen candidate or the approved queue is exhausted. A separate `dashboard` service exposes a local operations view on `http://localhost:8888`.

### OpenClaw

The runtime stack can also run an `openclaw-gateway` container alongside the research services.

What is wired today:

- `research-api` is exposed on `http://localhost:8890`
- `ops-bridge` runs on the internal Compose network and exposes narrow service restarts for the allowlisted runtime services only
- `openclaw-gateway` runs on the same Compose network and receives `TROTTERS_API_BASE=http://research-api:8890`
- `openclaw-gateway` also receives `TROTTERS_OPS_BRIDGE_TOKEN` so the supervisor plugin can call the internal ops bridge
- OpenClaw persists its state under [`runtime/openclaw/`](c:/Dev/TrottersIndependantTraders/runtime/openclaw)
- the repo-managed default OpenClaw config lives at [`configs/openclaw/openclaw.json`](c:/Dev/TrottersIndependantTraders/configs/openclaw/openclaw.json)
- the curated supervisor runbook lives at [`trotters-runbook.json`](c:/Dev/TrottersIndependantTraders/configs/openclaw/trotters-runbook.json)
- the local OpenClaw runtime plugin lives at [`index.js`](c:/Dev/TrottersIndependantTraders/extensions/openclaw/trotters-runtime/index.js)

Required `.env` entries:

- `TROTTERS_API_TOKEN`
- `OPENCLAW_IMAGE`
- `OPENCLAW_GATEWAY_BIND`
- `OPENCLAW_GATEWAY_PORT`
- `OPENCLAW_GATEWAY_TOKEN`
- `TROTTERS_OPS_BRIDGE_TOKEN`

Runtime-supervisor model auth:

- the supervisor cron loop needs model-provider credentials in the `openclaw-gateway` container before it can act autonomously
- provide one supported provider key in `.env`, for example `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`
- alternatively, if you have already configured another local OpenClaw agent inside the same state volume, set `OPENCLAW_SUPERVISOR_AUTH_SOURCE_AGENT` and the gateway bootstrap will copy that agent's `auth-profiles.json` into `runtime-supervisor`

The gateway is started by the main Compose file, so bringing up the runtime stack also starts OpenClaw:

```bash
docker compose up --build -d --scale worker=6
```

Local endpoints:

- OpenClaw gateway websocket: `ws://localhost:18789`
- OpenClaw control UI: `http://127.0.0.1:18789/`
- OpenClaw canvas UI assets: `http://127.0.0.1:18789/__openclaw__/canvas/`
- Research API: `http://localhost:8890`
- Ops bridge: `http://ops-bridge:8891` on the internal Compose network only

Authentication:

- the OpenClaw UI is easiest to bootstrap with `http://127.0.0.1:18789/#token=<OPENCLAW_GATEWAY_TOKEN>`
- the research API requires `Authorization: Bearer <TROTTERS_API_TOKEN>` on all `/api/v1/*` routes
- on first browser connection, OpenClaw may require one-time device pairing approval

Operational notes:

- OpenClaw serves its Control UI at `/`, but authentication happens on the websocket handshake, so a plain unauthenticated browser hit may show `Disconnected from gateway` until the token is provided
- the gateway is intentionally published on loopback only: `127.0.0.1:${OPENCLAW_GATEWAY_PORT}`
- if you change [`configs/openclaw/openclaw.json`](c:/Dev/TrottersIndependantTraders/configs/openclaw/openclaw.json), restart the gateway with `docker compose up -d openclaw-gateway`
- if the UI shows `pairing required`, approve the pending browser device from the gateway host with `docker compose exec openclaw-gateway openclaw devices list` and `docker compose exec openclaw-gateway openclaw devices approve <request_id>`
- the gateway startup now seeds a recurring isolated cron job named `trotters-runtime-supervisor`, so the default `runtime-supervisor` agent wakes every 2 minutes and checks the runtime without a manual prompt
- the supervisor uses only the repo-managed `trotters-runtime` plugin tools and the curated runbook; it does not get raw Docker socket access
- if provider auth is missing, the cron job still exists but each scheduled turn will fail fast with a `No API key found for provider ...` diagnostic until you add a model API key or copy an existing auth profile into the supervisor agent

Suggested Docker Desktop resources for this repo:

- `5` workers: allocate at least `10 GiB` memory
- `6-8` workers: prefer `12 GiB` memory
- Docker disk image: `40-50 GB` minimum, `60 GB` safer for frequent rebuilds
- Keep additional free host disk space for bind-mounted research outputs under [`runtime/`](c:/Dev/TrottersIndependantTraders/runtime)

## Autonomous Research

The autonomous workflow is designed to let the research stack keep searching without manual intervention.

What runs in the background:

- `coordinator`: leases queued jobs and keeps runtime state healthy
- `worker`: executes distributed `promotion-check` jobs
- `campaign-manager`: decides what tranche to run next and advances campaigns until they finish
- `research-director`: decides what campaign to run next and chains campaigns until a viable strategy is found or the approved queue is exhausted
- `dashboard`: shows queue health, worker status, campaign detail, notifications, and stop controls
- `dashboard` also includes a plain-English `/guide` page explaining the system, the terminology, and the intended path from research candidate to later paper/live trading
- the paper-trading boundary and current readiness state are documented in [`context/16_paper_trading_status.md`](context/16_paper_trading_status.md)
- the current OpenClaw control-plane status is documented in [`context/18_openclaw_status_and_backlog.md`](context/18_openclaw_status_and_backlog.md)
- the active next-iteration workflow queue lives in [`feature_workflows/00_program_board.md`](feature_workflows/00_program_board.md)

Campaign phases currently follow this path:

1. `focused_operability`
2. `benchmark_pivot` if focused tuning fails
3. `stability_pivot` if the benchmark-aware pivot still fails
4. `stress_pack` on the shortlisted candidates
5. stop only when a candidate is frozen or the campaign is exhausted

Director-level policy currently works like this:

1. start the first approved seed config
2. let the campaign manager run it to completion
3. if the campaign freezes a candidate, stop successfully
4. if the campaign exhausts, launch the next approved seed config
5. if a campaign fails or is manually stopped, halt the director for operator review

Typical background workflow:

```bash
# 1. Start the runtime stack
docker compose up --build -d --scale worker=4

# 2. Start one deterministic research director
python -m trotters_trader.cli research-director-start \
  --config configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml \
  --runtime-root runtime/research_runtime \
  --catalog-output-dir runtime/catalog \
  --director-name broad-operability \
  --campaign-max-hours 24 \
  --campaign-max-jobs 1500 \
  --stage-candidate-limit 120 \
  --shortlist-size 3

# Optional: provide an explicit queue instead of the built-in default plan
# python -m trotters_trader.cli research-director-start \
#   --director-plan-file configs/directors/broad_operability.json \
#   --runtime-root runtime/research_runtime \
#   --catalog-output-dir runtime/catalog \
#   --director-name broad-operability

# 3. Check director progress later
python -m trotters_trader.cli research-director-status \
  --runtime-root runtime/research_runtime \
  --director-id <director_id>

# 4. Open the dashboard
# http://localhost:8888

# 5. Stop a director without tearing down the whole stack
python -m trotters_trader.cli research-director-stop \
  --runtime-root runtime/research_runtime \
  --director-id <director_id> \
  --stop-reason operator_pause

# 6. Inspect queue and worker health
python -m trotters_trader.cli research-status \
  --runtime-root runtime/research_runtime \
  --catalog-output-dir runtime/catalog
```

Running locally overnight:

- keep the computer powered on and keep Docker Desktop running
- set Windows sleep to `Never` while plugged in if you want research to continue unattended
- it is fine for the display to turn off; the important part is that the machine does not sleep
- keep the compose stack up while research is active:

```bash
docker compose up -d --scale worker=4
docker compose ps
```

If the machine restarts, the runtime state is still persisted. Bring Docker back up, then restart the stack with the same compose command and the coordinator/director should resume from saved state.

Important campaign controls:

- `--campaign-max-hours`: hard wall-clock budget for the campaign
- `--campaign-max-jobs`: hard cap on total jobs submitted by the campaign
- `--stage-candidate-limit`: trims each tranche to the first `N` generated scenarios
- `--shortlist-size`: how many candidates proceed into the stress pack
- `research-campaign-stop`: stops orchestration for one campaign and cancels queued jobs by default
- `research-director-start`: starts a director with a built-in deterministic queue or a supplied plan file
- `research-director-stop`: stops higher-level orchestration; optionally also stops the active campaign
- `research-director-status`: shows which campaign the director is currently supervising
- `research-dashboard`: serves the local dashboard on `--dashboard-host` / `--dashboard-port`
- the dashboard includes a `/guide` page for non-technical / non-trading users who want a high-level explanation of the application
- the dashboard now includes `/directors/<director_id>` so the operator can inspect the full director queue and plan progress
- `--director-plan-file`: supplies an explicit queue of campaign configs for the director
- `--disable-director-adoption`: prevents the director from adopting an already-running matching campaign
- `--stop-active-campaign`: when stopping a director, also stop its active campaign
- `--keep-queued-jobs`: leaves already-queued jobs in place when stopping a campaign
- `--stop-reason`: records why the operator stopped the campaign

Director plan file shape:

```json
{
  "plan_name": "broad_operability",
  "campaigns": [
    {
      "config_path": "configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml",
      "campaign_name": "broad-operability-primary",
      "campaign_max_hours": 24,
      "campaign_max_jobs": 1500,
      "stage_candidate_limit": 120,
      "shortlist_size": 3,
      "quality_gate": "all"
    }
  ]
}
```

Plan-file notes:

- `config_path` is required and must point to an existing config file
- `plan_name` is optional but recommended for dashboard readability
- per-entry overrides are optional; if omitted, the director-level defaults are used
- a tracked example plan is available at [`configs/directors/broad_operability.json`](c:/Dev/TrottersIndependantTraders/configs/directors/broad_operability.json)

Notification hooks:

- `--notification-command`: optional shell command to run on selected campaign events
- `--notify-events`: comma-separated event list for the hook; defaults to `campaign_finished,campaign_stopped,campaign_failed,strategy_promoted`
- `strategy_promoted`: dedicated success event emitted when a candidate is actually frozen/promoted, separate from the broader `campaign_finished` event
- the hook receives `TROTTERS_CAMPAIGN_ID`, `TROTTERS_CAMPAIGN_NAME`, `TROTTERS_EVENT_TYPE`, `TROTTERS_EVENT_MESSAGE`, and `TROTTERS_NOTIFICATION_PAYLOAD_PATH`
- hook failures do not stop the campaign manager; they are written into the notification artifact instead

Runtime outputs:

- runtime database: [`runtime/research_runtime/state/research_runtime.sqlite3`](c:/Dev/TrottersIndependantTraders/runtime/research_runtime/state/research_runtime.sqlite3)
- runtime exports: [`runtime/research_runtime/exports`](c:/Dev/TrottersIndependantTraders/runtime/research_runtime/exports)
- director spec files: [`runtime/research_runtime/director_specs`](c:/Dev/TrottersIndependantTraders/runtime/research_runtime/director_specs)
- campaign notifications jsonl: [`runtime/research_runtime/exports/campaign_notifications.jsonl`](c:/Dev/TrottersIndependantTraders/runtime/research_runtime/exports/campaign_notifications.jsonl)
- per-event notification payloads and hook logs: [`runtime/research_runtime/exports/campaign_notifications`](c:/Dev/TrottersIndependantTraders/runtime/research_runtime/exports/campaign_notifications)
- research catalog: [`runtime/catalog/research_catalog`](c:/Dev/TrottersIndependantTraders/runtime/catalog/research_catalog)
- profile history: [`runtime/catalog/profile_history`](c:/Dev/TrottersIndependantTraders/runtime/catalog/profile_history)

What to expect while a campaign is running:

- workers will mostly execute `promotion-check` jobs
- the campaign remains in `running` status until a tranche is processed and a final decision is made
- once a stage completes, the campaign manager writes updated tranche/program artifacts into [`runtime/catalog`](c:/Dev/TrottersIndependantTraders/runtime/catalog)
- stopping a campaign prevents new tranche submission; any already-running jobs are allowed to finish but the manager will not advance that campaign further
- if no candidate survives the configured pivots and stress pack within budget, the campaign finishes as exhausted rather than running forever
- if a director is active, an exhausted campaign can be followed automatically by the next approved campaign without manual intervention

## CSV Schema

Expected columns:

```text
trade_date,instrument,open,high,low,close,volume
```

Example:

```text
2024-01-02,TSCO.L,289.0,291.5,287.2,290.4,1200000
```

## Project Layout

```text
configs/        Backtest configuration
data/           Local input datasets
src/            Application code
tests/          Basic scaffold tests
context/           Stable architecture and research context
feature_workflows/ Active feature and job planning context
```

## Data Layers

The ingestion path now has explicit layers:

```text
data/raw/       Unmodified source copies
data/staging/   Source-specific staged tables
data/canonical/ Backtest-ready canonical tables
data/features/  Materialized research features
```

The current adapter is `sample_csv`, but the pipeline is now set up so larger vendor-specific adapters can stage into `data/staging/` without changing the backtest engine.
Canonical datasets now also include `dataset_manifest.json`, which records the source name and the adjustment policy used to build `adjusted_close`.
`data/raw/` is treated as local working input and is intentionally not tracked in Git, aside from a placeholder file that keeps the directory available.

CLI commands now isolate intermediate files by command scope. In practice that means `stage`, `ingest`, and `backtest` write under command-specific subdirectories beneath `data/staging/` and `data/canonical/` instead of sharing one mutable workspace. Raw vendor payloads under `data/raw/` remain shared.

## Supported Source Adapters

- `bulk_csv`: vendor-agnostic flat-file import for larger historical datasets
- `sample_csv`: direct CSV-to-staging copy for the built-in toy dataset
- `alpha_vantage_json`: reads a directory of raw Alpha Vantage daily JSON payloads and stages them into `daily_bars.csv`
- `eodhd_json`: reads a directory of raw EODHD daily JSON payloads and stages them into `daily_bars.csv`

## Bulk Historical Import Workflow

For multi-year research, the preferred path is now `bulk_csv`, not Alpha Vantage free.

Use [`configs/bulk_historical.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/bulk_historical.toml) and place your files in [`data/bulk`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/data/bulk/README.md):

```bash
python -m trotters_trader.cli stage --config configs/bulk_historical.toml
python -m trotters_trader.cli ingest --config configs/bulk_historical.toml
python -m trotters_trader.cli backtest --config configs/bulk_historical.toml
```

Expected schemas:

`daily_bars.csv`

```text
trade_date,instrument,open,high,low,close,volume
```

Optional extra column:

```text
adjusted_close
```

`instruments.csv`

```text
instrument,exchange_mic,currency,isin,sedol,company_number,status,listing_date,delisting_date,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket
```

`corporate_actions.csv`

```text
instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount
```

The staging layer validates required columns and blank required values before canonicalization. If `adjusted_close` is absent in bulk bars, staging defaults it to `close`.
If you set `adjustment_policy = "vendor_adjusted_close"`, the source must actually provide `adjusted_close`; staging will fail fast otherwise.

## EODHD Download Workflow

Use [`configs/eodhd.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd.toml) with `EODHD_API_KEY` stored in `.env`.
The config now separates:

- `download_instruments_csv`: [`data/universes/uk_starter_watchlist.csv`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/data/universes/uk_starter_watchlist.csv)
- `source_instruments_csv`: [`data/universes/uk_starter_instrument_master.csv`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/data/universes/uk_starter_instrument_master.csv)

The watchlist is only a symbol list for acquisition. It is not treated as a complete reference master.
The instrument master now supports optional `sector`, `industry`, `benchmark_bucket`, `liquidity_bucket`, `tradability_status`, and `universe_bucket` fields so universe filtering and basket construction can use non-price metadata.
It also supports `listing_date` and `delisting_date` so validation and universe selection can distinguish active, inactive, and delisted names without leaking future information.

Download named symbols into raw JSON:

```bash
python -m trotters_trader.cli download-eodhd --config configs/eodhd.toml --instrument TSCO.L --from-date 2018-01-01
```

Then stage and ingest:

```bash
python -m trotters_trader.cli stage --config configs/eodhd.toml
python -m trotters_trader.cli ingest --config configs/eodhd.toml
python -m trotters_trader.cli backtest --config configs/eodhd.toml
```

The downloader stores raw payloads in `data/raw/eodhd_json/`. The staging adapter preserves raw OHLC and uses EODHD `adjusted_close` when present. If `adjusted_close` is missing, staging falls back to `close`.

For a more credible large-universe research baseline, use [`configs/eodhd_momentum.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum.toml). That config switches to cross-sectional momentum with:

- `top_n = 8`
- `weighting = "vol_inverse"`
- quarterly-style rebalancing via `rebalance_frequency_days = 63`
- `target_gross_exposure = 0.60`
- `max_position_weight = 0.10`
- `initial_deployment_turnover_pct = 0.20`
- tighter churn controls and a positive momentum threshold

To explore nearby momentum variants:

```bash
python -m trotters_trader.cli momentum-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

To compare the named momentum research profiles:

```bash
python -m trotters_trader.cli compare-momentum-profiles --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli momentum-refine --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli risk-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli regime-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli sector-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

The profile intent is:

- `aggressive`: higher turnover and faster re-entry for stronger upside capture
- `balanced`: the current frozen baseline candidate
- `defensive`: lower turnover, tighter exposure, longer holding periods

The intended use is:

- `balanced`: default research profile for split validation and nearby parameter sweeps
- `aggressive`: wider deployment and faster re-entry, useful when testing upside capture against drawdown tolerance
- `defensive`: tighter exposure and slower turnover, useful when testing whether risk reduction is destroying excess return

Runnable profile configs are available at:

- [`configs/eodhd_momentum.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum.toml) for the current balanced baseline candidate
- [`configs/eodhd_momentum_aggressive.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_aggressive.toml)
- [`configs/eodhd_momentum_defensive.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_defensive.toml)
- [`configs/eodhd_momentum_core.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_core.toml) for the current core-universe subset
- [`configs/eodhd_momentum_broad.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_broad.toml) for the expanded research universe scaffold
- [`configs/eodhd_momentum_candidate.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_candidate.toml) as the starter-universe candidate template for tranche research

The broad-universe workflow keeps the validated 24-name starter set intact while preparing a wider UK watchlist and instrument master:

- [`data/universes/uk_broad_watchlist.csv`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/data/universes/uk_broad_watchlist.csv)
- [`data/universes/uk_broad_instrument_master.csv`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/data/universes/uk_broad_instrument_master.csv)

Use that config when you want to expand EODHD downloads and coverage:

```bash
python -m trotters_trader.cli download-eodhd --config configs/eodhd_momentum_broad.toml --from-date 2018-01-01
python -m trotters_trader.cli coverage --config configs/eodhd_momentum_broad.toml
```

Do not expect [`configs/eodhd_momentum_broad.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum_broad.toml) to backtest cleanly until the extra broad-universe raw JSON files exist under `data/raw/eodhd_json/`.
This broad configuration is now the default non-toy UK research universe in the repo.

`momentum-refine` is the narrow sweep around the balanced baseline. It only varies:

- `top_n` in `2, 3, 4`
- `min_score` in `0.02, 0.03`
- `rebalance_frequency_days` in `42, 63`

All other stability and execution controls stay pinned to the balanced baseline config so the report isolates the return/turnover trade-off near the current baseline.

On the current EODHD dataset, the later risk sweep produced a more realistic balanced baseline by widening the book and explicitly capping gross exposure:

- `top_n = 8`
- `min_score = 0.03`
- `rebalance_frequency_days = 63`
- `target_gross_exposure = 0.60`
- `max_position_weight = 0.10`
- `initial_deployment_turnover_pct = 0.20`

That profile was the first one to stay out of `fail` in both `train` and `holdout`.

The momentum config now carries an explicit three-stage research split:

- `train`: `2019-01-02` to `2022-12-30`
- `validation`: `2023-01-03` to `2024-12-31`
- `holdout`: `2025-01-01` to `2026-03-19`

Run it with:

```bash
python -m trotters_trader.cli validate-split --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

That command keeps pre-period history available for signal warmup, but clips trading, benchmarking, and reporting to the requested train, validation, or holdout window.

Current promotion-check result on the starter universe for [`configs/eodhd_momentum.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd_momentum.toml):

- `train`: `fail`, mainly on turnover and drawdown
- `validation`: `fail`, mainly on benchmark underperformance
- `holdout`: `fail`, mainly on benchmark underperformance
- walk-forward over the validation span: `3` windows, `0` pass windows, not eligible

So the balanced starter-universe profile remains the best current baseline candidate, but it is not promotable under the Phase 8 gate.

The current diagnosis for that holdout lag is structural, not just signal quality:

- the original profile only targeted `top_n = 4`
- `max_position_weight = 0.07` capped effective deployable exposure very low
- `max_rebalance_turnover_pct = 0.06` also made initial deployment from cash extremely slow

The allocator now supports explicit `target_gross_exposure` and a separate `initial_deployment_turnover_pct` so underinvested states can ramp into the target book faster while keeping the normal rebalance budget conservative.

To compare a small set of exposure and deployment repairs across both train and holdout, run:

```bash
python -m trotters_trader.cli risk-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

On the current EODHD dataset, that sweep shows:

- the original baseline still fails holdout badly because it is too underinvested
- explicit gross-exposure control plus faster initial deployment repairs that structural problem
- the balanced profile `gross60_deploy20_n8_w10` is the first scenario that remained non-failing in both `train` and `holdout`
- more aggressive deployment still improves holdout further, but at the cost of failing train-period drawdown

On the current full sample, that balanced config still fails because max drawdown is about `23.07%`, above the `20%` fail threshold. So the remaining problem is now risk control, not deployment.

For structural regime experiments, use:

```bash
python -m trotters_trader.cli regime-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

On the current starter universe, the `off` scenario still ranks best across `train`, `validation`, and `holdout`, so the current EODHD momentum config keeps the benchmark-regime filter disabled.

For basket-construction sector tests, use:

```bash
python -m trotters_trader.cli sector-sweep --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

On the current starter universe, the baseline `off` scenario still ranks best. Sector caps at `3`, `2`, and `1` all reduce either train-period drawdown quality or holdout excess return enough to be inferior to the uncapped baseline. So sector metadata and sector-cap experiments are now in the framework, but sector caps are not part of the current momentum baseline.

The runtime now also reports basket-level diagnostics and benchmark-relative risk diagnostics in each run summary:

- average portfolio names
- unique sectors and industries
- sector and industry concentration
- active sector and benchmark-bucket deviation vs the equal-weight benchmark universe
- beta, correlation, tracking error, and relative volatility vs the primary benchmark

To run walk-forward validation on the current EODHD momentum baseline:

```bash
python -m trotters_trader.cli walk-forward --config configs/eodhd_momentum.toml --quality-gate pass_warn
```

To run the full Phase 8 promotion workflow:

```bash
python -m trotters_trader.cli promotion-check --config configs/eodhd_momentum.toml --quality-gate pass_warn
python -m trotters_trader.cli promotion-check --config configs/eodhd_momentum_broad.toml --quality-gate pass_warn
```

That command now writes:

- split-validation comparison artifacts
- walk-forward comparison artifacts
- `promotion_decision.json`
- `promotion_summary.md`
- append-only profile history under `runs/profile_history/`

## Features And Catalog

To materialize the current feature set explicitly:

```bash
python -m trotters_trader.cli materialize-features --config configs/eodhd_momentum.toml
```

That writes:

- `data/features/<set_name>/features.csv`
- `data/features/<set_name>/manifest.json`

For now the feature set includes the momentum return, realized volatility, and trailing drawdown inputs needed by the cross-sectional momentum strategy.

The repo now also maintains a machine-readable research catalog under `runs/research_catalog/`:

- `catalog.jsonl`
- `experiment_catalog.json`
- `experiment_catalog.csv`
- `latest_profile_artifacts.json`

Single backtests, comparison reports, promotion reports, and research decisions all register there automatically.

Comparison reports now also write:

- `research_decision.json`
- `research_decision.md`

Those artifacts explain which run ranked highest under the evaluation policy and when a higher raw-return run was rejected on discipline rather than performance alone.

The tranche workflow now writes separate tranche artifacts for starter-universe research:

- `tranche_summary.md`
- `tranche_rankings.csv`
- `tranche_decision.json`

Those artifacts are produced by `universe-slice-sweep`, `ranking-sweep`, `construction-sweep`, and `starter-tranche`, and they are cataloged alongside normal reports under `runs/research_catalog/`.

Current promotion outcome:

- starter balanced profile: frozen, not promoted, not eligible
- broad balanced profile: frozen, not promoted, not eligible

Before backtesting a larger universe, audit what you actually downloaded:

```bash
python -m trotters_trader.cli coverage --config configs/eodhd.toml
```

That report tells you:

- expected instrument count from the universe file
- covered instrument count
- missing instruments
- earliest and latest available dates
- per-instrument row counts

It also writes persistent artifacts to `data/coverage/`:

- `<run_name>_summary.json`
- `<run_name>_missing.csv`

Use the missing-symbol CSV as the next download queue when you expand the universe.

## Alpha Vantage Download Workflow

1. Put your key in `.env` as `AV_KEY=...`
2. Download raw payloads:

```bash
python -m trotters_trader.cli download-alpha-vantage --config configs/backtest.toml --limit 5
```

For free-tier usage, target instruments explicitly and let the downloader skip existing files by default:

```bash
python -m trotters_trader.cli download-alpha-vantage --config configs/backtest.toml --instrument SBRY.L --raw-series --outputsize compact
```

Use `--instrument` multiple times to request more than one symbol. Add `--force` only when you intentionally want to overwrite an existing raw JSON payload.

3. Switch `data.source_name` to `alpha_vantage_json` and point `data.source_bars_csv` at the raw JSON directory when you want to stage from those files.
4. Run `stage`, then `ingest`, then `backtest`

For `alpha_vantage_json`, set `data.source_name = "alpha_vantage_json"` and point `data.source_bars_csv` at a directory of JSON files. Each file should be named after the internal instrument you want in the backtest, for example `TSCO.L.json`, and contain an Alpha Vantage daily time-series payload.
