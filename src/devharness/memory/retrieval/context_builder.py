"""Memory context builder.

Queries the memory service for relevant decisions, errors, and patterns,
then formats the results as plain text suitable for injection into the
agent's context window.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from devharness.core.models import TaskDAG, Thread
    from devharness.memory.service import MemoryService

logger = logging.getLogger(__name__)


async def build_memory_context(
    thread: Thread,
    task: TaskDAG | str | None,
    memory_service: MemoryService,
) -> str | None:
    """Build a memory context string for injection into agent context.

    Queries the memory service for:
    - Past decisions related to the current task
    - Previously encountered errors in similar contexts
    - Recurring patterns and preferences

    Returns ``None`` when the memory service is unavailable or returns
    no results.
    """
    if not memory_service.available:
        return None

    task_text = _task_description(task)
    query_text = f"thread:{thread.id} {task_text}" if task_text else f"thread:{thread.id}"

    results = await memory_service.search(query_text, limit=10)
    if not results:
        return None

    sections: list[str] = ["## Relevant Memory"]
    for item in results:
        entry = _format_entry(item)
        if entry:
            sections.append(entry)

    if len(sections) <= 1:
        return None

    return "\n\n".join(sections)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _task_description(task: Any) -> str:
    if task is None:
        return ""
    if isinstance(task, str):
        return task
    # TaskDAG
    return getattr(task, "goal", "")


def _format_entry(item: dict[str, Any]) -> str:
    """Format a single memory result dict as a short text block."""
    title = item.get("title", item.get("content", ""))
    kind = item.get("kind", "note")
    details = item.get("details", "")
    if not title:
        return ""
    parts = [f"- **[{kind}]** {title}"]
    if details:
        parts.append(f"  {details}")
    return "\n".join(parts)
