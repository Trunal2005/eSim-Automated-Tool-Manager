# ADR-006: Structured Logging

## Context
The tool manager performs complex operations (installations, updates) that may fail due to unpredictable system states. When failures occur, we need detailed logs for debugging. However, dumping verbose logs to the console creates a poor user experience.

## Decision
We implement a dual-logging strategy:
1. **Console**: Human-readable, color-coded output (via Rich in the CLI) showing high-level progress and warnings.
2. **File**: Machine-parseable JSON-lines format written to a rotating log file in the user's data directory.

## Rationale
- **Debuggability**: JSON-lines logs include rich context (timestamps, log levels, tool IDs, execution times, full tracebacks) that are invaluable for post-mortem analysis.
- **User Experience**: The console remains clean and focused on actionable information.
- **Telemetry Readiness**: JSON-lines logs can be easily aggregated or searched using standard tools (like `jq` or centralized log management systems) if necessary in the future.

## Consequences
- Developers must use the standard `logging` module, which is configured by `infra.logging_config` to route to both handlers appropriately.
- Console formatting is handled separately by the presentation layer (CLI formatters or GUI log windows).
