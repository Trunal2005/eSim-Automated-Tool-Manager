# ADR-001: Use SQLite for State and History

## Context
The eSim Tool Manager needs to persist its understanding of installed tools, configuration profiles, and the history of installation and update operations. Initially, a JSON or YAML file might seem sufficient for configuration, but maintaining a robust history and querying state requires more structure.

## Decision
We will use SQLite as the primary data store for the tool manager's state.

## Rationale
- **Transactional Integrity**: SQLite supports atomic transactions, preventing corrupt state if the tool manager crashes during an update.
- **Queryability**: A relational model allows us to easily answer questions like "Show me all failed installations of Ngspice in the last month."
- **Zero Configuration**: SQLite requires no separate server process and is built into the Python standard library, making it perfect for a desktop CLI/GUI tool.
- **Schema Evolution**: We can use a numbered migration system to evolve the schema as the tool manager adds features (e.g., managing more complex tool dependencies).

## Consequences
- We must implement a simple migration system (`001_initial.sql`, etc.) to handle database initialization and upgrades.
- The state file will be stored in the user's home directory (e.g., `~/.esim-tool-manager/esim_tools.db`).
