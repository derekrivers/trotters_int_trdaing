# Domain Model

## Core Entities

### Instrument

- internal_id
- ticker
- exchange_mic
- isin
- sedol
- currency
- company_number
- status
- effective_from
- effective_to

### DailyBar

- instrument_id
- trade_date
- open
- high
- low
- close
- adjusted_close
- volume
- source
- source_timestamp

### CorporateAction

- instrument_id
- action_type
- ex_date
- record_date
- payable_date
- ratio_or_amount
- source

### FeatureSnapshot

- instrument_id
- trade_date
- feature_name
- feature_value
- feature_version

### Signal

- strategy_id
- trade_date
- instrument_id
- signal_type
- signal_value

### TargetPosition

- strategy_id
- trade_date
- instrument_id
- target_weight
- target_shares

### Order

- order_id
- strategy_id
- instrument_id
- created_at
- intended_trade_date
- side
- quantity
- order_type

### Fill

- fill_id
- order_id
- instrument_id
- fill_date
- fill_price
- fill_quantity
- fees
- taxes
- slippage_bps

### PositionLot

- instrument_id
- acquisition_date
- quantity
- cost_basis

### PortfolioSnapshot

- trade_date
- cash
- gross_exposure
- net_exposure
- market_value
- nav

## Architectural Rules

- Keep source identifiers and internal identifiers separate.
- Preserve raw and adjusted prices distinctly.
- Store enough data to reproduce fills and tax assumptions later.
- Do not collapse trades directly into end-of-day positions without preserving the trade ledger.

## Recommended Storage Split

- `raw/`: unmodified source payloads
- `staging/`: normalized but source-specific tables
- `canonical/`: internal schemas used by the engine
- `artifacts/`: run outputs and reports
