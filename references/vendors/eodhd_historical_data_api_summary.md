# EODHD Historical Data API — Source Summary

**Source URL:** https://eodhd.com/financial-apis/api-for-historical-data-and-volumes  
**Tagged as expertise area:** Historical market data APIs, end-of-day equities data, API-based stock data sourcing, trading-research data ingestion.

## What this page covers

This page documents EODHD's **End-of-Day Historical Stock Market Data API**. It focuses on how to request historical EOD prices and volume data for global instruments using symbol-plus-exchange identifiers such as `MCD.US`, with support for **daily, weekly, and monthly** intervals and output in **CSV or JSON**.

## Main capabilities described

- Historical EOD data is available for **more than 150,000 tickers globally**.
- Coverage includes **US stocks, ETFs, and mutual funds**, with US history described as going back to the beginning for many instruments, while **most non-US exchanges are covered from roughly 2000 onward**.
- The API supports **raw OHLC**, an **adjusted close**, and **volume**.
- Data can be requested with `period=d|w|m`, sorted ascending or descending, and filtered to a date range with `from=YYYY-MM-DD` and `to=YYYY-MM-DD`.
- The page gives examples in multiple languages, including **cURL, PHP, Python, and R**.

## Important technical notes

### Adjustment semantics
The page makes a key distinction that matters for backtesting and research quality:

- **OHLC values are raw** and are **not adjusted** for splits or dividends.
- **Adjusted close** is adjusted for **both splits and dividends**.
- **Volume** is adjusted for **splits**.

This means the endpoint is useful, but consumers need to be careful about **which field** they use in research pipelines. If a strategy expects fully split-adjusted OHLC bars, this page says the standard EOD endpoint is **not** providing that directly.

### Query patterns
The page describes these main request patterns:

- Standard endpoint: `/api/eod/{SYMBOL}.{EXCHANGE_ID}`
- Date filtering via `from` and `to`
- Interval selection via `period`
- JSON output via `fmt=json`
- Single-field filters such as `filter=last_close` or `filter=last_volume`

### Yahoo-style compatibility
The page also includes a **Yahoo-style compatibility endpoint** (`/api/table.csv`) for users migrating from older unofficial Yahoo Finance-style queries. It explains the alternate parameter format for dates and symbols.

### Bulk daily updates
For exchange-wide daily refreshes, the page points users to a separate **Bulk API for EOD, Splits and Dividends**, noting that this is the preferred route for efficient daily updates across many securities.

## Plan and usage limits mentioned on the page

- A **DEMO** key is available for testing only on a very small set of example tickers.
- The **free plan** is described as giving **20 API calls per day** and **1 year of historical EOD depth**.
- The page states that **1 API call is consumed per request**, regardless of the returned history length for that request.
- It also mentions an overall API limit of **100,000 requests per day**.

## Update timing details

The page says EOD prices are typically updated:

- **2–3 hours after market close** for exchanges generally.
- About **15 minutes after close** for major US exchanges such as NYSE and NASDAQ.
- Some symbol types, including **US mutual funds, PINK, OTCBB, and some indices**, may update only the **next morning**.

This is an important operational note for any workflow that depends on “same-day final” prices.

## Why this source is useful

This page is useful as a **practical implementation source** for building a historical market-data ingestion layer because it explains:

1. how to call the API,
2. how identifiers are structured,
3. what the free tier can and cannot do,
4. how corporate-action adjustments are represented,
5. and when new EOD data should be expected.

## Caveats for strategy research

For professional or semi-professional strategy research, this source is helpful but should be used with care:

- The page is strongest as **product documentation**, not as an independent validation of data quality.
- The adjustment model means you must avoid assuming that OHLC bars are fully corporate-action adjusted.
- The free tier is too shallow for multi-year backtests.
- The page does not, on its own, guarantee survivorship-aware universes or stable identifier handling across delistings and symbol changes; those needs would require checking EODHD’s related endpoints such as delisted data, symbol/exchange history, or ID mapping.

## Best future use of this source

Use this source as a reference for:

- EODHD endpoint syntax
- parameter options and response formats
- historical depth expectations
- adjustment semantics
- free-tier constraints
- daily refresh timing
- deciding when to pair this API with other endpoints for delistings, corporate actions, or identifier mapping

## One-line takeaway

EODHD’s historical data API page is a strong operational reference for pulling global end-of-day price histories, but any serious research workflow must pay close attention to its adjustment semantics, historical-depth limits on cheaper tiers, and the need for companion endpoints to cover delistings and identifier continuity.
