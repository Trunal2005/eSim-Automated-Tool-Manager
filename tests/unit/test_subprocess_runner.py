"""Unit tests for the subprocess runner."""

import sys

from esim_tool_manager.infra.subprocess_runner import run_safe


class TestRunSafe:
    """Tests for safe subprocess execution."""

    def test_successful_command(self) -> None:
        result = run_safe([sys.executable, "--version"])
        assert result.success is True
        assert result.returncode == 0
        assert "Python" in result.stdout

    def test_command_not_found(self) -> None:
        result = run_safe(["nonexistent_command_xyz_123"])
        assert result.success is False
        assert "not found" in result.error_message.lower() or result.returncode != 0

    def test_command_with_args(self) -> None:
        result = run_safe([sys.executable, "-c", "print('hello')"])
        assert result.success is True
        assert "hello" in result.stdout

    def test_command_failure(self) -> None:
        result = run_safe([sys.executable, "-c", "import sys; sys.exit(1)"])
        assert result.success is False
        assert result.returncode == 1

    def test_timeout(self) -> None:
        result = run_safe(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout=1,
        )
        assert result.timed_out is True
        assert result.success is False

    def test_captures_stderr(self) -> None:
        result = run_safe(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"]
        )
        assert "error" in result.stderr

    def test_to_dict(self) -> None:
        result = run_safe([sys.executable, "--version"])
        data = result.to_dict()
        assert "command" in data
        assert "stdout" in data
        assert "success" in data
        assert data["success"] is True

    def test_never_uses_shell(self) -> None:
        # This test verifies the function doesn't accept shell=True
        # by checking the function doesn't have a shell parameter
        import inspect
        sig = inspect.signature(run_safe)
        params = sig.parameters
        # shell is not a parameter at all — it's hardcoded to False
        assert "shell" not in params
