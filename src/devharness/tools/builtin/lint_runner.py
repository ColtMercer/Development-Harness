"""Lint runner tool (ruff)."""

from __future__ import annotations

from typing import Any

import anyio

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool

_MAX_OUTPUT_BYTES = 50 * 1024


class LintRunnerTool(BaseTool):
    """Run ruff check and return linting issues."""

    name = "lint_runner"
    description = "Run ruff check and return lint issues."
    category = ToolCategory.EXECUTE

    async def execute(  # type: ignore[override]
        self,
        *,
        path: str = ".",
        args: list[str] | None = None,
        working_dir: str = ".",
    ) -> ToolResult:
        cmd = ["ruff", "check", path] + (args or [])

        try:
            result = await anyio.run_process(cmd, cwd=working_dir)
        except FileNotFoundError:
            return self._error("ruff is not installed or not on PATH.")
        except Exception as exc:
            return self._error(f"Lint error: {exc}")

        stdout = (result.stdout or b"").decode(errors="replace")
        stderr = (result.stderr or b"").decode(errors="replace")

        combined = stdout
        if stderr:
            combined += f"\n--- stderr ---\n{stderr}"

        output = self._truncated(combined or "No issues found.", _MAX_OUTPUT_BYTES)
        output.metadata["exit_code"] = result.returncode
        output.metadata["clean"] = result.returncode == 0
        if result.returncode not in (0, 1):
            output.is_error = True
        return output

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File or directory to lint.",
                    "default": ".",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional arguments for ruff check.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for lint execution.",
                    "default": ".",
                },
            },
        }
