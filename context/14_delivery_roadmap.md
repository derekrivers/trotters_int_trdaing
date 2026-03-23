# Delivery Roadmap

## Status Summary

All roadmap phases before Phase 9 are implemented at the platform level.

- Phase 1 is complete.
- Phase 2 is complete.
- Phase 3 is complete.
- Phase 4 is complete.
- Phase 5 is complete.
- Phase 6 is complete.
- Phase 7 is complete.
- Phase 8 is complete.

That does not yet mean the roadmap outcome has been achieved.
The repo now has a real historical research workflow, but it still does not have a promotion-eligible momentum baseline.

The current bottleneck is no longer missing infrastructure.
It is converting recent candidate improvements into a profile that passes validation, holdout, and walk-forward promotion gates at the same time.

Current repo state:

- the frozen `momentum_balanced` profile remains not promotable under the current policy
- recent universe-slice and ranking tranches produced candidates with some improvement, but none passed the full promotion gate
- recent momentum-refinement runs produced promising full-sample candidates that have not yet been carried through the tranche and promotion path

In other words:

- engineering phases are complete through Phase 8
- research target completion is still in progress

## Phase 1: Context And Decisions

Status: complete

- Confirmed first strategy family: cross-sectional momentum is the current research baseline
- Confirmed first data scope: daily bars only
- Confirmed initial Python project structure and CLI workflow
- Confirmed UK equity cost assumptions for deterministic backtests

## Phase 2: Data Foundation

Status: complete

- Built source adapters for:
  - sample CSV
  - Alpha Vantage JSON
  - EODHD JSON
  - bulk CSV import
- Built raw -> staging -> canonical data flow
- Persist raw, staged, canonical, and run artifacts locally
- Added coverage reporting and download watchlist support

Delivered:

- instrument lifecycle fields are supported in the instrument master via `listing_date` and `delisting_date`
- validation now catches bars and corporate actions that extend beyond an instrument's valid trading life
- active-only universe selection now allows historically valid delisted names when they overlap the research period
- adjustment policy is explicit per source via `adjustment_policy`
- canonical datasets now persist `dataset_manifest.json` with adjustment semantics
- staging fails fast when a configured adjustment policy requires inputs the source does not provide
- split and dividend action handling is supported in the canonical adjustment path
- coverage reports now surface metadata gaps as well as symbol/date coverage
- the broad EODHD universe is now documented as the default non-toy UK research universe

Outcome:

- the repo now has explicit lifecycle, adjustment, and coverage semantics rather than treating them as informal conventions
- the remaining research bottlenecks are strategy quality and universe breadth, not data-foundation ambiguity

## Phase 3: Backtest Core

Status: complete

- Strategy interface implemented
- Portfolio construction logic implemented
- Execution simulator implemented
- Daily NAV, fills, closed trades, and ledger-style outputs implemented
- Benchmark models implemented

## Phase 4: Validation

Status: complete

- Dataset integrity checks implemented
- Reproducibility improved with isolated staging/canonical workspaces
- Benchmark comparison implemented
- Split validation implemented
- Walk-forward validation implemented
- Basket-level and benchmark-relative diagnostics implemented
- Promotion criteria and promotion-check workflow implemented
- Comparison reporting across runs and configs implemented

## Phase 5: Research Workflow

Status: complete

- CLI reports implemented
- experiment configs implemented
- parameter sweeps implemented
- sensitivity, threshold, momentum, risk, and regime sweeps implemented
- named momentum profiles implemented
- profile history and promotion artifacts implemented

Delivered:

- a materialized feature layer now persists momentum inputs under `data/features/`
- cross-sectional momentum can consume precomputed features during backtests
- feature manifests record the lookback windows and source canonical dataset for a feature set
- reports now state whether a run used precomputed features and which feature set it used
- a machine-readable research catalog now spans single runs, comparison reports, promotion reports, and research decisions under `runs/research_catalog/`
- latest profile artifacts can now be resolved without manual folder inspection
- comparison reports now emit research decisions in addition to rankings
- research decisions explain when a higher raw-return run was rejected on evaluation discipline rather than promoted on return alone

Outcome:

- the repo now has a first-class research workflow rather than a loose collection of run folders
- future strategy changes can be traced through feature sets, comparison evidence, promotion checks, and cataloged decisions

