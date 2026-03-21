# Market Microstructure

## Canonical Venue Documents

- LSE MIT201: order types, priority, auctions, trading behavior.
- LSE rulebook: member-firm obligations, venue rules, operational constraints.

## Source-Derived Findings

- MIT201 describes order handling in terms of trading-session context, so execution logic cannot be modeled correctly without session awareness.
- MIT201 documents that supported order behavior depends on trading-service and business-parameter configuration, which means strategy assumptions should not hard-code one universal order model.
- LSE delayed market data is published 15 minutes after initial publication and is provided for information purposes only.
- Onward distribution of delayed data with fees or as part of paid value-added services requires licensing.

## What This Means For The Bot

- The first backtesting engine should not try to model full intraday queue position or hidden-liquidity behavior.
- A daily-bar simulator is acceptable for the first version if it explicitly states that it is not a venue-faithful execution model.
- Execution assumptions should be conservative: next-bar fills, configurable spread penalty, configurable participation caps, and explicit costs.
- Real-time or announcement-driven trading should be deferred until there is a licensed and technically suitable data path.

## Core Microstructure Rules

- Always know the session state: auction, continuous, or otherwise restricted.
- Treat venue priority rules as binding.
- Do not use live venues as a testing environment.

## Project Implications

- Backtests should account for session state, spread, and execution behavior rather than assuming frictionless fills.
- Public RNS access should be treated as human-oriented access, with licensing friction considered for automation.

## Primary References

```text
MIT201 (Guide to the trading system): https://docs.londonstockexchange.com/sites/default/files/documents/mit201-guide-to-the-trading-system-15-7-20251208.pdf
Rules of the London Stock Exchange (effective 19 January 2026): https://docs.londonstockexchange.com/sites/default/files/documents/rules-of-the-london-stock-exchange-effective-19-january-2026_0.pdf
RNS (Regulatory News Service): https://www.lse.co.uk/rns/
Delayed market data terms: https://www.londonstockexchange.com/delayed-market-data/terms-and-conditions.htm
```
