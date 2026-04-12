"""Base tool abstraction for the harness."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from devharness.core.models import ToolCategory, ToolResult


class BaseTool(ABC):
    """Abstract base class for all tools in the harness.

    Subclasses must define ``name``, ``description``, ``category`` and implement
    ``execute`` and ``get_input_schema``.
    """

    name: str
    description: str
    category: ToolCategory

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given keyword arguments."""

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """Return a JSON Schema dict describing the accepted parameters."""

    # Convenience ----------------------------------------------------------------

    def _ok(self, output: str, **meta: Any) -> ToolResult:
        """Shortcut to build a successful ToolResult."""
        return ToolResult(output=output, metadata=meta)

    def _error(self, message: str, **meta: Any) -> ToolResult:
        """Shortcut to build an error ToolResult."""
        return ToolResult(output=message, is_error=True, metadata=meta)

    def _truncated(self, output: str, max_bytes: int) -> ToolResult:
        """Return a ToolResult truncated to *max_bytes* with a flag."""
        if len(output.encode()) <= max_bytes:
            return self._ok(output)
        truncated = output.encode()[:max_bytes].decode(errors="ignore")
        return ToolResult(output=truncated, truncated=True)

    def to_llm_definition(self) -> dict[str, Any]:
        """Serialise this tool into the dict shape expected by LLM APIs."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
        }
