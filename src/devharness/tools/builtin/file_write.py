"""File write tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool


class FileWriteTool(BaseTool):
    """Write content to a file, creating parent directories if needed."""

    name = "file_write"
    description = "Write content to a file. Creates parent directories as needed."
    category = ToolCategory.WRITE

    async def execute(  # type: ignore[override]
        self,
        *,
        path: str,
        content: str,
        create_parents: bool = True,
    ) -> ToolResult:
        target = Path(path)

        try:
            if create_parents:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except Exception as exc:
            return self._error(f"Write error: {exc}")

        return self._ok(
            f"Wrote {len(content)} bytes to {path}",
            bytes_written=len(content.encode("utf-8")),
        )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to write to.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
                "create_parents": {
                    "type": "boolean",
                    "description": "Create parent directories if they do not exist.",
                    "default": True,
                },
            },
            "required": ["path", "content"],
        }
