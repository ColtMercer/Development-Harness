"""File read tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool


class FileReadTool(BaseTool):
    """Read the contents of a file with optional line range."""

    name = "file_read"
    description = "Read a file's contents, optionally returning a specific line range."
    category = ToolCategory.READ

    async def execute(  # type: ignore[override]
        self,
        *,
        path: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ToolResult:
        target = Path(path)
        if not target.exists():
            return self._error(f"File not found: {path}")
        if not target.is_file():
            return self._error(f"Not a file: {path}")

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._error(f"Read error: {exc}")

        lines = text.splitlines(keepends=True)
        total = len(lines)

        if offset > 0:
            lines = lines[offset:]
        if limit is not None:
            lines = lines[:limit]

        content = "".join(lines)
        return self._ok(
            content,
            total_lines=total,
            offset=offset,
            limit=limit,
        )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-based).",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return.",
                },
            },
            "required": ["path"],
        }
