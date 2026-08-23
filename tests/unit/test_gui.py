"""Unit tests for the GUI layer.

These tests use pytest-qt to simulate a PyQt6 application context.
They verify that the main window can be constructed and that the
asynchronous worker threads interact with the UI correctly, specifically
verifying thread-safety of SQLite database connections.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from esim_tool_manager.cli.app import get_services
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.models import Tool, ToolCategory, InstallStrategy, InstallMethod, OSFamily
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.gui.main_window import MainWindow

# Provide a QApplication instance for the tests
@pytest.fixture(scope="session")
def qapp_args() -> list[str]:
    return []

@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path for testing."""
    return tmp_path / "test_gui.db"

@pytest.fixture
def mock_services(temp_db_path: Path) -> dict:
    """Create a real set of services but using a temporary database."""
    db = DatabaseManager(db_path=temp_db_path)
    db.__enter__()
    
    # Run migrations
    db.run_migrations()
    
    # Insert a fake tool to test UI rendering
    fake_tool = Tool(
        id="fake_tool",
        category=ToolCategory.SYSTEM,
        display_name="Fake Tool",
        description="A fake tool for testing",
        version_command=["fake-tool", "--version"],
        version_regex=r"fake-tool (\d+\.\d+)",
        min_version="1.0",
        known_good_version="1.0",
        install_strategies={
            "linux": InstallStrategy(os_family=OSFamily.LINUX, method=InstallMethod.PACKAGE_MANAGER, package_name="fake-tool")
        }
    )
    from esim_tool_manager.infra.os_detect import SystemInfo
    mock_info_val = SystemInfo(_os_name="linux")
    registry = RegistryManager(db)
    # The worker threads will re-read from the DB, so we need to save the tool to the DB properly
    registry._insert_tool(fake_tool)
    
    # Mock system info so we don't run real checks
    with patch("esim_tool_manager.gui.workers.get_system_info", return_value=mock_info_val):
        
        from esim_tool_manager.core.dependency_checker import DependencyChecker
        from esim_tool_manager.core.config_manager import ConfigManager
        from esim_tool_manager.core.doctor import Doctor
        from esim_tool_manager.core.installer import Installer
        
        checker = DependencyChecker(registry, mock_info_val)
        
        # Mock the actual subprocess check at the class level so threads see it
        def fake_check(self, tool, *args, **kwargs):
            from esim_tool_manager.data.models import ToolCheckResult, ToolStatus
            return ToolCheckResult(tool_id=tool.id, status=ToolStatus.OK, installed_version="1.0", message="All good")
            
        with patch("esim_tool_manager.core.dependency_checker.DependencyChecker.check_tool", new=fake_check):
            config = ConfigManager(registry, mock_info_val)
            installer = Installer(registry, checker, mock_info_val)
            
            from esim_tool_manager.core.updater import Updater
            updater = Updater(registry, checker, mock_info_val)
            doctor = Doctor(checker, config)

            yield {
                "db": db,
                "registry": registry,
                "checker": checker,
                "config": config,
                "installer": installer,
                "updater": updater,
                "doctor": doctor,
            }

def test_main_window_construction(qtbot, mock_services) -> None:
    """Assert the main window can be instantiated without raising errors."""
    window = MainWindow(mock_services)
    qtbot.addWidget(window)
    assert window.windowTitle() == "eSim Tool Manager"


def test_system_status_tab_no_thread_error(qtbot, mock_services) -> None:
    """Simulate opening the System Status tab and verify it populates correctly without SQLite errors."""
    window = MainWindow(mock_services)
    qtbot.addWidget(window)
    
    # The worker starts automatically in __init__ via _refresh_status
    # We need to wait for the worker signal to finish
    with qtbot.waitSignal(window.worker.signals.finished, timeout=5000):
        pass
        
    # Assert that the health label does not contain an error
    error_text = window.health_label.text()
    assert "Error:" not in error_text
    
    # Assert the table has at least one row (our fake tool)
    assert window.status_table.rowCount() > 0
    
    # Assert the first column of the first row is our fake tool
    item = window.status_table.item(0, 0)
    assert item is not None
    assert item.text() == "fake_tool"


def test_refresh_status_multiple_times(qtbot, mock_services) -> None:
    """Assert that triggering 'Refresh Status' twice in a row does not raise SQLite threading errors."""
    window = MainWindow(mock_services)
    qtbot.addWidget(window)
    
    # Wait for the initial refresh to finish
    with qtbot.waitSignal(window.worker.signals.finished, timeout=5000):
        pass
        
    # Trigger refresh 1
    window._refresh_status()
    with qtbot.waitSignal(window.worker.signals.finished, timeout=5000):
        pass
    assert "Error:" not in window.health_label.text()
        
    # Trigger refresh 2
    window._refresh_status()
    with qtbot.waitSignal(window.worker.signals.finished, timeout=5000):
        pass
    assert "Error:" not in window.health_label.text()
