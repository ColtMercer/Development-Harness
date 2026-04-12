"""Repository search tool using ripgrep."""

from __future__ import annotations

from typing import Any

import anyio

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool

_MAX_OUTPUT_BYTES = 50 * 1024


class SearchTool(BaseTool):
    """Search for patterns in files using ripgrep (rg)."""

    name = "search"
    description = "Search for a regex pattern in files using ripgrep."
    category = ToolCategory.READ

    async def execute(  # type: ignore[override]
        self,
        *,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        case_insensitive: bool = False,
        max_results: int = 200,
    ) -> ToolResult:
        cmd = ["rg", "--line-number", "--no-heading", f"--max-count={max_results}"]

        if case_insensitive:
            cmd.append("-i")
        if glob:
            cmd.extend(["--glob", glob])

        cmd.extend([pattern, path])

        try:
            result = await anyio.run_process(cmd)
        except FileNotFoundError:
            return self._error("ripgrep (rg) is not installed or not on PATH.")
        except Exception as exc:
            return self._error(f"Search error: {exc}")

        stdout = (result.stdout or b"").decode(errors="replace")
        stderr = (result.stderr or b"").decode(errors="replace")

        if result.returncode == 1:
            return self._ok("No matches found.")
        if result.returncode not in (0, 1):
            return self._error(f"rg exited with code {result.returncode}: {stderr}")

        return self._truncated(stdout, _MAX_OUTPUT_BYTES)

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in.",
                    "default": ".",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py').",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Whether to ignore case.",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching lines per file.",
                    "default": 200,
                },
            },
            "required": ["pattern"],
        }
