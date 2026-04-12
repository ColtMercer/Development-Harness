"""Tests for devharness.tools.registry.ToolRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from devharness.core.errors import ToolNotFoundError
from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool
from devharness.tools.registry import ToolRegistry


class _DummyTool(BaseTool):
    """Minimal concrete tool for testing."""

    def __init__(self, name: str, category: ToolCategory = ToolCategory.READ) -> None:
        self.name = name
        self.description = f"Dummy {name}"
        self.category = category

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(output=f"ran {self.name}")

    def get_input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# Register and get
# ---------------------------------------------------------------------------


class TestRegisterAndGet:
    def test_register_and_get(self) -> None:
        reg = ToolRegistry()
        tool = _DummyTool("my_tool")
        reg.register(tool)

        retrieved = reg.get("my_tool")
        assert retrieved is tool

    def test_get_nonexistent_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent")

    def test_register_overwrites(self) -> None:
        reg = ToolRegistry()
        tool_v1 = _DummyTool("tool", ToolCategory.READ)
        tool_v2 = _DummyTool("tool", ToolCategory.WRITE)
        reg.register(tool_v1)
        reg.register(tool_v2)

        assert reg.get("tool").category == ToolCategory.WRITE

    def test_get_category(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("reader", ToolCategory.READ))
        reg.register(_DummyTool("writer", ToolCategory.WRITE))

        assert reg.get_category("reader") == ToolCategory.READ
        assert reg.get_category("writer") == ToolCategory.WRITE


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_list_empty(self) -> None:
        reg = ToolRegistry()
        assert reg.list_tools() == []

    def test_list_returns_all(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("a"))
        reg.register(_DummyTool("b"))
        reg.register(_DummyTool("c"))

        tools = reg.list_tools()
        names = [t.name for t in tools]
        assert names == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# get_definitions_for_llm with filters
# ---------------------------------------------------------------------------


class TestGetDefinitionsForLLM:
    def _setup_registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        reg.register(_DummyTool("file_read", ToolCategory.READ))
        reg.register(_DummyTool("file_write", ToolCategory.WRITE))
        reg.register(_DummyTool("shell", ToolCategory.EXECUTE))
        reg.register(_DummyTool("search", ToolCategory.READ))
        return reg

    def test_no_filters(self) -> None:
        reg = self._setup_registry()
        defs = reg.get_definitions_for_llm()
        assert len(defs) == 4

    def test_allowed_filter(self) -> None:
        reg = self._setup_registry()
        defs = reg.get_definitions_for_llm(allowed=["file_read", "search"])
        names = [d["name"] for d in defs]
        assert set(names) == {"file_read", "search"}

    def test_denied_filter(self) -> None:
        reg = self._setup_registry()
        defs = reg.get_definitions_for_llm(denied=["shell"])
        names = [d["name"] for d in defs]
        assert "shell" not in names
        assert len(names) == 3

    def test_allowed_and_denied(self) -> None:
        reg = self._setup_registry()
        # denied takes precedence
        defs = reg.get_definitions_for_llm(
            allowed=["file_read", "shell"],
            denied=["shell"],
        )
        names = [d["name"] for d in defs]
        assert names == ["file_read"]

    def test_definition_shape(self) -> None:
        reg = ToolRegistry()
        reg.register(_DummyTool("tool_a"))
        defs = reg.get_definitions_for_llm()
        assert len(defs) == 1
        d = defs[0]
        assert d["name"] == "tool_a"
        assert "description" in d
        assert "input_schema" in d


# ---------------------------------------------------------------------------
# Decorator-based registration
# ---------------------------------------------------------------------------


class TestDecoratorRegistration:
    def test_decorator_registers_tool(self) -> None:
        reg = ToolRegistry()

        @reg.tool("greet", ToolCategory.READ, "Greet a user")
        async def greet(name: str) -> ToolResult:
            return ToolResult(output=f"Hello {name}")

        tool = reg.get("greet")
        assert tool.name == "greet"
        assert tool.category == ToolCategory.READ

    async def test_decorator_tool_executes(self) -> None:
        reg = ToolRegistry()

        @reg.tool("add", ToolCategory.READ, "Add numbers")
        async def add(a: int, b: int) -> ToolResult:
            return ToolResult(output=str(a + b))

        tool = reg.get("add")
        result = await tool.execute(a=2, b=3)
        assert result.output == "5"
