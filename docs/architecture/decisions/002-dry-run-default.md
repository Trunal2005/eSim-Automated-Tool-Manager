# ADR-002: Dry-Run Default for Mutating Operations

## Context
The tool manager executes shell commands with elevated privileges (e.g., `sudo apt-get install`, `brew install`) and modifies user environment variables. Mistakes in these operations can damage a user's system or break existing installations.

## Decision
All operations that mutate system state (install, update, apply-profile) will operate in a "dry-run" mode by default.

## Rationale
- **Safety First**: Users should be able to see exactly what commands the tool manager intends to run before it executes them.
- **Transparency**: Dry-runs build trust. A user can run `esim-tool-manager install` to verify the intended actions without fear of unintended consequences.
- **Explicit Consent**: Real execution requires an explicit flag (`--yes` in the CLI) or a confirmation dialog (in the GUI).

## Consequences
- Every package manager abstraction and installer method must support a `dry_run` parameter.
- The CLI and GUI must present dry-run output clearly, distinguishing it from actual execution output.
