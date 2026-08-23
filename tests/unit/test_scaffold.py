"""Scaffold verification test — ensures the package is importable."""

from esim_tool_manager import __version__, __app_name__


def test_version_is_set() -> None:
    """The package version should be a semantic version string."""
    assert __version__ == "0.1.0"


def test_app_name_is_set() -> None:
    """The app name should match the console-script entry."""
    assert __app_name__ == "esim-tool-manager"
