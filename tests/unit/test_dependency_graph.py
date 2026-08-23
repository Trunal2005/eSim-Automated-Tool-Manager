"""Unit tests for the dependency graph."""

import pytest

from esim_tool_manager.data.models import Tool, ToolCategory
from esim_tool_manager.core.dependency_graph import CyclicDependencyError, DependencyGraph


def _make_tool(tool_id: str, deps: list[str] | None = None) -> Tool:
    """Helper to create a minimal Tool for graph testing."""
    return Tool(
        id=tool_id,
        display_name=tool_id.title(),
        description=f"Test tool {tool_id}",
        category=ToolCategory.SYSTEM,
        version_command=[tool_id, "--version"],
        version_regex=r"(\d+\.\d+)",
        min_version="1.0",
        known_good_version="2.0",
        dependencies=deps or [],
    )


class TestDependencyGraphBasics:
    """Tests for basic graph operations."""

    def test_empty_graph(self) -> None:
        graph = DependencyGraph()
        assert len(graph.nodes) == 0
        assert graph.topological_sort() == []

    def test_single_node_no_deps(self) -> None:
        graph = DependencyGraph([_make_tool("ngspice")])
        assert "ngspice" in graph.nodes
        assert graph.get_dependencies("ngspice") == set()
        assert graph.topological_sort() == ["ngspice"]

    def test_two_independent_nodes(self) -> None:
        graph = DependencyGraph([
            _make_tool("ngspice"),
            _make_tool("kicad"),
        ])
        order = graph.topological_sort()
        assert set(order) == {"ngspice", "kicad"}
        assert len(order) == 2

    def test_simple_dependency(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("nghdl", deps=["ghdl"]),
        ])
        order = graph.topological_sort()
        assert order.index("ghdl") < order.index("nghdl")

    def test_multiple_dependencies(self) -> None:
        """NGHDL depends on both GHDL and Ngspice."""
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("ngspice"),
            _make_tool("nghdl", deps=["ghdl", "ngspice"]),
        ])
        order = graph.topological_sort()
        assert order.index("ghdl") < order.index("nghdl")
        assert order.index("ngspice") < order.index("nghdl")


class TestTransitiveDependencies:
    """Tests for transitive dependency resolution."""

    def test_get_all_dependencies(self) -> None:
        """A → B → C: A transitively depends on C."""
        graph = DependencyGraph([
            _make_tool("c"),
            _make_tool("b", deps=["c"]),
            _make_tool("a", deps=["b"]),
        ])
        all_deps = graph.get_all_dependencies("a")
        assert all_deps == {"b", "c"}

    def test_get_all_dependents(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("nghdl", deps=["ghdl"]),
        ])
        dependents = graph.get_all_dependents("ghdl")
        assert "nghdl" in dependents

    def test_diamond_dependency(self) -> None:
        """Diamond: D depends on B and C, both depend on A."""
        graph = DependencyGraph([
            _make_tool("a"),
            _make_tool("b", deps=["a"]),
            _make_tool("c", deps=["a"]),
            _make_tool("d", deps=["b", "c"]),
        ])
        order = graph.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

        all_deps = graph.get_all_dependencies("d")
        assert all_deps == {"a", "b", "c"}


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_direct_cycle(self) -> None:
        graph = DependencyGraph([
            _make_tool("a", deps=["b"]),
            _make_tool("b", deps=["a"]),
        ])
        with pytest.raises(CyclicDependencyError):
            graph.topological_sort()

    def test_indirect_cycle(self) -> None:
        graph = DependencyGraph([
            _make_tool("a", deps=["b"]),
            _make_tool("b", deps=["c"]),
            _make_tool("c", deps=["a"]),
        ])
        with pytest.raises(CyclicDependencyError):
            graph.topological_sort()

    def test_get_all_dependencies_detects_cycle(self) -> None:
        graph = DependencyGraph([
            _make_tool("a", deps=["b"]),
            _make_tool("b", deps=["a"]),
        ])
        with pytest.raises(CyclicDependencyError):
            graph.get_all_dependencies("a")


class TestInstallOrder:
    """Tests for install order computation."""

    def test_install_order_includes_transitive_deps(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("ngspice"),
            _make_tool("nghdl", deps=["ghdl", "ngspice"]),
            _make_tool("kicad"),
        ])
        # User wants nghdl — should get ghdl and ngspice first
        order = graph.get_install_order(["nghdl"])
        assert "ghdl" in order
        assert "ngspice" in order
        assert "nghdl" in order
        assert "kicad" not in order  # Not requested, not a dependency
        assert order.index("ghdl") < order.index("nghdl")
        assert order.index("ngspice") < order.index("nghdl")

    def test_install_order_deduplicates(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("ngspice"),
            _make_tool("nghdl", deps=["ghdl", "ngspice"]),
        ])
        order = graph.get_install_order(["nghdl", "ghdl"])
        # ghdl should appear only once
        assert order.count("ghdl") == 1


class TestValidation:
    """Tests for dependency graph validation."""

    def test_valid_graph_no_issues(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("ngspice"),
            _make_tool("nghdl", deps=["ghdl", "ngspice"]),
        ])
        issues = graph.validate()
        assert len(issues) == 0

    def test_missing_dependency_warning(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("ngspice"),
            _make_tool("nghdl", deps=["ghdl", "ngspice"]),
        ])
        # nghdl is installed but ghdl is not
        issues = graph.validate(installed_tool_ids={"nghdl", "ngspice"})
        assert len(issues) >= 1
        assert any(
            i.dependency_id == "ghdl" and i.tool_id == "nghdl" for i in issues
        )

    def test_to_dict(self) -> None:
        graph = DependencyGraph([
            _make_tool("ghdl"),
            _make_tool("nghdl", deps=["ghdl"]),
        ])
        data = graph.to_dict()
        assert "nodes" in data
        assert "edges" in data
        assert "ghdl" in data["nodes"]
        assert "nghdl" in data["nodes"]
        assert data["edges"]["nghdl"] == ["ghdl"]
