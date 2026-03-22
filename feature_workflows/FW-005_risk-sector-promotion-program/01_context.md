# Context

## Problem

- the strongest repo-backed branch was the broad `risk + sector` family, but the evidence was spread across runtime artifacts, configs, and roadmap notes
- that made it harder to keep a disciplined research path and easier to re-open exhausted branches without noticing

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- the resolved branch is centered on:
  - `configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml`
  - `configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml`
- the fresh `sec3` follow-up run on March 22, 2026 confirmed that the branch still failed promotion because validation and holdout stayed benchmark-negative and walk-forward robustness fell to `0 / 3` passing windows
- the branch is now retired under explicit stop conditions instead of remaining an implicit "current best" path

## Non-Goals

- do not weaken promotion policy to force a win
- do not open a brand-new research family until this branch is either promoted or explicitly retired
- do not treat infrastructure throughput improvements as strategy validity
