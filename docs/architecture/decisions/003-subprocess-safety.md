# ADR-003: Strict Subprocess Safety

## Context
The application frequently interacts with the host operating system by invoking external binaries (package managers, version commands, etc.). This introduces security risks (shell injection) and reliability risks (hanging processes).

## Decision
We will enforce strict safety rules for all subprocess invocations via a centralized wrapper (`run_safe`):
1. **Never use `shell=True`**. All commands must be passed as lists of arguments.
2. **Always enforce timeouts**. No command is permitted to run indefinitely.
3. **Capture and structure output**. Never let raw tracebacks leak to the user; always return a structured result.

## Rationale
- Security: Avoiding `shell=True` prevents malicious or accidental shell injection vulnerabilities, especially if any input is ever derived from external sources.
- Reliability: A hung `apt-get` or `brew` process shouldn't freeze the tool manager. Timeouts ensure the application remains responsive.
- User Experience: Wrapping raw exceptions into actionable `SubprocessResult` objects allows the GUI and CLI to present clean, understandable error messages.

## Consequences
- Developers must use `run_safe` instead of calling `subprocess` directly.
- Complex shell pipelines (e.g., `foo | bar`) are not supported natively; logic must be handled in Python.
