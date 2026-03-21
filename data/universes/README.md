# Universe Files

Use this directory for explicit research universes rather than reusing the tiny sample dataset metadata.

Current file:

- `uk_starter_watchlist.csv`
- `uk_starter_instrument_master.csv`
- `uk_broad_watchlist.csv`
- `uk_broad_instrument_master.csv`
- `uk_core_watchlist.csv`
- `uk_exploration_watchlist.csv`

Schema:

`uk_starter_watchlist.csv`

```text
instrument
```

`uk_starter_instrument_master.csv`

```text
instrument,exchange_mic,currency,isin,sedol,company_number,status,listing_date,delisting_date,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket
```

`uk_broad_watchlist.csv`

```text
instrument
```

`uk_broad_instrument_master.csv`

```text
instrument,exchange_mic,currency,isin,sedol,company_number,status,listing_date,delisting_date,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket
```

Recommended workflow:

1. Expand `uk_starter_watchlist.csv` to the symbols you actually want to download.
2. Use it as `download_instruments_csv` in source configs such as [`configs/eodhd.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/eodhd.toml).
3. Keep `uk_starter_instrument_master.csv` aligned with the same universe for staging and validation.
4. Run the downloader.
5. Run `coverage` before backtesting so you can verify symbol and date coverage.

This file is a download watchlist, not a full instrument master. Keep identifier-rich reference data in a separate instrument master file for canonicalization and backtesting.
Optional sector and industry metadata live in the instrument master so portfolio construction can enforce basket constraints such as `max_positions_per_sector`.
The instrument master now also carries `liquidity_bucket`, `tradability_status`, and `universe_bucket` so universe filtering and basket diagnostics can distinguish core vs exploration names and liquid vs less-liquid names.
Lifecycle fields `listing_date` and `delisting_date` are optional but supported. Use them when you need to preserve historically valid delisted names without leaking future membership into a backtest.
Use the `starter` files when you want to preserve the validated 24-name research baseline. Use the `broad` files when you want to expand EODHD downloads and coverage without mutating that baseline.
The `broad` universe is now the repo's default non-toy UK research universe.
