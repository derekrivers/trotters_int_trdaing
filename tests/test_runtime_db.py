from __future__ import annotations

import unittest

from trotters_trader.runtime_db import RuntimeConnectionAdapter, RuntimeDatabaseConfig, translate_sql


class _FakeCursor:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, parameters: tuple[object, ...] = ()):
        self.calls.append((sql, parameters))
        return _FakeCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class RuntimeDatabaseTests(unittest.TestCase):
    def test_translate_sql_rewrites_qmark_parameters_for_postgres(self) -> None:
        translated = translate_sql(
            "SELECT * FROM jobs WHERE job_id = ? AND status = ?",
            backend="postgres",
        )

        self.assertEqual(translated, "SELECT * FROM jobs WHERE job_id = %s AND status = %s")

    def test_translate_sql_rewrites_begin_immediate_for_postgres(self) -> None:
        self.assertEqual(translate_sql("BEGIN IMMEDIATE", backend="postgres"), "BEGIN")

    def test_runtime_connection_adapter_uses_translated_postgres_sql(self) -> None:
        fake = _FakeConnection()
        connection = RuntimeConnectionAdapter(
            fake,
            backend="postgres",
            database_target="postgresql://runtime:***@runtime-db:5432/trotters_runtime",
        )

        connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            ("workers", "heartbeat_at"),
        )

        self.assertEqual(
            fake.calls,
            [
                (
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    ("workers", "heartbeat_at"),
                )
            ],
        )

    def test_runtime_database_config_redacts_password_in_target(self) -> None:
        config = RuntimeDatabaseConfig(
            sqlite_path="runtime/research_runtime/state/research_runtime.sqlite3",
            database_url="postgresql://trotters:secret@runtime-db:5432/trotters_runtime",
        )

        self.assertEqual(config.target, "postgresql://trotters:***@runtime-db:5432/trotters_runtime")


if __name__ == "__main__":
    unittest.main()
