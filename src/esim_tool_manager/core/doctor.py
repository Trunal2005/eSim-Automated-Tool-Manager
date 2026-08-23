"""Doctor — one-shot health check combining all diagnostics.

The 'doctor' command is a comprehensive health check that:
1. Runs dependency checks on all tools
2. Validates the dependency graph
3. Validates configuration (env vars, paths)
4. Produces a unified report with severity levels
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.data.models import (
    DiagnosticMessage,
    Severity,
    ToolCheckResult,
    ToolStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class DoctorReport:
    """Comprehensive health check report.

    Attributes:
        tool_results: Individual tool check results.
        diagnostics: Diagnostic messages from all checks.
        overall_healthy: Whether the system is in good shape overall.
    """

    tool_results: list[ToolCheckResult] = field(default_factory=list)
    diagnostics: list[DiagnosticMessage] = field(default_factory=list)
    overall_healthy: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        return {
            "overall_healthy": self.overall_healthy,
            "summary": {
                "total_tools": len(self.tool_results),
                "ok": sum(1 for r in self.tool_results if r.status == ToolStatus.OK),
                "missing": sum(1 for r in self.tool_results if r.status == ToolStatus.MISSING),
                "outdated": sum(1 for r in self.tool_results if r.status == ToolStatus.OUTDATED),
                "issues": sum(1 for r in self.tool_results if r.status not in (ToolStatus.OK,)),
                "diagnostics": len(self.diagnostics),
                "errors": sum(
                    1
                    for d in self.diagnostics
                    if d.severity in (Severity.ERROR, Severity.CRITICAL)
                ),
                "warnings": sum(
                    1 for d in self.diagnostics if d.severity == Severity.WARNING
                ),
            },
            "tool_results": [r.to_dict() for r in self.tool_results],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }


class Doctor:
    """Comprehensive health check for the eSim toolchain.

    Combines dependency checking, graph validation, and configuration
    validation into a single unified report.

    Args:
        checker: The dependency checker.
        config_manager: The configuration manager.
    """

    def __init__(
        self,
        checker: DependencyChecker,
        config_manager: ConfigManager,
    ) -> None:
        self._checker = checker
        self._config_manager = config_manager

    def run(self) -> DoctorReport:
        """Run the full health check.

        Returns:
            A DoctorReport with all findings.
        """
        report = DoctorReport()

        # 1. Check all tools
        logger.info("Running dependency checks...")
        report.tool_results = self._checker.check_all()

        for result in report.tool_results:
            if result.status == ToolStatus.MISSING:
                report.diagnostics.append(
                    DiagnosticMessage(
                        severity=Severity.WARNING,
                        category="dependency",
                        message=result.message,
                        suggestion=f"Install {result.tool_id} using: "
                        f"esim-tool-manager install {result.tool_id}",
                    )
                )
            elif result.status == ToolStatus.OUTDATED:
                report.diagnostics.append(
                    DiagnosticMessage(
                        severity=Severity.WARNING,
                        category="dependency",
                        message=result.message,
                        suggestion=f"Update {result.tool_id} using: "
                        f"esim-tool-manager update {result.tool_id}",
                    )
                )
            elif result.status == ToolStatus.VERSION_UNPARSEABLE:
                report.diagnostics.append(
                    DiagnosticMessage(
                        severity=Severity.INFO,
                        category="dependency",
                        message=result.message,
                        suggestion=f"Verify {result.tool_id} installation manually.",
                    )
                )

        # 2. Validate dependency graph
        logger.info("Validating dependency graph...")
        dep_issues = self._checker.validate_dependency_graph()
        for issue in dep_issues:
            report.diagnostics.append(
                DiagnosticMessage(
                    severity=issue.severity,
                    category="dependency_graph",
                    message=issue.message,
                    suggestion=f"Install {issue.dependency_id} before using {issue.tool_id}.",
                )
            )

        # 3. Validate configuration
        logger.info("Validating configuration...")
        config_issues = self._config_manager.validate_config()
        for issue in config_issues:
            report.diagnostics.append(
                DiagnosticMessage(
                    severity=Severity.WARNING,
                    category="configuration",
                    message=issue.message,
                    suggestion=issue.suggestion,
                )
            )

        # Determine overall health
        has_errors = any(
            d.severity in (Severity.ERROR, Severity.CRITICAL)
            for d in report.diagnostics
        )
        has_missing_core = any(
            r.status == ToolStatus.MISSING
            for r in report.tool_results
            if r.tool_id in ("ngspice", "kicad", "python3", "git")
        )
        report.overall_healthy = not has_errors and not has_missing_core

        logger.info(
            "Doctor report: %s (%d tools checked, %d diagnostics)",
            "HEALTHY" if report.overall_healthy else "ISSUES FOUND",
            len(report.tool_results),
            len(report.diagnostics),
        )

        return report
