"""Built-in tools shipped with the harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devharness.tools.registry import ToolRegistry

from .diff_tool import DiffTool
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .git_status import GitStatusTool
from .lint_runner import LintRunnerTool
from .search import SearchTool
from .shell import ShellTool
from .test_runner import TestRunnerTool


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Instantiate and register every built-in tool."""
    registry.register(ShellTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(SearchTool())
    registry.register(GitStatusTool())
    registry.register(TestRunnerTool())
    registry.register(LintRunnerTool())
    registry.register(DiffTool())
