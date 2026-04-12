"""Build observer -- watches build system output for compile/type errors."""

from __future__ import annotations

import logging

import anyio

from devharness.core.models import Observation, ObservationSeverity, Thread, Turn
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class BuildObserver(BaseObserver):
    """Watch build system for compilation and type errors."""

    name = "build"

    def __init__(self, build_command: str = "python -m py_compile") -> None:
        self._build_command = build_command
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        observations: list[Observation] = []
        workspace = thread.config.workspace_root

        try:
            result = await anyio.run_process(
                ["bash", "-c", self._build_command],
                cwd=workspace,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="replace")[:10_000]
                stdout = result.stdout.decode(errors="replace")[:10_000]
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.ERROR,
                        title="Build failed",
                        details=(stderr or stdout)[:2000],
                        data={"returncode": result.returncode},
                    )
                )
        except Exception as e:
            logger.warning("Build observer failed: %s", e)

        return observations

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
