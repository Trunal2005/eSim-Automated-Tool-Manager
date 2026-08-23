"""Dependency checker — detects installed tools and validates versions.

This module is READ-ONLY: it never modifies system state. It detects tool
presence via shutil.which + explicit path checks, runs version commands
safely (timeout-bound, never shell=True), and semver-compares against
the registry's minimum required versions.
"""

from __future__ import annotations

import logging
import re
import shutil
from typing import Any

from packaging.version import InvalidVersion, Version

from esim_tool_manager.core.dependency_graph import DependencyGraph
from esim_tool_manager.data.models import (
    DependencyIssue,
    Severity,
    Tool,
    ToolCheckResult,
    ToolStatus,
)
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import SystemInfo, get_system_info
from esim_tool_manager.infra.subprocess_runner import run_safe

logger = logging.getLogger(__name__)


def _parse_version(version_str: str) -> Version | None:
    """Try to parse a version string, returning None on failure."""
    try:
        return Version(version_str)
    except InvalidVersion:
        # Try normalizing common patterns
        # e.g., "5.050" -> "5.50", "47" -> "47.0"
        cleaned = version_str.strip()
        if cleaned and cleaned[0].isdigit():
            try:
                return Version(cleaned)
            except InvalidVersion:
                return None
    return None


class DependencyChecker:
    """Checks the installation status of all managed tools.

    This is a read-only operation — it never installs, modifies, or removes anything.

    Args:
        registry: The tool registry to check against.
        system_info: System information for OS-specific checks.
    """

    def __init__(
        self,
        registry: RegistryManager,
        system_info: SystemInfo | None = None,
    ) -> None:
        self._registry = registry
        self._system_info = system_info or get_system_info()

    def check_tool(self, tool: Tool) -> ToolCheckResult:
        """Check the installation status of a single tool.

        Detects presence via shutil.which + explicit path checks,
        runs the version command, and compares against minimum requirements.

        Args:
            tool: The tool to check.

        Returns:
            A ToolCheckResult with the determined status.
        """
        os_family = self._system_info.os_family

        # Check if the tool has an install strategy for this OS
        strategy = tool.install_strategies.get(os_family)
        expected_path = tool.expected_paths.get(os_family)

        # Detect the executable
        exe_path = self._find_executable(tool, expected_path)

        if exe_path is None:
            return ToolCheckResult(
                tool_id=tool.id,
                status=ToolStatus.MISSING,
                required_version=tool.min_version,
                message=f"{tool.display_name} is not installed. "
                f"Could not find '{tool.version_command[0]}' on PATH"
                + (f" or at {expected_path}" if expected_path else "")
                + ".",
            )

        # Run the version command using the detected executable path
        cmd_args = [exe_path] + tool.version_command[1:]
        result = run_safe(cmd_args, timeout=10)

        if not result.success and result.timed_out:
            return ToolCheckResult(
                tool_id=tool.id,
                status=ToolStatus.VERSION_UNPARSEABLE,
                executable_path=exe_path,
                required_version=tool.min_version,
                message=f"{tool.display_name} was found at {exe_path}, "
                f"but the version command timed out.",
            )

        # Parse version from output
        version_output = result.stdout or result.stderr
        version_str = self._extract_version(version_output, tool.version_regex)

        if version_str is None:
            return ToolCheckResult(
                tool_id=tool.id,
                status=ToolStatus.VERSION_UNPARSEABLE,
                executable_path=exe_path,
                required_version=tool.min_version,
                message=f"{tool.display_name} was found at {exe_path}, "
                f"but could not parse version from output: "
                f"'{version_output[:100]}'",
            )

        # Compare versions
        installed_ver = _parse_version(version_str)
        min_ver = _parse_version(tool.min_version)

        if installed_ver is None or min_ver is None:
            return ToolCheckResult(
                tool_id=tool.id,
                status=ToolStatus.VERSION_UNPARSEABLE,
                installed_version=version_str,
                executable_path=exe_path,
                required_version=tool.min_version,
                message=f"{tool.display_name} {version_str} is installed, "
                f"but version comparison failed (could not parse "
                f"'{version_str}' or '{tool.min_version}').",
            )

        if installed_ver < min_ver:
            return ToolCheckResult(
                tool_id=tool.id,
                status=ToolStatus.OUTDATED,
                installed_version=version_str,
                executable_path=exe_path,
                required_version=tool.min_version,
                message=f"{tool.display_name} {version_str} is installed but "
                f"outdated (minimum required: {tool.min_version}).",
            )

        return ToolCheckResult(
            tool_id=tool.id,
            status=ToolStatus.OK,
            installed_version=version_str,
            executable_path=exe_path,
            required_version=tool.min_version,
            message=f"{tool.display_name} {version_str} is installed and "
            f"meets requirements (>= {tool.min_version}).",
        )

    def check_all(self) -> list[ToolCheckResult]:
        """Check all tools in the registry.

        Returns:
            List of ToolCheckResult for every registered tool.
        """
        tools = self._registry.get_all_tools()
        results = []
        for tool in tools:
            logger.debug("Checking tool: %s", tool.id)
            result = self.check_tool(tool)
            results.append(result)
            logger.info(
                "Tool %s: %s — %s",
                tool.id,
                result.status.value,
                result.message,
            )
        return results

    def validate_dependency_graph(self) -> list[DependencyIssue]:
        """Validate the dependency graph based on current installation status.

        Checks that for every tool that IS installed, its dependencies
        are also installed. Surfaces specific, actionable errors like
        "GHDL is missing, which blocks NGHDL."

        Returns:
            List of DependencyIssue objects.
        """
        tools = self._registry.get_all_tools()
        graph = DependencyGraph(tools)
        check_results = self.check_all()

        # Build set of installed tool IDs
        installed_ids = {
            r.tool_id
            for r in check_results
            if r.status == ToolStatus.OK
        }

        # Validate graph with installed set
        issues = graph.validate(installed_tool_ids=installed_ids)

        # Add specific actionable messages for missing dependencies
        for tool in tools:
            if tool.dependencies:
                for dep_id in tool.dependencies:
                    dep_result = next(
                        (r for r in check_results if r.tool_id == dep_id), None
                    )
                    if dep_result and dep_result.status == ToolStatus.MISSING:
                        issues.append(
                            DependencyIssue(
                                tool_id=tool.id,
                                dependency_id=dep_id,
                                severity=Severity.ERROR,
                                message=f"{tool.display_name} requires "
                                f"{dep_id}, which is not installed. "
                                f"Install {dep_id} first to use {tool.display_name}.",
                            )
                        )

        return issues

    def _find_executable(
        self, tool: Tool, expected_path: str | None
    ) -> str | None:
        """Find the executable for a tool.

        Checks shutil.which first (searches PATH), then falls back to
        the expected install path from the registry.
        """
        # Check version_command[0] on PATH
        cmd_name = tool.version_command[0]

        # On Windows, also try 'python' instead of 'python3'
        candidates = [cmd_name]
        if cmd_name == "python3" and self._system_info.is_windows:
            # Prefer 'python' on Windows to avoid the python3.exe Microsoft Store stub
            candidates = ["python", "python3"]

        for candidate in candidates:
            found = shutil.which(candidate)
            if found:
                return found

        # Check expected install path
        if expected_path:
            from pathlib import Path

            p = Path(expected_path)
            if p.exists() and p.is_file():
                return str(p)

        return None

    def _extract_version(
        self, output: str, version_regex: str
    ) -> str | None:
        """Extract a version string from command output using a regex."""
        if not output:
            return None
        match = re.search(version_regex, output, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all tool statuses as a dictionary.

        Returns:
            Dictionary with counts by status and full results list.
        """
        results = self.check_all()
        status_counts: dict[str, int] = {}
        for result in results:
            status = result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_tools": len(results),
            "status_counts": status_counts,
            "results": [r.to_dict() for r in results],
        }
