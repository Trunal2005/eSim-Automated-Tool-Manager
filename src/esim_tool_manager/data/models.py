"""Data models for the eSim Tool Manager.

Defines the core data structures used throughout the application:
tools, install strategies, check results, configuration, and history records.
All models use dataclasses with full type hints for clarity and immutability.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ToolCategory(enum.Enum):
    """Categories of EDA tools managed by the tool manager.

    Each tool belongs to one primary category that describes its role
    in the eSim toolchain.
    """

    SIMULATION = "simulation"
    SCHEMATIC = "schematic"
    PCB = "pcb"
    DIGITAL = "digital"
    ANALOG = "analog"
    VCS = "vcs"
    RUNTIME = "runtime"
    SYSTEM = "system"


class ToolStatus(enum.Enum):
    """Result of checking a tool's installation status.

    Attributes:
        OK: Tool is installed and meets the minimum version requirement.
        MISSING: Tool is not found on the system.
        OUTDATED: Tool is installed but below the minimum required version.
        VERSION_UNPARSEABLE: Tool is installed but its version output could not be parsed.
        INCOMPATIBLE_OS: Tool is not supported on the current operating system.
    """

    OK = "ok"
    MISSING = "missing"
    OUTDATED = "outdated"
    VERSION_UNPARSEABLE = "version_unparseable"
    INCOMPATIBLE_OS = "incompatible_os"


class OSFamily(enum.Enum):
    """Supported operating system families."""

    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"


class InstallMethod(enum.Enum):
    """How a tool can be installed on a given OS.

    Attributes:
        PACKAGE_MANAGER: Install via the system's native package manager (apt/brew/choco).
        DIRECT_DOWNLOAD: Download a binary/archive from a URL and extract/install manually.
        MANUAL: Requires manual installation; the tool manager provides instructions only.
    """

    PACKAGE_MANAGER = "package_manager"
    DIRECT_DOWNLOAD = "direct_download"
    MANUAL = "manual"


class Severity(enum.Enum):
    """Severity level for diagnostic messages from the doctor/health-check."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class InstallStrategy:
    """Describes how to install a tool on a specific OS.

    Attributes:
        os_family: Which OS this strategy applies to.
        method: The installation method (package manager, direct download, or manual).
        package_name: Package name for the system package manager (e.g. 'ngspice' for apt).
        download_url: URL for direct downloads.
        checksum_sha256: Expected SHA256 checksum of the downloaded file.
        manual_url: Documentation URL for manual installation.
        extra_commands: Additional shell commands to run after installation (list of arg lists).
    """

    os_family: OSFamily
    method: InstallMethod
    package_name: str | None = None
    download_url: str | None = None
    checksum_sha256: str | None = None
    manual_url: str | None = None
    extra_commands: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON/DB storage."""
        return {
            "os_family": self.os_family.value,
            "method": self.method.value,
            "package_name": self.package_name,
            "download_url": self.download_url,
            "checksum_sha256": self.checksum_sha256,
            "manual_url": self.manual_url,
            "extra_commands": self.extra_commands,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallStrategy:
        """Deserialize from a dictionary."""
        return cls(
            os_family=OSFamily(data["os_family"]),
            method=InstallMethod(data["method"]),
            package_name=data.get("package_name"),
            download_url=data.get("download_url"),
            checksum_sha256=data.get("checksum_sha256"),
            manual_url=data.get("manual_url"),
            extra_commands=data.get("extra_commands", []),
        )


@dataclass
class Tool:
    """A managed tool in the eSim toolchain.

    Represents a single external tool (e.g. Ngspice, KiCad) with all metadata
    needed to detect, install, update, and configure it across platforms.

    Attributes:
        id: Unique identifier (lowercase, e.g. 'ngspice').
        display_name: Human-readable name (e.g. 'Ngspice').
        description: Brief description of the tool's purpose.
        category: Which EDA category the tool belongs to.
        version_command: Shell command (as arg list) to check the installed version.
        version_regex: Regex pattern to extract the version string from command output.
        min_version: Minimum acceptable version string.
        known_good_version: A known-good/latest verified version string.
        install_strategies: Per-OS installation strategies.
        env_vars: Environment variables this tool expects (name -> description).
        expected_paths: Expected install paths per OS family.
        dependencies: List of tool IDs this tool depends on.
        homepage: Project homepage URL.
    """

    id: str
    display_name: str
    description: str
    category: ToolCategory
    version_command: list[str]
    version_regex: str
    min_version: str
    known_good_version: str
    install_strategies: dict[str, InstallStrategy] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    expected_paths: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    homepage: str = ""

    def get_strategy_for_os(self, os_family: OSFamily) -> InstallStrategy | None:
        """Get the install strategy for a specific OS, or None if unsupported."""
        return self.install_strategies.get(os_family.value)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON/DB storage."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category.value,
            "version_command": self.version_command,
            "version_regex": self.version_regex,
            "min_version": self.min_version,
            "known_good_version": self.known_good_version,
            "install_strategies": {
                k: v.to_dict() for k, v in self.install_strategies.items()
            },
            "env_vars": self.env_vars,
            "expected_paths": self.expected_paths,
            "dependencies": self.dependencies,
            "homepage": self.homepage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tool:
        """Deserialize from a dictionary (e.g. from YAML seed or DB JSON)."""
        strategies = {}
        for key, val in data.get("install_strategies", {}).items():
            strategies[key] = InstallStrategy.from_dict(val)

        return cls(
            id=data["id"],
            display_name=data["display_name"],
            description=data["description"],
            category=ToolCategory(data["category"]),
            version_command=data["version_command"],
            version_regex=data["version_regex"],
            min_version=data["min_version"],
            known_good_version=data["known_good_version"],
            install_strategies=strategies,
            env_vars=data.get("env_vars", {}),
            expected_paths=data.get("expected_paths", {}),
            dependencies=data.get("dependencies", []),
            homepage=data.get("homepage", ""),
        )


@dataclass(frozen=True)
class ToolCheckResult:
    """Result of checking a single tool's installation status.

    Attributes:
        tool_id: The tool that was checked.
        status: The determined status.
        installed_version: The detected version string, if any.
        required_version: The minimum required version.
        message: Human-readable explanation of the result.
        executable_path: Path to the found executable, if any.
    """

    tool_id: str
    status: ToolStatus
    installed_version: str | None = None
    required_version: str = ""
    message: str = ""
    executable_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        return {
            "tool_id": self.tool_id,
            "status": self.status.value,
            "installed_version": self.installed_version,
            "required_version": self.required_version,
            "message": self.message,
            "executable_path": self.executable_path,
        }


@dataclass(frozen=True)
class DependencyIssue:
    """A specific dependency-graph issue (e.g. missing transitive dependency).

    Attributes:
        tool_id: The tool that has the issue.
        dependency_id: The dependency that's problematic.
        severity: How severe the issue is.
        message: Human-readable description.
    """

    tool_id: str
    dependency_id: str
    severity: Severity
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        return {
            "tool_id": self.tool_id,
            "dependency_id": self.dependency_id,
            "severity": self.severity.value,
            "message": self.message,
        }


@dataclass
class InstallRecord:
    """A record of a tool installation attempt.

    Attributes:
        tool_id: Which tool was installed.
        version: Version that was installed.
        method: How it was installed.
        success: Whether the installation succeeded.
        timestamp: When the installation was attempted.
        log_output: Captured stdout/stderr from the install process.
        dry_run: Whether this was a dry-run (no actual changes).
    """

    tool_id: str
    version: str
    method: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    log_output: str = ""
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "version": self.version,
            "method": self.method,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "log_output": self.log_output,
            "dry_run": self.dry_run,
        }


@dataclass
class UpdateRecord:
    """A record of a tool update attempt.

    Attributes:
        tool_id: Which tool was updated.
        from_version: Previous version.
        to_version: New version.
        success: Whether the update succeeded.
        timestamp: When the update was attempted.
        log_output: Captured output from the update process.
    """

    tool_id: str
    from_version: str
    to_version: str
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    log_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "log_output": self.log_output,
        }


@dataclass
class ConfigProfile:
    """A named configuration profile bundling a set of tools and settings.

    Profiles allow users to quickly switch between different eSim configurations
    (e.g. 'minimal-analog' vs 'full-mixed-signal' vs 'digital-only').

    Attributes:
        name: Profile identifier (e.g. 'full-mixed-signal').
        display_name: Human-readable name.
        description: What this profile is for.
        tool_ids: List of tool IDs included in this profile.
        env_overrides: Additional environment variable overrides.
    """

    name: str
    display_name: str
    description: str
    tool_ids: list[str] = field(default_factory=list)
    env_overrides: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "tool_ids": self.tool_ids,
            "env_overrides": self.env_overrides,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfigProfile:
        """Deserialize from a dictionary."""
        return cls(
            name=data["name"],
            display_name=data["display_name"],
            description=data["description"],
            tool_ids=data.get("tool_ids", []),
            env_overrides=data.get("env_overrides", {}),
        )


@dataclass(frozen=True)
class DiagnosticMessage:
    """A single diagnostic message from the doctor/health-check system.

    Attributes:
        severity: How important this message is.
        category: What aspect of the system this relates to (e.g. 'dependency', 'config').
        message: Human-readable description.
        suggestion: Suggested action to resolve the issue.
    """

    severity: Severity
    category: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
        }
