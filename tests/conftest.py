"""Shared test fixtures for the eSim Tool Manager test suite."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory for each test."""
    return tmp_path


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a path for a temporary SQLite database."""
    return tmp_path / "test_esim_tools.db"


@pytest.fixture
def tmp_db_connection(tmp_db_path: Path) -> sqlite3.Connection:
    """Provide a temporary SQLite database connection.

    The connection is closed automatically after the test.
    """
    conn = sqlite3.connect(str(tmp_db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
