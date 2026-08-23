"""Unit tests for OS detection."""

from unittest.mock import patch

from esim_tool_manager.infra.os_detect import ShellType, SystemInfo


class TestSystemInfo:
    """Tests for SystemInfo detection."""

    def test_os_family_windows(self) -> None:
        info = SystemInfo(_os_name="windows")
        assert info.os_family == "windows"
        assert info.is_windows is True
        assert info.is_linux is False
        assert info.is_macos is False

    def test_os_family_linux(self) -> None:
        info = SystemInfo(_os_name="linux")
        assert info.os_family == "linux"
        assert info.is_linux is True

    def test_os_family_darwin(self) -> None:
        info = SystemInfo(_os_name="darwin")
        assert info.os_family == "macos"
        assert info.is_macos is True

    def test_shell_detection_powershell(self) -> None:
        info = SystemInfo(_os_name="windows")
        with patch.dict("os.environ", {"PSModulePath": "something"}):
            # Need to clear the cache
            if "active_shell" in info.__dict__:
                del info.__dict__["active_shell"]
            assert info.active_shell == ShellType.POWERSHELL

    def test_to_dict(self) -> None:
        info = SystemInfo()
        data = info.to_dict()
        assert "os_family" in data
        assert "platform" in data
        assert "available_package_managers" in data

    def test_platform_summary_is_string(self) -> None:
        info = SystemInfo()
        assert isinstance(info.platform_summary, str)
        assert len(info.platform_summary) > 0
