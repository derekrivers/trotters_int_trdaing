# Phase 10 Task List

## Purpose

This task list turns Phase 10 of the delivery roadmap into commit-sized execution steps.

The working rule for this phase is:

1. complete one logical step
2. run the relevant tests successfully
3. make one local commit
4. only then move to the next step

GitHub workflow / CI automation is intentionally deferred until the end of this phase or later.

## Workstreams

The next delivery phase has four main workstreams:

1. promotion handoff and candidate explanation
2. research-director policy externalization and controls
3. dashboard observability and operator summaries
4. paper-trading preparation boundary

## Execution Order

### Step 1: Promotion Handoff Dashboard

Goal:

- add dashboard pages that explain promoted or shortlisted strategies in plain English

Deliverables:

- promoted-candidate summary page
- candidate comparison page
- plain-English explanation blocks:
  - what the strategy does
  - why it passed
  - where it is weak
  - what should happen next

Test gate:

- add/extend dashboard tests
- run targeted dashboard tests
- run host suite if shared runtime/report code changes

Commit boundary:

- one commit for promotion handoff pages and tests

### Step 2: Candidate Scorecards And Operator Recommendation

Goal:

- turn promotion artifacts into operator-facing scorecards

Deliverables:

- strategy scorecard artifact
- explicit recommendation states:
  - `reject`
  - `needs_more_research`
  - `paper_trade_next`
- side-by-side control vs candidate comparison

Test gate:

- report tests
- dashboard tests
- host suite if ranking/report logic changed

Commit boundary:

- one commit for scorecards, recommendation logic, and tests

Implementation checklist:

- define the operator-facing scorecard shape before editing code:
  - candidate identity
  - control identity
  - promotion status
  - recommendation state
  - key strengths
  - key weaknesses
  - next action
- decide the mapping from runtime/report outcomes to operator recommendation states:
  - `paper_trade_next`
  - `needs_more_research`
  - `reject`
- add scorecard generation in the reporting layer rather than only in dashboard HTML
- ensure the scorecard can be generated from persisted campaign state:
  - `control_row`
  - `shortlisted`
  - `stress_results`
  - `final_decision`
- add plain-English explanation fields in the scorecard artifact:
  - why this candidate is the current best
  - what evidence is still missing
  - whether the result is promotion-worthy or still exploratory
- add a side-by-side control vs selected-candidate summary artifact
- expose scorecard data in the dashboard handoff page
- show the explicit operator recommendation prominently in the dashboard
- link from campaign detail and handoff pages to the scorecard artifact if present

Suggested file touch list:

- `src/trotters_trader/reports.py`
- `src/trotters_trader/dashboard.py`
- `tests/test_reports.py`
- `tests/test_dashboard.py`

Execution order:

1. add scorecard artifact writer and serializer in the reports layer
2. add recommendation mapping logic with deterministic rules
3. add dashboard rendering for the scorecard and recommendation banner
4. add or extend tests for artifact contents and dashboard rendering
5. run the test gate
6. commit only after a clean working tree

Definition of done:

- one scorecard artifact exists for a finished operability campaign
- recommendation is visible without reading raw JSON
- control vs candidate comparison is readable by a non-expert operator
- tests prove both artifact generation and dashboard rendering

### Step 3: External Director Plan Files

Goal:

- move the research-director queue from hard-coded defaults toward explicit plan files

Deliverables:

- first-class director plan file format
- plan loading, validation, and persistence improvements
- dashboard visibility for the full plan queue

Test gate:

- runtime tests for plan loading and state transitions
- CLI tests for plan file options
- host suite

Commit boundary:

- one commit for plan-file support and tests

Implementation checklist:

- define a first-class director plan file format before changing runtime behavior:
  - plan name
  - seed / ordered campaign queue
  - per-entry config path
  - optional campaign name override
  - per-entry budget controls if needed later
  - fallback behavior when a campaign exhausts
- decide where plan files live in the repo:
  - likely `configs/directors/` or similar
- add loader and validator logic that fails clearly on:
  - missing config paths
  - malformed plan structure
  - empty queue
  - duplicate queue indexes if explicit indexes are allowed
