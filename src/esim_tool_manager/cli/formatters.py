"""Rich-formatted output and JSON serialization for the CLI.

Provides formatters for:
- Color-coded status tables (green=OK, red=MISSING, yellow=OUTDATED)
- Progress bars for install/download operations
- JSON serialization for --json mode
"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from esim_tool_manager.data.models import Severity, ToolStatus

console = Console()

# Status color mapping
STATUS_COLORS = {
    ToolStatus.OK: "green",
    ToolStatus.MISSING: "red",
    ToolStatus.OUTDATED: "yellow",
    ToolStatus.VERSION_UNPARSEABLE: "cyan",
    ToolStatus.INCOMPATIBLE_OS: "dim",
}

STATUS_ICONS = {
    ToolStatus.OK: "✅",
    ToolStatus.MISSING: "❌",
    ToolStatus.OUTDATED: "⚠️",
    ToolStatus.VERSION_UNPARSEABLE: "❓",
    ToolStatus.INCOMPATIBLE_OS: "🚫",
}

SEVERITY_COLORS = {
    Severity.INFO: "blue",
    Severity.WARNING: "yellow",
    Severity.ERROR: "red",
    Severity.CRITICAL: "bold red",
}


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout."""
    console.print_json(json.dumps(data, indent=2, default=str))


def print_status_table(results: list[dict[str, Any]]) -> None:
    """Print a color-coded status table for tool check results."""
    table = Table(
        title="eSim Tool Status",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("", width=3)  # Status icon
    table.add_column("Tool", style="bold")
    table.add_column("Status")
    table.add_column("Installed")
    table.add_column("Required")
    table.add_column("Message", max_width=50)

    for result in results:
        status = ToolStatus(result["status"])
        color = STATUS_COLORS.get(status, "white")
        icon = STATUS_ICONS.get(status, "")

        table.add_row(
            icon,
            result["tool_id"],
            Text(status.value.upper(), style=color),
            result.get("installed_version") or "-",
            result.get("required_version") or "-",
            Text(result.get("message", "")[:50], style="dim"),
        )

    console.print(table)


def print_install_results(results: list[dict[str, Any]]) -> None:
    """Print install results as a formatted table."""
    table = Table(
        title="Installation Results",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Tool", style="bold")
    table.add_column("Method")
    table.add_column("Result")
    table.add_column("Details", max_width=60)

    for result in results:
        success = result.get("success", False)
        dry_run = result.get("dry_run", True)

        if dry_run:
            result_text = Text("DRY RUN", style="cyan")
        elif success:
            result_text = Text("SUCCESS", style="green")
        else:
            result_text = Text("FAILED", style="red")

        table.add_row(
            result["tool_id"],
            result.get("method", "-"),
            result_text,
            Text(result.get("message", "")[:60], style="dim"),
        )

    console.print(table)


def print_update_results(results: list[dict[str, Any]]) -> None:
    """Print update check or apply results."""
    if not results:
        console.print("[green]All tools are up to date![/green]")
        return

    table = Table(
        title="Available Updates",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Tool", style="bold")
    table.add_column("Installed")
    table.add_column("Available")
    table.add_column("Method")

    for result in results:
        table.add_row(
            result.get("tool_id") or result.get("display_name", ""),
            result.get("installed_version") or result.get("from_version", "-"),
            result.get("available_version") or result.get("to_version", "-"),
            result.get("method", "-"),
        )

    console.print(table)


def print_profiles(profiles: list[dict[str, Any]]) -> None:
    """Print configuration profiles as a table."""
    table = Table(
        title="Configuration Profiles",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Name", style="bold")
    table.add_column("Display Name")
    table.add_column("Description")
    table.add_column("Tools")

    for profile in profiles:
        tools = ", ".join(profile.get("tool_ids", []))
        table.add_row(
            profile["name"],
            profile["display_name"],
            profile["description"],
            tools,
        )

    console.print(table)


def print_history(records: list[dict[str, Any]], history_type: str = "install") -> None:
    """Print install/update history as a table."""
    if not records:
        console.print(f"[dim]No {history_type} history found.[/dim]")
        return

    table = Table(
        title=f"{history_type.title()} History",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Timestamp", style="dim")
    table.add_column("Tool", style="bold")

    if history_type == "install":
        table.add_column("Version")
        table.add_column("Method")
        table.add_column("Dry Run")
    else:
        table.add_column("From")
        table.add_column("To")

    table.add_column("Result")

    for record in records:
        success = record.get("success", 0)
        result_text = Text("✅" if success else "❌")
        timestamp = record.get("timestamp", "")

        if history_type == "install":
            table.add_row(
                timestamp,
                record.get("tool_id", ""),
                record.get("version", "-"),
                record.get("method", "-"),
                "Yes" if record.get("dry_run") else "No",
                result_text,
            )
        else:
            table.add_row(
                timestamp,
                record.get("tool_id", ""),
                record.get("from_version", "-"),
                record.get("to_version", "-"),
                result_text,
            )

    console.print(table)


def print_doctor_report(report: dict[str, Any]) -> None:
    """Print a doctor health check report."""
    summary = report.get("summary", {})
    healthy = report.get("overall_healthy", False)

    # Header
    if healthy:
        console.print("\n[bold green]🏥 System Health: HEALTHY[/bold green]\n")
    else:
        console.print("\n[bold red]🏥 System Health: ISSUES FOUND[/bold red]\n")

    # Summary
    console.print(f"  Tools checked: {summary.get('total_tools', 0)}")
    console.print(f"  [green]OK:[/green] {summary.get('ok', 0)}")
    console.print(f"  [red]Missing:[/red] {summary.get('missing', 0)}")
    console.print(f"  [yellow]Outdated:[/yellow] {summary.get('outdated', 0)}")
    console.print(f"  Diagnostics: {summary.get('diagnostics', 0)}")
    console.print()

    # Tool status table
    print_status_table(report.get("tool_results", []))

    # Diagnostics
    diagnostics = report.get("diagnostics", [])
    if diagnostics:
        console.print("\n[bold]Diagnostics:[/bold]")
        for diag in diagnostics:
            severity = diag.get("severity", "info")
            color = SEVERITY_COLORS.get(Severity(severity), "white")
            console.print(
                f"  [{color}][{severity.upper()}][/{color}] "
                f"{diag.get('message', '')}"
            )
            if diag.get("suggestion"):
                console.print(f"    [dim]→ {diag['suggestion']}[/dim]")
