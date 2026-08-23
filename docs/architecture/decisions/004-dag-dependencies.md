# ADR-004: Directed Acyclic Graph (DAG) for Dependencies

## Context
The eSim toolchain has interdependent components. For example, NGHDL requires both GHDL and Ngspice to be installed first. A simple flat list of tools is insufficient to guarantee correct installation order.

## Decision
We model tool dependencies as a Directed Acyclic Graph (DAG) and use Kahn's algorithm for topological sorting to determine installation order.

## Rationale
- **Correctness**: Topological sorting mathematically guarantees that dependencies are installed before the tools that require them.
- **Validation**: The DAG structure allows us to proactively detect cyclic dependencies or missing transitive dependencies during the `doctor` check.
- **Extensibility**: When new tools are added to eSim with complex dependency chains, the graph model handles them automatically without requiring hardcoded logic changes.

## Consequences
- The `RegistryManager` defines dependencies as lists of tool IDs, which are parsed into a `DependencyGraph` object.
- The `Installer` must always consult the dependency graph before executing a batch installation.
