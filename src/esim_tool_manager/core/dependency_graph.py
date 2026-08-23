"""Dependency graph for the eSim toolchain.

Models inter-tool dependencies as a Directed Acyclic Graph (DAG) and provides
topological sorting for correct install ordering. For example, NGHDL depends
on both GHDL and Ngspice, so those must be installed first.

Design Decision (ADR-004): A dependency graph (DAG) is used instead of a flat
list because:
1. It enables correct install ordering via topological sort.
2. It surfaces transitive dependency issues (e.g. "GHDL is missing, which
   blocks NGHDL") as specific, actionable error messages.
3. It generalizes cleanly to future tools without code changes.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from esim_tool_manager.data.models import DependencyIssue, Severity, Tool

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """Raised when a cycle is detected in the dependency graph."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        cycle_str = " → ".join(cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_str}")


class DependencyGraph:
    """A directed acyclic graph (DAG) modeling inter-tool dependencies.

    Nodes are tool IDs; directed edges go from a tool to each of its
    dependencies (i.e., an edge A → B means "A depends on B, so B must
    be installed before A").

    Args:
        tools: List of Tool objects to build the graph from.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        # Adjacency list: tool_id -> set of dependency tool_ids
        self._dependencies: dict[str, set[str]] = defaultdict(set)
        # Reverse adjacency: tool_id -> set of tool_ids that depend on it
        self._dependents: dict[str, set[str]] = defaultdict(set)
        # All known tool IDs
        self._nodes: set[str] = set()

        if tools:
            for tool in tools:
                self.add_tool(tool)

    def add_tool(self, tool: Tool) -> None:
        """Add a tool and its dependencies to the graph.

        Args:
            tool: The Tool object to add.
        """
        self._nodes.add(tool.id)
        for dep_id in tool.dependencies:
            self._dependencies[tool.id].add(dep_id)
            self._dependents[dep_id].add(tool.id)
            self._nodes.add(dep_id)

    @property
    def nodes(self) -> set[str]:
        """All tool IDs in the graph."""
        return self._nodes.copy()

    def get_dependencies(self, tool_id: str) -> set[str]:
        """Get direct dependencies of a tool.

        Args:
            tool_id: The tool to query.

        Returns:
            Set of tool IDs that this tool directly depends on.
        """
        return self._dependencies.get(tool_id, set()).copy()

    def get_all_dependencies(self, tool_id: str) -> set[str]:
        """Get all transitive dependencies of a tool (depth-first).

        Args:
            tool_id: The tool to query.

        Returns:
            Set of all tool IDs that this tool transitively depends on.

        Raises:
            CyclicDependencyError: If a cycle is detected.
        """
        visited: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            if node in path:
                cycle_start = path.index(node)
                raise CyclicDependencyError(path[cycle_start:] + [node])
            if node in visited:
                return
            path.append(node)
            for dep in self._dependencies.get(node, set()):
                dfs(dep)
            path.pop()
            visited.add(node)

        dfs(tool_id)
        visited.discard(tool_id)  # Don't include the tool itself
        return visited

    def get_dependents(self, tool_id: str) -> set[str]:
        """Get tools that directly depend on the given tool.

        Args:
            tool_id: The tool to query.

        Returns:
            Set of tool IDs that directly depend on this tool.
        """
        return self._dependents.get(tool_id, set()).copy()

    def get_all_dependents(self, tool_id: str) -> set[str]:
        """Get all tools that transitively depend on the given tool.

        Args:
            tool_id: The tool to query.

        Returns:
            Set of all tool IDs that transitively depend on this tool.
        """
        visited: set[str] = set()
        queue = deque(self._dependents.get(tool_id, set()))

        while queue:
            node = queue.popleft()
            if node not in visited:
                visited.add(node)
                queue.extend(self._dependents.get(node, set()) - visited)

        return visited

    def topological_sort(self) -> list[str]:
        """Return tool IDs in topological order (dependencies first).

        Uses Kahn's algorithm for a stable, deterministic sort.

        Returns:
            List of tool IDs sorted so that each tool appears after all
            of its dependencies.

        Raises:
            CyclicDependencyError: If the graph contains a cycle.
        """
        # Compute in-degrees
        in_degree: dict[str, int] = {node: 0 for node in self._nodes}
        for node, deps in self._dependencies.items():
            for dep in deps:
                if dep in in_degree:
                    # node depends on dep, so node's in-degree isn't affected,
                    # but we need edges from dep -> node in the install-order graph
                    pass

        # In the install-order graph, edges go dependency → dependent
        # So in-degree = number of dependencies a tool has
        for node in self._nodes:
            in_degree[node] = len(
                self._dependencies.get(node, set()) & self._nodes
            )

        # Start with tools that have no dependencies
        queue: deque[str] = deque(
            sorted(node for node, deg in in_degree.items() if deg == 0)
        )
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)

            # For each tool that depends on this node, reduce its in-degree
            for dependent in sorted(self._dependents.get(node, set())):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) != len(self._nodes):
            # Some nodes weren't processed — there's a cycle
            remaining = self._nodes - set(result)
            raise CyclicDependencyError(sorted(remaining))

        return result

    def validate(
        self, installed_tool_ids: set[str] | None = None
    ) -> list[DependencyIssue]:
        """Validate the dependency graph for issues.

        Checks for:
        - References to tools not in the graph
        - Cycles (caught as CyclicDependencyError)
        - Missing dependencies for installed tools (if installed_tool_ids provided)

        Args:
            installed_tool_ids: Optional set of tool IDs that are currently installed.
                If provided, checks that all dependencies of installed tools are
                also installed.

        Returns:
            List of DependencyIssue objects describing any problems found.
        """
        issues: list[DependencyIssue] = []

        # Check for references to unknown tools
        for tool_id, deps in self._dependencies.items():
            for dep_id in deps:
                if dep_id not in self._nodes:
                    issues.append(
                        DependencyIssue(
                            tool_id=tool_id,
                            dependency_id=dep_id,
                            severity=Severity.ERROR,
                            message=f"Tool '{tool_id}' depends on '{dep_id}', "
                            f"which is not registered in the tool registry.",
                        )
                    )

        # Check for cycles
        try:
            self.topological_sort()
        except CyclicDependencyError as e:
            for tool_id in e.cycle[:-1]:
                issues.append(
                    DependencyIssue(
                        tool_id=tool_id,
                        dependency_id=tool_id,
                        severity=Severity.CRITICAL,
                        message=f"Cyclic dependency detected involving '{tool_id}': "
                        f"{' → '.join(e.cycle)}",
                    )
                )

        # Check installed tools have their dependencies satisfied
        if installed_tool_ids is not None:
            for tool_id in installed_tool_ids:
                for dep_id in self._dependencies.get(tool_id, set()):
                    if dep_id not in installed_tool_ids:
                        issues.append(
                            DependencyIssue(
                                tool_id=tool_id,
                                dependency_id=dep_id,
                                severity=Severity.WARNING,
                                message=f"Tool '{tool_id}' depends on '{dep_id}', "
                                f"which is not installed. "
                                f"'{tool_id}' may not function correctly.",
                            )
                        )

        return issues

    def get_install_order(self, tool_ids: list[str]) -> list[str]:
        """Get the install order for a specific set of tools.

        Given a list of tools the user wants installed, this returns the
        full set of tools (including transitive dependencies) in the
        correct install order.

        Args:
            tool_ids: List of tool IDs the user wants installed.

        Returns:
            List of tool IDs in correct install order, including any
            transitive dependencies not in the original list.
        """
        # Collect all transitive dependencies
        all_needed: set[str] = set(tool_ids)
        for tool_id in tool_ids:
            all_needed |= self.get_all_dependencies(tool_id)

        # Get the full topological sort and filter to only needed tools
        full_order = self.topological_sort()
        return [tid for tid in full_order if tid in all_needed]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dictionary for JSON output."""
        return {
            "nodes": sorted(self._nodes),
            "edges": {
                tool_id: sorted(deps)
                for tool_id, deps in sorted(self._dependencies.items())
                if deps
            },
        }
