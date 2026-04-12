"""Test runner tool (pytest)."""

from __future__ import annotations

from typing import Any

import anyio

from devharness.core.models import ToolCategory, ToolResult
from devharness.tools.base import BaseTool

_MAX_OUTPUT_BYTES = 50 * 1024


class TestRunnerTool(BaseTool):
    """Run pytest with configurable arguments and return the output."""

    name = "test_runner"
    description = "Run pytest and return test results."
    category = ToolCategory.EXECUTE

    async def execute(  # type: ignore[override]
        self,
        *,
        args: list[str] | None = None,
        working_dir: str = ".",
        timeout: int = 300,
    ) -> ToolResult:
        cmd = ["python", "-m", "pytest"] + (args or [])

        try:
            result = await anyio.run_process(cmd, cwd=working_dir)
        except Exception as exc:
            return self._error(f"Test runner error: {exc}")

        stdout = (result.stdout or b"").decode(errors="replace")
        stderr = (result.stderr or b"").decode(errors="replace")

        combined = stdout
        if stderr:
            combined += f"\n--- stderr ---\n{stderr}"

        output = self._truncated(combined, _MAX_OUTPUT_BYTES)
        output.metadata["exit_code"] = result.returncode
        output.metadata["passed"] = result.returncode == 0
        if result.returncode != 0:
            output.is_error = True
        return output

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments passed to pytest (e.g. ['-v', 'tests/']).",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for test execution.",
                    "default": ".",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds for the test run.",
                    "default": 300,
                },
            },
        }
