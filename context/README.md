# Project Context

This directory is the maintained stable context base for the project.

It should contain durable project knowledge and current high-level status notes, not temporary feature execution checklists or rollout scratchpads.
Active planning now lives under `feature_workflows/`.

## How to use this folder

- Start with `00_project_overview.md` for scope and current direction.
- Use `01_sources_ranked.md` plus the core foundation notes for governance, execution, and data-pipeline context.
- Use `11_architecture_principles.md`, `12_backtesting_system_architecture.md`, and `13_domain_model.md` for software design context.
- Use `16_paper_trading_status.md` for the current paper-trading boundary.
- Use `20_openclaw_lessons_learned.md`, `21_openclaw_agent_guide.md`, and `18_openclaw_status_and_backlog.md` for OpenClaw context.
- Use `22_tech_stack_and_runtime_brief.md` for a current-state stack, container, and runtime handoff summary.
- Use `../feature_workflows/README.md` and `../feature_workflows/00_program_board.md` for active feature and job planning.

## File Index

- `00_project_overview.md`
- `01_sources_ranked.md`
- `02_legal_and_governance_constraints.md`
- `04_execution_and_market_structure.md`
- `06_risk_and_research_references.md`
- `07_strategy_templates.md`
- `08_data_pipelines_and_api_calls.md`
- `11_architecture_principles.md`
- `12_backtesting_system_architecture.md`
- `13_domain_model.md`
- `14_delivery_roadmap.md`
- `15_phase10_tasklist.md`
- `16_paper_trading_status.md`
- `18_openclaw_status_and_backlog.md`
- `20_openclaw_lessons_learned.md`
- `21_openclaw_agent_guide.md`
- `22_tech_stack_and_runtime_brief.md`

## Moved Out Of Context

Vendor-specific reference dumps now live under `references/vendors/`.

## Maintenance Rules

- Prefer primary sources over summaries.
- Record dates when rules, rates, or terms are time-sensitive.
- Keep `context/` for stable reference only.
- Put active feature planning and execution notes in `feature_workflows/`.
- Keep `deep-research-report.md` as the original source artifact unless and until we replace it deliberately.
