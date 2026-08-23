"""Tool registry manager — loads, queries, and manages the tool registry.

Provides a RegistryManager class that:
- Loads the YAML seed registry on first run (idempotent)
- Provides CRUD operations on the tools table
- Loads and manages configuration profiles
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.models import (
    ConfigProfile,
    InstallStrategy,
    Tool,
    ToolCategory,
)

logger = logging.getLogger(__name__)


class RegistryManager:
    """Manages the tool registry backed by SQLite.

    Loads the seed registry YAML on first run and provides query methods
    for tool lookup, search, and category filtering.

    Args:
        db: The database manager to use for persistence.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def initialize(self) -> None:
        """Run migrations and seed the registry if the tools table is empty.

        This is safe to call multiple times — migrations are idempotent
        and seeding only happens if the tools table is empty.
        """
        self._db.run_migrations()
        if self._is_tools_table_empty():
            logger.info("Tools table is empty — loading seed registry")
            self._load_seed_registry()
        else:
            logger.debug("Tools table already populated — skipping seed")

    def _is_tools_table_empty(self) -> bool:
        """Check if the tools table has any rows."""
        if not self._db.table_exists("tools"):
            return True
        row = self._db.fetchone("SELECT COUNT(*) as cnt FROM tools")
        return row is not None and row["cnt"] == 0

    def _load_seed_registry(self) -> None:
        """Load tools and profiles from the seed YAML file into the database."""
        seed_data = self._read_seed_yaml()
        if not seed_data:
            logger.warning("No seed data found — registry will be empty")
            return

        tools_data = seed_data.get("tools", [])
        profiles_data = seed_data.get("profiles", [])

        for tool_data in tools_data:
            tool = self._parse_tool_from_seed(tool_data)
            self._insert_tool(tool)
            logger.debug("Seeded tool: %s", tool.id)

        for profile_data in profiles_data:
            profile = ConfigProfile.from_dict(profile_data)
            self._insert_profile(profile)
            logger.debug("Seeded profile: %s", profile.name)

        logger.info(
            "Seed registry loaded: %d tools, %d profiles",
            len(tools_data),
            len(profiles_data),
        )

    def _read_seed_yaml(self) -> dict[str, Any]:
        """Read the seed_registry.yaml from the package data."""
        try:
            seed_file = resources.files("esim_tool_manager.data") / "seed_registry.yaml"
            content = seed_file.read_text(encoding="utf-8")
            return yaml.safe_load(content) or {}
        except (TypeError, FileNotFoundError) as e:
            logger.warning("Could not read seed from package resources: %s", e)
            # Fallback: try filesystem path
            fallback = Path(__file__).parent / "seed_registry.yaml"
            if fallback.exists():
                content = fallback.read_text(encoding="utf-8")
                return yaml.safe_load(content) or {}
            return {}

    def _parse_tool_from_seed(self, data: dict[str, Any]) -> Tool:
        """Parse a tool entry from the YAML seed format into a Tool dataclass.

        The YAML format uses a slightly different structure for install_strategies
        (keyed by OS name rather than os_family value), so this method normalizes it.
        """
        strategies: dict[str, InstallStrategy] = {}
        for os_key, strategy_data in data.get("install_strategies", {}).items():
            strategy = InstallStrategy.from_dict(strategy_data)
            strategies[os_key] = strategy

        return Tool(
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

    def _insert_tool(self, tool: Tool) -> None:
        """Insert a tool into the database."""
        self._db.execute(
            """
            INSERT OR REPLACE INTO tools (id, display_name, description, category, data_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                tool.id,
                tool.display_name,
                tool.description,
                tool.category.value,
                json.dumps(tool.to_dict()),
            ),
        )
        self._db.commit()

    def _insert_profile(self, profile: ConfigProfile) -> None:
        """Insert a configuration profile into the database."""
        self._db.execute(
            """
            INSERT OR REPLACE INTO config_profiles
            (name, display_name, description, tool_ids_json, env_overrides_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                profile.name,
                profile.display_name,
                profile.description,
                json.dumps(profile.tool_ids),
                json.dumps(profile.env_overrides),
            ),
        )
        self._db.commit()

    # ── Query Methods ─────────────────────────────────────────────────

    def get_all_tools(self) -> list[Tool]:
        """Get all tools in the registry.

        Returns:
            List of all Tool objects, sorted by display name.
        """
        rows = self._db.fetchall(
            "SELECT data_json FROM tools ORDER BY display_name"
        )
        return [Tool.from_dict(json.loads(row["data_json"])) for row in rows]

    def get_tool(self, tool_id: str) -> Tool | None:
        """Get a specific tool by its ID.

        Args:
            tool_id: The unique tool identifier (e.g. 'ngspice').

        Returns:
            The Tool object, or None if not found.
        """
        row = self._db.fetchone(
            "SELECT data_json FROM tools WHERE id = ?", (tool_id,)
        )
        if row is None:
            return None
        return Tool.from_dict(json.loads(row["data_json"]))

    def search_tools(self, query: str) -> list[Tool]:
        """Search tools by name or description.

        Args:
            query: Search string (case-insensitive partial match).

        Returns:
            List of matching Tool objects.
        """
        rows = self._db.fetchall(
            """
            SELECT data_json FROM tools
            WHERE LOWER(display_name) LIKE ? OR LOWER(description) LIKE ?
            ORDER BY display_name
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [Tool.from_dict(json.loads(row["data_json"])) for row in rows]

    def get_tools_by_category(self, category: ToolCategory) -> list[Tool]:
        """Get all tools in a specific category.

        Args:
            category: The category to filter by.

        Returns:
            List of Tool objects in the specified category.
        """
        rows = self._db.fetchall(
            "SELECT data_json FROM tools WHERE category = ? ORDER BY display_name",
            (category.value,),
        )
        return [Tool.from_dict(json.loads(row["data_json"])) for row in rows]

    def get_tool_ids(self) -> list[str]:
        """Get all tool IDs in the registry.

        Returns:
            List of tool ID strings, sorted alphabetically.
        """
        rows = self._db.fetchall("SELECT id FROM tools ORDER BY id")
        return [row["id"] for row in rows]

    # ── Profile Methods ───────────────────────────────────────────────

    def get_all_profiles(self) -> list[ConfigProfile]:
        """Get all configuration profiles.

        Returns:
            List of all ConfigProfile objects.
        """
        rows = self._db.fetchall(
            "SELECT name, display_name, description, tool_ids_json, env_overrides_json "
            "FROM config_profiles ORDER BY name"
        )
        profiles = []
        for row in rows:
            profiles.append(
                ConfigProfile(
                    name=row["name"],
                    display_name=row["display_name"],
                    description=row["description"],
                    tool_ids=json.loads(row["tool_ids_json"]),
                    env_overrides=json.loads(row["env_overrides_json"]),
                )
            )
        return profiles

    def get_profile(self, name: str) -> ConfigProfile | None:
        """Get a specific profile by name.

        Args:
            name: The profile name (e.g. 'full-mixed-signal').

        Returns:
            The ConfigProfile object, or None if not found.
        """
        row = self._db.fetchone(
            "SELECT name, display_name, description, tool_ids_json, env_overrides_json "
            "FROM config_profiles WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        return ConfigProfile(
            name=row["name"],
            display_name=row["display_name"],
            description=row["description"],
            tool_ids=json.loads(row["tool_ids_json"]),
            env_overrides=json.loads(row["env_overrides_json"]),
        )

    # ── History Methods ───────────────────────────────────────────────

    def add_install_record(
        self,
        tool_id: str,
        version: str,
        method: str,
        success: bool,
        log_output: str = "",
        dry_run: bool = True,
    ) -> int:
        """Record an installation attempt.

        Args:
            tool_id: Which tool was installed.
            version: Version that was installed.
            method: Installation method used.
            success: Whether the installation succeeded.
            log_output: Captured output from the install process.
            dry_run: Whether this was a dry-run.

        Returns:
            The row ID of the inserted record.
        """
        return self._db.insert_json(
            "install_history",
            {
                "tool_id": tool_id,
                "version": version,
                "method": method,
                "success": 1 if success else 0,
                "dry_run": 1 if dry_run else 0,
                "log_output": log_output,
            },
        )

    def add_update_record(
        self,
        tool_id: str,
        from_version: str,
        to_version: str,
        success: bool,
        log_output: str = "",
    ) -> int:
        """Record an update attempt.

        Args:
            tool_id: Which tool was updated.
            from_version: Previous version.
            to_version: New version.
            success: Whether the update succeeded.
            log_output: Captured output from the update process.

        Returns:
            The row ID of the inserted record.
        """
        return self._db.insert_json(
            "update_history",
            {
                "tool_id": tool_id,
                "from_version": from_version,
                "to_version": to_version,
                "success": 1 if success else 0,
                "log_output": log_output,
            },
        )

    def get_install_history(
        self, tool_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get installation history records.

        Args:
            tool_id: Optional filter by tool ID.
            limit: Maximum number of records to return.

        Returns:
            List of history records as dictionaries.
        """
        if tool_id:
            rows = self._db.fetchall(
                "SELECT * FROM install_history WHERE tool_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (tool_id, limit),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM install_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in rows]

    def get_update_history(
        self, tool_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get update history records.

        Args:
            tool_id: Optional filter by tool ID.
            limit: Maximum number of records to return.

        Returns:
            List of history records as dictionaries.
        """
        if tool_id:
            rows = self._db.fetchall(
                "SELECT * FROM update_history WHERE tool_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (tool_id, limit),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM update_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in rows]
