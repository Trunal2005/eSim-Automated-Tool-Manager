# eSim Automated Tool Manager

> Automated Tool Manager for eSim — manages installation, updates, configuration, and dependencies for the eSim EDA toolchain (FOSSEE, IIT Bombay).

[![Python Support](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CI Matrix](https://github.com/trunalpatil/esim-tool-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/trunalpatil/esim-tool-manager/actions/workflows/ci.yml)

A production-grade tool to tame the complexity of installing and configuring the eSim electronic design automation (EDA) suite across Linux, Windows, and macOS. 

This project was built as a screening task for the FOSSEE Semester Long Internship (Autumn 2026).

## Features

- **Safe By Default**: All mutating operations (install/update) default to a `dry-run`, ensuring you know exactly what will happen before modifying your system.
- **Dependency Resolution**: Models the eSim toolchain as a Directed Acyclic Graph (DAG), guaranteeing tools like GHDL and Ngspice are installed before NGHDL.
- **Dual Interfaces**: Includes a rich, color-coded Typer CLI and a responsive PyQt6 GUI.
- **Robust Architecture**: Built with a clean layered architecture, ensuring the UI is decoupled from core logic.
- **JSON Output**: First-class support for machine-readable JSON output via the `--json` flag for scripting and integration.
- **Health Checks**: A comprehensive `doctor` command validates paths, versions, and dependencies in one shot.

## Architecture

Please review the Architecture Decision Records (ADRs) for insights into the design philosophy:
- [ADR-001: SQLite for State](docs/architecture/decisions/001-sqlite-for-state.md)
- [ADR-002: Dry-Run Default](docs/architecture/decisions/002-dry-run-default.md)
- [ADR-003: Strict Subprocess Safety](docs/architecture/decisions/003-subprocess-safety.md)
- [ADR-004: DAG for Dependencies](docs/architecture/decisions/004-dag-dependencies.md)
- [ADR-005: Clean Layered Architecture](docs/architecture/decisions/005-clean-architecture.md)
- [ADR-006: Structured Logging](docs/architecture/decisions/006-structured-logging.md)

## Installation

Requires Python 3.10 or newer.

```bash
# Clone the repository
git clone https://github.com/trunalpatil/esim-tool-manager.git
cd esim-tool-manager

# Install with GUI support and development tools
pip install -e ".[all]"
```

## Usage (CLI)

```bash
# Check the status of all tools
esim-tool-manager status

# Run a comprehensive health check
esim-tool-manager doctor

# Install the minimal analog profile (dry-run by default)
esim-tool-manager install --profile minimal-analog

# Actually install it
esim-tool-manager install --profile minimal-analog --yes

# List configuration profiles
esim-tool-manager profiles

# View install history
esim-tool-manager history install

# Output status as JSON
esim-tool-manager --json status
```

## Usage (GUI)

To launch the graphical interface:

```bash
python -m esim_tool_manager.gui.app
```

## Development

Run tests using pytest:

```bash
pytest tests/
```

Code quality checks (Ruff, Black, MyPy):

```bash
pre-commit run --all-files
```

## License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details.
