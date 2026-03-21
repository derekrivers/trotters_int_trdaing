from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import unittest

from trotters_trader.config import AppConfig, load_config


class IsolatedWorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        runtime_root = Path("tests/.tmp_runtime")
        runtime_root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(self.id().encode("utf-8")).hexdigest()[:10]
        test_root = runtime_root / f"case_{digest}"
        if test_root.exists():
            shutil.rmtree(test_root, ignore_errors=True)
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp_root = test_root

    def tearDown(self) -> None:
        if self.temp_root.exists():
            shutil.rmtree(self.temp_root, ignore_errors=True)
        super().tearDown()

    def isolated_config(self, config_or_path: AppConfig | Path | str) -> AppConfig:
        config = load_config(config_or_path) if isinstance(config_or_path, (Path, str)) else config_or_path
        return replace(
            config,
            run=replace(config.run, output_dir=self.temp_root / "runs"),
            data=replace(
                config.data,
                staging_dir=self.temp_root / "staging",
                canonical_dir=self.temp_root / "canonical",
                raw_dir=self.temp_root / "raw",
            ),
            features=replace(
                config.features,
                feature_dir=self.temp_root / "features",
            ),
        )


def _safe_name(name: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in name)
    return safe or "test"
