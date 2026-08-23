"""Command-line interface for the eSim Tool Manager.

Uses Typer to provide a robust CLI with nested commands, auto-generated help,
and rich formatting (or JSON output for machine parsing).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from esim_tool_manager.cli import formatters
from esim_tool_manager.core.config_manager import ConfigManager
from esim_tool_manager.core.dependency_checker import DependencyChecker
from esim_tool_manager.core.doctor import Doctor
from esim_tool_manager.core.installer import Installer
from esim_tool_manager.core.updater import Updater
from esim_tool_manager.data.database import DatabaseManager
from esim_tool_manager.data.registry import RegistryManager
from esim_tool_manager.infra.logging_config import setup_logging
from esim_tool_manager.infra.os_detect import get_system_info

app = typer.Typer(
    name="esim-tool-manager",
    help="Automated Tool Manager for eSim — manages installation, updates, "
    "configuration, and dependencies for the eSim EDA toolchain.",
    add_completion=False,
    no_args_is_help=True,
)

# Global state to pass between callbacks and commands
state = {
    "json": False,
}

# --- Core Service Initialization ---


def get_services() -> dict[str, any]:
    """Initialize and return the core services."""
    db = DatabaseManager()
    db.__enter__()  # Ensure connection is open
    registry = RegistryManager(db)
    registry.initialize()

    system_info = get_system_info()
    checker = DependencyChecker(registry, system_info)
    config_manager = ConfigManager(registry, system_info)
    installer = Installer(registry, checker, system_info)
    updater = Updater(registry, checker, system_info)
    doctor = Doctor(checker, config_manager)

    return {
        "db": db,
        "registry": registry,
        "checker": checker,
        "config": config_manager,
        "installer": installer,
        "updater": updater,
        "doctor": doctor,
    }


# --- Global Options ---


@app.callback()
def main_callback(
    json_output: bool = typer.Option(
        False, "--json", help="Output results in machine-readable JSON format."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose debug logging."
    ),
) -> None:
    """eSim Tool Manager - CLI."""
    state["json"] = json_output
    console_level = logging.DEBUG if verbose else logging.INFO
    setup_logging(console_level=console_level)


# --- Commands ---


@app.command()
def status() -> None:
    """Show the status of all managed tools."""
    services = get_services()
    checker: DependencyChecker = services["checker"]

    summary = checker.get_summary()

    if state["json"]:
        formatters.print_json(summary)
    else:
        formatters.print_status_table(summary["results"])


@app.command()
def doctor() -> None:
    """Run a comprehensive system health check."""
    services = get_services()
    doctor_service: Doctor = services["doctor"]

    report = doctor_service.run()

    if state["json"]:
        formatters.print_json(report.to_dict())
    else:
        formatters.print_doctor_report(report.to_dict())
    
    if not report.overall_healthy:
        raise typer.Exit(code=1)


@app.command()
def install(
    tool_id: Optional[str] = typer.Argument(
        None, help="The ID of the tool to install (leave empty to install all via profile)."
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Configuration profile to install."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt and execute immediately (disables dry-run)."
    ),
) -> None:
    """Install a tool or all tools in a profile.
    
    By default, this runs as a DRY-RUN and shows what would happen.
    Use --yes to actually execute the installation.
    """
    services = get_services()
    installer: Installer = services["installer"]
    
    dry_run = not yes
    
    # Simple CLI confirmation callback
    def confirm(msg: str) -> bool:
        if state["json"]:
            return False  # Never prompt in JSON mode
        return typer.confirm(msg)
    
    confirm_cb = confirm if not dry_run else None

    if tool_id:
        result = installer.install_tool(tool_id, dry_run=dry_run, confirm_callback=confirm_cb)
        results = [result.to_dict()]
    else:
        install_results = installer.install_all(profile_name=profile, dry_run=dry_run, confirm_callback=confirm_cb)
        results = [r.to_dict() for r in install_results]

    if state["json"]:
        formatters.print_json(results)
    else:
        formatters.print_install_results(results)
    
    # Check for any failures
    if any(not r.get("success", False) for r in results):
        raise typer.Exit(code=1)


@app.command()
def update(
    tool_id: Optional[str] = typer.Argument(
        None, help="The ID of the tool to update (leave empty to update all)."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Execute the update immediately (disables dry-run)."
    ),
) -> None:
    """Check for and apply updates to tools.
    
    By default, this runs as a DRY-RUN and shows what would happen.
    Use --yes to actually execute the updates.
    """
    services = get_services()
    updater: Updater = services["updater"]
    
    dry_run = not yes

    if tool_id:
        result = updater.update_tool(tool_id, dry_run=dry_run)
        results = [result.to_dict()]
    else:
        if dry_run:
            # Just check updates if no tool is specified and we're in dry-run
            updates = updater.check_updates()
            results = [u.to_dict() for u in updates]
            if state["json"]:
                formatters.print_json(results)
            else:
                formatters.print_update_results(results)
            return
        
        update_results = updater.update_all(dry_run=dry_run)
        results = [r.to_dict() for r in update_results]

    if state["json"]:
        formatters.print_json(results)
    else:
        formatters.print_install_results(results)  # install and update results have similar structure
    
    if any(not r.get("success", False) for r in results):
        raise typer.Exit(code=1)


@app.command()
def history(
    kind: str = typer.Argument("install", help="'install' or 'update'"),
    tool: Optional[str] = typer.Option(None, "--tool", "-t", help="Filter by tool ID."),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of records to show."),
) -> None:
    """View installation or update history."""
    services = get_services()
    registry: RegistryManager = services["registry"]
    
    if kind.lower() == "install":
        records = registry.get_install_history(tool_id=tool, limit=limit)
    elif kind.lower() == "update":
        records = registry.get_update_history(tool_id=tool, limit=limit)
    else:
        typer.secho(f"Unknown history kind: {kind}. Use 'install' or 'update'.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if state["json"]:
        formatters.print_json(records)
    else:
        formatters.print_history(records, history_type=kind.lower())


@app.command()
def profiles() -> None:
    """List available configuration profiles."""
    services = get_services()
    config_mgr: ConfigManager = services["config"]
    
    prof_list = config_mgr.get_profiles()
    results = [p.to_dict() for p in prof_list]
    
    if state["json"]:
        formatters.print_json(results)
    else:
        formatters.print_profiles(results)


@app.command()
def apply_profile(
    name: str = typer.Argument(..., help="Name of the profile to apply."),
    persist: bool = typer.Option(False, "--persist", help="Persist environment variables to your shell profile."),
) -> None:
    """Apply a configuration profile's environment variables."""
    services = get_services()
    config_mgr: ConfigManager = services["config"]
    
    applied = config_mgr.apply_profile(name, persist=persist)
    
    if not applied:
        if state["json"]:
            formatters.print_json({"success": False, "message": f"Profile '{name}' not found or empty."})
        else:
            typer.secho(f"Profile '{name}' not found or has no environment variables.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    result = {
        "success": True,
        "profile": name,
        "env_vars_set": applied,
        "persisted": persist
    }
    
    if state["json"]:
        formatters.print_json(result)
    else:
        typer.secho(f"Applied profile '{name}' successfully.", fg=typer.colors.GREEN)
        for k, v in applied.items():
            typer.echo(f"  {k}={v}")


def main() -> None:
    """Entry point for the CLI application."""
    try:
        app()
    except Exception as e:
        if state.get("json"):
            formatters.print_json({"error": str(e), "success": False})
        else:
            typer.secho(f"Error: {e}", fg=typer.colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()