## Phase 6: Universe Enrichment

Status: complete

- Expand the UK universe beyond the starter list
- Add sector, industry, and benchmark-membership metadata to the instrument master
- Add liquidity buckets and simple tradability flags
- Define a research-grade core universe and a wider exploration universe

Why this matters:

- current price-only controls are not enough
- sector concentration and universe composition likely explain part of the drawdown behavior

Delivered:

- instrument master now supports sector, industry, benchmark bucket, liquidity bucket, tradability status, and universe bucket
- starter UK universe now distinguishes `core` and `explore` names
- coverage audits now summarize metadata composition as well as symbol/date coverage
- universe filters can now select by benchmark bucket, tradability status, universe bucket, and excluded liquidity buckets

Still constrained by:

- starter-universe size
- lack of survivorship / delisting handling

## Phase 7: Cross-Sectional Risk Controls

Status: complete

- Add sector / industry exposure caps
- Add benchmark-relative position sizing or risk budgeting inside the selected basket
- Add basket-level volatility and beta diagnostics
- Add concentration controls beyond single-name caps

Why this matters:

- simple regime filters and drawdown screens did not improve the actual trade-off
- the next improvement has to come from how the selected basket is constructed

Delivered:

- sector, industry, and benchmark-bucket caps are implemented in basket construction
- benchmark-relative weighting (`beta_vol_inverse`) remains available as an experimental mode
- basket diagnostics now report concentration and active metadata deviations
- risk diagnostics now report beta, correlation, tracking error, and relative volatility against the primary benchmark
- sector-sweep experiments are implemented and persisted like the other research sweeps

Outcome:

- on the current starter universe, none of the tested caps or basket overlays beat the uncapped balanced momentum baseline
- Phase 7 is complete as an engineering phase, but it did not produce a promoted replacement profile

## Phase 8: Research Discipline

Status: complete

- Add walk-forward validation
- Separate train / validation / holdout more explicitly
- Freeze promoted profiles and track when they change
- Add minimum evidence rules before promoting a new config

Why this matters:

- the repo can now generate many plausible variants
- without tighter research discipline, parameter churn becomes the main risk

Current state:

- configs now carry explicit research-profile metadata (`profile_name`, `profile_version`, `frozen_on`, `promoted`)
- explicit `train`, `validation`, and `holdout` periods are supported
- walk-forward validation now uses the validation span explicitly when it exists
- promotion-policy thresholds are implemented for split evidence and walk-forward evidence
- `promotion-check` now writes persistent promotion reports and profile history entries
- the current balanced starter-universe profile is frozen but not promotable under the Phase 8 gate
- the current broad-universe profile is also not promotable under the Phase 8 gate

Outcome:

- the repo now enforces research discipline mechanically rather than relying on informal judgment
- the gating system is working as intended, but it is still rejecting the current baseline and recent tranche candidates
- the next work is not to build more gating infrastructure; it is to drive a stronger candidate through the existing gate

## Phase 9: Optional Live-Readiness Preparation

Status: not started, not immediate priority

- broker abstraction
- order generation handoff
- live market-calendar handling
- operational alerts and kill switches

This should stay later. The current system is still a research platform, not a live trading system.

## Phase 10: Operator Clarity And Promotion Handoff

Status: in progress

Phase 10 foundations are now materially implemented, but the phase is not finished.

Implemented foundations:

- promotion handoff pages, candidate scorecards, and candidate comparison views exist
- director plan files and pause/resume/skip controls exist
- dashboard history, notification severity, and operator summaries exist
- paper-trade decision export and readiness boundary artifacts exist
- the OpenClaw operator layer now exists with one always-on supervisor, event-driven specialist agents, summaries, and dispatch telemetry
- a basic GitHub Actions test workflow exists

Why the phase is still incomplete:

- the main operator view still needs a clearer answer for the current best candidate and next action
- paper trading still lacks separate rehearsal state, a daily runner, operator decision logging, and explicit hard blocking
- OpenClaw repeated-incident trust and plugin-trust hygiene still need further hardening
- the strongest `risk + sector` research branch is still not promoted or explicitly retired

Active planning model:

