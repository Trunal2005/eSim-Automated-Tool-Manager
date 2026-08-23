"""Unit tests for core services (dependency checker, installer, updater, config, doctor)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.dependency_checker import DependencyChecker, _parse_version
from esim_tool_manager.core.doctor import Doctor
from esim_tool_manager.core.installer import Installer
from esim_tool_manager.core.updater import Updater
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.models import (
    InstallMethod,
    InstallStrategy,
    OSFamily,
    Tool,
    ToolCategory,
    ToolStatus,
)
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import SystemInfo


@pytest.fixture
def registry(tmp_path: Path) -> RegistryManager:
    """Create a seeded registry for testing."""
    db = DatabaseManager(tmp_path / "test.db")
    db.__enter__()
    reg = RegistryManager(db)
    reg.initialize()
    return reg


@pytest.fixture
def system_info() -> SystemInfo:
    """Create system info for the current OS."""
    return SystemInfo()


# ── Version Parsing Tests ─────────────────────────────────────────────


class TestVersionParsing:
    """Tests for version string parsing."""

    def test_parse_simple_version(self) -> None:
        v = _parse_version("47")
        assert v is not None

    def test_parse_semver(self) -> None:
        v = _parse_version("10.0.5")
        assert v is not None

    def test_parse_two_part(self) -> None:
        v = _parse_version("5.050")
        assert v is not None

    def test_parse_invalid(self) -> None:
        v = _parse_version("not_a_version")
        assert v is None

    def test_version_comparison(self) -> None:
        v40 = _parse_version("40")
        v47 = _parse_version("47")
        assert v40 is not None and v47 is not None
        assert v40 < v47


# ── Dependency Checker Tests ──────────────────────────────────────────


class TestDependencyChecker:
    """Tests for the dependency checker."""

    def test_check_tool_finds_python(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        """Python3 should be detectable on any system running these tests."""
        checker = DependencyChecker(registry, system_info)
        tool = registry.get_tool("python3")
        assert tool is not None

        # Manually adjust version_command for Windows
        if system_info.is_windows:
            tool.version_command = ["python", "--version"]

        result = checker.check_tool(tool)
        # Python should be found since we're running tests with it
        assert result.status in (ToolStatus.OK, ToolStatus.VERSION_UNPARSEABLE)

    def test_check_tool_git(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        """Git should be detectable if installed."""
        checker = DependencyChecker(registry, system_info)
        tool = registry.get_tool("git")
        assert tool is not None
        result = checker.check_tool(tool)
        # Git might or might not be installed
        assert result.status in (
            ToolStatus.OK,
            ToolStatus.MISSING,
            ToolStatus.OUTDATED,
            ToolStatus.VERSION_UNPARSEABLE,
        )

    def test_check_all_returns_results(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        results = checker.check_all()
        assert len(results) >= 7  # At least 7 tools in registry
        for result in results:
            assert result.tool_id
            assert isinstance(result.status, ToolStatus)

    def test_get_summary(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        summary = checker.get_summary()
        assert "total_tools" in summary
        assert "status_counts" in summary
        assert "results" in summary
        assert summary["total_tools"] >= 7

    def test_extract_version_ngspice(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        version = checker._extract_version(
            "ngspice-47 : created from ngspice revision 47",
            r"(?i)ngspice[- ]*(\d+(?:\.\d+)*)",
        )
        assert version == "47"

    def test_extract_version_git(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        version = checker._extract_version(
            "git version 2.55.0.windows.1",
            r"git version (\d+\.\d+\.\d+)",
        )
        assert version == "2.55.0"


# ── Installer Tests ──────────────────────────────────────────────────


class TestInstaller:
    """Tests for the tool installer."""

    def test_install_nonexistent_tool(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        installer = Installer(registry, checker, system_info)
        result = installer.install_tool("nonexistent")
        assert result.success is False
        assert "not in the registry" in result.message

    def test_dry_run_install(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        installer = Installer(registry, checker, system_info)
        result = installer.install_tool("git", dry_run=True)
        # Should either be "already installed" or "DRY RUN would install"
        assert result.dry_run is True or "already installed" in result.message.lower()

    def test_install_all_dry_run(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        installer = Installer(registry, checker, system_info)
        results = installer.install_all(dry_run=True)
        assert len(results) >= 7
        for result in results:
            assert result.tool_id

    def test_install_with_profile(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        installer = Installer(registry, checker, system_info)
        results = installer.install_all(profile_name="minimal-analog", dry_run=True)
        tool_ids = [r.tool_id for r in results]
        assert "ngspice" in tool_ids
        assert "kicad" in tool_ids


# ── Updater Tests ────────────────────────────────────────────────────


class TestUpdater:
    """Tests for the update system."""

    def test_check_updates(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        updater = Updater(registry, checker, system_info)
        updates = updater.check_updates()
        # Updates is a list — could be empty if everything is up to date
        assert isinstance(updates, list)

    def test_update_nonexistent_tool(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        updater = Updater(registry, checker, system_info)
        result = updater.update_tool("nonexistent")
        assert result.success is False

    def test_update_all_dry_run(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        updater = Updater(registry, checker, system_info)
        results = updater.update_all(dry_run=True)
        assert isinstance(results, list)


# ── Config Manager Tests ─────────────────────────────────────────────


class TestConfigManager:
    """Tests for configuration management."""

    def test_get_env_var(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        mgr = ConfigManager(registry, system_info)
        # PATH should always be set
        path = mgr.get_env_var("PATH")
        assert path is not None

    def test_set_env_var(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        mgr = ConfigManager(registry, system_info)
        result = mgr.set_env_var("ESIM_TEST_VAR", "test_value", tool_id="ngspice")
        assert result is True
        import os
        assert os.environ.get("ESIM_TEST_VAR") == "test_value"
        # Clean up
        del os.environ["ESIM_TEST_VAR"]

    def test_get_profiles(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        mgr = ConfigManager(registry, system_info)
        profiles = mgr.get_profiles()
        assert len(profiles) >= 3

    def test_validate_config(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        mgr = ConfigManager(registry, system_info)
        issues = mgr.validate_config()
        assert isinstance(issues, list)


# ── Doctor Tests ─────────────────────────────────────────────────────


class TestDoctor:
    """Tests for the doctor health check."""

    def test_run_produces_report(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        config_mgr = ConfigManager(registry, system_info)
        doctor = Doctor(checker, config_mgr)
        report = doctor.run()

        assert len(report.tool_results) >= 7
        assert isinstance(report.diagnostics, list)
        assert isinstance(report.overall_healthy, bool)

    def test_report_to_dict(
        self, registry: RegistryManager, system_info: SystemInfo
    ) -> None:
        checker = DependencyChecker(registry, system_info)
        config_mgr = ConfigManager(registry, system_info)
        doctor = Doctor(checker, config_mgr)
        report = doctor.run()
        data = report.to_dict()

        assert "overall_healthy" in data
        assert "summary" in data
        assert "tool_results" in data
        assert "diagnostics" in data
        assert data["summary"]["total_tools"] >= 7
