from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    psycopg = None
    dict_row = None


if psycopg is None:
    RUNTIME_DB_OPERATIONAL_ERRORS: tuple[type[Exception], ...] = (sqlite3.OperationalError,)
else:
    RUNTIME_DB_OPERATIONAL_ERRORS = (sqlite3.OperationalError, psycopg.OperationalError)


@dataclass(frozen=True)
class RuntimeDatabaseConfig:
    sqlite_path: Path
    database_url: str | None = None

    @property
    def backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"

    @property
    def target(self) -> str:
        if not self.database_url:
            return str(self.sqlite_path)
        return redact_database_url(self.database_url)


class RuntimeCursorAdapter:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class RuntimeConnectionAdapter:
    def __init__(self, connection: Any, *, backend: str, database_target: str) -> None:
        self._connection = connection
        self.backend = backend
        self.database_target = database_target

    def execute(self, sql: str, parameters: tuple[object, ...] = ()):
        translated = translate_sql(sql, backend=self.backend)
        return RuntimeCursorAdapter(self._connection.execute(translated, parameters))

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self._connection.executescript(script)
            return
        for statement in split_sql_statements(script):
            self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def connect_runtime_database(config: RuntimeDatabaseConfig, *, timeout_seconds: float) -> RuntimeConnectionAdapter:
    if config.backend == "sqlite":
        connection = sqlite3.connect(config.sqlite_path, timeout=timeout_seconds)
        connection.row_factory = sqlite3.Row
        return RuntimeConnectionAdapter(connection, backend="sqlite", database_target=config.target)
    if psycopg is None or dict_row is None:
        raise RuntimeError(
            "Postgres runtime support requires the optional psycopg dependency, but it is not installed."
        )
    connection = psycopg.connect(
        config.database_url,
        autocommit=False,
        connect_timeout=max(int(timeout_seconds), 1),
        row_factory=dict_row,
    )
    return RuntimeConnectionAdapter(connection, backend="postgres", database_target=config.target)


def redact_database_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.username:
        return value
    username = parts.username
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{username}:***@{host}{port}"
    safe = SplitResult(parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    return urlunsplit(safe)


def split_sql_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def translate_sql(sql: str, *, backend: str) -> str:
    if backend != "postgres":
        return sql
    normalized = " ".join(sql.strip().split()).upper()
    if normalized == "BEGIN IMMEDIATE":
        return "BEGIN"
    return sql.replace("?", "%s")


def is_retryable_runtime_db_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "locked",
            "deadlock detected",
            "could not obtain lock",
            "serialization failure",
            "the database system is starting up",
        )
    )
