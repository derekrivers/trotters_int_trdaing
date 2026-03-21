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
