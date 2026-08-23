"""Unit tests for the CLI."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from esim_tool_manager.cli.app import app

runner = CliRunner()


@patch("esim_tool_manager.cli.app.get_services")
def test_status_command(mock_get_services) -> None:
    # Setup mock
    mock_checker = mock_get_services.return_value["checker"]
    mock_checker.get_summary.return_value = {
        "total_tools": 1,
        "status_counts": {"ok": 1},
        "results": [
            {
                "tool_id": "ngspice",
                "status": "ok",
                "installed_version": "47",
                "required_version": "40",
                "message": "All good",
            }
        ],
    }

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "eSim Tool Status" in result.stdout
    assert "ngspice" in result.stdout


@patch("esim_tool_manager.cli.app.get_services")
def test_status_command_json(mock_get_services) -> None:
    # Setup mock
    mock_checker = mock_get_services.return_value["checker"]
    mock_checker.get_summary.return_value = {
        "total_tools": 1,
        "results": [{"tool_id": "ngspice", "status": "ok"}],
    }

    result = runner.invoke(app, ["--json", "status"])
    assert result.exit_code == 0
    
    # Verify valid JSON
    data = json.loads(result.stdout)
    assert data["total_tools"] == 1
    assert data["results"][0]["tool_id"] == "ngspice"


@patch("esim_tool_manager.cli.app.get_services")
def test_doctor_healthy(mock_get_services) -> None:
    mock_doctor = mock_get_services.return_value["doctor"]
    
    class MockReport:
        overall_healthy = True
        def to_dict(self):
            return {"overall_healthy": True, "summary": {"total_tools": 1}}
            
    mock_doctor.run.return_value = MockReport()

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "HEALTHY" in result.stdout


@patch("esim_tool_manager.cli.app.get_services")
def test_doctor_unhealthy(mock_get_services) -> None:
    mock_doctor = mock_get_services.return_value["doctor"]
    
    class MockReport:
        overall_healthy = False
        def to_dict(self):
            return {"overall_healthy": False, "summary": {"total_tools": 1}}
            
    mock_doctor.run.return_value = MockReport()

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "ISSUES FOUND" in result.stdout


@patch("esim_tool_manager.cli.app.get_services")
def test_install_dry_run(mock_get_services) -> None:
    mock_installer = mock_get_services.return_value["installer"]
    
    class MockResult:
        success = True
        def to_dict(self):
            return {"tool_id": "ngspice", "success": True, "dry_run": True, "message": "Would install"}
            
    mock_installer.install_tool.return_value = MockResult()

    result = runner.invoke(app, ["install", "ngspice"])
    assert result.exit_code == 0
    assert "ngspice" in result.stdout
    assert "DRY RUN" in result.stdout


@patch("esim_tool_manager.cli.app.get_services")
def test_profiles_command(mock_get_services) -> None:
    mock_config = mock_get_services.return_value["config"]
    
    class MockProfile:
        def to_dict(self):
            return {
                "name": "test-profile",
                "display_name": "Test",
                "description": "A test profile",
                "tool_ids": ["git"]
            }
            
    mock_config.get_profiles.return_value = [MockProfile()]

    result = runner.invoke(app, ["profiles"])
    assert result.exit_code == 0
    assert "Configuration Profiles" in result.stdout
    assert "test-profile" in result.stdout