- `context/` remains the stable reference layer
- `feature_workflows/` is now the active planning and execution-context layer

Current workflow order inside Phase 10:

1. `FW-001_docs-and-planning-sync` (`done`)
2. `FW-002_candidate-handoff-and-dashboard`
3. `FW-003_paper-trading-rehearsal-core`
4. `FW-004_openclaw-trust-hardening`
5. `FW-005_risk-sector-promotion-program`

Out of scope for the remaining Phase 10 work:

- broker integration
- real-money execution
- broad autonomous live-trading control
- a large refactor-only program detached from feature work
- CI expansion beyond the current basic test workflow

## Current Recommended Build Target

The correct target now is no longer "first backtest scaffold".
It is:

1. one credible UK equity research universe
2. one promotion-eligible momentum baseline
3. one strict split-validation workflow
4. one basket-level risk-control layer
5. one reproducible promotion path for future strategy changes
6. one operator-readable promotion handoff
7. one paper-trading-ready handoff boundary after promotion

That is the next engineering baseline worth optimizing.

## Immediate Next Research Target

The highest-signal next step is:

1. take the strongest momentum-refinement candidate as the new seed profile
2. run it through validation, walk-forward, and promotion-check as a named candidate
3. if it improves split outcomes, rerun universe-slice, ranking, and construction tranches from that seed
4. only freeze and promote a replacement profile if it passes the existing policy without exceptions

Today, the most credible seed is not the frozen `momentum_balanced` baseline.
It is the recent momentum-refinement family centered on:

- `top_n` in the 3 to 4 range
- `min_score` at 0.02 to 0.03
- `rebalance_frequency_days` at 63

That is the clearest repo-backed path from platform completion to research-target completion.

Latest checkpoint:

- the top four `rf-63` momentum-refinement seeds were run through `promotion-check`
- none became promotion-eligible
- the strongest seeds improved walk-forward evidence to 2 passing windows, but all still failed validation and holdout on benchmark-relative excess return
- no seed from that family currently justifies downstream tranche expansion as a promotion candidate

Broader-universe checkpoint:

- a broad-universe candidate built from the strongest `top_n = 4`, `min_score = 0.02`, `rebalance_frequency_days = 63` seed materially improved on the frozen broad baseline
- that candidate reached promotion-eligible walk-forward evidence and improved validation to a warn-level result
- it still failed holdout badly on benchmark-relative excess return
- a follow-up broad-universe ranking tranche did not produce any candidate that improved both validation and holdout

Current implication:

- the repo now has a clear negative result for both the starter and broad universes under the current momentum family
- the next research step should pivot away from small momentum-parameter and ranking tweaks and toward a different research program aimed at the late-period holdout failure

Architecture checkpoint:

- broad-universe `beta_vol_inverse` weighting produced identical realized holdout fills to the plain `vol_inverse` broad candidate
- that means weighting-only variants are currently being neutralized by the same selected basket and downstream turnover-budget constraints
- this removes beta-weighting as a meaningful near-term research branch for the current broad candidate family

Construction checkpoint:

- the full broad-universe construction sweep was run from the strongest broad momentum seed
- 72 construction variants were evaluated across `top_n`, gross exposure, rebalance cadence, holding period, and buffer size
- no construction candidate improved both validation and holdout without failing policy
- this is a stronger result than the earlier tranche checks because it suggests the current broad momentum family is structurally exhausted, not just slightly mis-tuned

Alternative-family checkpoint:

- a `drawdown_penalized` broad momentum seed was tested and remained non-promotable
- it kept walk-forward evidence intact but slightly worsened validation and holdout relative to the best raw-score broad seed
- a broad mean-reversion seed was then tested as a deliberate family pivot
- that mean-reversion candidate was materially worse than the broad momentum seed on validation, holdout, and walk-forward evidence

Updated implication:

- broad long-only UK stock selection is not currently failing because of one missing momentum parameter or one missing weighting mode
- the strongest live branch remains the broad momentum seed with `top_n = 4`, `min_score = 0.02`, `rebalance_frequency_days = 63`, even though it is still not promotable
- the next credible research program should target benchmark-relative late-period robustness with a more substantive model change, not more local tuning of the current momentum engine

Parallel research checkpoint:

