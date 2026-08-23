"""Unit tests for the database manager."""

from pathlib import Path

import pytest

from esim_tool_manager.data.database import DatabaseManager


class TestDatabaseManager:
    """Tests for DatabaseManager initialization and migrations."""

    def test_creates_database_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            assert db.db_path == db_path
            # Trigger a query to force file creation
            db.execute("SELECT 1")
        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "dir" / "test.db"
        with DatabaseManager(db_path) as db:
            db.execute("SELECT 1")
        assert db_path.parent.exists()

    def test_run_migrations_creates_tables(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            applied = db.run_migrations()
            assert len(applied) >= 1
            assert "001_initial.sql" in applied

            # Verify tables exist
            assert db.table_exists("tools")
            assert db.table_exists("install_history")
            assert db.table_exists("update_history")
            assert db.table_exists("tool_config")
            assert db.table_exists("config_profiles")
            assert db.table_exists("_migrations")

    def test_migrations_are_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            first_run = db.run_migrations()
            second_run = db.run_migrations()
            assert len(first_run) >= 1
            assert len(second_run) == 0  # Nothing new to apply

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            row = db.fetchone("PRAGMA journal_mode")
            assert row is not None
            assert row[0] == "wal"

    def test_foreign_keys_enabled(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            row = db.fetchone("PRAGMA foreign_keys")
            assert row is not None
            assert row[0] == 1

    def test_insert_and_fetch(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            db.run_migrations()
            rowid = db.insert_json(
                "tools",
                {
                    "id": "test-tool",
                    "display_name": "Test Tool",
                    "description": "A test tool",
                    "category": "system",
                    "data_json": '{"id": "test-tool"}',
                },
            )
            assert rowid > 0

            row = db.fetchone("SELECT * FROM tools WHERE id = ?", ("test-tool",))
            assert row is not None
            assert row["display_name"] == "Test Tool"

    def test_fetchall(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            db.run_migrations()
            for i in range(3):
                db.insert_json(
                    "tools",
                    {
                        "id": f"tool-{i}",
                        "display_name": f"Tool {i}",
                        "description": "",
                        "category": "system",
                        "data_json": f'{{"id": "tool-{i}"}}',
                    },
                )
            rows = db.fetchall("SELECT * FROM tools")
            assert len(rows) == 3

    def test_context_manager_closes_connection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = DatabaseManager(db_path)
        with db:
            db.execute("SELECT 1")
        # After exiting, connection should be closed
        assert db._conn is None

    def test_table_exists_false_for_missing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        with DatabaseManager(db_path) as db:
            assert not db.table_exists("nonexistent_table")
