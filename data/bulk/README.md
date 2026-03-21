# Bulk Historical Dataset Drop Zone

Put research-grade local flat files here when you choose a bulk historical source.

Required files:

- `daily_bars.csv`
- `instruments.csv`
- `corporate_actions.csv`

Expected schemas:

`daily_bars.csv`

```text
trade_date,instrument,open,high,low,close,volume
```

Optional extra column:

```text
adjusted_close
```

If `adjusted_close` is omitted, staging will copy `close` into `adjusted_close`.
If you configure `adjustment_policy = "vendor_adjusted_close"`, this column is no longer optional; staging will reject the dataset if it is missing.

`instruments.csv`

```text
instrument,exchange_mic,currency,isin,sedol,company_number,status,listing_date,delisting_date,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket
```

`listing_date` and `delisting_date` are optional but supported. They let the repo validate historical instrument lifecycles and include delisted names without leaking future membership into the backtest.

`corporate_actions.csv`

```text
instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount
```

Use [`configs/bulk_historical.toml`](c:/Users/derek/OneDrive/Documents/Development/TrottersIndependantTraders/configs/bulk_historical.toml) once these files are present.
