import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from trotters_trader.alpha_vantage import (
    default_api_symbol,
    download_daily_series,
    filter_instruments,
    instruments_for_download,
    load_api_key,
)
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.config import DataConfig, load_config
from trotters_trader.eodhd import (
    default_api_symbol as default_eodhd_api_symbol,
    download_daily_series as download_eodhd_daily_series,
    load_api_key as load_eodhd_api_key,
)
from trotters_trader.staging import stage_source_data
from tests.support import IsolatedWorkspaceTestCase


class IngestionTests(IsolatedWorkspaceTestCase):
    def test_load_api_key_from_env_file(self) -> None:
        root = Path("tests/.tmp_env")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("AV_KEY=test-key\n", encoding="utf-8")
            self.assertEqual(load_api_key(env_file), "test-key")
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_default_api_symbol_maps_lse_suffix(self) -> None:
        self.assertEqual(default_api_symbol("TSCO.L"), "TSCO.LON")
        self.assertEqual(default_api_symbol("IBM"), "IBM")

    def test_eodhd_default_api_symbol_maps_lse_suffix(self) -> None:
        self.assertEqual(default_eodhd_api_symbol("TSCO.L"), "TSCO.LSE")
        self.assertEqual(default_eodhd_api_symbol("IBM"), "IBM")

    def test_load_eodhd_api_key_from_env_file(self) -> None:
        root = Path("tests/.tmp_env_eodhd")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("EODHD_API_KEY=test-key\n", encoding="utf-8")
            self.assertEqual(load_eodhd_api_key(env_file), "test-key")
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_instruments_for_download_uses_internal_instrument_file(self) -> None:
        root = Path("tests/.tmp_symbols")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n"
                "SBRY.L,XLON,GBP,GB0000000002,0000002,23456789,ACTIVE\n",
                encoding="utf-8",
            )
            symbols = instruments_for_download(instruments, limit=1)
            self.assertEqual(symbols, [("TSCO.L", "TSCO.LON")])
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_instruments_for_download_accepts_watchlist_schema(self) -> None:
        root = Path("tests/.tmp_watchlist_symbols")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            instruments = root / "watchlist.csv"
            instruments.write_text(
                "instrument\n"
                "TSCO.L\n"
                "SBRY.L\n",
                encoding="utf-8",
            )
            symbols = instruments_for_download(instruments, limit=2)
            self.assertEqual(symbols, [("TSCO.L", "TSCO.LON"), ("SBRY.L", "SBRY.LON")])
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_filter_instruments_selects_requested_names(self) -> None:
        instruments = [("TSCO.L", "TSCO.LON"), ("SBRY.L", "SBRY.LON")]
        filtered = filter_instruments(instruments, ["SBRY.L"])
        self.assertEqual(filtered, [("SBRY.L", "SBRY.LON")])

    def test_download_daily_series_saves_raw_json(self) -> None:
        root = Path("tests/.tmp_download")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("AV_KEY=test-key\n", encoding="utf-8")
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=root / "alpha_vantage",
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            class _Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {
                            "Time Series (Daily)": {
                                "2024-01-02": {
                                    "1. open": "10",
                                    "2. high": "11",
                                    "3. low": "9",
                                    "4. close": "10.5",
                                    "5. adjusted close": "10.4",
                                    "6. volume": "1000",
                                }
                            }
                        }
                    ).encode("utf-8")

            with patch("trotters_trader.alpha_vantage.urlopen", return_value=_Response()):
                result = download_daily_series(config, env_path=env_file, limit=1)

            self.assertEqual(len(result["downloaded"]), 1)
            self.assertEqual(result["errors"], [])
            self.assertTrue((root / "raw" / "alpha_vantage_json" / "TSCO.L.json").exists())
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_download_daily_series_skips_existing_files_by_default(self) -> None:
        root = Path("tests/.tmp_download_skip")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("AV_KEY=test-key\n", encoding="utf-8")
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )
            raw_dir = root / "raw" / "alpha_vantage_json"
            raw_dir.mkdir(parents=True)
            existing_file = raw_dir / "TSCO.L.json"
            existing_file.write_text('{"cached": true}', encoding="utf-8")

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=root / "alpha_vantage",
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            with patch("trotters_trader.alpha_vantage.urlopen") as mock_urlopen:
                result = download_daily_series(config, env_path=env_file, limit=1)

            self.assertEqual(result["errors"], [])
            self.assertEqual(len(result["downloaded"]), 1)
            self.assertEqual(result["downloaded"][0]["status"], "skipped_existing")
            mock_urlopen.assert_not_called()
            self.assertEqual(existing_file.read_text(encoding="utf-8"), '{"cached": true}')
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_download_daily_series_can_target_specific_instrument(self) -> None:
        root = Path("tests/.tmp_download_targeted")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("AV_KEY=test-key\n", encoding="utf-8")
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n"
                "SBRY.L,XLON,GBP,GB0000000002,0000002,23456789,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=root / "alpha_vantage",
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            class _Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {
                            "Time Series (Daily)": {
                                "2024-01-02": {
                                    "1. open": "10",
                                    "2. high": "11",
                                    "3. low": "9",
                                    "4. close": "10.5",
                                    "5. adjusted close": "10.4",
                                    "6. volume": "1000",
                                }
                            }
                        }
                    ).encode("utf-8")

            with patch("trotters_trader.alpha_vantage.urlopen", return_value=_Response()):
                result = download_daily_series(
                    config,
                    env_path=env_file,
                    requested_instruments=["SBRY.L"],
                )

            self.assertEqual(result["errors"], [])
            self.assertEqual(len(result["downloaded"]), 1)
            self.assertEqual(result["downloaded"][0]["instrument"], "SBRY.L")
            self.assertEqual(result["downloaded"][0]["api_symbol"], "SBRY.LON")
            self.assertTrue((root / "raw" / "alpha_vantage_json" / "SBRY.L.json").exists())
            self.assertFalse((root / "raw" / "alpha_vantage_json" / "TSCO.L.json").exists())
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_eodhd_download_daily_series_saves_raw_json(self) -> None:
        root = Path("tests/.tmp_eodhd_download")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            env_file = root / ".env"
            env_file.write_text("EODHD_API_KEY=test-key\n", encoding="utf-8")
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="eodhd_json",
                source_bars_csv=root / "eodhd",
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            class _Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        [
                            {
                                "date": "2024-01-02",
                                "open": 10,
                                "high": 11,
                                "low": 9,
                                "close": 10.5,
                                "adjusted_close": 10.4,
                                "volume": 1000,
                            }
                        ]
                    ).encode("utf-8")

            with patch("trotters_trader.eodhd.urlopen", return_value=_Response()):
                result = download_eodhd_daily_series(
                    config,
                    env_path=env_file,
                    date_from="2020-01-01",
                    date_to="2024-12-31",
                    limit=1,
                )

            self.assertEqual(len(result["downloaded"]), 1)
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["from"], "2020-01-01")
            self.assertEqual(result["to"], "2024-12-31")
            self.assertTrue((root / "raw" / "eodhd_json" / "TSCO.L.json").exists())
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_staging_writes_staging_tables(self) -> None:
        config = self.isolated_config(load_config(Path("configs/backtest.toml")))
        outputs = stage_source_data(config.data)

        self.assertTrue(Path(outputs["staged_bars"]).exists())
        self.assertTrue(Path(outputs["staged_instruments"]).exists())
        self.assertTrue(Path(outputs["staged_corporate_actions"]).exists())

    def test_ingestion_writes_canonical_tables(self) -> None:
        config = self.isolated_config(load_config(Path("configs/backtest.toml")))
        outputs = materialize_canonical_data(config.data)

        self.assertTrue(Path(outputs["bars"]).exists())
        self.assertTrue(Path(outputs["instruments"]).exists())
        self.assertTrue(Path(outputs["corporate_actions"]).exists())
        self.assertTrue(Path(outputs["manifest"]).exists())

    def test_alpha_vantage_json_stages_into_flat_bar_table(self) -> None:
        root = Path("tests/.tmp_alpha_vantage_stage")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            source_dir = root / "alpha_vantage"
            source_dir.mkdir(parents=True)
            (source_dir / "TSCO.L.json").write_text(
                json.dumps(
                    {
                        "Meta Data": {"2. Symbol": "TSCO.LON"},
                        "Time Series (Daily)": {
                            "2024-01-03": {
                                "1. open": "11.0",
                                "2. high": "12.0",
                                "3. low": "10.5",
                                "4. close": "11.5",
                                "5. adjusted close": "11.4",
                                "6. volume": "1000",
                            },
                            "2024-01-02": {
                                "1. open": "10.0",
                                "2. high": "11.0",
                                "3. low": "9.5",
                                "4. close": "10.5",
                                "5. adjusted close": "10.4",
                                "6. volume": "900",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=source_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            outputs = stage_source_data(config)
            staged_rows = (root / "staging" / "daily_bars.csv").read_text(encoding="utf-8")

            self.assertTrue(Path(outputs["staged_bars"]).exists())
            self.assertIn("adjusted_close", staged_rows)
            self.assertIn("TSCO.L", staged_rows)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_alpha_vantage_stage_allows_source_dir_equal_to_raw_dir(self) -> None:
        root = Path("tests/.tmp_alpha_vantage_same_dir")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            raw_dir = root / "raw"
            source_dir = raw_dir / "alpha_vantage_json"
            source_dir.mkdir(parents=True)
            (source_dir / "TSCO.L.json").write_text(
                json.dumps(
                    {
                        "Time Series (Daily)": {
                            "2024-01-02": {
                                "1. open": "10.0",
                                "2. high": "11.0",
                                "3. low": "9.5",
                                "4. close": "10.5",
                                "5. adjusted close": "10.4",
                                "6. volume": "900",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=source_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=raw_dir,
            )

            outputs = stage_source_data(config)

            self.assertTrue(Path(outputs["staged_bars"]).exists())
            self.assertTrue((source_dir / "TSCO.L.json").exists())
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_alpha_vantage_json_can_materialize_canonical_data(self) -> None:
        root = Path("tests/.tmp_alpha_vantage_canonical")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            source_dir = root / "alpha_vantage"
            source_dir.mkdir(parents=True)
            (source_dir / "TSCO.L.json").write_text(
                json.dumps(
                    {
                        "Time Series (Daily)": {
                            "2024-01-02": {
                                "1. open": "10.0",
                                "2. high": "11.0",
                                "3. low": "9.5",
                                "4. close": "10.5",
                                "5. adjusted close": "10.4",
                                "6. volume": "900",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="alpha_vantage_json",
                source_bars_csv=source_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            outputs = materialize_canonical_data(config)

            self.assertTrue(Path(outputs["bars"]).exists())
            self.assertTrue(Path(outputs["instruments"]).exists())
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_eodhd_json_stages_into_flat_bar_table(self) -> None:
        root = Path("tests/.tmp_eodhd_stage")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            source_dir = root / "eodhd"
            source_dir.mkdir(parents=True)
            (source_dir / "TSCO.L.json").write_text(
                json.dumps(
                    [
                        {
                            "date": "2024-01-02",
                            "open": 10.0,
                            "high": 11.0,
                            "low": 9.5,
                            "close": 10.5,
                            "adjusted_close": 10.4,
                            "volume": 900,
                        },
                        {
                            "date": "2024-01-03",
                            "open": 11.0,
                            "high": 12.0,
                            "low": 10.5,
                            "close": 11.5,
                            "adjusted_close": 11.4,
                            "volume": 1000,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="eodhd_json",
                source_bars_csv=source_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            outputs = stage_source_data(config)
            staged_rows = (root / "staging" / "daily_bars.csv").read_text(encoding="utf-8")

            self.assertTrue(Path(outputs["staged_bars"]).exists())
            self.assertIn("adjusted_close", staged_rows)
            self.assertIn("TSCO.L", staged_rows)
            self.assertIn("10.4", staged_rows)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_eodhd_json_ignores_raw_files_outside_instrument_master(self) -> None:
        root = Path("tests/.tmp_eodhd_filter")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            source_dir = root / "eodhd"
            source_dir.mkdir(parents=True)
            payload = json.dumps(
                [
                    {
                        "date": "2024-01-02",
                        "open": 10.0,
                        "high": 11.0,
                        "low": 9.5,
                        "close": 10.5,
                        "adjusted_close": 10.4,
                        "volume": 900,
                    }
                ]
            )
            (source_dir / "TSCO.L.json").write_text(payload, encoding="utf-8")
            (source_dir / "EXTRA.L.json").write_text(payload, encoding="utf-8")
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="eodhd_json",
                source_bars_csv=source_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            outputs = stage_source_data(config)
            staged_rows = (root / "staging" / "daily_bars.csv").read_text(encoding="utf-8")

            self.assertTrue(Path(outputs["staged_bars"]).exists())
            self.assertIn("TSCO.L", staged_rows)
            self.assertNotIn("EXTRA.L", staged_rows)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_bulk_csv_stages_normalized_files(self) -> None:
        root = Path("tests/.tmp_bulk_stage")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            bars = root / "bars.csv"
            bars.write_text(
                "trade_date,instrument,open,high,low,close,volume\n"
                "2024-01-02,TSCO.L,10.0,11.0,9.5,10.5,900\n"
                "2024-01-03,TSCO.L,10.6,11.2,10.1,11.0,1000\n",
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n"
                "TSCO.L,DIVIDEND,2024-01-03,2024-01-04,2024-01-05,0.10\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="bulk_csv",
                source_bars_csv=bars,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            outputs = stage_source_data(config)
            staged_rows = (root / "staging" / "daily_bars.csv").read_text(encoding="utf-8")

            self.assertTrue(Path(outputs["staged_bars"]).exists())
            self.assertIn("adjusted_close", staged_rows)
            self.assertIn("2024-01-02,TSCO.L,10.0,11.0,9.5,10.5,10.5,900", staged_rows)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_bulk_csv_rejects_missing_required_columns(self) -> None:
        root = Path("tests/.tmp_bulk_invalid")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            bars = root / "bars.csv"
            bars.write_text(
                "trade_date,instrument,open,high,low,close\n"
                "2024-01-02,TSCO.L,10.0,11.0,9.5,10.5\n",
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="bulk_csv",
                source_bars_csv=bars,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            with self.assertRaisesRegex(Exception, "missing required columns: volume"):
                stage_source_data(config)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_bulk_csv_rejects_vendor_adjusted_policy_without_adjusted_close(self) -> None:
        root = Path("tests/.tmp_bulk_adjustment_policy")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            bars = root / "bars.csv"
            bars.write_text(
                "trade_date,instrument,open,high,low,close,volume\n"
                "2024-01-02,TSCO.L,10.0,11.0,9.5,10.5,900\n",
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="bulk_csv",
                source_bars_csv=bars,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
                adjustment_policy="vendor_adjusted_close",
            )

            with self.assertRaisesRegex(Exception, "does not provide adjusted_close"):
                stage_source_data(config)
        finally:
            if root.exists():
                shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
