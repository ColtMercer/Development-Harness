"""Diff / patch tool."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool


class DiffTool(BaseTool):
    """Generate unified diffs between files or raw strings."""

    name = "diff"
    description = "Generate a unified diff between two files or two strings."
    category = ToolCategory.READ

    async def execute(  # type: ignore[override]
        self,
        *,
        a: str | None = None,
        b: str | None = None,
        file_a: str | None = None,
        file_b: str | None = None,
        context_lines: int = 3,
    ) -> ToolResult:
        # Resolve contents
        try:
            lines_a = self._resolve(a, file_a, label="a/file_a")
            lines_b = self._resolve(b, file_b, label="b/file_b")
        except ValueError as exc:
            return self._error(str(exc))

        label_a = file_a or "a"
        label_b = file_b or "b"

        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=label_a,
            tofile=label_b,
            n=context_lines,
        )
        result = "".join(diff)
        if not result:
            return self._ok("Files are identical.")
        return self._ok(result)

    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(
        raw: str | None,
        file_path: str | None,
        label: str,
    ) -> list[str]:
        if raw is not None:
            return raw.splitlines(keepends=True)
        if file_path is not None:
            p = Path(file_path)
            if not p.exists():
                raise ValueError(f"File not found for {label}: {file_path}")
            return p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        raise ValueError(f"Must provide either a string or file path for {label}.")

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "a": {
                    "type": "string",
                    "description": "First string to diff (mutually exclusive with file_a).",
                },
                "b": {
                    "type": "string",
                    "description": "Second string to diff (mutually exclusive with file_b).",
                },
                "file_a": {
                    "type": "string",
                    "description": "Path to first file (mutually exclusive with a).",
                },
                "file_b": {
                    "type": "string",
                    "description": "Path to second file (mutually exclusive with b).",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Number of context lines around each change.",
                    "default": 3,
                },
            },
        }
