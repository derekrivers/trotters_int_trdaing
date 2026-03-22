# Execution And Market Structure

## Purpose

Capture the venue and execution assumptions that matter for research realism and later operational design.

## Canonical Venue Documents

- LSE MIT201
- LSE rulebook
- RNS access and delayed-data terms

## Core Findings

- Order handling depends on trading-session context, so execution logic cannot be modeled correctly without session awareness.
- Supported order behavior depends on trading service and business-parameter configuration; do not hard-code one universal order model.
- LSE delayed market data is informational and published 15 minutes late.
- Onward distribution of delayed data can still require licensing.

## Execution Design Rules

- The first backtesting engine should not pretend to model full intraday queue position or hidden-liquidity behavior.
- A daily-bar simulator is acceptable if it explicitly states that it is not venue-faithful.
- Execution assumptions should stay conservative: next-bar fills, spread penalty, configurable participation caps, and explicit costs.
- Real-time or announcement-driven trading should stay deferred until there is a licensed and technically suitable data path.

## Execution Goals

- minimize total cost: fees, spread, impact, opportunity cost
- control risk: volatility exposure, information leakage, and operational failure

## Measurement And Benchmarking

- implementation shortfall
- VWAP and TWAP as descriptive benchmarks
- auction benchmarks where relevant

## Canonical Models

- Almgren-Chriss
- Bertsimas-Lo

## Project Implications

- Backtests should account for session state, spread, and execution behavior instead of assuming frictionless fills.
- Public RNS access should be treated as human-oriented access with licensing friction for automation.
- Do not use live venues as a testing environment.

## Primary References

```text
MIT201 (Guide to the trading system): https://docs.londonstockexchange.com/sites/default/files/documents/mit201-guide-to-the-trading-system-15-7-20251208.pdf
Rules of the London Stock Exchange (effective 19 January 2026): https://docs.londonstockexchange.com/sites/default/files/documents/rules-of-the-london-stock-exchange-effective-19-january-2026_0.pdf
RNS (Regulatory News Service): https://www.lse.co.uk/rns/
Delayed market data terms: https://www.londonstockexchange.com/delayed-market-data/terms-and-conditions.htm
Bertsimas and Lo (1998): https://www.mit.edu/~dbertsim/papers/Finance/Optimal%20control%20of%20execution%20costs.pdf
Almgren and Chriss preprint: https://www.smallake.kr/wp-content/uploads/2016/03/optliq.pdf
Journal of Risk citation page: https://www.risk.net/journal-risk/2161150/optimal-execution-portfolio-transactions
```
