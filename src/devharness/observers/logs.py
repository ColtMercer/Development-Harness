"""Log observer -- tails application log files and detects errors.

Parses structured (JSON) and unstructured logs. Reports new error entries
since the last observation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from devharness.core.models import Observation, ObservationSeverity, Thread, Turn
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)

DEFAULT_ERROR_PATTERN = re.compile(
    r"(ERROR|CRITICAL|FATAL|Exception|Traceback|panic|PANIC)", re.IGNORECASE
)
DEFAULT_WARNING_PATTERN = re.compile(
    r"(WARNING|WARN|DeprecationWarning)", re.IGNORECASE
)


class LogObserver(BaseObserver):
    """Tail and parse application log files for errors."""

    name = "logs"

    def __init__(
        self,
        log_paths: list[str] | None = None,
        error_pattern: str | None = None,
        warning_pattern: str | None = None,
    ) -> None:
        self._log_paths = log_paths or []
        self._error_re = re.compile(error_pattern) if error_pattern else DEFAULT_ERROR_PATTERN
        self._warning_re = (
            re.compile(warning_pattern) if warning_pattern else DEFAULT_WARNING_PATTERN
        )
        self._last_positions: dict[str, int] = {}
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Read new log entries since last check and report errors/warnings."""
        observations: list[Observation] = []
        workspace = thread.config.workspace_root

        for log_pattern in self._log_paths:
            log_dir = Path(workspace)
            for log_file in log_dir.glob(log_pattern):
                obs = self._check_log_file(log_file, thread.id, turn)
                observations.extend(obs)

        return observations

    def _check_log_file(
        self, path: Path, thread_id: str, turn: Turn | None
    ) -> list[Observation]:
        """Read new lines from a log file and check for errors."""
        observations: list[Observation] = []
        key = str(path)

        if not path.exists():
            return observations

        last_pos = self._last_positions.get(key, 0)

        try:
            with open(path) as f:
                f.seek(last_pos)
                new_content = f.read(100_000)  # cap at 100KB per check
                self._last_positions[key] = f.tell()
        except OSError:
            return observations

        if not new_content:
            return observations

        for line_num, line in enumerate(new_content.split("\n")):
            if self._error_re.search(line):
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread_id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.ERROR,
                        title=f"Error in {path.name}",
                        details=line[:500],
                        data={"file": str(path), "line": line[:1000]},
                        source_file=str(path),
                    )
                )
            elif self._warning_re.search(line):
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread_id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.WARNING,
                        title=f"Warning in {path.name}",
                        details=line[:500],
                        data={"file": str(path), "line": line[:1000]},
                        source_file=str(path),
                    )
                )

        return observations

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
