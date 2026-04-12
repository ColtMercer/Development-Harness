"""Sub-agent pool for delegating lightweight tasks.

The :class:`SubAgentPool` spawns isolated agent instances with restricted
tool sets and returns compressed results.  This is used by the orchestrator
to fan out independent sub-tasks (e.g. from a TaskDAG) without bloating
the primary agent's context window.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

import anyio

from devharness.agents.base import AgentBackend
from devharness.agents.claude_code import ClaudeCodeBackend
from devharness.core.errors import AgentError
from devharness.core.models import (
    AgentConstraints,
    AgentContext,
    AgentEvent,
    ApprovalMode,
    SubAgentConfig,
    SubAgentResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300  # seconds


class SubAgentPool:
    """Manages a pool of lightweight sub-agent invocations.

    Parameters
    ----------
    default_backend:
        The backend used for sub-agents unless ``model_override`` in the
        config selects a different one.
    workspace_root:
        Working directory for sub-agent processes.
    max_concurrency:
        Maximum number of sub-agents that can run in parallel.
    """

    def __init__(
        self,
        default_backend: AgentBackend | None = None,
        workspace_root: str = ".",
        max_concurrency: int = 4,
    ) -> None:
        self._default_backend = default_backend or ClaudeCodeBackend()
        self._workspace_root = workspace_root
        self._max_concurrency = max_concurrency
        self._semaphore = anyio.Semaphore(max_concurrency)

    # --------------------------------------------------------------------- #
    # Backend resolution
    # --------------------------------------------------------------------- #

    def _backend_for_config(self, config: SubAgentConfig) -> AgentBackend:
        """Resolve the backend to use for a given sub-agent config.

        When ``model_override`` is set we create a fresh ClaudeCodeBackend
        with extra flags to select the model.  Otherwise we reuse the
        default backend.
        """
        if config.model_override:
            return ClaudeCodeBackend(
                extra_flags=["--model", config.model_override],
            )
        return self._default_backend

    # --------------------------------------------------------------------- #
    # Single sub-agent execution
    # --------------------------------------------------------------------- #

    async def run_sub_agent(self, config: SubAgentConfig) -> SubAgentResult:
        """Run a single sub-agent task and return a compressed result.

        The sub-agent runs with restricted tools, an isolated context
        (no conversation history), and a hard timeout.
        """
        async with self._semaphore:
            return await self._execute(config)

    async def _execute(self, config: SubAgentConfig) -> SubAgentResult:
        backend = self._backend_for_config(config)
        constraints = AgentConstraints(
            approval_mode=ApprovalMode.FULL_TRUST,
            allowed_tools=config.tools or None,
            workspace_root=self._workspace_root,
            read_only=config.read_only,
        )
        context = AgentContext()

        collected_text: list[str] = []
        tool_calls_count = 0
        start = time.monotonic()

        try:
            with anyio.fail_after(config.timeout or _DEFAULT_TIMEOUT):
                event_iter: AsyncIterator[AgentEvent] = backend.run_task(
                    prompt=config.task,
                    context=context,
                    tools=config.tools,
                    constraints=constraints,
                )
                async for event in event_iter:
                    if event.type == "text":
                        content = event.data.get("content", "")
                        if content:
                            collected_text.append(content)
                    elif event.type == "tool_call":
                        tool_calls_count += 1
                    elif event.type == "done":
                        done_content = event.data.get("content", "")
                        if done_content:
                            collected_text.append(done_content)
                    elif event.type == "error":
                        return SubAgentResult(
                            task=config.task,
                            response="",
                            tool_calls_count=tool_calls_count,
                            duration_ms=(time.monotonic() - start) * 1000,
                            error=event.data.get("message", "unknown error"),
                        )
        except TimeoutError:
            logger.warning("Sub-agent timed out after %ds: %s", config.timeout, config.task[:80])
            await backend.cancel()
            return SubAgentResult(
                task=config.task,
                response="",
                tool_calls_count=tool_calls_count,
                duration_ms=(time.monotonic() - start) * 1000,
                error=f"Sub-agent timed out after {config.timeout}s",
            )
        except AgentError as exc:
            return SubAgentResult(
                task=config.task,
                response="",
                tool_calls_count=tool_calls_count,
                duration_ms=(time.monotonic() - start) * 1000,
                error=str(exc),
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        response = self._compress_response(collected_text, config.response_format)

        return SubAgentResult(
            task=config.task,
            response=response,
            tool_calls_count=tool_calls_count,
            duration_ms=elapsed_ms,
        )

    # --------------------------------------------------------------------- #
    # Batch execution
    # --------------------------------------------------------------------- #

    async def run_batch(
        self,
        configs: list[SubAgentConfig],
    ) -> list[SubAgentResult]:
        """Run multiple sub-agent tasks concurrently (up to max_concurrency).

        Returns results in the same order as the input configs.
        """
        results: list[SubAgentResult | None] = [None] * len(configs)

        async def _run_indexed(index: int, cfg: SubAgentConfig) -> None:
            results[index] = await self.run_sub_agent(cfg)

        async with anyio.create_task_group() as tg:
            for i, cfg in enumerate(configs):
                tg.start_soon(_run_indexed, i, cfg)

        # All slots should be filled; satisfy the type checker.
        return [r for r in results if r is not None]

    # --------------------------------------------------------------------- #
    # Response compression
    # --------------------------------------------------------------------- #

    @staticmethod
    def _compress_response(chunks: list[str], fmt: str) -> str:
        """Join and optionally compress the collected text chunks.

        Parameters
        ----------
        chunks:
            Raw text fragments collected from the sub-agent.
        fmt:
            Response format: ``"summary"`` truncates long output,
            ``"structured"`` and ``"citations"`` pass through as-is.
        """
        full = "".join(chunks).strip()

        if fmt == "summary" and len(full) > 4000:
            # Keep first and last portions for context.
            return full[:2000] + "\n\n[... truncated ...]\n\n" + full[-1500:]

        return full
