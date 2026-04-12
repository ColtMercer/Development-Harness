"""Abstract base class for agent backends.

All agent backends (Claude Code, Codex, etc.) implement this interface
so the harness can swap them without touching orchestration logic.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator

from devharness.core.models import AgentConstraints, AgentContext, AgentEvent


class AgentBackend(abc.ABC):
    """Pluggable backend that wraps a CLI-based agent as a subprocess."""

    @abc.abstractmethod
    async def run_task(
        self,
        prompt: str,
        context: AgentContext,
        tools: list[str],
        constraints: AgentConstraints,
    ) -> AsyncIterator[AgentEvent]:
        """Execute a task and yield structured events as they arrive.

        Parameters
        ----------
        prompt:
            The user/harness prompt to send to the agent.
        context:
            Harness context (system prompt, observations, memory, etc.).
        tools:
            List of tool names available to the agent.
        constraints:
            Approval mode, allowed/denied tools, workspace restrictions.

        Yields
        ------
        AgentEvent
            Structured events parsed from the agent's streaming output.
        """
        ...  # pragma: no cover
        # Make the function an async generator so type checkers are happy.
        if False:  # noqa: SIM108 -- unreachable yield for typing
            yield AgentEvent(type="never")  # type: ignore[misc]

    @abc.abstractmethod
    async def cancel(self) -> None:
        """Cancel the currently-running agent subprocess (if any).

        Implementations should send SIGTERM, wait briefly, then SIGKILL
        if the process has not exited.
        """

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the agent CLI is available and functional.

        Typically runs ``<cli> --version`` or equivalent and checks the
        exit code.
        """
