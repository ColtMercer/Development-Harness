"""Shell command execution tool."""

from __future__ import annotations

from typing import Any

import anyio

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool

_MAX_OUTPUT_BYTES = 50 * 1024  # 50 KB


class ShellTool(BaseTool):
    """Run a shell command and capture its output."""

    name = "shell"
    description = "Execute a shell command and return stdout/stderr."
    category = ToolCategory.EXECUTE

    async def execute(  # type: ignore[override]
        self,
        *,
        command: str,
        working_dir: str = ".",
        timeout: int = 120,
    ) -> ToolResult:
        try:
            result = await anyio.run_process(
                ["bash", "-c", command],
                cwd=working_dir,
                stdout=anyio.PIPE if hasattr(anyio, "PIPE") else None,
                stderr=anyio.PIPE if hasattr(anyio, "PIPE") else None,
            )
        except Exception as exc:
            return self._error(f"Shell error: {exc}")

        stdout = (result.stdout or b"").decode(errors="replace")
        stderr = (result.stderr or b"").decode(errors="replace")

        combined = stdout
        if stderr:
            combined += f"\n--- stderr ---\n{stderr}"

        output = self._truncated(combined, _MAX_OUTPUT_BYTES)
        output.metadata["exit_code"] = result.returncode
        if result.returncode != 0:
            output.is_error = True
        return output

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command.",
                    "default": ".",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds.",
                    "default": 120,
                },
            },
            "required": ["command"],
        }
