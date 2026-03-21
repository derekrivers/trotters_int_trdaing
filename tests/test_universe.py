from datetime import date
import unittest

from trotters_trader.config import UniverseConfig
from trotters_trader.domain import DailyBar, Instrument
from trotters_trader.universe import eligible_instruments


class UniverseTests(unittest.TestCase):
    def test_filters_by_volume_and_status(self) -> None:
        instruments = {
            "TSCO.L": Instrument(
                instrument="TSCO.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB00BLGZ9862",
                sedol="BLGZ986",
                company_number="00445790",
                status="ACTIVE",
            ),
            "LOWVOL.L": Instrument(
                instrument="LOWVOL.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB0000000001",
                sedol="0000001",
                company_number="00000001",
                status="ACTIVE",
            ),
        }
        bars = {
            "TSCO.L": [
                DailyBar(date(2024, 1, 2), "TSCO.L", 1, 1, 1, 1, 1, 1_500_000),
                DailyBar(date(2024, 1, 3), "TSCO.L", 1, 1, 1, 1, 1, 1_500_000),
                DailyBar(date(2024, 1, 4), "TSCO.L", 1, 1, 1, 1, 1, 1_500_000),
                DailyBar(date(2024, 1, 5), "TSCO.L", 1, 1, 1, 1, 1, 1_500_000),
                DailyBar(date(2024, 1, 8), "TSCO.L", 1, 1, 1, 1, 1, 1_500_000),
            ],
            "LOWVOL.L": [
                DailyBar(date(2024, 1, 2), "LOWVOL.L", 1, 1, 1, 1, 1, 10),
                DailyBar(date(2024, 1, 3), "LOWVOL.L", 1, 1, 1, 1, 1, 10),
                DailyBar(date(2024, 1, 4), "LOWVOL.L", 1, 1, 1, 1, 1, 10),
                DailyBar(date(2024, 1, 5), "LOWVOL.L", 1, 1, 1, 1, 1, 10),
                DailyBar(date(2024, 1, 8), "LOWVOL.L", 1, 1, 1, 1, 1, 10),
            ],
        }
        config = UniverseConfig(
            allowed_exchange_mic=("XLON",),
            allowed_currency="GBP",
            active_only=True,
            min_history_days=5,
            min_average_volume=1000.0,
        )

        result = eligible_instruments(bars, instruments, config)

        self.assertEqual(set(result), {"TSCO.L"})

    def test_active_only_can_include_delisted_name_if_it_was_live_in_period(self) -> None:
        instruments = {
            "OLD.L": Instrument(
                instrument="OLD.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB0000000003",
                sedol="0000003",
                company_number="00000003",
                status="DELISTED",
                listing_date=date(2020, 1, 1),
                delisting_date=date(2024, 6, 30),
            ),
        }
        bars = {
            "OLD.L": [DailyBar(date(2024, 1, 2), "OLD.L", 1, 1, 1, 1, 1, 1_500_000)] * 5,
        }
        config = UniverseConfig(
            allowed_exchange_mic=("XLON",),
            allowed_currency="GBP",
            active_only=True,
            min_history_days=5,
            min_average_volume=1000.0,
        )

        result = eligible_instruments(
            bars,
            instruments,
            config,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        self.assertEqual(set(result), {"OLD.L"})

    def test_active_only_excludes_delisted_name_if_period_is_after_delisting(self) -> None:
        instruments = {
            "OLD.L": Instrument(
                instrument="OLD.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB0000000003",
                sedol="0000003",
                company_number="00000003",
                status="DELISTED",
                listing_date=date(2020, 1, 1),
                delisting_date=date(2024, 6, 30),
            ),
        }
        bars = {
            "OLD.L": [DailyBar(date(2024, 1, 2), "OLD.L", 1, 1, 1, 1, 1, 1_500_000)] * 5,
        }
        config = UniverseConfig(
            allowed_exchange_mic=("XLON",),
            allowed_currency="GBP",
            active_only=True,
            min_history_days=5,
            min_average_volume=1000.0,
        )

        result = eligible_instruments(
            bars,
            instruments,
            config,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )

        self.assertEqual(set(result), set())

    def test_filters_by_metadata_buckets(self) -> None:
        instruments = {
            "CORE.L": Instrument(
                instrument="CORE.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB0000000001",
                sedol="0000001",
                company_number="00000001",
                status="ACTIVE",
                benchmark_bucket="FTSE100",
                liquidity_bucket="high",
                tradability_status="TRADABLE",
                universe_bucket="core",
            ),
            "EXPLORE.L": Instrument(
                instrument="EXPLORE.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB0000000002",
                sedol="0000002",
                company_number="00000002",
                status="ACTIVE",
                benchmark_bucket="FTSE250",
                liquidity_bucket="low",
                tradability_status="RESTRICTED",
                universe_bucket="explore",
            ),
        }
        bars = {
            "CORE.L": [DailyBar(date(2024, 1, 2), "CORE.L", 1, 1, 1, 1, 1, 1_500_000)] * 5,
            "EXPLORE.L": [DailyBar(date(2024, 1, 2), "EXPLORE.L", 1, 1, 1, 1, 1, 1_500_000)] * 5,
        }
        config = UniverseConfig(
            allowed_exchange_mic=("XLON",),
            allowed_currency="GBP",
            active_only=True,
            min_history_days=5,
            min_average_volume=1000.0,
            allowed_benchmark_buckets=("FTSE100",),
            allowed_tradability_statuses=("TRADABLE",),
            allowed_universe_buckets=("core",),
            excluded_liquidity_buckets=("low",),
        )

        result = eligible_instruments(bars, instruments, config)

        self.assertEqual(set(result), {"CORE.L"})


if __name__ == "__main__":
    unittest.main()
