from datetime import date
import unittest

from trotters_trader.domain import CorporateAction, DailyBar, Instrument
from trotters_trader.validation import DataValidationError, validate_market_data


class ValidationTests(unittest.TestCase):
    def test_duplicate_bar_dates_raise(self) -> None:
        instruments = {
            "TSCO.L": Instrument(
                instrument="TSCO.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB00BLGZ9862",
                sedol="BLGZ986",
                company_number="00445790",
                status="ACTIVE",
            )
        }
        bar = DailyBar(
            trade_date=date(2024, 1, 2),
            instrument="TSCO.L",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            adjusted_close=100.5,
            volume=1000.0,
        )

        with self.assertRaises(DataValidationError):
            validate_market_data({"TSCO.L": [bar, bar]}, instruments, {})

    def test_bar_after_delisting_date_raises(self) -> None:
        instruments = {
            "TSCO.L": Instrument(
                instrument="TSCO.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB00BLGZ9862",
                sedol="BLGZ986",
                company_number="00445790",
                status="DELISTED",
                listing_date=date(2020, 1, 1),
                delisting_date=date(2024, 1, 3),
            )
        }
        bars = {
            "TSCO.L": [
                DailyBar(date(2024, 1, 2), "TSCO.L", 100.0, 101.0, 99.0, 100.5, 100.5, 1000.0),
                DailyBar(date(2024, 1, 4), "TSCO.L", 100.0, 101.0, 99.0, 100.5, 100.5, 1000.0),
            ]
        }

        with self.assertRaisesRegex(DataValidationError, "extends beyond delisting_date"):
            validate_market_data(bars, instruments, {})

    def test_delisted_instrument_requires_delisting_date(self) -> None:
        instruments = {
            "TSCO.L": Instrument(
                instrument="TSCO.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB00BLGZ9862",
                sedol="BLGZ986",
                company_number="00445790",
                status="DELISTED",
            )
        }

        with self.assertRaisesRegex(DataValidationError, "missing delisting_date"):
            validate_market_data({}, instruments, {})

    def test_corporate_action_before_listing_date_raises(self) -> None:
        instruments = {
            "TSCO.L": Instrument(
                instrument="TSCO.L",
                exchange_mic="XLON",
                currency="GBP",
                isin="GB00BLGZ9862",
                sedol="BLGZ986",
                company_number="00445790",
                status="ACTIVE",
                listing_date=date(2021, 1, 1),
            )
        }
        actions = {
            "TSCO.L": [
                CorporateAction(
                    instrument="TSCO.L",
                    action_type="DIVIDEND",
                    ex_date=date(2020, 12, 1),
                    record_date=date(2020, 12, 2),
                    payable_date=date(2020, 12, 3),
                    ratio_or_amount=0.10,
                )
            ]
        }

        with self.assertRaisesRegex(DataValidationError, "predates listing_date"):
            validate_market_data({}, instruments, actions)


if __name__ == "__main__":
    unittest.main()
