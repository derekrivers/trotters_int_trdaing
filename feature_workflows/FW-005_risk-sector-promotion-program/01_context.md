# Context

## Problem

- the strongest repo-backed branch is now the broad `risk + sector` family, but the evidence is spread across runtime artifacts, configs, and roadmap notes
- that makes it harder to keep a disciplined research path and easier to re-open exhausted branches without noticing

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- the current strongest branch is centered on:
  - `configs/eodhd_momentum_broad_candidate_risk_gross65_deploy20_n8_w09_cb12.toml`
  - `configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml`
- it improved holdout behavior materially but still failed promotion because walk-forward robustness fell away

## Non-Goals

- do not weaken promotion policy to force a win
- do not open a brand-new research family until this branch is either promoted or explicitly retired
- do not treat infrastructure throughput improvements as strategy validity
