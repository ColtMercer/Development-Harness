"""Hook execution engine.

Runs hook scripts as subprocesses with context injected via environment
variables.  Exit-code semantics:

- **0**: Success.  Output is swallowed (SILENT -- no context pollution).
- **2**: Re-engage.  Stdout is returned to the agent as new context.
- **Other**: Warning logged, execution continues.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import anyio

from devharness.core.models import HookConfig, HookEvent, HookResult

logger = logging.getLogger(__name__)

# Exit code that signals the agent should re-engage with the hook's stdout.
_REENGAGE_EXIT_CODE = 2


class HookEngine:
    """Execute hook scripts as subprocesses."""

    async def run_hooks(
        self,
        event: HookEvent,
        context: dict[str, Any],
        hooks: list[HookConfig],
    ) -> HookResult | None:
        """Run all *hooks* registered for *event* sequentially.

        Returns the first HookResult that requests re-engagement (exit
        code 2), or the last result if none do, or ``None`` if *hooks*
        is empty.

        Parameters
        ----------
        event:
            The lifecycle event that triggered hook execution.
        context:
            Dict of context values exposed to the hook script as
            environment variables (all values are stringified).
        hooks:
            Pre-filtered list of HookConfig objects to execute.
        """
        if not hooks:
            return None

        last_result: HookResult | None = None

        for hook in hooks:
            if not hook.enabled:
                continue

            result = await self._run_single(hook, context)
            last_result = result

            if result.exit_code == _REENGAGE_EXIT_CODE:
                logger.info(
                    "Hook %r requested re-engagement (exit 2)", hook.name
                )
                return result

            if result.exit_code != 0:
                logger.warning(
                    "Hook %r exited with code %d: %s",
                    hook.name,
                    result.exit_code,
                    result.stderr.strip() or "(no stderr)",
                )

        return last_result

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _run_single(
        self,
        hook: HookConfig,
        context: dict[str, Any],
    ) -> HookResult:
        """Execute a single hook script and return its result."""
        env = {k: str(v) for k, v in context.items()}

        start = time.monotonic()
        try:
            result = await anyio.run_process(
                ["sh", "-c", hook.script],
                env=env,
                check=False,
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            return HookResult(
                hook_name=hook.name,
                exit_code=result.returncode,
                stdout=result.stdout.decode("utf-8", errors="replace"),
                stderr=result.stderr.decode("utf-8", errors="replace"),
                duration_ms=elapsed_ms,
            )
        except TimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.warning("Hook %r timed out after %ds", hook.name, hook.timeout)
            return HookResult(
                hook_name=hook.name,
                exit_code=-1,
                stderr=f"Hook timed out after {hook.timeout}s",
                duration_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("Hook %r failed to execute: %s", hook.name, exc)
            return HookResult(
                hook_name=hook.name,
                exit_code=-1,
                stderr=str(exc),
                duration_ms=elapsed_ms,
            )
