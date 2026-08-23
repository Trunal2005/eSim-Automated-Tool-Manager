"""Unit tests for data models."""

from esim_tool_manager.data.models import (
    ConfigProfile,
    DependencyIssue,
    InstallMethod,
    InstallRecord,
    InstallStrategy,
    OSFamily,
    Severity,
    Tool,
    ToolCategory,
    ToolCheckResult,
    ToolStatus,
    UpdateRecord,
)


class TestToolCategory:
    """Tests for the ToolCategory enum."""

    def test_all_categories_exist(self) -> None:
        categories = [c.value for c in ToolCategory]
        assert "simulation" in categories
        assert "schematic" in categories
        assert "digital" in categories

    def test_from_string(self) -> None:
        assert ToolCategory("simulation") == ToolCategory.SIMULATION


class TestToolStatus:
    """Tests for the ToolStatus enum."""

    def test_all_statuses_exist(self) -> None:
        assert ToolStatus.OK.value == "ok"
        assert ToolStatus.MISSING.value == "missing"
        assert ToolStatus.OUTDATED.value == "outdated"
        assert ToolStatus.VERSION_UNPARSEABLE.value == "version_unparseable"
        assert ToolStatus.INCOMPATIBLE_OS.value == "incompatible_os"


class TestInstallStrategy:
    """Tests for InstallStrategy serialization."""

    def test_roundtrip_serialization(self) -> None:
        strategy = InstallStrategy(
            os_family=OSFamily.LINUX,
            method=InstallMethod.PACKAGE_MANAGER,
            package_name="ngspice",
        )
        data = strategy.to_dict()
        restored = InstallStrategy.from_dict(data)
        assert restored.os_family == OSFamily.LINUX
        assert restored.method == InstallMethod.PACKAGE_MANAGER
        assert restored.package_name == "ngspice"

    def test_direct_download_strategy(self) -> None:
        strategy = InstallStrategy(
            os_family=OSFamily.WINDOWS,
            method=InstallMethod.DIRECT_DOWNLOAD,
            download_url="https://example.com/tool.zip",
            checksum_sha256="abc123",
        )
        data = strategy.to_dict()
        assert data["download_url"] == "https://example.com/tool.zip"
        assert data["checksum_sha256"] == "abc123"


class TestTool:
    """Tests for Tool serialization and methods."""

    def _make_tool(self) -> Tool:
        return Tool(
            id="ngspice",
            display_name="Ngspice",
            description="SPICE simulator",
            category=ToolCategory.SIMULATION,
            version_command=["ngspice", "--version"],
            version_regex=r"ngspice (\d+)",
            min_version="40",
            known_good_version="47",
            install_strategies={
                "linux": InstallStrategy(
                    os_family=OSFamily.LINUX,
                    method=InstallMethod.PACKAGE_MANAGER,
                    package_name="ngspice",
                ),
            },
            env_vars={"NGSPICE_HOME": "Root dir"},
            dependencies=[],
            homepage="https://ngspice.sourceforge.io/",
        )

    def test_roundtrip_serialization(self) -> None:
        tool = self._make_tool()
        data = tool.to_dict()
        restored = Tool.from_dict(data)
        assert restored.id == "ngspice"
        assert restored.display_name == "Ngspice"
        assert restored.category == ToolCategory.SIMULATION
        assert restored.min_version == "40"
        assert "linux" in restored.install_strategies

    def test_get_strategy_for_os(self) -> None:
        tool = self._make_tool()
        linux_strategy = tool.get_strategy_for_os(OSFamily.LINUX)
        assert linux_strategy is not None
        assert linux_strategy.package_name == "ngspice"

        windows_strategy = tool.get_strategy_for_os(OSFamily.WINDOWS)
        assert windows_strategy is None

    def test_to_dict_contains_all_fields(self) -> None:
        tool = self._make_tool()
        data = tool.to_dict()
        expected_keys = {
            "id", "display_name", "description", "category",
            "version_command", "version_regex", "min_version",
            "known_good_version", "install_strategies", "env_vars",
            "expected_paths", "dependencies", "homepage",
        }
        assert set(data.keys()) == expected_keys


class TestToolCheckResult:
    """Tests for ToolCheckResult."""

    def test_to_dict(self) -> None:
        result = ToolCheckResult(
            tool_id="ngspice",
            status=ToolStatus.OK,
            installed_version="47",
            required_version="40",
            message="Ngspice 47 is installed and meets requirements.",
        )
        data = result.to_dict()
        assert data["tool_id"] == "ngspice"
        assert data["status"] == "ok"
        assert data["installed_version"] == "47"

    def test_missing_status(self) -> None:
        result = ToolCheckResult(
            tool_id="ghdl",
            status=ToolStatus.MISSING,
            message="GHDL is not installed.",
        )
        assert result.installed_version is None
        assert result.executable_path is None


class TestDependencyIssue:
    """Tests for DependencyIssue."""

    def test_to_dict(self) -> None:
        issue = DependencyIssue(
            tool_id="nghdl",
            dependency_id="ghdl",
            severity=Severity.WARNING,
            message="GHDL is required by NGHDL but not installed.",
        )
        data = issue.to_dict()
        assert data["tool_id"] == "nghdl"
        assert data["dependency_id"] == "ghdl"
        assert data["severity"] == "warning"


class TestInstallRecord:
    """Tests for InstallRecord."""

    def test_to_dict(self) -> None:
        record = InstallRecord(
            tool_id="ngspice",
            version="47",
            method="apt",
            success=True,
            dry_run=False,
        )
        data = record.to_dict()
        assert data["tool_id"] == "ngspice"
        assert data["success"] is True
        assert data["dry_run"] is False
        assert "timestamp" in data


class TestUpdateRecord:
    """Tests for UpdateRecord."""

    def test_to_dict(self) -> None:
        record = UpdateRecord(
            tool_id="git",
            from_version="2.40.0",
            to_version="2.55.0",
            success=True,
        )
        data = record.to_dict()
        assert data["from_version"] == "2.40.0"
        assert data["to_version"] == "2.55.0"


class TestConfigProfile:
    """Tests for ConfigProfile."""

    def test_roundtrip_serialization(self) -> None:
        profile = ConfigProfile(
            name="full-mixed-signal",
            display_name="Full Mixed-Signal",
            description="Complete eSim setup",
            tool_ids=["ngspice", "kicad", "ghdl"],
            env_overrides={"CUSTOM_VAR": "value"},
        )
        data = profile.to_dict()
        restored = ConfigProfile.from_dict(data)
        assert restored.name == "full-mixed-signal"
        assert len(restored.tool_ids) == 3
        assert restored.env_overrides["CUSTOM_VAR"] == "value"
