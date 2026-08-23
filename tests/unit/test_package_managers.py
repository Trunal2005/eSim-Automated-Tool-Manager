"""Unit tests for package managers."""

from unittest.mock import patch

from esim_tool_manager.infra.package_managers import (
    AptManager,
    BrewManager,
    ChocoManager,
    PackageInfo,
)
from esim_tool_manager.infra.subprocess_runner import SubprocessResult


class TestAptManager:
    """Tests for the APT package manager wrapper."""

    def test_name(self) -> None:
        mgr = AptManager()
        assert mgr.name == "apt"

    def test_install_command(self) -> None:
        mgr = AptManager()
        cmd = mgr.get_install_command("ngspice")
        assert cmd == ["sudo", "apt-get", "install", "-y", "ngspice"]

    def test_update_command(self) -> None:
        mgr = AptManager()
        cmd = mgr.get_update_command("ngspice")
        assert cmd == ["sudo", "apt-get", "upgrade", "-y", "ngspice"]

    def test_dry_run_install(self) -> None:
        mgr = AptManager()
        result = mgr.install("ngspice", dry_run=True)
        assert result.success is True
        assert "DRY RUN" in result.stdout

    def test_dry_run_update(self) -> None:
        mgr = AptManager()
        result = mgr.update("ngspice", dry_run=True)
        assert result.success is True
        assert "DRY RUN" in result.stdout


class TestBrewManager:
    """Tests for the Homebrew package manager wrapper."""

    def test_name(self) -> None:
        mgr = BrewManager()
        assert mgr.name == "brew"

    def test_install_command(self) -> None:
        mgr = BrewManager()
        cmd = mgr.get_install_command("ngspice")
        assert cmd == ["brew", "install", "ngspice"]

    def test_dry_run_install(self) -> None:
        mgr = BrewManager()
        result = mgr.install("ngspice", dry_run=True)
        assert "DRY RUN" in result.stdout


class TestChocoManager:
    """Tests for the Chocolatey package manager wrapper."""

    def test_name(self) -> None:
        mgr = ChocoManager()
        assert mgr.name == "choco"

    def test_install_command(self) -> None:
        mgr = ChocoManager()
        cmd = mgr.get_install_command("git")
        assert cmd == ["choco", "install", "git", "-y"]

    def test_dry_run_install(self) -> None:
        mgr = ChocoManager()
        result = mgr.install("git", dry_run=True)
        assert "DRY RUN" in result.stdout


class TestPackageInfo:
    """Tests for PackageInfo dataclass."""

    def test_to_dict(self) -> None:
        info = PackageInfo(
            name="ngspice",
            installed_version="47",
            available_version="47",
            is_installed=True,
        )
        data = info.to_dict()
        assert data["name"] == "ngspice"
        assert data["is_installed"] is True

    def test_not_installed(self) -> None:
        info = PackageInfo(name="ghdl")
        assert info.is_installed is False
        assert info.installed_version is None
