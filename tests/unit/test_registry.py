"""Unit tests for the registry manager."""

from pathlib import Path

import pytest

from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.models import ToolCategory
from esim_tool_manager.data.registry import RegistryManager


@pytest.fixture
def registry(tmp_path: Path) -> RegistryManager:
    """Create a fresh registry manager with a temp database, seeded from YAML."""
    db = DatabaseManager(tmp_path / "test.db")
    db.__enter__()
    reg = RegistryManager(db)
    reg.initialize()
    return reg


class TestRegistryInitialization:
    """Tests for registry loading and seeding."""

    def test_initialize_loads_tools(self, registry: RegistryManager) -> None:
        tools = registry.get_all_tools()
        assert len(tools) >= 7  # At least the 7 core tools

    def test_initialize_is_idempotent(self, registry: RegistryManager) -> None:
        count_before = len(registry.get_all_tools())
        registry.initialize()  # Second call
        count_after = len(registry.get_all_tools())
        assert count_before == count_after

    def test_seed_loads_profiles(self, registry: RegistryManager) -> None:
        profiles = registry.get_all_profiles()
        assert len(profiles) >= 3  # minimal-analog, digital-only, full-mixed-signal


class TestToolQueries:
    """Tests for tool query methods."""

    def test_get_tool_by_id(self, registry: RegistryManager) -> None:
        tool = registry.get_tool("ngspice")
        assert tool is not None
        assert tool.display_name == "Ngspice"
        assert tool.category == ToolCategory.SIMULATION

    def test_get_nonexistent_tool(self, registry: RegistryManager) -> None:
        tool = registry.get_tool("nonexistent")
        assert tool is None

    def test_search_tools(self, registry: RegistryManager) -> None:
        results = registry.search_tools("spice")
        assert len(results) >= 1
        assert any(t.id == "ngspice" for t in results)

    def test_search_tools_case_insensitive(self, registry: RegistryManager) -> None:
        results = registry.search_tools("KICAD")
        assert len(results) >= 1
        assert any(t.id == "kicad" for t in results)

    def test_get_tools_by_category(self, registry: RegistryManager) -> None:
        digital_tools = registry.get_tools_by_category(ToolCategory.DIGITAL)
        assert len(digital_tools) >= 2  # ghdl, verilator, nghdl, ngveri
        for tool in digital_tools:
            assert tool.category == ToolCategory.DIGITAL

    def test_get_tool_ids(self, registry: RegistryManager) -> None:
        ids = registry.get_tool_ids()
        assert "ngspice" in ids
        assert "kicad" in ids
        assert "git" in ids

    def test_tool_has_version_info(self, registry: RegistryManager) -> None:
        tool = registry.get_tool("ngspice")
        assert tool is not None
        assert tool.min_version == "40"
        assert tool.known_good_version == "47"
        assert tool.version_command == ["ngspice", "--version"]
        assert len(tool.version_regex) > 0

    def test_tool_has_install_strategies(self, registry: RegistryManager) -> None:
        tool = registry.get_tool("ngspice")
        assert tool is not None
        assert "linux" in tool.install_strategies
        assert tool.install_strategies["linux"].package_name == "ngspice"

    def test_tool_dependencies(self, registry: RegistryManager) -> None:
        nghdl = registry.get_tool("nghdl")
        assert nghdl is not None
        assert "ghdl" in nghdl.dependencies
        assert "ngspice" in nghdl.dependencies


class TestProfileQueries:
    """Tests for configuration profile queries."""

    def test_get_profile_by_name(self, registry: RegistryManager) -> None:
        profile = registry.get_profile("full-mixed-signal")
        assert profile is not None
        assert "ngspice" in profile.tool_ids
        assert "kicad" in profile.tool_ids

    def test_get_nonexistent_profile(self, registry: RegistryManager) -> None:
        profile = registry.get_profile("nonexistent")
        assert profile is None

    def test_minimal_analog_profile(self, registry: RegistryManager) -> None:
        profile = registry.get_profile("minimal-analog")
        assert profile is not None
        assert "ngspice" in profile.tool_ids
        assert "kicad" in profile.tool_ids
        # Should NOT include digital tools
        assert "ghdl" not in profile.tool_ids
        assert "verilator" not in profile.tool_ids


class TestHistoryRecords:
    """Tests for install/update history recording."""

    def test_add_and_retrieve_install_record(
        self, registry: RegistryManager
    ) -> None:
        rowid = registry.add_install_record(
            tool_id="ngspice",
            version="47",
            method="apt",
            success=True,
            dry_run=False,
        )
        assert rowid > 0

        history = registry.get_install_history(tool_id="ngspice")
        assert len(history) == 1
        assert history[0]["tool_id"] == "ngspice"
        assert history[0]["version"] == "47"
        assert history[0]["success"] == 1

    def test_add_and_retrieve_update_record(
        self, registry: RegistryManager
    ) -> None:
        rowid = registry.add_update_record(
            tool_id="git",
            from_version="2.40.0",
            to_version="2.55.0",
            success=True,
        )
        assert rowid > 0

        history = registry.get_update_history(tool_id="git")
        assert len(history) == 1
        assert history[0]["from_version"] == "2.40.0"

    def test_install_history_limit(self, registry: RegistryManager) -> None:
        for i in range(10):
            registry.add_install_record(
                tool_id="ngspice",
                version=str(40 + i),
                method="apt",
                success=True,
            )
        history = registry.get_install_history(tool_id="ngspice", limit=5)
        assert len(history) == 5

    def test_all_install_history(self, registry: RegistryManager) -> None:
        registry.add_install_record("ngspice", "47", "apt", True)
        registry.add_install_record("git", "2.55.0", "apt", True)
        history = registry.get_install_history()
        assert len(history) >= 2
