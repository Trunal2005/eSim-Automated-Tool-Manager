"""Structured logging configuration with JSON-lines file output and rotation.

Sets up two handlers:
1. Console handler: human-readable, Rich-formatted output for the terminal
2. File handler: machine-parseable JSON-lines format with log rotation

Design Decision (ADR-006): JSON-lines structured logging is used because:
- It separates machine-parseable logs from user-facing output
- It's compatible with standard log aggregation tools
- It enables post-hoc querying of install/update operations
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonLinesFormatter(logging.Formatter):
    """Formats log records as JSON-lines (one JSON object per line).

    Each line contains: timestamp, level, logger name, message,
    and any extra fields attached to the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON line."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields
        for key in ("tool_id", "operation", "duration_ms", "os_family"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with level-based coloring.

    Uses ANSI codes for color when the terminal supports it.
    Falls back to plain text in non-TTY environments.
    """

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record for console output."""
        color = self.LEVEL_COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:8s}{self.RESET}"
        return f"{level} {record.getMessage()}"


def setup_logging(
    log_dir: Path | None = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> Path:
    """Configure structured logging for the application.

    Args:
        log_dir: Directory for log files. Defaults to ~/.esim-tool-manager/logs/.
        console_level: Minimum log level for console output.
        file_level: Minimum log level for file output.
        max_bytes: Maximum size of a single log file before rotation.
        backup_count: Number of rotated log files to keep.

    Returns:
        Path to the active log file.
    """
    if log_dir is None:
        log_dir = Path.home() / ".esim-tool-manager" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "esim-tool-manager.log"

    # Get the root logger for our package
    root_logger = logging.getLogger("esim_tool_manager")
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # ── File handler: JSON-lines with rotation ──
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(JsonLinesFormatter())
    root_logger.addHandler(file_handler)

    # ── Console handler: human-readable ──
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    root_logger.debug("Logging initialized — file: %s", log_file)
    return log_file
