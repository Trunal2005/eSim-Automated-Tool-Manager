"""Safe subprocess execution wrapper.

Provides a `run_safe` function that:
- Never uses shell=True (security: prevents shell injection)
- Enforces timeouts on all subprocess calls
- Returns structured results, not raw exceptions
- Produces actionable error messages, never raw tracebacks to the user
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # seconds


@dataclass(frozen=True)
class SubprocessResult:
    """Structured result from a subprocess execution.

    Attributes:
        command: The command that was executed (as a list of strings).
        stdout: Captured standard output.
        stderr: Captured standard error.
        returncode: Process exit code (0 = success).
        timed_out: Whether the process was killed due to timeout.
        error_message: Human-readable error description, if applicable.
    """

    command: list[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False
    error_message: str = ""

    @property
    def success(self) -> bool:
        """Whether the command completed successfully (return code 0, no timeout)."""
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON output."""
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "success": self.success,
            "error_message": self.error_message,
        }


def run_safe(
    cmd: list[str],
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
) -> SubprocessResult:
    """Execute a command safely without shell=True.

    This is the ONLY way subprocess calls should be made in this application.
    It enforces security (no shell injection), reliability (timeout-bound),
    and usability (structured error messages).

    Args:
        cmd: Command to execute as a list of strings (e.g. ['git', '--version']).
        timeout: Maximum execution time in seconds.
        cwd: Working directory for the command.
        env: Environment variables to set for the subprocess.
        capture_output: Whether to capture stdout/stderr.

    Returns:
        A SubprocessResult with the command's output and exit status.
    """
    logger.debug("Running command: %s (timeout=%ds)", cmd, timeout)

    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            shell=False,  # NEVER shell=True — security requirement
        )
        return SubprocessResult(
            command=cmd,
            stdout=result.stdout.strip() if result.stdout else "",
            stderr=result.stderr.strip() if result.stderr else "",
            returncode=result.returncode,
        )

    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, cmd)
        return SubprocessResult(
            command=cmd,
            timed_out=True,
            returncode=-1,
            error_message=f"Command timed out after {timeout} seconds: {' '.join(cmd)}",
        )

    except FileNotFoundError:
        logger.debug("Command not found: %s", cmd[0])
        return SubprocessResult(
            command=cmd,
            returncode=-1,
            error_message=f"Command not found: '{cmd[0]}'. "
            f"Is it installed and on your PATH?",
        )

    except PermissionError:
        logger.warning("Permission denied running: %s", cmd)
        return SubprocessResult(
            command=cmd,
            returncode=-1,
            error_message=f"Permission denied running '{cmd[0]}'. "
            f"You may need elevated privileges.",
        )

    except OSError as e:
        logger.error("OS error running %s: %s", cmd, e)
        return SubprocessResult(
            command=cmd,
            returncode=-1,
            error_message=f"OS error running '{cmd[0]}': {e}",
        )
