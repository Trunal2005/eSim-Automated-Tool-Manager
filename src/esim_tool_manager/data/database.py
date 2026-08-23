"""SQLite database connection manager with numbered migration support.

Provides a DatabaseManager class that handles:
- Creating/opening the SQLite database
- Running numbered SQL migrations in order
- Tracking which migrations have been applied
- Context-manager-based connection lifecycle
"""

from __future__ import annotations

import json
import logging
import sqlite3
from importlib import resources
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default database filename
DEFAULT_DB_NAME = "esim_tools.db"


class DatabaseManager:
    """Manages the SQLite database for the eSim Tool Manager.

    Handles connection lifecycle, schema migrations, and provides
    helper methods for common database operations.

    Args:
        db_path: Path to the SQLite database file. If None, uses a default
                 location in the user's data directory.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".esim-tool-manager" / DEFAULT_DB_NAME
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        """The path to the SQLite database file."""
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the current database connection, opening one if needed."""
        if self._conn is None:
            self._conn = self._open_connection()
        return self._conn

    def _open_connection(self) -> sqlite3.Connection:
        """Open a new SQLite connection with recommended settings."""
        logger.debug("Opening database connection: %s", self._db_path)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")

    def __enter__(self) -> DatabaseManager:
        """Context manager entry — ensures connection is open."""
        _ = self.connection  # Force open
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit — closes the connection."""
        self.close()

    def run_migrations(self) -> list[str]:
        """Run all pending SQL migrations in order.

        Migrations are read from the `migrations/` directory within the
        `esim_tool_manager.data` package. Each migration file is named
        with a numeric prefix (e.g. `001_initial.sql`) and is executed
        in sorted order. Applied migrations are tracked in the `_migrations`
        table to ensure idempotency.

        Returns:
            List of migration names that were applied in this run.
        """
        conn = self.connection
        applied: list[str] = []

        # Ensure the migrations tracking table exists (bootstrap)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()

        # Get already-applied migrations
        cursor = conn.execute("SELECT migration_name FROM _migrations ORDER BY id")
        already_applied = {row["migration_name"] for row in cursor.fetchall()}

        # Discover migration files from the package
        migration_files = self._discover_migrations()

        for migration_name, sql_content in sorted(migration_files):
            if migration_name in already_applied:
                logger.debug("Migration already applied: %s", migration_name)
                continue

            logger.info("Applying migration: %s", migration_name)
            try:
                conn.executescript(sql_content)
                conn.execute(
                    "INSERT INTO _migrations (migration_name) VALUES (?)",
                    (migration_name,),
                )
                conn.commit()
                applied.append(migration_name)
                logger.info("Migration applied successfully: %s", migration_name)
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("Migration failed: %s — %s", migration_name, e)
                raise RuntimeError(
                    f"Database migration '{migration_name}' failed: {e}"
                ) from e

        if not applied:
            logger.debug("All migrations already applied")

        return applied

    def _discover_migrations(self) -> list[tuple[str, str]]:
        """Discover SQL migration files from the package's migrations/ directory.

        Returns:
            List of (migration_name, sql_content) tuples, sorted by name.
        """
        migrations: list[tuple[str, str]] = []

        try:
            migrations_pkg = resources.files("esim_tool_manager.data") / "migrations"
            for item in sorted(migrations_pkg.iterdir()):
                if hasattr(item, "name") and item.name.endswith(".sql"):
                    sql_content = item.read_text(encoding="utf-8")
                    migrations.append((item.name, sql_content))
        except (TypeError, FileNotFoundError) as e:
            logger.warning("Could not discover migrations from package: %s", e)
            # Fallback: try filesystem path relative to this file
            migrations_dir = Path(__file__).parent / "migrations"
            if migrations_dir.is_dir():
                for sql_file in sorted(migrations_dir.glob("*.sql")):
                    sql_content = sql_file.read_text(encoding="utf-8")
                    migrations.append((sql_file.name, sql_content))

        return migrations

    # ── Helper methods for common operations ──────────────────────────

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement with parameters."""
        return self.connection.execute(sql, params)

    def executemany(
        self, sql: str, params_list: list[tuple[Any, ...]]
    ) -> sqlite3.Cursor:
        """Execute a SQL statement with multiple parameter sets."""
        return self.connection.executemany(sql, params_list)

    def commit(self) -> None:
        """Commit the current transaction."""
        self.connection.commit()

    def fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> sqlite3.Row | None:
        """Execute and fetch a single row."""
        cursor = self.execute(sql, params)
        return cursor.fetchone()

    def fetchall(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> list[sqlite3.Row]:
        """Execute and fetch all rows."""
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def insert_json(self, table: str, data: dict[str, Any]) -> int:
        """Insert a row into a table from a dictionary.

        Args:
            table: Table name.
            data: Column name -> value mapping.

        Returns:
            The rowid of the inserted row.
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = tuple(
            json.dumps(v) if isinstance(v, (dict, list)) else v
            for v in data.values()
        )
        cursor = self.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",  # noqa: S608
            values,
        )
        self.commit()
        return cursor.lastrowid or 0

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        row = self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return row is not None
