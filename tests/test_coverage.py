from pathlib import Path
import json
import shutil
import unittest

from trotters_trader.config import DataConfig
from trotters_trader.coverage import summarize_data_coverage, write_coverage_artifacts


class CoverageTests(unittest.TestCase):
    def test_eodhd_raw_coverage_reports_missing_instruments(self) -> None:
        root = Path("tests/.tmp_coverage_eodhd")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            raw_dir = root / "raw" / "eodhd_json"
            raw_dir.mkdir(parents=True)
            (raw_dir / "TSCO.L.json").write_text(
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
                        }
                    ]
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE,Consumer Staples,Food Retail,FTSE100,high,TRADABLE,core\n"
                "SBRY.L,XLON,GBP,GB0000000002,0000002,23456789,ACTIVE,Consumer Staples,Food Retail,FTSE100,high,TRADABLE,core\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="eodhd_json",
                source_bars_csv=raw_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=None,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            summary = summarize_data_coverage(config)

            self.assertEqual(summary["covered_instruments"], 1)
            self.assertEqual(summary["expected_instruments"], 2)
            self.assertEqual(summary["missing_instruments"], ["SBRY.L"])
            self.assertEqual(summary["earliest_date"], "2024-01-02")
            self.assertEqual(summary["metadata_counts"]["sector"]["Consumer Staples"], 2)
            self.assertIn("metadata_gaps", summary)
            self.assertEqual(summary["metadata_gaps"]["missing_counts"]["listing_date"], 2)
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_coverage_prefers_download_watchlist_when_present(self) -> None:
        root = Path("tests/.tmp_coverage_watchlist")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            raw_dir = root / "raw" / "eodhd_json"
            raw_dir.mkdir(parents=True)
            (raw_dir / "HSBA.L.json").write_text(
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
                        }
                    ]
                ),
                encoding="utf-8",
            )
            instruments = root / "instruments.csv"
            instruments.write_text(
                "instrument,exchange_mic,currency,isin,sedol,company_number,status,sector,industry,benchmark_bucket,liquidity_bucket,tradability_status,universe_bucket\n"
                "TSCO.L,XLON,GBP,GB0000000001,0000001,12345678,ACTIVE,Consumer Staples,Food Retail,FTSE100,high,TRADABLE,core\n",
                encoding="utf-8",
            )
            watchlist = root / "watchlist.csv"
            watchlist.write_text(
                "instrument\n"
                "HSBA.L\n"
                "SHEL.L\n",
                encoding="utf-8",
            )
            actions = root / "corporate_actions.csv"
            actions.write_text(
                "instrument,action_type,ex_date,record_date,payable_date,ratio_or_amount\n",
                encoding="utf-8",
            )

            config = DataConfig(
                source_name="eodhd_json",
                source_bars_csv=raw_dir,
                source_instruments_csv=instruments,
                download_instruments_csv=watchlist,
                source_corporate_actions_csv=actions,
                staging_dir=root / "staging",
                canonical_dir=root / "canonical",
                raw_dir=root / "raw",
            )

            summary = summarize_data_coverage(config)

            self.assertEqual(summary["expected_instruments"], 2)
            self.assertEqual(summary["covered_instruments"], 1)
            self.assertEqual(summary["missing_instruments"], ["SHEL.L"])
        finally:
            if root.exists():
                shutil.rmtree(root)

    def test_coverage_artifacts_write_json_and_missing_csv(self) -> None:
        root = Path("tests/.tmp_coverage_artifacts")
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        try:
            summary = {
                "source": "raw_eodhd_json",
                "path": "data/raw/eodhd_json",
                "expected_instruments": 2,
                "covered_instruments": 1,
                "missing_instruments": ["SBRY.L"],
                "coverage_ratio": 0.5,
                "total_rows": 100,
                "earliest_date": "2020-01-01",
                "latest_date": "2024-12-31",
                "per_instrument": {
                    "TSCO.L": {
                        "rows": 100,
                        "start_date": "2020-01-01",
                        "end_date": "2024-12-31",
                    }
                },
            }

            outputs = write_coverage_artifacts(summary, output_dir=root, report_name="eodhd_test")

            self.assertTrue(Path(outputs["summary_json"]).exists())
            self.assertTrue(Path(outputs["missing_csv"]).exists())
            missing_csv = Path(outputs["missing_csv"]).read_text(encoding="utf-8")
            self.assertIn("instrument", missing_csv)
            self.assertIn("SBRY.L", missing_csv)
        finally:
            if root.exists():
                shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
