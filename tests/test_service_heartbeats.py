from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import shutil
import unittest
import uuid

from trotters_trader.service_heartbeats import check_service_heartbeat, heartbeat_path, load_service_heartbeats, write_service_heartbeat


class ServiceHeartbeatTests(unittest.TestCase):
    def test_write_and_load_service_heartbeat(self) -> None:
        root = self._workspace_root("write_load")
        try:
            write_service_heartbeat(root, "coordinator", metadata={"poll_seconds": 2.0}, pid=123)
            records = load_service_heartbeats(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        coordinator = next(record for record in records if record["service"] == "coordinator")
        self.assertEqual(coordinator["status"], "ok")
        self.assertEqual(coordinator["pid"], 123)
        self.assertEqual(coordinator["metadata"]["poll_seconds"], 2.0)

    def test_check_service_heartbeat_raises_for_stale_record(self) -> None:
        root = self._workspace_root("stale")
        try:
            heartbeat_file = heartbeat_path(root, "campaign-manager")
            heartbeat_file.write_text(
                json.dumps(
                    {
                        "service": "campaign-manager",
                        "recorded_at_utc": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
                        "pid": 456,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "campaign-manager"):
                check_service_heartbeat(root, "campaign-manager", max_age_seconds=90)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _workspace_root(self, label: str) -> Path:
        root = Path("tests/.tmp_runtime") / f"service_heartbeat_{label}_{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=True)
        return root


if __name__ == "__main__":
    unittest.main()
