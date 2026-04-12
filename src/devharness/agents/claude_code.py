"""Claude Code agent backend.

Spawns the ``claude`` CLI as a subprocess with ``--output-format stream-json``
and translates the streaming JSON into :class:`AgentEvent` objects.
"""

from __future__ import annotations

import logging
import shutil
import signal
from collections.abc import AsyncIterator

import anyio
import anyio.abc

from devharness.agents.base import AgentBackend
from devharness.agents.output_parser import parse_claude_code_event
from devharness.core.errors import AgentError
from devharness.core.models import AgentConstraints, AgentContext, AgentEvent

logger = logging.getLogger(__name__)

_TERM_GRACE_SECONDS = 5.0


class ClaudeCodeBackend(AgentBackend):
    """Backend that wraps the ``claude`` CLI as a subprocess.

    Parameters
    ----------
    cli_path:
        Explicit path to the ``claude`` binary.  When *None* the binary is
        resolved via ``$PATH``.
    extra_flags:
        Additional CLI flags appended to every invocation.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        extra_flags: list[str] | None = None,
    ) -> None:
        self._cli_path = cli_path or "claude"
        self._extra_flags = extra_flags or []
        self._process: anyio.abc.Process | None = None

    # --------------------------------------------------------------------- #
    # Prompt construction
    # --------------------------------------------------------------------- #

    @staticmethod
    def _build_prompt(prompt: str, context: AgentContext) -> str:
        """Inject harness context into the prompt text.

        The harness prepends system-level information (skill prompts,
        observation summaries, memory context) so the agent can act on
        real-time project state without extra tool calls.
        """
        sections: list[str] = []

        if context.system_prompt:
            sections.append(f"<system-context>\n{context.system_prompt}\n</system-context>")

        if context.instructions:
            joined = "\n".join(f"- {i}" for i in context.instructions)
            sections.append(f"<instructions>\n{joined}\n</instructions>")

        if context.observation_summary:
            sections.append(
                f"<observations>\n{context.observation_summary}\n</observations>"
            )

        if context.memory_context:
            sections.append(
                f"<memory-context>\n{context.memory_context}\n</memory-context>"
            )

        if sections:
            preamble = "\n\n".join(sections)
            return f"{preamble}\n\n{prompt}"
        return prompt

    # --------------------------------------------------------------------- #
    # Command construction
    # --------------------------------------------------------------------- #

    def _build_command(
        self,
        prompt: str,
        constraints: AgentConstraints,
    ) -> list[str]:
        cmd = [
            self._cli_path,
            "--output-format",
            "stream-json",
            "--no-input",
            "-p",
            prompt,
        ]

        if constraints.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(constraints.allowed_tools)])

        if constraints.denied_tools:
            cmd.extend(["--disallowedTools", ",".join(constraints.denied_tools)])

        cmd.extend(self._extra_flags)
        return cmd

    # --------------------------------------------------------------------- #
    # Core interface
    # --------------------------------------------------------------------- #

    async def run_task(
        self,
        prompt: str,
        context: AgentContext,
        tools: list[str],
        constraints: AgentConstraints,
    ) -> AsyncIterator[AgentEvent]:
        full_prompt = self._build_prompt(prompt, context)
        cmd = self._build_command(full_prompt, constraints)

        logger.info("Starting claude subprocess: %s", " ".join(cmd[:4]) + " ...")

        try:
            self._process = await anyio.open_process(
                cmd,
                stdout=anyio.abc.PIPE,
                stderr=anyio.abc.PIPE,
                cwd=constraints.workspace_root,
            )
        except FileNotFoundError:
            raise AgentError(
                f"claude CLI not found at '{self._cli_path}'. "
                "Install it or set cli_path explicitly."
            )

        assert self._process.stdout is not None  # noqa: S101

        try:
            async for raw_line in self._process.stdout:
                line = raw_line.decode("utf-8", errors="replace")
                event = parse_claude_code_event(line)
                if event is not None:
                    yield event
        except anyio.ClosedResourceError:
            logger.debug("Claude Code stdout stream closed.")
        finally:
            await self._drain_and_wait()

    async def _drain_and_wait(self) -> None:
        """Wait for the subprocess to exit and log stderr if present."""
        proc = self._process
        if proc is None:
            return

        try:
            stderr_bytes = b""
            if proc.stderr is not None:
                try:
                    stderr_bytes = await proc.stderr.receive()
                except (anyio.ClosedResourceError, anyio.EndOfStream):
                    pass
            await proc.wait()
            if proc.returncode and proc.returncode != 0:
                logger.warning(
                    "claude exited with code %d: %s",
                    proc.returncode,
                    stderr_bytes.decode("utf-8", errors="replace")[:500],
                )
        except Exception:
            logger.debug("Error during subprocess cleanup", exc_info=True)
        finally:
            self._process = None

    async def cancel(self) -> None:
        """Send SIGTERM to the running subprocess, then SIGKILL if needed."""
        proc = self._process
        if proc is None:
            return

        try:
            proc.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            self._process = None
            return

        with anyio.move_on_after(_TERM_GRACE_SECONDS):
            await proc.wait()
            self._process = None
            return

        # Still alive after grace period -- force kill.
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        self._process = None

    async def health_check(self) -> bool:
        """Check that the ``claude`` CLI is reachable by running ``--version``."""
        cli = self._cli_path
        if cli == "claude" and shutil.which("claude") is None:
            return False

        try:
            result = await anyio.run_process(
                [cli, "--version"],
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError):
            return False