- the Docker coordinator and three-worker runtime is now working end to end for real research jobs, not just smoke tests
- a new `research-batch` submission path can materialize one shared canonical dataset and queue stage-specific `promotion-check` tournaments safely for worker containers
- the first real queued batch was a `universe-slice` tournament for `momentum_broad_candidate_beta_n4_ms002_rf63`
- that batch completed cleanly across the worker pool and reproduced the known control result: validation remained `warn`, holdout remained `fail`, and no universe-slice candidate improved the benchmark-relative holdout outcome
- this is notable progress on infrastructure and throughput, but not yet on strategy viability; the value is that future tranche programs can now be run in parallel instead of serially

Parallel follow-up checkpoint:

- the next queued batch was a `risk` tournament on `momentum_broad_candidate_beta_n4_ms002_rf63`
- that batch identified one materially better holdout branch: `gross65_deploy20_n8_w09_cb12`
- this candidate improved holdout excess return from roughly `-24.0%` to roughly `-15.4%`, but validation degraded to roughly `-14.3%` and walk-forward pass count fell from `2` to `1`
- a named follow-up seed was created from that risk branch and run through a queued `sector` tournament
- the best sector follow-up, `sec3`, produced the strongest combined split result seen so far on this broad candidate family: validation improved back to roughly `-3.8%` while holdout improved further to roughly `-12.9%`
- that is still not promotion-eligible and walk-forward evidence fell to `0` passing windows, but it is the clearest repo-backed sign yet that cross-sectional risk controls can move the holdout problem in the right direction
- a final queued `regime` overlay batch on top of the `risk + sector` seed did not improve the result, so regime controls remain a weak branch for this candidate family

Updated next implication:

- the strongest current research branch is no longer the plain broad momentum seed; it is now the `risk + sector` family centered on the `gross65_deploy20_n8_w09_cb12` seed with a `max_positions_per_sector = 3` follow-up
- the next credible work should stay in that family and target restoring walk-forward robustness while preserving the holdout improvement, rather than returning to universe slicing, ranking tweaks, or benchmark-regime overlays

Risk-sector retirement checkpoint on March 22, 2026:

- the `sec3` follow-up was rerun directly into `runtime/catalog` under the current promotion policy
- validation remained benchmark-negative at roughly `-3.8%`
- holdout remained benchmark-negative at roughly `-12.9%`
- walk-forward finished at `0 / 3` passing windows
- that means the `risk + sector` branch has now exhausted its defined path without producing a promotion-eligible candidate
- the branch is no longer "current best"; it is explicitly retired in `runtime/catalog/risk_sector_promotion_program/research_program.json`
- the next research iteration should select a different family or a materially new hypothesis rather than reopening this path without new evidence


Beta-defensive continuation checkpoint on March 23, 2026:

- the next approved research family was set to `beta_defensive_continuation` using the existing `momentum_broad_candidate_beta_defensive_n4_ms002_rf63` seed
- that branch was chosen because it is a repo-defined materially different robustness hypothesis, while the `risk + sector` family is explicitly retired and the broad/drawdown operability paths are already exhausted
- the OpenClaw supervisor summary now carries the exhausted director plan forward as `current_plan_id`, so `trotters_runbook.next_work_item` can advance from `broad_operability` to the next approved item instead of restarting from queue position one
- a new research-program artifact was written to `runtime/catalog/beta_defensive_continuation_program/research_program.json` with status `active` and `recommended_action = run_next_step`
- the live Compose-backed runtime was resumed on `beta-defensive-director` / `beta-defensive-primary`, restoring active work after the earlier idle exhausted state


Queue expansion checkpoint on March 23, 2026:

- the OpenClaw runbook was expanded from `2` to `3` approved items by adding `refine_seed_continuation` after `beta_defensive_continuation`
- this refine branch is explicitly a lower-priority fallback, not a new highest-conviction direction
- `momentum_broad_candidate_refine_n4_ms002_rf63` was chosen because it is the remaining repo-defined broad-family seed that is still operationally credible enough to run
- `mean_reversion_broad_candidate_n8_ms005_rf21` remains outside the queue because the roadmap already records it as materially worse than the broad momentum control
- the queue-growth rule is now: workflow-first evidence review, then research-program definition, then director plan, then runbook entry

