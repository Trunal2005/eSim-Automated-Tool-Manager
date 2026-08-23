# ADR-005: Clean Layered Architecture

## Context
This project provides both a Typer-based CLI and a PyQt6-based GUI. If business logic is entangled with the presentation layer, maintaining both interfaces becomes difficult and error-prone.

## Decision
We enforce a strict layered architecture:
1. **Data Layer**: Models, Registry, SQLite DB.
2. **Infrastructure Layer**: OS detection, package managers, subprocess execution, logging.
3. **Core Layer**: Business logic (Installer, Updater, Dependency Checker, Doctor).
4. **Presentation Layer**: CLI (Typer) and GUI (PyQt6).

## Rationale
- **Separation of Concerns**: Core services do not know whether they are being called by a CLI command or a GUI button click.
- **Testability**: Core logic can be unit-tested in isolation without mocking UI components.
- **Maintainability**: Changes to the GUI do not risk breaking the CLI, and vice versa.

## Consequences
- The Presentation Layer must only interact with the Core Layer and Data Models. It cannot bypass the Core Layer to directly manipulate the database or invoke subprocesses.
