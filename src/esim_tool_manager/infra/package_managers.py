"""Package manager abstraction layer.

Provides a unified interface for system package managers (apt, brew, choco)
with dry-run-by-default semantics. Each manager detects its own presence
before attempting operations.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any

from esim_tool_manager.infra.subprocess_runner import SubprocessResult, run_safe

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PackageInfo:
    """Information about a package from a package manager.

    Attributes:
        name: Package name.
        installed_version: Currently installed version, or None if not installed.
        available_version: Latest available version, or None if unknown.
        is_installed: Whether the package is currently installed.
    """

    name: str
    installed_version: str | None = None
    available_version: str | None = None
    is_installed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "name": self.name,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
            "is_installed": self.is_installed,
        }


class PackageManager(abc.ABC):
    """Abstract base class for system package managers.

    All concrete implementations must detect their own availability and
    provide install/query operations with dry-run support.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable name of this package manager."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if this package manager is installed and usable."""

    @abc.abstractmethod
    def get_install_command(self, package_name: str) -> list[str]:
        """Get the command that would install a package.

        This always returns the command — it does NOT execute it.
        Used for dry-run output and for actual execution.
        """

    @abc.abstractmethod
    def get_update_command(self, package_name: str) -> list[str]:
        """Get the command that would update a package."""

    @abc.abstractmethod
    def query_package(self, package_name: str) -> PackageInfo:
        """Query the package manager for info about a specific package."""

    def install(
        self, package_name: str, dry_run: bool = True
    ) -> SubprocessResult:
        """Install a package.

        Args:
            package_name: The package to install.
            dry_run: If True, only return the command without executing.

        Returns:
            SubprocessResult with the outcome.
        """
        cmd = self.get_install_command(package_name)

        if dry_run:
            logger.info("[DRY RUN] Would execute: %s", " ".join(cmd))
            return SubprocessResult(
                command=cmd,
                stdout=f"[DRY RUN] Would execute: {' '.join(cmd)}",
                returncode=0,
            )

        logger.info("Installing package: %s via %s", package_name, self.name)
        return run_safe(cmd, timeout=300)  # 5 min timeout for installs

    def update(
        self, package_name: str, dry_run: bool = True
    ) -> SubprocessResult:
        """Update a package.

        Args:
            package_name: The package to update.
            dry_run: If True, only return the command without executing.

        Returns:
            SubprocessResult with the outcome.
        """
        cmd = self.get_update_command(package_name)

        if dry_run:
            logger.info("[DRY RUN] Would execute: %s", " ".join(cmd))
            return SubprocessResult(
                command=cmd,
                stdout=f"[DRY RUN] Would execute: {' '.join(cmd)}",
                returncode=0,
            )

        logger.info("Updating package: %s via %s", package_name, self.name)
        return run_safe(cmd, timeout=300)


class AptManager(PackageManager):
    """Debian/Ubuntu APT package manager."""

    @property
    def name(self) -> str:
        return "apt"

    def is_available(self) -> bool:
        result = run_safe(["apt-get", "--version"], timeout=5)
        return result.success

    def get_install_command(self, package_name: str) -> list[str]:
        return ["sudo", "apt-get", "install", "-y", package_name]

    def get_update_command(self, package_name: str) -> list[str]:
        return ["sudo", "apt-get", "upgrade", "-y", package_name]

    def query_package(self, package_name: str) -> PackageInfo:
        """Query apt-cache for package info."""
        result = run_safe(
            ["apt-cache", "policy", package_name], timeout=10
        )
        if not result.success:
            return PackageInfo(name=package_name)

        installed = None
        available = None
        is_installed = False

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Installed:"):
                version = line.split(":", 1)[1].strip()
                if version != "(none)":
                    installed = version
                    is_installed = True
            elif line.startswith("Candidate:"):
                version = line.split(":", 1)[1].strip()
                if version != "(none)":
                    available = version

        return PackageInfo(
            name=package_name,
            installed_version=installed,
            available_version=available,
            is_installed=is_installed,
        )


class BrewManager(PackageManager):
    """macOS Homebrew package manager."""

    @property
    def name(self) -> str:
        return "brew"

    def is_available(self) -> bool:
        result = run_safe(["brew", "--version"], timeout=5)
        return result.success

    def get_install_command(self, package_name: str) -> list[str]:
        return ["brew", "install", package_name]

    def get_update_command(self, package_name: str) -> list[str]:
        return ["brew", "upgrade", package_name]

    def query_package(self, package_name: str) -> PackageInfo:
        """Query Homebrew for package info."""
        result = run_safe(
            ["brew", "info", "--json=v2", package_name], timeout=10
        )
        if not result.success:
            return PackageInfo(name=package_name)

        import json

        try:
            data = json.loads(result.stdout)
            formulae = data.get("formulae", [])
            if formulae:
                formula = formulae[0]
                versions = formula.get("versions", {})
                installed = formula.get("installed", [])
                return PackageInfo(
                    name=package_name,
                    installed_version=installed[0]["version"] if installed else None,
                    available_version=versions.get("stable"),
                    is_installed=len(installed) > 0,
                )
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        return PackageInfo(name=package_name)


class ChocoManager(PackageManager):
    """Windows Chocolatey package manager."""

    @property
    def name(self) -> str:
        return "choco"

    def is_available(self) -> bool:
        result = run_safe(["choco", "--version"], timeout=5)
        return result.success

    def get_install_command(self, package_name: str) -> list[str]:
        return ["choco", "install", package_name, "-y"]

    def get_update_command(self, package_name: str) -> list[str]:
        return ["choco", "upgrade", package_name, "-y"]

    def query_package(self, package_name: str) -> PackageInfo:
        """Query Chocolatey for package info."""
        # Check installed
        result = run_safe(
            ["choco", "list", "--local-only", "--exact", package_name],
            timeout=10,
        )
        installed = None
        is_installed = False
        if result.success:
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].lower() == package_name.lower():
                    installed = parts[1]
                    is_installed = True
                    break

        # Check latest available
        available = None
        result = run_safe(
            ["choco", "list", "--exact", package_name], timeout=10
        )
        if result.success:
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].lower() == package_name.lower():
                    available = parts[1]
                    break

        return PackageInfo(
            name=package_name,
            installed_version=installed,
            available_version=available,
            is_installed=is_installed,
        )


def get_package_manager_for_os(os_family: str) -> PackageManager | None:
    """Get the appropriate package manager for the current OS.

    Args:
        os_family: The OS family ('linux', 'windows', 'macos').

    Returns:
        The first available PackageManager for the OS, or None.
    """
    managers: dict[str, list[PackageManager]] = {
        "linux": [AptManager()],
        "macos": [BrewManager()],
        "windows": [ChocoManager()],
    }

    for manager in managers.get(os_family, []):
        if manager.is_available():
            return manager

    return None
