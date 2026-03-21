# Architecture Principles

## Objective

Design a simple trading bot that can be used first for historical backtesting on UK equities, while preserving a clean path to paper trading and eventually live execution.

## Scope Boundary For Version One

- Historical backtesting only
- UK equities only
- Daily or end-of-day bars only
- No broker integration
- No live order routing
- No dependence on real-time news

## Why This Scope Is Correct

- FCA NSM is explicitly archive-oriented and not a real-time service.
- Public LSE delayed data is informational and time-delayed.
- Public RNS access has licensing and distribution constraints.
- Alpha Vantage free access is sufficient for prototype-scale historical research, but not for a serious intraday or live stack.
- Companies House is useful for issuer and filing context, not for price discovery.

## Non-Negotiable Design Rules

- Separate research, backtesting, and live-trading concerns from the start.
- Treat data ingestion as a first-class subsystem, not a helper script.
- Preserve raw source payloads for auditability and debugging.
- Normalize external data into internal canonical schemas before strategies see it.
- Make every backtest run reproducible through config snapshots and immutable inputs.
- Model costs explicitly: fees, spread assumptions, slippage, and stamp duty where applicable.
- Keep strategies pure: they should consume market state and emit target positions or orders, not perform I/O.

## Recommended Technical Shape

- Language: Python
- Storage: Parquet for datasets, DuckDB for local analytics and joins
- Config: versioned YAML or TOML
- Validation: Pydantic or equivalent typed schemas at system boundaries
- Orchestration: simple CLI tasks first, scheduler later

## Layering Rule

The system should be split into these layers:

1. Source adapters
2. Canonical data models
3. Feature and signal generation
4. Portfolio construction
5. Execution simulation
6. Analytics and reporting

Strategies should depend only on the canonical models and feature inputs, never on raw vendor response formats.

## Primary Source Anchors

```text
FCA NSM investor user guide: https://www.fca.org.uk/publication/primary-market/nsm-investor-user-guide.pdf
FCA NSM help and FAQs: https://www.fca.org.uk/publication/primary-market/fca-nsm-help-and-faqs.pdf
Companies House authentication: https://developer.company-information.service.gov.uk/authentication
Companies House rate limiting: https://developer-specs.company-information.service.gov.uk/guides/rateLimiting
Alpha Vantage documentation: https://www.alphavantage.co/documentation/
Alpha Vantage support: https://www.alphavantage.co/support/
LSE delayed market data terms: https://www.londonstockexchange.com/delayed-market-data/terms-and-conditions.htm
RNS pricing and policy guidelines 2026: https://www.lseg.com/content/dam/lseg/en_us/documents/rns/rns-pricing-and-policy-guidelines-2026.pdf
```
