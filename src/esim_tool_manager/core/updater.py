"""Update/upgrade system — checks for and applies tool updates.

Queries native package managers for latest available versions and
compares against installed versions. All update operations are
dry-run-gated by default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.data.models import ToolStatus
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import SystemInfo, get_system_info
from esim_tool_manager.infra.package_managers import get_package_manager_for_os

logger = logging.getLogger(__name__)


@dataclass
class UpdateAvailable:
    """Describes an available update for a tool.

    Attributes:
        tool_id: The tool with an update available.
        display_name: Human-readable tool name.
        installed_version: Currently installed version.
        available_version: Latest available version.
        method: How the update would be applied.
    """

    tool_id: str
    display_name: str
    installed_version: str
    available_version: str
    method: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "display_name": self.display_name,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
            "method": self.method,
        }


@dataclass
class UpdateResult:
    """Result of a tool update attempt.

    Attributes:
        tool_id: Which tool was updated.
        success: Whether the update succeeded.
        from_version: Previous version.
        to_version: New version (or target version).
        message: Human-readable result description.
        dry_run: Whether this was a dry-run.
        command: The command that was (or would be) executed.
    """

    tool_id: str
    success: bool
    from_version: str = ""
    to_version: str = ""
    message: str = ""
    dry_run: bool = True
    command: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "success": self.success,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "message": self.message,
            "dry_run": self.dry_run,
            "command": self.command,
        }


class Updater:
    """Checks for and applies tool updates.

    Args:
        registry: The tool registry.
        checker: The dependency checker.
        system_info: System information for OS-specific operations.
    """

    def __init__(
        self,
        registry: RegistryManager,
        checker: DependencyChecker,
        system_info: SystemInfo | None = None,
    ) -> None:
        self._registry = registry
        self._checker = checker
        self._system_info = system_info or get_system_info()
        self._pkg_manager = get_package_manager_for_os(self._system_info.os_family)

    def check_updates(self) -> list[UpdateAvailable]:
        """Check all installed tools for available updates.

        Returns:
            List of UpdateAvailable for tools with newer versions.
        """
        updates: list[UpdateAvailable] = []
        tools = self._registry.get_all_tools()

        for tool in tools:
            check_result = self._checker.check_tool(tool)

            # Only check updates for installed tools
            if check_result.status not in (ToolStatus.OK, ToolStatus.OUTDATED):
                continue

            installed_version = check_result.installed_version or ""

            # Try to get latest version from package manager
            os_family = self._system_info.os_family
            strategy = tool.install_strategies.get(os_family)

            if strategy and strategy.package_name and self._pkg_manager:
                pkg_info = self._pkg_manager.query_package(strategy.package_name)
                if (
                    pkg_info.available_version
                    and pkg_info.available_version != installed_version
                ):
                    updates.append(
                        UpdateAvailable(
                            tool_id=tool.id,
                            display_name=tool.display_name,
                            installed_version=installed_version,
                            available_version=pkg_info.available_version,
                            method=self._pkg_manager.name,
                        )
                    )
                    continue

            # Compare against known_good_version from registry
            if (
                tool.known_good_version
                and installed_version
                and installed_version != tool.known_good_version
            ):
                from packaging.version import Version, InvalidVersion

                try:
                    if Version(installed_version) < Version(tool.known_good_version):
                        updates.append(
                            UpdateAvailable(
                                tool_id=tool.id,
                                display_name=tool.display_name,
                                installed_version=installed_version,
                                available_version=tool.known_good_version,
                                method="registry",
                            )
                        )
                except InvalidVersion:
                    pass

        return updates

    def update_tool(self, tool_id: str, dry_run: bool = True) -> UpdateResult:
        """Update a single tool.

        Args:
            tool_id: The tool to update.
            dry_run: If True (default), show what would happen.

        Returns:
            UpdateResult with the outcome.
        """
        tool = self._registry.get_tool(tool_id)
        if tool is None:
            return UpdateResult(
                tool_id=tool_id,
                success=False,
                message=f"Tool '{tool_id}' is not in the registry.",
            )

        check_result = self._checker.check_tool(tool)
        if check_result.status == ToolStatus.MISSING:
            return UpdateResult(
                tool_id=tool_id,
                success=False,
                message=f"{tool.display_name} is not installed. "
                f"Use 'install' instead of 'update'.",
            )

        os_family = self._system_info.os_family
        strategy = tool.install_strategies.get(os_family)

        if not strategy or not strategy.package_name or not self._pkg_manager:
            return UpdateResult(
                tool_id=tool_id,
                success=False,
                message=f"Cannot update {tool.display_name} automatically. "
                f"No package manager strategy available.",
            )

        cmd = self._pkg_manager.get_update_command(strategy.package_name)

        if dry_run:
            return UpdateResult(
                tool_id=tool_id,
                success=True,
                from_version=check_result.installed_version or "",
                message=f"[DRY RUN] Would update {tool.display_name} via "
                f"{self._pkg_manager.name}: {' '.join(cmd)}",
                dry_run=True,
                command=cmd,
            )

        result = self._pkg_manager.update(strategy.package_name, dry_run=False)

        update_result = UpdateResult(
            tool_id=tool_id,
            success=result.success,
            from_version=check_result.installed_version or "",
            message=result.stdout or result.error_message,
            dry_run=False,
            command=cmd,
        )

        # Record the update attempt
        self._registry.add_update_record(
            tool_id=tool_id,
            from_version=update_result.from_version,
            to_version=update_result.to_version,
            success=update_result.success,
            log_output=update_result.message,
        )

        return update_result

    def update_all(self, dry_run: bool = True) -> list[UpdateResult]:
        """Update all tools that have updates available.

        Args:
            dry_run: If True (default), show what would happen.

        Returns:
            List of UpdateResult for each tool.
        """
        updates = self.check_updates()
        results = []

        for update in updates:
            result = self.update_tool(update.tool_id, dry_run=dry_run)
            results.append(result)

        if not updates:
            logger.info("All tools are up to date.")

        return results
