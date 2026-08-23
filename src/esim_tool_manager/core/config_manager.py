"""Configuration manager — persists env vars, paths, and named profiles.

Handles per-tool environment variables, install paths, shell profile
persistence, and named configuration profiles (e.g. 'minimal-analog',
'full-mixed-signal', 'digital-only').
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from esim_tool_manager.data.models import ConfigProfile
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.os_detect import SystemInfo, get_system_info

logger = logging.getLogger(__name__)


@dataclass
class ConfigIssue:
    """A configuration validation issue.

    Attributes:
        tool_id: The tool with the issue.
        key: The config key (env var name, path, etc.)
        message: Description of the issue.
        current_value: The current (possibly invalid) value.
        suggestion: Suggested fix.
    """

    tool_id: str
    key: str
    message: str
    current_value: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "tool_id": self.tool_id,
            "key": self.key,
            "message": self.message,
            "current_value": self.current_value,
            "suggestion": self.suggestion,
        }


class ConfigManager:
    """Manages tool configuration, environment variables, and profiles.

    Args:
        registry: The tool registry.
        system_info: System information for shell detection.
    """

    def __init__(
        self,
        registry: RegistryManager,
        system_info: SystemInfo | None = None,
    ) -> None:
        self._registry = registry
        self._system_info = system_info or get_system_info()

    def get_env_var(self, key: str) -> str | None:
        """Get the current value of an environment variable.

        Args:
            key: Environment variable name.

        Returns:
            The value, or None if not set.
        """
        return os.environ.get(key)

    def set_env_var(
        self,
        key: str,
        value: str,
        persist: bool = False,
        tool_id: str | None = None,
    ) -> bool:
        """Set an environment variable.

        Args:
            key: Environment variable name.
            value: Value to set.
            persist: If True, also write to the shell profile file.
            tool_id: Optional tool ID for tracking.

        Returns:
            True if the env var was set successfully.
        """
        # Set in current process
        os.environ[key] = value
        logger.info("Set environment variable: %s=%s", key, value)

        # Persist to DB if tool_id provided
        if tool_id:
            self._registry._db.execute(
                """
                INSERT OR REPLACE INTO tool_config (tool_id, key, value, config_type)
                VALUES (?, ?, ?, 'env_var')
                """,
                (tool_id, key, value),
            )
            self._registry._db.commit()

        # Persist to shell profile
        if persist:
            return self._persist_to_shell_profile(key, value)

        return True

    def get_tool_config(self, tool_id: str) -> dict[str, str]:
        """Get all stored configuration for a tool.

        Args:
            tool_id: The tool to query.

        Returns:
            Dictionary of config key -> value.
        """
        rows = self._registry._db.fetchall(
            "SELECT key, value FROM tool_config WHERE tool_id = ?",
            (tool_id,),
        )
        return {row["key"]: row["value"] for row in rows}

    def validate_config(self) -> list[ConfigIssue]:
        """Validate all tool configurations.

        Checks that configured paths exist, env vars are set, etc.

        Returns:
            List of ConfigIssue objects for any problems found.
        """
        issues: list[ConfigIssue] = []
        tools = self._registry.get_all_tools()

        for tool in tools:
            # Check expected env vars
            for env_key, description in tool.env_vars.items():
                value = os.environ.get(env_key)
                if value:
                    # Verify the path exists if it looks like a path
                    if env_key.endswith(("HOME", "ROOT", "PREFIX", "PATH")):
                        if not Path(value).exists():
                            issues.append(
                                ConfigIssue(
                                    tool_id=tool.id,
                                    key=env_key,
                                    message=f"Environment variable {env_key} is set to "
                                    f"'{value}', but this path does not exist.",
                                    current_value=value,
                                    suggestion=f"Update {env_key} to point to the actual "
                                    f"{tool.display_name} installation directory.",
                                )
                            )

            # Check expected install paths
            os_family = self._system_info.os_family
            expected_path = tool.expected_paths.get(os_family)
            if expected_path and expected_path.strip():
                if not Path(expected_path).exists():
                    # This is just informational — the tool might be installed elsewhere
                    logger.debug(
                        "%s expected path %s does not exist (may be installed elsewhere)",
                        tool.display_name,
                        expected_path,
                    )

        return issues

    def get_profiles(self) -> list[ConfigProfile]:
        """Get all available configuration profiles.

        Returns:
            List of ConfigProfile objects.
        """
        return self._registry.get_all_profiles()

    def get_profile(self, name: str) -> ConfigProfile | None:
        """Get a specific profile by name.

        Args:
            name: Profile name.

        Returns:
            The ConfigProfile, or None if not found.
        """
        return self._registry.get_profile(name)

    def apply_profile(self, name: str, persist: bool = False) -> dict[str, str]:
        """Apply a configuration profile.

        Sets all environment variables defined in the profile's tools
        and env_overrides.

        Args:
            name: Profile name to apply.
            persist: If True, persist env vars to shell profile.

        Returns:
            Dictionary of all env vars that were set.
        """
        profile = self._registry.get_profile(name)
        if profile is None:
            logger.warning("Profile '%s' not found", name)
            return {}

        applied: dict[str, str] = {}

        # Apply env_overrides from the profile
        for key, value in profile.env_overrides.items():
            self.set_env_var(key, value, persist=persist)
            applied[key] = value

        logger.info("Applied profile '%s': %d env vars set", name, len(applied))
        return applied

    def _persist_to_shell_profile(self, key: str, value: str) -> bool:
        """Write an environment variable export to the user's shell profile.

        Args:
            key: Environment variable name.
            value: Value to export.

        Returns:
            True if successfully written.
        """
        profile_path = self._system_info.shell_profile_path
        if profile_path is None:
            logger.warning("Could not determine shell profile path")
            return False

        shell = self._system_info.active_shell

        # Format the export line based on shell type
        from esim_tool_manager.infra.os_detect import ShellType

        if shell == ShellType.FISH:
            export_line = f'set -gx {key} "{value}"'
        elif shell == ShellType.POWERSHELL:
            export_line = f'$env:{key} = "{value}"'
        else:
            # bash, zsh, and others use export
            export_line = f'export {key}="{value}"'

        # Check if already set in the profile
        marker = f"# esim-tool-manager: {key}"
        try:
            if profile_path.exists():
                content = profile_path.read_text(encoding="utf-8")
                if marker in content:
                    # Update existing entry
                    lines = content.splitlines()
                    new_lines = []
                    for line in lines:
                        if marker in line:
                            new_lines.append(f"{export_line}  {marker}")
                        else:
                            new_lines.append(line)
                    profile_path.write_text(
                        "\n".join(new_lines) + "\n", encoding="utf-8"
                    )
                    logger.info("Updated %s in %s", key, profile_path)
                    return True

            # Append new entry
            with open(profile_path, "a", encoding="utf-8") as f:
                f.write(f"\n{export_line}  {marker}\n")

            logger.info("Added %s to %s", key, profile_path)
            return True

        except OSError as e:
            logger.error("Failed to write to %s: %s", profile_path, e)
            return False
