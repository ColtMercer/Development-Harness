"""Central registry for tool instances."""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

from devharness.core.errors import ToolNotFoundError
from devharness.core.models import ToolCategory, ToolResult

from .base import BaseTool
from .schema import fn_to_json_schema


class _FunctionTool(BaseTool):
    """Wraps a plain async (or sync) function as a BaseTool."""

    def __init__(
        self,
        fn: Callable[..., Any],
        name: str,
        category: ToolCategory,
        description: str,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self._fn = fn
        self._schema = fn_to_json_schema(fn)

    async def execute(self, **kwargs: Any) -> ToolResult:
        result = self._fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolResult):
            return result
        return ToolResult(output=str(result))

    def get_input_schema(self) -> dict[str, Any]:
        return self._schema


class ToolRegistry:
    """Thread-safe registry that holds all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # -- mutation ---------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.  Overwrites if name already exists."""
        self._tools[tool.name] = tool

    def tool(
        self,
        name: str,
        category: ToolCategory,
        description: str = "",
    ) -> Callable[..., Any]:
        """Decorator that wraps a function and registers it as a tool.

        Usage::

            @registry.tool("my_tool", ToolCategory.READ, "Does a thing")
            async def my_tool(path: str) -> ToolResult:
                ...
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            wrapped = _FunctionTool(fn, name=name, category=category, description=description)
            self.register(wrapped)

            @functools.wraps(fn)
            async def wrapper(**kwargs: Any) -> ToolResult:
                return await wrapped.execute(**kwargs)

            return wrapper

        return decorator

    # -- queries ----------------------------------------------------------------

    def get(self, name: str) -> BaseTool:
        """Return the tool with the given *name* or raise ToolNotFoundError."""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"Tool not found: {name}")

    def get_category(self, name: str) -> ToolCategory:
        """Return the category for tool *name*."""
        return self.get(name).category

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools in insertion order."""
        return list(self._tools.values())

    def get_definitions_for_llm(
        self,
        allowed: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return LLM-ready definitions, filtered by *allowed* / *denied* lists.

        * If *allowed* is set, only those tools are included.
        * If *denied* is set, those tools are excluded.
        * If both are set, *denied* takes precedence.
        """
        tools = self.list_tools()

        if allowed is not None:
            allowed_set = set(allowed)
            tools = [t for t in tools if t.name in allowed_set]

        if denied is not None:
            denied_set = set(denied)
            tools = [t for t in tools if t.name not in denied_set]

        return [t.to_llm_definition() for t in tools]
