"""Operating system, distribution, and shell detection.

Provides a SystemInfo singleton that caches detected information about
the current system: OS family, Linux distro, active shell, and available
package managers.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LinuxDistroFamily(Enum):
    """Major Linux distribution families."""

    DEBIAN = "debian"      # Ubuntu, Debian, Mint, Pop!_OS
    REDHAT = "redhat"      # Fedora, RHEL, CentOS, Rocky
    ARCH = "arch"          # Arch, Manjaro, EndeavourOS
    SUSE = "suse"          # openSUSE, SLES
    UNKNOWN = "unknown"


class ShellType(Enum):
    """Common shell types."""

    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"
    POWERSHELL = "powershell"
    CMD = "cmd"
    UNKNOWN = "unknown"


class PackageManagerType(Enum):
    """Supported system package managers."""

    APT = "apt"
    DNF = "dnf"
    PACMAN = "pacman"
    ZYPPER = "zypper"
    BREW = "brew"
    CHOCO = "choco"


@dataclass
class SystemInfo:
    """Cached information about the current operating system and environment.

    All properties are computed lazily and cached on first access.
    Use `SystemInfo.detect()` to create an instance.
    """

    _os_name: str = field(default_factory=lambda: platform.system().lower())

    @cached_property
    def os_family(self) -> str:
        """The OS family: 'linux', 'windows', or 'macos'."""
        mapping = {
            "linux": "linux",
            "darwin": "macos",
            "windows": "windows",
        }
        return mapping.get(self._os_name, self._os_name)

    @cached_property
    def is_linux(self) -> bool:
        """Whether the current OS is Linux."""
        return self.os_family == "linux"

    @cached_property
    def is_windows(self) -> bool:
        """Whether the current OS is Windows."""
        return self.os_family == "windows"

    @cached_property
    def is_macos(self) -> bool:
        """Whether the current OS is macOS."""
        return self.os_family == "macos"

    @cached_property
    def linux_distro_family(self) -> LinuxDistroFamily:
        """The Linux distribution family, or UNKNOWN on non-Linux systems."""
        if not self.is_linux:
            return LinuxDistroFamily.UNKNOWN

        # Try reading /etc/os-release (standard on modern Linux)
        os_release = self._read_os_release()
        id_like = os_release.get("ID_LIKE", "").lower()
        distro_id = os_release.get("ID", "").lower()

        # Check ID_LIKE first (e.g., Ubuntu has ID_LIKE="debian")
        for family_id, family in [
            ("debian", LinuxDistroFamily.DEBIAN),
            ("ubuntu", LinuxDistroFamily.DEBIAN),
            ("rhel", LinuxDistroFamily.REDHAT),
            ("fedora", LinuxDistroFamily.REDHAT),
            ("centos", LinuxDistroFamily.REDHAT),
            ("arch", LinuxDistroFamily.ARCH),
            ("suse", LinuxDistroFamily.SUSE),
        ]:
            if family_id in id_like or family_id in distro_id:
                return family

        return LinuxDistroFamily.UNKNOWN

    @cached_property
    def linux_distro_name(self) -> str:
        """The Linux distribution pretty name (e.g. 'Ubuntu 24.04 LTS')."""
        if not self.is_linux:
            return ""
        os_release = self._read_os_release()
        return os_release.get("PRETTY_NAME", "Unknown Linux")

    @cached_property
    def active_shell(self) -> ShellType:
        """The currently active shell."""
        if self.is_windows:
            # Check for PowerShell vs cmd
            if os.environ.get("PSModulePath"):
                return ShellType.POWERSHELL
            return ShellType.CMD

        shell_path = os.environ.get("SHELL", "")
        shell_name = Path(shell_path).name.lower() if shell_path else ""

        shell_map = {
            "bash": ShellType.BASH,
            "zsh": ShellType.ZSH,
            "fish": ShellType.FISH,
        }
        return shell_map.get(shell_name, ShellType.UNKNOWN)

    @cached_property
    def shell_profile_path(self) -> Path | None:
        """Path to the current shell's profile/rc file for env var persistence."""
        home = Path.home()

        profile_map = {
            ShellType.BASH: [home / ".bashrc", home / ".bash_profile"],
            ShellType.ZSH: [home / ".zshrc"],
            ShellType.FISH: [home / ".config" / "fish" / "config.fish"],
            ShellType.POWERSHELL: self._get_powershell_profile_paths(),
        }

        candidates = profile_map.get(self.active_shell, [])
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate

        # Return the first candidate even if it doesn't exist yet
        if candidates and candidates[0]:
            return candidates[0]

        return None

    @cached_property
    def available_package_managers(self) -> list[PackageManagerType]:
        """List of package managers available on this system."""
        available = []
        for pm in PackageManagerType:
            cmd = pm.value
            if pm == PackageManagerType.APT:
                cmd = "apt-get"  # apt-get is more scriptable than apt
            if shutil.which(cmd):
                available.append(pm)
        return available

    @cached_property
    def platform_summary(self) -> str:
        """A human-readable one-line summary of the platform."""
        parts = [platform.system(), platform.release()]
        if self.is_linux and self.linux_distro_name:
            parts.append(f"({self.linux_distro_name})")
        parts.append(f"[{platform.machine()}]")
        return " ".join(parts)

    def _read_os_release(self) -> dict[str, str]:
        """Read and parse /etc/os-release on Linux."""
        result: dict[str, str] = {}
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, _, value = line.partition("=")
                        result[key] = value.strip('"')
        except (FileNotFoundError, PermissionError):
            pass
        return result

    def _get_powershell_profile_paths(self) -> list[Path]:
        """Get possible PowerShell profile paths."""
        # PowerShell stores its profile path in $PROFILE
        ps_profile = os.environ.get("USERPROFILE", "")
        if ps_profile:
            docs = Path(ps_profile) / "Documents"
            return [
                docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
                docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
            ]
        return []

    def to_dict(self) -> dict[str, Any]:
        """Serialize system info to a dictionary for JSON output."""
        return {
            "os_family": self.os_family,
            "platform": self.platform_summary,
            "linux_distro_family": self.linux_distro_family.value,
            "linux_distro_name": self.linux_distro_name,
            "active_shell": self.active_shell.value,
            "shell_profile_path": str(self.shell_profile_path) if self.shell_profile_path else None,
            "available_package_managers": [pm.value for pm in self.available_package_managers],
        }

    @classmethod
    def detect(cls) -> SystemInfo:
        """Create a SystemInfo instance with auto-detected values."""
        info = cls()
        logger.debug("Detected system: %s", info.platform_summary)
        return info


# Module-level singleton for convenience
_system_info: SystemInfo | None = None


def get_system_info() -> SystemInfo:
    """Get the cached SystemInfo singleton."""
    global _system_info
    if _system_info is None:
        _system_info = SystemInfo.detect()
    return _system_info
