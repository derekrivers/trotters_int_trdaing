from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    instrument: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float


@dataclass(frozen=True)
class Instrument:
    instrument: str
    exchange_mic: str
    currency: str
    isin: str
    sedol: str
    company_number: str
    status: str
    listing_date: date | None = None
    delisting_date: date | None = None
    sector: str = ""
    industry: str = ""
    benchmark_bucket: str = ""
    liquidity_bucket: str = ""
    tradability_status: str = ""
    universe_bucket: str = ""


@dataclass(frozen=True)
class CorporateAction:
    instrument: str
    action_type: str
    ex_date: date
    record_date: date
    payable_date: date
    ratio_or_amount: float


@dataclass(frozen=True)
class Order:
    trade_date: date
    instrument: str
    quantity: int
    side: str


@dataclass(frozen=True)
class Fill:
    trade_date: date
    instrument: str
    quantity: int
    side: str
    requested_quantity: int
    price: float
    gross_notional: float
    commission: float
    slippage: float
    spread_cost: float
    stamp_duty: float
    participation_rate: float


@dataclass(frozen=True)
class Position:
    instrument: str
    quantity: int


@dataclass(frozen=True)
class PortfolioSnapshot:
    trade_date: date
    cash: float
    gross_market_value: float
    gross_exposure_ratio: float
    net_asset_value: float


@dataclass(frozen=True)
class ClosedTrade:
    trade_date: date
    instrument: str
    quantity: int
    realized_pnl: float
    return_pct: float