- update director start logic to accept a plan file instead of only built-in defaults
- persist the normalized plan into director state so running directors remain inspectable
- preserve backwards compatibility:
  - if no plan file is supplied, keep the current default queue behavior
- add dashboard visibility for:
  - total planned campaigns
  - current queue position
  - pending queue entries
  - completed / exhausted queue entries
- add CLI options for plan-file startup and status inspection
- ensure adoptable active campaigns still work when a matching plan entry already exists

Suggested file touch list:

- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/cli.py`
- `src/trotters_trader/dashboard.py`
- `tests/test_research_runtime.py`
- `tests/test_cli.py`
- `tests/test_dashboard.py`
- new plan fixture(s) under `tests/fixtures/` if useful

Execution order:

1. define and document the director plan schema
2. implement plan loading and validation
3. wire plan-file support into director startup
4. persist normalized plan state for later inspection
5. surface plan queue state in dashboard and status output
6. add runtime, CLI, and dashboard tests
7. run the full Step 3 test gate
8. commit only after a clean working tree

Definition of done:

- a director can be started from an explicit plan file
- the active and pending queue is visible without reading source code
- malformed plan files fail early with clear errors
- old behavior still works when no plan file is provided
- tests cover happy path and invalid-plan path

### Step 4: Director Operator Controls

Goal:

- give the operator safe control over autonomous search without editing code

Deliverables:

- pause director
- resume director
- skip next planned campaign
- dashboard controls and status display

Test gate:

- runtime tests for pause/resume/skip
- dashboard tests for control forms and status rendering
- host suite

Commit boundary:

- one commit for director controls and tests

### Step 5: Dashboard History And Event Summaries

Goal:

- make the dashboard useful over time rather than only as a live status page

Deliverables:

- recent campaign outcomes summary
- recent director outcomes summary
- success / failure / exhausted counts
- “what changed since last check” section

Test gate:

- dashboard tests
- host suite if runtime export shape changes

Commit boundary:

- one commit for historical summaries and tests

### Step 6: Notification Severity And Success Banners

Goal:

- make important events obvious to a non-expert operator

Deliverables:

- severity levels for notifications
- promotion success banner
- clearer exhausted / failed / stopped messaging

Test gate:

- dashboard tests
- runtime notification tests

Commit boundary:

- one commit for notification UX and tests

### Step 7: Paper-Trading Preparation Docs

Goal:

- define the next boundary after promotion without jumping to live trading

Deliverables:

- paper-trading architecture note
- operator checklist for post-promotion review
- boundary doc:
  - what exists now
  - what paper trading requires
  - what live trading would require later

Test gate:

- docs review only

Commit boundary:

- one docs-focused commit

### Step 8: Simulated Daily Decision Export

Goal:

- make a promoted strategy capable of producing a daily decision package for paper operations

Deliverables:

- daily target holdings export
- rebalance action summary
- expected turnover summary
- warnings for missing or stale inputs

Test gate:

- report/runtime tests
- host suite
- container suite if runtime path changes materially

Commit boundary:

- one commit for simulated daily export and tests

### Step 9: Paper-Trade Readiness Review

Goal:

- decide whether the repo is ready for a paper-trading phase

Deliverables:

- explicit readiness checklist
- gap list for paper execution
- recommendation:
  - ready for paper-trading build
  - needs more research tooling
  - needs more operator tooling

Test gate:

- docs review only unless code changes are included

Commit boundary:

- one docs/review commit if needed

## Commit Discipline

For every step above:

- do not mix unrelated runtime, dashboard, and docs changes unless they are inseparable
- keep tests with the feature they validate
- do not start the next step until the current step has:
  - passing relevant tests
  - a clean `git status`
  - a local commit

Suggested commit style:

- `feat: add promotion handoff dashboard pages`
- `feat: add candidate operator scorecards`
- `feat: externalize research director plans`
- `feat: add director pause resume and skip controls`
- `feat: add dashboard history summaries`
- `feat: improve notification severity and success banners`
- `docs: add paper-trading preparation guide`
- `feat: add simulated daily decision export`

## Deferred Until Later

Keep these explicitly out of the current phase unless priorities change:

- GitHub Actions / CI workflows
- broker integration
- live order routing
- local or remote LLM-driven control logic
- production deployment automation
