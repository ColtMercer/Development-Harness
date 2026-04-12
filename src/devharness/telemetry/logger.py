"""Structured JSON logging.

Provides a :class:`StructuredFormatter` that outputs one JSON object per
log line, and a convenience :func:`setup_logging` function to configure
the root logger.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Logging formatter that emits JSON lines.

    Each log record is serialised as a single JSON object containing
    at minimum ``timestamp``, ``level``, ``logger``, and ``message``
    keys. Extra attributes attached to the record are merged in.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        # Merge any extra fields set via ``logger.info("msg", extra={...})``
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in (
                "name", "msg", "args", "created", "relativeCreated",
                "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "pathname", "filename", "module", "levelno", "levelname",
                "msecs", "thread", "threadName", "process", "processName",
                "taskName", "message",
            ):
                continue
            entry[key] = value

        return json.dumps(entry, default=str)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Configure the root logger with structured JSON output to stderr.

    Parameters
    ----------
    level:
        Logging level (int or string like ``"DEBUG"``).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers on repeated calls.
    for handler in root.handlers[:]:
        if isinstance(handler.formatter, StructuredFormatter):
            return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)
