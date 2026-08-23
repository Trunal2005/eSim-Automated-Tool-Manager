"""Tool installer — orchestrates installation with dry-run-by-default safety.

Design Decision (ADR-002): Dry-run is the default for ALL mutating operations.
Every real install requires explicit confirmation (--yes flag in CLI, confirm
dialog in GUI). This is a safety-first design for a tool that runs system commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.core.dependency_graph import DependencyGraph
from esim_tool_manager.data.models import InstallMethod, Tool, ToolStatus
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import SystemInfo, get_system_info
from esim_tool_manager.infra.package_managers import (
    PackageManager,
    get_package_manager_for_os,
)

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of a tool installation attempt.

    Attributes:
        tool_id: Which tool was installed.
        success: Whether the installation succeeded.
        method: The installation method used.
        message: Human-readable result description.
        dry_run: Whether this was a dry-run (no actual changes).
        command: The command that was (or would be) executed.
    """

    tool_id: str
    success: bool
    method: str = ""
    message: str = ""
    dry_run: bool = True
    command: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "success": self.success,
            "method": self.method,
            "message": self.message,
            "dry_run": self.dry_run,
            "command": self.command,
        }


class Installer:
    """Orchestrates tool installation with dependency resolution and dry-run safety.

    Args:
        registry: The tool registry.
        checker: The dependency checker for status verification.
        system_info: System information for OS-specific routing.
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

    def install_tool(
        self,
        tool_id: str,
        dry_run: bool = True,
        confirm_callback: Callable[[str], bool] | None = None,
    ) -> InstallResult:
        """Install a single tool.

        Args:
            tool_id: The tool to install.
            dry_run: If True (default), show what would happen without doing it.
            confirm_callback: Optional callback for user confirmation.
                Called with a message string, returns True to proceed.

        Returns:
            InstallResult with the outcome.
        """
        tool = self._registry.get_tool(tool_id)
        if tool is None:
            return InstallResult(
                tool_id=tool_id,
                success=False,
                message=f"Tool '{tool_id}' is not in the registry.",
            )

        os_family = self._system_info.os_family
        strategy = tool.install_strategies.get(os_family)

        if strategy is None:
            return InstallResult(
                tool_id=tool_id,
                success=False,
                message=f"{tool.display_name} has no install strategy for {os_family}. "
                f"Visit {tool.homepage} for manual installation instructions.",
            )

        # Check if already installed
        check_result = self._checker.check_tool(tool)
        if check_result.status == ToolStatus.OK:
            return InstallResult(
                tool_id=tool_id,
                success=True,
                message=f"{tool.display_name} {check_result.installed_version} "
                f"is already installed and meets requirements.",
            )

        # Route to the correct install method
        if strategy.method == InstallMethod.PACKAGE_MANAGER:
            return self._install_via_package_manager(tool, strategy, dry_run, confirm_callback)
        elif strategy.method == InstallMethod.DIRECT_DOWNLOAD:
            return self._install_via_direct_download(tool, strategy, dry_run, confirm_callback)
        elif strategy.method == InstallMethod.MANUAL:
            url = strategy.manual_url or tool.homepage
            return InstallResult(
                tool_id=tool_id,
                success=False,
                method="manual",
                message=f"{tool.display_name} requires manual installation. "
                f"Please visit: {url}",
            )
        else:
            return InstallResult(
                tool_id=tool_id,
                success=False,
                message=f"Unknown install method: {strategy.method}",
            )

    def install_all(
        self,
        profile_name: str | None = None,
        dry_run: bool = True,
        confirm_callback: Callable[[str], bool] | None = None,
    ) -> list[InstallResult]:
        """Install all tools, optionally filtered by a configuration profile.

        Uses topological sort to install in dependency order.

        Args:
            profile_name: Optional profile to filter tools.
            dry_run: If True (default), show what would happen.
            confirm_callback: Optional user confirmation callback.

        Returns:
            List of InstallResult for each tool.
        """
        if profile_name:
            profile = self._registry.get_profile(profile_name)
            if profile is None:
                return [
                    InstallResult(
                        tool_id="profile",
                        success=False,
                        message=f"Profile '{profile_name}' not found.",
                    )
                ]
            tool_ids = profile.tool_ids
        else:
            tool_ids = self._registry.get_tool_ids()

        # Resolve install order using dependency graph
        tools = self._registry.get_all_tools()
        graph = DependencyGraph(tools)
        ordered_ids = graph.get_install_order(tool_ids)

        results = []
        for tool_id in ordered_ids:
            result = self.install_tool(tool_id, dry_run=dry_run, confirm_callback=confirm_callback)
            results.append(result)

            # Log the install attempt
            self._registry.add_install_record(
                tool_id=tool_id,
                version=result.method,
                method=result.method,
                success=result.success,
                log_output=result.message,
                dry_run=dry_run,
            )

        return results

    def _install_via_package_manager(
        self,
        tool: Tool,
        strategy: Any,
        dry_run: bool,
        confirm_callback: Callable[[str], bool] | None,
    ) -> InstallResult:
        """Install a tool using the system package manager."""
        if self._pkg_manager is None:
            return InstallResult(
                tool_id=tool.id,
                success=False,
                method="package_manager",
                message=f"No package manager available for {self._system_info.os_family}. "
                f"Cannot install {tool.display_name} automatically.",
            )

        package_name = strategy.package_name
        if not package_name:
            return InstallResult(
                tool_id=tool.id,
                success=False,
                method="package_manager",
                message=f"No package name configured for {tool.display_name} "
                f"on {self._system_info.os_family}.",
            )

        cmd = self._pkg_manager.get_install_command(package_name)

        if dry_run:
            return InstallResult(
                tool_id=tool.id,
                success=True,
                method="package_manager",
                message=f"[DRY RUN] Would install {tool.display_name} via "
                f"{self._pkg_manager.name}: {' '.join(cmd)}",
                dry_run=True,
                command=cmd,
            )

        # Real install — requires confirmation
        if confirm_callback:
            msg = (
                f"Install {tool.display_name} via {self._pkg_manager.name}?\n"
                f"Command: {' '.join(cmd)}"
            )
            if not confirm_callback(msg):
                return InstallResult(
                    tool_id=tool.id,
                    success=False,
                    method="package_manager",
                    message="Installation cancelled by user.",
                )

        result = self._pkg_manager.install(package_name, dry_run=False)
        return InstallResult(
            tool_id=tool.id,
            success=result.success,
            method="package_manager",
            message=result.stdout or result.error_message,
            dry_run=False,
            command=cmd,
        )

    def _install_via_direct_download(
        self,
        tool: Tool,
        strategy: Any,
        dry_run: bool,
        confirm_callback: Callable[[str], bool] | None,
    ) -> InstallResult:
        """Install a tool via direct download."""
        url = strategy.download_url
        if not url:
            manual_url = strategy.manual_url or tool.homepage
            return InstallResult(
                tool_id=tool.id,
                success=False,
                method="direct_download",
                message=f"No download URL configured for {tool.display_name}. "
                f"Please visit: {manual_url}",
            )

        if dry_run:
            return InstallResult(
                tool_id=tool.id,
                success=True,
                method="direct_download",
                message=f"[DRY RUN] Would download {tool.display_name} from: {url}"
                + (f"\n  Checksum: {strategy.checksum_sha256}" if strategy.checksum_sha256 else ""),
                dry_run=True,
            )

        # Real download requires confirmation
        if confirm_callback:
            msg = f"Download and install {tool.display_name} from:\n{url}"
            if not confirm_callback(msg):
                return InstallResult(
                    tool_id=tool.id,
                    success=False,
                    method="direct_download",
                    message="Installation cancelled by user.",
                )

        # For now, return a message about the download URL
        # Actual download+extract logic would go here
        return InstallResult(
            tool_id=tool.id,
            success=False,
            method="direct_download",
            message=f"Direct download installation is not yet fully implemented. "
            f"Please download manually from: {url}",
            dry_run=False,
        )
