"""Git status / diff / log tool."""

from __future__ import annotations

from typing import Any

import anyio

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool

_MAX_OUTPUT_BYTES = 50 * 1024

_ALLOWED_SUBCOMMANDS = {"status", "diff", "log", "show", "branch", "stash"}


class GitStatusTool(BaseTool):
    """Run read-only git commands (status, diff, log, etc.)."""

    name = "git_status"
    description = "Run a read-only git subcommand (status, diff, log, show, branch, stash)."
    category = ToolCategory.READ

    async def execute(  # type: ignore[override]
        self,
        *,
        subcommand: str = "status",
        args: list[str] | None = None,
        working_dir: str = ".",
    ) -> ToolResult:
        if subcommand not in _ALLOWED_SUBCOMMANDS:
            return self._error(
                f"Subcommand '{subcommand}' is not allowed. "
                f"Allowed: {', '.join(sorted(_ALLOWED_SUBCOMMANDS))}"
            )

        cmd = ["git", subcommand] + (args or [])

        try:
            result = await anyio.run_process(cmd, cwd=working_dir)
        except Exception as exc:
            return self._error(f"Git error: {exc}")

        stdout = (result.stdout or b"").decode(errors="replace")
        stderr = (result.stderr or b"").decode(errors="replace")

        if result.returncode != 0:
            return self._error(f"git {subcommand} failed (exit {result.returncode}):\n{stderr or stdout}")

        return self._truncated(stdout or "(no output)", _MAX_OUTPUT_BYTES)

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "description": "Git subcommand to run.",
                    "enum": sorted(_ALLOWED_SUBCOMMANDS),
                    "default": "status",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional arguments for the git subcommand.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Repository working directory.",
                    "default": ".",
                },
            },
        }
