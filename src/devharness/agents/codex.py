"""Codex agent backend.

Spawns the ``codex`` CLI as a subprocess and translates its streaming
JSON output into :class:`AgentEvent` objects.  The interface mirrors
:class:`ClaudeCodeBackend` so the harness can swap backends transparently.
"""

from __future__ import annotations

import logging
import shutil
import signal
from collections.abc import AsyncIterator

import anyio
import anyio.abc

from devharness.agents.base import AgentBackend
from devharness.agents.output_parser import parse_codex_event
from devharness.core.errors import AgentError
from devharness.core.models import AgentConstraints, AgentContext, AgentEvent

logger = logging.getLogger(__name__)

_TERM_GRACE_SECONDS = 5.0


class CodexBackend(AgentBackend):
    """Backend that wraps the ``codex`` CLI as a subprocess.

    Parameters
    ----------
    cli_path:
        Explicit path to the ``codex`` binary.  When *None* the binary is
        resolved via ``$PATH``.
    extra_flags:
        Additional CLI flags appended to every invocation.
    """

    def __init__(
        self,
        cli_path: str | None = None,
        extra_flags: list[str] | None = None,
    ) -> None:
        self._cli_path = cli_path or "codex"
        self._extra_flags = extra_flags or []
        self._process: anyio.abc.Process | None = None

    # --------------------------------------------------------------------- #
    # Prompt construction
    # --------------------------------------------------------------------- #

    @staticmethod
    def _build_prompt(prompt: str, context: AgentContext) -> str:
        """Inject harness context into the prompt text."""
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
            "--prompt",
            prompt,
        ]

        # Codex approval mode mapping
        if constraints.read_only:
            cmd.extend(["--approval-mode", "read-only"])
        elif constraints.approval_mode.value == "full_trust":
            cmd.extend(["--approval-mode", "full-auto"])
        else:
            cmd.extend(["--approval-mode", "suggest"])

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

        logger.info("Starting codex subprocess: %s", " ".join(cmd[:4]) + " ...")

        try:
            self._process = await anyio.open_process(
                cmd,
                stdout=anyio.abc.PIPE,
                stderr=anyio.abc.PIPE,
                cwd=constraints.workspace_root,
            )
        except FileNotFoundError:
            raise AgentError(
                f"codex CLI not found at '{self._cli_path}'. "
                "Install it or set cli_path explicitly."
            )

        assert self._process.stdout is not None  # noqa: S101

        try:
            async for raw_line in self._process.stdout:
                line = raw_line.decode("utf-8", errors="replace")
                event = parse_codex_event(line)
                if event is not None:
                    yield event
        except anyio.ClosedResourceError:
            logger.debug("Codex stdout stream closed.")
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
                    "codex exited with code %d: %s",
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
        """Check that the ``codex`` CLI is reachable."""
        cli = self._cli_path
        if cli == "codex" and shutil.which("codex") is None:
            return False

        try:
            result = await anyio.run_process(
                [cli, "--version"],
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, OSError):
            return False
