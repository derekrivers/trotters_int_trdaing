# Project Overview

## Purpose

Build and maintain a project context base for UK equity trading research and implementation.

The immediate goal is to turn the original research dump into a structured reference set that can support:

- compliance-aware system design,
- tax-aware record keeping,
- market-structure-aware execution logic,
- research and data-pipeline implementation.

## Current Source Base

Primary source document:

- `deep-research-report.md`

This file contains:

- a long-form report,
- ranked source analysis,
- contradictions handling,
- a proposed multi-file codex structure,
- reference links and example API calls.

## Working Assumptions

- Geography: UK-focused equities.
- Priority order: governance, tax, venue mechanics, issuer data, then market-data tooling.
- Budget posture from the source report: free sources first.
- Intended use: project context and engineering guidance, not personal tax or legal advice.
- Initial build target: a simple historical-data trading bot for backtesting, not live trading.
- Earliest practical data scope: daily or end-of-day data, because free sources are materially weaker for licensed real-time and deep intraday usage.

## Project Context Structure

- `01_sources_ranked.md`: primary source stack and direct links.
- `02_regulatory_compliance.md`: FCA-led compliance constraints.
- `03_tax_treatment.md`: HMRC-led tax treatment notes.
- `04_market_microstructure.md`: LSE execution mechanics context.
- `05_execution_best_practices.md`: execution models and TCA references.
- `06_risk_management.md`: trading and data control framework.
- `07_strategy_templates.md`: research templates and academic anchors.
- `08_data_pipelines_and_api_calls.md`: ingestion patterns and examples.
- `09_contradictions_resolution.md`: source conflict handling.
- `10_academic_and_industry_sources.md`: supporting research references.
- `11_architecture_principles.md`: system-level engineering rules for the bot.
- `12_backtesting_system_architecture.md`: target component architecture for the first build.
- `13_domain_model.md`: core entities and storage contracts.
- `14_delivery_roadmap.md`: delivery sequence from context to code.

## Expansion Rules

- Add decisions and project-specific conventions here as they are made.
- Add source-specific detail to the relevant topic file, not this overview.
- When a source changes materially, note the effective date in the affected file.

## Next Context To Add

- actual project objectives and scope boundaries,
- chosen tech stack and repo architecture,
- instrument universe and exchange coverage,
- data vendor decisions,
- execution environment and broker constraints,
- testing and validation standards.

## Current Architectural Direction

The current source review supports a narrow first milestone:

- research and backtesting only,
- UK equities,
- historical daily bars,
- offline simulation of orders and fills,
- explicit cost modeling including commissions, spread assumptions, and UK stamp duty where applicable.

This is the right first boundary because:

- FCA NSM is archive-oriented rather than real-time.
- Companies House is useful for issuer metadata and event context, not price formation.
- LSE public delayed data and public RNS access do not justify building a live or low-latency system at this stage.
- Alpha Vantage is usable for prototyping historical research, but its free plan is too constrained for a production-grade intraday workflow.
